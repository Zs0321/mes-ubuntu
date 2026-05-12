#!/usr/bin/env bash
set -euo pipefail
URLS=(
  "http://127.0.0.1:8899/health"
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
echo "healthcheck failed" >&2
exit 1
