#!/usr/bin/env python3
"""Edge camera bridge for Windows edge station testing.

Provides:
- GET  /api/health
- GET  /api/camera/frame?station_id=S01
- POST /api/button/press   {"station_id":"S01"}
- GET  /api/button/next?station_id=S01

Camera source modes:
- mock   : synthetic frame (no camera dependency)
- opencv : local camera index via cv2.VideoCapture
- rtsp   : RTSP stream via cv2.VideoCapture
- mvs    : HikRobot MVS SDK via MvCameraControl_class
- auto   : opencv if cv2 available, otherwise mvs/mock
"""

from __future__ import annotations

import io
import importlib
import logging
import os
import sys
import threading
import time
from collections import defaultdict, deque
from ctypes import POINTER, byref, cast, c_ubyte, memset, sizeof
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Optional
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, redirect, request, send_file, send_from_directory
from PIL import Image, ImageDraw, ImageFont
try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


LOGGER = logging.getLogger("edge_camera_bridge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = Flask(__name__)
_EVENT_LOCK = threading.Lock()
_BUTTON_EVENTS: Dict[str, Deque[dict]] = defaultdict(deque)
UI_ROOT = Path(__file__).resolve().parent / "edge_ui"


def _normalize_mes_base(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if not text.startswith("http://") and not text.startswith("https://"):
        text = f"http://{text}"
    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


class MESAPIProxy:
    def __init__(self, base_url: str = ""):
        self.base_url = _normalize_mes_base(base_url)
        self.lock = threading.Lock()
        self.session = requests.Session() if requests is not None else None
        self.logged_in = False
        self.projects_read_permission = False
        self.web_qc_permission = False
        self.mobile_qc_permission = False
        # backward-compatible alias for old frontend bundles
        self.qc_api_permission = False
        self.username = ""
        self.protocol = ""
        self.last_error = ""
        self.last_login_at = ""

    def set_base_url(self, base_url: str) -> str:
        normalized = _normalize_mes_base(base_url)
        if not normalized:
            return ""
        with self.lock:
            self.base_url = normalized
        return normalized

    def status_payload(self) -> dict:
        with self.lock:
            return {
                "requests_enabled": requests is not None,
                "mes_base": self.base_url,
                "logged_in": self.logged_in,
                "projects_read_permission": bool(self.projects_read_permission),
                "web_qc_permission": bool(self.web_qc_permission),
                "mobile_qc_permission": bool(self.mobile_qc_permission),
                "qc_api_permission": bool(self.qc_api_permission),
                "username": self.username,
                "protocol": self.protocol,
                "last_login_at": self.last_login_at,
                "last_error": self.last_error,
            }

    def logout(self) -> None:
        if requests is None:
            return
        with self.lock:
            old = self.session
            self.session = requests.Session()
            self.logged_in = False
            self.projects_read_permission = False
            self.web_qc_permission = False
            self.mobile_qc_permission = False
            self.qc_api_permission = False
            self.username = ""
            self.protocol = ""
            self.last_login_at = ""
            self.last_error = ""
        if old is not None:
            try:
                if self.base_url:
                    old.get(f"{self.base_url}/logout", timeout=6)
            except Exception:
                pass

    def login(self, mes_base: str, username: str, password: str, protocol: str) -> tuple[bool, str]:
        if requests is None:
            return False, "缺少 requests 依赖，请重新安装边缘包依赖"

        normalized_base = _normalize_mes_base(mes_base) if mes_base else ""
        user = str(username or "").strip()
        pwd = str(password or "").strip()
        proto = str(protocol or "smb").strip().lower() or "smb"
        if proto not in {"smb", "webdav"}:
            proto = "smb"

        if not normalized_base:
            with self.lock:
                normalized_base = self.base_url
        if not normalized_base:
            return False, "MES 地址不能为空"
        if not user or not pwd:
            return False, "用户名和密码不能为空"

        new_session = requests.Session()
        try:
            _ = new_session.post(
                f"{normalized_base}/login",
                data={
                    "username": user,
                    "password": pwd,
                    "protocol": proto,
                },
                timeout=15,
                allow_redirects=True,
            )
            qc_verify_resp = new_session.get(
                f"{normalized_base}/api/projects",
                timeout=15,
                allow_redirects=False,
            )
        except Exception as exc:
            err = f"连接 MES 失败: {exc}"
            with self.lock:
                self.last_error = err
                self.logged_in = False
                self.projects_read_permission = False
                self.web_qc_permission = False
                self.mobile_qc_permission = False
                self.qc_api_permission = False
            return False, err

        session_check_status = int(qc_verify_resp.status_code or 0)
        location = str(qc_verify_resp.headers.get("Location") or "")
        if session_check_status in (301, 302) and "/login" in location:
            message = "MES 会话未建立，请检查账号密码"
            with self.lock:
                self.logged_in = False
                self.projects_read_permission = False
                self.web_qc_permission = False
                self.mobile_qc_permission = False
                self.qc_api_permission = False
                self.username = ""
                self.protocol = ""
                self.last_login_at = ""
                self.last_error = message
            return False, message
        if session_check_status == 401:
            message = "MES 鉴权失败，请检查账号密码"
            with self.lock:
                self.logged_in = False
                self.projects_read_permission = False
                self.web_qc_permission = False
                self.mobile_qc_permission = False
                self.qc_api_permission = False
                self.username = ""
                self.protocol = ""
                self.last_login_at = ""
                self.last_error = message
            return False, message

        project_read_perm = session_check_status == 200
        details = []
        if not project_read_perm:
            details.append(f"项目配置读取权限HTTP {session_check_status}")

        web_perm = False
        mobile_perm = False
        message = "MES 登录成功"
        try:
            projects_resp = new_session.get(
                f"{normalized_base}/motor-qc/api/projects",
                timeout=15,
                allow_redirects=False,
            )
            web_perm = projects_resp.status_code == 200
            if not web_perm:
                if projects_resp.status_code == 403:
                    details.append("无 web:run_qc 权限")
                else:
                    details.append(f"任务中心权限HTTP {projects_resp.status_code}")
        except Exception as exc:
            details.append(f"任务中心权限检测失败: {exc}")

        try:
            mobile_resp = new_session.post(
                f"{normalized_base}/api/qc/analyze",
                json={},
                timeout=15,
                allow_redirects=False,
            )
            mobile_status = int(mobile_resp.status_code or 0)
            # Mobile QC endpoint returns 400 for missing params when permission/session are valid.
            mobile_perm = mobile_status in (200, 400)
            if not mobile_perm:
                details.append(f"移动端QC接口HTTP {mobile_status}")
        except Exception as exc:
            details.append(f"移动端QC接口检测失败: {exc}")

        if details:
            message = f"MES 登录成功（{'；'.join(details)}）"

        with self.lock:
            self.base_url = normalized_base
            self.session = new_session
            self.logged_in = True
            self.projects_read_permission = bool(project_read_perm)
            self.web_qc_permission = bool(web_perm)
            self.mobile_qc_permission = bool(mobile_perm)
            self.qc_api_permission = bool(mobile_perm)
            self.username = user
            self.protocol = proto
            self.last_login_at = datetime.now().isoformat(timespec="seconds")
            self.last_error = ""
        return True, message

    def forward_current_request(self, target_path: str) -> Response:
        if requests is None:
            return jsonify({"ok": False, "message": "requests not installed"}), 500

        raw_path = "/" + str(target_path or "").lstrip("/")
        if not (
            raw_path == "/motor-qc/api"
            or raw_path.startswith("/motor-qc/api/")
            or raw_path.startswith("/api/qc/")
            or raw_path.startswith("/api/h2/recommend/")
            or raw_path == "/api/photos/upload"
            or raw_path.startswith("/api/photos/")
            or raw_path == "/api/projects"
            or raw_path.startswith("/api/projects/")
            or raw_path.startswith("/api/process-config/")
        ):
            return jsonify({"ok": False, "message": "proxy path not allowed", "path": raw_path}), 400

        with self.lock:
            base = self.base_url
            session_obj = self.session
            logged_in = self.logged_in

        if not base:
            return jsonify({"ok": False, "message": "MES 地址未配置"}), 400
        if not logged_in or session_obj is None:
            return jsonify({"ok": False, "message": "请先在本地页面登录 MES"}), 401

        target_url = f"{base}{raw_path}"
        method = request.method.upper()
        try:
            kwargs = {
                "params": list(request.args.items(multi=True)),
                "allow_redirects": False,
                "timeout": 60,
            }
            if method in {"POST", "PUT", "PATCH", "DELETE"}:
                if request.files:
                    kwargs["data"] = list(request.form.items(multi=True))
                    files = []
                    for field_name, fs in request.files.items(multi=True):
                        filename = fs.filename or "upload.bin"
                        mimetype = fs.mimetype or "application/octet-stream"
                        files.append((field_name, (filename, fs.stream.read(), mimetype)))
                    kwargs["files"] = files
                else:
                    body = request.get_data() or b""
                    if body:
                        kwargs["data"] = body
                    content_type = str(request.headers.get("Content-Type") or "").strip()
                    if content_type:
                        kwargs["headers"] = {"Content-Type": content_type}

            upstream = session_obj.request(method, target_url, **kwargs)
        except Exception as exc:
            with self.lock:
                self.last_error = f"代理请求失败: {exc}"
            return jsonify({"ok": False, "message": f"代理请求失败: {exc}"}), 502

        if upstream.status_code in (301, 302) and "/login" in str(upstream.headers.get("Location") or ""):
            with self.lock:
                self.logged_in = False
                self.last_error = "MES 会话失效，请重新登录"
            return jsonify({"ok": False, "message": "MES 会话失效，请重新登录"}), 401

        response = Response(upstream.content, status=upstream.status_code)
        for key, value in upstream.headers.items():
            lower = key.lower()
            if lower in {"content-encoding", "transfer-encoding", "connection", "content-length", "set-cookie"}:
                continue
            response.headers[key] = value
        return response


@app.after_request
def add_cors_headers(response):
    # MES page runs on 172.16.x.x while bridge runs on 127.0.0.1.
    # Cross-origin access is required for edge camera/button polling.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Max-Age"] = "600"
    return response


def _station_id() -> str:
    query_station = str(request.args.get("station_id") or "").strip()
    if query_station:
        return query_station
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        body_station = str(payload.get("station_id") or "").strip()
        if body_station:
            return body_station
    return "S01"


def _jpeg_bytes_from_pil(image: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _mock_frame(station_id: str, width: int, height: int, quality: int) -> bytes:
    now = time.time()
    phase = int(now * 3) % 20
    x = 80 + phase * 40
    y = 140 + (phase % 7) * 20

    image = Image.new("RGB", (width, height), color=(12, 23, 36))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, width - 40, height - 40), outline=(70, 90, 120), width=3)
    draw.rectangle((x, y, x + 120, y + 120), fill=(20, 140, 220))
    draw.rectangle((width - x - 180, height - y - 90, width - x - 20, height - y - 50), fill=(20, 180, 100))

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"EDGE CAMERA BRIDGE  station={station_id}  {ts}"
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    draw.text((70, 74), text, fill=(230, 236, 242), font=font)

    return _jpeg_bytes_from_pil(image, quality=quality)


def _decode_c_char_array(value) -> str:
    try:
        raw = bytes(value)
    except Exception:
        try:
            raw = bytearray(value)
        except Exception:
            return ""
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()


@dataclass
class CameraConfig:
    source: str = "auto"
    width: int = 1280
    height: int = 720
    camera_index: int = 0
    rtsp_url: str = ""
    mvs_python_dir: str = ""
    mvs_serial: str = ""
    mvs_index: int = 0
    jpeg_quality: int = 88


class CameraProvider:
    def __init__(self, config: CameraConfig):
        source = (config.source or "auto").strip().lower()
        if source not in {"auto", "mock", "opencv", "rtsp", "mvs"}:
            source = "auto"
        self.config = config
        self.source = source
        self.cv2_enabled = cv2 is not None
        self.capture = None
        self.mvs_module = None
        self.mvs_camera = None
        self.mvs_error = ""
        self.mvs_selected = {}
        self.last_frame_mock = False
        self.last_frame_stale = False
        self.last_frame_error = ""
        self.last_good_jpeg: Optional[bytes] = None
        self.last_good_ts = 0.0
        self.max_stale_frame_sec = 8.0
        self.lock = threading.Lock()
        self.fail_count = 0
        self.last_open_ts = 0.0
        self.open_interval_sec = 1.5

    def _candidate_mvs_python_dirs(self) -> list[str]:
        candidates = []
        env_dir = str(os.environ.get("MVS_PYTHON_DIR") or "").strip()
        if self.config.mvs_python_dir:
            candidates.append(str(self.config.mvs_python_dir).strip())
        if env_dir:
            candidates.append(env_dir)
        candidates.extend(
            [
                r"C:\Program Files\MVS\Development\Samples\Python\MvImport",
                r"C:\Program Files (x86)\MVS\Development\Samples\Python\MvImport",
                r"C:\Program Files\MVS\Development\Samples\Python",
                r"C:\Program Files (x86)\MVS\Development\Samples\Python",
            ]
        )
        normalized = []
        seen = set()
        for item in candidates:
            if not item:
                continue
            p = str(Path(item))
            if p in seen:
                continue
            seen.add(p)
            normalized.append(p)
        return normalized

    def _load_mvs_module(self) -> bool:
        if self.mvs_module is not None:
            return True

        last_error = ""
        for base_dir in self._candidate_mvs_python_dirs():
            if not os.path.isdir(base_dir):
                continue
            if base_dir not in sys.path:
                sys.path.insert(0, base_dir)
            mv_import = os.path.join(base_dir, "MvImport")
            if os.path.isdir(mv_import) and mv_import not in sys.path:
                sys.path.insert(0, mv_import)
            try:
                self.mvs_module = importlib.import_module("MvCameraControl_class")
                self.mvs_error = ""
                LOGGER.info("MVS module loaded from %s", base_dir)
                return True
            except Exception as exc:
                last_error = str(exc)

        try:
            self.mvs_module = importlib.import_module("MvCameraControl_class")
            self.mvs_error = ""
            return True
        except Exception as exc:
            last_error = str(exc)

        self.mvs_error = f"MVS import failed: {last_error or 'MvCameraControl_class not found'}"
        self.mvs_module = None
        return False

    def _release_opencv_capture(self) -> None:
        if self.capture is None:
            return
        try:
            self.capture.release()
        except Exception:
            pass
        self.capture = None

    def _close_mvs_camera(self) -> None:
        cam = self.mvs_camera
        if cam is None:
            return
        try:
            cam.MV_CC_StopGrabbing()
        except Exception:
            pass
        try:
            cam.MV_CC_CloseDevice()
        except Exception:
            pass
        try:
            cam.MV_CC_DestroyHandle()
        except Exception:
            pass
        self.mvs_camera = None

    def shutdown(self) -> None:
        self._release_opencv_capture()
        self._close_mvs_camera()

    def _effective_source(self) -> str:
        if self.source == "auto":
            if self.cv2_enabled:
                return "opencv"
            if self._load_mvs_module():
                return "mvs"
            return "mock"
        if self.source in {"opencv", "rtsp"} and not self.cv2_enabled:
            return "mock"
        if self.source == "mvs" and not self._load_mvs_module():
            return "mock"
        return self.source

    def _open_capture_if_needed(self, force: bool = False) -> None:
        mode = self._effective_source()
        if mode != "opencv" and mode != "rtsp":
            self._release_opencv_capture()
            return
        if cv2 is None:
            return

        now = time.time()
        if not force and now - self.last_open_ts < self.open_interval_sec:
            return
        self.last_open_ts = now

        if self.capture is not None:
            try:
                opened = bool(self.capture.isOpened())
            except Exception:
                opened = False
            if opened:
                return
            self._release_opencv_capture()

        target = self.config.camera_index if mode == "opencv" else self.config.rtsp_url
        if mode == "rtsp" and not str(target).strip():
            LOGGER.warning("RTSP source selected but rtsp_url is empty; fallback to mock")
            return
        try:
            cap = cv2.VideoCapture(target)
            if not cap.isOpened():
                cap.release()
                self.fail_count += 1
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.config.width))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.config.height))
            self.capture = cap
            self.fail_count = 0
            LOGGER.info("Camera opened: mode=%s target=%s", mode, target)
        except Exception as exc:
            self.fail_count += 1
            LOGGER.warning("Open camera failed: %s", exc)

    def _read_opencv_frame(self) -> Optional[bytes]:
        if cv2 is None:
            return None
        mode = self._effective_source()
        if mode not in {"opencv", "rtsp"}:
            return None

        self._open_capture_if_needed(force=False)
        if self.capture is None:
            return None

        ok, frame = self.capture.read()
        if not ok or frame is None:
            self.fail_count += 1
            if self.fail_count >= 3:
                self._open_capture_if_needed(force=True)
            return None
        self.fail_count = 0

        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(self.config.jpeg_quality)],
        )
        if not success:
            return None
        return encoded.tobytes()

    def _enumerate_mvs_devices(self):
        if not self._load_mvs_module():
            return []
        mvs = self.mvs_module
        device_list = mvs.MV_CC_DEVICE_INFO_LIST()
        memset(byref(device_list), 0, sizeof(device_list))
        tlayer = int(getattr(mvs, "MV_GIGE_DEVICE", 0)) | int(getattr(mvs, "MV_USB_DEVICE", 0))
        if tlayer == 0:
            self.mvs_error = "MVS constants missing (MV_GIGE_DEVICE/MV_USB_DEVICE)"
            return []
        ret = mvs.MvCamera.MV_CC_EnumDevices(tlayer, device_list)
        if ret != 0:
            self.mvs_error = f"MV_CC_EnumDevices failed: 0x{int(ret):x}"
            return []
        devices = []
        count = int(getattr(device_list, "nDeviceNum", 0))
        for idx in range(count):
            ptr = device_list.pDeviceInfo[idx]
            if not ptr:
                continue
            info = cast(ptr, POINTER(mvs.MV_CC_DEVICE_INFO)).contents
            layer = int(getattr(info, "nTLayerType", 0))
            serial = ""
            model = ""
            try:
                if layer == int(getattr(mvs, "MV_GIGE_DEVICE", 0)):
                    serial = _decode_c_char_array(info.SpecialInfo.stGigEInfo.chSerialNumber)
                    model = _decode_c_char_array(info.SpecialInfo.stGigEInfo.chModelName)
                elif layer == int(getattr(mvs, "MV_USB_DEVICE", 0)):
                    serial = _decode_c_char_array(info.SpecialInfo.stUsb3VInfo.chSerialNumber)
                    model = _decode_c_char_array(info.SpecialInfo.stUsb3VInfo.chModelName)
            except Exception:
                pass
            devices.append(
                {
                    "index": idx,
                    "ptr": ptr,
                    "serial": serial,
                    "model": model,
                    "layer": layer,
                }
            )
        return devices

    def _open_mvs_if_needed(self, force: bool = False) -> None:
        if self._effective_source() != "mvs":
            self._close_mvs_camera()
            return
        if not self._load_mvs_module():
            self.fail_count += 1
            return

        now = time.time()
        if not force and now - self.last_open_ts < self.open_interval_sec:
            if self.mvs_camera is not None:
                return
        self.last_open_ts = now

        if self.mvs_camera is not None:
            return

        devices = self._enumerate_mvs_devices()
        if not devices:
            self.fail_count += 1
            if not self.mvs_error:
                self.mvs_error = "No MVS devices found"
            return

        target_serial = str(self.config.mvs_serial or "").strip().lower()
        selected = None
        if target_serial:
            for item in devices:
                if str(item.get("serial") or "").strip().lower() == target_serial:
                    selected = item
                    break
        if selected is None:
            mvs_index = int(self.config.mvs_index or 0)
            if mvs_index < 0 or mvs_index >= len(devices):
                mvs_index = 0
            selected = devices[mvs_index]

        mvs = self.mvs_module
        cam = mvs.MvCamera()
        device_info = cast(selected["ptr"], POINTER(mvs.MV_CC_DEVICE_INFO)).contents
        ret = cam.MV_CC_CreateHandle(device_info)
        if ret != 0:
            self.fail_count += 1
            self.mvs_error = f"MV_CC_CreateHandle failed: 0x{int(ret):x}"
            return

        access_mode = int(getattr(mvs, "MV_ACCESS_Exclusive", 1))
        ret = cam.MV_CC_OpenDevice(access_mode, 0)
        if ret != 0:
            self.fail_count += 1
            self.mvs_error = f"MV_CC_OpenDevice failed: 0x{int(ret):x}"
            try:
                cam.MV_CC_DestroyHandle()
            except Exception:
                pass
            return

        if selected["layer"] == int(getattr(mvs, "MV_GIGE_DEVICE", 0)):
            try:
                packet_size = int(cam.MV_CC_GetOptimalPacketSize())
                if packet_size > 0:
                    cam.MV_CC_SetIntValue("GevSCPSPacketSize", packet_size)
            except Exception:
                pass

        try:
            cam.MV_CC_SetEnumValue("TriggerMode", 0)
        except Exception:
            pass

        ret = cam.MV_CC_StartGrabbing()
        if ret != 0:
            self.fail_count += 1
            self.mvs_error = f"MV_CC_StartGrabbing failed: 0x{int(ret):x}"
            try:
                cam.MV_CC_CloseDevice()
            except Exception:
                pass
            try:
                cam.MV_CC_DestroyHandle()
            except Exception:
                pass
            return

        self.mvs_camera = cam
        self.mvs_selected = {
            "index": int(selected.get("index", 0)),
            "serial": str(selected.get("serial") or ""),
            "model": str(selected.get("model") or ""),
        }
        self.mvs_error = ""
        self.fail_count = 0
        LOGGER.info(
            "MVS camera opened: index=%s serial=%s model=%s",
            self.mvs_selected.get("index"),
            self.mvs_selected.get("serial"),
            self.mvs_selected.get("model"),
        )

    def _read_mvs_frame(self) -> Optional[bytes]:
        if self._effective_source() != "mvs":
            return None
        self._open_mvs_if_needed(force=False)
        cam = self.mvs_camera
        mvs = self.mvs_module
        if cam is None or mvs is None:
            return None

        frame_out = mvs.MV_FRAME_OUT()
        memset(byref(frame_out), 0, sizeof(frame_out))
        ret = cam.MV_CC_GetImageBuffer(frame_out, 1000)
        if ret != 0:
            self.fail_count += 1
            self.mvs_error = f"MV_CC_GetImageBuffer failed: 0x{int(ret):x}"
            if self.fail_count >= 3:
                self._close_mvs_camera()
                self._open_mvs_if_needed(force=True)
            return None

        try:
            width = int(frame_out.stFrameInfo.nWidth)
            height = int(frame_out.stFrameInfo.nHeight)
            frame_len = int(frame_out.stFrameInfo.nFrameLen)
            if width <= 0 or height <= 0 or frame_len <= 0:
                self.mvs_error = "Invalid MVS frame info"
                return None

            pixel_bgr = int(getattr(mvs, "PixelType_Gvsp_BGR8_Packed", 0))
            src_pixel_type = int(frame_out.stFrameInfo.enPixelType)

            bgr_bytes = b""
            if pixel_bgr and src_pixel_type == pixel_bgr:
                max_len = width * height * 3
                src = cast(frame_out.pBufAddr, POINTER(c_ubyte * frame_len)).contents
                bgr_bytes = bytes(src[:max_len])
            else:
                if not pixel_bgr:
                    self.mvs_error = "MVS PixelType_Gvsp_BGR8_Packed not found"
                    return None
                conv = mvs.MV_CC_PIXEL_CONVERT_PARAM()
                memset(byref(conv), 0, sizeof(conv))
                conv.nWidth = width
                conv.nHeight = height
                conv.pSrcData = frame_out.pBufAddr
                conv.nSrcDataLen = frame_len
                conv.enSrcPixelType = src_pixel_type
                conv.enDstPixelType = pixel_bgr
                dst_size = width * height * 3
                dst_buf = (c_ubyte * dst_size)()
                conv.pDstBuffer = dst_buf
                conv.nDstBufferSize = dst_size
                ret = cam.MV_CC_ConvertPixelType(conv)
                if ret != 0:
                    self.mvs_error = f"MV_CC_ConvertPixelType failed: 0x{int(ret):x}"
                    return None
                bgr_bytes = bytes(dst_buf)

            image = Image.frombytes("RGB", (width, height), bgr_bytes, "raw", "BGR")
            self.fail_count = 0
            self.mvs_error = ""
            return _jpeg_bytes_from_pil(image, quality=self.config.jpeg_quality)
        finally:
            try:
                cam.MV_CC_FreeImageBuffer(frame_out)
            except Exception:
                pass

    def frame_jpeg(self, station_id: str) -> bytes:
        with self.lock:
            mode = self._effective_source()
            bytes_data = None
            if mode in {"opencv", "rtsp"}:
                bytes_data = self._read_opencv_frame()
            elif mode == "mvs":
                bytes_data = self._read_mvs_frame()

            if bytes_data:
                self.last_frame_mock = False
                self.last_frame_stale = False
                self.last_frame_error = ""
                self.last_good_jpeg = bytes_data
                self.last_good_ts = time.time()
                return bytes_data
            now = time.time()
            if self.last_good_jpeg is not None and (now - self.last_good_ts) <= self.max_stale_frame_sec:
                self.last_frame_mock = False
                self.last_frame_stale = True
                if mode == "mvs":
                    self.last_frame_error = str(self.mvs_error or "MVS frame unavailable")
                elif mode in {"opencv", "rtsp"}:
                    self.last_frame_error = "OpenCV frame unavailable"
                else:
                    self.last_frame_error = "Camera frame unavailable"
                return self.last_good_jpeg
            self.last_frame_mock = True
            self.last_frame_stale = False
            if mode == "mvs":
                self.last_frame_error = str(self.mvs_error or "MVS frame unavailable")
            elif mode in {"opencv", "rtsp"}:
                if self.capture is None:
                    self.last_frame_error = "OpenCV capture not opened"
                else:
                    self.last_frame_error = "OpenCV frame unavailable"
            else:
                self.last_frame_error = "Mock source configured"
            return _mock_frame(
                station_id=station_id,
                width=self.config.width,
                height=self.config.height,
                quality=self.config.jpeg_quality,
            )

    def health_payload(self) -> dict:
        mode = self._effective_source()
        opencv_opened = False
        if self.capture is not None:
            try:
                opencv_opened = bool(self.capture.isOpened())
            except Exception:
                opencv_opened = False
        return {
            "ok": True,
            "service": "edge_camera_bridge",
            "configured_source": self.source,
            "effective_source": mode,
            "cv2_enabled": self.cv2_enabled,
            "capture_opened": bool(opencv_opened or self.mvs_camera is not None),
            "opencv_opened": opencv_opened,
            "mvs_enabled": bool(self.mvs_module is not None),
            "mvs_opened": bool(self.mvs_camera is not None),
            "mvs_error": self.mvs_error,
            "mvs_python_dir": str(self.config.mvs_python_dir or ""),
            "mvs_serial": str(self.config.mvs_serial or ""),
            "mvs_index": int(self.config.mvs_index or 0),
            "mvs_selected": self.mvs_selected,
            "last_frame_mock": bool(self.last_frame_mock),
            "last_frame_stale": bool(self.last_frame_stale),
            "last_frame_error": str(self.last_frame_error or ""),
            "camera_index": self.config.camera_index,
            "rtsp_url_configured": bool(self.config.rtsp_url),
            "width": self.config.width,
            "height": self.config.height,
            "fail_count": self.fail_count,
        }
