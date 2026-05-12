#!/usr/bin/env pwsh
# SSH 自动启动应用脚本（使用 OpenSSH）
# 适用于 Windows 10+ 自带的 OpenSSH 客户端

# 服务器配置
$SSH_HOST = "172.16.30.2"
$SSH_PORT = "30001"
$SSH_USER = "panovation"
$SSH_PASS = "Clt2020clt"
$REMOTE_APP_DIR = "/volume1/web/QRMES"  # 根据实际路径调整
$PYTHON_CMD = "python3"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SSH 自动启动应用脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "目标服务器: $SSH_HOST:$SSH_PORT" -ForegroundColor Yellow
Write-Host "用户: $SSH_USER" -ForegroundColor Yellow
Write-Host "应用目录: $REMOTE_APP_DIR" -ForegroundColor Yellow
Write-Host ""

# 检查 SSH 命令是否可用
$sshCmd = Get-Command ssh -ErrorAction SilentlyContinue
if (-not $sshCmd) {
    Write-Host "错误: 未找到 ssh 命令" -ForegroundColor Red
    Write-Host ""
    Write-Host "请安装 OpenSSH 客户端:" -ForegroundColor Yellow
    Write-Host "设置 -> 应用 -> 可选功能 -> 添加功能 -> OpenSSH 客户端" -ForegroundColor Yellow
    exit 1
}

Write-Host "步骤 1: 准备 SSH 连接..." -ForegroundColor Green

# 创建临时脚本文件
$tempScript = [System.IO.Path]::GetTempFileName()
$tempScript = $tempScript -replace '\.tmp$', '.sh'

$scriptContent = @"
#!/bin/bash
cd $REMOTE_APP_DIR || exit 1

echo '========================================='
echo '当前目录:'
pwd
echo ''

echo '检查 Python 版本:'
$PYTHON_CMD --version
echo ''

echo '检查应用文件:'
if [ -f mesapp.py ]; then
    echo '✓ mesapp.py 存在'
else
    echo '✗ mesapp.py 不存在'
    exit 1
fi
echo ''

echo '停止旧进程...'
pkill -f 'python.*mesapp.py' && echo '✓ 旧进程已停止' || echo '没有运行中的进程'
sleep 1
echo ''

echo '创建日志目录...'
mkdir -p logs
echo ''

echo '启动应用...'
nohup $PYTHON_CMD mesapp.py > logs/mesapp.log 2>&1 &
APP_PID=`$!`
echo "✓ 应用已启动 (PID: `$APP_PID)"
echo ''

echo '等待应用启动...'
sleep 3
echo ''

echo '检查进程状态:'
if ps -p `$APP_PID > /dev/null 2>&1; then
    echo "✓ 进程运行中 (PID: `$APP_PID)"
else
    echo '✗ 进程未运行'
fi
echo ''

echo '检查端口监听:'
netstat -tuln | grep ':5000' && echo '✓ 端口 5000 已监听' || echo '⚠ 端口 5000 未监听'
echo ''

echo '最新日志 (最后 30 行):'
echo '========================================='
tail -n 30 logs/mesapp.log
echo '========================================='
echo ''

echo '✓ 部署完成!'
echo ''
echo '访问地址:'
echo '  主页: http://$SSH_HOST:5000'
echo '  照片管理: http://$SSH_HOST:5000/admin/photos'
echo ''
echo '查看实时日志:'
echo '  tail -f $REMOTE_APP_DIR/logs/mesapp.log'
"@

# 保存脚本到临时文件
$scriptContent | Out-File -FilePath $tempScript -Encoding UTF8

Write-Host "步骤 2: 上传启动脚本..." -ForegroundColor Green

# 使用 scp 上传脚本
$env:SSHPASS = $SSH_PASS
scp -P $SSH_PORT -o StrictHostKeyChecking=no $tempScript "${SSH_USER}@${SSH_HOST}:/tmp/start_app.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Host "警告: scp 上传失败，尝试使用 ssh 直接执行..." -ForegroundColor Yellow
}

Write-Host "步骤 3: 执行启动脚本..." -ForegroundColor Green
Write-Host ""

# 使用 sshpass 或直接 ssh 执行
# 注意: Windows 上可能需要手动输入密码
ssh -p $SSH_PORT -o StrictHostKeyChecking=no "${SSH_USER}@${SSH_HOST}" "bash /tmp/start_app.sh || bash -c '$scriptContent'"

# 清理临时文件
Remove-Item $tempScript -ErrorAction SilentlyContinue

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "✓ 部署和启动完成!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "应用地址: http://$SSH_HOST:5000" -ForegroundColor Cyan
    Write-Host "照片管理: http://$SSH_HOST:5000/admin/photos" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "查看日志:" -ForegroundColor Yellow
    Write-Host "  ssh -p $SSH_PORT $SSH_USER@$SSH_HOST" -ForegroundColor Gray
    Write-Host "  tail -f $REMOTE_APP_DIR/logs/mesapp.log" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "✗ 部署失败!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "请检查:" -ForegroundColor Yellow
    Write-Host "1. SSH 连接是否正常" -ForegroundColor Yellow
    Write-Host "2. 服务器路径是否正确: $REMOTE_APP_DIR" -ForegroundColor Yellow
    Write-Host "3. Python 是否已安装" -ForegroundColor Yellow
    Write-Host "4. 是否有执行权限" -ForegroundColor Yellow
}
