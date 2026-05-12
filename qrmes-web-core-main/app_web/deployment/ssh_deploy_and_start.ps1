#!/usr/bin/env pwsh
# SSH 自动部署和启动脚本
# 用于连接到远程服务器并启动 Python 应用

# 服务器配置
$SSH_HOST = "172.16.30.2"
$SSH_PORT = "30001"
$SSH_USER = "panovation"
$SSH_PASS = "Clt2020clt"
$REMOTE_APP_DIR = "/volume1/web/QRMES"  # 根据实际路径调整
$PYTHON_CMD = "python3"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SSH 自动部署和启动脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "目标服务器: $SSH_HOST:$SSH_PORT" -ForegroundColor Yellow
Write-Host "用户: $SSH_USER" -ForegroundColor Yellow
Write-Host ""

# 检查是否安装了 plink (PuTTY)
$plinkPath = Get-Command plink -ErrorAction SilentlyContinue
if (-not $plinkPath) {
    Write-Host "错误: 未找到 plink 命令" -ForegroundColor Red
    Write-Host "请安装 PuTTY 或使用 OpenSSH" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "安装方法:" -ForegroundColor Yellow
    Write-Host "1. 下载 PuTTY: https://www.putty.org/" -ForegroundColor Yellow
    Write-Host "2. 或使用 OpenSSH (Windows 10+): 设置 -> 应用 -> 可选功能 -> OpenSSH 客户端" -ForegroundColor Yellow
    exit 1
}

Write-Host "步骤 1: 连接到服务器..." -ForegroundColor Green

# 使用 plink 执行远程命令
# 注意: 首次连接需要手动确认主机密钥
$commands = @"
cd $REMOTE_APP_DIR
echo '当前目录:'
pwd
echo ''
echo '检查 Python 版本:'
$PYTHON_CMD --version
echo ''
echo '检查应用文件:'
ls -la mesapp.py
echo ''
echo '停止旧进程...'
pkill -f 'python.*mesapp.py' || echo '没有运行中的进程'
echo ''
echo '启动应用...'
nohup $PYTHON_CMD mesapp.py > logs/mesapp.log 2>&1 &
echo ''
echo '等待应用启动...'
sleep 3
echo ''
echo '检查进程状态:'
ps aux | grep 'python.*mesapp.py' | grep -v grep || echo '进程未找到'
echo ''
echo '检查日志 (最后 20 行):'
tail -n 20 logs/mesapp.log
echo ''
echo '完成!'
"@

# 执行远程命令
Write-Host "步骤 2: 执行远程命令..." -ForegroundColor Green
Write-Host ""

# 使用 plink 连接并执行命令
# -pw: 密码
# -P: 端口
# -batch: 非交互模式
echo $SSH_PASS | plink -ssh -P $SSH_PORT -l $SSH_USER -pw $SSH_PASS -batch $SSH_HOST $commands

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "部署和启动完成!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "应用地址: http://$SSH_HOST:5000" -ForegroundColor Cyan
    Write-Host "照片管理: http://$SSH_HOST:5000/admin/photos" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "查看日志:" -ForegroundColor Yellow
    Write-Host "  ssh -p $SSH_PORT $SSH_USER@$SSH_HOST" -ForegroundColor Gray
    Write-Host "  tail -f $REMOTE_APP_DIR/logs/mesapp.log" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "部署失败!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "请检查:" -ForegroundColor Yellow
    Write-Host "1. SSH 连接是否正常" -ForegroundColor Yellow
    Write-Host "2. 服务器路径是否正确" -ForegroundColor Yellow
    Write-Host "3. Python 是否已安装" -ForegroundColor Yellow
}
