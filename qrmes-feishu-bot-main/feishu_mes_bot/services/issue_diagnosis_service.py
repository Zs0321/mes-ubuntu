from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List

from .repository_catalog import RepositoryCatalog


RULES = {
    "apk_update": {
        "title": "APK 更新",
        "probable_causes": [
            "服务器 APK 文件名不符合 `AppName v1.2.3_456.apk` 规则，导致 /api/apk/latest 无法识别。",
            "新包只改了 versionName 没改 versionCode，客户端会判断成没有新版本。",
            "APK 没有部署到 `/volume2/MES/QRMES/APK`，或部署脚本没有执行完成。",
        ],
        "actions": [
            "先看 `qrmes-web-core` 的 `/api/apk/latest`、`/api/apk/check-update` 返回。",
            "确认 `qrmes-android/app/build.gradle` 里的 versionCode 已递增。",
            "确认 `qrmes-android/scripts/deploy_apk_to_qrmes_apk.sh` 已把包推到目标目录。",
        ],
        "refs": [
            "/api/apk/latest",
            "/api/apk/check-update",
            "qrmes-android/app/build.gradle",
            "qrmes-android/scripts/deploy_apk_to_qrmes_apk.sh",
        ],
    },
    "web_publish": {
        "title": "Web 发布后打不开",
        "probable_causes": [
            "Web 进程未启动或端口未监听，/health 探测直接失败。",
            "脚本仍检查 `/api/health`，而主服务真实健康地址是 `/health`，会造成误判。",
            "发布后未拉起依赖目录或数据目录异常，导致运行中途退出。",
        ],
        "actions": [
            "先看 `/health`，再看 `/api/health`，两者都失败时再查 `runtime.log` 和 `scripts/status_local.sh`。",
            "确认 `qrmes-web-core/scripts/healthcheck.sh`、`scripts/status_local.sh` 是否存在并可执行。",
            "如果是单机脚本启动，再查 `MESAPP_DATA_DIR/log` 下日志。",
        ],
        "refs": ["/health", "/api/health", "runtime.log", "scripts/status_local.sh"],
    },
    "project_config": {
        "title": "项目配置不同步",
        "probable_causes": [
            "APK 端拿不到服务端配置后回退到了本地缓存或默认配置。",
            "项目配置接口返回正常，但用户没有 `config:read` 或管理权限，导致保存/读取不一致。",
            "服务端项目配置已更新，但 APK 仍使用旧的 apiBaseUrl 或旧缓存。",
        ],
        "actions": [
            "先查 `/api/process-config/projects/<project>/config` 和 `/api/process-config/me/groups`。",
            "让现场补充项目名、产品类型、序列号，再看 `resolve-serial-rule` 的结果。",
            "确认 APK 是否最近切换过内外网地址，避免读到另一套环境。",
        ],
        "refs": [
            "/api/process-config/projects/<project>/config",
            "/api/process-config/me/groups",
            "/api/process-config/resolve-serial-rule",
        ],
    },
    "photo_upload": {
        "title": "照片上传/查图异常",
        "probable_causes": [
            "图片文件上传到了 picture 目录，但 unified.db/process_photos 元数据没有补写成功。",
            "文件名不符合 `serial_step_yyyyMMdd_HHmmss.jpg` 规则，导致 Web 过滤时查不到。",
            "用户实际请求的过滤条件和文件落盘路径不一致。",
        ],
        "actions": [
            "先看 `/api/photos/upload`、`/api/photos/metadata` 是否报错。",
            "同时确认 picture 目录、`unified.db`、`process_photos` 记录是否一致。",
            "补充序列号、项目名、工序名、时间范围后再查列表接口参数。",
        ],
        "refs": ["/api/photos/upload", "/api/photos/metadata", "unified.db", "process_photos"],
    },
    "h2_database": {
        "title": "H2 产品记录库",
        "probable_causes": [
            "产品记录库 `product_records.db` 路径不对，或服务端没有读到正确 DATA_DIR。",
            "接口本身可用，但目标序列号压根不在产品记录库里。",
            "历史数据迁移、去重或绑定项目校验导致查询结果与预期不一致。",
        ],
        "actions": [
            "先访问 `/api/h2/health` 判断服务是不是活着。",
            "确认 `product_records.db` 路径和 DATA_DIR。",
            "再查具体序列号是否真实存在。",
        ],
        "refs": ["/api/h2/health", "product_records.db"],
    },
    "login_permission": {
        "title": "登录/权限",
        "probable_causes": [
            "用户存在于外部系统，但并未在 `web_users.db` 启用。",
            "返回 401 是认证失败，返回 403 多半是账号有了但权限不足。",
            "外网登录开关或角色权限缺失，导致 APK 和 Web 现象不同。",
        ],
        "actions": [
            "先区分 401 还是 403。",
            "确认 `/api/mobile-auth/login` 和 `/api/user/<username>/permissions` 的返回。",
            "检查 `web_users.db`、用户启用状态、`can_external_login` 和角色权限。",
        ],
        "refs": ["/api/mobile-auth/login", "/api/user/<username>/permissions", "web_users.db"],
    },
    "database_generic": {
        "title": "数据库通用问题",
        "probable_causes": [
            "把 `web_users.db`、`product_records.db`、`unified.db`、`material_config.db` 混成同一个问题看了。",
            "DATA_DIR 漂移后，应用和人工排查看的不是同一套数据库文件。",
            "SQLite 文件存在，但权限、锁或 WAL 状态异常。",
        ],
        "actions": [
            "先明确是哪一个库：用户库、产品记录库、照片元数据、物料配置还是活动测试。",
            "确认运行环境解析出的 DATA_DIR。",
            "再检查具体 DB 文件是否存在、是否可写。",
        ],
        "refs": ["web_users.db", "product_records.db", "unified.db", "material_config.db", "active_tests.json"],
    },
    "finance": {
        "title": "Finance / 金蝶",
        "probable_causes": [
            "Finance 服务活着，但 `kingdee_ready=false`，通常是环境变量或金蝶配置没就绪。",
            "缺少 `KINGDEE_*` 配置，或上游金蝶接口认证失败。",
            "运行时环境文件缺失，例如 `.env.finance_demo_125` 没有挂上。",
        ],
        "actions": [
            "先看 `/api/health` 的 `kingdee_ready`。",
            "再看 `/api/kingdee/status` 的 `missing[]` 和表单配置。",
            "确认运行环境文件和金蝶账号配置是否存在。",
        ],
        "refs": ["/api/health", "/api/kingdee/status", ".env.finance_demo_125"],
    },
    "motor_qc": {
        "title": "Motor QC / 相机桥接",
        "probable_causes": [
            "主质检服务正常，但 edge bridge 没起或相机没打开。",
            "MVS/OpenCV 依赖异常，导致 `capture_opened` 或 `mvs_opened` 为 false。",
            "桥接服务在 mock 模式，现场误以为拿到真实相机画面。",
        ],
        "actions": [
            "先看 `/motor-qc/api/health`，再看桥接 `/api/health`。",
            "重点关注 `capture_opened`、`mvs_error`、`last_frame_error`。",
            "如果前端正常但桥接异常，优先查 edge bridge 日志和本地相机驱动。",
        ],
        "refs": ["/motor-qc/api/health", "/api/health", "capture_opened", "mvs_error"],
    },
}


