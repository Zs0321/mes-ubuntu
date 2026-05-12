#!/bin/bash
# ============================================================
# QR MES 系统一键部署脚本
# ============================================================
# 用途：自动化部署 QR MES 系统到 Ubuntu 服务器
# 使用：sudo ./deploy.sh
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置变量
APP_DIR="/opt/qrmes"
DEPLOYMENT_DIR="$APP_DIR/QRTestScanner/app_web/deployment"
LOG_FILE="/tmp/qrmes-deploy-$(date +%Y%m%d_%H%M%S).log"

# 函数：打印消息
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[错误]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

warning() {
    echo -e "${YELLOW}[警告]${NC} $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[信息]${NC} $1" | tee -a "$LOG_FILE"
}

# 函数：检查命令是否存在
check_command() {
    if ! command -v $1 &> /dev/null; then
        return 1
    fi
    return 0
}

# 欢迎信息
clear
echo -e "${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════════╗
║                                           ║
║     QR MES 系统自动化部署脚本             ║
║                                           ║
║     Version: 1.0                          ║
║     Date: 2025-12-04                      ║
║                                           ║
╚═══════════════════════════════════════════╝
EOF
echo -e "${NC}\n"

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then 
    error "请使用 sudo 运行此脚本"
fi

log "开始部署流程，日志文件：$LOG_FILE"

# ============================================================
# 步骤 1: 环境检查
# ============================================================
log "步骤 1/8: 检查系统环境..."

# 检查操作系统
if [ ! -f /etc/os-release ]; then
    error "无法识别操作系统"
fi

source /etc/os-release
info "操作系统：$PRETTY_NAME"

# 检查必要命令
info "检查必要的命令..."
REQUIRED_COMMANDS="curl wget git"
for cmd in $REQUIRED_COMMANDS; do
    if ! check_command $cmd; then
        warning "$cmd 未安装，正在安装..."
        apt-get install -y $cmd >> "$LOG_FILE" 2>&1
    else
        info "✓ $cmd 已安装"
    fi
done

# ============================================================
# 步骤 2: 安装 Docker
# ============================================================
log "步骤 2/8: 安装 Docker..."

if ! check_command docker; then
    info "正在安装 Docker..."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sh /tmp/get-docker.sh >> "$LOG_FILE" 2>&1
    usermod -aG docker $SUDO_USER
    info "✓ Docker 安装完成"
else
    info "✓ Docker 已安装：$(docker --version)"
fi

# ============================================================
# 步骤 3: 安装 Docker Compose
# ============================================================
log "步骤 3/8: 安装 Docker Compose..."

if ! check_command docker-compose; then
    info "正在安装 Docker Compose..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose >> "$LOG_FILE" 2>&1
    chmod +x /usr/local/bin/docker-compose
    info "✓ Docker Compose 安装完成"
else
    info "✓ Docker Compose 已安装：$(docker-compose --version)"
fi

# ============================================================
# 步骤 4: 创建应用目录
# ============================================================
log "步骤 4/8: 创建应用目录..."

if [ ! -d "$APP_DIR" ]; then
    mkdir -p "$APP_DIR"
    chown -R $SUDO_USER:$SUDO_USER "$APP_DIR"
    info "✓ 已创建目录：$APP_DIR"
else
    info "✓ 目录已存在：$APP_DIR"
fi

# ============================================================
# 步骤 5: 配置 NAS 挂载
# ============================================================
log "步骤 5/8: 配置 NAS 挂载..."

if [ -f "$(dirname $0)/mount-nas.sh" ]; then
    info "运行 NAS 挂载脚本..."
    bash "$(dirname $0)/mount-nas.sh" >> "$LOG_FILE" 2>&1
    info "✓ NAS 挂载配置完成"
else
    warning "未找到 mount-nas.sh，请手动配置 NAS 挂载"
fi

# ============================================================
# 步骤 6: 部署应用
# ============================================================
log "步骤 6/8: 部署应用..."

if [ ! -d "$DEPLOYMENT_DIR" ]; then
    error "找不到部署目录：$DEPLOYMENT_DIR"
fi

cd "$DEPLOYMENT_DIR"

# 检查 .env 文件
if [ ! -f .env ]; then
    warning ".env 文件不存在，从模板创建..."
    if [ -f .env.example ]; then
        cp .env.example .env
        info "✓ 已创建 .env 文件"
        warning "请编辑 .env 文件配置必要的参数"
        echo ""
        echo -e "${YELLOW}必须配置的参数：${NC}"
        echo "  - FLASK_SECRET_KEY"
        echo "  - NAS_USERNAME"
        echo "  - NAS_PASSWORD"
        echo "  - NAS_HOST_MOUNT_PATH"
        echo ""
        read -p "按 Enter 键编辑 .env 文件..." 
        vim .env
    else
        error "找不到 .env.example 文件"
    fi
fi

# 创建数据目录
info "创建数据目录..."
mkdir -p data/{databases,logs/nginx,cache,config,redis}

# ============================================================
# 步骤 7: 构建并启动容器
# ============================================================
log "步骤 7/8: 构建并启动 Docker 容器..."

info "正在构建镜像..."
docker-compose build >> "$LOG_FILE" 2>&1

info "正在启动容器..."
docker-compose up -d >> "$LOG_FILE" 2>&1

# 等待容器启动
info "等待容器启动..."
sleep 10

# ============================================================
# 步骤 8: 验证部署
# ============================================================
log "步骤 8/8: 验证部署..."

# 检查容器状态
info "检查容器状态..."
docker-compose ps

# 健康检查
info "执行健康检查..."
if curl -f http://localhost/health > /dev/null 2>&1; then
    info "✓ Nginx 健康检查通过"
else
    warning "✗ Nginx 健康检查失败"
fi

if docker exec qrmes-redis redis-cli ping > /dev/null 2>&1; then
    info "✓ Redis 健康检查通过"
else
    warning "✗ Redis 健康检查失败"
fi

# ============================================================
# 完成
# ============================================================
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                           ║${NC}"
echo -e "${GREEN}║         部署完成！                        ║${NC}"
echo -e "${GREEN}║                                           ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════╝${NC}"
echo ""

info "部署信息："
echo "  • 应用目录：$APP_DIR"
echo "  • 部署目录：$DEPLOYMENT_DIR"
echo "  • 日志文件：$LOG_FILE"
echo ""

info "访问地址："
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "  • 内网访问：http://$SERVER_IP"
echo "  • 本地访问：http://localhost"
echo ""

info "常用命令："
echo "  • 查看日志：cd $DEPLOYMENT_DIR && docker-compose logs -f"
echo "  • 重启服务：cd $DEPLOYMENT_DIR && docker-compose restart"
echo "  • 停止服务：cd $DEPLOYMENT_DIR && docker-compose down"
echo "  • 查看状态：cd $DEPLOYMENT_DIR && docker-compose ps"
echo ""

warning "下一步操作："
echo "  1. 迁移数据库文件到：$DEPLOYMENT_DIR/data/databases/"
echo "  2. 验证 NAS 挂载：ls /mnt/nas-qrmes/QRMES"
echo "  3. 在浏览器中测试：http://$SERVER_IP"
echo "  4. 检查应用日志：docker-compose logs -f flask-app"
echo ""

log "部署流程结束"
