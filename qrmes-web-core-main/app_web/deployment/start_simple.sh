#!/bin/bash

echo "=========================================="
echo "简单启动脚本（禁用权限API）"
echo "=========================================="

cd /volume2/MES/app_web

# 1. 停止旧进程
echo "1. 停止旧进程..."
pkill -9 -f "python.*mesapp.py" 2>/dev/null
sleep 2

# 2. 清除缓存
echo "2. 清除Python缓存..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

# 3. 启动应用
echo ""
echo "3. 启动应用..."
echo "=========================================="
python3 mesapp.py
