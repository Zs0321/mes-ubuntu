from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable


class RepairLogManager:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, title: str, lines: Iterable[str] | None = None) -> None:
        payload = [f'[{datetime.now().isoformat(timespec="seconds")}] {title}']
        for line in lines or []:
            text = str(line).rstrip()
            if text:
                payload.append(text)
        payload.append('')
        with self.path.open('a', encoding='utf-8') as fh:
            fh.write('\n'.join(payload))

    def tail(self, limit: int = 120) -> list[str]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding='utf-8', errors='replace').splitlines()
        except Exception:
            return []
        return lines[-max(1, limit):]
