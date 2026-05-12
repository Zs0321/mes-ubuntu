from __future__ import annotations

import re
from dataclasses import dataclass

from .openai_compatible_service import OpenAiCompatibleService


SYSTEM_PROMPT = (
    "You are an MES assistant for factory production, project configuration, quality workbench, "
    "and APK troubleshooting. Always answer in Simplified Chinese. "
    "Give a direct conclusion first, then explain the likely cause and concrete next steps when the user is asking a real problem. "
    "Prefer concise but useful answers with 2-4 concrete points instead of vague capability statements. "
    "Do not hide behind phrases like '我会帮你' or '我可以做什么' unless the user is explicitly asking about capability. "
    "Do not invent APIs, permissions, or data. "
    "Never output chain-of-thought, reasoning steps, drafting notes, internal monologue, or analysis sections."
)

FORBIDDEN_REPLY_PATTERNS = (
    "thinking process",
    "internal monologue",
    "drafting",
    "reasoning:",
    "chain of thought",
    "analysis:",
    "思考过程",
    "内部草稿",
)


@dataclass(slots=True)
class LlmAnswerService:
    client: OpenAiCompatibleService
    model: str

    def answer(self, text: str) -> str | None:
        prompt = (text or "").strip()
        if not prompt or not self.model.strip():
            return None

        content = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=400,
        )
        return self._clean_reply(content)

    @staticmethod
    def _clean_reply(content: str | None) -> str | None:
        if not content:
            return None
        reply = str(content).strip()
        if not reply:
            return None
        lowered = reply.lower()
        if any(marker in lowered for marker in FORBIDDEN_REPLY_PATTERNS):
            return None
        if "Thinking Process:" in reply:
            marker = "Thinking Process:"
            _, _, tail = reply.partition(marker)
            candidate = tail.strip()
            if "\n\n" in candidate:
                reply = candidate.rsplit("\n\n", 1)[-1].strip() or reply
        if reply.lower().startswith("final answer:"):
            reply = reply.split(":", 1)[-1].strip()
        reply = re.sub(r"^\s*(final answer|最终答案|答复|结论)\s*[:：]\s*", "", reply, flags=re.IGNORECASE)
        return reply or None