CAMERA = CameraProvider(CameraConfig())
MES_PROXY = MESAPIProxy(base_url=os.environ.get("MES_BASE_URL", "http://172.16.30.2:8891"))


def _shutdown_camera_provider():
    try:
        CAMERA.shutdown()
    except Exception:
        pass


@app.get("/")
def root_page():
    return redirect("/edge-ui", code=302)


@app.get("/edge-ui")
def edge_ui_page():
    index_file = UI_ROOT / "index.html"
    if not index_file.exists():
        return jsonify({"ok": False, "message": f"edge UI not found: {index_file}"}), 404
    resp = send_file(index_file)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.get("/edge-ui/assets/<path:asset_path>")
def edge_ui_assets(asset_path: str):
    assets_dir = UI_ROOT / "assets"
    if not assets_dir.exists():
        return jsonify({"ok": False, "message": f"edge UI assets not found: {assets_dir}"}), 404
    resp = send_from_directory(assets_dir, asset_path)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.get("/edge-api/auth/status")
def edge_auth_status():
    mes_base = str(request.args.get("mes_base") or "").strip()
    if mes_base:
        MES_PROXY.set_base_url(mes_base)
    return jsonify({"ok": True, **MES_PROXY.status_payload()})


@app.post("/edge-api/auth/login")
def edge_auth_login():
    payload = request.get_json(silent=True) or {}
    ok, message = MES_PROXY.login(
        mes_base=str(payload.get("mes_base") or "").strip(),
        username=str(payload.get("username") or "").strip(),
        password=str(payload.get("password") or "").strip(),
        protocol=str(payload.get("protocol") or "smb").strip().lower(),
    )
    status = MES_PROXY.status_payload()
    status.update({"ok": ok, "message": message})
    return jsonify(status), (200 if ok else 401)


