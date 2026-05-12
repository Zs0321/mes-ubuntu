#!/usr/bin/env bash
set -euo pipefail

APP_HOME="${APP_HOME:-/volume2/qrmes}"
REPO_DIR="${REPO_DIR:-/volume2/mes_ubuntu}"
REPO_URL="${REPO_URL:-git@172.16.30.9:Xiaoai/mes_ubuntu.git}"
BRANCH="${BRANCH:-main}"
LOG_DIR="${LOG_DIR:-$APP_HOME/logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/gitlab_deploy.log}"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

echo "[$(date '+%F %T')] deploy check start"

if ! command -v git >/dev/null 2>&1; then
  echo "git not found"
  exit 1
fi

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "[$(date '+%F %T')] cloning repository into $REPO_DIR"
  rm -rf "$REPO_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
  changed=1
else
  git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
  git -C "$REPO_DIR" fetch --prune origin "$BRANCH"
  current_commit="$(git -C "$REPO_DIR" rev-parse HEAD)"
  target_commit="$(git -C "$REPO_DIR" rev-parse "origin/$BRANCH")"
  if [ "$current_commit" = "$target_commit" ]; then
    echo "[$(date '+%F %T')] no changes ($current_commit)"
    exit 0
  fi
  echo "[$(date '+%F %T')] updating $current_commit -> $target_commit"
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
  git -C "$REPO_DIR" clean -fd
  changed=1
fi

if [ "${changed:-0}" = "1" ]; then
  chmod +x "$APP_HOME/start.sh" "$APP_HOME/stop.sh" "$APP_HOME/status.sh" "$REPO_DIR/gradlew" 2>/dev/null || true
  "$APP_HOME/stop.sh" || true
  "$APP_HOME/start.sh"
  "$APP_HOME/status.sh" || true
fi

echo "[$(date '+%F %T')] deploy check end"
