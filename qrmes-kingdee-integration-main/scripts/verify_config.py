#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
python3 - <<'PY'
from qrmes_kingdee_integration.config import load_settings
settings = load_settings()
print(settings.kingdee.public_summary)
PY
