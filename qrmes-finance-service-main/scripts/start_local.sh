#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/runtime.pid"
LOG_FILE="$ROOT_DIR/runtime.log"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.11 || command -v python3)}"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/app_web:${PYTHONPATH:-}"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "already running: $(cat "$PID_FILE")"
  exit 0
fi
if [ ! -d .venv ]; then
  $PYTHON_BIN -m venv .venv
fi
source .venv/bin/activate
python -m ensurepip --upgrade >/dev/null 2>&1 || true
python -m pip install -U pip >/dev/null
if [ -f requirements.txt ]; then
  python -m pip install -r requirements.txt >/dev/null
fi
if [ -x "$ROOT_DIR/scripts/install_shared_core.sh" ]; then
  "$ROOT_DIR/scripts/install_shared_core.sh" >/dev/null || true
fi
nohup python -m app_web.run_finance_demo >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "started qrmes-finance-service pid=$(cat "$PID_FILE") port_hint=9003"
