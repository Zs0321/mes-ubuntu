# 自动更新权限配置文件 (Windows)
#
# 用途：定期从数据库生成权限配置文件供 WebDAV 用户使用
# 建议：添加到 Windows 任务计划程序每分钟执行一次

# 配置
$ScriptDir = "F:\MES\app_web"
$OutputDir = "F:\MES\files\config"
$Python = "python"
$LogFile = "F:\MES\logs\permissions_update.log"

# 确保日志目录存在
$LogDir = Split-Path -Parent $LogFile
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# 记录时间
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $LogFile -Value "[$Timestamp] Starting permissions file update..."

# 切换到脚本目录
Set-Location $ScriptDir

# 执行生成脚本
try {
    & $Python generate_permissions_file.py $OutputDir 2>&1 | Add-Content -Path $LogFile
    
    if ($LASTEXITCODE -eq 0) {
        $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $LogFile -Value "[$Timestamp] Permissions file updated successfully"
    } else {
        $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $LogFile -Value "[$Timestamp] ERROR: Failed to update permissions file (Exit code: $LASTEXITCODE)"
        exit 1
    }
} catch {
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$Timestamp] ERROR: Exception occurred: $_"
    exit 1
}
