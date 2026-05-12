from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from ..models import PrefixMatch
from .mes_query_service import detect_serial


@dataclass(slots=True)
class PermissionQueryService:
    prefix_service: object
    user_resolver: object
    project_config_db_path: str
    web_users_db_path: str
    image_downloader: object | None = None
    vision_service: object | None = None

    def is_permission_question(self, text: str) -> bool:
        content = str(text or "").strip()
        if not content:
            return False
        return "权限" in content or ("工序" in content and any(word in content for word in ("没有", "为何", "为啥", "不能")))

    def extract_serial(self, text: str) -> str | None:
        return detect_serial(text or "")

    def reply_for_serial(self, serial: str, sender_staff_id: str, sender_nick: str) -> str:
        final_serial = str(serial or "").strip()
        if not final_serial:
            return "请先提供要检查的序列号，或者直接发二维码/标签图片给我。"

        resolve_result = self.user_resolver.resolve_mes_username(sender_staff_id, sender_nick)
        status = str(resolve_result.get("status") or "").strip()
        if status != "matched":
            return self._build_user_resolution_reply(resolve_result)

        mes_username = str(resolve_result.get("username") or "").strip()
        source = str(resolve_result.get("source") or "").strip()
        user_row = self._get_active_user(mes_username)
        if not user_row:
            return f"已解析到候选 MES 用户：{mes_username}，但该用户未启用或不存在。"

        group_names = self._get_user_group_names(str(user_row["id"] or ""))
        query_serial, prefix_matches = self.prefix_service.resolve_for_query(final_serial)
        if not prefix_matches:
            return (
                f"已匹配 MES 用户：{mes_username}（来源：{self._source_label(source)}）\n"
                f"用户群组：{self._join_labels(group_names, '未配置群组')}\n"
                f"序列号：{query_serial}\n"
                "未命中产品二维码前缀规则，暂时无法继续判断工序权限。"
            )

        lines = [
            f"已匹配 MES 用户：{mes_username}（来源：{self._source_label(source)}）",
            f"用户群组：{self._join_labels(group_names, '未配置群组')}",
        ]
        for index, match in enumerate(prefix_matches, start=1):
            lines.extend(self._build_permission_lines(index, query_serial, match, group_names))
        return "\n".join(lines)

    def reply_for_images(
        self,
        download_codes: tuple[str, ...],
        user_text: str,
        sender_staff_id: str,
        sender_nick: str,
    ) -> str:
        if not self.image_downloader or not self.vision_service:
            return "当前机器人还没有启用图片权限检查能力，请先直接发送序列号。"

        images = self.image_downloader.download_images(download_codes)
        if not images:
            return "图片下载失败，暂时无法做工序权限判断。请稍后重试，或直接发送序列号。"

        recognition = self.vision_service.recognize(images, user_text=user_text)
        serials = tuple(dict.fromkeys(recognition.serial_numbers))
        if not serials:
            serial_from_text = self.extract_serial(user_text)
            serials = (serial_from_text,) if serial_from_text else ()
        if not serials:
            return "我已经收到二维码/标签图片，但还没识别到可用于权限判断的完整序列号。请补一张更清晰的图片，或直接把序列号发给我。"

        replies = []
        for index, item in enumerate(serials, start=1):
            block = self.reply_for_serial(item, sender_staff_id, sender_nick)
            replies.append(f"{index}. {block}" if len(serials) > 1 else block)
        return "\n\n".join(replies)

    def _build_user_resolution_reply(self, result: dict) -> str:
        status = str(result.get("status") or "").strip()
        name = str(result.get("name") or "").strip() or "当前提问人"
        candidates = [str(item or "").strip() for item in (result.get("candidates") or []) if str(item or "").strip()]

        if status == "multiple_exact":
            return (
                f"找到多个与钉钉真实姓名“{name}”完全同名的 MES 账号，请确认你要用哪个账号继续判断工序权限：\n"
                + "\n".join(f"- {item}" for item in candidates)
            )
        if status == "fuzzy_candidates":
            return (
                f"没有找到与钉钉真实姓名“{name}”完全一致的 MES 账号，但找到了这些相近账号，请确认你要用哪个账号继续判断工序权限：\n"
                + "\n".join(f"- {item}" for item in candidates)
            )
        return "未匹配到 MES 用户。当前规则会优先按钉钉真实姓名精确匹配；同名时会提示你确认账号；精确匹配不到时再给出模糊候选。"

    def _build_permission_lines(
        self,
        index: int,
        serial: str,
        match: PrefixMatch,
        group_names: list[str],
    ) -> list[str]:
        steps = self._get_process_steps(match.project_name, match.product_type)
        if not steps:
            return [
                f"{index}. 序列号：{serial}",
                f"   命中产品：{match.project_name} / {match.product_type}",
                "   未找到该产品的工序配置，暂时无法判断工序权限。",
            ]

        normalized_groups = {self._norm(item) for item in group_names if self._norm(item)}
        allowed_steps: list[str] = []
        blocked_steps: list[tuple[str, list[str]]] = []

        for step in steps:
            departments = [str(item or "").strip() for item in (step.get("departments") or []) if str(item or "").strip()]
            if not departments:
                allowed_steps.append(step["name"])
                continue
            normalized_departments = {self._norm(item) for item in departments if self._norm(item)}
            if normalized_groups & normalized_departments:
                allowed_steps.append(step["name"])
            else:
                blocked_steps.append((step["name"], departments))

        lines = [
            f"{index}. 序列号：{serial}",
            f"   命中产品：{match.project_name} / {match.product_type}",
            f"   工序总数：{len(steps)}",
            f"   可执行工序：{len(allowed_steps)}",
            f"   缺少工序权限：{len(blocked_steps)}",
        ]
        if allowed_steps:
            allowed_text = "、".join(allowed_steps[:8])
            if len(allowed_steps) > 8:
                allowed_text += "……"
            lines.append(f"   可执行工序明细：{allowed_text}")
        if blocked_steps:
            blocked_labels = [
                f"{name}（责任部门：{'、'.join(departments)}）"
                for name, departments in blocked_steps[:8]
            ]
            blocked_text = "；".join(blocked_labels)
            if len(blocked_steps) > 8:
                blocked_text += "……"
            lines.append(f"   缺少权限工序：{blocked_text}")
        return lines

    def _get_active_user(self, username: str):
        try:
            conn = sqlite3.connect(self.web_users_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT id, synology_username
                FROM users
                WHERE lower(synology_username) = lower(?)
                  AND coalesce(is_active, 1) = 1
                LIMIT 1
                """,
                (username,),
            )
            row = cursor.fetchone()
            conn.close()
            return row
        except Exception:
            return None

    def _get_user_group_names(self, user_id: str) -> list[str]:
        if not user_id:
            return []
        try:
            conn = sqlite3.connect(self.web_users_db_path)
            cursor = conn.execute(
                """
                SELECT g.name
                FROM user_groups ug
                JOIN groups g ON g.id = ug.group_id
                WHERE ug.user_id = ?
                ORDER BY g.name
                """,
                (user_id,),
            )
            rows = [str(row[0] or "").strip() for row in cursor.fetchall()]
            conn.close()
        except Exception:
            return []
        return [row for row in rows if row]

    def _get_process_steps(self, project_name: str, product_type: str) -> list[dict]:
        try:
            conn = sqlite3.connect(self.project_config_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT ps.name, ps.step_order, ps.responsible_departments_json
                FROM process_steps ps
                JOIN product_types pt ON pt.id = ps.product_type_id
                JOIN projects p ON p.id = pt.project_id
                WHERE p.project_name = ?
                  AND pt.type_name = ?
                ORDER BY ps.step_order, ps.id
                """,
                (project_name, product_type),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return []

        result = []
        for row in rows:
            departments = []
            try:
                raw = json.loads(row["responsible_departments_json"] or "[]")
                if isinstance(raw, list):
                    departments = [str(item or "").strip() for item in raw if str(item or "").strip()]
            except Exception:
                departments = []
            result.append(
                {
                    "name": str(row["name"] or "").strip(),
                    "order": int(row["step_order"] or 0),
                    "departments": departments,
                }
            )
        return result

    @staticmethod
    def _join_labels(values: list[str], empty_text: str) -> str:
        return "、".join(values) if values else empty_text

    @staticmethod
    def _source_label(source: str) -> str:
        if source == "real_name_alias":
            return "钉钉真实姓名映射"
        if source == "real_name_exact":
            return "钉钉真实姓名"
        if source == "sender_nick":
            return "钉钉显示名"
        return "未知来源"

    @staticmethod
    def _norm(value: str) -> str:
        return str(value or "").strip().lower()
