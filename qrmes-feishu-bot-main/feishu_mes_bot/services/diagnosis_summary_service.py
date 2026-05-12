from __future__ import annotations


class DiagnosisSummaryService:
    def __init__(self, client, model: str):
        self.client = client
        self.model = model

    def summarize(self, user_text: str, diagnosis_text: str) -> str | None:
        if not self.client:
            return None
        prompt = (
            "请基于下面排障结论，补一小段‘追问建议’，帮助用户一次性补齐排查信息。"
            "只输出 1-3 句中文，不要重复原文。\n"
            "用户问题：%s\n\n当前诊断：%s" % (user_text, diagnosis_text)
        )
        return self.client.chat(self.model, '你是 MES 排障追问助手。', prompt)
