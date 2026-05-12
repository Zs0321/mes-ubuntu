from __future__ import annotations

import hashlib
from typing import Literal


def generate_signature(
    db_id: str,
    username: str,
    app_id: str,
    app_secret: str,
    timestamp: int,
    algorithm: Literal["sha256", "sha1"] = "sha256",
) -> str:
    parts = sorted([db_id, username, app_id, app_secret, str(timestamp)])
    raw = "".join(parts).encode("utf-8")
    if algorithm == "sha1":
        return hashlib.sha1(raw).hexdigest()
    return hashlib.sha256(raw).hexdigest()
