from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DIALOG_FRAGMENT_TARGET = 'app/src/main/java/com/testcenter/qrscanner/QualityProcessDetailDialogFragment.kt'
DIALOG_FRAGMENT_OLD_SNIPPET = """    private lateinit var photoAdapter: QualityDetailPhotoAdapter
    private val apiService by lazy { ApiClient.getApiService(requireContext()) }
    private var activePhoto: QualityPhotoDto? = null
    private var hasRequestedDetail: Boolean = false
    private var detailJob: Job? = null

    override fun onCreateDialog(savedInstanceState: Bundle?): Dialog {
        _binding = DialogQualityProcessDetailBinding.inflate(LayoutInflater.from(requireContext()))
        setupUi()
        return MaterialAlertDialogBuilder(requireContext())
            .setView(binding.root)
            .create()
    }
"""

DIALOG_FRAGMENT_NEW_SNIPPET = """    private lateinit var photoAdapter: QualityDetailPhotoAdapter
    private var activePhoto: QualityPhotoDto? = null
    private var hasRequestedDetail: Boolean = false
    private var detailJob: Job? = null

    private fun getApiServiceOrNull() = context?.let { ApiClient.getApiService(it) }

    override fun onCreateDialog(savedInstanceState: Bundle?): Dialog {
        val currentBinding = DialogQualityProcessDetailBinding.inflate(LayoutInflater.from(requireContext()))
        _binding = currentBinding
        setupUi(currentBinding)
        return MaterialAlertDialogBuilder(requireContext())
            .setView(currentBinding.root)
            .create()
    }
"""

SETUP_UI_OLD_SNIPPET = """    private fun setupUi() {
        binding.btnClose.setOnClickListener { dismissAllowingStateLoss() }
        binding.btnOpenFullScreen.setOnClickListener { openFullScreenPhoto() }
        binding.btnDeletePhoto.setOnClickListener { confirmDeleteCurrentPhoto() }
        binding.ivPreview.setOnClickListener { openFullScreenPhoto() }

        photoAdapter = QualityDetailPhotoAdapter { photo ->
            showPhoto(photo)
        }
        binding.recyclerViewPhotos.apply {
            layoutManager = LinearLayoutManager(requireContext(), LinearLayoutManager.HORIZONTAL, false)
            adapter = photoAdapter
            isNestedScrollingEnabled = false
        }
    }
"""

SETUP_UI_NEW_SNIPPET = """    private fun setupUi(currentBinding: DialogQualityProcessDetailBinding) {
        currentBinding.btnClose.setOnClickListener { dismissAllowingStateLoss() }
        currentBinding.btnOpenFullScreen.setOnClickListener { openFullScreenPhoto() }
        currentBinding.btnDeletePhoto.setOnClickListener { confirmDeleteCurrentPhoto() }
        currentBinding.ivPreview.setOnClickListener { openFullScreenPhoto() }

        photoAdapter = QualityDetailPhotoAdapter { photo ->
            showPhoto(photo)
        }
        currentBinding.recyclerViewPhotos.apply {
            layoutManager = LinearLayoutManager(currentBinding.root.context, LinearLayoutManager.HORIZONTAL, false)
            adapter = photoAdapter
            isNestedScrollingEnabled = false
        }
    }
"""

API_SERVICE_OLD_SNIPPET = '        val service = apiService\n'
API_SERVICE_NEW_SNIPPET = '        val service = getApiServiceOrNull() ?: return\n'

