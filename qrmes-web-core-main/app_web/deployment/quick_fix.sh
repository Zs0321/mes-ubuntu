#!/bin/bash
# 快速修复脚本 - 移除群晖依赖并修复数据库持久化
# Bash脚本（Linux/Mac）

echo "========================================"
echo "数据库持久化修复和群晖协议移除工具"
echo "========================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 1. 检查Python环境
echo -e "${YELLOW}[1/6] 检查Python环境...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓ Python已安装: $PYTHON_VERSION${NC}"
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version)
    echo -e "${GREEN}✓ Python已安装: $PYTHON_VERSION${NC}"
    PYTHON_CMD="python"
else
    echo -e "${RED}✗ Python未安装，请先安装Python 3.7+${NC}"
    exit 1
fi

# 2. 查找数据库文件
echo ""
echo -e "${YELLOW}[2/6] 查找数据库文件...${NC}"

DB_PATHS=(
    "app/files/users.db"
    "../app/files/users.db"
    "users.db"
)

DB_PATH=""
for path in "${DB_PATHS[@]}"; do
    if [ -f "$path" ]; then
        DB_PATH="$path"
        echo -e "${GREEN}✓ 找到数据库: $DB_PATH${NC}"
        break
    fi
done

if [ -z "$DB_PATH" ]; then
    echo -e "${RED}✗ 未找到数据库文件${NC}"
    echo -e "${YELLOW}请手动指定数据库路径，或创建新数据库${NC}"
    
    read -p "是否创建新数据库? (y/N): " CREATE_NEW
    if [ "$CREATE_NEW" = "y" ]; then
        DB_PATH="app/files/users.db"
        mkdir -p "app/files"
        echo -e "${GREEN}✓ 将创建新数据库: $DB_PATH${NC}"
    else
        exit 1
    fi
fi

# 3. 备份数据库
echo ""
echo -e "${YELLOW}[3/6] 备份数据库...${NC}"

if [ -f "$DB_PATH" ]; then
    BACKUP_PATH="${DB_PATH}.backup_$(date +%Y%m%d_%H%M%S)"
    cp "$DB_PATH" "$BACKUP_PATH"
    echo -e "${GREEN}✓ 数据库已备份到: $BACKUP_PATH${NC}"
else
    echo -e "${YELLOW}! 数据库文件不存在，将创建新数据库${NC}"
fi

# 4. 运行数据库迁移
echo ""
echo -e "${YELLOW}[4/6] 运行数据库迁移...${NC}"

read -p "请输入管理员密码（默认: admin123）: " ADMIN_PASSWORD
if [ -z "$ADMIN_PASSWORD" ]; then
    ADMIN_PASSWORD="admin123"
fi

echo -e "${CYAN}执行迁移脚本...${NC}"
$PYTHON_CMD migrate_database.py "$DB_PATH" "$ADMIN_PASSWORD"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 数据库迁移成功${NC}"
else
    echo -e "${RED}✗ 数据库迁移失败${NC}"
    echo -e "${YELLOW}请检查错误信息并手动修复${NC}"
    exit 1
fi

# 5. 检查新文件
echo ""
echo -e "${YELLOW}[5/6] 检查新文件...${NC}"

REQUIRED_FILES=(
    "local_auth_service.py"
    "user_management_service_v2.py"
    "migrate_database.py"
)

ALL_FILES_EXIST=true
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓ $file${NC}"
    else
        echo -e "${RED}✗ $file 不存在${NC}"
        ALL_FILES_EXIST=false
    fi
done

if [ "$ALL_FILES_EXIST" = false ]; then
    echo -e "${YELLOW}! 部分文件缺失，请确保所有新文件都已创建${NC}"
fi

# 6. 显示下一步操作
echo ""
echo -e "${YELLOW}[6/6] 完成!${NC}"
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}下一步操作:${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${NC}1. 更新 mesapp.py 文件:${NC}"
echo -e "   将以下代码:"
echo -e "   from synology_auth_client import SynologyAuthService"
echo -e "   synology_auth = SynologyAuthService(...)"
echo ""
echo -e "   替换为:"
echo -e "   from user_management_service_v2 import UserManagementService"
echo -e "   user_service = UserManagementService(db_path)"
echo ""
echo -e "${NC}2. 重启应用:${NC}"
echo -e "   python mesapp.py"
echo ""
echo -e "${NC}3. 使用以下凭据登录:${NC}"
echo -e "   用户名: admin"
echo -e "   密码: $ADMIN_PASSWORD"
echo ""
echo -e "${YELLOW}4. 登录后立即修改密码!${NC}"
echo ""
echo -e "${CYAN}详细说明请查看: IMPLEMENTATION_GUIDE.md${NC}"
echo ""

# 询问是否查看实施指南
read -p "是否查看实施指南? (y/N): " VIEW_GUIDE
if [ "$VIEW_GUIDE" = "y" ]; then
    if [ -f "IMPLEMENTATION_GUIDE.md" ]; then
        less "IMPLEMENTATION_GUIDE.md"
    else
        echo -e "${RED}实施指南文件不存在${NC}"
    fi
fi

echo ""
echo -e "${GREEN}脚本执行完成!${NC}"
