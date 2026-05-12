#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-/home/aiyan/qrmes/.venv/bin/python}"
QRMES_KINGDEE_DB_PATH="${QRMES_KINGDEE_DB_PATH:-/volume2/MES/QRMES/kingdee_sync.db}" \
QRMES_KINGDEE_AUTO_SYNC="${QRMES_KINGDEE_AUTO_SYNC:-true}" \
QRMES_KINGDEE_PULL_INTERVAL_SECONDS="${QRMES_KINGDEE_PULL_INTERVAL_SECONDS:-300}" \
QRMES_KINGDEE_PORT="${QRMES_KINGDEE_PORT:-9010}" \
"$PYTHON_BIN" -m flask --app qrmes_kingdee_integration.api.app run --host 0.0.0.0 --port "${QRMES_KINGDEE_PORT:-9010}"
