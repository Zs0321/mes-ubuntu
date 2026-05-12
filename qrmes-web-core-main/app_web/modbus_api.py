#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Modbus communication API for tester device."""

from __future__ import annotations

from collections import deque
from datetime import datetime
import logging
import threading
from typing import Any, Deque, Dict, List, Optional

from flask import Blueprint, jsonify, request

from qrmes_shared_core.config import config
from services.modbus_service import (
    ModbusError,
    ModbusExceptionResponse,
    ModbusTcpClient,
    ModbusTcpParams,
    decode_ascii_from_registers,
    encode_ascii_to_registers,
    error_code_text,
    result_text,
    status_text,
)

logger = logging.getLogger(__name__)

modbus_bp = Blueprint("modbus_api", __name__, url_prefix="/api/modbus")

DEFAULT_MODBUS_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "host": "",
    "port": 502,
    "unit_id": 1,
    "timeout_sec": 2.0,
    "text_encoding": "ascii",
    "status_register": 0x0001,
    "error_register": 0x0002,
    "result_register": 0x0003,
    "result_count": 1,
    "start_register": 0x0001,
    "stop_register": 0x0002,
    "barcode_register": 0x0003,
    "barcode_register_count": 64,
    "profile_register": 0x0044,
    "profile_register_count": 32,
    "profile_one_char_per_register": True,
    "poll_interval_sec": 1.0,
    "history_limit": 500,
}

_poll_lock = threading.Lock()
_poll_stop = threading.Event()
_poll_thread: Optional[threading.Thread] = None
_poll_latest: Optional[Dict[str, Any]] = None
_poll_history: Deque[Dict[str, Any]] = deque(maxlen=DEFAULT_MODBUS_CONFIG["history_limit"])
_poll_last_error: Optional[str] = None


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _cfg_key(name: str) -> str:
    return f"modbus_{name}"


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_settings(raw: Dict[str, Any]) -> Dict[str, Any]:
    cfg = dict(DEFAULT_MODBUS_CONFIG)
    cfg.update(raw or {})
    cfg["enabled"] = _as_bool(cfg.get("enabled"), DEFAULT_MODBUS_CONFIG["enabled"])
    cfg["host"] = str(cfg.get("host", "")).strip()
    cfg["port"] = _as_int(cfg.get("port"), DEFAULT_MODBUS_CONFIG["port"])
    cfg["unit_id"] = _as_int(cfg.get("unit_id"), DEFAULT_MODBUS_CONFIG["unit_id"])
    cfg["timeout_sec"] = _as_float(cfg.get("timeout_sec"), DEFAULT_MODBUS_CONFIG["timeout_sec"])
    cfg["text_encoding"] = str(cfg.get("text_encoding", "ascii") or "ascii").strip()
    cfg["status_register"] = _as_int(cfg.get("status_register"), DEFAULT_MODBUS_CONFIG["status_register"])
    cfg["error_register"] = _as_int(cfg.get("error_register"), DEFAULT_MODBUS_CONFIG["error_register"])
    cfg["result_register"] = _as_int(cfg.get("result_register"), DEFAULT_MODBUS_CONFIG["result_register"])
    cfg["result_count"] = _as_int(cfg.get("result_count"), DEFAULT_MODBUS_CONFIG["result_count"])
    cfg["start_register"] = _as_int(cfg.get("start_register"), DEFAULT_MODBUS_CONFIG["start_register"])
    cfg["stop_register"] = _as_int(cfg.get("stop_register"), DEFAULT_MODBUS_CONFIG["stop_register"])
    cfg["barcode_register"] = _as_int(cfg.get("barcode_register"), DEFAULT_MODBUS_CONFIG["barcode_register"])
    cfg["barcode_register_count"] = _as_int(
        cfg.get("barcode_register_count"),
        DEFAULT_MODBUS_CONFIG["barcode_register_count"],
    )
    cfg["profile_register"] = _as_int(cfg.get("profile_register"), DEFAULT_MODBUS_CONFIG["profile_register"])
    cfg["profile_register_count"] = _as_int(
        cfg.get("profile_register_count"),
        DEFAULT_MODBUS_CONFIG["profile_register_count"],
    )
    cfg["profile_one_char_per_register"] = _as_bool(
        cfg.get("profile_one_char_per_register"),
        DEFAULT_MODBUS_CONFIG["profile_one_char_per_register"],
    )
    cfg["poll_interval_sec"] = _as_float(
        cfg.get("poll_interval_sec"),
        DEFAULT_MODBUS_CONFIG["poll_interval_sec"],
    )
    cfg["history_limit"] = _as_int(cfg.get("history_limit"), DEFAULT_MODBUS_CONFIG["history_limit"])

    cfg["port"] = max(1, min(cfg["port"], 65535))
    cfg["unit_id"] = max(1, min(cfg["unit_id"], 255))
    cfg["timeout_sec"] = max(0.2, min(cfg["timeout_sec"], 30.0))
    cfg["result_count"] = max(1, min(cfg["result_count"], 125))
    cfg["barcode_register_count"] = max(1, min(cfg["barcode_register_count"], 123))
    cfg["profile_register_count"] = max(1, min(cfg["profile_register_count"], 123))
    cfg["poll_interval_sec"] = max(0.2, min(cfg["poll_interval_sec"], 30.0))
    cfg["history_limit"] = max(10, min(cfg["history_limit"], 5000))
    return cfg


