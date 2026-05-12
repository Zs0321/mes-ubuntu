#!/usr/bin/env bash
set -euo pipefail

# Build a transfer-ready bundle for edge-station testing.
# Output:
#   output/packages/edge-station-test-bundle-<timestamp>.zip

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/output/packages"
TS="$(date +%Y%m%d_%H%M%S)"
PKG_NAME="edge-station-test-bundle-${TS}"
STAGE_DIR="${OUT_DIR}/${PKG_NAME}"
BACKEND_DIR="${STAGE_DIR}/backend_patch"
CLIENT_DIR="${STAGE_DIR}/edge_client"

mkdir -p "${BACKEND_DIR}" "${CLIENT_DIR}/scripts"

copy_backend_file() {
  local rel="$1"
  local src="${ROOT_DIR}/${rel}"
  local dst="${BACKEND_DIR}/${rel}"
  if [[ ! -f "${src}" ]]; then
    echo "[WARN] missing backend file: ${rel}" >&2
    return 0
  fi
  mkdir -p "$(dirname "${dst}")"
  cp "${src}" "${dst}"
}

copy_client_file() {
  local rel="$1"
  local src="${ROOT_DIR}/${rel}"
  local dst="${CLIENT_DIR}/${rel}"
  if [[ ! -f "${src}" ]]; then
    echo "[WARN] missing edge client file: ${rel}" >&2
    return 0
  fi
  mkdir -p "$(dirname "${dst}")"
  cp "${src}" "${dst}"
}

copy_client_dir() {
  local rel="$1"
  local src="${ROOT_DIR}/${rel}"
  local dst="${CLIENT_DIR}/${rel}"
  if [[ ! -d "${src}" ]]; then
    echo "[WARN] missing edge client dir: ${rel}" >&2
    return 0
  fi
  mkdir -p "${dst}"
  cp -R "${src}/." "${dst}/"
}

# --- Backend patch files (sync to MES web test env) ---
BACKEND_FILES=(
  "app_web/templates/motor_qc/base.html"
  "app_web/templates/motor_qc/tasks.html"
  "app_web/templates/motor_qc/review.html"
  "app_web/static/css/motor_qc/styles.css"
  "app_web/static/js/motor_qc/api-client.js"
  "app_web/static/js/motor_qc/tasks.js"
  "app_web/static/js/motor_qc/edge-station-store.js"
  "app_web/static/js/motor_qc/edge-camera-adapter.js"
  "app_web/static/js/motor_qc/edge-button-adapter.js"
  "app_web/static/js/motor_qc/edge-similarity.js"
  "app_web/static/js/motor_qc/edge-uploader.js"
  "app_web/static/js/motor_qc/edge-ui.js"
  "app_web/motor_qc/routes.py"
  "app_web/permission_guard.py"
)

for item in "${BACKEND_FILES[@]}"; do
  copy_backend_file "${item}"
done

# --- Edge client files (run on Windows edge machine) ---
copy_client_file "scripts/edge_local_bridge_stub.py"
copy_client_file "scripts/edge_camera_bridge.py"
copy_client_file "scripts/edge_local_frontend_regression.py"
copy_client_dir "scripts/edge_ui"

mkdir -p "${CLIENT_DIR}/scripts/edge_ui/assets"
EDGE_UI_ASSET_SPECS=(
  "app_web/static/css/motor_qc/styles.css:styles.css"
  "app_web/static/js/motor_qc/api-client.js:api-client.js"
  "app_web/static/js/motor_qc/edge-station-store.js:edge-station-store.js"
  "app_web/static/js/motor_qc/edge-camera-adapter.js:edge-camera-adapter.js"
  "app_web/static/js/motor_qc/edge-button-adapter.js:edge-button-adapter.js"
  "app_web/static/js/motor_qc/edge-similarity.js:edge-similarity.js"
  "app_web/static/js/motor_qc/edge-uploader.js:edge-uploader.js"
  "app_web/static/js/motor_qc/edge-ui.js:edge-ui.js"
)
for spec in "${EDGE_UI_ASSET_SPECS[@]}"; do
  src_rel="${spec%%:*}"
  dst_name="${spec##*:}"
  src_path="${ROOT_DIR}/${src_rel}"
  if [[ ! -f "${src_path}" ]]; then
    echo "[WARN] missing edge UI asset: ${src_rel}" >&2
    continue
  fi
  cp "${src_path}" "${CLIENT_DIR}/scripts/edge_ui/assets/${dst_name}"
