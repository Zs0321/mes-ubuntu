#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/aiyan/MES-TEST-aiyan/mes_ubuntu"
APP_DIR="$ROOT_DIR/app_web"
EFFECTIVE_DATA_DIR="${MESAPP_DATA_DIR:-/home/aiyan/QRMES}"
LOG_DIR="${MESAPP_LOG_DIR:-$EFFECTIVE_DATA_DIR/log}"
PID_FILE="$LOG_DIR/mesapp_17216207.pid"
LOG_FILE="$LOG_DIR/mesapp_17216207.log"

mkdir -p "$LOG_DIR"
cd "$APP_DIR"

export MESAPP_DATA_DIR="$EFFECTIVE_DATA_DIR"
export MESAPP_HOST="${MESAPP_HOST:-0.0.0.0}"
export MESAPP_PORT="${MESAPP_PORT:-9001}"
export PATH="$HOME/.local/bin:$PATH"

KINGDEE_ENV_FILE="${KINGDEE_ENV_FILE:-$ROOT_DIR/.env.finance_demo_125}"
if [ -f "$KINGDEE_ENV_FILE" ]; then
  set -a
  . "$KINGDEE_ENV_FILE"
  set +a
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "mesapp already running: $(cat "$PID_FILE")"
  exit 0
fi

PYTHON_BIN="$(command -v python3)"
echo "using python: $PYTHON_BIN"
echo "data dir: $MESAPP_DATA_DIR"
echo "log file: $LOG_FILE"
nohup "$PYTHON_BIN" mesapp.py >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
sleep 5
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "mesapp started"
  echo "pid: $(cat "$PID_FILE")"
  echo "log: $LOG_FILE"
  echo "url: http://172.16.20.7:$MESAPP_PORT"
  echo "health: http://172.16.20.7:$MESAPP_PORT/health"
else
  echo "mesapp failed to start"
  tail -n 60 "$LOG_FILE" || true
  exit 1
fi
