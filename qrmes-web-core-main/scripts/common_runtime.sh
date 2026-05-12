#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${PID_FILE:-$ROOT_DIR/runtime.pid}"
LOG_FILE="${LOG_FILE:-$ROOT_DIR/runtime.log}"
RUNTIME_ENV_FILE="${RUNTIME_ENV_FILE:-$ROOT_DIR/runtime.env}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DEFAULT_MESAPP_HOST="${DEFAULT_MESAPP_HOST:-0.0.0.0}"
DEFAULT_MESAPP_PORT="${DEFAULT_MESAPP_PORT:-9001}"
FINANCE_ENV_CANDIDATES=(
  "${FINANCE_ENV_FILE:-}"
  "$ROOT_DIR/../.env"
)

load_optional_finance_env() {
  local candidate
  local parsed
  for candidate in "${FINANCE_ENV_CANDIDATES[@]}"; do
    if [ -n "$candidate" ] && [ -f "$candidate" ]; then
      parsed="$(python3 - "$candidate" <<'PY'
from pathlib import Path
import shlex
import sys
path = Path(sys.argv[1])
allowed_prefixes = ('KINGDEE_',)
for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():
    line = raw.strip()
    if not line or line.startswith('#'):
        continue
    if line.startswith('export '):
        line = line[7:].strip()
    if '=' not in line:
        continue
    key, value = line.split('=', 1)
    key = key.strip()
    if not key.startswith(allowed_prefixes):
        continue
    if not key or not key.replace('_', 'A').isalnum() or key[0].isdigit():
        continue
    print(f'export {key}={shlex.quote(value)}')
PY
)"
      if [ -n "$parsed" ]; then
        set -a
        eval "$parsed"
        set +a
      fi
      break
    fi
  done
}

load_runtime_env() {
  if [ -f "$RUNTIME_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$RUNTIME_ENV_FILE"
    set +a
  fi
  export MESAPP_HOST="${MESAPP_HOST:-$DEFAULT_MESAPP_HOST}"
  export MESAPP_PORT="${MESAPP_PORT:-$DEFAULT_MESAPP_PORT}"
}

build_runtime_pythonpath() {
  local current_pythonpath="${1:-${PYTHONPATH:-}}"
  local -a candidates=(
    "$ROOT_DIR/app_web"
    "$ROOT_DIR"
    "$ROOT_DIR/../qrmes-motor-qc/app_web"
    "$ROOT_DIR/../qrmes-finance-service/app_web"
  )
  local -A seen=()
  local -a merged=()
  local entry

  for entry in "${candidates[@]}"; do
    if [ -d "$entry" ] && [ -z "${seen[$entry]:-}" ]; then
      merged+=("$entry")
      seen[$entry]=1
    fi
  done

  IFS=':' read -r -a existing <<< "$current_pythonpath"
  for entry in "${existing[@]}"; do
    if [ -n "$entry" ] && [ -z "${seen[$entry]:-}" ]; then
      merged+=("$entry")
      seen[$entry]=1
    fi
  done

  local joined=""
  for entry in "${merged[@]}"; do
    if [ -z "$joined" ]; then
      joined="$entry"
    else
      joined+="::$entry"
    fi
  done
  echo "${joined//::/:}"
}

write_runtime_env() {
  {
    printf 'MESAPP_HOST=%q\n' "$MESAPP_HOST"
    printf 'MESAPP_PORT=%q\n' "$MESAPP_PORT"
    printf 'PYTHONPATH=%q\n' "$PYTHONPATH"
    for key in TOOL_EXPIRY_DINGTALK_WEBHOOK TOOL_EXPIRY_DINGTALK_SECRET; do
      value="${!key:-}"
      if [ -n "$value" ]; then
        printf '%s=%q\n' "$key" "$value"
      fi
    done
  } > "$RUNTIME_ENV_FILE"
}

prepare_runtime_env() {
  load_runtime_env
  load_optional_finance_env
  export PYTHONPATH
  PYTHONPATH="$(build_runtime_pythonpath "${PYTHONPATH:-}")"
  write_runtime_env
}

ensure_runtime_venv() {
  cd "$ROOT_DIR"
  if [ ! -d .venv ]; then
    "$PYTHON_BIN" -m venv .venv
  fi
  if [ ! -x .venv/bin/python ]; then
    echo "missing virtualenv python: $ROOT_DIR/.venv/bin/python" >&2
    exit 1
  fi
  .venv/bin/python -m ensurepip --upgrade >/dev/null 2>&1 || true
  .venv/bin/python -m pip install -U pip >/dev/null
}

install_runtime_requirements() {
  cd "$ROOT_DIR"
  if [ -f requirements.txt ]; then
    .venv/bin/python -m pip install -r requirements.txt
  fi
  if [ -x "$ROOT_DIR/scripts/install_shared_core.sh" ]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/install_shared_core.sh" || true
  fi
}

start_runtime_process() {
  cd "$ROOT_DIR"
  prepare_runtime_env
  nohup "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/app_web/mesapp.py" >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "started qrmes-web-core pid=$(cat "$PID_FILE") port=$MESAPP_PORT host=$MESAPP_HOST"
}
