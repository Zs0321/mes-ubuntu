#!/bin/bash

###############################################################################
# 群晖服务器API访问权限配置脚本
# 用于配置群晖DSM API访问权限和WebDAV服务
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置变量
SYNOLOGY_HOST="${SYNOLOGY_HOST:-172.16.30.2}"
SYNOLOGY_PORT="${SYNOLOGY_PORT:-5000}"
SYNOLOGY_ADMIN_USER="${SYNOLOGY_ADMIN_USER:-admin}"

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# 显示标题
show_header() {
    echo "========================================="
    echo "  群晖服务器API访问权限配置"
    echo "========================================="
    echo ""
    echo "目标服务器: ${SYNOLOGY_HOST}:${SYNOLOGY_PORT}"
    echo ""
}

# 检查群晖服务器连接
check_synology_connection() {
    log_step "1. 检查群晖服务器连接..."
    
    if ping -c 1 -W 2 ${SYNOLOGY_HOST} > /dev/null 2>&1; then
        log_info "✓ 服务器可达: ${SYNOLOGY_HOST}"
    else
        log_error "✗ 无法连接到服务器: ${SYNOLOGY_HOST}"
        log_error "请检查网络连接和服务器地址"
        exit 1
    fi
    
    # 检查DSM API端口
    if nc -z -w 2 ${SYNOLOGY_HOST} ${SYNOLOGY_PORT} 2>/dev/null; then
        log_info "✓ DSM API端口可访问: ${SYNOLOGY_PORT}"
    else
        log_warn "✗ DSM API端口不可访问: ${SYNOLOGY_PORT}"
        log_warn "请确保DSM服务正在运行"
    fi
    
    echo ""
}

# 测试DSM API
test_dsm_api() {
    log_step "2. 测试DSM API..."
    
    # 测试API信息端点
    API_URL="http://${SYNOLOGY_HOST}:${SYNOLOGY_PORT}/webapi/query.cgi?api=SYNO.API.Info&version=1&method=query"
    
    log_info "测试API端点: ${API_URL}"
    
    RESPONSE=$(curl -s -w "\n%{http_code}" "${API_URL}" 2>/dev/null || echo "000")
    HTTP_CODE=$(echo "$RESPONSE" | tail -n 1)
    BODY=$(echo "$RESPONSE" | head -n -1)
    
    if [ "$HTTP_CODE" = "200" ]; then
        log_info "✓ DSM API响应正常 (HTTP 200)"
        echo "响应内容: ${BODY:0:100}..."
    else
        log_error "✗ DSM API响应异常 (HTTP ${HTTP_CODE})"
        log_error "请检查DSM服务状态"
    fi
    
    echo ""
}

# 配置WebDAV服务
configure_webdav() {
    log_step "3. 配置WebDAV服务..."
    
    echo "请在群晖DSM中手动完成以下配置："
    echo ""
    echo "1. 登录DSM控制面板"
    echo "2. 打开 '控制面板' > 'WebDAV'"
    echo "3. 启用WebDAV服务"
    echo "4. 配置端口（建议: HTTP 5005, HTTPS 5006）"
    echo "5. 点击'应用'保存设置"
    echo ""
    
    read -p "WebDAV服务是否已启用？(y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "✓ WebDAV服务已启用"
        
        # 测试WebDAV连接
        WEBDAV_PORT="${WEBDAV_PORT:-5005}"
        if nc -z -w 2 ${SYNOLOGY_HOST} ${WEBDAV_PORT} 2>/dev/null; then
            log_info "✓ WebDAV端口可访问: ${WEBDAV_PORT}"
        else
            log_warn "✗ WebDAV端口不可访问: ${WEBDAV_PORT}"
        fi
    else
        log_warn "请先启用WebDAV服务"
    fi
    
    echo ""
}

# 配置共享文件夹权限
configure_shared_folder() {
    log_step "4. 配置共享文件夹权限..."
    
    echo "请在群晖DSM中手动完成以下配置："
    echo ""
    echo "1. 登录DSM控制面板"
    echo "2. 打开 '控制面板' > '共享文件夹'"
    echo "3. 选择或创建 'MES' 共享文件夹"
    echo "4. 点击'编辑' > '权限'"
    echo "5. 为应用用户授予读写权限"
    echo "6. 在'高级权限'中启用WebDAV访问"
    echo ""
    
    read -p "共享文件夹权限是否已配置？(y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "✓ 共享文件夹权限已配置"
    else
        log_warn "请先配置共享文件夹权限"
    fi
    
    echo ""
}

