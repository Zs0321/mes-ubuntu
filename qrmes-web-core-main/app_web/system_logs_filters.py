"""
日志采集范围规则（纯函数，便于测试）
"""

from __future__ import annotations


def should_log_access_path(path: str) -> bool:
    path = path or ""

    # 静态资源不记
    if path.startswith("/static/"):
        return False

    # 避免日志接口递归
    if path == "/logs" or path.startswith("/api/logs"):
        return False

    # 仅记录后台管理访问
    if path.startswith("/admin/") or path.startswith("/admin/api/"):
        return True

    return False