done

cat > "${CLIENT_DIR}/requirements-edge-client.txt" <<'REQ'
flask
pillow
opencv-python
requests
REQ

cat > "${CLIENT_DIR}/requirements-edge-regression.txt" <<'REQ'
playwright
REQ

cat > "${CLIENT_DIR}/start_edge_bridge.ps1" <<'PS1'
param(
  [string]$Host = "127.0.0.1",
  [int]$Port = 19091,
  [string]$Source = "mvs",
  [int]$CameraIndex = 0,
  [string]$RtspUrl = "",
  [string]$MvsPythonDir = "",
  [string]$MvsSerial = "",
  [int]$MvsIndex = 0,
  [string]$MesBase = "http://172.16.30.2:8891"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$argsList = @(
  ".\scripts\edge_camera_bridge.py",
  "--host", $Host,
  "--port", $Port,
  "--source", $Source,
  "--camera-index", $CameraIndex,
  "--mvs-python-dir", $MvsPythonDir,
  "--mvs-serial", $MvsSerial,
  "--mvs-index", $MvsIndex,
  "--mes-base", $MesBase
)
if ($RtspUrl -ne "") {
  $argsList += @("--rtsp-url", $RtspUrl)
}
python @argsList
PS1

cat > "${CLIENT_DIR}/run_edge_regression.ps1" <<'PS1'
param(
  [string]$BaseUrl = "http://127.0.0.1:8891",
  [string]$BridgeUrl = "http://127.0.0.1:19091",
  [string]$ProjectId = "柳工3.5T双12叉车",
  [string]$MesUser = "",
  [string]$MesPass = "",
  [string]$MesProtocol = "smb"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($MesUser -ne "") { $env:MES_USER = $MesUser }
if ($MesPass -ne "") { $env:MES_PASS = $MesPass }
$env:MES_PROTOCOL = $MesProtocol

python .\scripts\edge_local_frontend_regression.py `
  --base-url $BaseUrl `
  --bridge-url $BridgeUrl `
  --project-id $ProjectId
PS1

cat > "${CLIENT_DIR}/start_edge_bridge.bat" <<'BAT'
@echo off
setlocal

set "HOST=127.0.0.1"
set "PORT=19091"
set "SOURCE=mvs"
set "CAMERA_INDEX=0"
set "RTSP_URL="
set "MVS_PYTHON_DIR="
set "MVS_SERIAL="
set "MVS_INDEX=0"
set "MES_BASE=http://172.16.30.2:8891"

if not "%~1"=="" set "SOURCE=%~1"
if not "%~2"=="" set "CAMERA_INDEX=%~2"
if /I "%SOURCE%"=="rtsp" if not "%~3"=="" set "RTSP_URL=%~3"
if not "%~4"=="" set "MVS_PYTHON_DIR=%~4"
if not "%~5"=="" set "MVS_SERIAL=%~5"
if not "%~6"=="" set "MVS_INDEX=%~6"
if not "%~7"=="" set "MES_BASE=%~7"

where python >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_BIN=python"
  set "PYTHON_ARGS="
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_BIN=py"
    set "PYTHON_ARGS=-3"
  ) else (
    echo [ERROR] python or py launcher not found in PATH.
    exit /b 1
  )
)

if /I "%SOURCE%"=="rtsp" if "%RTSP_URL%"=="" echo [WARN] SOURCE=rtsp but no RTSP URL provided, bridge may fallback to mock.
if /I "%SOURCE%"=="rtsp" if "%RTSP_URL%"=="" goto :RUN_RTSP_NO_URL
if /I "%SOURCE%"=="rtsp" goto :RUN_RTSP_WITH_URL
goto :RUN_DEFAULT

:RUN_RTSP_NO_URL
call "%PYTHON_BIN%" %PYTHON_ARGS% .\scripts\edge_camera_bridge.py --host %HOST% --port %PORT% --source %SOURCE% --camera-index %CAMERA_INDEX% --mvs-python-dir "%MVS_PYTHON_DIR%" --mvs-serial "%MVS_SERIAL%" --mvs-index %MVS_INDEX% --mes-base "%MES_BASE%"
goto :DONE

:RUN_RTSP_WITH_URL
call "%PYTHON_BIN%" %PYTHON_ARGS% .\scripts\edge_camera_bridge.py --host %HOST% --port %PORT% --source %SOURCE% --camera-index %CAMERA_INDEX% --rtsp-url "%RTSP_URL%" --mvs-python-dir "%MVS_PYTHON_DIR%" --mvs-serial "%MVS_SERIAL%" --mvs-index %MVS_INDEX% --mes-base "%MES_BASE%"
goto :DONE

:RUN_DEFAULT
call "%PYTHON_BIN%" %PYTHON_ARGS% .\scripts\edge_camera_bridge.py --host %HOST% --port %PORT% --source %SOURCE% --camera-index %CAMERA_INDEX% --mvs-python-dir "%MVS_PYTHON_DIR%" --mvs-serial "%MVS_SERIAL%" --mvs-index %MVS_INDEX% --mes-base "%MES_BASE%"

:DONE
endlocal
BAT

cat > "${CLIENT_DIR}/open_edge_ui.bat" <<'BAT'
@echo off
setlocal

set "MES_HOST=172.16.30.2:8891"
set "STATION_ID=S01"
set "EDGE_PROJECT_ID="
set "EDGE_PROCESS_NAME="
set "BRIDGE_URL=http://127.0.0.1:19091"

if not "%~1"=="" set "MES_HOST=%~1"
if not "%~2"=="" set "STATION_ID=%~2"
if not "%~3"=="" set "EDGE_PROJECT_ID=%~3"
if not "%~4"=="" set "EDGE_PROCESS_NAME=%~4"

set "EDGE_URL=http://127.0.0.1:19091/edge-ui"
echo [INFO] EDGE_URL=%EDGE_URL%
start "" "%EDGE_URL%"
endlocal
BAT

cat > "${CLIENT_DIR}/start_edge_station_ui.bat" <<'BAT'
@echo off
setlocal

set "MES_HOST=172.16.30.2:8891"
set "STATION_ID=S01"
set "SOURCE=mvs"
set "CAMERA_INDEX=0"
set "RTSP_URL="
set "EDGE_PROJECT_ID="
set "EDGE_PROCESS_NAME="
set "MVS_PYTHON_DIR="
set "MVS_SERIAL="
set "MVS_INDEX=0"

if not "%~1"=="" set "MES_HOST=%~1"
if not "%~2"=="" set "STATION_ID=%~2"
if not "%~3"=="" set "SOURCE=%~3"
if not "%~4"=="" set "CAMERA_INDEX=%~4"
if not "%~5"=="" set "RTSP_URL=%~5"
if not "%~6"=="" set "EDGE_PROJECT_ID=%~6"
if not "%~7"=="" set "EDGE_PROCESS_NAME=%~7"
if not "%~8"=="" set "MVS_PYTHON_DIR=%~8"
if not "%~9"=="" set "MVS_SERIAL=%~9"

start "Edge Camera Bridge" cmd /k call .\start_edge_bridge.bat "%SOURCE%" "%CAMERA_INDEX%" "%RTSP_URL%" "%MVS_PYTHON_DIR%" "%MVS_SERIAL%" "%MVS_INDEX%" "%MES_HOST%"
timeout /t 2 >nul
call .\open_edge_ui.bat "%MES_HOST%" "%STATION_ID%" "%EDGE_PROJECT_ID%" "%EDGE_PROCESS_NAME%"
endlocal
BAT

cat > "${CLIENT_DIR}/start_edge_one_click.bat" <<'BAT'
@echo off
setlocal

set "MES_HOST=172.16.30.2:8891"
set "STATION_ID=S01"
set "SOURCE=mvs"
set "CAMERA_INDEX=0"
set "RTSP_URL="
set "EDGE_PROJECT_ID="
set "EDGE_PROCESS_NAME="
set "MVS_PYTHON_DIR="
set "MVS_SERIAL="
set "MVS_INDEX=0"

if not "%~1"=="" set "MES_HOST=%~1"
if not "%~2"=="" set "STATION_ID=%~2"
if not "%~3"=="" set "SOURCE=%~3"
if not "%~4"=="" set "CAMERA_INDEX=%~4"
if not "%~5"=="" set "RTSP_URL=%~5"
if not "%~6"=="" set "EDGE_PROJECT_ID=%~6"
if not "%~7"=="" set "EDGE_PROCESS_NAME=%~7"
if not "%~8"=="" set "MVS_PYTHON_DIR=%~8"
if not "%~9"=="" set "MVS_SERIAL=%~9"

where python >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_BIN=python"
  set "PYTHON_ARGS="
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON_BIN=py"
    set "PYTHON_ARGS=-3"
  ) else (
    echo [ERROR] python or py launcher not found in PATH.
    pause
    exit /b 1
  )
)

echo [INFO] Checking edge dependencies...
if /I "%SOURCE%"=="mvs" (
  call "%PYTHON_BIN%" %PYTHON_ARGS% -c "import flask,PIL,requests" >nul 2>nul
) else (
  call "%PYTHON_BIN%" %PYTHON_ARGS% -c "import flask,PIL,cv2,requests" >nul 2>nul
)
if errorlevel 1 (
  echo [INFO] Installing edge dependencies...
  call "%PYTHON_BIN%" %PYTHON_ARGS% -m pip install -r .\requirements-edge-client.txt
  if errorlevel 1 (
    echo [ERROR] dependency installation failed.
    pause
    exit /b 1
  )
)

if /I not "%SOURCE%"=="mvs" goto :SKIP_MVS_PATH_DETECT
set "MVS_PATH_MAIN=C:\Program Files\MVS\Development\Samples\Python\MvImport\MvCameraControl_class.py"
set "MVS_PATH_X86=C:\Program Files (x86)\MVS\Development\Samples\Python\MvImport\MvCameraControl_class.py"
if "%MVS_PYTHON_DIR%"=="" if exist "%MVS_PATH_MAIN%" set "MVS_PYTHON_DIR=C:\Program Files\MVS\Development\Samples\Python\MvImport"
if "%MVS_PYTHON_DIR%"=="" if exist "%MVS_PATH_X86%" set "MVS_PYTHON_DIR=C:\Program Files (x86)\MVS\Development\Samples\Python\MvImport"
if "%MVS_PYTHON_DIR%"=="" echo [WARN] MVS Python import path not auto-detected. Bridge will still try default paths.
if not "%MVS_PYTHON_DIR%"=="" echo [INFO] MVS_PYTHON_DIR=%MVS_PYTHON_DIR%
:SKIP_MVS_PATH_DETECT

echo [INFO] Starting edge station UI...
call .\start_edge_station_ui.bat "%MES_HOST%" "%STATION_ID%" "%SOURCE%" "%CAMERA_INDEX%" "%RTSP_URL%" "%EDGE_PROJECT_ID%" "%EDGE_PROCESS_NAME%" "%MVS_PYTHON_DIR%" "%MVS_SERIAL%" "%MVS_INDEX%"
endlocal
BAT

cat > "${CLIENT_DIR}/README_EDGE_CLIENT.md" <<'MD'
# Edge Client Test Pack (Windows)

## 0) Double-click startup (recommended)
Just double-click:
```bat
start_edge_one_click.bat
```
- It auto-checks/install dependencies (first run), starts bridge, then opens UI.

## 1) Manual install (optional)
```powershell
pip install -r .\requirements-edge-client.txt
```

## 2) Start edge camera bridge
### Preferred: BAT (no PowerShell policy issue)
```bat
start_edge_bridge.bat mvs
```
- `mvs` uses HikRobot MVS SDK (industrial camera).
- If your Hik camera provides RTSP stream instead:
```bat
start_edge_bridge.bat rtsp 0 "rtsp://<camera-ip>/Streaming/Channels/101"
```

### Alternative: PowerShell (bypass policy)
```powershell
powershell -ExecutionPolicy Bypass -File .\start_edge_bridge.ps1
```

### Camera health check (recommended)
Open in browser:
- `http://127.0.0.1:19091/api/health`

Expected for real camera:
- `effective_source` is `mvs` or `rtsp`
- `capture_opened` is `true`
- `fail_count` stays low

Preview test:
- `http://127.0.0.1:19091/api/camera/frame?station_id=S01`

## 3) Open complete edge UI page
### One-click (start bridge + open UI)
```bat
start_edge_station_ui.bat 172.16.30.2:8891 S01 mvs
```

### Open UI only
```bat
open_edge_ui.bat 172.16.30.2:8891 S01
```
- Opens local page: `http://127.0.0.1:19091/edge-ui` (no direct MES page access).

UI opens in edge mode with these defaults:
- Camera source: `local_bridge`
- Button source: `local_bridge`
- Bridge URL: `http://127.0.0.1:19091`
- MES access mode: API proxy (requires page-top login once)
- If account has no `web:run_qc`: page auto-switches to manual project/process + mobile QC analyze mode
- Project/process: configure in page, then click "保存配置"

Optional prefill project/process on launch:
```bat
open_edge_ui.bat 172.16.30.2:8891 S01 "柳工3.5T双12叉车" "电容板固定"
```

Optional specify MVS python path/serial:
```bat
start_edge_one_click.bat 172.16.30.2:8891 S01 mvs 0 "" "" "" "C:\Program Files\MVS\Development\Samples\Python\MvImport" "<CAM_SERIAL>" 0
```

Then in page:
- 顶部输入 MES 地址/账号/密码，点击“登录 MES”
- 扫码开始
- 按钮结束（可通过 bridge 的 `/api/button/press` 或真实按钮接入）

## 4) Optional automated regression
```powershell
pip install -r .\requirements-edge-regression.txt
playwright install webkit

powershell -ExecutionPolicy Bypass -File .\run_edge_regression.ps1 `
  -BaseUrl "http://127.0.0.1:8891" `
  -BridgeUrl "http://127.0.0.1:19091" `
  -ProjectId "柳工3.5T双12叉车" `
  -MesUser "<账号>" `
  -MesPass "<密码>"
```

Regression report path:
- `output/playwright/edge-local-regression-*/report.json`
MD

cat > "${STAGE_DIR}/README.md" <<'MD'
# Edge Station Test Bundle

This package contains:

1. `backend_patch/`
   - Motor QC edge-mode frontend + route files to sync into MES web test environment.

2. `edge_client/`
   - Windows edge-machine camera bridge + full edge UI launchers + regression script.

## Suggested test sequence
1. Sync `backend_patch/*` to MES **test** env code path (same relative paths), restart test mesapp.
2. Copy `edge_client/*` to edge machine.
3. Double-click `start_edge_one_click.bat` on edge machine.
4. Execute manual flow (scan start / button end), then run optional regression script.
MD

cat > "${STAGE_DIR}/MANIFEST.txt" <<EOF
package=${PKG_NAME}
built_at=$(date +"%Y-%m-%d %H:%M:%S %z")
source_root=${ROOT_DIR}
backend_files=${#BACKEND_FILES[@]}
EOF

if ! command -v zip >/dev/null 2>&1; then
  echo "[ERROR] zip command not found"
  exit 1
fi

(
  cd "${OUT_DIR}"
  zip -qr "${PKG_NAME}.zip" "${PKG_NAME}"
)

echo "BUNDLE_DIR=${STAGE_DIR}"
echo "BUNDLE_ZIP=${OUT_DIR}/${PKG_NAME}.zip"
