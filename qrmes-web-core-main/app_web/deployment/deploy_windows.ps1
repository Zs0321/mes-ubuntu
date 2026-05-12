# QRTestScanner Windows Server 2016 部署脚本
# 自动化部署流程

param(
    [string]$Action = "install"  # install, update, restart, status
)

$ErrorActionPreference = "Stop"
$AppName = "QRTestScannerMES"
$AppPath = "F:\GitHub\hours\QRTestScanner\app_web"
$NssmPath = "C:\nssm\win64\nssm.exe"

Write-Host "=" * 60
Write-Host "QRTestScanner Windows Server 部署脚本"
Write-Host "=" * 60
Write-Host ""

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-Service {
    Write-Host "[1/8] 检查管理员权限..."
    if (-not (Test-Administrator)) {
        Write-Error "需要管理员权限运行此脚本"
        exit 1
    }
    
    Write-Host "[2/8] 检查Python安装..."
    try {
        $pythonVersion = python --version
        Write-Host "  ✓ $pythonVersion"
    } catch {
        Write-Error "Python未安装或不在PATH中"
        exit 1
    }
    
    Write-Host "[3/8] 安装Python依赖..."
    Set-Location $AppPath
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    pip install waitress
    Write-Host "  ✓ 依赖安装完成"
    
    Write-Host "[4/8] 创建日志目录..."
    $LogPath = Join-Path $AppPath "logs"
    if (-not (Test-Path $LogPath)) {
        New-Item -ItemType Directory -Path $LogPath -Force | Out-Null
    }
    Write-Host "  ✓ 日志目录: $LogPath"
    
    Write-Host "[5/8] 检查NSSM..."
    if (-not (Test-Path $NssmPath)) {
        Write-Error "NSSM未找到，请从 https://nssm.cc/download 下载并解压到 C:\nssm"
        exit 1
    }
    Write-Host "  ✓ NSSM已安装"
    
    Write-Host "[6/8] 创建Windows服务..."
    $PythonExe = (Get-Command python).Source
    $StartScript = Join-Path $AppPath "start_waitress.py"
    
    # 检查服务是否已存在
    $existingService = Get-Service -Name $AppName -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Host "  ⚠ 服务已存在，先删除旧服务..."
        Stop-Service $AppName -ErrorAction SilentlyContinue
        & $NssmPath remove $AppName confirm
        Start-Sleep -Seconds 2
    }
    
    # 安装服务
    & $NssmPath install $AppName $PythonExe $StartScript
    & $NssmPath set $AppName AppDirectory $AppPath
    & $NssmPath set $AppName DisplayName "QRTestScanner MES Application"
    & $NssmPath set $AppName Description "QRTestScanner Manufacturing Execution System Web Backend"
    & $NssmPath set $AppName Start SERVICE_AUTO_START
    & $NssmPath set $AppName AppStdout "$AppPath\logs\service_stdout.log"
    & $NssmPath set $AppName AppStderr "$AppPath\logs\service_stderr.log"
    & $NssmPath set $AppName AppRotateFiles 1
    & $NssmPath set $AppName AppRotateBytes 10485760
    
    Write-Host "  ✓ 服务创建完成"
    
    Write-Host "[7/8] 启动服务..."
    Start-Service $AppName
    Start-Sleep -Seconds 3
    
    Write-Host "[8/8] 验证服务状态..."
    $service = Get-Service $AppName
    if ($service.Status -eq 'Running') {
        Write-Host "  ✓ 服务运行正常"
    } else {
        Write-Error "服务启动失败，状态: $($service.Status)"
        exit 1
    }
    
    Write-Host ""
    Write-Host "=" * 60
    Write-Host "部署完成！"
    Write-Host "=" * 60
    Write-Host "服务名称: $AppName"
    Write-Host "访问地址: http://localhost:8891"
    Write-Host "健康检查: http://localhost:8891/api/h2/health"
    Write-Host ""
    Write-Host "管理命令:"
    Write-Host "  启动服务: Start-Service $AppName"
    Write-Host "  停止服务: Stop-Service $AppName"
    Write-Host "  重启服务: Restart-Service $AppName"
    Write-Host "  查看状态: Get-Service $AppName"
    Write-Host "  查看日志: Get-Content $AppPath\logs\service_stdout.log -Tail 20"
    Write-Host ""
}

function Update-Application {
    Write-Host "[1/4] 停止服务..."
    Stop-Service $AppName -ErrorAction SilentlyContinue
    Write-Host "  ✓ 服务已停止"
    
    Write-Host "[2/4] 更新代码..."
    Set-Location (Split-Path $AppPath -Parent)
    git pull
    Write-Host "  ✓ 代码已更新"
    
    Write-Host "[3/4] 更新依赖..."
    Set-Location $AppPath
    pip install -r requirements.txt --upgrade
    Write-Host "  ✓ 依赖已更新"
    
    Write-Host "[4/4] 启动服务..."
    Start-Service $AppName
    Start-Sleep -Seconds 3
    Write-Host "  ✓ 服务已启动"
    
    Write-Host ""
    Write-Host "更新完成！"
}

function Restart-Application {
    Write-Host "重启服务..."
    Restart-Service $AppName
    Start-Sleep -Seconds 3
    $service = Get-Service $AppName
    Write-Host "服务状态: $($service.Status)"
}

function Get-ApplicationStatus {
    Write-Host "服务状态信息:"
    Write-Host "=" * 60
    
    $service = Get-Service $AppName -ErrorAction SilentlyContinue
    if ($service) {
        Write-Host "服务名称: $($service.Name)"
        Write-Host "显示名称: $($service.DisplayName)"
        Write-Host "运行状态: $($service.Status)"
        Write-Host "启动类型: $($service.StartType)"
    } else {
        Write-Host "服务未安装"
        return
    }
    
    Write-Host ""
    Write-Host "最近日志 (最后20行):"
    Write-Host "-" * 60
    $logFile = Join-Path $AppPath "logs\service_stdout.log"
    if (Test-Path $logFile) {
        Get-Content $logFile -Tail 20
    } else {
        Write-Host "日志文件不存在"
    }
}

# 主逻辑
switch ($Action.ToLower()) {
    "install" { Install-Service }
    "update" { Update-Application }
    "restart" { Restart-Application }
    "status" { Get-ApplicationStatus }
    default {
        Write-Host "未知操作: $Action"
        Write-Host "可用操作: install, update, restart, status"
        Write-Host ""
        Write-Host "使用示例:"
        Write-Host "  .\deploy_windows.ps1 -Action install"
        Write-Host "  .\deploy_windows.ps1 -Action update"
        Write-Host "  .\deploy_windows.ps1 -Action restart"
        Write-Host "  .\deploy_windows.ps1 -Action status"
    }
}
