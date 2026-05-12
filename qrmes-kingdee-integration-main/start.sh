#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="${QRMES_KINGDEE_RUNTIME_DIR:-${ROOT_DIR}/.runtime}"
PID_FILE="$RUNTIME_DIR/runtime.pid"
LOG_FILE="$RUNTIME_DIR/runtime.log"
PYTHON_BIN="${PYTHON_BIN:-/home/aiyan/qrmes/.venv/bin/python}"
PORT="${QRMES_KINGDEE_PORT:-9010}"
export QRMES_KINGDEE_DB_PATH="${QRMES_KINGDEE_DB_PATH:-/volume2/MES/QRMES/kingdee_sync.db}"
export QRMES_KINGDEE_AUTO_SYNC="${QRMES_KINGDEE_AUTO_SYNC:-true}"
export QRMES_KINGDEE_PULL_INTERVAL_SECONDS="${QRMES_KINGDEE_PULL_INTERVAL_SECONDS:-300}"
mkdir -p "$RUNTIME_DIR"
cd "$ROOT_DIR"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "already running: pid=$(cat "$PID_FILE")"
  exit 0
fi
nohup "$PYTHON_BIN" -m flask --app qrmes_kingdee_integration.api.app run --host 0.0.0.0 --port "$PORT" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "started qrmes-kingdee-integration pid=$(cat "$PID_FILE") port=$PORT runtime_dir=$RUNTIME_DIR"
