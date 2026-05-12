from __future__ import annotations

from dataclasses import dataclass

from .config import BotConfig
from .handlers.router import MessageRouter
from .service_factory import create_router


@dataclass(slots=True)
class Runtime:
    config: BotConfig
    router: MessageRouter


def create_runtime(config: BotConfig) -> Runtime:
    return Runtime(config=config, router=create_router(config))
