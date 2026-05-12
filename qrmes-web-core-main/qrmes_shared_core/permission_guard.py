"""
集中式权限守卫（供独立蓝图复用，避免 import mesapp.py 造成循环依赖/副作用）。

约定：
- Web-only：只读取 Flask session（不处理 Basic Auth）。
- 测试可通过 app.config['WEB_USERS_DB_PATH'] 注入隔离数据库路径。
"""

from __future__ import annotations

from functools import wraps
from pathlib import Path
from typing import Optional, Tuple, Dict

from flask import current_app, flash, jsonify, redirect, request, session, url_for

from .config import config
from .data_dir_utils import resolve_data_dir
from .permission_service import Permission, PermissionService
from .synology_auth_client import SynologyAuthService
from .user_management_service import LocalUser, UserManagementService


_CACHED: Dict[str, Tuple[UserManagementService, PermissionService]] = {}


def _is_dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".perm_guard_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _get_users_db_path() -> Path:
    injected = None
    try:
        injected = current_app.config.get("WEB_USERS_DB_PATH")
    except Exception:
        injected = None

    if injected:
        return Path(injected)

    try:
        repo_root = Path(__file__).resolve().parent.parent
        data_dir = resolve_data_dir(
            nas_local_base_path=getattr(config, "nas_local_base_path", None),
            repo_root=repo_root,
            create=False,
        )
    except Exception:
        data_dir = Path(config.nas_local_base_path)

    if not _is_dir_writable(data_dir):
        fallback = Path(__file__).resolve().parent.parent / "app" / "files"
        fallback.mkdir(parents=True, exist_ok=True)
        data_dir = fallback

    return data_dir / "web_users.db"


def _get_services() -> Tuple[UserManagementService, PermissionService]:
    db_path = _get_users_db_path()
    key = str(db_path)
    cached = _CACHED.get(key)
    if cached:
        return cached

    synology_auth = SynologyAuthService(
        base_url=config.synology_api_url,
        verify_ssl=config.synology_api_verify_ssl,
    )
    user_service = UserManagementService(db_path, synology_auth)
    perm_service = PermissionService(user_service)
    _CACHED[key] = (user_service, perm_service)
    return user_service, perm_service


def _is_api_request() -> bool:
    try:
        return request.path.startswith("/api/") or request.path.startswith("/motor-qc/api/")
    except Exception:
        return False


def get_current_local_user() -> Optional[LocalUser]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    user_service, _ = _get_services()
    return user_service.get_user_by_id(user_id)


def require_permission_value(permission_value: str):
    """
    权限验证装饰器（入参为 Permission.value 字符串，例如 'web:run_qc'）。
    - 未登录：API 返回 401；页面重定向 /login
    - 无权限：API 返回 403；页面重定向 / 并 flash 提示
    """

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                if _is_api_request():
                    return jsonify({"success": False, "message": "请先登录"}), 401
                flash("请先登录", "warning")
                return redirect(url_for("login"))

            user_service, perm_service = _get_services()
            user = user_service.get_user_by_id(user_id)
            if not user:
                if _is_api_request():
                    return jsonify({"success": False, "message": "用户未登录"}), 401
                flash("用户未登录", "warning")
                return redirect(url_for("login"))

            perm_enum = None
            for p in Permission:
                if p.value == permission_value:
                    perm_enum = p
                    break
            if perm_enum is None:
                # 开发/配置错误：权限未注册
                return jsonify({"success": False, "message": "权限配置错误"}), 500

            if not perm_service.has_permission(user, perm_enum):
                if _is_api_request():
                    return jsonify({"success": False, "message": "权限不足"}), 403
                flash("权限不足", "error")
                return redirect(url_for("index"))

            return f(*args, **kwargs)

        return wrapper

    return decorator
