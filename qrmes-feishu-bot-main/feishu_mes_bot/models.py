from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class IncomingMessage:
    text: str
    sender_name: str
    sender_open_id: str
    chat_id: str
    chat_type: str
    message_id: str
    at_bot: bool
    receive_id: str
    receive_id_type: str
    message_type: str = "text"
    mentions: Tuple[str, ...] = field(default_factory=tuple)
    resource_key: str = ""
    resource_type: str = ""
    resource_name: str = ""
