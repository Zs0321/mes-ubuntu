#!/usr/bin/env bash
set -euo pipefail

EFFECTIVE_DATA_DIR="${MESAPP_DATA_DIR:-/home/aiyan/QRMES}"
LOG_DIR="${MESAPP_LOG_DIR:-$EFFECTIVE_DATA_DIR/log}"
PID_FILE="$LOG_DIR/mesapp_17216207.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "pid file not found"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  sleep 2
  if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID"
  fi
  echo "stopped pid: $PID"
else
  echo "process not running: $PID"
fi
rm -f "$PID_FILE"
