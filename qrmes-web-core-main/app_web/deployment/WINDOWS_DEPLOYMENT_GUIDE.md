# Windows环境部署指南

> 警告
> 本文档描述的是历史独立服务器/生产部署流程，不适用于当前 NAS 测试环境 `172.16.30.2:8891`。
> 当前测试环境请部署到 `/volume2/MES/test/app_web`，并使用 [docs/skills/mes-update-nas-sync/SKILL.md](/Users/mini/QRTestScanner-clean/docs/skills/mes-update-nas-sync/SKILL.md) 与 [docs/2026-02-19-openclaw-codex-handoff.md](/Users/mini/QRTestScanner-clean/docs/2026-02-19-openclaw-codex-handoff.md) 中的测试环境流程。
> 下文保留，仅供需要维护历史 `/volume2/MES/app_web` 独立部署的场景参考。

## 说明

由于你在Windows环境下工作，原有的Shell脚本（.sh文件）无法直接运行。本指南提供历史独立部署流程在Windows环境下的操作方式。

---

## 方案一：使用Git Bash（推荐）

如果你已安装Git for Windows，可以使用Git Bash运行Shell脚本。

### 1. 打开Git Bash
在项目目录右键选择 "Git Bash Here"

### 2. 运行脚本
```bash
cd app_web/deployment
chmod +x *.sh
./synology_api_setup.sh
./deploy.sh
```

---

## 方案二：使用WSL（Windows Subsystem for Linux）

### 1. 启用WSL
```powershell
# 以管理员身份运行PowerShell
wsl --install
```

### 2. 在WSL中运行
```bash
cd /mnt/f/GitHub/hours/QRTestScanner/app_web/deployment
chmod +x *.sh
./synology_api_setup.sh
./deploy.sh
```

---

## 方案三：手动部署（适用于Windows）

如果无法使用上述方案，可以手动执行部署步骤。

### 步骤1：准备配置文件

创建配置文件 `app_web/deployment/synology_config.env`：

```env
# 群晖服务器配置
SYNOLOGY_HOST=172.16.30.2
SYNOLOGY_PORT=5000
SYNOLOGY_USE_HTTPS=false

# API配置
SYNOLOGY_API_VERSION=6
SYNOLOGY_TIMEOUT=10

# WebDAV配置
WEBDAV_URL=http://172.16.30.2:5005
WEBDAV_BASE_PATH=/MES/files

# 应用用户凭据（请填写）
SYNOLOGY_USERNAME=your_username
SYNOLOGY_PASSWORD=your_password

# 文件存储配置
USE_WEBDAV=false
NAS_LOCAL_BASE_PATH=/volume2/MES/files
```

### 步骤2：使用SSH连接到NAS

使用SSH客户端（如PuTTY或Windows Terminal）连接到群晖NAS：

```
主机：172.16.30.2
用户名：panovation
端口：22
```

### 步骤3：在NAS上创建目录结构

连接到NAS后，执行以下命令：

```bash
# 创建应用目录
sudo mkdir -p /volume2/MES/app_web
sudo mkdir -p /volume2/MES/app_web/static
sudo mkdir -p /volume2/MES/app_web/templates
sudo mkdir -p /volume2/MES/app_web/deployment

# 创建数据目录
sudo mkdir -p /volume2/MES/data

# 创建文件存储目录
sudo mkdir -p /volume2/MES/files/projects
sudo mkdir -p /volume2/MES/files/record
sudo mkdir -p /volume2/MES/files/photos

# 创建备份目录
sudo mkdir -p /volume2/MES/backups

# 设置权限
sudo chown -R panovation:users /volume2/MES
sudo chmod -R 755 /volume2/MES
```

### 步骤4：初始化数据库

在NAS上执行：

```bash
cd /volume2/MES/app_web/deployment

# 初始化用户数据库
sqlite3 /volume2/MES/data/users.db < database_setup.sql
```

