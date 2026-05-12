"""
配置管理模块
"""

import base64
import json
import os
from pathlib import Path
from typing import Optional

from .data_dir_utils import DEFAULT_NAS_DATA_DIR

# 配置文件路径
CONFIG_FILE = Path(__file__).parent / 'webdav_config.json'
SOURCE_CONFIG_FILE = Path('/volume2/mes_ubuntu/app_web/webdav_config.json')
RUNTIME_CONFIG_CANDIDATES = (
    Path('/volume2/qrmes-v3.0/qrmes-web-core/app_web/webdav_config.json'),
    Path('/volume2/qrmes/app_web/webdav_config.json'),
)


_ENV_BOOL_TRUE = {'1', 'true', 'yes', 'y', 'on'}
_ENV_BOOL_FALSE = {'0', 'false', 'no', 'n', 'off'}


def _env_text(*keys: str) -> Optional[str]:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != '':
            return str(value).strip()
    return None


def _env_bool(*keys: str) -> Optional[bool]:
    value = _env_text(*keys)
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in _ENV_BOOL_TRUE:
        return True
    if lowered in _ENV_BOOL_FALSE:
        return False
    return None


def _env_int(*keys: str) -> Optional[int]:
    value = _env_text(*keys)
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _apply_env_overrides(config_data: dict) -> dict:
    overrides = {
        'kingdee_base_url': _env_text('KINGDEE_BASE_URL'),
        'kingdee_acct_id': _env_text('KINGDEE_ACCT_ID', 'KINGDEE_DB_ID'),
        'kingdee_username': _env_text('KINGDEE_USERNAME'),
        'kingdee_app_id': _env_text('KINGDEE_APP_ID'),
        'kingdee_app_secret': _env_text('KINGDEE_APP_SECRET'),
        'motor_qc_vision_provider': _env_text('MOTOR_QC_VISION_PROVIDER'),
        'claude_api_key': _env_text('CLAUDE_API_KEY'),
        'claude_model': _env_text('CLAUDE_MODEL'),
        'qwen_api_key': _env_text('QWEN_API_KEY'),
        'qwen_model': _env_text('QWEN_MODEL'),
        'qwen_base_url': _env_text('QWEN_BASE_URL'),
        'dashscope_api_key': _env_text('DASHSCOPE_API_KEY'),
        'pricing_ai_api_key': _env_text('PRICING_AI_API_KEY'),
        'pricing_ai_model': _env_text('PRICING_AI_MODEL'),
        'pricing_ai_base_url': _env_text('PRICING_AI_BASE_URL'),
        'pricing_qwen_model': _env_text('PRICING_QWEN_MODEL'),
    }

    bool_overrides = {
        'kingdee_workhour_enabled': _env_bool('KINGDEE_WORKHOUR_ENABLED'),
        'kingdee_verify_ssl': _env_bool('KINGDEE_VERIFY_SSL'),
    }

    int_overrides = {
        'kingdee_lcid': _env_int('KINGDEE_LCID'),
        'kingdee_timeout_secs': _env_int('KINGDEE_TIMEOUT_SECS', 'KINGDEE_TIMEOUT_SECONDS'),
        'pricing_qwen_timeout': _env_int('PRICING_QWEN_TIMEOUT'),
        'pricing_qwen_timeout_retry': _env_int('PRICING_QWEN_TIMEOUT_RETRY'),
        'pricing_ai_max_workers': _env_int('PRICING_AI_MAX_WORKERS'),
    }

    merged = dict(config_data or {})
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    for key, value in bool_overrides.items():
        if value is not None:
            merged[key] = value
    for key, value in int_overrides.items():
        if value is not None:
            merged[key] = value
    return merged

