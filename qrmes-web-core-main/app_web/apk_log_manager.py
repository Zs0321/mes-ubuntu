from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _source_kind(record: Dict[str, Any]) -> str:
    source = str(record.get("source") or "").strip().lower()
    if source == 'apk_auto':
        return 'auto_report'
    return 'manual_user'


class ApkLogManager:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _metadata_path(self, stored_name: str) -> Path:
        return self.base_dir / f"{stored_name}.json"

    def _zip_path(self, stored_name: str) -> Path:
        return self.base_dir / stored_name

    def _sanitize_fragment(self, value: str, fallback: str) -> str:
        text = (value or "").strip()
        text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
        text = text.strip("._-")
        return text or fallback

    def _parse_embedded_device_info(self, zip_path: Path) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "device_info_text": "",
            "log_entries": [],
            "log_file_count": 0,
        }
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                info["log_entries"] = [name for name in names if name.endswith(".log")]
                info["log_file_count"] = len(info["log_entries"])
                if "device_info.txt" in names:
                    raw = zf.read("device_info.txt")
                    info["device_info_text"] = raw.decode("utf-8", errors="replace")
        except Exception:
            return info
        return info

    def save_upload(
        self,
        *,
        file_bytes: bytes,
        original_filename: str,
        username: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not file_bytes:
            raise ValueError("empty upload")

        meta = dict(metadata or {})
        username_safe = self._sanitize_fragment(username, "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique = uuid.uuid4().hex[:8]
        stored_name = f"apklog_{timestamp}_{username_safe}_{unique}.zip"

        zip_path = self._zip_path(stored_name)
        zip_path.write_bytes(file_bytes)

        parsed = self._parse_embedded_device_info(zip_path)
        uploaded_at = datetime.now().isoformat(timespec="seconds")
        record = {
            "stored_name": stored_name,
            "original_filename": original_filename or stored_name,
            "username": username,
            "uploaded_at": uploaded_at,
            "size_bytes": zip_path.stat().st_size,
            "app_version_name": meta.get("app_version_name") or "",
            "app_version_code": int(meta.get("app_version_code") or 0),
            "device_model": meta.get("device_model") or "",
            "manufacturer": meta.get("manufacturer") or "",
            "android_version": meta.get("android_version") or "",
            "source": meta.get("source") or "apk",
            "event_type": meta.get("event_type") or "",
            "severity": meta.get("severity") or "",
            "feature": meta.get("feature") or "",
            "reason_code": meta.get("reason_code") or "",
            "http_status": int(meta.get("http_status") or 0) if str(meta.get("http_status") or "").strip() else None,
            "trigger": meta.get("trigger") or "",
            "summary": meta.get("summary") or "",
            "extra_json": meta.get("extra_json") or "",
            "ip": meta.get("ip") or "",
            "device_info_text": parsed.get("device_info_text") or "",
            "log_file_count": parsed.get("log_file_count") or 0,
            "log_entries": parsed.get("log_entries") or [],
        }
        self._metadata_path(stored_name).write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return record

    def list_uploads(
        self,
        *,
        username: Optional[str] = None,
        q: Optional[str] = None,
        date: Optional[str] = None,
        event_type: Optional[str] = None,
        feature: Optional[str] = None,
        reason_code: Optional[str] = None,
        source_kind: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for meta_path in self.base_dir.glob("*.zip.json"):
            try:
                record = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            zip_path = self._zip_path(record.get("stored_name", ""))
            if not zip_path.exists():
                continue
            if username and record.get("username") != username:
                continue
            if date and not str(record.get("uploaded_at") or "").startswith(date):
                continue
            if event_type and str(record.get("event_type") or "") != event_type:
                continue
            if feature and str(record.get("feature") or "") != feature:
                continue
            if reason_code and str(record.get("reason_code") or "") != reason_code:
                continue
            if source_kind and _source_kind(record) != source_kind:
                continue
            if q:
                haystack = "\n".join(
                    [
                        str(record.get("username") or ""),
                        str(record.get("original_filename") or ""),
                        str(record.get("device_model") or ""),
                        str(record.get("manufacturer") or ""),
                        str(record.get("app_version_name") or ""),
                        str(record.get("event_type") or ""),
                        str(record.get("feature") or ""),
                        str(record.get("reason_code") or ""),
                        str(record.get("summary") or ""),
                        str(record.get("device_info_text") or ""),
                    ]
                ).lower()
                if q.lower() not in haystack:
                    continue
            rows.append(record)

        rows.sort(key=lambda item: item.get("uploaded_at") or "", reverse=True)
        return rows[: max(1, min(limit, 500))]

    def get_upload(self, stored_name: str) -> Optional[Dict[str, Any]]:
        meta_path = self._metadata_path(stored_name)
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def get_upload_file(self, stored_name: str) -> Optional[Path]:
        path = self._zip_path(stored_name)
        if path.exists() and path.is_file():
            return path
        return None
