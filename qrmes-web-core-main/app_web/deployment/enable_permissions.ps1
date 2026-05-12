# 启用权限管理系统的 PowerShell 脚本

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "启用权限管理系统" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 检查Python环境
$pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Host "错误: 未找到 Python" -ForegroundColor Red
    exit 1
}

$python = $pythonCmd.Name

# 运行初始化脚本
Write-Host ""
Write-Host "步骤 1: 初始化权限数据库" -ForegroundColor Yellow
Write-Host "------------------------------------------"

& $python init_permission_db.py $args

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "✗ 数据库初始化失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "步骤 2: 重启服务" -ForegroundColor Yellow
Write-Host "------------------------------------------"
Write-Host "请手动重启 mesapp.py 服务:"
Write-Host "  1. 按 Ctrl+C 停止当前服务"
Write-Host "  2. 运行: python mesapp.py"
Write-Host ""

Write-Host "步骤 3: 登录系统" -ForegroundColor Yellow
Write-Host "------------------------------------------"
Write-Host "使用您的群晖NAS账号登录系统"
Write-Host "管理员账户将自动获得完整权限"
Write-Host ""

Write-Host "==========================================" -ForegroundColor Green
Write-Host "✓ 权限系统启用完成" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
