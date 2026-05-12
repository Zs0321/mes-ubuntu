#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
nohup .venv/bin/python -m feishu_mes_bot.bot_app > runtime.log 2>&1 &
echo $! > runtime.pid
echo "started pid $(cat runtime.pid)"
