import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from dingtalk_mes_bot.handlers.router import MessageRouter
from dingtalk_mes_bot.models import IncomingMessage
from dingtalk_mes_bot.services.dingtalk_doc_service import DingTalkDocService
from dingtalk_mes_bot.services.faq_service import FaqService
from dingtalk_mes_bot.services.llm_answer_service import LlmAnswerService
from dingtalk_mes_bot.services.mes_answer_service import MesAnswerService
from dingtalk_mes_bot.services.mes_query_service import MesQueryService


class FakeLlmAnswerService:
    def __init__(self, answer: str = "这是模型兜底回复"):
        self.answer_text = answer
        self.calls: list[str] = []

    def answer(self, text: str) -> str | None:
        self.calls.append(text)
        return self.answer_text


class FakeImageQueryService:
    def __init__(self, answer: str = "图片识别结果"):
        self.answer_text = answer
        self.calls = []

    def reply_for_images(self, download_codes, user_text=""):
        self.calls.append((tuple(download_codes), user_text))
        return self.answer_text


class FakeClient:
    def __init__(self, content: str | None):
        self.content = content
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.content


class FakeHttpResponse:
    def __init__(self, payload: str, status: int = 200):
        self._payload = payload.encode("utf-8")
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeQueryService:
    def __init__(self):
        self.calls = []

    def query_today_photo_uploads(self):
        self.calls.append("today_photo_uploads")
        return "今天已上传工序照片 1250 张。"

    def query_today_photo_project_distribution(self):
        self.calls.append("today_photo_project_distribution")
        return "今天工序照片共分布在 2 个项目，共 12 张。"


class FakeDocActionService:
    def __init__(self, reply: str | None = None):
        self.reply = reply
        self.calls = []

    def maybe_handle(self, message):
        self.calls.append(message)
        return self.reply


class FakePermissionQueryService:
    def __init__(self, serial_reply: str = "权限结果", image_reply: str = "图片权限结果"):
        self.serial_reply = serial_reply
        self.image_reply = image_reply
        self.serial_calls = []
        self.image_calls = []

    def is_permission_question(self, text: str) -> bool:
        return "权限" in text

    def reply_for_serial(self, serial: str, sender_staff_id: str, sender_nick: str) -> str:
        self.serial_calls.append((serial, sender_staff_id, sender_nick))
        return self.serial_reply

    def reply_for_images(self, download_codes, user_text: str, sender_staff_id: str, sender_nick: str) -> str:
        self.image_calls.append((tuple(download_codes), user_text, sender_staff_id, sender_nick))
        return self.image_reply


class FakeMesAnswerService:
    def __init__(self, answer_map=None):
        self.answer_map = answer_map or {}
        self.calls = []

    def answer(self, text: str) -> str | None:
        self.calls.append(text)
        return self.answer_map.get(text)


class FakeDiagnosisService:
    def __init__(self, can_handle=True, reply='诊断结果'):
        self._can_handle = can_handle
        self.reply = reply
        self.calls = []

    def can_handle(self, text: str) -> bool:
        self.calls.append(('can_handle', text))
        return self._can_handle

    def diagnose(self, text: str) -> str:
        self.calls.append(('diagnose', text))
        return self.reply