# 默认配置
DEFAULT_CONFIG = {
    "protocol": "smb",  # smb 或 webdav
    "smb_server": "172.16.30.10",
    "smb_share_name": "mes",
    "smb_base_path": "QRMES",
    "webdav_url": "https://panovation.i234.me:5006",
    "synology_api_url": "https://172.16.30.10:5001",
    "synology_api_verify_ssl": True,
    # 用户同步自动任务配置
    "user_sync_auto_enabled": False,
    "user_sync_auto_time": "12:30",
    "user_sync_auto_sync_groups": True,
    "user_sync_admin_username": "",
    "user_sync_admin_password": "",
    "user_sync_auto_last_run_date": "",
    "user_sync_auto_last_run_at": "",
    "user_sync_auto_last_success": None,
    "user_sync_auto_last_error": "",
    "webdav_username": "",
    "webdav_password": "",
    "webdav_base_path": "/mes/QRMES",
    "use_webdav": False,  # 是否使用网络存储（False 则使用本地文件）
    # 群晖本机挂载路径（指向与 SMB 共享同一位置），用于直接本地读写
    "nas_local_base_path": DEFAULT_NAS_DATA_DIR,
    # 金蝶工时只读查询配置
    "kingdee_workhour_enabled": False,
    "kingdee_base_url": "",
    "kingdee_acct_id": "",
    "kingdee_username": "",
    "kingdee_app_id": "",
    "kingdee_app_secret": "",
    "kingdee_lcid": 2052,
    "kingdee_verify_ssl": True,
    "kingdee_timeout_secs": 15,
    "kingdee_workhour_form_id": "SFC_OperationPlanning",
    "kingdee_workhour_field_keys": [
        "FBillNo",
        "FMONumber",
        "FOperNumber",
        "FOperDescription",
        "FProductId.FNumber",
        "FProductId.FSpecification",
        "FQualifiedQty",
    ],
    "kingdee_workhour_filter_template": "FMONumber='{serial_escaped}'",
    "kingdee_workhour_order_string": "FID DESC",
    "kingdee_workhour_top_rows": 0,
    "kingdee_workhour_limit": 200,
    "kingdee_workhour_start_row": 0,
    "kingdee_workhour_product_code_field": "FProductId.FNumber",
    "kingdee_workhour_spec_model_field": "FProductId.FSpecification",
    "kingdee_workhour_work_order_field": "FMONumber",
    "kingdee_workhour_process_code_field": "FOperNumber",
    "kingdee_workhour_process_name_field": "FOperDescription",
    "kingdee_workhour_process_desc_field": "FOperDescription",
    "kingdee_workhour_completed_qty_field": "FQualifiedQty",
    "kingdee_workhour_qty_field": "FQualifiedQty",
    "kingdee_workhour_report_form_id": "SFC_OperationReport",
    "kingdee_workhour_report_field_keys": [
        "FBillNo",
        "FCreateDate",
        "FDocumentStatus",
        "FMONumber",
        "FOperNumber",
        "FOperDescription",
        "FMaterialId.FNumber",
        "FMaterialId.FSpecification",
        "FUnitID.FName",
        "FReworkQty",
        "FFinishQty",
    ],
    "kingdee_workhour_report_filter_template": "FMONumber='{value_escaped}'",
    "kingdee_workhour_report_order_string": "FID DESC",
    "kingdee_workhour_report_top_rows": 0,
    "kingdee_workhour_report_limit": 500,
    "kingdee_workhour_report_start_row": 0,
    "kingdee_workhour_report_product_code_field": "FMaterialId.FNumber",
    "kingdee_workhour_report_spec_model_field": "FMaterialId.FSpecification",
    "kingdee_workhour_report_work_order_field": "FMONumber",
    "kingdee_workhour_report_process_code_field": "FOperNumber",
    "kingdee_workhour_report_process_name_field": "FOperDescription",
    "kingdee_workhour_report_process_desc_field": "FOperDescription",
    "kingdee_workhour_report_completed_qty_field": "FFinishQty",
    "kingdee_workhour_report_bill_no_field": "FBillNo",
    "kingdee_workhour_report_created_at_field": "FCreateDate",
    "kingdee_workhour_report_status_field": "FDocumentStatus",
    "kingdee_workhour_report_unit_field": "FUnitID.FName",
    "kingdee_workhour_report_rework_qty_field": "FReworkQty",
    "kingdee_workhour_report_actual_hours_field": "",
    "kingdee_production_form_id": "PRD_MO",
    "kingdee_production_field_keys": [
        "FBillNo",
        "FMaterialId.FNumber",
        "FSerialNo",
        "FRptFinishQty",
    ],
    "kingdee_production_filter_template": "FSerialNo='{serial_escaped}'",
    "kingdee_production_order_string": "",
    "kingdee_production_top_rows": 0,
    "kingdee_production_limit": 50,
    "kingdee_production_start_row": 0,
    "kingdee_production_work_order_field": "FBillNo",
    "kingdee_production_product_code_field": "FMaterialId.FNumber",
    "kingdee_production_serial_field": "FSerialNo",
    "kingdee_production_completed_qty_field": "",
    # AI / 模型运行配置
    "motor_qc_vision_provider": "claude",
    "claude_api_key": "",
    "claude_model": "claude-sonnet-4-5-20250929",
    "qwen_api_key": "",
    "qwen_model": "qwen3-vl-flash",
    "qwen_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "dashscope_api_key": "",
    "pricing_ai_api_key": "",
    "pricing_ai_model": "",
    "pricing_ai_base_url": "",
    "pricing_qwen_model": "qwen3.5-plus",
    "pricing_qwen_timeout": 90,
    "pricing_qwen_timeout_retry": 1,
    "pricing_ai_max_workers": 2,
}


