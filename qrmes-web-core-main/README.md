# QRTestScanner / MES

QRTestScanner 是一套用于 MES 场景的 Android 与 Web 联合系统。当前仓库只保存代码，运行数据保留在服务器本地目录，不纳入 Git。

## 当前架构

- Android 客户端：`app/`
- Web 后端：`app_web/`
- Git 仓库：`http://172.16.30.9/Xiaoai/mes_ubuntu`
- 目标服务器：`http://172.16.30.10:8891/`
- 服务器代码目录：`/volume2/mes_ubuntu`
- 服务器运行目录：`/volume2/qrmes`
- 服务器数据目录：`/volume2/MES/QRMES`

当前模式为“代码与数据分离”：

- Git 只管理 `QRTestScanner` 代码
- `QRMES` 中的数据库、图片、项目配置、APK 包等运行数据保留在服务器本地

## 主要功能

- APK 扫码识别、工序拍照、工序记录、质量工作台
- Web 端记录查询、用户管理、权限管理、日志管理、APK 日志查询
- AI 质检，支持在线模型与本地模型配置
- APK 在线检查更新与下载

## 目录说明

```text
app/                     Android 客户端
app_web/                 Flask Web 后端
scripts/                 部署与辅助脚本
docs/                    项目文档
```

## 本地开发

### Android

- 使用 Android Studio 打开项目根目录
- 主要代码在 `app/src/main/...`
- Release 包输出目录：`app/build/outputs/apk/release/`

### Web

- 后端主入口：`app_web/mesapp.py`
- 当前线上运行依赖的数据目录：`/volume2/MES/QRMES`

## 服务器部署

### 运行目录

- 代码：`/volume2/mes_ubuntu`
- 启动脚本：`/volume2/qrmes/start.sh`
- 停止脚本：`/volume2/qrmes/stop.sh`
- 状态脚本：`/volume2/qrmes/status.sh`
- 立即更新：`/volume2/qrmes/bin/update_now.sh`

### 自动部署

当前支持两种部署方式：

1. GitLab CI 直连部署  
   合并到 `main` 后，由 GitLab 通过 SSH 调用 `/volume2/qrmes/bin/update_now.sh`
2. 定时兜底部署  
   `.10` 服务器每天 `03:00` 自动执行 `/volume2/qrmes/bin/deploy_watch.sh`

### 部署脚本

- 仓库脚本：`scripts/deploy_from_gitlab.sh`
- 服务器脚本：`/volume2/qrmes/bin/deploy_from_gitlab.sh`

### 健康检查

```bash
curl http://172.16.30.10:8891/health
```

## Git 工作流

当前推荐流程：

1. 本地新建功能分支开发
2. 提交到 GitLab 分支
3. 发起 Merge Request
4. 合并到 `main`
5. 自动部署到 `.10`

说明：

- `main` 建议只允许合并，不允许直接 push
- GitLab CI 使用部署私钥直连 `.10`

## 数据说明

服务器本地数据目录为：

```text
/volume2/MES/QRMES
```

常见内容包括：

- `projects/` 项目配置 JSON
- `picture/` 图片
- `APK/` APK 发布包
- `web_users.db` 用户管理数据库
- 其他业务数据库与日志目录

## APK 发布

Release APK 由 Android Gradle 构建生成，当前命名规则类似：

```text
Panovation MesApp v1.2.87_087.apk
```

常用位置：

- 原始产物：`app/build/outputs/apk/release/`
- 桌面副本：`C:\Users\pc\Desktop\APK`
- 服务器更新目录：`/volume2/MES/QRMES/APK`

## 常用命令

### 服务器状态

```bash
/volume2/qrmes/status.sh
```

### 立即拉取并部署

```bash
/volume2/qrmes/bin/update_now.sh
```

### 查看服务健康状态

```bash
curl http://127.0.0.1:8891/health
```

## 备注

- 本仓库当前已切换为代码仓库，不再将 `QRMES` 数据目录纳入 Git。
- 线上服务启动位置已经切换到 `/volume2/mes_ubuntu/app_web`。

如与 `qrmes-shared-core` 同级放置，可先执行 `scripts/install_shared_core.sh` 安装共享层。

可用 `scripts/healthcheck.sh` 做本地健康检查。