def _load_settings() -> Dict[str, Any]:
    data = {}
    for key, default in DEFAULT_MODBUS_CONFIG.items():
        data[key] = config.get(_cfg_key(key), default)
    return _normalize_settings(data)


def _save_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = {}
    for key in DEFAULT_MODBUS_CONFIG.keys():
        if key in updates:
            sanitized[key] = updates[key]
    merged = _load_settings()
    merged.update(sanitized)
    merged = _normalize_settings(merged)

    payload = {_cfg_key(k): v for k, v in merged.items()}
    config.update(payload)
    _resize_history(merged["history_limit"])
    return merged


def _resize_history(limit: int) -> None:
    global _poll_history
    with _poll_lock:
        if _poll_history.maxlen == limit:
            return
        _poll_history = deque(list(_poll_history)[-limit:], maxlen=limit)


def _require_host(settings: Dict[str, Any]) -> Optional[str]:
    if not settings.get("host"):
        return "modbus host 未配置"
    return None


def _create_client(settings: Dict[str, Any]) -> ModbusTcpClient:
    params = ModbusTcpParams(
        host=settings["host"],
        port=settings["port"],
        unit_id=settings["unit_id"],
        timeout_sec=settings["timeout_sec"],
    )
    return ModbusTcpClient(params)


def _format_exception(exc: Exception) -> str:
    if isinstance(exc, ModbusExceptionResponse):
        return (
            f"设备返回异常: 功能码=0x{exc.function_code:02X}, "
            f"异常码=0x{exc.exception_code:02X}"
        )
    return str(exc)


def _read_device_snapshot(settings: Dict[str, Any]) -> Dict[str, Any]:
    client = _create_client(settings)
    status_value = client.read_input_registers(settings["status_register"], 1)[0]
    error_value = client.read_input_registers(settings["error_register"], 1)[0]
    result_registers = client.read_input_registers(
        settings["result_register"], settings["result_count"]
    )

    payload: Dict[str, Any] = {
        "timestamp": _now_iso(),
        "status_code": status_value,
        "status_text": status_text(status_value),
        "error_code": error_value,
        "error_text": error_code_text(error_value),
        "result_registers": result_registers,
        "result_register_hex": [f"0x{v:04X}" for v in result_registers],
    }
    if result_registers:
        payload["result_code"] = result_registers[0]
        payload["result_text"] = result_text(result_registers[0])
    return payload


def _append_poll_event(item: Dict[str, Any]) -> None:
    global _poll_latest
    with _poll_lock:
        _poll_latest = item
        _poll_history.append(item)


def _poll_loop() -> None:
    global _poll_last_error
    while not _poll_stop.is_set():
        settings = _load_settings()
        try:
            snapshot = _read_device_snapshot(settings)
            snapshot["ok"] = True
            _poll_last_error = None
            _append_poll_event(snapshot)
        except Exception as exc:
            err = _format_exception(exc)
            _poll_last_error = err
            _append_poll_event(
                {
                    "timestamp": _now_iso(),
                    "ok": False,
                    "error": err,
                }
            )
        if _poll_stop.wait(settings["poll_interval_sec"]):
            break


@modbus_bp.route("/config", methods=["GET"])
def get_modbus_config():
    settings = _load_settings()
    return jsonify({"success": True, "config": settings})


@modbus_bp.route("/config", methods=["POST"])
def update_modbus_config():
    data = request.get_json(silent=True) or {}
    settings = _save_settings(data)
    logger.info("[Modbus] config updated: host=%s port=%s", settings["host"], settings["port"])
    return jsonify({"success": True, "config": settings})


