import unittest

from feishu_mes_bot.handlers.router import MessageRouter
from feishu_mes_bot.models import IncomingMessage


class FakeDiagnosisService:
    def __init__(self, can_handle=True, reply="诊断结果"):
        self._can_handle = can_handle
        self.reply = reply
        self.calls = []

    def can_handle(self, text):
        self.calls.append(("can_handle", text))
        return self._can_handle

    def diagnose(self, text):
        self.calls.append(("diagnose", text))
        return self.reply


class FakeLlmAnswerService:
    def __init__(self, reply="LLM兜底"):
        self.reply = reply
        self.calls = []

    def answer(self, text):
        self.calls.append(text)
        return self.reply


class RouterTests(unittest.TestCase):
    def test_router_prefers_issue_diagnosis(self):
        diagnosis = FakeDiagnosisService(reply="定位到 Web 发布问题")
        llm = FakeLlmAnswerService()
        router = MessageRouter(diagnosis_service=diagnosis, llm_answer_service=llm)
        message = IncomingMessage(
            text="web发布后打不开",
            sender_name="tester",
            sender_open_id="ou_1",
            chat_id="oc_1",
            chat_type="group",
            message_id="om_1",
            at_bot=True,
            receive_id="oc_1",
            receive_id_type="chat_id",
        )

        reply = router.route(message)
        self.assertEqual("定位到 Web 发布问题", reply)
        self.assertEqual([], llm.calls)
        self.assertEqual([("can_handle", "web发布后打不开"), ("diagnose", "web发布后打不开")], diagnosis.calls)

    def test_router_falls_back_to_llm(self):
        diagnosis = FakeDiagnosisService(can_handle=False)
        llm = FakeLlmAnswerService(reply="请提供更多上下文")
        router = MessageRouter(diagnosis_service=diagnosis, llm_answer_service=llm)
        message = IncomingMessage(
            text="帮我优化下话术",
            sender_name="tester",
            sender_open_id="ou_1",
            chat_id="oc_1",
            chat_type="group",
            message_id="om_1",
            at_bot=True,
            receive_id="oc_1",
            receive_id_type="chat_id",
        )

        reply = router.route(message)
        self.assertEqual("请提供更多上下文", reply)
        self.assertEqual(["帮我优化下话术"], llm.calls)

    def test_router_empty_text_prompt(self):
        diagnosis = FakeDiagnosisService()
        llm = FakeLlmAnswerService()
        router = MessageRouter(diagnosis_service=diagnosis, llm_answer_service=llm)
        message = IncomingMessage(
            text="   ",
            sender_name="tester",
            sender_open_id="ou_1",
            chat_id="oc_1",
            chat_type="group",
            message_id="om_1",
            at_bot=True,
            receive_id="oc_1",
            receive_id_type="chat_id",
        )

        reply = router.route(message)
        self.assertIn("请直接描述", reply)
        self.assertEqual([], llm.calls)


if __name__ == "__main__":
    unittest.main()
