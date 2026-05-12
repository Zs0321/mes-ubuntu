#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qrmes_kingdee_integration.config import load_settings
from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore

settings = load_settings()
store = SQLiteSyncStore(settings.local_db_path)
print(f'initialized local db: {store.db_path}')
