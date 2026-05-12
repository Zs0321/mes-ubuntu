#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from tool_expiry_dingtalk import DingtalkToolExpiryNotifier
from tool_expiry_service import ToolExpiryError, ToolExpiryService

logger = logging.getLogger(__name__)

tool_expiry_bp = Blueprint("tool_expiry", __name__, url_prefix="/api/tool-expiry")


def _db_path() -> Path:
    configured = current_app.config.get("TOOL_EXPIRY_DB_PATH")
    if configured:
        return Path(str(configured))
    data_dir = current_app.config.get("DATA_DIR")
    if data_dir:
        return Path(str(data_dir)) / "tool_expiry" / "tool_expiry.db"
    database_path = current_app.config.get("DATABASE_PATH")
    if database_path:
        return Path(str(database_path)).with_name("tool_expiry.db")
    return Path("data") / "tool_expiry.db"


def _notifier() -> Any:
    configured = current_app.config.get("TOOL_EXPIRY_NOTIFIER")
    if configured is not None:
        return configured
    return DingtalkToolExpiryNotifier.from_app_config(current_app.config)


def _today_provider():
    return current_app.config.get("TOOL_EXPIRY_TODAY_PROVIDER")


@tool_expiry_bp.route("/scan", methods=["POST"])
def scan_tool_expiry():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"success": False, "message": "请求体格式错误"}), 400

    raw_code = data.get("rawCode") or data.get("raw_code") or ""
    if not str(raw_code or "").strip():
        return jsonify({"success": False, "message": "rawCode 不能为空"}), 400

    service = ToolExpiryService(
        _db_path(),
        notifier=_notifier(),
        today_provider=_today_provider(),
        logger_=logger,
    )
    try:
        result = service.handle_scan(
            raw_code=str(raw_code),
            tool_name=str(data.get("toolName") or data.get("tool_name") or ""),
            operator=str(data.get("operator") or data.get("operatorName") or ""),
        )
    except ToolExpiryError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("工具二维码扫码接口处理失败: %s", exc)
        return jsonify({"success": False, "message": "工具二维码扫码处理失败: %s" % exc}), 500

    return jsonify(result)


@tool_expiry_bp.route("/health", methods=["GET"])
def tool_expiry_health():
    return jsonify({"success": True, "message": "tool expiry api ok"})
