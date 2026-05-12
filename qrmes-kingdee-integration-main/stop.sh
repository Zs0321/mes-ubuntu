#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="${QRMES_KINGDEE_RUNTIME_DIR:-${ROOT_DIR}/.runtime}"
PID_FILE="$RUNTIME_DIR/runtime.pid"
if [ ! -f "$PID_FILE" ]; then
  echo "not running"
  exit 0
fi
PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "stopped pid=$PID"
else
  echo "stale pid=$PID"
fi
rm -f "$PID_FILE"
