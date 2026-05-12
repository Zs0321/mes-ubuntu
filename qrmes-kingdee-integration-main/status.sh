#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="${QRMES_KINGDEE_RUNTIME_DIR:-${ROOT_DIR}/.runtime}"
PID_FILE="$RUNTIME_DIR/runtime.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "running pid=$(cat "$PID_FILE") runtime_dir=$RUNTIME_DIR"
else
  echo "stopped runtime_dir=$RUNTIME_DIR"
fi
