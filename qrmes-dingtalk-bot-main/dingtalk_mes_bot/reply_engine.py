from __future__ import annotations

from .models import IncomingMessage
from .runtime import Runtime


def build_reply(runtime: Runtime, message: IncomingMessage) -> str:
    return runtime.router.route(message)
