#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m app_web.run_motor_qc
