#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.11 || command -v python3)}"
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/app_web:${PYTHONPATH:-}"
$PYTHON_BIN -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade >/dev/null 2>&1 || true
python -m pip install -U pip
if [ -f requirements.txt ]; then
  python -m pip install -r requirements.txt
fi
if [ -x "$ROOT_DIR/scripts/install_shared_core.sh" ]; then
  "$ROOT_DIR/scripts/install_shared_core.sh" || true
fi
nohup python3 -m app_web.run_finance_demo > "$ROOT_DIR/runtime.log" 2>&1 &
echo $! > "$ROOT_DIR/runtime.pid"
echo "started qrmes-finance-service on port hint 9003"
