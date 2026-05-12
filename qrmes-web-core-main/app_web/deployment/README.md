# QR MES 系统部署目录

> 警告
> 本目录是历史的独立服务器/生产部署方案，不适用于当前 NAS 测试环境 `172.16.30.2:8891`。
> 当前测试环境的正确目标目录是 `/volume2/MES/test/app_web`，请使用 [docs/skills/mes-update-nas-sync/SKILL.md](/Users/mini/QRTestScanner-clean/docs/skills/mes-update-nas-sync/SKILL.md) 和 [docs/2026-02-19-openclaw-codex-handoff.md](/Users/mini/QRTestScanner-clean/docs/2026-02-19-openclaw-codex-handoff.md)。
> 本目录下的 `deploy.sh` / `deploy.ps1` 现在要求显式确认历史流程，避免误发到当前测试环境。

本目录包含 QR MES 系统的完整部署配置和脚本，用于将应用部署到独立服务器并实现与群晖 NAS 的存储分离。

---

## 📁 目录结构

```
deployment/
├── README.md                      # 本文件
├── DEPLOYMENT_GUIDE.md            # 详细部署指南
├── docker-compose.yml             # Docker Compose 编排配置
├── Dockerfile                     # Flask 应用容器化配置
├── .env.example                   # 环境变量配置模板
├── nginx/                         # Nginx 配置目录
│   ├── nginx.conf                 # Nginx 主配置
│   ├── conf.d/
│   │   └── default.conf           # 站点配置
│   └── ssl/                       # SSL 证书目录（需要时创建）
├── scripts/                       # 部署脚本
│   ├── deploy.sh                  # 一键部署脚本
│   ├── mount-nas.sh               # NAS 挂载脚本
│   └── backup.sh                  # 备份脚本（待创建）
└── data/                          # 持久化数据目录（运行时创建）
    ├── databases/                 # SQLite 数据库
    ├── logs/                      # 应用日志
    ├── cache/                     # 缓存数据
    ├── config/                    # 配置文件
    └── redis/                     # Redis 数据
```

---

## 🚀 快速开始

### 方式一：使用一键部署脚本（推荐）

在 Ubuntu 服务器上执行：

```bash
# 1. 上传部署文件到服务器
scp -r deployment/ your_username@server_ip:/tmp/

# 2. SSH 登录服务器
ssh your_username@server_ip

# 3. 进入部署目录
cd /tmp/deployment

# 4. 编辑 NAS 挂载脚本中的配置
sudo vim scripts/mount-nas.sh
# 修改 NAS_SERVER, NAS_USERNAME, NAS_PASSWORD 等参数

# 5. 运行一键部署脚本
sudo bash scripts/deploy.sh
```

脚本会自动完成：
- ✅ 安装 Docker 和 Docker Compose
- ✅ 配置 NAS 挂载
- ✅ 创建应用目录
- ✅ 配置环境变量
- ✅ 构建并启动容器

### 方式二：手动部署

参考 [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) 中的详细步骤。

---

## 📋 前置要求

### 服务器要求

- **操作系统**: Ubuntu 22.04 LTS 或 CentOS 8+
- **CPU**: 2 核+（推荐 4 核）
- **内存**: 4GB+（推荐 8GB）
- **磁盘**: 50GB+ SSD
- **网络**: 千兆网卡（推荐万兆）

### 网络要求

- ✅ 服务器与 NAS 在同一内网
- ✅ 服务器能访问 NAS SMB 端口 (445)
- ✅ 服务器能访问群晖 API (5001)
- ✅ 客户端能访问服务器 80/443 端口

### 软件要求

- Docker 20.10+
- Docker Compose 2.0+
- Git（可选，用于克隆代码）

---

## ⚙️ 配置说明

### 1. 环境变量配置

复制环境变量模板：

```bash
cp .env.example .env
vim .env
```

必须修改的配置项：

```bash
# Flask 密钥（使用命令生成：openssl rand -base64 32）
FLASK_SECRET_KEY=your_secret_key_here

# NAS 连接配置
NAS_SERVER=172.16.30.2
NAS_USERNAME=your_nas_username
NAS_PASSWORD=your_nas_password
NAS_HOST_MOUNT_PATH=/mnt/nas-qrmes

# 群晖 API 配置
SYNOLOGY_API_URL=https://172.16.30.2:5001
```

### 2. NAS 挂载配置

编辑 `scripts/mount-nas.sh`：

```bash
NAS_SERVER="172.16.30.2"        # NAS 服务器 IP
NAS_SHARE="mes"                 # NAS 共享名
NAS_USERNAME="your_username"    # NAS 用户名
NAS_PASSWORD="your_password"    # NAS 密码
MOUNT_POINT="/mnt/nas-qrmes"    # 挂载点路径
```

### 3. Nginx 配置

如果需要自定义 Nginx 配置，编辑：

- `nginx/nginx.conf` - 全局配置
- `nginx/conf.d/default.conf` - 站点配置

---

## 🔧 常用命令

### 容器管理

```bash
# 进入部署目录
cd /opt/qrmes/QRTestScanner/app_web/deployment

# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f

# 查看容器状态
docker-compose ps

# 进入容器
docker exec -it qrmes-flask-app bash
```

### NAS 挂载管理

```bash
# 查看挂载状态
mount | grep nas-qrmes

# 手动挂载
sudo mount -a

# 手动卸载
sudo umount /mnt/nas-qrmes

# 重新运行挂载脚本
sudo bash scripts/mount-nas.sh
```

### 日志查看

```bash
# 应用日志
docker-compose logs -f flask-app

# Nginx 访问日志
tail -f data/logs/nginx/qrmes-access.log

# Nginx 错误日志
tail -f data/logs/nginx/qrmes-error.log

# Redis 日志
docker-compose logs -f redis
```

---

## 🐛 故障排查

### 问题 1：容器无法启动

```bash
# 查看详细日志
docker-compose logs flask-app

# 检查端口占用
sudo netstat -tlnp | grep 5001

# 检查环境变量
cat .env
```

### 问题 2：无法访问照片

```bash
# 检查 NAS 挂载
mount | grep nas-qrmes
ls -la /mnt/nas-qrmes/QRMES/picture

# 检查容器内挂载
docker exec qrmes-flask-app ls /app/nas-mount/qrmes/picture

# 重新挂载 NAS
sudo umount /mnt/nas-qrmes
sudo mount -a
```

### 问题 3：数据库锁表

```bash
# 检查数据库文件权限
ls -la data/databases/

# 重启 Flask 应用
docker-compose restart flask-app

# 如果持续出现，考虑升级到 PostgreSQL
```

更多问题请查看 [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) 的"故障排查"章节。

---

## 📚 相关文档

- [deployment_architecture.md](../docs/deployment_architecture.md) - 部署架构设计
- [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - 详细部署指南
- [architecture_analysis_and_roadmap.md](../docs/architecture_analysis_and_roadmap.md) - 系统架构分析与演进路线图

---

## 🔐 安全建议

1. **修改默认密码**: 确保所有密码都是强密码
2. **限制访问**: 配置防火墙白名单
3. **启用 HTTPS**: 生产环境建议启用 SSL/TLS
4. **定期备份**: 配置自动备份脚本
5. **更新系统**: 定期更新系统和 Docker

---

## 📞 支持

如有问题，请参考：

1. [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - 详细部署指南
2. [故障排查](#-故障排查) - 常见问题解决方案
3. 项目 Issues 页面

---

**创建日期**: 2025-12-04  
**最后更新**: 2025-12-04  
**维护者**: Cascade AI
