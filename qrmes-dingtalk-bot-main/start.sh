#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT_DIR/runtime.pid"
LOG_FILE="$ROOT_DIR/runtime.log"
DEFAULT_PYTHON_BIN="/home/aiyan/qrmes/.venv/bin/python"
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
PYTHON_BIN="${PYTHON_BIN:-$DEFAULT_PYTHON_BIN}"

MODE="${DINGTALK_BOT_MODE:-stream}"
MODULE="dingtalk_mes_bot.stream_app"
if [[ "$MODE" == "http" ]]; then
  MODULE="dingtalk_mes_bot.bot_app"
fi

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "already running: pid=$(cat "$PID_FILE") mode=$MODE module=$MODULE"
  exit 0
fi

if [ -x "$ROOT_DIR/scripts/install_shared_core.sh" ]; then
  "$ROOT_DIR/scripts/install_shared_core.sh" >/dev/null || true
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "python not executable: $PYTHON_BIN" >&2
  exit 1
fi

if [[ "$MODE" == "stream" ]]; then
  if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import dingtalk_stream
PY
  then
    echo "missing python dependency: dingtalk_stream in $PYTHON_BIN" >&2
    exit 1
  fi
fi

nohup "$PYTHON_BIN" -m "$MODULE" >> "$LOG_FILE" 2>&1 &
PID="$!"
echo "$PID" > "$PID_FILE"
sleep 3
if kill -0 "$PID" 2>/dev/null; then
  echo "started qrmes-dingtalk-bot pid=$PID mode=$MODE module=$MODULE python=$PYTHON_BIN"
else
  echo "failed to start qrmes-dingtalk-bot pid=$PID mode=$MODE module=$MODULE python=$PYTHON_BIN" >&2
  tail -n 40 "$LOG_FILE" >&2 || true
  rm -f "$PID_FILE"
  exit 1
fi
