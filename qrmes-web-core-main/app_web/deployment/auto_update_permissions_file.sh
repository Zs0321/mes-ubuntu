#!/bin/bash
#
# 自动更新权限配置文件
# 
# 用途：定期从数据库生成权限配置文件供 WebDAV 用户使用
# 建议：添加到 crontab 每分钟执行一次
#
# 添加到 crontab:
# */1 * * * * /volume2/MES/app_web/auto_update_permissions_file.sh >> /var/log/permissions_update.log 2>&1
#

# 配置
SCRIPT_DIR="/volume2/MES/app_web"
OUTPUT_DIR="/volume2/MES/files/config"
PYTHON="/usr/bin/python3"
LOG_FILE="/var/log/permissions_update.log"

# 切换到脚本目录
cd "$SCRIPT_DIR" || exit 1

# 记录时间
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting permissions file update..."

# 执行生成脚本
$PYTHON generate_permissions_file.py "$OUTPUT_DIR"

# 检查结果
if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Permissions file updated successfully"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Failed to update permissions file"
    exit 1
fi
