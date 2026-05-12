#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/common_runtime.sh"

load_runtime_env
URLS=(
  "http://127.0.0.1:${MESAPP_PORT}/health"
  "http://127.0.0.1:${MESAPP_PORT}/api/h2/health"
)
for url in "${URLS[@]}"; do
  if command -v curl >/dev/null 2>&1; then
    if curl -fsS "$url" >/tmp/qrmes_healthcheck.out 2>/dev/null; then
      echo "OK $url"
      cat /tmp/qrmes_healthcheck.out
      exit 0
    fi
  fi
done
echo "healthcheck failed on port ${MESAPP_PORT}" >&2
exit 1
