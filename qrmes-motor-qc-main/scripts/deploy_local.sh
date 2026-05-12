#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
if [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi
if [ -x "$ROOT_DIR/scripts/install_shared_core.sh" ]; then
  "$ROOT_DIR/scripts/install_shared_core.sh" || true
fi
nohup python3 -m app_web.run_motor_qc > "$ROOT_DIR/runtime.log" 2>&1 &
echo $! > "$ROOT_DIR/runtime.pid"
echo "started qrmes-motor-qc on port hint 9002"
