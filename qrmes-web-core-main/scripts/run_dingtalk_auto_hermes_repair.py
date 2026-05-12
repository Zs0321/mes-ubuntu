#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_WEB_DIR = REPO_ROOT / 'app_web'
if str(APP_WEB_DIR) not in sys.path:
    sys.path.insert(0, str(APP_WEB_DIR))

from dingtalk_bot_monitor import load_bot_monitor_snapshot  # noqa: E402
from dingtalk_hermes_repair_service import DingTalkHermesRepairService  # noqa: E402

DEFAULT_REPO_CANDIDATES = (
    '/volume2/mes_ubuntu_split_result/qrmes-dingtalk-bot',
    '/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-dingtalk-bot',
)


def resolve_repo_root() -> Path:
    env_path = os.getenv('DINGTALK_AUTO_REPAIR_REPO')
    if env_path and Path(env_path).exists():
        return Path(env_path)
    for candidate in DEFAULT_REPO_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path
    return Path(DEFAULT_REPO_CANDIDATES[0])


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def append_runtime_log(path: Path, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec='seconds')
    payload = [f'[{now}] {title}']
    payload.extend(str(line) for line in lines if str(line).strip())
    with path.open('a', encoding='utf-8') as fh:
        fh.write('\n'.join(payload) + '\n')


def compute_next_run(now: datetime, every_minutes: int) -> str:
    slot = max(1, every_minutes)
    next_slot = now.replace(second=0, microsecond=0) + timedelta(minutes=slot)
    return next_slot.isoformat(timespec='seconds')


def append_diff_history(status_payload: dict[str, Any], entry: dict[str, Any], limit: int = 12) -> None:
    history = list(status_payload.get('diff_history') or [])
    history.append(entry)
    status_payload['diff_history'] = history[-limit:]


