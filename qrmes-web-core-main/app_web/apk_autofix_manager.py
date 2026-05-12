from __future__ import annotations

import difflib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ALLOWED_SEVERITIES = {'fatal', 'error'}
PHOTO_UPLOAD_TARGET = 'app/src/main/java/com/testcenter/qrscanner/PhotoCaptureActivity.kt'
OLD_PHOTO_UPLOAD_TOAST = 'Toast.makeText(this@PhotoCaptureActivity, "上传失败: ${e.message}", Toast.LENGTH_LONG).show()'
NEW_PHOTO_UPLOAD_TOAST = 'Toast.makeText(this@PhotoCaptureActivity, buildUploadFailureMessage(e), Toast.LENGTH_LONG).show()'
HELPER_MARKER = 'private fun buildUploadFailureMessage(error: Throwable?): String'
HELPER_SNIPPET = """

    private fun buildUploadFailureMessage(error: Throwable?): String {
        return when (error) {
            is java.net.SocketTimeoutException -> "上传失败：网络超时，请稍后重试"
            is java.net.UnknownHostException -> "上传失败：无法连接服务器，请检查网络"
            is java.io.IOException -> "上传失败：网络异常，请确认 MES 服务可用"
            else -> {
                val raw = error?.message?.trim().orEmpty()
                if (raw.isNotEmpty()) "上传失败：$raw" else "上传失败，请稍后重试"
            }
        }
    }
"""


