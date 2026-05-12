#!/bin/bash
# NAS 测试环境部署脚本 (在 MES 目录内创建 test 子目录)
# 目标: 在 /volume2/MES/test 创建测试环境，共享生产数据

set -e  # 遇到错误立即退出

# NAS 连接信息
NAS_HOST="172.16.30.2"
NAS_PORT="30001"
NAS_USER="panovation"
NAS_PASSWORD="Clt2020clt"

# 路径配置
MES_DIR="/volume2/MES"
TEST_DIR="/volume2/MES/test"
PROD_APP_DIR="/volume2/MES/app_web"
DATA_DIR="/volume2/MES/data"  # 共享生产数据

echo "========================================="
echo "NAS 测试环境部署脚本"
echo "========================================="
echo ""
echo "MES 根目录: ${MES_DIR}"
echo "测试环境: ${TEST_DIR}"
echo "共享数据目录: ${DATA_DIR}"
echo ""

# 步骤 1: 检查并停止生产环境
echo "[步骤 1/6] 检查并停止生产环境..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << 'EOF'
echo "查找 mesapp.py 进程..."
PID=$(ps aux | grep "python3 mesapp.py" | grep -v grep | grep -v "test" | awk '{print $2}')
if [ -n "$PID" ]; then
    echo "找到生产环境进程 PID: $PID，正在停止..."
    kill $PID
    sleep 2
    # 确认进程已停止
    if ps -p $PID > /dev/null 2>&1; then
        echo "进程未停止，强制终止..."
        kill -9 $PID
    fi
    echo "✓ 生产环境已停止"
else
    echo "✓ 生产环境未运行"
fi
EOF

# 步骤 2: 创建测试环境目录结构
echo ""
echo "[步骤 2/6] 创建测试环境目录..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
echo "创建测试环境目录: ${TEST_DIR}"
mkdir -p ${TEST_DIR}
mkdir -p ${TEST_DIR}/logs
mkdir -p ${DATA_DIR}/thumbnails  # 在共享数据目录创建缩略图目录

echo "✓ 测试环境目录已创建"
EOF

# 步骤 3: 打包本地代码
echo ""
echo "[步骤 3/6] 打包本地代码..."
cd /Users/mini/QRTestScanner-clean
tar -czf /tmp/mes_test_deploy.tar.gz \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='.gradle' \
    --exclude='build' \
    --exclude='uploads' \
    --exclude='*.db' \
    --exclude='data' \
    app_web/ \
    scripts/

echo "✓ 代码打包完成: /tmp/mes_test_deploy.tar.gz"
ls -lh /tmp/mes_test_deploy.tar.gz

# 步骤 4: 上传代码到 NAS
echo ""
echo "[步骤 4/6] 上传代码到 NAS..."
sshpass -p "${NAS_PASSWORD}" scp -P ${NAS_PORT} \
    /tmp/mes_test_deploy.tar.gz \
    ${NAS_USER}@${NAS_HOST}:${TEST_DIR}/

echo "✓ 代码上传完成"

# 步骤 5: 解压并配置测试环境
echo ""
echo "[步骤 5/6] 解压并配置测试环境..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
cd ${TEST_DIR}

echo "解压代码..."
tar -xzf mes_test_deploy.tar.gz
rm mes_test_deploy.tar.gz

echo "复制生产环境配置..."
if [ -f ${PROD_APP_DIR}/webdav_config.json ]; then
    cp ${PROD_APP_DIR}/webdav_config.json ${TEST_DIR}/app_web/
    echo "✓ 已复制 webdav_config.json"
fi

echo "设置权限..."
chmod +x ${TEST_DIR}/app_web/mesapp.py

echo "✓ 测试环境配置完成"
EOF

# 步骤 6: 创建测试环境启动和停止脚本
echo ""
echo "[步骤 6/6] 创建启动和停止脚本..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << 'OUTER_EOF'

# 创建启动脚本
cat > /volume2/MES/test/start_test.sh << 'EOF'
#!/bin/bash
# 测试环境启动脚本

cd /volume2/MES/test/app_web

# 设置环境变量（使用共享数据目录）
export FLASK_ENV=development
export DATA_DIR=/volume2/MES/data
export REDIS_HOST=localhost
export REDIS_PORT=6379