class RouterTests(unittest.TestCase):
    def test_faq_hit(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        msg = IncomingMessage("batch sync all projects", "tester", "2", "", True)
        reply = router.route(msg)
        self.assertIn("批量同步当前所有项目", reply)

    def test_sync_project_question_replies_in_chinese(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        msg = IncomingMessage("如何同步项目", "tester", "2", "", True)
        reply = router.route(msg)
        self.assertIn("同步", reply)
        self.assertIn("当前项目配置", reply)

    def test_pending_review_question_replies_in_chinese(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        msg = IncomingMessage("为什么待复核", "tester", "2", "", True)
        reply = router.route(msg)
        self.assertIn("待复核", reply)
        self.assertIn("人工", reply)

    def test_fallback_reply_is_chinese(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        msg = IncomingMessage("你会做什么", "tester", "2", "", True)
        reply = router.route(msg)
        self.assertIn("MES", reply)

    def test_faq_hit_should_not_call_llm(self):
        llm = FakeLlmAnswerService()
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            llm,
            FakeImageQueryService(),
        )
        msg = IncomingMessage("为什么待复核", "tester", "2", "", True)
        reply = router.route(msg)
        self.assertIn("待复核", reply)
        self.assertEqual([], llm.calls)

    def test_picture_message_gets_friendly_reply_without_llm(self):
        llm = FakeLlmAnswerService()
        image_query = FakeImageQueryService("图片已识别，发现 2 个序列号")
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            llm,
            image_query,
        )
        msg = IncomingMessage(
            "[图片消息]",
            "tester",
            "2",
            "",
            True,
            message_type="picture",
            image_download_codes=("img-code-001",),
        )
        reply = router.route(msg)
        self.assertIn("发现 2 个序列号", reply)
        self.assertEqual([], llm.calls)
        self.assertEqual([(("img-code-001",), "[图片消息]")], image_query.calls)

    def test_today_photo_question_routes_to_mes_query(self):
        llm = FakeLlmAnswerService()
        mes = FakeMesAnswerService({"今天上传了多少张工序照片": "今天已上传 1250 张工序照片。"})
        router = MessageRouter(
            FaqService(),
            mes,
            llm,
            FakeImageQueryService(),
        )
        msg = IncomingMessage("今天上传了多少张工序照片", "tester", "2", "", True)
        reply = router.route(msg)
        self.assertEqual("今天已上传 1250 张工序照片。", reply)
        self.assertEqual([], llm.calls)

    def test_today_photo_distribution_question_routes_to_mes_query(self):
        llm = FakeLlmAnswerService()
        expected = "今天工序照片共分布在 2 个项目，共 12 张。"
        mes = FakeMesAnswerService({"这1255张工序照片分布在几个项目？每个项目的照片量是多少？": expected})
        router = MessageRouter(
            FaqService(),
            mes,
            llm,
            FakeImageQueryService(),
        )
        msg = IncomingMessage("这1255张工序照片分布在几个项目？每个项目的照片量是多少？", "tester", "2", "", True)
        reply = router.route(msg)
        self.assertEqual(expected, reply)
        self.assertEqual([], llm.calls)

    def test_document_action_runs_before_llm(self):
        llm = FakeLlmAnswerService()
        doc_action = FakeDocActionService("已创建文档：今日工序照片统计 2026-04-14")
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            llm,
            FakeImageQueryService(),
            doc_action_service=doc_action,
        )
        msg = IncomingMessage("把今天上传的照片数量统计到文档中", "tester", "2", "", True, sender_staff_id="staff-001")
        reply = router.route(msg)
        self.assertEqual("已创建文档：今日工序照片统计 2026-04-14", reply)
        self.assertEqual([], llm.calls)
        self.assertEqual(1, len(doc_action.calls))

    def test_diagnosis_runs_before_llm(self):
        llm = FakeLlmAnswerService()
        diagnosis = FakeDiagnosisService(reply='诊断到 Web 服务异常')
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            llm,
            FakeImageQueryService(),
            diagnosis_service=diagnosis,
        )
        msg = IncomingMessage("web发布后打不开", "tester", "2", "", True)
        reply = router.route(msg)
        self.assertEqual('诊断到 Web 服务异常', reply)
        self.assertEqual([], llm.calls)
        self.assertEqual([('can_handle', 'web发布后打不开'), ('diagnose', 'web发布后打不开')], diagnosis.calls)


    def test_permission_question_with_image_routes_to_permission_service(self):
        llm = FakeLlmAnswerService()
        permission_service = FakePermissionQueryService(image_reply="\u56fe\u7247\u6743\u9650\u68c0\u67e5\u7ed3\u679c")
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            llm,
            FakeImageQueryService(),
            permission_query_service=permission_service,
        )
        msg = IncomingMessage(
            "\u8fd9\u4e2a\u4e8c\u7ef4\u7801\u4e3a\u4ec0\u4e48\u6ca1\u6709\u5de5\u5e8f\u6743\u9650",
            "yan.ai",
            "2",
            "",
            True,
            sender_staff_id="staff-001",
            message_type="picture",
            image_download_codes=("img-001",),
        )
        reply = router.route(msg)
        self.assertEqual("\u56fe\u7247\u6743\u9650\u68c0\u67e5\u7ed3\u679c", reply)
        self.assertEqual([], llm.calls)
        self.assertEqual(1, len(permission_service.image_calls))

    def test_requirement_planning_long_message_runs_before_permission_route(self):
        llm = FakeLlmAnswerService("这是整理后的 spec")
        permission_service = FakePermissionQueryService(serial_reply="不应命中权限")
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            llm,
            FakeImageQueryService(),
            permission_query_service=permission_service,
        )
        text = (
            "我有一个想法，mes app能不能做到一个断点提醒，生产完自动提醒测试和下一个部门，"
            "还能统计在制品和堆积再制品，请帮我整理这个 spec 和实现方式。"
        )
        reply = router.route(IncomingMessage(text, "tester", "2", "", True))
        self.assertEqual("这是整理后的 spec", reply)
        self.assertTrue(llm.calls)
        self.assertEqual([], permission_service.serial_calls)
        self.assertEqual([], permission_service.image_calls)

    def test_short_followup_summary_no_longer_falls_back_to_mes_intro(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("再总结一下", "tester", "2", "", True))
        self.assertIn("继续总结", reply)
        self.assertIn("再贴一次", reply)

    def test_weather_question_returns_capability_boundary(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("我想要查询南京今天的天气", "tester", "2", "", True))
        self.assertIn("暂不支持直接查询天气", reply)
        self.assertIn("MES", reply)

    def test_mes_capability_question_returns_overview(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("mes系统都有什么功能？", "tester", "2", "", True))
        self.assertIn("生产工单与排产", reply)
        self.assertIn("条码/序列号追踪", reply)

    def test_hermes_question_returns_hermes_intro(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("什么是Hermes", "tester", "2", "", True))
        self.assertIn("Hermes 是当前机器人接入的智能问答后端", reply)


