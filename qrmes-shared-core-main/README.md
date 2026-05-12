# qrmes-shared-core

从 `mes_ubuntu/app_web` 抽出的共享 Python 基础层。

当前已收纳模块：
- `data_dir_utils.py`
- `config.py`
- `auth.py`
- `permission_guard.py`
- `permission_service.py`
- `synology_auth_client.py`
- `user_management_service.py`
- `webdav_client.py`
- `webdav_client_v2.py`
- `smb_client.py`
- `project_name_utils.py`
- `project_config_manager.py`
- `config_history_manager.py`
- `test_report_service.py`

用途：
- 给 `qrmes-web-core`
- `qrmes-motor-qc`
- `qrmes-finance-service`

提供统一共享模块，降低后续继续拆仓时的重复维护成本。
