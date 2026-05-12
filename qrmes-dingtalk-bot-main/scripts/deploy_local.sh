#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
python3 -m venv .venv
source .venv/bin/activate
python -m ensurepip --upgrade >/dev/null 2>&1 || true
python -m pip install -U pip
if [ -f requirements.txt ]; then
  python -m pip install -r requirements.txt
fi
if [ -x "$ROOT_DIR/scripts/install_shared_core.sh" ]; then
  "$ROOT_DIR/scripts/install_shared_core.sh" || true
fi
nohup python3 -m dingtalk_mes_bot.bot_app > "$ROOT_DIR/runtime.log" 2>&1 &
echo $! > "$ROOT_DIR/runtime.pid"
echo "started qrmes-dingtalk-bot on port hint 8899"
