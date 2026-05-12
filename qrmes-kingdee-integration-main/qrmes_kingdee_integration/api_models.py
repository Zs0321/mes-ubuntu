from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApiResult:
    ok: bool
    data: dict[str, Any]
    status_code: int = 200
