"""Shared DATA_DIR resolver for NAS/local deployments."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_NAS_DATA_DIR = "/volume2/MES/QRMES"
DATA_MARKERS: tuple[str, ...] = (
    "projects.json",
    "projects",
    "picture",
    "documents",
    "record",
    "web_users.db",
)


def _has_markers(path: Path, markers: Iterable[str] = DATA_MARKERS) -> bool:
    try:
        return any((path / marker).exists() for marker in markers)
    except Exception:
        return False


def resolve_data_dir(
    *,
    nas_local_base_path: Optional[str],
    repo_root: Optional[Path] = None,
    logger=None,
    create: bool = True,
) -> Path:
    """Resolve shared data root in a stable order.

    Priority:
    1) `MESAPP_DATA_DIR` / `DATA_DIR` env (if it looks valid, or NAS path has no data markers)
    2) `nas_local_base_path` (if exists/looks valid)
    3) local fallback `<repo>/app/files`
    """
    project_root = repo_root or Path(__file__).resolve().parent.parent
    fallback = project_root / "app" / "files"
    nas_path = Path((nas_local_base_path or DEFAULT_NAS_DATA_DIR).strip() or DEFAULT_NAS_DATA_DIR)

    env_raw = (os.getenv("MESAPP_DATA_DIR") or os.getenv("DATA_DIR") or "").strip()
    env_path = Path(env_raw).expanduser() if env_raw else None

    env_has_markers = _has_markers(env_path) if env_path else False
    nas_has_markers = _has_markers(nas_path)

    selected: Path
    reason: str

    if env_path:
        if env_has_markers or not nas_has_markers:
            selected = env_path
            reason = f"env:{env_path}"
        else:
            selected = nas_path
            reason = (
                f"nas_local_base_path:{nas_path} "
                f"(skip env {env_path}, no markers)"
            )
    elif nas_has_markers or nas_path.exists():
        selected = nas_path
        reason = f"nas_local_base_path:{nas_path}"
    else:
        selected = fallback
        reason = f"fallback:{fallback}"

    if create:
        selected.mkdir(parents=True, exist_ok=True)

    if logger is not None:
        logger.info(f"[配置] DATA_DIR 解析结果: {selected} ({reason})")

    return selected
