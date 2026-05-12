from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_MONITOR_DIRS = (
    '/volume2/qrmes-v3.0/qrmes-dingtalk-bot/monitor',
    '/Volumes/172.16.30.10/volume2/qrmes-v3.0/qrmes-dingtalk-bot/monitor',
)
DINGTALK_REPO_MARKERS = (
    '/qrmes-dingtalk-bot/',
    '/dingtalk_mes_bot/',
)
DEFAULT_LIVE_LOGS = (
    '/volume2/qrmes-v3.0/qrmes-dingtalk-bot/runtime.log',
    '/Volumes/172.16.30.10/volume2/qrmes-v3.0/qrmes-dingtalk-bot/runtime.log',
)
DEFAULT_LEGACY_LOGS = (
    '/volume2/qrmes-v3.0/qrmes-dingtalk-bot/runtime_legacy.log',
    '/Volumes/172.16.30.10/volume2/qrmes-v3.0/qrmes-dingtalk-bot/runtime_legacy.log',
)


def _resolve_path(path_like: str | Path | None, candidates: tuple[str, ...]) -> Path:
    if path_like:
        return Path(path_like)
    for item in candidates:
        path = Path(item)
        if path.exists():
            return path
    return Path(candidates[0])


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists() or limit <= 0:
        return []
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except Exception:
        return []
    return lines[-limit:]


def _filter_dingtalk_changed_files(status: dict[str, Any]) -> dict[str, Any]:
    changed_files = [
        str(item)
        for item in (status.get('changed_files') or [])
        if isinstance(item, str) and any(marker in item for marker in DINGTALK_REPO_MARKERS)
    ]
    filtered = dict(status)
    filtered['changed_files'] = changed_files
    filtered['diff_preview'] = list(filtered.get('diff_preview') or [])
    filtered['patch_text'] = str(filtered.get('patch_text') or '')
    if not changed_files:
        filtered['summary'] = filtered.get('summary') or '当前暂无钉钉机器人仓库源码修复摘要。'
        filtered['last_action'] = filtered.get('last_action') or '本轮未记录钉钉机器人源码修改'
        filtered['verification'] = list(filtered.get('verification') or [])
    return filtered


def load_bot_monitor_snapshot(
    monitor_dir: str | Path | None = None,
    live_log_path: str | Path | None = None,
    legacy_log_path: str | Path | None = None,
    tail_lines: int = 80,
) -> dict[str, Any]:
    monitor_dir = _resolve_path(monitor_dir or os.getenv('DINGTALK_BOT_MONITOR_DIR'), DEFAULT_MONITOR_DIRS)
    watch_path = monitor_dir / 'log_watch_latest.json'
    status_path = monitor_dir / 'dingtalk_autofix_status.json'
    if not status_path.exists():
        status_path = monitor_dir / 'autofix_status.json'
    watch = _load_json(watch_path)
    status = _filter_dingtalk_changed_files(_load_json(status_path))

    live_log = _resolve_path(live_log_path or watch.get('live_log') or os.getenv('DINGTALK_BOT_LIVE_LOG_PATH'), DEFAULT_LIVE_LOGS)
    legacy_log = _resolve_path(legacy_log_path or watch.get('legacy_log') or os.getenv('DINGTALK_BOT_LEGACY_LOG_PATH'), DEFAULT_LEGACY_LOGS)

    live_interactions = list(watch.get('live_interactions') or [])
    legacy_interactions = list(watch.get('legacy_interactions') or [])
    suspicious_live = [item for item in live_interactions if item.get('suspicious')]
    suspicious_legacy = [item for item in legacy_interactions if item.get('suspicious')]

    return {
        'monitor_dir': str(monitor_dir),
        'watch_path': str(watch_path),
        'status_path': str(status_path),
        'watch': {
            **watch,
            'live_category_stats': list(watch.get('live_category_stats') or []),
            'legacy_category_stats': list(watch.get('legacy_category_stats') or []),
        },
        'status': status,
        'live_log_path': str(live_log),
        'legacy_log_path': str(legacy_log),
        'live_log_tail': _tail_lines(live_log, tail_lines),
        'legacy_log_tail': _tail_lines(legacy_log, min(20, tail_lines)),
        'live_interactions': live_interactions,
        'legacy_interactions': legacy_interactions,
        'suspicious_live_interactions': suspicious_live,
        'suspicious_legacy_interactions': suspicious_legacy,
    }
