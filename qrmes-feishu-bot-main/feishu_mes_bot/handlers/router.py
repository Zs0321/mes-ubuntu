from __future__ import annotations

from dataclasses import dataclass

from ..models import IncomingMessage


@dataclass
class MessageRouter:
    diagnosis_service: object
    llm_answer_service: object = None

    def route(self, message: IncomingMessage) -> str:
        text = (message.text or "").strip()
        if not text:
            return "请直接描述问题现象，最好带上：APK/Web/后端/数据库、项目名、序列号、报错时间。"

        if self.diagnosis_service and self.diagnosis_service.can_handle(text):
            return self.diagnosis_service.diagnose(text)

        if self.llm_answer_service:
            fallback = self.llm_answer_service.answer(text)
            if fallback:
                return fallback

        return "我现在更擅长定位 APK、Web、后端服务和数据库问题。你可以直接说“web发布后打不开”“APK更新失败”“数据库权限异常”。"
