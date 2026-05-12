from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IncomingMessage:
    text: str
    sender_nick: str
    conversation_type: str
    session_webhook: str
    at_bot: bool
    sender_staff_id: str = ""
    message_type: str = "text"
    image_download_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DownloadedImage:
    download_code: str
    mime_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class VisionRecognitionResult:
    serial_numbers: tuple[str, ...]
    product_type_names: tuple[str, ...]
    raw_qr_texts: tuple[str, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PrefixMatch:
    project_name: str
    product_type: str
    prefix: str
    length: int


@dataclass(frozen=True, slots=True)
class SerialQueryResult:
    serial: str
    found: bool
    project_name: str = ""
    product_type: str = ""
    quality_summary: str = ""
    process_summary: str = ""
    prefix_matches: tuple[PrefixMatch, ...] = ()