@dataclass
class IssueDiagnosisService:
    repository_catalog: RepositoryCatalog
    probe_service: object
    summary_service: object = None

    def can_handle(self, text: str) -> bool:
        return bool(self.repository_catalog.matched_domains(text))

    def diagnose(self, text: str) -> str:
        domains = self.repository_catalog.matched_domains(text)
        targets = self.repository_catalog.infer_targets(text)
        probe_report = self.probe_service.collect(targets)
        lines = []
        lines.append("问题归类：%s" % self._compose_title(domains))
        lines.append("涉及仓库：%s" % "、".join(targets))
        lines.append("")
        lines.append("自动检查：")
        for target in targets:
            lines.extend(self._format_probe(target, probe_report.get(target, {})))

        sqlite_lines = self._run_sqlite_diagnostics(text, domains)
        if sqlite_lines:
            lines.append("")
            lines.append("SQLite定点诊断：")
            lines.extend(sqlite_lines)

        lines.append("")
        lines.append("高概率原因：")
        for item in self._collect_rule_items(domains, "probable_causes"):
            lines.append("- %s" % item)
        lines.append("")
        lines.append("建议动作：")
        for item in self._collect_rule_items(domains, "actions"):
            lines.append("- %s" % item)
        lines.append("")
        lines.append("关键接口/文件：")
        for item in self._collect_rule_items(domains, "refs"):
            lines.append("- %s" % item)
        diagnosis_text = "\n".join(lines).strip()
        if self.summary_service:
            summary = self.summary_service.summarize(text, diagnosis_text)
            if summary:
                diagnosis_text = diagnosis_text + "\n\n追问建议：\n- " + summary.strip().replace("\n", "\n- ")
        return diagnosis_text

    def _compose_title(self, domains: List[str]) -> str:
        if not domains:
            return "通用排障"
        titles = []
        for domain in domains:
            rule = RULES.get(domain)
            if rule and rule["title"] not in titles:
                titles.append(rule["title"])
        return " + ".join(titles)

    def _collect_rule_items(self, domains: List[str], field: str) -> List[str]:
        items = []
        for domain in domains:
            rule = RULES.get(domain)
            if not rule:
                continue
            for item in rule.get(field, []):
                if item not in items:
                    items.append(item)
        return items

    def _run_sqlite_diagnostics(self, text: str, domains: List[str]) -> List[str]:
        lines = []
        configs = getattr(self.repository_catalog, 'sqlite_diagnostics', {})
        for domain in domains:
            for config in configs.get(domain, []):
                lookup_value = self._extract_lookup_value(text, config.get('extract_pattern', ''))
                if not lookup_value:
                    continue
                db_path = config.get('path', '')
                if not db_path or not os.path.exists(db_path):
                    lines.append('- %s: 数据库不存在 %s' % (config.get('label', 'sqlite'), db_path))
                    continue
                result = self._query_sqlite(config, lookup_value)
                if result:
                    lines.append('- %s: 命中 %s' % (config.get('label', 'sqlite'), result))
                else:
                    lines.append('- %s: 未查到 %s=%s' % (config.get('label', 'sqlite'), config.get('lookup_column'), lookup_value))
        return lines

    def _extract_lookup_value(self, text: str, pattern: str) -> str:
        if not pattern:
            return ''
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return ''
        if match.groups():
            return next((group for group in match.groups() if group), '') or match.group(0)
        return match.group(0)

    def _query_sqlite(self, config: Dict[str, object], lookup_value: str) -> str:
        columns = config.get('select_columns') or [config.get('lookup_column')]
        table = config.get('table')
        lookup_column = config.get('lookup_column')
        sql = 'SELECT %s FROM %s WHERE %s = ? LIMIT 1' % (', '.join(columns), table, lookup_column)
        conn = sqlite3.connect(config.get('path'))
        try:
            row = conn.execute(sql, (lookup_value,)).fetchone()
        finally:
            conn.close()
        if not row:
            return ''
        parts = []
        for key, value in zip(columns, row):
            parts.append('%s=%s' % (key, value))
        return ', '.join(parts)

    def _format_probe(self, target: str, report: Dict[str, list]) -> List[str]:
        lines = ["- %s" % target]
        for health in report.get("health", []):
            status = "OK" if health.get("ok") else "FAIL"
            lines.append("  - 健康 %s: %s" % (health.get("label"), status))
            detail = health.get("detail")
            if detail:
                lines.append("    详情: %s" % detail)
        for script in report.get("scripts", []):
            status = "存在" if script.get("exists") else "缺失"
            if script.get("exists"):
                status += ",可执行" if script.get("executable") else ",不可执行"
            lines.append("  - 脚本 %s: %s" % (script.get("path"), status))
        for file_info in report.get("files", []):
            status = "存在" if file_info.get("exists") else "缺失"
            extra = []
            if file_info.get("kind") == 'log' and file_info.get('tail'):
                extra.append("tail=%s" % file_info.get('tail'))
            if file_info.get("kind") == 'sqlite' and file_info.get('tables'):
                extra.append("tables=%s" % file_info.get('tables'))
            extra_text = ("; " + "; ".join(extra)) if extra else ""
            lines.append("  - 文件 %s: %s%s" % (file_info.get("path"), status, extra_text))
        return lines
