# 自动部署到服务器指南

## 📋 部署方式

### 方式1: 一键部署（推荐）

按 `Ctrl+Shift+P` → 输入 "Tasks: Run Task" → 选择：

**🚢 部署到服务器（SMB同步+重启）**
- 自动同步 `app_web` 文件夹到服务器
- 自动重启Python应用
- 完整的部署流程

### 方式2: 仅同步文件

**📦 仅同步文件到服务器（不重启）**
- 只同步文件，不重启应用
- 适合频繁修改时使用

### 方式3: 文件监控自动部署

**👁️ 启动文件监控自动部署**
- 自动监控 `app_web` 目录变化
- 文件修改后自动同步到服务器
- 适合开发调试时使用
- 按 `Ctrl+C` 停止监控

### 方式4: 运行PowerShell脚本

```powershell
# 完整部署（同步+重启）
.\deploy_to_server.ps1

# 仅同步文件
.\deploy_to_server_simple.ps1

# 启动文件监控
.\watch_and_deploy.ps1
```

## 🔧 配置信息

- **本地目录**: `app_web`
- **SMB共享路径**: `\\172.16.30.2\mes\app_web`
- **远程服务器路径**: `/volume2/MES/app_web`
- **Python命令**: `python3 mesapp.py`

## 📦 同步说明

### 包含的文件
- 所有 `.py` Python源文件
- 所有 `.html` 模板文件
- 所有 `.js` / `.css` 静态文件
- 配置文件和数据文件

### 排除的文件/目录
- `__pycache__` - Python缓存
- `.pytest_cache` - 测试缓存
- `.venv` / `venv` - 虚拟环境
- `.git` - Git仓库
- `node_modules` - Node模块
- `*.pyc` / `*.pyo` - 编译的Python文件
- `*.log` - 日志文件

## 🚀 部署流程

1. **检查SMB连接** - 确认可以访问 `\\172.16.30.2\mes\app_web`
2. **同步文件** - 使用robocopy镜像同步（增量更新）
3. **停止旧应用** - `pkill -f mesapp.py`
4. **启动新应用** - `python3 mesapp.py`（后台运行）
5. **确认状态** - 检查应用是否正常启动

## 📊 查看应用状态

### 检查应用是否运行
```powershell
ssh -p 30001 panovation@172.16.30.2 "ps aux | grep mesapp.py"
```

### 查看应用日志
```powershell
ssh -p 30001 panovation@172.16.30.2 "tail -f /volume2/MES/app_web/mesapp.log"
```

或使用Kiro任务：
- **📊 检查远程Python应用状态**
- **🚀 启动远程Python应用**（查看实时输出）

## 🔐 权限要求

### SMB共享权限
- 需要对 `\\172.16.30.2\mes\app_web` 有读写权限
- 如果无法访问，请检查网络凭据

### SSH权限
- 需要SSH访问权限
- 密码: `Clt2020clt`
- 或配置SSH密钥认证

## 🐛 故障排除

### SMB共享无法访问

1. 检查网络连接：
   ```powershell
   Test-NetConnection 172.16.30.2 -Port 445
   ```

2. 手动挂载SMB共享：
   ```powershell
   net use \\172.16.30.2\mes /user:panovation Clt2020clt
   ```

3. 在文件资源管理器中访问：
   - 打开 `\\172.16.30.2\mes\app_web`
   - 输入凭据

### 文件同步失败

- 检查本地 `app_web` 目录是否存在
- 确认有足够的磁盘空间
- 检查文件是否被占用

### 应用启动失败

1. 手动SSH连接检查：
   ```bash
   ssh -p 30001 panovation@172.16.30.2
   cd /volume2/MES/app_web
   source .venv/bin/activate
   python3 mesapp.py
   ```

2. 查看错误日志：
   ```bash
   tail -100 /volume2/MES/app_web/mesapp.log
   ```

3. 检查虚拟环境：
   ```bash
   ls -la /volume2/MES/app_web/.venv
   ```

## 💡 开发工作流建议

### 快速迭代开发
1. 启动文件监控：运行 "👁️ 启动文件监控自动部署"
2. 修改代码，保存后自动同步
3. 手动重启应用查看效果

### 正式部署
1. 运行 "🚢 部署到服务器（SMB同步+重启）"
2. 等待部署完成
3. 检查应用状态和日志

### 仅更新文件（不影响运行中的应用）
1. 运行 "📦 仅同步文件到服务器（不重启）"
2. 适合更新静态文件、模板等

## 📚 相关文件

- `deploy_to_server.ps1` - 完整部署脚本
- `deploy_to_server_simple.ps1` - 简单同步脚本
- `watch_and_deploy.ps1` - 文件监控脚本
- `.vscode/tasks.json` - Kiro任务配置

## 🎯 快速开始

最简单的方式：

1. 确保可以访问 `\\172.16.30.2\mes\app_web`
2. 按 `Ctrl+Shift+P` → "Tasks: Run Task"
3. 选择 "🚢 部署到服务器（SMB同步+重启）"
4. 等待完成！
