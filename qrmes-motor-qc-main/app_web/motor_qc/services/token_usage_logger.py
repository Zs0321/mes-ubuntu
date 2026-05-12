"""AI token usage structured logger for Motor QC vision calls."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from qrmes_shared_core.config import config
    from qrmes_shared_core.data_dir_utils import resolve_data_dir
except Exception:  # pragma: no cover - fallback for package-style imports
    from app_web.config import config  # type: ignore
    from app_web.data_dir_utils import resolve_data_dir  # type: ignore

try:
    import system_logs_db
except Exception:  # pragma: no cover - fallback for package-style imports
    from app_web import system_logs_db  # type: ignore

logger = logging.getLogger(__name__)

_DB_READY = False
_DB_LOCK = threading.Lock()


def _get_data_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return resolve_data_dir(
        nas_local_base_path=getattr(config, "nas_local_base_path", None),
        repo_root=repo_root,
        logger=logger,
    )


def _system_logs_db_path() -> Path:
    return _get_data_dir() / "log" / "system_logs.db"


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _extract_usage(usage: Any) -> Dict[str, int]:
    if not isinstance(usage, dict):
        usage = {}

    prompt_tokens = _to_int(
        usage.get("prompt_tokens", usage.get("input_tokens", 0))
    )
    completion_tokens = _to_int(
        usage.get("completion_tokens", usage.get("output_tokens", 0))
    )
    total_tokens = _to_int(usage.get("total_tokens", 0))
    if total_tokens <= 0:
        total_tokens = max(0, prompt_tokens + completion_tokens)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _sanitize_context_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _extract_serial_process_from_filename(stem: str) -> Dict[str, Optional[str]]:
    serial_number: Optional[str] = None
    process_step: Optional[str] = None
    candidate = str(stem or "").strip()
    if not candidate:
        return {"serial_number": None, "process_step": None}

    # New temporary naming: qc__{serial}__{process}__{idx}_{random}
    if candidate.startswith("qc__"):
        chunks = candidate.split("__", 3)
        if len(chunks) >= 4:
            serial_number = _sanitize_context_text(chunks[1])
            process_step = _sanitize_context_text(chunks[2])
            return {"serial_number": serial_number, "process_step": process_step}

    # Legacy temporary naming: qc_{serial}_{idx}_{random}
    legacy_temp = re.match(r"^qc_([^_]+)_\d+_.+$", candidate)
    if legacy_temp:
        serial_number = _sanitize_context_text(legacy_temp.group(1))
        return {"serial_number": serial_number, "process_step": None}

    # Strip PhotoService timestamp prefix: 20260228_120001_{original_filename}
    with_prefix = re.match(r"^\d{8}_\d{6}_(.+)$", candidate)
    if with_prefix:
        candidate = with_prefix.group(1)

    # Parse common process photo naming:
    # {serial}_{process}_{YYYYMMDD}_{HHMMSS}[_{suffix}]
    match = re.match(r"^([^_]+)_(.+)_(\d{8})_(\d{6})(?:_.+)?$", candidate)
    if match:
        serial_number = _sanitize_context_text(match.group(1))
        process_step = _sanitize_context_text(match.group(2))
        return {"serial_number": serial_number, "process_step": process_step}

    # Fallback: {serial}_{process}_{YYYYMMDDHHMMSS}
    compact = re.match(r"^([^_]+)_(.+)_(\d{14})(?:_.+)?$", candidate)
    if compact:
        serial_number = _sanitize_context_text(compact.group(1))
        process_step = _sanitize_context_text(compact.group(2))
        return {"serial_number": serial_number, "process_step": process_step}

    return {"serial_number": None, "process_step": None}


def _extract_photo_context(
    image_path: Optional[str],
    usage_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    if not image_path:
        base = {"serial_number": None, "process_step": None, "image_name": None}
    else:
        path_obj = Path(str(image_path))
        image_name = path_obj.name
        serial_number = path_obj.parent.name if path_obj.parent else None
        process_step = None

        if serial_number and image_name.startswith(f"{serial_number}_"):
            stem = path_obj.stem
            remainder = stem[len(serial_number) + 1 :]
            if remainder:
                parts = remainder.split("_")
                if len(parts) >= 4 and parts[-1].isdigit() and parts[-2].isdigit() and parts[-3].isdigit():
                    process_step = "_".join(parts[:-3])
                elif len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
                    process_step = "_".join(parts[:-2])
                elif len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) == 14:
                    process_step = "_".join(parts[:-1])
                elif "_" in remainder:
                    process_step = remainder.rsplit("_", 1)[0]
                else:
                    process_step = remainder

        parsed = _extract_serial_process_from_filename(path_obj.stem)
        if parsed.get("serial_number"):
            serial_number = parsed.get("serial_number")
        if parsed.get("process_step"):
            process_step = parsed.get("process_step")

        base = {
            "serial_number": _sanitize_context_text(serial_number),
            "process_step": _sanitize_context_text(process_step),
            "image_name": image_name,
        }

    context = usage_context if isinstance(usage_context, dict) else {}
    if context:
        serial_override = (
            context.get("serial_number")
            or context.get("product_serial")
            or context.get("serial")
        )
        process_override = (
            context.get("process_step")
            or context.get("process_name")
            or context.get("process")
            or context.get("step")
        )
        image_name_override = (
            context.get("image_name")
            or context.get("file_name")
            or context.get("filename")
        )

        if _sanitize_context_text(serial_override):
            base["serial_number"] = _sanitize_context_text(serial_override)
        if _sanitize_context_text(process_override):
            base["process_step"] = _sanitize_context_text(process_override)
        if _sanitize_context_text(image_name_override):
            base["image_name"] = _sanitize_context_text(image_name_override)

        base["project_code"] = _sanitize_context_text(
            context.get("project_code") or context.get("project_name")
        )
        base["product_type"] = _sanitize_context_text(
            context.get("product_type")
        )
        base["station_id"] = _sanitize_context_text(
            context.get("station_id") or context.get("stationId")
        )
        base["upload_mode"] = _sanitize_context_text(
            context.get("upload_mode") or context.get("uploadMode")
        )
        base["source"] = _sanitize_context_text(context.get("source"))

    return base


def _ensure_db_ready() -> None:
    global _DB_READY
    if _DB_READY:
        return
    with _DB_LOCK:
        if _DB_READY:
            return
        db_path = _system_logs_db_path()
        # Ensure folder exists even when data_dir is writable but /log is not created yet.
        db_path.parent.mkdir(parents=True, exist_ok=True)
        system_logs_db.ensure_system_logs_db(db_path)
        _DB_READY = True


def log_ai_token_usage(
    *,
    provider: str,
    model: str,
    usage: Optional[Dict[str, Any]],
    image_path: Optional[str] = None,
    usage_context: Optional[Dict[str, Any]] = None,
    latency_ms: Optional[int] = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> None:
    """Write AI token usage into system_logs SQLite as operation logs."""
    try:
        _ensure_db_ready()
        usage_norm = _extract_usage(usage or {})
        context = _extract_photo_context(image_path, usage_context)

        image_size_bytes = 0
        if image_path:
            try:
                image_size_bytes = int(Path(image_path).stat().st_size)
            except Exception:
                image_size_bytes = 0

        details = {
            "provider": (provider or "").strip().lower(),
            "model": (model or "").strip(),
            "prompt_tokens": usage_norm["prompt_tokens"],
            "completion_tokens": usage_norm["completion_tokens"],
            "total_tokens": usage_norm["total_tokens"],
            "latency_ms": _to_int(latency_ms) if latency_ms is not None else None,
            "image_path": image_path or "",
            "image_name": context["image_name"],
            "serial_number": context["serial_number"],
            "process_step": context["process_step"],
            "project_code": context.get("project_code"),
            "product_type": context.get("product_type"),
            "station_id": context.get("station_id"),
            "upload_mode": context.get("upload_mode"),
            "source": context.get("source"),
            "image_size_bytes": image_size_bytes,
            "success": bool(success),
            "error_message": error_message or "",
            "recorded_at_ms": int(time.time() * 1000),
        }

        row = {
            "ts": int(time.time() * 1000),
            "kind": "operation",
            "level": "INFO" if success else "ERROR",
            "success": bool(success),
            "action": "AI_VISION_USAGE",
            "target": f"{details['provider']}:{details['model']}",
            "message": (
                f"tokens={details['total_tokens']} "
                f"(prompt={details['prompt_tokens']}, completion={details['completion_tokens']})"
            ),
            "details_json": details,
        }
        system_logs_db.insert_system_logs(_system_logs_db_path(), [row])
    except Exception as exc:
        # Logging must never break main flow.
        logger.debug("log_ai_token_usage failed: %s", exc)
