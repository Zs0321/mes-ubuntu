# MES系统维护和故障排除指南

## 目录

1. [系统维护](#系统维护)
2. [日常检查](#日常检查)
3. [备份与恢复](#备份与恢复)
4. [性能监控](#性能监控)
5. [故障排除](#故障排除)
6. [常见问题](#常见问题)
7. [紧急联系](#紧急联系)

---

## 系统维护

### 1.1 服务管理

#### 启动服务
```bash
sudo systemctl start mesapp
```

#### 停止服务
```bash
sudo systemctl stop mesapp
```

#### 重启服务
```bash
sudo systemctl restart mesapp
```

#### 查看服务状态
```bash
sudo systemctl status mesapp
```

#### 设置开机自启
```bash
sudo systemctl enable mesapp
```

#### 禁用开机自启
```bash
sudo systemctl disable mesapp
```

### 1.2 日志管理

#### 查看实时日志
```bash
sudo tail -f /var/log/mesapp.log
```

#### 查看最近100行日志
```bash
sudo tail -100 /var/log/mesapp.log
```

#### 查看审计日志
```bash
sudo tail -f /var/log/mesapp_audit.log
```

#### 搜索错误日志
```bash
sudo grep "ERROR" /var/log/mesapp.log
```

#### 按日期查看日志
```bash
sudo grep "2025-01-15" /var/log/mesapp.log
```

#### 清理旧日志
```bash
# 保留最近7天的日志
sudo find /var/log -name "mesapp*.log.*" -mtime +7 -delete
```

### 1.3 数据库维护

#### 备份数据库
```bash
# 备份用户数据库
sqlite3 /volume2/MES/data/users.db ".backup /volume2/MES/backups/users_$(date +%Y%m%d).db"

# 备份H2数据库
cp /volume2/MES/data/product_records.db /volume2/MES/backups/product_records_$(date +%Y%m%d).db
```

#### 数据库完整性检查
```bash
# 检查SQLite数据库
sqlite3 /volume2/MES/data/users.db "PRAGMA integrity_check;"
```

#### 数据库优化
```bash
# 优化SQLite数据库
sqlite3 /volume2/MES/data/users.db "VACUUM;"
```

#### 查看数据库大小
```bash
du -h /volume2/MES/data/*.db
```

### 1.4 文件存储维护

#### 检查存储空间
```bash
df -h /volume2/MES
```

#### 查看照片存储使用情况
```bash
du -sh /volume2/MES/files/photos/*
```

#### 清理临时文件
```bash
# 清理超过30天的临时文件
find /volume2/MES/files/temp -type f -mtime +30 -delete
```

#### 检查文件权限
```bash
ls -la /volume2/MES/files/
```

#### 修复文件权限
```bash
sudo chown -R panovation:users /volume2/MES/files/
sudo chmod -R 755 /volume2/MES/files/
```

---

## 日常检查

### 2.1 每日检查清单

#### 服务状态检查
```bash
#!/bin/bash
# daily_check.sh

echo "=== MES系统每日检查 ==="
echo "检查时间: $(date)"
echo ""

# 1. 检查服务状态
echo "1. 服务状态:"
systemctl is-active mesapp && echo "  ✓ 服务运行正常" || echo "  ✗ 服务未运行"
echo ""

# 2. 检查端口
echo "2. 端口监听:"
netstat -tuln | grep 8891 && echo "  ✓ 端口8891正常监听" || echo "  ✗ 端口8891未监听"
echo ""

# 3. 检查磁盘空间
echo "3. 磁盘空间:"
df -h /volume2/MES | tail -1
echo ""

# 4. 检查最近错误
echo "4. 最近错误 (最近1小时):"
sudo grep "ERROR" /var/log/mesapp.log | grep "$(date +%Y-%m-%d)" | tail -5
echo ""

# 5. 检查数据库连接
echo "5. 数据库连接:"
sqlite3 /volume2/MES/data/users.db "SELECT COUNT(*) FROM users;" && echo "  ✓ 数据库连接正常" || echo "  ✗ 数据库连接失败"
echo ""

echo "=== 检查完成 ==="
```

#### 运行每日检查
```bash
chmod +x daily_check.sh
./daily_check.sh
```

### 2.2 每周检查清单

- [ ] 检查备份文件完整性
- [ ] 清理旧日志文件
- [ ] 检查数据库大小和性能
- [ ] 检查照片存储空间
- [ ] 审查权限拒绝日志
- [ ] 检查系统更新

### 2.3 每月检查清单

- [ ] 完整数据库备份
- [ ] 系统性能评估
- [ ] 用户账户审计
- [ ] 安全日志审查
- [ ] 存储空间规划
- [ ] 系统文档更新

---

## 备份与恢复

### 3.1 自动备份脚本

```bash
#!/bin/bash
# backup.sh - MES系统自动备份脚本

BACKUP_DIR="/volume2/MES/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

echo "开始备份: $(date)"

# 创建备份目录
mkdir -p ${BACKUP_DIR}/${DATE}

# 1. 备份数据库
echo "备份数据库..."
sqlite3 /volume2/MES/data/users.db ".backup ${BACKUP_DIR}/${DATE}/users.db"
cp /volume2/MES/data/product_records.db ${BACKUP_DIR}/${DATE}/product_records.db

# 2. 备份配置文件
echo "备份配置文件..."
cp -r /volume2/MES/files/projects ${BACKUP_DIR}/${DATE}/
cp /volume2/MES/files/*.json ${BACKUP_DIR}/${DATE}/

# 3. 备份应用代码
echo "备份应用代码..."
tar -czf ${BACKUP_DIR}/${DATE}/app_web.tar.gz -C /volume2/MES app_web

# 4. 创建备份清单
echo "创建备份清单..."
cat > ${BACKUP_DIR}/${DATE}/backup_manifest.txt << EOF
备份时间: $(date)
备份内容:
- 用户数据库: users.db
- 产品记录数据库: product_records.db
- 项目配置: projects/
- 配置文件: *.json
- 应用代码: app_web.tar.gz
EOF

# 5. 压缩备份
echo "压缩备份..."
cd ${BACKUP_DIR}
tar -czf backup_${DATE}.tar.gz ${DATE}
rm -rf ${DATE}

# 6. 清理旧备份
echo "清理旧备份..."
find ${BACKUP_DIR} -name "backup_*.tar.gz" -mtime +${RETENTION_DAYS} -delete

echo "备份完成: $(date)"
echo "备份文件: ${BACKUP_DIR}/backup_${DATE}.tar.gz"
```

#### 设置定时备份
```bash
# 编辑crontab
crontab -e

# 添加每天凌晨2点执行备份
0 2 * * * /volume2/MES/scripts/backup.sh >> /var/log/mesapp_backup.log 2>&1
```

### 3.2 恢复数据

#### 恢复数据库
```bash
#!/bin/bash
# restore.sh - 数据恢复脚本

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "用法: $0 <备份文件路径>"
    exit 1
fi

echo "开始恢复: $(date)"
echo "备份文件: $BACKUP_FILE"

# 1. 停止服务
echo "停止服务..."
sudo systemctl stop mesapp

# 2. 备份当前数据
echo "备份当前数据..."
cp /volume2/MES/data/users.db /volume2/MES/data/users.db.before_restore
cp /volume2/MES/data/product_records.db /volume2/MES/data/product_records.db.before_restore

# 3. 解压备份文件
echo "解压备份文件..."
TEMP_DIR=$(mktemp -d)
tar -xzf $BACKUP_FILE -C $TEMP_DIR

# 4. 恢复数据库
echo "恢复数据库..."
BACKUP_DIR=$(ls -d $TEMP_DIR/*/ | head -1)
cp ${BACKUP_DIR}/users.db /volume2/MES/data/
cp ${BACKUP_DIR}/product_records.db /volume2/MES/data/

# 5. 恢复配置文件
echo "恢复配置文件..."
cp -r ${BACKUP_DIR}/projects /volume2/MES/files/
cp ${BACKUP_DIR}/*.json /volume2/MES/files/

# 6. 清理临时文件
rm -rf $TEMP_DIR

# 7. 启动服务
echo "启动服务..."
sudo systemctl start mesapp

# 8. 验证恢复
sleep 3
if systemctl is-active mesapp; then
    echo "✓ 恢复成功，服务已启动"
else
    echo "✗ 恢复失败，服务未启动"
    echo "正在回滚..."
    cp /volume2/MES/data/users.db.before_restore /volume2/MES/data/users.db
    cp /volume2/MES/data/product_records.db.before_restore /volume2/MES/data/product_records.db
    sudo systemctl start mesapp
fi

echo "恢复完成: $(date)"
```

---

## 性能监控

### 4.1 系统资源监控

#### CPU使用率
```bash
top -b -n 1 | grep mesapp
```

#### 内存使用
```bash
ps aux | grep mesapp | awk '{print $4, $6}'
```

#### 磁盘I/O
```bash
iostat -x 1 5
```

### 4.2 应用性能监控

#### 请求响应时间
```bash
# 测试健康检查端点
time curl -s http://172.16.30.2:8891/api/h2/health
```

#### 数据库查询性能
```bash
# 启用SQLite查询分析
sqlite3 /volume2/MES/data/users.db
.timer on
SELECT * FROM users;
```

#### 并发连接数
```bash
netstat -an | grep :8891 | grep ESTABLISHED | wc -l
```

### 4.3 性能优化建议

#### 数据库优化
```sql
-- 创建索引
CREATE INDEX IF NOT EXISTS idx_users_username ON users(synology_username);
CREATE INDEX IF NOT EXISTS idx_photos_product ON process_photos(product_serial);

-- 分析查询计划
EXPLAIN QUERY PLAN SELECT * FROM users WHERE synology_username = 'test';
```

#### 应用优化
- 启用缓存机制
- 优化照片压缩
- 使用连接池
- 实施请求限流

---

## 故障排除

### 5.1 服务无法启动

**症状：** `systemctl start mesapp` 失败

**排查步骤：**

1. 查看服务状态
```bash
sudo systemctl status mesapp
```

2. 查看错误日志
```bash
sudo journalctl -u mesapp -n 50
```

3. 检查Python语法
```bash
cd /volume2/MES/app_web
python3 -m py_compile mesapp.py
```

4. 检查端口占用
```bash
netstat -tuln | grep 8891
```

5. 检查文件权限
```bash
ls -la /volume2/MES/app_web/mesapp.py
```

**解决方案：**
- 修复Python语法错误
- 释放被占用的端口
- 修复文件权限问题
- 检查依赖包是否完整

### 5.2 无法连接数据库

**症状：** 应用日志显示数据库连接错误

**排查步骤：**

1. 检查数据库文件
```bash
ls -la /volume2/MES/data/*.db
```

2. 测试数据库连接
```bash
sqlite3 /volume2/MES/data/users.db "SELECT 1;"
```

3. 检查数据库完整性
```bash
sqlite3 /volume2/MES/data/users.db "PRAGMA integrity_check;"
```

**解决方案：**
- 恢复数据库备份
- 修复数据库文件权限
- 重建损坏的索引

### 5.3 群晖认证失败

**症状：** 用户无法登录，提示认证失败

**排查步骤：**

1. 测试群晖API连接
```bash
curl -s "http://172.16.30.2:5000/webapi/query.cgi?api=SYNO.API.Info&version=1&method=query"
```

2. 检查网络连接
```bash
ping 172.16.30.2
```

3. 查看认证日志
```bash
sudo grep "AUTH" /var/log/mesapp.log | tail -20
```

**解决方案：**
- 检查群晖服务器状态
- 验证API配置正确
- 检查用户账号状态
- 重启群晖DSM服务

### 5.4 照片上传失败

**症状：** 移动端照片无法上传

**排查步骤：**

1. 检查存储空间
```bash
df -h /volume2/MES/files/photos
```

2. 检查文件权限
```bash
ls -la /volume2/MES/files/photos
```

3. 查看上传日志
```bash
sudo grep "photo.*upload" /var/log/mesapp.log | tail -20
```

4. 测试文件写入
```bash
touch /volume2/MES/files/photos/test.txt
```

**解决方案：**
- 清理存储空间
- 修复目录权限
- 检查网络连接
- 增加上传超时时间

### 5.5 Web界面无法访问

**症状：** 浏览器无法打开Web管理界面

**排查步骤：**

1. 检查服务状态
```bash
sudo systemctl status mesapp
```

2. 检查端口监听
```bash
netstat -tuln | grep 8891
```

3. 测试本地访问
```bash
curl -I http://localhost:8891
```

4. 检查防火墙
```bash
sudo iptables -L -n | grep 8891
```

**解决方案：**
- 重启服务
- 开放防火墙端口
- 检查网络配置
- 清除浏览器缓存

---

## 常见问题

### Q1: 如何重置管理员密码？

**答：** 管理员密码由群晖账户系统管理，请在群晖DSM中重置密码。

### Q2: 数据库文件损坏怎么办？

**答：** 
1. 停止服务
2. 从备份恢复数据库
3. 如无备份，尝试使用SQLite恢复工具

### Q3: 如何迁移到新服务器？

**答：** 
1. 在新服务器上安装系统
2. 恢复完整备份
3. 更新配置文件中的服务器地址
4. 测试所有功能

### Q4: 如何升级系统？

**答：** 
1. 创建完整备份
2. 停止服务
3. 上传新版本文件
4. 运行数据库迁移脚本
5. 启动服务并测试

### Q5: 日志文件太大怎么办？

**答：** 
```bash
# 配置日志轮转
sudo nano /etc/logrotate.d/mesapp

# 添加配置
/var/log/mesapp.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## 紧急联系

### 技术支持

**IT支持部门**
- 电话：内线 XXX
- 邮箱：it-support@company.com
- 工作时间：周一至周五 8:00-17:00

**系统管理员**
- 姓名：[管理员姓名]
- 电话：[联系电话]
- 邮箱：[邮箱地址]
- 24小时紧急电话：[紧急电话]

### 供应商支持

**软件开发商**
- 公司：[公司名称]
- 联系人：[联系人]
- 电话：[电话]
- 邮箱：[邮箱]

### 紧急处理流程

1. **发现问题** → 记录问题现象和时间
2. **初步排查** → 按照故障排除指南操作
3. **联系支持** → 如无法解决，联系技术支持
4. **问题升级** → 重大问题升级到系统管理员
5. **记录归档** → 问题解决后记录处理过程

---

## 附录

### A. 系统文件位置

| 类型 | 路径 |
|------|------|
| 应用目录 | /volume2/MES/app_web |
| 数据目录 | /volume2/MES/data |
| 文件存储 | /volume2/MES/files |
| 备份目录 | /volume2/MES/backups |
| 日志文件 | /var/log/mesapp.log |
| 审计日志 | /var/log/mesapp_audit.log |
| 服务文件 | /etc/systemd/system/mesapp.service |

### B. 常用命令速查

```bash
# 服务管理
sudo systemctl start|stop|restart|status mesapp

# 日志查看
sudo tail -f /var/log/mesapp.log

# 数据库备份
sqlite3 /volume2/MES/data/users.db ".backup backup.db"

# 检查磁盘空间
df -h /volume2/MES

# 检查端口
netstat -tuln | grep 8891

# 测试API
curl http://172.16.30.2:8891/api/h2/health
```

---

**文档版本：** 1.0  
**更新日期：** 2025年1月15日  
**维护团队：** IT运维部门
