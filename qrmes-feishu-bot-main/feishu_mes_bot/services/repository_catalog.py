from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RepositoryTarget:
    key: str
    title: str
    repo_dir: str
    aliases: tuple = field(default_factory=tuple)
    health_checks: tuple = field(default_factory=tuple)
    script_paths: tuple = field(default_factory=tuple)
    file_paths: tuple = field(default_factory=tuple)


class RepositoryCatalog:
    def __init__(self):
        self.targets = {
            "qrmes-android": RepositoryTarget(
                key="qrmes-android",
                title="Android/APK 客户端",
                repo_dir="qrmes-android",
                aliases=("apk", "android", "客户端", "移动端"),
                script_paths=("scripts/deploy_apk_to_qrmes_apk.sh",),
                file_paths=("app/build.gradle",),
            ),
            "qrmes-web-core": RepositoryTarget(
                key="qrmes-web-core",
                title="Web 核心服务",
                repo_dir="qrmes-web-core",
                aliases=("web", "发布", "网站", "后端", "登录", "照片", "配置", "数据库"),
                health_checks=(("web /health", "http://127.0.0.1:9001/health"), ("web /api/health", "http://127.0.0.1:9001/api/health"), ("H2 /api/h2/health", "http://127.0.0.1:9001/api/h2/health")),
                script_paths=("scripts/healthcheck.sh", "scripts/status_local.sh"),
                file_paths=("runtime.log", "runtime.pid", "app_web/mesapp.py", "unified.db", "product_records.db", "web_users.db"),
            ),
            "qrmes-finance-service": RepositoryTarget(
                key="qrmes-finance-service",
                title="Finance / 金蝶服务",
                repo_dir="qrmes-finance-service",
                aliases=("finance", "金蝶", "报价", "财务"),
                health_checks=(("finance /api/health", "http://127.0.0.1:9003/api/health"), ("finance /api/kingdee/status", "http://127.0.0.1:9003/api/kingdee/status")),
                script_paths=("scripts/healthcheck.sh", "scripts/status_local.sh"),
                file_paths=("runtime.log", "runtime.pid", "app_web/finance_demo.py"),
            ),
            "qrmes-motor-qc": RepositoryTarget(
                key="qrmes-motor-qc",
                title="Motor QC / 边缘质检",
                repo_dir="qrmes-motor-qc",
                aliases=("motor", "质检", "相机", "edge", "桥接"),
                health_checks=(("motor-qc /health", "http://127.0.0.1:9002/motor-qc/api/health"), ("edge bridge /api/health", "http://127.0.0.1:9002/api/health")),
                script_paths=("scripts/healthcheck.sh", "scripts/status_local.sh"),
                file_paths=("runtime.log", "runtime.pid", "app_web/run_motor_qc.py"),
            ),
        }
        self.domain_keywords = {
            "apk_update": ("apk更新", "更新失败", "下载apk", "版本"),
            "web_publish": ("web发布", "打不开", "部署后", "页面打不开", "白屏"),
            "project_config": ("项目配置", "不同步", "工序", "责任部门", "序列号规则"),
            "photo_upload": ("照片", "图片", "上传失败", "查不到图片", "元数据"),
            "h2_database": ("h2", "产品记录", "序列号查不到"),
            "login_permission": ("登录", "权限", "401", "403", "用户"),
            "database_generic": ("数据库", "db", "sqlite", "锁表", "数据没了"),
            "finance": ("金蝶", "finance", "报价", "财务"),
            "motor_qc": ("motor", "质检", "相机", "edge", "桥接"),
        }
        self.sqlite_diagnostics = {
            'h2_database': [
                {
                    'path': '/volume2/MES/QRMES/record/product_records.db',
                    'table': 'product_records',
                    'lookup_column': 'product_serial',
                    'extract_pattern': '([A-Z]{2}\d{4,}|SN\d{4,})',
                    'select_columns': ['product_serial', 'project_name', 'product_type'],
                    'label': 'product_records',
                }
            ],
            'login_permission': [
                {
                    'path': '/volume2/MES/QRMES/web_users.db',
                    'table': 'users',
                    'lookup_column': 'username',
                    'extract_pattern': '([A-Za-z][A-Za-z0-9_.-]{2,})',
                    'select_columns': ['username', 'role', 'is_active'],
                    'label': 'web_users',
                }
            ],
            'photo_upload': [
                {
                    'path': '/volume2/MES/QRMES/unified.db',
                    'table': 'process_photos',
                    'lookup_column': 'product_serial',
                    'extract_pattern': '([A-Z]{2}\d{4,}|SN\d{4,})',
                    'select_columns': ['product_serial', 'project_name', 'process_name', 'file_path'],
                    'label': 'process_photos',
                }
            ],
        }

    def infer_targets(self, text: str) -> List[str]:
        lowered = (text or "").lower()
        targets = []
        if any(keyword in lowered for keyword in ("apk", "android", "移动端", "客户端")):
            targets.append("qrmes-android")
        if any(keyword in lowered for keyword in ("web", "发布", "后端", "数据库", "登录", "权限", "照片", "配置", "h2")):
            targets.append("qrmes-web-core")
        if any(keyword in lowered for keyword in ("finance", "金蝶", "报价", "财务")):
            targets.append("qrmes-finance-service")
        if any(keyword in lowered for keyword in ("motor", "质检", "相机", "edge", "桥接")):
            targets.append("qrmes-motor-qc")
        if not targets:
            targets.append("qrmes-web-core")
        ordered = []
        for key in targets:
            if key not in ordered:
                ordered.append(key)
        return ordered

    def matched_domains(self, text: str) -> List[str]:
        lowered = (text or "").lower()
        matched = []
        for domain, keywords in self.domain_keywords.items():
            if any(keyword in lowered for keyword in keywords):
                matched.append(domain)
        return matched

    def get_target(self, key: str) -> RepositoryTarget:
        return self.targets[key]
