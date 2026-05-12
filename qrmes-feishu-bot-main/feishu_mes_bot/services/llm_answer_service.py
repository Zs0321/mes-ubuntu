from __future__ import annotations


class LlmAnswerService:
    def __init__(self, client, model: str):
        self.client = client
        self.model = model

    def answer(self, text: str) -> str | None:
        if not text or not self.client:
            return None
        system_prompt = (
            "你是 MES 飞书排障助手。仅在确定性规则没命中时，给出简短中文建议。"
            "不要编造接口状态；如果信息不足，明确提示补充现象。"
        )
        return self.client.chat(self.model, system_prompt, text)
