from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass


@dataclass(slots=True)
class IssueDiagnosisService:
    probe_service: object
    h2_db_path: str = '/volume2/MES/QRMES/record/product_records.db'
    file_downloader: object | None = None

    def can_handle(self, text: str) -> bool:
        content = (text or '').strip().lower()
        if not content:
            return False
        return any(keyword in content for keyword in (
            'web发布', '发布后', '打不开', 'apk更新', '更新失败', '登录403', '登录401', '401', '403', '产品记录库', '查不到', '金蝶', '数据库', '照片上传失败', '日志', '报错', 'traceback', '500', 'connection refused'
        ))

    def diagnose(self, text: str) -> str:
        return self._build_report(text, [])

    def diagnose_message(self, message) -> str | None:
        text = (getattr(message, 'text', '') or '').strip()
        attachments = tuple(getattr(message, 'image_download_codes', ()) or ())
        if not self.can_handle(text) and not attachments:
            return None
        return self._build_report(text, attachments)

    def _build_report(self, text: str, attachments: tuple[str, ...]) -> str:
        content = (text or '').strip()
        lowered = content.lower()
        targets = ['qrmes-web-core']
        if 'apk' in lowered:
            targets.insert(0, 'qrmes-android')
        if '金蝶' in content or 'finance' in lowered:
            targets.append('qrmes-finance-service')
        targets = tuple(dict.fromkeys(targets))
        report = self.probe_service.collect(list(targets)) if self.probe_service else {}
        lines = []
        lines.append(f'问题归类：{self._category(content, attachments)}')
        lines.append('涉及仓库：' + '、'.join(targets))
        lines.append('')
        lines.append('自动检查：')
        for target in targets:
            lines.extend(self._format_probe(target, report.get(target, {})))
        sqlite_lines = self._sqlite_diagnosis(content)
        if sqlite_lines:
            lines.append('')
            lines.append('SQLite定点诊断：')
            lines.extend(sqlite_lines)
        log_lines = self._attachment_diagnosis(attachments)
        if log_lines:
            lines.append('')
            lines.append('日志诊断：')
            lines.extend(log_lines)
        lines.append('')
        lines.append('高概率原因：')
        for item in self._causes(content, log_lines):
            lines.append('- ' + item)
        lines.append('')
        lines.append('建议动作：')
        for item in self._actions(content, log_lines):
            lines.append('- ' + item)
        return '\n'.join(lines)

    def _category(self, text: str, attachments: tuple[str, ...]) -> str:
        lowered = text.lower()
        if attachments and ('日志' in text or '[文件消息]' in text or 'traceback' in lowered or '500' in text):
            return '日志/服务异常诊断'
        if 'apk' in lowered:
            return 'APK 更新/客户端访问'
        if '金蝶' in text or 'finance' in lowered:
            return 'Finance / 金蝶'
        if '产品记录库' in text or '查不到' in text:
            return 'H2 产品记录库'
        if '401' in text or '403' in text or '登录' in text:
            return '登录/权限'
        return 'Web/后端发布诊断'

    def _causes(self, text: str, log_lines: list[str]) -> list[str]:
        lowered = text.lower()
        joined_logs = ' '.join(log_lines).lower()
        if log_lines:
            causes = []
            if 'connection refused' in joined_logs:
                causes.append('日志里出现 connection refused，通常是目标服务未启动、端口未监听，或反向代理指向错误地址。')
            if 'http 500' in joined_logs or '500' in joined_logs:
                causes.append('日志里出现 HTTP 500，说明服务端已经报错，优先看后端异常栈和依赖配置。')
            if 'traceback' in joined_logs:
                causes.append('日志里有 Traceback，说明不是前端展示问题，而是服务端执行过程中抛异常。')
            if 'sqlite' in joined_logs and 'locked' in joined_logs:
                causes.append('日志里出现 sqlite locked，说明并发写入冲突或事务未及时释放。')
            if causes:
                return causes
        if 'apk' in lowered:
            return [
                'APK 文件名或版本号不符合更新规则，服务端无法识别最新包。',
                '客户端 base URL 指到了旧环境，导致更新检查或接口访问异常。',
            ]
        if '金蝶' in text or 'finance' in lowered:
            return [
                '金蝶环境变量未就绪，接口健康状态可能显示 kingdee_ready=false。',
                '上游金蝶接口认证失败或网络不可达。',
            ]
        if '产品记录库' in text or '查不到' in text:
            return [
                '产品记录库路径不对，或序列号本身不在数据库里。',
                '当前环境读到的不是同一套 product_records.db。',
            ]
        if '401' in text or '403' in text or '登录' in text:
            return [
                '登录态已失效，或请求没有带上有效 token / cookie。',
                '当前账号没有对应接口、页面或工序权限，导致网关或服务直接拒绝。',
            ]
        return [
            'Web 服务未正常启动，或发布后健康检查路径不一致。',
            '运行日志里已有异常，但现场只看到了页面打不开。',
        ]

    def _actions(self, text: str, log_lines: list[str]) -> list[str]:
        lowered = text.lower()
        joined_logs = ' '.join(log_lines).lower()
        if log_lines:
            actions = ['先按日志里最早出现的错误关键词定位具体服务，再回头看前端现象。']
            if 'connection refused' in joined_logs:
                actions.append('确认被调用服务进程是否在运行，以及端口和目标地址是否正确。')
            if 'http 500' in joined_logs or '500' in joined_logs:
                actions.append('查看对应后端服务 runtime.log / traceback，优先处理服务端异常。')
            if 'sqlite' in joined_logs and 'locked' in joined_logs:
                actions.append('检查是否存在高并发写入、未提交事务或长事务占锁。')
            return actions
        if 'apk' in lowered:
            return [
                '先确认 /api/apk/latest 和 /api/apk/check-update 返回。',
                '检查 qrmes-android 的 versionCode 是否递增。',
            ]
        if '金蝶' in text or 'finance' in lowered:
            return [
                '先查看 /api/health 和 /api/kingdee/status。',
                '确认 .env.finance_demo_125 及 KINGDEE_* 配置。',
            ]
        if '产品记录库' in text or '查不到' in text:
            return [
                '先看 /api/h2/health，再确认 product_records.db 实际路径。',
                '用具体序列号做 SQLite 定点查询确认数据是否存在。',
            ]
        if '401' in text or '403' in text or '登录' in text:
            return [
                '先抓一条失败请求，对比正常请求是否缺少 Authorization、Cookie 或 token。',
                '再按报错时间查网关和后端日志，确认是登录态失效还是账号权限不足。',
            ]
        return [
            '先看 /health 和 /api/health，再查 runtime.log / status_local.sh。',
            '如果是 401/403，再确认当前账号权限与登录态。',
        ]

    def _format_probe(self, target: str, report: dict) -> list[str]:
        lines = [f'- {target}']
        for health in report.get('health', []):
            status = 'OK' if health.get('ok') else 'FAIL'
            lines.append(f"  - 健康 {health.get('label')}: {status}")
            if health.get('detail'):
                lines.append(f"    详情: {health.get('detail')}")
        return lines

    def _sqlite_diagnosis(self, text: str) -> list[str]:
        serial = self._extract_serial(text)
        if not serial:
            return []
        if not os.path.exists(self.h2_db_path):
            return [f'- product_records: 数据库不存在 {self.h2_db_path}']
        try:
            conn = sqlite3.connect(self.h2_db_path)
            row = conn.execute(
                'SELECT product_serial, project_name, product_type FROM product_records WHERE product_serial = ? LIMIT 1',
                (serial,),
            ).fetchone()
            conn.close()
        except Exception as exc:
            return [f'- product_records: 查询失败 {exc}']
        if not row:
            return [f'- product_records: 未查到 product_serial={serial}']
        return [f'- product_records: product_serial={row[0]}, project_name={row[1]}, product_type={row[2]}']

    def _attachment_diagnosis(self, attachments: tuple[str, ...]) -> list[str]:
        if not attachments or not self.file_downloader:
            return []
        try:
            files = self.file_downloader.download_images(attachments)
        except Exception as exc:
            return [f'- 文件下载失败: {exc}']
        if not files:
            return ['- 文件下载失败或无可解析内容']
        raw = files[0].data.decode('utf-8', errors='ignore')
        lines = []
        excerpt = '\n'.join([line.strip() for line in raw.splitlines() if line.strip()][:8])
        if excerpt:
            lines.append(f'- 日志摘录: {excerpt}')
        lowered = raw.lower()
        for token in ('traceback', 'connection refused', 'http 500', '401', '403', 'sqlite', 'locked', 'timeout', 'kingdee', 'webdav', 'smb'):
            if token in lowered:
                lines.append(f'- 命中关键字: {token}')
        return lines

    def _extract_serial(self, text: str) -> str | None:
        match = re.search(r'(SN\d{4,}|[A-Z]{2}\d{4,})', text, re.IGNORECASE)
        if not match:
            return None
        return match.group(1)
