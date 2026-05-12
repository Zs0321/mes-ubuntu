#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
bash ./stop.sh || true
bash ./start.sh
bash ./status.sh
