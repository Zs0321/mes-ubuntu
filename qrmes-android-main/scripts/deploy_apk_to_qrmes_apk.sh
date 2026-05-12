#!/usr/bin/env bash
set -euo pipefail

# Fixed publish target for mobile APK updates.
# SMB path: smb://172.16.30.2/MES/QRMES/APK/
NAS_HOST="${NAS_HOST:-172.16.30.2}"
NAS_PORT="${NAS_PORT:-30001}"
NAS_USER="${NAS_USER:-panovation}"
NAS_PASS="${NAS_PASS:-Clt2020clt}"
REMOTE_APK_DIR="${REMOTE_APK_DIR:-/volume2/MES/QRMES/APK}"
VERSION_NAME="$(sed -nE 's/^[[:space:]]*versionName[[:space:]]+\"([0-9.]+)\".*/\1/p' app/build.gradle | head -n 1)"
VERSION_CODE_RAW="$(sed -nE 's/^[[:space:]]*versionCode[[:space:]]+([0-9]+).*/\1/p' app/build.gradle | head -n 1)"
if [[ -z "${VERSION_NAME}" ]]; then VERSION_NAME="1.2"; fi
if [[ -z "${VERSION_CODE_RAW}" ]]; then
  echo "ERROR: failed to read versionCode from app/build.gradle" >&2
  exit 1
fi
VERSION_CODE_PAD="$(printf "%03d" "${VERSION_CODE_RAW}")"
DEFAULT_RELEASE_APK="app/build/outputs/apk/release/Panovation MesApp v${VERSION_NAME}_${VERSION_CODE_PAD}.apk"
LOCAL_APK_PATH="${1:-${DEFAULT_RELEASE_APK}}"

if [[ "${LOCAL_APK_PATH}" == *"-debug"* ]] || [[ "${LOCAL_APK_PATH}" == *"/debug/"* ]]; then
  echo "ERROR: debug APK is not allowed for NAS publish: ${LOCAL_APK_PATH}" >&2
  exit 1
fi

if [[ ! -f "${LOCAL_APK_PATH}" ]]; then
  echo "ERROR: local apk not found: ${LOCAL_APK_PATH}" >&2
  echo "TIP: build release first -> ./gradlew :app:assembleRelease" >&2
  exit 1
fi

if ! command -v sshpass >/dev/null 2>&1; then
  echo "ERROR: sshpass is required." >&2
  exit 1
fi

REMOTE_NAME="$(basename "${LOCAL_APK_PATH}")"
REMOTE_PATH="${REMOTE_APK_DIR}/${REMOTE_NAME}"

echo "Publishing APK"
echo "  local : ${LOCAL_APK_PATH}"
echo "  remote: ${REMOTE_PATH}"

sshpass -p "${NAS_PASS}" ssh -p "${NAS_PORT}" -o StrictHostKeyChecking=no "${NAS_USER}@${NAS_HOST}" "mkdir -p '${REMOTE_APK_DIR}'"
sshpass -p "${NAS_PASS}" ssh -p "${NAS_PORT}" -o StrictHostKeyChecking=no "${NAS_USER}@${NAS_HOST}" "cat > '${REMOTE_PATH}'" < "${LOCAL_APK_PATH}"

sshpass -p "${NAS_PASS}" ssh -p "${NAS_PORT}" -o StrictHostKeyChecking=no "${NAS_USER}@${NAS_HOST}" \
  "ls -lh '${REMOTE_PATH}'; ls -1 '${REMOTE_APK_DIR}' | grep 'Panovation MesApp v${VERSION_NAME}_' | tail -n 5"

echo "Done."
