#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
exec python3 -m feishu_mes_bot.main