# 启动应用（使用端口 5001）
echo "========================================="
echo "启动测试环境..."
echo "========================================="
echo "数据目录: /volume2/MES/data (共享生产数据)"
echo "访问地址: http://172.16.30.2:5001"
echo "日志文件: /volume2/MES/test/logs/app.log"
echo ""

python3 mesapp.py --port 5001 > /volume2/MES/test/logs/app.log 2>&1 &

PID=$!
echo "✓ 测试环境已启动"
echo "PID: $PID"
echo ""
echo "查看日志: tail -f /volume2/MES/test/logs/app.log"
echo "停止服务: ./stop_test.sh"
EOF

# 创建停止脚本
cat > /volume2/MES/test/stop_test.sh << 'EOF'
#!/bin/bash
# 测试环境停止脚本

echo "停止测试环境..."
PID=$(ps aux | grep "python3 mesapp.py" | grep "5001" | grep -v grep | awk '{print $2}')

if [ -n "$PID" ]; then
    echo "找到测试环境进程 PID: $PID"
    kill $PID
    sleep 2

    # 确认进程已停止
    if ps -p $PID > /dev/null 2>&1; then
        echo "进程未停止，强制终止..."
        kill -9 $PID
    fi

    echo "✓ 测试环境已停止"
else
    echo "测试环境未运行"
fi
EOF

# 创建生产环境启动脚本
cat > /volume2/MES/start_prod.sh << 'EOF'
#!/bin/bash
# 生产环境启动脚本

cd /volume2/MES/app_web

echo "========================================="
echo "启动生产环境..."
echo "========================================="
echo "访问地址: http://172.16.30.2:5000"
echo ""

python3 mesapp.py > /volume2/MES/logs/app.log 2>&1 &

PID=$!
echo "✓ 生产环境已启动"
echo "PID: $PID"
EOF

# 创建生产环境停止脚本
cat > /volume2/MES/stop_prod.sh << 'EOF'
#!/bin/bash
# 生产环境停止脚本

echo "停止生产环境..."
PID=$(ps aux | grep "python3 mesapp.py" | grep -v "5001" | grep -v grep | grep -v "test" | awk '{print $2}')

if [ -n "$PID" ]; then
    echo "找到生产环境进程 PID: $PID"
    kill $PID
    sleep 2

    # 确认进程已停止
    if ps -p $PID > /dev/null 2>&1; then
        echo "进程未停止，强制终止..."
        kill -9 $PID
    fi

    echo "✓ 生产环境已停止"
else
    echo "生产环境未运行"
fi
EOF

# 设置执行权限
chmod +x /volume2/MES/test/start_test.sh
chmod +x /volume2/MES/test/stop_test.sh
chmod +x /volume2/MES/start_prod.sh
chmod +x /volume2/MES/stop_prod.sh

echo "✓ 启动和停止脚本已创建"
OUTER_EOF

echo ""
echo "========================================="
echo "✓ 部署完成！"
echo "========================================="
echo ""
echo "目录结构:"
echo "/volume2/MES/"
echo "├── app_web/          # 生产环境代码"
echo "├── data/             # 共享数据目录"
echo "│   ├── *.db         # 数据库文件"
echo "│   └── thumbnails/  # 缩略图缓存"
echo "├── test/            # 测试环境"
echo "│   ├── app_web/     # 测试代码（新版本）"
echo "│   └── logs/        # 测试日志"
echo "├── start_prod.sh    # 启动生产环境"
echo "├── stop_prod.sh     # 停止生产环境"
echo "└── logs/            # 生产日志"
echo ""
echo "下一步操作:"
echo ""
echo "1. SSH 登录 NAS:"
echo "   ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST}"
echo ""
echo "2. 启动测试环境:"
echo "   cd /volume2/MES/test"
echo "   ./start_test.sh"
echo ""
echo "3. 查看测试日志:"
echo "   tail -f /volume2/MES/test/logs/app.log"
echo ""
echo "4. 访问测试环境:"
echo "   http://172.16.30.2:5001"
echo ""
echo "5. 停止测试环境:"
echo "   cd /volume2/MES/test"
echo "   ./stop_test.sh"
echo ""
echo "6. 恢复生产环境:"
echo "   cd /volume2/MES"
echo "   ./start_prod.sh"
echo ""
echo "注意: 测试环境和生产环境共享 /volume2/MES/data 数据目录"
echo ""
