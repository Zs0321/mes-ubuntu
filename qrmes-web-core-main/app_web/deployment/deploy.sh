#!/bin/bash

###############################################################################
# MES应用完整部署脚本（历史独立服务器/生产流程）
# 当前 NAS 测试环境 172.16.30.2:8891 请使用 docs/skills/mes-update-nas-sync/SKILL.md
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置变量
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
NAS_HOST="${NAS_HOST:-172.16.30.2}"
NAS_USER="${NAS_USER:-panovation}"
NAS_PORT="${NAS_PORT:-30001}"
NAS_APP_DIR="${NAS_APP_DIR:-/volume2/MES/app_web}"
NAS_DATA_DIR="${NAS_DATA_DIR:-/volume2/MES/data}"
NAS_FILES_DIR="${NAS_FILES_DIR:-/volume2/MES/files}"
SERVICE_NAME="mesapp"
ALLOW_LEGACY_DEPLOY="${ALLOW_LEGACY_DEPLOY:-0}"

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
    echo "  MES应用完整部署（历史流程）"
    echo "========================================="
    echo ""
    echo "目标服务器: ${NAS_HOST}"
    echo "部署目录: ${NAS_APP_DIR}"
    echo ""
}

guard_legacy_deploy() {
    if [ "${ALLOW_LEGACY_DEPLOY}" != "1" ]; then
        log_error "此脚本属于历史独立服务器/生产部署流程，不适用于当前 NAS 测试环境 172.16.30.2:8891。"
        log_error "当前测试环境请使用 docs/skills/mes-update-nas-sync/SKILL.md，并部署到 /volume2/MES/test/app_web。"
        log_error "如确需执行历史 /volume2/MES/app_web 流程，请显式设置 ALLOW_LEGACY_DEPLOY=1。"
        exit 1
    fi

    if [ "${NAS_APP_DIR}" = "/volume2/MES/test/app_web" ]; then
        log_error "此历史脚本不支持测试环境目录 ${NAS_APP_DIR}。"
        log_error "测试环境请改用 docs/skills/mes-update-nas-sync/SKILL.md。"
        exit 1
    fi
}

# 检查本地环境
check_local_environment() {
    log_step "1. 检查本地环境..."
    
    # 检查必要的命令
    for cmd in ssh scp curl; do
        if ! command -v $cmd &> /dev/null; then
            log_error "缺少必要命令: $cmd"
            exit 1
        fi
    done
    
    log_info "✓ 本地环境检查通过"
    echo ""
}

# 检查远程连接
check_remote_connection() {
    log_step "2. 检查远程连接..."
    
    if ssh -p ${NAS_PORT} -o ConnectTimeout=5 ${NAS_USER}@${NAS_HOST} "echo 'Connection OK'" > /dev/null 2>&1; then
        log_info "✓ SSH连接正常"
    else
        log_error "✗ 无法连接到远程服务器"
        log_error "请检查SSH配置和网络连接"
        exit 1
    fi
    
    echo ""
}

# 创建远程目录结构
create_remote_directories() {
    log_step "3. 创建远程目录结构..."
    
    ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
        # 创建应用目录
        sudo mkdir -p ${NAS_APP_DIR}
        sudo mkdir -p ${NAS_APP_DIR}/static
        sudo mkdir -p ${NAS_APP_DIR}/templates
        sudo mkdir -p ${NAS_APP_DIR}/deployment
        
        # 创建数据目录
        sudo mkdir -p ${NAS_DATA_DIR}
        
        # 创建文件存储目录
        sudo mkdir -p ${NAS_FILES_DIR}/projects
        sudo mkdir -p ${NAS_FILES_DIR}/record
        sudo mkdir -p ${NAS_FILES_DIR}/photos
        
        # 创建日志目录
        sudo mkdir -p /var/log
        
        # 创建备份目录
        sudo mkdir -p /volume2/MES/backups
        
        # 设置权限
        sudo chown -R ${NAS_USER}:users ${NAS_APP_DIR}
        sudo chown -R ${NAS_USER}:users ${NAS_DATA_DIR}
        sudo chown -R ${NAS_USER}:users ${NAS_FILES_DIR}
        
        echo "目录结构创建完成"
EOF
    
    log_info "✓ 远程目录结构创建完成"
    echo ""
}