PHOTO_CAPTURE_TARGET = 'app/src/main/java/com/testcenter/qrscanner/PhotoCaptureActivity.kt'
PHOTO_UPLOAD_OLD_SNIPPET = 'Toast.makeText(this@PhotoCaptureActivity, "上传失败: ${e.message}", Toast.LENGTH_LONG).show()'
PHOTO_UPLOAD_NEW_SNIPPET = 'Toast.makeText(this@PhotoCaptureActivity, buildUploadFailureMessage(e), Toast.LENGTH_LONG).show()'
PHOTO_UPLOAD_HELPER_MARKER = 'private fun buildUploadFailureMessage(error: Throwable?): String'
PHOTO_UPLOAD_HELPER_SNIPPET = """

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


@dataclass(slots=True)
class ApkHermesRepairService:
    base_url: str
    workspace: str
    model: str = 'gpt-5.5'
    timeout: float = 60.0

    def suggest_fix(self, *, record: dict[str, Any], source_root: Path) -> dict[str, Any]:
        target = source_root / 'app/src/main/java/com/testcenter/qrscanner/PhotoCaptureActivity.kt'
        current = ''
        if target.exists():
            current = target.read_text(encoding='utf-8')[:20000]
        prompt = (
            '你是 APK Kotlin 修复助手。请基于给定日志与文件内容，输出严格 JSON，不要输出任何多余文字。\n'
            '返回字段固定为：summary,target_file,old_string,new_string,verification。\n'
            '要求：\n'
            '1. 仅在非常确定时返回 old_string/new_string；\n'
            '2. 如果无法安全修改，old_string 和 new_string 返回空字符串；\n'
            '3. verification 返回字符串数组；\n'
            '4. target_file 只能填写相对路径。\n\n'
            f'日志摘要: {record.get("summary") or ""}\n'
            f'severity: {record.get("severity") or ""}\n'
            f'feature: {record.get("feature") or ""}\n'
            f'reason_code: {record.get("reason_code") or ""}\n'
            f'event_type: {record.get("event_type") or ""}\n'
            f'extra_json: {record.get("extra_json") or ""}\n'
            f'候选文件: {target.relative_to(source_root) if target.exists() else "app/src/main/java/com/testcenter/qrscanner/PhotoCaptureActivity.kt"}\n'
            '文件内容如下:\n'
            f'{current}'
        )
        raw = self._chat([
            {'role': 'system', 'content': '你只返回 JSON。'},
            {'role': 'user', 'content': prompt},
        ])
        if not raw:
            return self._rule_based_fix(record=record, source_root=source_root)
        try:
            data = json.loads(raw)
        except Exception:
            fallback = self._rule_based_fix(record=record, source_root=source_root)
            if fallback.get('target_file'):
                fallback['summary'] = fallback.get('summary') or 'Hermes 返回了非 JSON 内容，已切到规则修复。'
                fallback['raw'] = raw
                return fallback
            return {
                'summary': 'Hermes 返回了非 JSON 内容',
                'target_file': '',
                'old_string': '',
                'new_string': '',
                'verification': [],
                'raw': raw,
            }
        if not isinstance(data, dict):
            return self._rule_based_fix(record=record, source_root=source_root)
        data.setdefault('summary', '')
        data.setdefault('target_file', '')
        data.setdefault('old_string', '')
        data.setdefault('new_string', '')
        data['verification'] = list(data.get('verification') or [])
        data['raw'] = raw
        if data['target_file'] and data['old_string'] and data['new_string']:
            return data
        fallback = self._rule_based_fix(record=record, source_root=source_root)
        if fallback.get('target_file'):
            fallback['summary'] = data.get('summary') or fallback.get('summary')
            fallback['raw'] = raw
            return fallback
        return data

    def _chat(self, messages: list[dict[str, Any]]) -> str | None:
        if not self.base_url.strip():
            return None
        session = self._post('/api/session/new', {'workspace': self.workspace, 'model': self.model})
        session_id = ((session or {}).get('session') or {}).get('session_id')
        if not session_id:
            return None
        merged = []
        for msg in messages:
            content = str(msg.get('content') or '').strip()
            if not content:
                continue
            merged.append(f'[{msg.get("role") or "user"}] {content}')
        prompt = '\n\n'.join(merged).strip()
        if not prompt:
            return None
        answer = self._post('/api/chat', {
            'session_id': session_id,
            'workspace': self.workspace,
            'model': self.model,
            'message': prompt,
        })
        raw = (answer or {}).get('answer')
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        req = urllib.request.Request(
            self.base_url.rstrip('/') + path,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode('utf-8', errors='replace')
        except Exception:
            return None
        try:
            data = json.loads(body)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _rule_based_fix(self, *, record: dict[str, Any], source_root: Path) -> dict[str, Any]:
        extra_json = str(record.get('extra_json') or '')
        summary = str(record.get('summary') or '')
        feature = str(record.get('feature') or '').strip()
        reason_code = str(record.get('reason_code') or '').strip()
        if feature == 'photo_upload' and reason_code in {'network_timeout', 'network_io_error', 'network_dns_failure', 'http_server_error', 'http_upload_failed', 'partial_failure', 'unknown_exception'}:
            target = source_root / PHOTO_CAPTURE_TARGET
            if not target.exists():
                return {'summary': '', 'target_file': '', 'old_string': '', 'new_string': '', 'verification': []}
            original = target.read_text(encoding='utf-8')
            updated = original.replace(PHOTO_UPLOAD_OLD_SNIPPET, PHOTO_UPLOAD_NEW_SNIPPET, 1)
            if PHOTO_UPLOAD_HELPER_MARKER not in updated:
                anchor = '    /**\n     * 上传成功后进行 QC 分析\n     */'
                if anchor in updated:
                    updated = updated.replace(anchor, PHOTO_UPLOAD_HELPER_SNIPPET + '\n' + anchor, 1)
            if updated == original:
                return {
                    'summary': '照片上传错误提示增强已在当前源码中存在。',
                    'target_file': PHOTO_CAPTURE_TARGET,
                    'old_string': '',
                    'new_string': '',
                    'verification': ['确认照片上传失败时提示更明确的网络/服务异常原因。'],
                }
            return {
                'summary': '已按照片上传失败规则回退修复 PhotoCaptureActivity 上传错误提示。',
                'target_file': PHOTO_CAPTURE_TARGET,
                'old_string': original,
                'new_string': updated,
                'verification': [
                    '确认照片上传失败时不再只显示原始异常，而是展示更明确的网络/服务提示。',
                    '确认照片上传成功链路和 QC 分析入口不受影响。',
                ],
            }
        if 'QualityProcessDetailDialogFragment' not in extra_json and 'NullPointerException' not in summary:
            return {'summary': '', 'target_file': '', 'old_string': '', 'new_string': '', 'verification': []}
        target = source_root / DIALOG_FRAGMENT_TARGET
        if not target.exists():
            return {'summary': '', 'target_file': '', 'old_string': '', 'new_string': '', 'verification': []}
        original = target.read_text(encoding='utf-8')
        updated = original
        updated = updated.replace(DIALOG_FRAGMENT_OLD_SNIPPET, DIALOG_FRAGMENT_NEW_SNIPPET, 1)
        updated = updated.replace(SETUP_UI_OLD_SNIPPET, SETUP_UI_NEW_SNIPPET, 1)
        updated = updated.replace(API_SERVICE_OLD_SNIPPET, API_SERVICE_NEW_SNIPPET, 1)
        if updated == original:
            return {
                'summary': 'QualityProcessDetailDialogFragment 的 view binding / context 生命周期防护已在当前源码中存在。',
                'target_file': DIALOG_FRAGMENT_TARGET,
                'old_string': '',
                'new_string': '',
                'verification': [
                    '重复打开/关闭工序详情弹窗后，再触发详情加载失败，不应再因 binding/context 失效导致崩溃。',
                    '确认工序详情弹窗仍能正常显示图片列表、错误提示和删除按钮。',
                ],
            }
        return {
            'summary': '已按 NullPointerException 规则回退修复 QualityProcessDetailDialogFragment 的 view binding / context 获取时机。',
            'target_file': DIALOG_FRAGMENT_TARGET,
            'old_string': original,
            'new_string': updated,
            'verification': [
                '重复打开/关闭工序详情弹窗后，再触发详情加载失败，不应再因 binding/context 失效导致崩溃。',
                '确认工序详情弹窗仍能正常显示图片列表、错误提示和删除按钮。',
            ],
        }