# 创建应用用户
create_app_user() {
    log_step "5. 创建应用用户..."
    
    echo "请在群晖DSM中手动完成以下配置："
    echo ""
    echo "1. 登录DSM控制面板"
    echo "2. 打开 '控制面板' > '用户账号'"
    echo "3. 点击'新增'创建用户"
    echo "4. 用户名建议: mesapp"
    echo "5. 设置强密码"
    echo "6. 分配到'users'群组"
    echo "7. 授予MES共享文件夹的读写权限"
    echo "8. 在'应用程序'选项卡中授予必要的应用权限"
    echo ""
    
    read -p "应用用户是否已创建？(y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "✓ 应用用户已创建"
        
        # 提示保存凭据
        echo ""
        log_warn "重要：请将用户凭据保存到环境变量或配置文件中"
        echo "export SYNOLOGY_USERNAME='mesapp'"
        echo "export SYNOLOGY_PASSWORD='your-password'"
    else
        log_warn "请先创建应用用户"
    fi
    
    echo ""
}

# 测试API认证
test_api_authentication() {
    log_step "6. 测试API认证..."
    
    read -p "请输入测试用户名: " TEST_USER
    read -s -p "请输入密码: " TEST_PASS
    echo ""
    
    # 测试登录API
    LOGIN_URL="http://${SYNOLOGY_HOST}:${SYNOLOGY_PORT}/webapi/auth.cgi"
    LOGIN_DATA="api=SYNO.API.Auth&version=3&method=login&account=${TEST_USER}&passwd=${TEST_PASS}&session=FileStation&format=cookie"
    
    log_info "测试认证..."
    
    RESPONSE=$(curl -s -X POST "${LOGIN_URL}" -d "${LOGIN_DATA}" 2>/dev/null)
    
    if echo "$RESPONSE" | grep -q '"success":true'; then
        log_info "✓ 认证成功"
        echo "响应: ${RESPONSE}"
    else
        log_error "✗ 认证失败"
        echo "响应: ${RESPONSE}"
        log_error "请检查用户名和密码"
    fi
    
    echo ""
}

# 生成配置文件
generate_config_file() {
    log_step "7. 生成配置文件..."
    
    CONFIG_FILE="synology_config.env"
    
    cat > ${CONFIG_FILE} << EOF
# 群晖服务器配置
# 生成时间: $(date)

# 服务器地址
SYNOLOGY_HOST=${SYNOLOGY_HOST}
SYNOLOGY_PORT=${SYNOLOGY_PORT}
SYNOLOGY_USE_HTTPS=false

# API配置
SYNOLOGY_API_VERSION=6
SYNOLOGY_TIMEOUT=10

# WebDAV配置
WEBDAV_URL=http://${SYNOLOGY_HOST}:5005
WEBDAV_BASE_PATH=/MES/files

# 应用用户凭据（请填写）
SYNOLOGY_USERNAME=
SYNOLOGY_PASSWORD=

# 文件存储配置
USE_WEBDAV=false
NAS_LOCAL_BASE_PATH=/volume2/MES/files
EOF
    
    log_info "✓ 配置文件已生成: ${CONFIG_FILE}"
    log_warn "请编辑配置文件并填写用户凭据"
    
    echo ""
}

# 显示配置摘要
show_summary() {
    log_step "配置摘要"
    
    echo "========================================="
    echo "  配置完成"
    echo "========================================="
    echo ""
    echo "已完成的配置："
    echo "  ✓ 服务器连接检查"
    echo "  ✓ DSM API测试"
    echo "  ✓ WebDAV服务配置"
    echo "  ✓ 共享文件夹权限"
    echo "  ✓ 应用用户创建"
    echo "  ✓ 配置文件生成"
    echo ""
    echo "下一步："
    echo "  1. 编辑 synology_config.env 文件"
    echo "  2. 填写应用用户凭据"
    echo "  3. 运行部署脚本"
    echo ""
    echo "配置文件位置: $(pwd)/synology_config.env"
    echo ""
}

# 主函数
main() {
    show_header
    check_synology_connection
    test_dsm_api
    configure_webdav
    configure_shared_folder
    create_app_user
    
    # 可选：测试认证
    read -p "是否测试API认证？(y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_api_authentication
    fi
    
    generate_config_file
    show_summary
}

# 显示使用说明
show_usage() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --host HOST       群晖服务器地址（默认: 172.16.30.2）"
    echo "  --port PORT       DSM API端口（默认: 5000）"
    echo "  --help            显示此帮助信息"
    echo ""
    echo "环境变量:"
    echo "  SYNOLOGY_HOST     群晖服务器地址"
    echo "  SYNOLOGY_PORT     DSM API端口"
    echo "  WEBDAV_PORT       WebDAV端口"
    echo ""
}

# 处理命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            SYNOLOGY_HOST="$2"
            shift 2
            ;;
        --port)
            SYNOLOGY_PORT="$2"
            shift 2
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            log_error "未知选项: $1"
            show_usage
            exit 1
            ;;
    esac
done

# 执行主函数
main