@modbus_bp.route("/protocol-capabilities", methods=["GET"])
def get_protocol_capabilities():
    """Capabilities derived from the 2024-04-26 protocol."""
    return jsonify(
        {
            "success": True,
            "mode": {
                "master_slave": "master_polling",
                "device_push_supported": False,
                "explain": "协议描述为PLC按地址查询数据，不包含设备主动上报报文定义",
            },
            "history": {
                "device_history_supported": False,
                "explain": "协议仅定义寄存器实时读写；历史记录需由上位机本地采集保存",
            },
            "function_codes": ["0x03", "0x04", "0x10"],
            "max_read_registers_once": 125,
            "transport": ["Modbus TCP", "Modbus RTU"],
        }
    )


@modbus_bp.route("/connect-test", methods=["POST"])
def test_modbus_connect():
    settings = _load_settings()
    data = request.get_json(silent=True) or {}
    if data:
        settings = _normalize_settings({**settings, **data})

    missing = _require_host(settings)
    if missing:
        return jsonify({"success": False, "error": missing}), 400

    try:
        snap = _read_device_snapshot(settings)
        return jsonify({"success": True, "message": "连接和读寄存器成功", "snapshot": snap})
    except Exception as exc:
        return jsonify({"success": False, "error": _format_exception(exc)}), 502


@modbus_bp.route("/status", methods=["GET"])
def read_modbus_status():
    settings = _load_settings()
    missing = _require_host(settings)
    if missing:
        return jsonify({"success": False, "error": missing}), 400
    try:
        return jsonify({"success": True, "snapshot": _read_device_snapshot(settings)})
    except Exception as exc:
        return jsonify({"success": False, "error": _format_exception(exc)}), 502


@modbus_bp.route("/command/start", methods=["POST"])
def command_start_test():
    settings = _load_settings()
    missing = _require_host(settings)
    if missing:
        return jsonify({"success": False, "error": missing}), 400

    data = request.get_json(silent=True) or {}
    station = _as_int(data.get("station", 1), 1)
    station = max(1, min(station, 16))
    try:
        client = _create_client(settings)
        ack = client.write_multiple_registers(settings["start_register"], [station])
        return jsonify({"success": True, "message": "启动指令已发送", "station": station, "ack": ack})
    except Exception as exc:
        return jsonify({"success": False, "error": _format_exception(exc)}), 502


@modbus_bp.route("/command/stop", methods=["POST"])
def command_stop_test():
    settings = _load_settings()
    missing = _require_host(settings)
    if missing:
        return jsonify({"success": False, "error": missing}), 400
    try:
        client = _create_client(settings)
        ack = client.write_multiple_registers(settings["stop_register"], [1])
        return jsonify({"success": True, "message": "停止指令已发送", "ack": ack})
    except Exception as exc:
        return jsonify({"success": False, "error": _format_exception(exc)}), 502


