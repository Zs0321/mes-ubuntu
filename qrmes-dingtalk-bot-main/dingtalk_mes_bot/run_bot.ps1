$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $root
$python = Join-Path $env:USERPROFILE "qrmes\.venv\bin\python"

Push-Location $repoRoot
try {
  if ($env:DINGTALK_BOT_MODE -eq "http") {
    & $python -m dingtalk_mes_bot.bot_app
  } else {
    & $python -m dingtalk_mes_bot.stream_app
  }
}
finally {
  Pop-Location
}