# 初始化数据库
initialize_database() {
    log_step "4. 初始化数据库..."
    
    # 上传数据库初始化脚本
    scp -P ${NAS_PORT} ${SCRIPT_DIR}/database_setup.sql ${NAS_USER}@${NAS_HOST}:${NAS_APP_DIR}/deployment/
    
    # 执行数据库初始化
    ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
        cd ${NAS_APP_DIR}/deployment
        
        # 检查sqlite3
        if ! command -v sqlite3 &> /dev/null; then
            echo "错误: sqlite3 未安装"
            exit 1
        fi
        
        # 初始化用户数据库
        sqlite3 ${NAS_DATA_DIR}/users.db < database_setup.sql
        
        echo "数据库初始化完成"
EOF
    
    log_info "✓ 数据库初始化完成"
    echo ""
}

# 上传应用文件
upload_application_files() {
    log_step "5. 上传应用文件..."
    
    cd ${PROJECT_ROOT}
    
    # 上传Python文件
    log_info "上传Python模块..."
    for file in mesapp.py config.py auth.py \
                data_access_layer.py permission_service.py \
                user_management_service.py synology_auth_client.py \
                photo_api.py process_config_api.py \
                project_config_manager.py config_history_manager.py \
                h2_api.py error_handler.py security_validator.py; do
        if [ -f "$file" ]; then
            scp -P ${NAS_PORT} $file ${NAS_USER}@${NAS_HOST}:${NAS_APP_DIR}/
            log_info "  ✓ $file"
        else
            log_warn "  ✗ 文件不存在: $file"
        fi
    done
    
    # 上传静态文件
    if [ -d "static" ]; then
        log_info "上传静态文件..."
        scp -P ${NAS_PORT} -r static/* ${NAS_USER}@${NAS_HOST}:${NAS_APP_DIR}/static/
        log_info "  ✓ static/"
    fi
    
    # 上传模板文件
    if [ -d "templates" ]; then
        log_info "上传模板文件..."
        scp -P ${NAS_PORT} -r templates/* ${NAS_USER}@${NAS_HOST}:${NAS_APP_DIR}/templates/
        log_info "  ✓ templates/"
    fi
    
    # 上传配置文件
    log_info "上传配置文件..."
    scp -P ${NAS_PORT} ${SCRIPT_DIR}/production_config.py ${NAS_USER}@${NAS_HOST}:${NAS_APP_DIR}/deployment/
    
    # 上传requirements.txt
    if [ -f "requirements.txt" ]; then
        scp requirements.txt ${NAS_USER}@${NAS_HOST}:${NAS_APP_DIR}/
        log_info "  ✓ requirements.txt"
    fi
    
    log_info "✓ 应用文件上传完成"
    echo ""
}

# 安装Python依赖
install_dependencies() {
    log_step "6. 安装Python依赖..."
    
    ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
        cd ${NAS_APP_DIR}
        
        # 检查pip3
        if ! command -v pip3 &> /dev/null; then
            echo "错误: pip3 未安装"
            echo "请先安装Python3和pip3"
            exit 1
        fi
        
        # 安装依赖
        if [ -f requirements.txt ]; then
            pip3 install -r requirements.txt --user
            echo "依赖安装完成"
        else
            echo "警告: requirements.txt 不存在"
        fi
EOF
    
    log_info "✓ Python依赖安装完成"
    echo ""
}

# 配置systemd服务
configure_systemd_service() {
    log_step "7. 配置systemd服务..."
    
    # 创建服务文件
    cat > /tmp/mesapp.service << 'EOF'
[Unit]
Description=MES Application Service
After=network.target

[Service]
Type=simple
User=panovation
WorkingDirectory=/volume2/MES/app_web
Environment="PYTHONUNBUFFERED=1"
Environment="FLASK_ENV=production"
ExecStart=/usr/bin/python3 /volume2/MES/app_web/mesapp.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/mesapp.log
StandardError=append:/var/log/mesapp.log

[Install]
WantedBy=multi-user.target
EOF
    
    # 上传服务文件
    scp /tmp/mesapp.service ${NAS_USER}@${NAS_HOST}:/tmp/
    
    # 安装服务
    ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
        sudo mv /tmp/mesapp.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable ${SERVICE_NAME}
        echo "systemd服务配置完成"
EOF
    
    log_info "✓ systemd服务配置完成"
    echo ""
}

# 初始化配置文件
initialize_config_files() {
    log_step "8. 初始化配置文件..."
    
    ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
        cd ${NAS_FILES_DIR}
        
        # 创建projects.json
        if [ ! -f projects.json ]; then
            echo '{"projects": []}' > projects.json
            echo "✓ 创建 projects.json"
        fi
        
        # 创建testers.json
        if [ ! -f testers.json ]; then
            echo '{"testers": []}' > testers.json
            echo "✓ 创建 testers.json"
        fi
        
        # 创建active_tests.json
        if [ ! -f active_tests.json ]; then
            echo '{"tests": []}' > active_tests.json
            echo "✓ 创建 active_tests.json"
        fi
        
        echo "配置文件初始化完成"
EOF
    
    log_info "✓ 配置文件初始化完成"
    echo ""
}

# 启动服务
start_service() {
    log_step "9. 启动服务..."
    
    ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} << EOF
        sudo systemctl start ${SERVICE_NAME}
        sleep 3
        sudo systemctl status ${SERVICE_NAME} --no-pager
EOF
    
    log_info "✓ 服务启动完成"
    echo ""
}

# 验证部署
verify_deployment() {
    log_step "10. 验证部署..."
    
    # 等待服务启动
    log_info "等待服务启动..."
    sleep 5
    
    # 检查健康端点
    HEALTH_URL="http://${NAS_HOST}:8891/api/h2/health"
    log_info "检查健康端点: ${HEALTH_URL}"
    
    MAX_RETRIES=5
    RETRY_COUNT=0
    
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" ${HEALTH_URL} 2>/dev/null || echo "000")
        
        if [ "$RESPONSE" = "200" ]; then
            log_info "✓ 健康检查通过 (HTTP 200)"
            break
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
                log_warn "健康检查失败 (HTTP ${RESPONSE})，重试 ${RETRY_COUNT}/${MAX_RETRIES}..."
                sleep 3
            else
                log_error "✗ 健康检查失败 (HTTP ${RESPONSE})"
                return 1
            fi
        fi
    done
    
    # 检查日志
    log_info "检查最新日志..."
    ssh -p ${NAS_PORT} ${NAS_USER}@${NAS_HOST} "sudo tail -20 /var/log/mesapp.log"
    
    echo ""
    log_info "✓ 部署验证完成"
    echo ""
}

# 显示部署摘要
show_deployment_summary() {
    echo "========================================="
    echo "  部署完成"
    echo "========================================="
    echo ""
    echo "应用信息:"
    echo "  地址: http://${NAS_HOST}:8891"
    echo "  健康检查: http://${NAS_HOST}:8891/api/h2/health"
    echo ""
    echo "服务管理:"
    echo "  启动: sudo systemctl start ${SERVICE_NAME}"
    echo "  停止: sudo systemctl stop ${SERVICE_NAME}"
    echo "  重启: sudo systemctl restart ${SERVICE_NAME}"
    echo "  状态: sudo systemctl status ${SERVICE_NAME}"
    echo ""
    echo "日志查看:"
    echo "  应用日志: sudo tail -f /var/log/mesapp.log"
    echo "  审计日志: sudo tail -f /var/log/mesapp_audit.log"
    echo ""
    echo "目录位置:"
    echo "  应用: ${NAS_APP_DIR}"
    echo "  数据: ${NAS_DATA_DIR}"
    echo "  文件: ${NAS_FILES_DIR}"
    echo ""
}

# 主函数
main() {
    show_header
    guard_legacy_deploy
    
    # 检查参数
    SKIP_DEPS=false
    SKIP_SERVICE=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-deps)
                SKIP_DEPS=true
                shift
                ;;
            --skip-service)
                SKIP_SERVICE=true
                shift
                ;;
            *)
                log_error "未知选项: $1"
                exit 1
                ;;
        esac
    done
    
    # 执行部署步骤
    check_local_environment
    check_remote_connection
    create_remote_directories
    initialize_database
    upload_application_files
    
    if [ "$SKIP_DEPS" = false ]; then
        install_dependencies
    else
        log_warn "跳过依赖安装"
    fi
    
    if [ "$SKIP_SERVICE" = false ]; then
        configure_systemd_service
    else
        log_warn "跳过服务配置"
    fi
    
    initialize_config_files
    start_service
    
    if verify_deployment; then
        show_deployment_summary
        exit 0
    else
        log_error "部署验证失败"
        log_error "请检查日志: sudo tail -f /var/log/mesapp.log"
        exit 1
    fi
}

# 显示使用说明
show_usage() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --skip-deps       跳过依赖安装"
    echo "  --skip-service    跳过服务配置"
    echo "  --help            显示此帮助信息"
    echo ""
    echo "环境变量:"
    echo "  NAS_HOST          NAS服务器地址（默认: 172.16.30.2）"
    echo "  NAS_USER          SSH用户名（默认: panovation）"
    echo "  NAS_APP_DIR       应用目录（默认: /volume2/MES/app_web）"
    echo "  ALLOW_LEGACY_DEPLOY  显式确认执行历史 /volume2/MES/app_web 部署流程（必须设为1）"
    echo ""
}

# 处理帮助参数
if [ "$1" = "--help" ]; then
    show_usage
    exit 0
fi

# 执行主函数
main "$@"
