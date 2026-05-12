from __future__ import annotations

from dataclasses import dataclass

from ..models import IncomingMessage
from ..services.doc_action_service import DocActionService
from ..services.faq_service import FaqService
from ..services.image_query_service import ImageQueryService
from ..services.llm_answer_service import LlmAnswerService
from ..services.mes_answer_service import MesAnswerService


@dataclass(slots=True)
class MessageRouter:
    faq_service: FaqService
    mes_answer_service: MesAnswerService
    llm_answer_service: LlmAnswerService
    image_query_service: ImageQueryService
    doc_action_service: DocActionService | None = None
    permission_query_service: object | None = None
    diagnosis_service: object | None = None

    def route(self, message: IncomingMessage) -> str:
        text = message.text.strip()
        if not text:
            return "请直接发送你的 MES 问题，我会尽量帮你定位。"

        if self.permission_query_service and self.permission_query_service.is_permission_question(text):
            if message.image_download_codes:
                return self.permission_query_service.reply_for_images(
                    message.image_download_codes,
                    user_text=text,
                    sender_staff_id=message.sender_staff_id,
                    sender_nick=message.sender_nick,
                )
            serial = self.permission_query_service.extract_serial(text)
            if serial:
                return self.permission_query_service.reply_for_serial(
                    serial,
                    sender_staff_id=message.sender_staff_id,
                    sender_nick=message.sender_nick,
                )
            return "请直接把序列号发给我，或者发二维码/标签图片，我来帮你判断当前提问人有没有对应工序权限。"

        if message.image_download_codes:
            return self.image_query_service.reply_for_images(message.image_download_codes, user_text=text)

        if self.diagnosis_service:
            if hasattr(self.diagnosis_service, 'diagnose_message'):
                diagnosis_reply = self.diagnosis_service.diagnose_message(message)
                if diagnosis_reply:
                    return diagnosis_reply
            elif self.diagnosis_service.can_handle(text):
                return self.diagnosis_service.diagnose(text)

        chitchat = self._reply_for_chitchat(text)
        if chitchat:
            return chitchat

        faq = self.faq_service.answer(text)
        if faq:
            return faq

        if self.doc_action_service:
            doc_reply = self.doc_action_service.maybe_handle(message)
            if doc_reply:
                return doc_reply

        mes = self.mes_answer_service.answer(text)
        if mes:
            return mes

        llm = self.llm_answer_service.answer(text)
        if llm:
            return llm

        return "我可以先帮你回答常见 MES 问题，也支持序列号查询、照片统计和部分权限判断。你可以直接问，比如“如何同步项目”“为什么待复核”“为什么401”。"

    def _reply_for_chitchat(self, text: str) -> str | None:
        content = (text or "").strip()
        if not content:
            return None

        base_answer = None
        if "你叫什么" in content or "你是谁" in content:
            base_answer = "我叫 MES小客服，是这套 MES 系统里的群聊助手。"
        elif "你来自哪里" in content:
            base_answer = "我来自你们当前这套 MES 机器人能力，和 MES 服务部署在一起。"
        elif "谁发明" in content or "谁开发" in content:
            base_answer = "我是你们这套 MES 项目里扩展出来的机器人能力，由 MES 的开发与运维一起做出来。"
        elif "你能帮我做什么" in content or "你会做什么" in content:
            base_answer = "我现在主要能帮助回答常见 MES 问题、查询部分实时统计、识别标签图片并辅助做基础排查。"
        elif "大模型" in content or "模型是啥" in content or "用的什么模型" in content:
            base_answer = "我当前文本问答主链路接的是 Hermes，运行在局域网里的独立 Hermes 服务上；图片识别仍保留原来的视觉识别链路。"
        elif "为什么你有时候答不出来" in content:
            base_answer = "有些问题如果还没接到真实查询接口，或者问题表达太泛，我就只能先给出基础说明，没法直接返回准确业务数据。"
        elif "怎么问你更容易答对" in content:
            base_answer = "最容易答对的方式是把问题说具体一点，最好带上序列号、项目名、日期或你想查询的统计口径。"

        if not base_answer:
            return None

        polished = self.llm_answer_service.answer(
            f"请基于这句固定事实，用自然、简短、口语化的中文补充 1 句话说明，不要改变事实，不要编造：{base_answer}"
        )
        if polished and polished != base_answer:
            return base_answer + chr(10) + polished
        return base_answer