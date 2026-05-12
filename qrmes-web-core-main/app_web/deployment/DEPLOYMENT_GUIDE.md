# QR MES 系统部署指南

> 警告
> 本文档针对独立 Ubuntu 服务器 + Docker 的历史部署架构，不是当前 NAS 测试环境 `172.16.30.2:8891` 的发布说明。
> 当前测试环境请部署到 `/volume2/MES/test/app_web`，并使用 [docs/skills/mes-update-nas-sync/SKILL.md](/Users/mini/QRTestScanner-clean/docs/skills/mes-update-nas-sync/SKILL.md) 与 [docs/2026-02-19-openclaw-codex-handoff.md](/Users/mini/QRTestScanner-clean/docs/2026-02-19-openclaw-codex-handoff.md)。

> **目标环境**: Ubuntu 22.04 LTS Server  
> **部署方式**: Docker + Docker Compose  
> **存储架构**: Web 服务器 + 群晖 NAS 分离  
> **预计时间**: 2-4 小时

---

## 目录

1. [前置准备](#1-前置准备)
2. [服务器环境配置](#2-服务器环境配置)
3. [NAS 挂载配置](#3-nas-挂载配置)
4. [应用部署](#4-应用部署)
5. [数据迁移](#5-数据迁移)
6. [验证测试](#6-验证测试)
7. [生产切换](#7-生产切换)
8. [故障排查](#8-故障排查)
9. [日常运维](#9-日常运维)

---

## 1. 前置准备

### 1.1 硬件要求

| 项目 | 最低配置 | 推荐配置 | 说明 |
|------|---------|---------|------|
| CPU | 2 核 | 4 核+ | 支持虚拟化 |
| 内存 | 4GB | 8GB+ | Docker 需要足够内存 |
| 磁盘 | 50GB SSD | 100GB+ SSD | 系统 + 数据库 + 日志 |
| 网络 | 千兆网卡 | 万兆网卡 | 连接 NAS |

### 1.2 网络要求

```
✅ 服务器与 NAS 在同一内网（172.16.30.0/24）
✅ 服务器能访问 NAS SMB 445 端口
✅ 服务器能访问群晖 API（5001 端口）
✅ 客户端能访问服务器 80/443 端口
```

### 1.3 准备清单

- [ ] 服务器已安装 Ubuntu 22.04 LTS
- [ ] 服务器已配置静态 IP（如 172.16.30.10）
- [ ] 已获取 NAS 访问凭据（用户名/密码）
- [ ] 已备份 NAS 上的所有数据
- [ ] 已备份当前系统的数据库文件

---

## 2. 服务器环境配置

### 2.1 更新系统

```bash
# SSH 登录服务器
ssh your_username@172.16.30.10

# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装必要工具
sudo apt install -y \
    git \
    curl \
    wget \
    vim \
    htop \
    net-tools \
    cifs-utils
```

### 2.2 安装 Docker

```bash
# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 将当前用户加入 docker 组
sudo usermod -aG docker $USER

# 退出重新登录使配置生效
exit
# 重新 SSH 登录

# 验证 Docker 安装
docker --version
```

### 2.3 安装 Docker Compose

```bash
# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# 添加执行权限
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker-compose --version
```

### 2.4 配置防火墙

```bash
# 如果使用 ufw
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp  # SSH
sudo ufw enable

# 或者使用 iptables
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
```

---

## 3. NAS 挂载配置

### 3.1 创建挂载点

```bash
# 创建 NAS 挂载目录
sudo mkdir -p /mnt/nas-qrmes

# 创建凭据文件（更安全）
sudo vim /etc/nas-credentials
```

在 `/etc/nas-credentials` 中添加：

```ini
username=your_nas_username
password=your_nas_password
domain=WORKGROUP
```

保存后设置权限：

```bash
sudo chmod 600 /etc/nas-credentials
```

### 3.2 配置自动挂载

编辑 `/etc/fstab`：

```bash
sudo vim /etc/fstab
```

添加以下行（根据实际情况修改）：

```bash
//172.16.30.2/mes /mnt/nas-qrmes cifs credentials=/etc/nas-credentials,iocharset=utf8,file_mode=0777,dir_mode=0777,vers=3.0 0 0
```

### 3.3 测试挂载

```bash
# 手动挂载测试
sudo mount -a

# 验证挂载
df -h | grep nas-qrmes
ls -la /mnt/nas-qrmes/QRMES

# 应该能看到 picture, projects.json 等目录和文件
```

### 3.4 挂载故障排查

如果挂载失败：

```bash
# 检查网络连通性
ping 172.16.30.2

# 测试 SMB 端口
telnet 172.16.30.2 445

# 手动挂载查看详细错误
sudo mount -t cifs -o username=xxx,password=xxx //172.16.30.2/mes /mnt/nas-qrmes

# 查看系统日志
sudo dmesg | tail -20
```

---

## 4. 应用部署

### 4.1 创建应用目录

```bash
# 创建应用根目录
sudo mkdir -p /opt/qrmes
sudo chown -R $USER:$USER /opt/qrmes
cd /opt/qrmes
```

### 4.2 克隆代码

```bash
# 从 GitLab 克隆代码
git clone http://your-gitlab-server/path/to/QRTestScanner.git
cd QRTestScanner/app_web

# 或者通过 SCP 上传代码
# scp -r E:\gitlab\QRTestScanner\app_web your_username@172.16.30.10:/opt/qrmes/
```

### 4.3 配置环境变量

```bash
# 进入部署目录
cd /opt/qrmes/QRTestScanner/app_web/deployment

# 复制环境变量模板
cp .env.example .env

# 编辑环境变量
vim .env
```

必须修改的配置项：

```bash
# Flask 密钥（使用下面命令生成）
FLASK_SECRET_KEY=$(openssl rand -base64 32)

# NAS 凭据
NAS_USERNAME=your_actual_username
NAS_PASSWORD=your_actual_password

# NAS 挂载点（与 fstab 中的路径一致）
NAS_HOST_MOUNT_PATH=/mnt/nas-qrmes

# 其他根据实际情况修改
SYNOLOGY_API_URL=https://172.16.30.2:5001
```

### 4.4 创建数据目录

```bash
# 在部署目录下创建持久化数据目录
mkdir -p data/databases
mkdir -p data/logs/nginx
mkdir -p data/cache
mkdir -p data/config
mkdir -p data/redis

# 创建 NAS 挂载的软链接（指向实际挂载点）
ln -s /mnt/nas-qrmes nas-mount
```

### 4.5 构建并启动容器

```bash
# 构建镜像
docker-compose build

# 启动服务（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 查看容器状态
docker-compose ps
```

预期输出：

```
NAME                COMMAND                  SERVICE             STATUS
qrmes-flask-app    "gunicorn --bind 0.0…"   flask-app           Up (healthy)
qrmes-nginx        "/docker-entrypoint.…"   nginx               Up (healthy)
qrmes-redis        "docker-entrypoint.s…"   redis               Up (healthy)
```

---

## 5. 数据迁移

### 5.1 迁移 SQLite 数据库

从旧环境（NAS 或其他服务器）复制数据库文件：

```bash
# 在旧服务器上
cd /path/to/old/databases
tar czf databases-backup.tar.gz *.db

# 传输到新服务器
scp databases-backup.tar.gz your_username@172.16.30.10:/tmp/

# 在新服务器上解压
cd /opt/qrmes/QRTestScanner/app_web/deployment/data/databases
tar xzf /tmp/databases-backup.tar.gz

# 验证文件
ls -lh
# 应该看到 web_users.db, test_reports.db 等文件
```

### 5.2 验证 NAS 数据

```bash
# 检查照片目录
ls /mnt/nas-qrmes/QRMES/picture/ | head -20

# 检查配置文件
cat /mnt/nas-qrmes/QRMES/projects.json

# 验证容器内能访问
docker exec qrmes-flask-app ls /app/nas-mount/qrmes/picture
```

### 5.3 重启应用

```bash
docker-compose restart flask-app
docker-compose logs -f flask-app
```

---

## 6. 验证测试

### 6.1 健康检查

```bash
# 检查 Flask 应用
curl http://localhost:5001/health

# 检查 Nginx
curl http://localhost/health

# 检查 Redis
docker exec qrmes-redis redis-cli ping
```

### 6.2 功能测试

在浏览器中打开：`http://172.16.30.10`

测试清单：

- [ ] 登录功能正常
- [ ] 能看到项目列表
- [ ] 照片能正常加载和显示
- [ ] 能创建新的测试记录
- [ ] 能上传照片
- [ ] 能生成报告
- [ ] 数据库读写正常

### 6.3 性能测试

```bash
# 简单压力测试（可选）
sudo apt install -y apache2-utils

# 测试首页（100 个请求，10 个并发）
ab -n 100 -c 10 http://172.16.30.10/

# 查看响应时间
```

---

## 7. 生产切换

### 7.1 DNS/IP 切换准备

如果客户端通过域名访问：

```bash
# 更新 DNS 记录，将域名指向新服务器 IP
# 或者修改客户端的 hosts 文件

# Windows 客户端修改 C:\Windows\System32\drivers\etc\hosts
# 添加：
# 172.16.30.10  qrmes.company.local
```

### 7.2 切换步骤

1. **通知用户**：系统将在 X 时间进行维护升级
2. **停止旧服务**：在 NAS 或旧服务器上停止应用
3. **最后数据同步**：确保数据库是最新的
4. **切换 IP/DNS**：将客户端指向新服务器
5. **监控运行**：观察 1-2 小时，确保稳定

### 7.3 回滚方案

如果新系统出现问题：

```bash
# 停止新服务
docker-compose down

# 客户端改回旧服务器地址
# 启动旧服务
```

---

## 8. 故障排查

### 8.1 常见问题

#### 问题 1：容器无法启动

```bash
# 查看详细日志
docker-compose logs flask-app

# 常见原因：
# - 端口被占用：sudo netstat -tlnp | grep 5001
# - 环境变量配置错误：cat .env
# - NAS 挂载失败：df -h | grep nas
```

#### 问题 2：无法访问照片

```bash
# 检查 NAS 挂载
mount | grep nas-qrmes

# 检查容器内挂载
docker exec qrmes-flask-app ls /app/nas-mount/qrmes/picture

# 检查权限
ls -la /mnt/nas-qrmes/QRMES/picture
```

#### 问题 3：数据库锁表

```bash
# 检查数据库文件权限
ls -la /opt/qrmes/deployment/data/databases/

# 检查是否有其他进程访问
sudo lsof | grep web_users.db

# 重启 Flask 应用
docker-compose restart flask-app
```

### 8.2 查看日志

```bash
# 应用日志
docker-compose logs -f flask-app

# Nginx 访问日志
tail -f /opt/qrmes/deployment/data/logs/nginx/qrmes-access.log

# Nginx 错误日志
tail -f /opt/qrmes/deployment/data/logs/nginx/qrmes-error.log

# 系统日志
sudo journalctl -u docker -f
```

---

## 9. 日常运维

### 9.1 启动/停止服务

```bash
# 停止服务
docker-compose down

# 启动服务
docker-compose up -d

# 重启服务
docker-compose restart

# 查看状态
docker-compose ps
```

### 9.2 备份策略

#### 数据库备份

```bash
#!/bin/bash
# backup-db.sh

BACKUP_DIR="/opt/qrmes/backups/databases"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
cd /opt/qrmes/deployment/data/databases
tar czf $BACKUP_DIR/databases-$DATE.tar.gz *.db

# 保留最近 30 天的备份
find $BACKUP_DIR -name "databases-*.tar.gz" -mtime +30 -delete
```

#### NAS 备份

群晖 NAS 自带快照和备份功能，建议配置：

- 每天凌晨自动快照
- 每周完整备份到外部存储
- 重要数据启用版本控制

### 9.3 日志轮转

```bash
# 创建 logrotate 配置
sudo vim /etc/logrotate.d/qrmes

# 内容：
/opt/qrmes/deployment/data/logs/**/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    missingok
    create 644 root root
}
```

### 9.4 监控建议

使用 Prometheus + Grafana（可选）：

```bash
# 取消 docker-compose.yml 中监控服务的注释
vim docker-compose.yml

# 重新启动
docker-compose up -d prometheus grafana

# 访问 Grafana
# http://172.16.30.10:3000
# 默认用户名/密码：admin/admin
```

### 9.5 更新应用

```bash
# 拉取最新代码
cd /opt/qrmes/QRTestScanner
git pull origin main

# 重新构建并重启
cd app_web/deployment
docker-compose build
docker-compose up -d

# 查看日志确认
docker-compose logs -f
```

---

## 10. 进阶配置

### 10.1 HTTPS 配置

安装 Let's Encrypt 证书：

```bash
# 安装 certbot
sudo apt install -y certbot

# 生成证书（需要域名）
sudo certbot certonly --standalone -d your-domain.com

# 将证书复制到 nginx 目录
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem \
    /opt/qrmes/deployment/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem \
    /opt/qrmes/deployment/nginx/ssl/key.pem

# 取消 nginx 配置中 HTTPS 的注释
vim nginx/conf.d/default.conf

# 重启 nginx
docker-compose restart nginx
```

### 10.2 配置域名

在路由器或 DNS 服务器上：

```
qrmes.company.local  →  172.16.30.10
```

---

## 附录

### A. 快速命令参考

```bash
# 查看所有容器状态
docker-compose ps

# 查看实时日志
docker-compose logs -f

# 重启单个服务
docker-compose restart flask-app

# 进入容器 shell
docker exec -it qrmes-flask-app bash

# 查看资源使用
docker stats

# 清理未使用的镜像和容器
docker system prune -a
```

### B. 性能优化建议

1. **数据库优化**：后续升级到 PostgreSQL
2. **缓存优化**：调整 Redis 内存大小
3. **Nginx 调优**：根据并发量调整 worker 数量
4. **网络优化**：使用万兆网卡连接 NAS
5. **SSD 优化**：数据库放在 SSD 上

### C. 安全加固

1. 修改 SSH 默认端口
2. 配置防火墙白名单
3. 定期更新系统和 Docker
4. 使用强密码和密钥认证
5. 限制 Docker API 访问

---

**文档维护者**: Cascade AI  
**创建日期**: 2025-12-04  
**最后更新**: 2025-12-04  
**版本**: v1.0
