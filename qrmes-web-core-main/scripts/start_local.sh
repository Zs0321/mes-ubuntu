#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/common_runtime.sh"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  load_runtime_env
  echo "already running: $(cat "$PID_FILE") port=$MESAPP_PORT"
  exit 0
fi

ensure_runtime_venv
install_runtime_requirements
start_runtime_process
