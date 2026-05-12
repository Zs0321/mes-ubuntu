#!/bin/bash
# NAS 测试环境部署脚本
# 目标: 在 NAS 上创建测试环境，不影响生产环境

set -e  # 遇到错误立即退出

# NAS 连接信息
NAS_HOST="172.16.30.2"
NAS_PORT="30001"
NAS_USER="panovation"
NAS_PASSWORD="Clt2020clt"

# 路径配置
PROD_DIR="/volume2/MES"
TEST_DIR="/volume2/MES_TEST"
BACKUP_DIR="/volume2/MES_BACKUP"

echo "========================================="
echo "NAS 测试环境部署脚本"
echo "========================================="
echo ""
echo "生产环境: ${PROD_DIR}"
echo "测试环境: ${TEST_DIR}"
echo "备份目录: ${BACKUP_DIR}"
echo ""

# 步骤 1: 检查生产环境进程
echo "[步骤 1/8] 检查生产环境进程..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << 'EOF'
echo "查找 mesapp.py 进程..."
ps aux | grep "python3 mesapp.py" | grep -v grep || echo "未找到运行中的进程"
EOF

# 步骤 2: 停止生产环境（如果运行中）
echo ""
echo "[步骤 2/8] 停止生产环境..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << 'EOF'
# 查找并停止 mesapp.py 进程
PID=$(ps aux | grep "python3 mesapp.py" | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
    echo "找到进程 PID: $PID，正在停止..."
    kill $PID
    sleep 2
    # 确认进程已停止
    if ps -p $PID > /dev/null 2>&1; then
        echo "进程未停止，强制终止..."
        kill -9 $PID
    fi
    echo "生产环境已停止"
else
    echo "生产环境未运行"
fi
EOF

# 步骤 3: 备份生产环境
echo ""
echo "[步骤 3/8] 备份生产环境..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
TIMESTAMP=\$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/MES_backup_\${TIMESTAMP}"

echo "创建备份目录: \${BACKUP_PATH}"
mkdir -p \${BACKUP_PATH}

echo "备份生产环境..."
cp -r ${PROD_DIR}/app_web \${BACKUP_PATH}/
cp -r ${PROD_DIR}/data \${BACKUP_PATH}/ 2>/dev/null || echo "data 目录不存在，跳过"

echo "备份完成: \${BACKUP_PATH}"
EOF

# 步骤 4: 创建测试环境目录
echo ""
echo "[步骤 4/8] 创建测试环境目录..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
echo "创建测试环境目录: ${TEST_DIR}"
mkdir -p ${TEST_DIR}
mkdir -p ${TEST_DIR}/data
mkdir -p ${TEST_DIR}/data/thumbnails
mkdir -p ${TEST_DIR}/logs
EOF

# 步骤 5: 打包本地代码
echo ""
echo "[步骤 5/8] 打包本地代码..."
cd /Users/mini/QRTestScanner-clean
tar -czf /tmp/mes_test_deploy.tar.gz \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='.gradle' \
    --exclude='build' \
    --exclude='uploads' \
    --exclude='*.db' \
    app_web/ \
    scripts/ \
    tests/

echo "代码打包完成: /tmp/mes_test_deploy.tar.gz"
ls -lh /tmp/mes_test_deploy.tar.gz

# 步骤 6: 上传代码到 NAS
echo ""
echo "[步骤 6/8] 上传代码到 NAS..."
sshpass -p "${NAS_PASSWORD}" scp -P ${NAS_PORT} \
    /tmp/mes_test_deploy.tar.gz \
    ${NAS_USER}@${NAS_HOST}:${TEST_DIR}/

# 步骤 7: 解压并配置测试环境
echo ""
echo "[步骤 7/8] 解压并配置测试环境..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
cd ${TEST_DIR}

echo "解压代码..."
tar -xzf mes_test_deploy.tar.gz
rm mes_test_deploy.tar.gz

echo "复制生产环境配置..."
if [ -f ${PROD_DIR}/app_web/webdav_config.json ]; then
    cp ${PROD_DIR}/app_web/webdav_config.json ${TEST_DIR}/app_web/
    echo "已复制 webdav_config.json"
fi

if [ -d ${PROD_DIR}/data ]; then
    echo "复制数据库文件..."
    cp ${PROD_DIR}/data/*.db ${TEST_DIR}/data/ 2>/dev/null || echo "未找到数据库文件"
fi

echo "设置权限..."
chmod +x ${TEST_DIR}/app_web/mesapp.py

echo "测试环境配置完成"
EOF

# 步骤 8: 创建测试环境启动脚本
echo ""
echo "[步骤 8/8] 创建测试环境启动脚本..."
sshpass -p "${NAS_PASSWORD}" ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << 'EOF'
cat > /volume2/MES_TEST/start_test.sh << 'SCRIPT'
#!/bin/bash
# 测试环境启动脚本

cd /volume2/MES_TEST/app_web

# 设置环境变量
export FLASK_ENV=development
export DATA_DIR=/volume2/MES_TEST/data
export REDIS_HOST=localhost
export REDIS_PORT=6379

# 启动应用（使用不同端口避免冲突）
echo "启动测试环境..."
echo "访问地址: http://172.16.30.2:5001"
python3 mesapp.py --port 5001 > /volume2/MES_TEST/logs/app.log 2>&1 &

echo "测试环境已启动"
echo "PID: $!"
echo "日志文件: /volume2/MES_TEST/logs/app.log"
SCRIPT

chmod +x /volume2/MES_TEST/start_test.sh
echo "启动脚本已创建: /volume2/MES_TEST/start_test.sh"
EOF

echo ""
echo "========================================="
echo "部署完成！"
echo "========================================="
echo ""
echo "测试环境路径: ${TEST_DIR}"
echo ""
echo "下一步操作:"
echo "1. SSH 登录 NAS:"
echo "   ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST}"
echo ""
echo "2. 启动测试环境:"
echo "   cd ${TEST_DIR}"
echo "   ./start_test.sh"
echo ""
echo "3. 查看日志:"
echo "   tail -f ${TEST_DIR}/logs/app.log"
echo ""
echo "4. 访问测试环境:"
echo "   http://172.16.30.2:5001"
echo ""
echo "5. 如需恢复生产环境:"
echo "   cd ${PROD_DIR}/app_web"
echo "   python3 mesapp.py &"
echo ""