class MesQueryServiceTests(unittest.TestCase):
    def test_mes_answer_service_detects_today_photo_project_distribution_question(self):
        query = FakeQueryService()
        service = MesAnswerService(query)
        reply = service.answer("这1255张工序照片分布在几个项目？每个项目的照片量是多少？")
        self.assertEqual("今天工序照片共分布在 2 个项目，共 12 张。", reply)
        self.assertEqual(["today_photo_project_distribution"], query.calls)

    def test_query_today_photo_project_distribution_groups_by_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "unified.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE process_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    captured_at INTEGER,
                    metadata TEXT
                )
                """
            )
            now = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
            yesterday = now - timedelta(days=1)
            rows = [
                (int(now.timestamp() * 1000), json.dumps({"projectName": "柳工双15"})),
                (int((now + timedelta(minutes=1)).timestamp() * 1000), json.dumps({"projectName": "柳工双15"})),
                (int((now + timedelta(minutes=2)).timestamp() * 1000), json.dumps({"projectName": "徐工二合一"})),
                (int(yesterday.timestamp() * 1000), json.dumps({"projectName": "不应计入"})),
            ]
            conn.executemany("INSERT INTO process_photos (captured_at, metadata) VALUES (?, ?)", rows)
            conn.commit()
            conn.close()

            service = MesQueryService("http://127.0.0.1:8891", unified_db_path=str(db_path))
            reply = service.query_today_photo_project_distribution()

        self.assertIn("今天工序照片共分布在 2 个项目，共 3 张。", reply)
        self.assertIn("1. 柳工双15：2 张", reply)
        self.assertIn("2. 徐工二合一：1 张", reply)


class LlmAnswerServiceTests(unittest.TestCase):
    def test_llm_answer_blocks_internal_draft_output(self):
        client = FakeClient(
            "4. **Drafting the Content (Internal Monologue/Draft):**\n"
            "* **Conclusion:** I don't have access to your MES database.\n"
            "* **Suggestions:** Check the Quality Workbench.\n"
        )
        service = LlmAnswerService(client=client, model="qwen3.5-35b-a3b")
        self.assertIsNone(service.answer("这1255张工序照片分布在几个项目？"))

    def test_llm_answer_keeps_normal_chinese_reply(self):
        client = FakeClient("今天工序照片主要集中在 3 个项目，最多的是柳工双15。")
        service = LlmAnswerService(client=client, model="qwen3.5-35b-a3b")
        self.assertEqual("今天工序照片主要集中在 3 个项目，最多的是柳工双15。", service.answer("今天照片分布情况"))


class DingTalkDocServiceTests(unittest.TestCase):
    def test_create_doc_converts_staff_id_to_union_id(self):
        service = DingTalkDocService(
            api_base_url="https://api.dingtalk.com",
            app_key="client-id",
            app_secret="client-secret",
            workspace_id="workspace-1",
            parent_node_id="parent-001",
        )
        captured = {}

        def fake_urlopen(req, timeout=20):
            if "oauth2/accessToken" in req.full_url:
                return FakeHttpResponse(json.dumps({"accessToken": "token-001", "expireIn": 7200}))
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["body"] = req.data.decode("utf-8")
            return FakeHttpResponse(json.dumps({
                "url": "https://alidocs.dingtalk.com/i/team/workspace-1/docs/doc-001",
                "nodeId": "doc-001",
                "docKey": "doc-key-001",
            }))

        with patch.object(service, "resolve_union_id_from_staff_id", return_value="union-001"), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = service.create_or_get_daily_photo_doc(date_text="2026-04-14", operator_id="staff-001")

        self.assertTrue(result.ok)
        self.assertTrue(result.created)
        self.assertEqual("POST", captured["method"])
        self.assertIn("/v1.0/doc/workspaces/workspace-1/docs", captured["url"])
        self.assertIn('"operatorId": "union-001"', captured["body"])

    def test_resolve_union_id_uses_userid_lookup(self):
        service = DingTalkDocService(
            api_base_url="https://api.dingtalk.com",
            app_key="client-id",
            app_secret="client-secret",
            workspace_id="workspace-1",
        )
        captured = {}

        def fake_urlopen(req, timeout=20):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["body"] = req.data.decode("utf-8")
            return FakeHttpResponse(json.dumps({
                "errcode": 0,
                "errmsg": "ok",
                "result": {
                    "userid": "staff-001",
                    "unionid": "union-001",
                },
            }))

        with patch.object(service, "_get_access_token", return_value="token-001"), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            union_id = service.resolve_union_id_from_staff_id("staff-001")

        self.assertEqual("union-001", union_id)
        self.assertEqual("POST", captured["method"])
        self.assertIn("topapi/v2/user/get?access_token=token-001", captured["url"])
        self.assertIn('"userid": "staff-001"', captured["body"])

    def test_query_node_by_url_converts_staff_id_to_union_id(self):
        service = DingTalkDocService(
            api_base_url="https://api.dingtalk.com",
            app_key="client-id",
            app_secret="client-secret",
            workspace_id="workspace-1",
        )
        captured = {}

        def fake_urlopen(req, timeout=20):
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["headers"] = dict(req.header_items())
            captured["body"] = req.data.decode("utf-8")
            return FakeHttpResponse(json.dumps({
                "nodeId": "node-001",
                "nodeType": "FOLDER",
            }))

        with patch.object(service, "_get_access_token", return_value="token-001"), \
             patch.object(service, "resolve_union_id_from_staff_id", return_value="union-001"), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = service.query_node_by_url(
                "https://alidocs.dingtalk.com/i/nodes/example?utm_scene=team_space",
                operator_id="staff-001",
            )

        self.assertTrue(result.ok)
        self.assertEqual("union-001", result.operator_union_id)
        self.assertIn("operatorId=union-001", captured["url"])
        self.assertEqual("POST", captured["method"])
        self.assertIn('"url": "https://alidocs.dingtalk.com/i/nodes/example?utm_scene=team_space"', captured["body"])


class ProjectCountAndChitchatTests(unittest.TestCase):
    def test_mes_answer_service_detects_active_project_count_question(self):
        class LocalQuery:
            def __init__(self):
                self.calls = []

            def query_active_project_count(self):
                self.calls.append("active_project_count")
                return "当前启用项目共 3 个。"

        query = LocalQuery()
        service = MesAnswerService(query)
        reply = service.answer("项目管理里面多少个项目")
        self.assertEqual("当前启用项目共 3 个。", reply)
        self.assertEqual(["active_project_count"], query.calls)

    def test_query_active_project_count_only_counts_active_and_not_archived(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "project_configs.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_name TEXT NOT NULL,
                    project_status TEXT NOT NULL DEFAULT 'active',
                    is_archived INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.executemany(
                "INSERT INTO projects (project_name, project_status, is_archived) VALUES (?, ?, ?)",
                [
                    ("A", "active", 0),
                    ("B", "active", 0),
                    ("C", "inactive", 0),
                    ("D", "active", 1),
                    ("E", "disabled", 0),
                ],
            )
            conn.commit()
            conn.close()

            service = MesQueryService(
                "http://127.0.0.1:8891",
                unified_db_path=str(Path(tmpdir) / "unified.db"),
                project_config_db_path=str(db_path),
            )
            reply = service.query_active_project_count()

        self.assertEqual("当前启用项目共 2 个。", reply)

    def test_router_answers_name_with_fixed_reply(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("你叫什么", "tester", "2", "", True))
        self.assertIn("MES小客服", reply)

    def test_router_answers_origin_with_fixed_reply(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("你来自哪里", "tester", "2", "", True))
        self.assertIn("MES", reply)

    def test_router_answers_creator_with_fixed_reply(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("谁发明的", "tester", "2", "", True))
        self.assertTrue("团队" in reply or "开发" in reply)

    def test_router_answers_model_question_with_hermes_reply(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService("补充一句：文本问题我会优先走 Hermes。"),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("你的大模型是啥", "tester", "2", "", True))
        self.assertIn("Hermes", reply)
        self.assertIn("图片识别", reply)

    def test_requirement_planning_question_prefers_llm_not_permission_fallback(self):
        llm = FakeLlmAnswerService(
            "1. 需求背景\n2. 目标\n3. 业务流程\n4. 状态流转\n5. 通知规则\n6. 任务拆解\n7. 验收标准"
        )
        permission_service = FakePermissionQueryService()
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            llm,
            FakeImageQueryService(),
            permission_query_service=permission_service,
        )
        reply = router.route(IncomingMessage("帮我整理这个需求的Spec和实现方式，并转成任务", "tester", "2", "", True))
        self.assertIn("需求背景", reply)
        self.assertIn("任务拆解", reply)
        self.assertEqual([], permission_service.serial_calls)
        self.assertEqual([], permission_service.image_calls)
        self.assertEqual(1, len(llm.calls))
        self.assertIn("你现在是 MES 需求架构与产品整理助手", llm.calls[0])
        self.assertIn("状态流转", llm.calls[0])
        self.assertIn("通知规则", llm.calls[0])
        self.assertIn("验收标准", llm.calls[0])

    def test_short_spec_request_returns_guidance_when_llm_unavailable(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(answer=None),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("帮我写spec", "tester", "2", "", True))
        self.assertIn("可以先写", reply)
        self.assertIn("需求背景", reply)
        self.assertIn("业务流程", reply)

    def test_quote_capability_question_no_longer_falls_back_to_mes_intro(self):
        router = MessageRouter(
            FaqService(),
            MesAnswerService(MesQueryService("http://127.0.0.1:8891")),
            FakeLlmAnswerService(answer=None),
            FakeImageQueryService(),
        )
        reply = router.route(IncomingMessage("你能报价吗", "tester", "2", "", True))
        self.assertIn("能", reply)
        self.assertIn("BOM", reply)
        self.assertNotIn("我可以先帮你回答常见 MES 问题", reply)


if __name__ == "__main__":
    unittest.main()