@app.post("/edge-api/auth/logout")
def edge_auth_logout():
    MES_PROXY.logout()
    return jsonify({"ok": True, "message": "已退出 MES 登录"})


@app.route("/edge-api/proxy/<path:target_path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def edge_proxy(target_path: str):
    return MES_PROXY.forward_current_request(target_path)


@app.route("/edge-api/proxy", defaults={"target_path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def edge_proxy_root(target_path: str):
    return MES_PROXY.forward_current_request(target_path)


@app.get("/api/health")
def health():
    payload = CAMERA.health_payload()
    payload["mes_proxy"] = MES_PROXY.status_payload()
    payload["ui_ready"] = (UI_ROOT / "index.html").exists()
    return jsonify(payload)


@app.get("/api/camera/frame")
def camera_frame():
    station = _station_id()
    payload = CAMERA.frame_jpeg(station)
    response = send_file(
        io.BytesIO(payload),
        mimetype="image/jpeg",
        as_attachment=False,
        download_name=f"{station}_frame.jpg",
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Edge-Camera-Mock"] = "1" if CAMERA.last_frame_mock else "0"
    response.headers["X-Edge-Camera-Stale"] = "1" if CAMERA.last_frame_stale else "0"
    response.headers["X-Edge-Camera-Source"] = str(CAMERA.health_payload().get("effective_source") or "")
    frame_error = str(CAMERA.last_frame_error or "")
    if frame_error and frame_error.isascii():
        response.headers["X-Edge-Camera-Error"] = frame_error
    return response


@app.post("/api/button/press")
def button_press():
    station = _station_id()
    event = {
        "event_id": f"{station}-{int(time.time() * 1000)}",
        "station_id": station,
        "ts": datetime.now().isoformat(),
        "pressed": True,
    }
    with _EVENT_LOCK:
        _BUTTON_EVENTS[station].append(event)
        if len(_BUTTON_EVENTS[station]) > 100:
            _BUTTON_EVENTS[station].popleft()
    return jsonify({"ok": True, "event": event})


@app.get("/api/button/next")
def button_next():
    station = _station_id()
    with _EVENT_LOCK:
        queue = _BUTTON_EVENTS[station]
        if queue:
            return jsonify(queue.popleft())
    return jsonify({"pressed": False, "station_id": station, "ts": datetime.now().isoformat()})


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run edge camera bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19091)
    parser.add_argument("--source", default="auto", choices=["auto", "mock", "opencv", "rtsp", "mvs"])
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--rtsp-url", default="")
    parser.add_argument("--mvs-python-dir", default=str(os.environ.get("MVS_PYTHON_DIR") or ""))
    parser.add_argument("--mvs-serial", default="")
    parser.add_argument("--mvs-index", type=int, default=0)
    parser.add_argument("--mes-base", default=str(os.environ.get("MES_BASE_URL") or "http://172.16.30.2:8891"))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--jpeg-quality", type=int, default=88)
    args = parser.parse_args()

    CAMERA.config = CameraConfig(
        source=args.source,
        width=max(320, int(args.width)),
        height=max(240, int(args.height)),
        camera_index=int(args.camera_index),
        rtsp_url=str(args.rtsp_url or "").strip(),
        mvs_python_dir=str(args.mvs_python_dir or "").strip(),
        mvs_serial=str(args.mvs_serial or "").strip(),
        mvs_index=max(0, int(args.mvs_index)),
        jpeg_quality=max(60, min(95, int(args.jpeg_quality))),
    )
    CAMERA.source = CAMERA.config.source
    MES_PROXY.set_base_url(str(args.mes_base or "").strip())

    LOGGER.info(
        "Starting edge camera bridge: host=%s port=%s source=%s mes=%s",
        args.host,
        args.port,
        CAMERA.source,
        MES_PROXY.status_payload().get("mes_base") or "",
    )
    try:
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
    finally:
        _shutdown_camera_provider()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
