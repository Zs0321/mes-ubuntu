#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/runtime.pid"
LOG_FILE="$ROOT_DIR/runtime.log"
HEALTH_SCRIPT="$ROOT_DIR/scripts/healthcheck.sh"
echo "repo: qrmes-finance-service"
echo "port_hint: 9003"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "process: running pid=$(cat "$PID_FILE")"
else
  echo "process: stopped"
fi
if [ -x "$HEALTH_SCRIPT" ]; then
  if "$HEALTH_SCRIPT" >/tmp/qrmes_status_health.out 2>/tmp/qrmes_status_health.err; then
    echo "health: ok"
    cat /tmp/qrmes_status_health.out
  else
    echo "health: failed"
    cat /tmp/qrmes_status_health.err 2>/dev/null || true
  fi
fi
if [ -f "$LOG_FILE" ]; then
  echo "log: $LOG_FILE"
  tail -n 10 "$LOG_FILE" || true
fi