@modbus_bp.route("/command/barcode", methods=["POST"])
def command_write_barcode():
    settings = _load_settings()
    missing = _require_host(settings)
    if missing:
        return jsonify({"success": False, "error": missing}), 400

    data = request.get_json(silent=True) or {}
    barcode = str(data.get("barcode", "") or "").strip()
    if not barcode:
        return jsonify({"success": False, "error": "barcode 不能为空"}), 400

    regs = encode_ascii_to_registers(
        barcode,
        settings["barcode_register_count"],
        one_char_per_register=False,
        encoding=settings["text_encoding"],
    )
    try:
        client = _create_client(settings)
        ack = client.write_multiple_registers(settings["barcode_register"], regs)
        return jsonify(
            {
                "success": True,
                "message": "条码写入成功",
                "barcode": barcode,
                "register_count": len(regs),
                "ack": ack,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": _format_exception(exc)}), 502


@modbus_bp.route("/command/profile", methods=["POST"])
def command_write_profile():
    settings = _load_settings()
    missing = _require_host(settings)
    if missing:
        return jsonify({"success": False, "error": missing}), 400

    data = request.get_json(silent=True) or {}
    profile = str(data.get("profile", "") or "").strip()
    if not profile:
        return jsonify({"success": False, "error": "profile 不能为空"}), 400

    regs = encode_ascii_to_registers(
        profile,
        settings["profile_register_count"],
        one_char_per_register=settings["profile_one_char_per_register"],
        encoding=settings["text_encoding"],
    )
    try:
        client = _create_client(settings)
        ack = client.write_multiple_registers(settings["profile_register"], regs)
        return jsonify(
            {
                "success": True,
                "message": "档案写入成功",
                "profile": profile,
                "register_count": len(regs),
                "ack": ack,
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": _format_exception(exc)}), 502


@modbus_bp.route("/read-registers", methods=["POST"])
def read_registers():
    settings = _load_settings()
    missing = _require_host(settings)
    if missing:
        return jsonify({"success": False, "error": missing}), 400

    data = request.get_json(silent=True) or {}
    function_code = _as_int(data.get("function_code", 4), 4)
    start_address = _as_int(data.get("start_address", 1), 1)
    count = _as_int(data.get("count", 1), 1)
    count = max(1, min(count, 125))

    if function_code not in (3, 4):
        return jsonify({"success": False, "error": "function_code 仅支持 3 或 4"}), 400

    try:
        client = _create_client(settings)
        if function_code == 3:
            values = client.read_holding_registers(start_address, count)
        else:
            values = client.read_input_registers(start_address, count)
        return jsonify(
            {
                "success": True,
                "function_code": function_code,
                "start_address": start_address,
                "count": count,
                "registers": values,
                "register_hex": [f"0x{v:04X}" for v in values],
                "ascii_2char": decode_ascii_from_registers(
                    values,
                    one_char_per_register=False,
                    encoding=settings["text_encoding"],
                ),
                "ascii_1char": decode_ascii_from_registers(
                    values,
                    one_char_per_register=True,
                    encoding=settings["text_encoding"],
                ),
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": _format_exception(exc)}), 502


@modbus_bp.route("/write-registers", methods=["POST"])
def write_registers():
    settings = _load_settings()
    missing = _require_host(settings)
    if missing:
        return jsonify({"success": False, "error": missing}), 400

    data = request.get_json(silent=True) or {}
    start_address = _as_int(data.get("start_address", 1), 1)
    values = data.get("values")
    if not isinstance(values, list) or not values:
        return jsonify({"success": False, "error": "values 必须是非空数组"}), 400
    try:
        registers = [max(0, min(0xFFFF, _as_int(v, 0))) for v in values]
        client = _create_client(settings)
        ack = client.write_multiple_registers(start_address, registers)
        return jsonify(
            {
                "success": True,
                "start_address": start_address,
                "count": len(registers),
                "ack": ack,
            }
        )
    except ModbusError as exc:
        return jsonify({"success": False, "error": _format_exception(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": _format_exception(exc)}), 502


@modbus_bp.route("/poller/start", methods=["POST"])
def start_poller():
    global _poll_thread, _poll_last_error
    data = request.get_json(silent=True) or {}
    if data:
        settings = _save_settings(data)
    else:
        settings = _load_settings()
    missing = _require_host(settings)
    if missing:
        return jsonify({"success": False, "error": missing}), 400

    with _poll_lock:
        if _poll_thread and _poll_thread.is_alive():
            return jsonify({"success": True, "message": "轮询已在运行中"})
        _poll_last_error = None
        _poll_stop.clear()
        _poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="modbus-poller")
        _poll_thread.start()
    return jsonify({"success": True, "message": "轮询已启动", "interval_sec": settings["poll_interval_sec"]})


@modbus_bp.route("/poller/stop", methods=["POST"])
def stop_poller():
    global _poll_thread
    _poll_stop.set()
    thread = None
    with _poll_lock:
        thread = _poll_thread
    if thread and thread.is_alive():
        thread.join(timeout=2.0)
    with _poll_lock:
        _poll_thread = None
    return jsonify({"success": True, "message": "轮询已停止"})


@modbus_bp.route("/poller/status", methods=["GET"])
def get_poller_status():
    with _poll_lock:
        running = bool(_poll_thread and _poll_thread.is_alive())
        latest = _poll_latest
        history_size = len(_poll_history)
        last_error = _poll_last_error
    return jsonify(
        {
            "success": True,
            "running": running,
            "latest": latest,
            "history_size": history_size,
            "last_error": last_error,
        }
    )


@modbus_bp.route("/poller/history", methods=["GET"])
def get_poller_history():
    limit = _as_int(request.args.get("limit", 100), 100)
    limit = max(1, min(limit, 1000))
    with _poll_lock:
        history = list(_poll_history)[-limit:]
    return jsonify(
        {
            "success": True,
            "count": len(history),
            "history": history,
        }
    )
