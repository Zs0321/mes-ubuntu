#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
if [ -f runtime.pid ]; then
  PID=$(cat runtime.pid)
  if kill -0 "$PID" >/dev/null 2>&1; then
    echo "process: running ($PID)"
  else
    echo "process: not running (stale pid $PID)"
  fi
else
  echo "process: no pid"
fi
if [ -f runtime.log ]; then
  echo "--- log tail ---"
  tail -n 20 runtime.log || true
fi
if [ -x scripts/healthcheck.sh ]; then
  echo "--- health ---"
  scripts/healthcheck.sh || true
fi
