#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_WEB_DIR = REPO_ROOT / 'app_web'
if str(APP_WEB_DIR) not in sys.path:
    sys.path.insert(0, str(APP_WEB_DIR))

from apk_autofix_manager import ApkAutofixManager  # noqa: E402
from apk_hermes_repair_service import ApkHermesRepairService  # noqa: E402
from apk_log_manager import ApkLogManager  # noqa: E402
from repair_log_manager import RepairLogManager  # noqa: E402

APK_LOGS_DIR = Path('/Volumes/172.16.30.10/volume2/MES/QRMES/log/apk_uploads')
APK_AUTOFIX_DIR = Path('/Volumes/172.16.30.10/volume2/MES/QRMES/log/apk_autofix')
APK_REPAIR_LOG_PATH = Path('/Volumes/172.16.30.10/volume2/MES/QRMES/log/apk_repair_runtime.log')
APK_ANDROID_SOURCE_ROOT = Path('/Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-android')


def compute_next_run(now: datetime, every_minutes: int) -> str:
    slot = max(1, every_minutes)
    next_slot = now.replace(second=0, microsecond=0) + timedelta(minutes=slot)
    return next_slot.isoformat(timespec='seconds')


def main() -> None:
    interval = int(os.getenv('APK_AUTO_REPAIR_INTERVAL_MINUTES', '20') or '20')
    limit = int(os.getenv('APK_AUTO_REPAIR_LIMIT', '10') or '10')
    base_url = os.getenv('APK_HERMES_BASE_URL') or os.getenv('DINGTALK_BOT_HERMES_BASE_URL') or 'http://172.16.20.201:8787'
    model = os.getenv('APK_HERMES_MODEL') or os.getenv('DINGTALK_BOT_HERMES_MODEL') or 'gpt-5.5'
    started_at = datetime.now().isoformat(timespec='seconds')
    next_run_at = compute_next_run(datetime.now(), interval)

    log_manager = RepairLogManager(APK_REPAIR_LOG_PATH)
    apk_log_manager = ApkLogManager(APK_LOGS_DIR)
    autofix_manager = ApkAutofixManager(APK_AUTOFIX_DIR)
    hermes_service = ApkHermesRepairService(base_url=base_url, workspace=str(APK_ANDROID_SOURCE_ROOT), model=model)

    rows = apk_log_manager.list_uploads(limit=max(limit * 3, limit))
    candidates = [
        row for row in rows
        if str(row.get('severity') or '').strip().lower() in {'fatal', 'error'}
    ][:limit]

    task_id = datetime.now().strftime('%Y%m%d%H%M%S')
    log_manager.append(
        'APK 自动 Hermes 修复开始',
        [
            f'task_id={task_id}',
            f'base_url={base_url}',
            f'model={model}',
            f'candidate_count={len(candidates)}',
            f'next_run_at={next_run_at}',
        ],
    )

    results = []
    for record in candidates:
        stored_name = str(record.get('stored_name') or '').strip()
        if not stored_name:
            continue
        suggestion = hermes_service.suggest_fix(record=record, source_root=APK_ANDROID_SOURCE_ROOT)
        status = autofix_manager.apply_hermes_fix(
            stored_name,
            record=record,
            source_repo='qrmes-android',
            source_root=APK_ANDROID_SOURCE_ROOT,
            suggestion=suggestion,
            started_at=started_at,
            repair_source='cron_auto_hermes_repair',
            next_auto_repair_at=next_run_at,
        )
        results.append({
            'stored_name': stored_name,
            'status': status.get('status'),
            'changed_files': status.get('changed_files') or [],
        })
        log_manager.append(
            f'APK 自动 Hermes 修复完成 stored_name={stored_name}',
            [
                f'status={status.get("status")}',
                f'changed_files={status.get("changed_files") or []}',
                f'next_auto_repair_at={next_run_at}',
            ],
        )

    print(json.dumps({
        'success': True,
        'task_id': task_id,
        'candidate_count': len(candidates),
        'next_run_at': next_run_at,
        'results': results,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
