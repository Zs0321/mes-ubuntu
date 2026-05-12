#!/usr/bin/env bash
set -euo pipefail

DEPLOY_HOST="${DEPLOY_HOST:-172.16.30.10}"
DEPLOY_PORT="${DEPLOY_PORT:-9909}"
DEPLOY_USER="${DEPLOY_USER:-aiyan}"
DEPLOY_COMMAND="${DEPLOY_COMMAND:-/volume2/qrmes/bin/update_now.sh}"
SSH_TARGET="${DEPLOY_USER}@${DEPLOY_HOST}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command ssh

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
ssh-keyscan -p "$DEPLOY_PORT" -H "$DEPLOY_HOST" >>"$HOME/.ssh/known_hosts" 2>/dev/null || true

if [ -n "${DEPLOY_SSH_PRIVATE_KEY:-}" ]; then
  printf '%s\n' "$DEPLOY_SSH_PRIVATE_KEY" >"$HOME/.ssh/gitlab_ci_deploy_key"
  chmod 600 "$HOME/.ssh/gitlab_ci_deploy_key"
  SSH_CMD=(ssh -i "$HOME/.ssh/gitlab_ci_deploy_key" -p "$DEPLOY_PORT" -o StrictHostKeyChecking=yes "$SSH_TARGET")
elif [ -n "${DEPLOY_SSH_PASSWORD:-}" ]; then
  require_command sshpass
  SSH_CMD=(sshpass -p "$DEPLOY_SSH_PASSWORD" ssh -p "$DEPLOY_PORT" -o StrictHostKeyChecking=yes "$SSH_TARGET")
else
  echo "Missing deploy credential. Set DEPLOY_SSH_PRIVATE_KEY or DEPLOY_SSH_PASSWORD in GitLab CI/CD variables." >&2
  exit 1
fi

echo "Deploying to ${SSH_TARGET}:${DEPLOY_COMMAND}"
"${SSH_CMD[@]}" "$DEPLOY_COMMAND"
