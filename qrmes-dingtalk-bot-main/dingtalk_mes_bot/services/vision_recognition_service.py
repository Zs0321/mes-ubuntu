from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass

from ..models import DownloadedImage, VisionRecognitionResult
from .openai_compatible_service import OpenAiCompatibleService


VISION_SYSTEM_PROMPT = (
    "You are an MES label recognition assistant. "
    "Extract all visible QR contents, full serial numbers, and product type names from the images. "
    "Return JSON only, with no explanation."
)

VISION_USER_PROMPT = (
    'Please analyze these label images and return strict JSON: '
    '{"serial_numbers":["..."],"product_type_names":["..."],"raw_qr_texts":["..."],"notes":["..."]}. '
    "Rules: keep serial_numbers in original case and symbols; if multiple QR codes are visible, list all of them; "
    "put uncertain observations into notes; product_type_names should only include clearly visible names; "
    "exclude work order numbers, MO numbers, quantities, dates, versions, and board names from serial_numbers."
)


@dataclass(slots=True)
class VisionRecognitionService:
    client: OpenAiCompatibleService
    model: str

    def recognize(self, images: list[DownloadedImage], user_text: str = "") -> VisionRecognitionResult:
        if not images or not self.model.strip():
            return VisionRecognitionResult((), (), (), ())

        content: list[dict[str, object]] = [{"type": "text", "text": self._build_prompt(user_text)}]
        for image in images:
            mime_type = image.mime_type or mimetypes.guess_type(image.download_code)[0] or "image/jpeg"
            image_b64 = base64.b64encode(image.data).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                }
            )

        reply = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0.1,
            max_tokens=600,
        )
        return self._parse_reply(reply)

    @staticmethod
    def _build_prompt(user_text: str) -> str:
        prompt = VISION_USER_PROMPT
        note = str(user_text or "").strip()
        if note and note != "[\u56fe\u7247\u6d88\u606f]":
            prompt += f" User note: {note}"
        return prompt

    @staticmethod
    def _parse_reply(reply: str | None) -> VisionRecognitionResult:
        if not reply:
            return VisionRecognitionResult((), (), (), ())
        text = str(reply).strip()
        text = VisionRecognitionService._extract_json_block(text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return VisionRecognitionResult((), (), (), (reply.strip(),))

        serial_numbers = VisionRecognitionService._normalize_string_list(data.get("serial_numbers"))
        product_type_names = VisionRecognitionService._normalize_string_list(data.get("product_type_names"))
        raw_qr_texts = VisionRecognitionService._normalize_string_list(data.get("raw_qr_texts"))
        notes = VisionRecognitionService._normalize_string_list(data.get("notes"))
        return VisionRecognitionResult(serial_numbers, product_type_names, raw_qr_texts, notes)

    @staticmethod
    def _normalize_string_list(value) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return tuple(normalized)

    @staticmethod
    def _extract_json_block(text: str) -> str:
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
        if fenced:
            return fenced.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1].strip()
        return text