def main() -> None:
    repo_root = resolve_repo_root()
    monitor_dir = repo_root / 'monitor'
    repair_log_path = monitor_dir / 'repair_runtime.log'
    schedule_minutes = int(os.getenv('DINGTALK_AUTO_REPAIR_INTERVAL_MINUTES', '15') or '15')
    base_url = os.getenv('DINGTALK_HERMES_BASE_URL') or os.getenv('DINGTALK_BOT_HERMES_BASE_URL') or 'http://172.16.20.201:8787'
    model = os.getenv('DINGTALK_HERMES_MODEL') or os.getenv('DINGTALK_BOT_HERMES_MODEL') or 'gpt-5.5'

    snapshot = load_bot_monitor_snapshot(monitor_dir=monitor_dir, tail_lines=80)
    status_path = Path(snapshot.get('status_path') or (monitor_dir / 'dingtalk_autofix_status.json'))
    status_payload = load_json(status_path)
    now = datetime.now()
    started_at = now.isoformat(timespec='seconds')
    next_run_at = compute_next_run(now, schedule_minutes)
    task_id = now.strftime('%Y%m%d%H%M%S')

    status_payload.update({
        'auto_repair_enabled': True,
        'auto_repair_schedule': f'every {schedule_minutes}m',
        'last_auto_repair_started_at': started_at,
        'next_auto_repair_at': next_run_at,
    })

    suspicious_items = list(snapshot.get('suspicious_live_interactions') or [])
    append_runtime_log(
        repair_log_path,
        '钉钉自动 Hermes 修复开始',
        [
            f'task_id={task_id}',
            f'base_url={base_url}',
            f'model={model}',
            f'status_path={status_path}',
            f'suspicious_count={len(suspicious_items)}',
            f'next_run_at={next_run_at}',
        ],
    )

    if not suspicious_items:
        completed_at = datetime.now().isoformat(timespec='seconds')
        status_payload.update({
            'checked_at': completed_at,
            'last_auto_repair_completed_at': completed_at,
            'last_action': '钉钉自动 Hermes 修复 skipped_no_suspicious',
            'summary': status_payload.get('summary') or '当前未发现新的可疑问答，无需自动修复。',
        })
        append_diff_history(status_payload, {
            'ts': completed_at,
            'started_at': started_at,
            'source': 'cron_auto_hermes_repair',
            'status': 'skipped_no_suspicious',
            'summary': '当前未发现新的可疑问答，无需自动修复。',
            'changed_files': [],
            'patch_text': '',
            'diff_preview': [],
            'verification': [],
        })
        status_path.write_text(json.dumps(status_payload, ensure_ascii=False, indent=2), encoding='utf-8')
        append_runtime_log(repair_log_path, '钉钉自动 Hermes 修复完成', [f'task_id={task_id}', 'status=skipped_no_suspicious'])
        print(json.dumps({'success': True, 'task_id': task_id, 'status': 'skipped_no_suspicious'}, ensure_ascii=False))
        return

    service = DingTalkHermesRepairService(base_url=base_url, workspace=str(repo_root), model=model)
    issue_fixes = service.suggest_issue_fixes(snapshot=snapshot)
    for issue in issue_fixes:
        append_runtime_log(
            repair_log_path,
            f"钉钉自动 issue 分析 {issue.get('issue_id') or 'issue-unknown'}",
            [
                f"question={issue.get('question') or ''}",
                f"reply={issue.get('reply') or ''}",
                f"root_cause={issue.get('root_cause') or ''}",
                f"fix_strategy={issue.get('fix_strategy') or ''}",
                (issue.get('raw') or '')[:2000],
            ],
        )

    suggestion = service.suggest_fix(snapshot={**snapshot, 'issue_fixes': issue_fixes}, source_root=repo_root)
    append_runtime_log(
        repair_log_path,
        '钉钉自动 Hermes 汇总修复建议',
        [
            f'task_id={task_id}',
            f"summary={suggestion.get('summary') or ''}",
            f"target_file={suggestion.get('target_file') or ''}",
            f"verification={suggestion.get('verification') or []}",
            (suggestion.get('raw') or '')[:4000],
        ],
    )

    changed_files: list[str] = []
    patch_text = ''
    diff_preview: list[str] = []
    status_value = 'hermes_analysis_only'
    target_rel = str(suggestion.get('target_file') or '').strip()
    old_string = str(suggestion.get('old_string') or '')
    new_string = str(suggestion.get('new_string') or '')
    if target_rel and old_string and new_string:
        patch_target = repo_root / target_rel
        if patch_target.exists():
            source_text = patch_target.read_text(encoding='utf-8')
            if old_string in source_text:
                updated = source_text.replace(old_string, new_string, 1)
                diff_lines = list(difflib.unified_diff(source_text.splitlines(), updated.splitlines(), fromfile=str(patch_target), tofile=str(patch_target), lineterm=''))
                patch_target.write_text(updated, encoding='utf-8')
                patch_text = '\n'.join(diff_lines)
                diff_preview = diff_lines[:120]
                changed_files = [str(patch_target)]
                status_value = 'hermes_fix_applied'
            elif new_string and new_string in source_text:
                changed_files = [str(patch_target)]
                status_value = 'hermes_fix_already_applied'
            else:
                status_value = 'hermes_fix_unapplied'
        else:
            status_value = 'hermes_target_missing'
    elif target_rel:
        patch_target = repo_root / target_rel
        if patch_target.exists():
            changed_files = [str(patch_target)]
            status_value = 'hermes_fix_already_applied'

        else:
            status_value = 'hermes_target_missing'

    completed_at = datetime.now().isoformat(timespec='seconds')
    status_payload.update({
        'checked_at': completed_at,
        'last_auto_repair_completed_at': completed_at,
        'last_action': f'钉钉自动 Hermes 修复 {status_value}',
        'summary': suggestion.get('summary') or status_payload.get('summary') or '钉钉自动 Hermes 修复已执行。',
        'changed_files': changed_files,
        'patch_text': patch_text,
        'diff_preview': diff_preview,
        'verification': list(suggestion.get('verification') or []),
        'issue_fixes': issue_fixes,
        'hermes_enabled': True,
        'hermes_result': {
            'summary': suggestion.get('summary') or '',
            'target_file': target_rel,
            'raw': suggestion.get('raw') or '',
            'status': status_value,
        },
    })
    append_diff_history(status_payload, {
        'ts': completed_at,
        'started_at': started_at,
        'source': 'cron_auto_hermes_repair',
        'status': status_value,
        'summary': suggestion.get('summary') or '',
        'changed_files': changed_files,
        'patch_text': patch_text,
        'diff_preview': diff_preview,
        'verification': list(suggestion.get('verification') or []),
        'target_file': target_rel,
    })
    status_path.write_text(json.dumps(status_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    append_runtime_log(
        repair_log_path,
        '钉钉自动 Hermes 修复完成',
        [
            f'task_id={task_id}',
            f'status={status_value}',
            f'changed_files={changed_files}',
            f'next_run_at={next_run_at}',
        ],
    )
    print(json.dumps({'success': True, 'task_id': task_id, 'status': status_value, 'changed_files': changed_files}, ensure_ascii=False))


if __name__ == '__main__':
    main()
