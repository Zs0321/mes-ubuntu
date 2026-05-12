from __future__ import annotations

from .bot_app import run_callback_server
from .config import load_config
from .long_connection import run_long_connection


def run(config=None):
    config = config or load_config()
    if config.mode == 'long_connection':
        return run_long_connection(config)
    return run_callback_server(config)


if __name__ == '__main__':
    run()