class ApkAutofixManager:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _status_path(self, stored_name: str) -> Path:
        safe = Path(stored_name or '').name
        return self.base_dir / f'{safe}.autofix.json'

    def load_status(self, stored_name: str) -> Dict[str, Any]:
        path = self._status_path(stored_name)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def prepare_source_fix(self, record: Dict[str, Any], *, source_repo: str, source_root: Path | None = None) -> Dict[str, Any]:
        stored_name = str(record.get('stored_name') or '').strip()
        severity = str(record.get('severity') or '').strip().lower()
        if not stored_name:
            raise ValueError('missing stored_name')
        if severity not in ALLOWED_SEVERITIES:
            raise ValueError('only fatal/error severities are supported')
        existing = self.load_status(stored_name)
        changed_files: List[str] = []
        patch_text = ''
        diff_preview: List[str] = []
        if source_root is not None:
            changed_files, patch_text, diff_preview = self._apply_known_source_fix(record, Path(source_root))
        payload = {
            **existing,
            'stored_name': stored_name,
            'severity': severity,
            'event_type': str(record.get('event_type') or '').strip(),
            'feature': str(record.get('feature') or '').strip(),
            'reason_code': str(record.get('reason_code') or '').strip(),
            'summary': str(record.get('summary') or '').strip(),
            'source_repo': source_repo,
            'status': 'source_fix_ready',
            'compile_status': existing.get('compile_status') or 'not_started',
            'prepared_at': datetime.now().isoformat(timespec='seconds'),
            'auto_compile': False,
            'scope': 'fatal_error_only',
            'notes': '仅针对 fatal / error 级别日志生成源码修复任务；不会自动编译 APK。',
            'changed_files': changed_files,
            'patch_text': patch_text,
            'diff_preview': diff_preview,
            'hermes_enabled': False,
            'hermes_result': {},
        }
        self._status_path(stored_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return payload

    def enqueue_build(self, stored_name: str, *, requested_by: str) -> Dict[str, Any]:
        payload = self.load_status(stored_name)
        if not payload:
            raise ValueError('autofix status not found')
        payload['compile_status'] = 'build_requested'
        payload['build_requested_at'] = datetime.now().isoformat(timespec='seconds')
        payload['build_requested_by'] = requested_by
        payload['status'] = payload.get('status') or 'source_fix_ready'
        self._status_path(stored_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return payload

    def update_build_status(self, stored_name: str, **fields: Any) -> Dict[str, Any]:
        payload = self.load_status(stored_name)
        if not payload:
            payload = {'stored_name': stored_name}
        payload.update(fields)
        self._status_path(stored_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return payload

    def apply_hermes_fix(
        self,
        stored_name: str,
        *,
        record: Dict[str, Any],
        source_repo: str,
        source_root: Path,
        suggestion: Dict[str, Any],
        started_at: str | None = None,
        repair_source: str = 'manual_hermes_repair',
        next_auto_repair_at: str | None = None,
    ) -> Dict[str, Any]:
        payload = self.load_status(stored_name) or {}
        target_rel = str(suggestion.get('target_file') or '').strip()
        old_string = str(suggestion.get('old_string') or '')
        new_string = str(suggestion.get('new_string') or '')
        summary = str(suggestion.get('summary') or '').strip()
        verification = list(suggestion.get('verification') or [])
        raw = suggestion.get('raw')
        changed_files: List[str] = []
        patch_text = ''
        diff_preview: List[str] = []
        status = 'hermes_analysis_only'
        if target_rel and old_string and new_string:
            target = source_root / target_rel
            if target.exists():
                source = target.read_text(encoding='utf-8')
                if old_string in source:
                    updated = source.replace(old_string, new_string, 1)
                    diff_lines = list(
                        difflib.unified_diff(
                            source.splitlines(),
                            updated.splitlines(),
                            fromfile=str(target),
                            tofile=str(target),
                            lineterm='',
                        )
                    )
                    target.write_text(updated, encoding='utf-8')
                    patch_text = '\n'.join(diff_lines)
                    diff_preview = diff_lines[:80]
                    changed_files = [str(target)]
                    status = 'hermes_fix_applied'
                elif new_string and new_string in source:
                    status = 'hermes_fix_already_applied'
                    changed_files = [str(target)]
                else:
                    status = 'hermes_fix_unapplied'
            else:
                status = 'hermes_target_missing'
        elif target_rel:
            target = source_root / target_rel
            if target.exists():
                status = 'hermes_fix_already_applied'
                changed_files = [str(target)]
        completed_at = datetime.now().isoformat(timespec='seconds')
        history = list(payload.get('diff_history') or [])
        effective_started_at = started_at or payload.get('last_manual_repair_started_at') or payload.get('last_auto_repair_started_at') or completed_at
        history.append({
            'ts': completed_at,
            'started_at': effective_started_at,
            'source': repair_source,
            'status': status,
            'summary': summary,
            'changed_files': changed_files,
            'patch_text': patch_text,
            'diff_preview': diff_preview,
            'verification': verification,
            'target_file': target_rel,
        })
        payload.update({
            'stored_name': stored_name,
            'severity': str(record.get('severity') or '').strip().lower(),
            'event_type': str(record.get('event_type') or '').strip(),
            'feature': str(record.get('feature') or '').strip(),
            'reason_code': str(record.get('reason_code') or '').strip(),
            'summary': str(record.get('summary') or '').strip(),
            'source_repo': source_repo,
            'status': status,
            'compile_status': payload.get('compile_status') or 'not_started',
            'prepared_at': completed_at,
            'auto_compile': False,
            'scope': 'fatal_error_only',
            'notes': 'APK 已接入 Hermes 后台修复模式；仍不会自动编译 APK。',
            'changed_files': changed_files,
            'patch_text': patch_text,
            'diff_preview': diff_preview,
            'diff_history': history[-12:],
            'verification': verification,
            'hermes_enabled': True,
            'hermes_result': {
                'summary': summary,
                'target_file': target_rel,
                'raw': raw,
                'status': status,
            },
        })
        if repair_source == 'cron_auto_hermes_repair':
            payload['last_auto_repair_started_at'] = effective_started_at
            payload['last_auto_repair_completed_at'] = completed_at
            if next_auto_repair_at:
                payload['next_auto_repair_at'] = next_auto_repair_at
        else:
            payload['last_manual_repair_started_at'] = effective_started_at
            payload['last_manual_repair_completed_at'] = completed_at
        self._status_path(stored_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return payload

    def batch_status(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for record in records:
            stored_name = str(record.get('stored_name') or '').strip()
            rows.append({
                **record,
                'autofix': self.load_status(stored_name),
            })
        return rows

    def _apply_known_source_fix(self, record: Dict[str, Any], source_root: Path) -> tuple[List[str], str, List[str]]:
        feature = str(record.get('feature') or '').strip()
        reason_code = str(record.get('reason_code') or '').strip()
        changed: List[str] = []
        patch_chunks: List[str] = []
        diff_preview: List[str] = []
        if feature == 'photo_upload' and reason_code in {
            'network_timeout', 'network_io_error', 'network_dns_failure', 'http_server_error', 'http_upload_failed', 'partial_failure', 'unknown_exception'
        }:
            target = source_root / PHOTO_UPLOAD_TARGET
            file_patch = self._patch_photo_upload_activity(target)
            if file_patch:
                changed.append(str(target))
                patch_chunks.append(file_patch)
                if not diff_preview:
                    diff_preview = file_patch.splitlines()[:80]
        patch_text = '\n\n'.join(chunk for chunk in patch_chunks if chunk).strip()
        return changed, patch_text, diff_preview

    def _patch_photo_upload_activity(self, target: Path) -> str:
        if not target.exists():
            return ''
        source = target.read_text(encoding='utf-8')
        updated = source
        changed = False
        if OLD_PHOTO_UPLOAD_TOAST in updated and NEW_PHOTO_UPLOAD_TOAST not in updated:
            updated = updated.replace(OLD_PHOTO_UPLOAD_TOAST, NEW_PHOTO_UPLOAD_TOAST)
            changed = True
        if HELPER_MARKER not in updated:
            anchor = '    /**\n     * 带结果回传的 finish\n     */'
            if anchor in updated:
                updated = updated.replace(anchor, HELPER_SNIPPET + '\n' + anchor)
                changed = True
        if changed:
            diff_lines = list(
                difflib.unified_diff(
                    source.splitlines(),
                    updated.splitlines(),
                    fromfile=str(target),
                    tofile=str(target),
                    lineterm='',
                )
            )
            target.write_text(updated, encoding='utf-8')
            return '\n'.join(diff_lines)
        return ''
