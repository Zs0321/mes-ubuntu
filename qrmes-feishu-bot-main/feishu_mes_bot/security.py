from __future__ import annotations

from typing import Any, Dict


def verify_event_token(payload: Dict[str, Any], verification_token: str) -> bool:
    if not verification_token:
        return True
    if not isinstance(payload, dict):
        return False
    header = payload.get("header") or {}
    token = header.get("token")
    return isinstance(token, str) and token == verification_token
