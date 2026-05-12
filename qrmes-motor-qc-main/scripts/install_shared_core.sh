#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SHARED_DIR="${SHARED_DIR:-$ROOT_DIR/../qrmes-shared-core}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ ! -f "$SHARED_DIR/pyproject.toml" ]; then
  echo "shared-core not found at: $SHARED_DIR" >&2
  exit 1
fi
$PYTHON_BIN -m pip install -e "$SHARED_DIR"
echo "installed qrmes-shared-core from $SHARED_DIR"
