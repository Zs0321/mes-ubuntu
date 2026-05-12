#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD:$PWD/app_web:${PYTHONPATH:-}"
python3 -m app_web.run_finance_demo
