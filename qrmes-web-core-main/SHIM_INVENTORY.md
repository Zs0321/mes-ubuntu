# Web Core shim inventory

保留这些 shim 以兼容剩余历史导入与测试路径：

- `app_web/config.py`
- `app_web/data_dir_utils.py`
- `app_web/auth.py`
- `app_web/permission_guard.py`
- `app_web/permission_service.py`
- `app_web/synology_auth_client.py`
- `app_web/user_management_service.py`
- `app_web/webdav_client.py`
- `app_web/webdav_client_v2.py`
- `app_web/smb_client.py`
- `app_web/project_name_utils.py`
- `app_web/project_config_manager.py`
- `app_web/config_history_manager.py`
- `app_web/test_report_service.py`

当前轮次未删除 shim，避免破坏尚未迁移完成的引用。

本轮判断：由于 tests 目录仍有少量旧导入，shim 继续保留，暂不删除。
