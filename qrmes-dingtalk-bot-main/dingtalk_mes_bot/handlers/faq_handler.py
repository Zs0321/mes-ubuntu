from __future__ import annotations

from dataclasses import dataclass

from ..services.faq_service import FaqService


@dataclass(slots=True)
class FaqHandler:
    faq_service: FaqService

    def handle(self, text: str) -> str | None:
        return self.faq_service.answer(text)
