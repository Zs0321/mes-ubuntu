#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT_DIR/runtime.pid"
LOG_FILE="$ROOT_DIR/runtime.log"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

load_env_file() {
  local env_file="$1"
  [ -f "$env_file" ] || return 0
  while IFS= read -r raw_line || [ -n "$raw_line" ]; do
    local line="${raw_line%$'\r'}"
    case "$line" in
      ""|\#*) continue ;;
    esac
    if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      export "$line"
    fi
  done < "$env_file"
}

cd "$ROOT_DIR"
load_env_file "$ENV_FILE"
MODE="${DINGTALK_BOT_MODE:-stream}"
MODULE="dingtalk_mes_bot.stream_app"
if [[ "$MODE" == "http" ]]; then
  MODULE="dingtalk_mes_bot.bot_app"
fi

echo "repo: qrmes-dingtalk-bot"
echo "mode: $MODE"
echo "module: $MODULE"
if [[ "$MODE" == "http" ]]; then
  echo "port_hint: ${DINGTALK_BOT_PORT:-8899}"
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  PID="$(cat "$PID_FILE")"
  echo "process: running pid=$PID"
  ps -p "$PID" -o pid=,ppid=,stat=,etime=,command= || true
else
  echo "process: stopped"
fi

if [ -f "$LOG_FILE" ]; then
  echo "log: $LOG_FILE"
  tail -n 20 "$LOG_FILE" || true
fi
