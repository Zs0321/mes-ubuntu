import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dingtalk_mes_bot.models import PrefixMatch
from dingtalk_mes_bot.services.dingtalk_mes_user_resolver import DingTalkMesUserResolver
from dingtalk_mes_bot.services.permission_query_service import PermissionQueryService


class FakePrefixService:
    def __init__(self, corrected_serial="GenesisLiGFLF10C2026041000461", matches=()):
        self.corrected_serial = corrected_serial
        self.matches = matches

    def resolve_for_query(self, serial: str):
        return self.corrected_serial, self.matches


class FakeUserResolver:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def resolve_mes_username(self, sender_staff_id: str, sender_nick: str):
        self.calls.append((sender_staff_id, sender_nick))
        return self.result


class PermissionQueryServiceTests(unittest.TestCase):
    def _build_alias_file(self, path: Path, payload: dict):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_project_db(self, path: Path):
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                project_name TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE product_types (
                id INTEGER PRIMARY KEY,
                project_id INTEGER,
                type_name TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE process_steps (
                id INTEGER PRIMARY KEY,
                product_type_id INTEGER,
                process_uid TEXT,
                name TEXT,
                step_order INTEGER,
                responsible_departments_json TEXT
            )
            """
        )
        conn.execute("INSERT INTO projects (id, project_name) VALUES (1, '柳工3.5T双15叉车(二合一控制器)')")
        conn.execute("INSERT INTO product_types (id, project_id, type_name) VALUES (10, 1, '电控二合一')")
        conn.execute(
            """
            INSERT INTO process_steps (product_type_id, process_uid, name, step_order, responsible_departments_json)
            VALUES
            (10, 'p1', '压装', 10, '[]'),
            (10, 'p2', '接线', 20, '["智能制造部-生产"]'),
            (10, 'p3', '复检', 30, '["质量部"]')
            """
        )
        conn.commit()
        conn.close()

    def _build_user_db(self, path: Path):
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                synology_username TEXT,
                display_name TEXT,
                is_active INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE groups (
                id TEXT PRIMARY KEY,
                name TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE user_groups (
                user_id TEXT,
                group_id TEXT
            )
            """
        )
        conn.execute("INSERT INTO users (id, synology_username, display_name, is_active) VALUES ('u1', 'yan.ai', '艾岩', 1)")
        conn.execute("INSERT INTO groups (id, name) VALUES ('g1', '智能制造部-生产')")
        conn.execute("INSERT INTO user_groups (user_id, group_id) VALUES ('u1', 'g1')")
        conn.commit()
        conn.close()

    def test_query_serial_permission_reports_missing_process_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_db = Path(tmpdir) / "project_configs.db"
            user_db = Path(tmpdir) / "web_users.db"
            self._build_project_db(project_db)
            self._build_user_db(user_db)

            service = PermissionQueryService(
                prefix_service=FakePrefixService(
                    matches=(
                        PrefixMatch(
                            project_name="柳工3.5T双15叉车(二合一控制器)",
                            product_type="电控二合一",
                            prefix="Genesis-LiGFL-F10-C",
                            length=16,
                        ),
                    )
                ),
                user_resolver=FakeUserResolver({"status": "matched", "username": "yan.ai", "source": "real_name_exact"}),
                project_config_db_path=str(project_db),
                web_users_db_path=str(user_db),
            )

            reply = service.reply_for_serial(
                serial="Genesis-LiGFL10C2026041000461",
                sender_staff_id="staff-001",
                sender_nick="艾岩",
            )

        self.assertIn("已匹配 MES 用户：yan.ai", reply)
        self.assertIn("工序总数：3", reply)
        self.assertIn("可执行工序：2", reply)
        self.assertIn("缺少工序权限：1", reply)
        self.assertIn("复检", reply)

    def test_query_serial_permission_reports_missing_mes_user(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_db = Path(tmpdir) / "project_configs.db"
            user_db = Path(tmpdir) / "web_users.db"
            self._build_project_db(project_db)
            self._build_user_db(user_db)

            service = PermissionQueryService(
                prefix_service=FakePrefixService(
                    matches=(
                        PrefixMatch(
                            project_name="柳工3.5T双15叉车(二合一控制器)",
                            product_type="电控二合一",
                            prefix="Genesis-LiGFL-F10-C",
                            length=16,
                        ),
                    )
                ),
                user_resolver=FakeUserResolver({"status": "not_found", "name": "艾岩"}),
                project_config_db_path=str(project_db),
                web_users_db_path=str(user_db),
            )

            reply = service.reply_for_serial(
                serial="Genesis-LiGFL10C2026041000461",
                sender_staff_id="staff-002",
                sender_nick="艾岩",
            )

        self.assertIn("未匹配到 MES 用户", reply)

    def test_dingtalk_user_resolver_initializes_slot_backed_cache(self):
        resolver = DingTalkMesUserResolver(
            app_key="client-id",
            app_secret="client-secret",
            web_users_db_path="/tmp/web_users.db",
        )
        self.assertEqual("", resolver._access_token)
        self.assertEqual(0.0, resolver._access_token_expires_at)

    def test_dingtalk_user_resolver_matches_real_name_exactly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_db = Path(tmpdir) / "web_users.db"
            self._build_user_db(user_db)
            resolver = DingTalkMesUserResolver(
                app_key="client-id",
                app_secret="client-secret",
                web_users_db_path=str(user_db),
            )
            with patch.object(DingTalkMesUserResolver, "_fetch_dingtalk_profile", return_value={"name": "艾岩"}):
                result = resolver.resolve_mes_username("staff-001", "yan.ai")

        self.assertEqual("matched", result["status"])
        self.assertEqual("yan.ai", result["username"])
        self.assertEqual("real_name_exact", result["source"])

    def test_dingtalk_user_resolver_reports_multiple_exact_name_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_db = Path(tmpdir) / "web_users.db"
            self._build_user_db(user_db)
            conn = sqlite3.connect(user_db)
            conn.execute("INSERT INTO users (id, synology_username, display_name, is_active) VALUES ('u2', 'yan.ai.2', '艾岩', 1)")
            conn.commit()
            conn.close()

            resolver = DingTalkMesUserResolver(
                app_key="client-id",
                app_secret="client-secret",
                web_users_db_path=str(user_db),
            )
            with patch.object(DingTalkMesUserResolver, "_fetch_dingtalk_profile", return_value={"name": "艾岩"}):
                result = resolver.resolve_mes_username("staff-001", "yan.ai")

        self.assertEqual("multiple_exact", result["status"])
        self.assertIn("yan.ai", result["candidates"])
        self.assertIn("yan.ai.2", result["candidates"])

    def test_dingtalk_user_resolver_reports_fuzzy_candidates_when_no_exact_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_db = Path(tmpdir) / "web_users.db"
            self._build_user_db(user_db)
            conn = sqlite3.connect(user_db)
            conn.execute("UPDATE users SET display_name = '艾岩-产线' WHERE id = 'u1'")
            conn.commit()
            conn.close()

            resolver = DingTalkMesUserResolver(
                app_key="client-id",
                app_secret="client-secret",
                web_users_db_path=str(user_db),
            )
            with patch.object(DingTalkMesUserResolver, "_fetch_dingtalk_profile", return_value={"name": "艾岩"}):
                result = resolver.resolve_mes_username("staff-001", "yan.ai")

        self.assertEqual("fuzzy_candidates", result["status"])
        self.assertIn("yan.ai", result["candidates"])

    def test_dingtalk_user_resolver_matches_real_name_alias_mapping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_db = Path(tmpdir) / "web_users.db"
            alias_file = Path(tmpdir) / "mes_user_aliases.json"
            self._build_user_db(user_db)
            self._build_alias_file(alias_file, {"艾岩": "yan.ai"})
            conn = sqlite3.connect(user_db)
            conn.execute("UPDATE users SET display_name = 'yan.ai' WHERE id = 'u1'")
            conn.commit()
            conn.close()

            resolver = DingTalkMesUserResolver(
                app_key="client-id",
                app_secret="client-secret",
                web_users_db_path=str(user_db),
                user_aliases_path=str(alias_file),
            )
            with patch.object(DingTalkMesUserResolver, "_fetch_dingtalk_profile", return_value={"name": "艾岩"}):
                result = resolver.resolve_mes_username("staff-001", "yan.ai")

        self.assertEqual("matched", result["status"])
        self.assertEqual("yan.ai", result["username"])
        self.assertEqual("real_name_alias", result["source"])

    def test_query_serial_permission_reports_multiple_exact_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_db = Path(tmpdir) / "project_configs.db"
            user_db = Path(tmpdir) / "web_users.db"
            self._build_project_db(project_db)
            self._build_user_db(user_db)

            service = PermissionQueryService(
                prefix_service=FakePrefixService(),
                user_resolver=FakeUserResolver(
                    {
                        "status": "multiple_exact",
                        "name": "艾岩",
                        "candidates": ["yan.ai", "yan.ai.2"],
                    }
                ),
                project_config_db_path=str(project_db),
                web_users_db_path=str(user_db),
            )

            reply = service.reply_for_serial(
                serial="Genesis-LiGFL10C2026041000461",
                sender_staff_id="staff-002",
                sender_nick="艾岩",
            )

        self.assertIn("同名", reply)
        self.assertIn("yan.ai", reply)
        self.assertIn("yan.ai.2", reply)


if __name__ == "__main__":
    unittest.main()
