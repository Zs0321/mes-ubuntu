#!/bin/bash
# ============================================================
# NAS 自动挂载脚本
# ============================================================
# 用途：在 Ubuntu/CentOS 服务器上自动挂载群晖 NAS
# 使用：sudo ./mount-nas.sh
# ============================================================

set -e

# 配置变量（根据实际情况修改）
NAS_SERVER="172.16.30.2"
NAS_SHARE="mes"
NAS_USERNAME="your_username"
NAS_PASSWORD="your_password"
MOUNT_POINT="/mnt/nas-qrmes"
CREDENTIALS_FILE="/etc/nas-credentials"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}======================================"
echo "    群晖 NAS 挂载配置脚本"
echo -e "======================================${NC}\n"

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}错误：请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# 1. 安装必要的包
echo -e "${YELLOW}[1/5] 安装必要的软件包...${NC}"
if command -v apt-get &> /dev/null; then
    # Ubuntu/Debian
    apt-get update -qq
    apt-get install -y cifs-utils
elif command -v yum &> /dev/null; then
    # CentOS/RHEL
    yum install -y cifs-utils
else
    echo -e "${RED}错误：不支持的操作系统${NC}"
    exit 1
fi

# 2. 创建挂载点
echo -e "${YELLOW}[2/5] 创建挂载点目录...${NC}"
if [ ! -d "$MOUNT_POINT" ]; then
    mkdir -p "$MOUNT_POINT"
    echo -e "${GREEN}✓ 已创建目录：$MOUNT_POINT${NC}"
else
    echo -e "${GREEN}✓ 目录已存在：$MOUNT_POINT${NC}"
fi

# 3. 创建凭据文件
echo -e "${YELLOW}[3/5] 配置 NAS 访问凭据...${NC}"
cat > "$CREDENTIALS_FILE" <<EOF
username=$NAS_USERNAME
password=$NAS_PASSWORD
domain=WORKGROUP
EOF

chmod 600 "$CREDENTIALS_FILE"
echo -e "${GREEN}✓ 凭据文件已创建：$CREDENTIALS_FILE${NC}"

# 4. 测试挂载
echo -e "${YELLOW}[4/5] 测试 NAS 挂载...${NC}"

# 先卸载（如果已挂载）
if mountpoint -q "$MOUNT_POINT"; then
    echo "正在卸载现有挂载点..."
    umount "$MOUNT_POINT"
fi

# 尝试挂载
if mount -t cifs "//$NAS_SERVER/$NAS_SHARE" "$MOUNT_POINT" \
    -o credentials="$CREDENTIALS_FILE",iocharset=utf8,file_mode=0777,dir_mode=0777,vers=3.0; then
    echo -e "${GREEN}✓ NAS 挂载成功！${NC}"
    
    # 显示挂载信息
    echo -e "\n${GREEN}挂载点内容：${NC}"
    ls -la "$MOUNT_POINT" | head -10
else
    echo -e "${RED}✗ NAS 挂载失败${NC}"
    echo "请检查："
    echo "  1. NAS 服务器地址：$NAS_SERVER"
    echo "  2. 共享名称：$NAS_SHARE"
    echo "  3. 用户名和密码是否正确"
    echo "  4. 网络连通性：ping $NAS_SERVER"
    echo "  5. SMB 端口：telnet $NAS_SERVER 445"
    exit 1
fi

# 5. 配置开机自动挂载
echo -e "${YELLOW}[5/5] 配置开机自动挂载...${NC}"

FSTAB_ENTRY="//$NAS_SERVER/$NAS_SHARE $MOUNT_POINT cifs credentials=$CREDENTIALS_FILE,iocharset=utf8,file_mode=0777,dir_mode=0777,vers=3.0 0 0"

# 检查 fstab 中是否已存在
if grep -q "$MOUNT_POINT" /etc/fstab; then
    echo -e "${YELLOW}⚠ /etc/fstab 中已存在挂载配置，跳过添加${NC}"
else
    # 备份 fstab
    cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d_%H%M%S)
    echo -e "${GREEN}✓ 已备份 /etc/fstab${NC}"
    
    # 添加到 fstab
    echo "" >> /etc/fstab
    echo "# QR MES NAS 挂载（自动生成于 $(date)）" >> /etc/fstab
    echo "$FSTAB_ENTRY" >> /etc/fstab
    echo -e "${GREEN}✓ 已添加到 /etc/fstab${NC}"
fi

# 测试 fstab
echo -e "\n${YELLOW}测试 fstab 配置...${NC}"
if mount -a; then
    echo -e "${GREEN}✓ fstab 配置正确${NC}"
else
    echo -e "${RED}✗ fstab 配置有误，请检查${NC}"
    exit 1
fi

# 显示最终状态
echo -e "\n${GREEN}======================================"
echo "    NAS 挂载配置完成！"
echo -e "======================================${NC}"
echo -e "\n挂载信息："
df -h | grep "$MOUNT_POINT"

echo -e "\n${GREEN}提示：${NC}"
echo "  • 挂载点：$MOUNT_POINT"
echo "  • NAS 地址：//$NAS_SERVER/$NAS_SHARE"
echo "  • 凭据文件：$CREDENTIALS_FILE"
echo "  • 开机自动挂载已启用"
echo -e "\n${YELLOW}下一步：${NC}"
echo "  1. 验证能访问 NAS 数据：ls $MOUNT_POINT/QRMES"
echo "  2. 继续部署应用：cd /opt/qrmes/deployment && docker-compose up -d"