### 步骤5：上传应用文件

使用WinSCP或其他SFTP客户端上传文件：

**连接信息：**
- 协议：SFTP
- 主机：172.16.30.2
- 端口：22
- 用户名：panovation

**上传以下文件到 `/volume2/MES/app_web/`：**
- mesapp.py
- config.py
- auth.py
- data_access_layer.py
- permission_service.py
- user_management_service.py
- synology_auth_client.py
- photo_api.py
- process_config_api.py
- project_config_manager.py
- config_history_manager.py
- h2_api.py
- error_handler.py
- security_validator.py
- webdav_client_v2.py
- smb_client.py
- requirements.txt

**上传目录：**
- static/ → /volume2/MES/app_web/static/
- templates/ → /volume2/MES/app_web/templates/
- deployment/ → /volume2/MES/app_web/deployment/

### 步骤6：安装Python依赖

在NAS上执行：

```bash
cd /volume2/MES/app_web
pip3 install -r requirements.txt --user
```

### 步骤7：配置systemd服务

在NAS上创建服务文件：

```bash
sudo nano /etc/systemd/system/mesapp.service
```

输入以下内容：

```ini
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
```

保存并退出（Ctrl+X, Y, Enter）

### 步骤8：启动服务

```bash
# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用开机自启
sudo systemctl enable mesapp

# 启动服务
sudo systemctl start mesapp

# 查看状态
sudo systemctl status mesapp
```

### 步骤9：验证部署

在Windows PowerShell中测试：

```powershell
# 测试健康检查端点
Invoke-WebRequest -Uri "http://172.16.30.2:8891/api/h2/health"
```

或使用浏览器访问：
```
http://172.16.30.2:8891
```

---

## 方案四：使用PowerShell脚本

我已经为你创建了PowerShell版本的部署脚本，请查看：
- `deploy.ps1` - PowerShell部署脚本

---

## 常见问题

### Q1: 如何使用WinSCP上传文件？

1. 下载并安装WinSCP：https://winscp.net/
2. 新建站点：
   - 文件协议：SFTP
   - 主机名：172.16.30.2
   - 端口号：22
   - 用户名：panovation
   - 密码：[你的密码]
3. 点击"登录"
4. 拖拽文件上传

### Q2: 如何使用PuTTY连接SSH？

1. 下载并安装PuTTY：https://www.putty.org/
2. 打开PuTTY
3. 输入主机名：172.16.30.2
4. 端口：22
5. 连接类型：SSH
6. 点击"Open"
7. 输入用户名和密码

### Q3: 如何查看日志？

在SSH连接中执行：
```bash
sudo tail -f /var/log/mesapp.log
```

### Q4: 如何重启服务？

```bash
sudo systemctl restart mesapp
```

---

## 推荐工具

### SSH客户端
- **Windows Terminal**（推荐）- Windows 11自带
- **PuTTY** - 经典SSH客户端
- **MobaXterm** - 功能强大的终端工具

### 文件传输工具
- **WinSCP**（推荐）- 图形化SFTP客户端
- **FileZilla** - 支持多种协议
- **MobaXterm** - 内置文件传输功能

### 文本编辑器
- **VS Code** - 支持远程SSH编辑
- **Notepad++** - 轻量级编辑器

---

## 下一步

部署完成后，你可以：

1. **访问Web管理界面**
   ```
   http://172.16.30.2:8891
   ```

2. **查看文档**
   - 用户操作指南：`app_web/docs/USER_GUIDE_*.md`
   - API文档：`app_web/docs/API_DOCUMENTATION.md`
   - 维护指南：`app_web/docs/MAINTENANCE_GUIDE.md`

3. **配置移动应用**
   - 在Android应用中配置服务器地址：172.16.30.2:8891

---

**需要帮助？**

如果遇到问题，请提供：
1. 错误信息截图
2. 日志内容
3. 执行的命令

我会帮你解决！