class Config:
    """配置管理器"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """加载配置"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self._config = _apply_env_overrides(json.load(f))
                print(f"[Config] Loaded configuration from {CONFIG_FILE}")
            except Exception as e:
                print(f"[Config] Error loading config: {e}, using defaults")
                self._config = _apply_env_overrides(DEFAULT_CONFIG.copy())
        else:
            print(f"[Config] No config file found, using defaults")
            self._config = _apply_env_overrides(DEFAULT_CONFIG.copy())
            self._save_config()
    
    def _save_config(self):
        """保存配置"""
        target_candidates = [CONFIG_FILE, SOURCE_CONFIG_FILE]
        runtime_target = None
        for candidate in RUNTIME_CONFIG_CANDIDATES:
            if candidate == CONFIG_FILE:
                runtime_target = candidate
                break
            if candidate.parent.exists():
                runtime_target = candidate
                break
        if runtime_target is not None:
            target_candidates.append(runtime_target)

        target_files = []
        for path in target_candidates:
            try:
                resolved = path.resolve()
            except Exception:
                resolved = path
            if any(existing == resolved for existing in target_files):
                continue
            target_files.append(resolved)

        errors = []
        for path in target_files:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, ensure_ascii=False, indent=2)
                print(f"[Config] Saved configuration to {path}")
            except Exception as e:
                errors.append(f"{path}: {e}")

        if errors:
            print(f"[Config] Error saving config: {'; '.join(errors)}")
            return False
        return True
    
    def get(self, key: str, default=None):
        """获取配置项"""
        return self._config.get(key, default)
    
    def set(self, key: str, value):
        """设置配置项"""
        self._config[key] = value
        return self._save_config()
    
    def get_all(self):
        """获取所有配置"""
        return self._config.copy()
    
    def update(self, updates: dict):
        """批量更新配置"""
        self._config.update(updates)
        return self._save_config()
    
    @property
    def protocol(self) -> str:
        return self.get('protocol', DEFAULT_CONFIG['protocol'])
    
    @property
    def smb_server(self) -> str:
        return self.get('smb_server', DEFAULT_CONFIG['smb_server'])
    
    @property
    def smb_share_name(self) -> str:
        return self.get('smb_share_name', DEFAULT_CONFIG['smb_share_name'])
    
    @property
    def smb_base_path(self) -> str:
        return self.get('smb_base_path', DEFAULT_CONFIG['smb_base_path'])
    
    @property
    def webdav_url(self) -> str:
        return self.get('webdav_url', DEFAULT_CONFIG['webdav_url'])
    
    @property
    def synology_api_url(self) -> str:
        return self.get('synology_api_url', DEFAULT_CONFIG['synology_api_url'])

    @property
    def synology_api_verify_ssl(self) -> bool:
        return self.get('synology_api_verify_ssl', DEFAULT_CONFIG['synology_api_verify_ssl'])

    @property
    def webdav_username(self) -> str:
        return self.get('webdav_username', DEFAULT_CONFIG['webdav_username'])
    
    @property
    def webdav_password(self) -> str:
        password = self.get('webdav_password', DEFAULT_CONFIG['webdav_password'])
        # 检查是否为加密密码
        if self.get('password_encrypted', False) and password:
            try:
                # 使用base64解码
                decoded_password = base64.b64decode(password).decode('utf-8')
                return decoded_password
            except Exception as e:
                print(f"[Config] 密码解码失败: {e}")
                return password
        return password
    
    @property
    def webdav_base_path(self) -> str:
        return self.get('webdav_base_path', DEFAULT_CONFIG['webdav_base_path'])
    
    @property
    def nas_local_base_path(self) -> str:
        """群晖本机数据根路径（如 /volume2/mes/QRMES）"""
        return self.get('nas_local_base_path', DEFAULT_CONFIG.get('nas_local_base_path', DEFAULT_NAS_DATA_DIR))
    
    @property
    def use_webdav(self) -> bool:
        return self.get('use_webdav', DEFAULT_CONFIG['use_webdav'])


# 全局配置实例
config = Config()

# Motor QC Vision API 配置
MOTOR_QC_CONFIG = {
    "vision_provider": str(os.getenv("MOTOR_QC_VISION_PROVIDER") or config.get("motor_qc_vision_provider", "claude") or "claude").strip(),
    "claude": {
        "api_key": str(os.getenv("CLAUDE_API_KEY") or config.get("claude_api_key", "") or "").strip(),
        "model": str(os.getenv("CLAUDE_MODEL") or config.get("claude_model", "claude-sonnet-4-5-20250929") or "claude-sonnet-4-5-20250929").strip(),
    },
    "qwen": {
        "api_key": str(os.getenv("QWEN_API_KEY") or config.get("qwen_api_key", "") or config.get("dashscope_api_key", "") or "").strip(),
        "model": str(os.getenv("QWEN_MODEL") or config.get("qwen_model", "qwen3-vl-flash") or "qwen3-vl-flash").strip(),
    }
}
