# QR测试扫描器项目规格文档

## 项目概述
QR测试扫描器是一个用于管理和配置各种工程机械项目的系统，支持产品类型管理、工艺步骤配置和版本控制。

## 版本历史

### 版本 3.9 - 2025年12月04日 11:32:00

#### 需求描述
修复 H2 数据库查询时时间格式兼容性问题

#### 问题分析

**旧数据使用格式化日期字符串**
- **错误日志**: `invalid literal for int() with base 10: '2025-12-04 10:31:45'`
- **原因**: 数据库中部分记录的 `scan_time` 是日期字符串，不是毫秒时间戳
- **影响**: 时间过滤和格式转换失败，导致 H2 查询降级到 CSV

#### 修改内容

**服务端 - `h2_api.py`**
- `format_timestamp_to_china_time()` 兼容字符串日期和毫秒时间戳

**服务端 - `mesapp.py`**
- 添加 `parse_scan_time()` 函数，智能解析两种时间格式
- 时间过滤逻辑使用新函数

---

### 版本 3.8 - 2025年12月04日 11:27:00

#### 需求描述
修复扫描数据的时间和物料名称显示错误

#### 问题分析

**问题1：扫描时间显示为 1970-01-01**
- **原因**: 客户端发送字符串时间戳，服务端未正确转换为整数
- **表现**: 时间戳被存储为 0 或无效值

**问题2：组件名称丢失，只显示序列号**
- **原因**: CSV 解析逻辑错误，把数据按 2 个一组处理
- **正确格式**: 表头包含物料名称，数据行包含序列号

#### 修改内容

**客户端 - `ProductRecordRepository.kt`**
- 修复 CSV 解析：从表头获取物料名称，从数据行获取序列号
- 修复时间戳：发送毫秒时间戳 `System.currentTimeMillis()`

**服务端 - `mesapp.py`**
- 修复 `scan_time` 处理：确保转换为整数毫秒时间戳
- 支持字符串数字、整数、浮点数等多种输入格式

---

### 版本 3.7 - 2025年12月04日 10:51:00

#### 需求描述
修复 Web 端数据查询页面无法查询到数据的问题

#### 问题分析

**查询"全部项目"时使用硬编码的项目列表**
- **原因**: `get_stats()` 没有返回 `recent_records`，代码回退到硬编码的项目列表
- **硬编码列表**: `['柳工双20', '柳工物流园双12', '测试项目']`
- **用户实际项目**: `三一重卡310油冷电机` 等不在列表中

#### 修改内容

**服务端 - `mesapp.py`**
- 从 `top_projects`（统计信息）动态获取数据库中实际存在的项目列表
- 遍历所有项目查询记录，不再使用硬编码列表

---

### 版本 3.6 - 2025年12月04日 10:39:00

#### 需求描述
修复 `/api/projects` POST 仍然返回 401 的问题（重启服务器后仍报错）

#### 问题分析

**`require_permission` 装饰器不支持 Basic Auth**
- **原因**: `require_permission` 只检查 `session['user']`，没有检查 `request.mobile_user`
- **影响**: 即使 `login_required` 通过了 Basic Auth，`require_permission` 仍然会返回 401

#### 修改内容

**服务端 - `mesapp.py`**
- `require_permission` 装饰器添加 Basic Auth 支持
- 检查 `request.mobile_user`（由 `login_required` 设置）
- 为移动端用户创建临时用户对象，赋予基本权限

---

### 版本 3.5 - 2025年12月04日 10:34:00

#### 需求描述
1. 修复 H2 数据库查询慢（每次请求都重新初始化）
2. 需重启服务器使 `/api/projects` 401 修复生效

#### 问题分析

**H2 数据库每次请求都重新初始化**
- **原因**: `DirectH2DatabaseManager` 的每个方法都创建新的 `H2ApiClient()` 实例
- **表现**: 日志显示每次查询都打印 `[H2数据库] 初始化完成`
- **解决方案**: 使用单例模式，只初始化一次 H2 客户端

#### 修改内容

**服务端 - `mesapp.py`**
- `DirectH2DatabaseManager` 添加类变量 `_h2_client` 作为单例
- 添加 `_get_h2_client()` 类方法获取单例客户端
- 修改 `upsert_record`, `get_record`, `get_records_by_project`, `delete_record`, `get_stats` 使用单例
- 修改 `init_h2_service()` 使用单例客户端

---

### 版本 3.4 - 2025年12月04日 10:14:00

#### 需求描述
修复 API 响应格式不匹配导致的"项目配置不存在"错误。

#### 问题分析

**API 返回格式与客户端期望不匹配**
- 服务端返回：`{"success": true, "data": {"configVersion": 33, ...}}`
- 客户端期望：`{"success": true, "config": {...}, "version": ...}`

#### 修改内容

**Android端 - `ApiService.kt`**
- `ProjectConfigResponse`: 使用 `@SerializedName("data")` 映射 `config` 字段
- `ProjectConfig`: 使用 `@SerializedName("configVersion")` 映射 `version` 字段，字段改为可空
- `ProductTypeConfig`: 添加 `materials` 和 `processSteps` 字段
- `ProcessConfig`: 使用 `@SerializedName("photoRequired")` 映射 `requirePhoto`

---

### 版本 3.3 - 2025年12月04日 10:06:00

#### 需求描述
1. 修复移动端 `/api/projects` 401认证错误
2. 修改零部件保存逻辑：每扫一个零部件就立即保存，而不是等所有扫完

#### 问题分析

**1. `/api/projects` 返回401**
- **原因**: `@login_required` 装饰器只支持 Flask session 认证，不支持 Basic Auth（移动端）
- **解决方案**: 修改 `auth.py` 中的 `login_required` 装饰器，支持 Basic Auth 头

**2. 扫码数据没有保存**
- **原因**: `componentBarcodeLauncher` 扫码回调只调用了 `checkAllComponentsScanned()`，没有调用 `saveComponentData()`
- **解决方案**: 修改扫码回调，每扫一个零部件就立即调用 `saveComponentData()` 保存

#### 修改内容

**1. 服务端 - `auth.py`**
- 修改 `login_required` 装饰器支持 Basic Auth
- API 请求返回 401 JSON 而非重定向到登录页

**2. Android端 - `MainActivity.kt`**
```kotlin
// 修改前 - componentBarcodeLauncher
scannedComponents[it.name] = result.contents
checkAllComponentsScanned()  // 只检查是否全部扫完

// 修改后
scannedComponents[component.name] = serialNumber
saveComponentData(component.name, serialNumber)  // 每扫一个就保存
checkAllComponentsScanned()
```

---

### 版本 3.2 - 2025年12月04日 09:00:00

#### 需求描述
修复移动端API路由404错误，统一移动端与Web端API路由格式。

#### 问题分析

**1. `/api/process-config/` 返回404**
- **原因**: Android端请求 `/api/process-config/{projectName}`，服务器端定义的是 `/api/process-config/projects/{projectName}/config`
- **解决方案**: 统一使用服务器端路由格式，修改Android端API调用

**2. `/api/h2/save` 路由缺失**
- **原因**: `mesapp.py` 中未定义 `/api/h2/save` 路由，该路由只在独立的 `h2_api.py` 中存在
- **解决方案**: 在 `mesapp.py` 中添加 `/api/h2/save` 路由

#### 修改内容

**1. Android端 - `ApiService.kt`**
```kotlin
// 修改前
@GET("api/process-config/{projectName}")
@POST("api/process-config/{projectName}")

// 修改后
@GET("api/process-config/projects/{projectName}/config")
@POST("api/process-config/projects/{projectName}/config")
```

**2. 服务器端 - `mesapp.py`**
- 添加 `/api/h2/save` POST 路由
- 支持保存产品记录到H2数据库
- 无需认证（移动端API）

#### API路由规范

| 功能 | 路由 | 方法 | 认证 |
|------|------|------|------|
| 获取项目配置 | `/api/process-config/projects/{projectName}/config` | GET | Web需认证 |
| 保存项目配置 | `/api/process-config/projects/{projectName}/config` | POST | 需管理员 |
| 查询产品记录 | `/api/h2/query/{serial}` | GET | 无需认证 |
| 保存产品记录 | `/api/h2/save` | POST | 无需认证 |

#### 设计原则
- 移动端和Web端统一使用相同的API路由格式
- 避免兼容路由，保持API一致性，便于后续扩展维护

---

### 版本 3.1 - 2025年12月03日 20:52:00

#### 需求描述
Web 后台用户管理与群组管理界面合并：将原本分离的"用户管理"和"群组管理"两个页面整合为一个统一的管理中心，采用 Tab 切换布局，并在群组详情中展示"群组默认权限"。

#### 背景与决策

**1. 架构评估**
- **调研对象**: Keycloak、Authentik、ZITADEL、ORY Kratos/Keto、Casbin 等开源 IAM/权限框架
- **评估结论**: 
  - 重型 IAM 平台（Keycloak 等）需要独立部署，改造成本高，不适合当前单系统场景
  - 当前已有完整的用户/群组/权限模型（`UserManagementService` + `PermissionService`）
  - 已深度对接群晖账号（`SynologyAuthService`），无需迁移认证体系
- **最终决策**: **不引入外部 IAM 框架**，在现有架构上优化 UI 和权限展示

**2. 界面设计方案**
- **布局**: B 方案 - 顶部 Tab 切换（用户 / 群组 / 权限）
- **入口**: 统一为 `/admin/users`，导航菜单只保留一个"用户管理"
- **群组默认权限**: 在群组详情右侧增加权限概览表格 + 跳转编辑按钮

#### 界面结构

**Tab 1: 用户**
- 用户统计卡片（总用户数 / 管理员 / 普通用户 / 活跃用户 / 群组总数）
- 用户列表表格：显示名、用户名、角色、邮箱、所属群组、权限数、最后登录
- 操作：查看详情、同步群晖用户、刷新

**Tab 2: 群组**
- 左侧：群组列表（名称、标识、成员数、来源标签）
- 右侧：群组详情
  - 基本信息：显示名、标识、来源、描述
  - **群组默认权限**（新增）：
    - 表格展示该群组显式配置的权限（allow/deny/未配置）
    - 按分类（web/mobile/api）分组显示
    - "编辑权限"按钮：跳转到权限 Tab 并自动选中该群组
  - 成员列表表格
- 操作：新建群组、编辑群组、管理成员、删除群组

**Tab 3: 权限**
- 主体选择：按用户配置 / 按群组配置
- 下拉框选择具体用户或群组
- 权限面板：按分类展示所有权限项，支持 allow/deny/inherit 三态切换
- 快捷操作：管理员模板、普通用户模板、重置覆写
- 保存按钮

#### 技术实现

**1. 前端改造**
- 合并 `templates/admin/users.html` 和 `templates/admin/groups.html` 内容
- 使用现有 Tab 切换机制（`.tab-switch` + `.tab-content`）
- 群组 Tab 复用 `groups.html` 的 JS 逻辑（`renderGroupList`、`loadGroupDetails` 等）
- 新增 `loadGroupPermissions(groupId)` 函数获取并渲染群组权限表格
- 新增 `editGroupPermissions(groupId)` 函数实现跳转到权限 Tab

**2. 后端改造**
- `admin_users()` 视图扩展：注入 `groups` 和 `all_users` 数据（原 `admin_groups()` 的数据）
- `admin_groups()` 路由改为重定向到 `/admin/users`
- 现有权限 API 无需修改：
  - `GET /admin/api/permissions/groups/<group_id>` - 获取群组权限详情
  - `PUT /admin/api/permissions/groups/<group_id>` - 更新群组权限

**3. 导航栏改造**
- `base.html` 中移除独立的"群组管理"菜单项
- 保留"用户管理"作为统一入口

#### 权限模型说明

权限计算优先级（从低到高）：
1. **角色默认权限**: `UserRole.ADMIN` / `UserRole.USER` 的基础权限集
2. **同步群组权限**: 从群晖导入的群组配置
3. **本地群组权限**: 在 MES 中创建或编辑的群组配置
4. **用户显式覆写**: 针对单个用户的 allow/deny 配置

群组默认权限展示的是第 2/3 层的显式配置，不包含角色默认和用户覆写。

#### 文件变更记录

- **修改文件**: `templates/admin/users.html`
  - **内容**: 合并群组管理功能，新增群组 Tab 和群组默认权限展示
  - **原因**: 实现用户/群组/权限统一管理界面

- **修改文件**: `templates/base.html`
  - **内容**: 移除独立的"群组管理"导航菜单
  - **原因**: 统一入口到用户管理页面

- **修改文件**: `mesapp.py`
  - **内容**: `admin_users()` 注入群组数据，`admin_groups()` 重定向
  - **原因**: 支持合并后的页面数据需求

- **备份文件**: `spec_20251203205200.MD`
  - **内容**: 版本 3.0 的完整备份
  - **原因**: 重大更新前的版本存档

#### 实施状态
- 规格设计：✅ 完成
- 前端实现：✅ 完成
- 后端调整：✅ 完成
- 测试验证：⏳ 待进行

---

### 版本 3.0 - 2025年12月03日 11:46:00

#### 需求描述
Android APP 架构重构：解决本地缓存与网络写入同步问题，存在数据漏写入的情况。采用 REST API + 服务端数据库的 C/S 架构替代当前的本地缓存 + SMB 同步方案。

#### 问题分析

**1. 当前架构问题**
- **数据漏写入**: 本地缓存 (`OfflineDataCache`) 与 SMB 网络写入不同步
- **并发冲突**: SMB 文件锁机制在多设备同时操作时易发生冲突
- **同步状态不透明**: 用户无法确认数据是否真正上传成功
- **架构复杂**: 需维护 Room/H2 本地数据库 + SMB 文件同步两套逻辑

**2. 当前 SMB 功能依赖分析**

| 功能 | SMB 使用方式 | 服务端 API 现状 | 迁移难度 |
|------|-------------|----------------|---------|
| 项目列表加载 | 读取 `projects.json` | ✅ 已有 `/api/projects` | 低 |
| 项目配置加载 | 读取 `projects/{项目名}.json` | ✅ 已有 `ProjectConfigManager` | 低 |
| 工序配置 | 读取/写入项目配置 | ✅ 已有 `process_config_api.py` | 低 |
| 产品记录保存 | 写入 CSV 文件 | ✅ 已有 `h2_api.py` | 低 |
| 产品记录查询 | 读取 CSV 文件 | ✅ 已有 `h2_api.py` | 低 |
| **照片上传** | 写入 `picture/` 目录 | ✅ 已有 `photo_api.py` | **无影响** |
| **照片列表/下载** | 读取 `picture/` 目录 | ✅ 已有 `photo_api.py` | **无影响** |
| 测试人员列表 | 读取 `testers.json` | ⚠️ 需新增 API | 中 |
| 活动测试状态 | 读取/写入 `active_tests.json` | ⚠️ 需新增 API | 中 |
| APK 更新检查 | 读取 `APK/` 目录 | ⚠️ 需新增 API | 中 |

**结论**: 移除 SMB **需要改造手机端照片上传调用方式**，但服务端 `photo_api.py` 已实现完整的照片管理 API。

**3. 手机端照片功能详细分析**

| 组件 | 当前实现 | 是否依赖 SMB | 改造方案 |
|------|---------|-------------|---------|
| `PhotoUploadService.kt` | HTTP API (`/api/photos/upload`) | ❌ 不依赖 | ✅ 无需改动 |
| `PhotoCaptureActivity.kt` | `fileManager.uploadPhoto()` | ⚠️ 依赖 SMB | 改为调用 `PhotoUploadService` |
| `CameraActivity.kt` | `fileManager.uploadPhoto()` | ⚠️ 依赖 SMB | 改为调用 `PhotoUploadService` |

**改造方案**: 统一使用 `PhotoUploadService`
- `PhotoCaptureActivity` 和 `CameraActivity` 改为调用 `PhotoUploadService.queuePhotoUpload()`
- 复用已有的 HTTP 上传逻辑，无需新增服务端 API

**4. 产品记录（扫码信息）依赖分析**

| 功能 | 调用位置 | 当前实现 | 服务端 API |
|------|---------|---------|-----------|
| 保存产品记录 | `MainActivity.kt` 第829、1622行 | `fileManager.saveProductRecord()` | ✅ `h2_api.py` |
| 查询产品记录 | `MainActivity.kt` 第1453行 | `fileManager.queryProductRecord()` | ✅ `h2_api.py` |
| H2 API 查询 | `MainActivity.kt` 第1363、1437行 | `H2ApiClient.queryProductRecord()` | ✅ **已用 HTTP** |

**5. 项目/工序配置依赖分析**

| 功能 | 调用位置 | 当前实现 | 服务端 API |
|------|---------|---------|-----------|
| 获取项目列表 | `ProjectManager.kt`、`MainActivity.kt` | `fileManager.fetchProjectList()` | ✅ `mesapp.py` |
| 获取项目配置 | `ProjectConfigManager.kt` | `fileManager.fetchProjectConfig()` | ✅ `process_config_api.py` |
| 保存项目配置 | `ProjectConfigManager.kt` | `fileManager.saveProjectConfig()` | ✅ `process_config_api.py` |
| 保存项目列表 | `ProjectManager.kt` | `fileManager.saveProjectList()` | ✅ `mesapp.py` |

**6. Android 端改造点汇总**

| 文件 | 改造点 | 工作量 |
|------|-------|--------|
| `MainActivity.kt` | `saveProductRecord`、`queryProductRecord` 改用 `H2ApiClient` | 中 |
| `ProjectManager.kt` | `fetchProjectList`、`saveProjectList` 改用 HTTP API | 中 |
| `ProjectConfigManager.kt` | `fetchProjectConfig`、`saveProjectConfig` 改用 HTTP API | 中 |
| `PhotoCaptureActivity.kt` | `uploadPhoto` 改用 `PhotoUploadService` | 低 |
| `CameraActivity.kt` | `uploadPhoto` 改用 `PhotoUploadService` | 低 |
| `ApkUpdateManager.kt` | 改用新的 APK API | 低 |

#### 架构对比

| 维度 | 当前架构 (本地DB + SMB) | 新架构 (REST API + 服务端DB) |
|------|------------------------|----------------------------|
| 数据一致性 | ⚠️ 弱 - 存在同步失败风险 | ✅ 强 - 写入即成功，失败即报错 |
| 并发处理 | ⚠️ 差 - 依赖文件锁 | ✅ 优 - 数据库事务保证 |
| 离线能力 | ✅ 支持离线操作 | ❌ 必须联网 |
| 网络依赖 | ✅ 低 | ⚠️ 高 |
| 维护成本 | ⚠️ 高 - 两套数据结构 | ✅ 低 - 逻辑集中在服务端 |

#### 解决方案：REST API 架构

**1. 核心设计原则**
- **纯在线模式**: Android 端不再维护本地数据库，所有数据实时写入服务端
- **即时反馈**: 操作成功/失败立即返回，无中间状态
- **服务端集中**: 业务逻辑集中在 Flask 后端，客户端只负责展示和交互

**2. 架构图**
```
┌─────────────────┐     HTTP/REST      ┌─────────────────────────────────┐
│   Android APP   │ ◄──────────────────► │   Flask 服务端 (NAS 本机)       │
│                 │                      │                                 │
│  - Retrofit     │                      │  - photo_api.py (照片管理)      │
│  - ViewModel    │                      │  - h2_api.py (产品记录)         │
│  - Repository   │                      │  - process_config_api.py (工序) │
│  (无本地DB)     │                      │  - 新增: testers_api.py         │
│                 │                      │  - 新增: active_tests_api.py    │
│                 │                      │  - 新增: apk_update_api.py      │
└─────────────────┘                      │                                 │
                                         │  ┌─────────────────────────┐    │
                                         │  │ NAS 本地文件系统        │    │
                                         │  │ - <DATA_DIR>/   │    │
                                         │  │   ├── picture/          │    │
                                         │  │   ├── projects/         │    │
                                         │  │   ├── record/           │    │
                                         │  │   └── APK/              │    │
                                         │  └─────────────────────────┘    │
                                         └─────────────────────────────────┘
```

**3. 服务端新增 API**

| API 路径 | 方法 | 功能 | 替代 SMB 功能 |
|---------|------|------|--------------|
| `/api/testers` | GET | 获取测试人员列表 | `testers.json` 读取 |
| `/api/testers` | POST | 保存测试人员列表 | `testers.json` 写入 |
| `/api/active-tests` | GET | 获取活动测试列表 | `active_tests.json` 读取 |
| `/api/active-tests` | POST | 添加/更新活动测试 | `active_tests.json` 写入 |
| `/api/active-tests/<serial>` | DELETE | 移除活动测试 | `active_tests.json` 删除 |
| `/api/apk/list` | GET | 获取可用 APK 列表 | `APK/` 目录列表 |
| `/api/apk/download/<filename>` | GET | 下载 APK 文件 | `APK/` 文件下载 |

**4. Android 端改造**

| 模块 | 当前实现 | 改造后 |
|------|---------|--------|
| 网络层 | `SMBFileManager` (1659行) | `Retrofit` + `ApiService` 接口 |
| 数据层 | `OfflineDataCache` + `UnifiedDataManager` | `Repository` 模式，直接调用 API |
| 缓存层 | Room/H2 本地数据库 | **移除**，仅保留内存缓存 |
| 同步层 | `WorkManager` 后台同步 | **移除**，改为同步 HTTP 调用 |

**5. 移除的文件/类**

Android 端:
- `cache/OfflineDataCache.kt` - 离线缓存
- `database/H2DatabaseManager.kt` - H2 数据库管理
- `database/UnifiedDataManager.kt` - 统一数据管理
- `network/SMBFileManager.kt` - SMB 文件管理 (1659行)
- `worker/` 目录下的 WorkManager 相关类

**6. 新增的文件/类**

Android 端 (已实施 ✅):
- `api/ApiService.kt` - Retrofit API 接口定义 ✅
- `api/ApiClient.kt` - Retrofit 客户端配置 ✅
- `repository/TesterRepository.kt` - 测试人员仓库 ✅
- `repository/ActiveTestRepository.kt` - 活动测试仓库 ✅
- `repository/ApkUpdateRepository.kt` - APK 更新仓库 ✅
- `repository/ProjectRepository.kt` - 项目数据仓库 ✅
- `repository/ProductRecordRepository.kt` - 产品记录仓库 ✅
- `repository/PhotoRepository.kt` - 照片仓库 ✅

服务端 (已实施 ✅):
- `testers_api.py` - 测试人员管理 API ✅
- `active_tests_api.py` - 活动测试状态 API ✅
- `apk_update_api.py` - APK 更新检查 API ✅

### 7. 已集成的现有代码 (已实施 ✅)

| 文件 | 改造内容 | 状态 |
|------|---------|------|
| `ProjectManager.kt` | 使用 `ProjectRepository` 替代 `FileManager` | ✅ |
| `ProjectConfigManager.kt` | 使用 `ProjectRepository` 替代 `FileManager` (工序配置同步) | ✅ |
| `ApkUpdateManager.kt` | 使用 `ApkUpdateRepository` 替代 `FileManager` | ✅ |
| `PhotoCaptureActivity.kt` | 使用 `PhotoRepository` 替代 `FileManager.uploadPhoto()` | ✅ |
| `CameraActivity.kt` | 使用 `PhotoRepository` 替代 `FileManager.uploadPhoto()` | ✅ |
| `MainActivity.kt` | 使用 `ProductRecordRepository` 替代 `FileManager.saveProductRecord/queryProductRecord` | ✅ |
| `build.gradle` | 添加 Retrofit + OkHttp 依赖 | ✅ |

#### 风险评估

**1. 网络依赖风险**
- **风险**: 工厂 Wi-Fi 信号差时，扫码操作会卡顿或失败
- **缓解措施**:
  - 设置合理的超时时间 (10秒)
  - 失败时显示明确的错误提示
  - 提供手动重试机制
  - 建议用户确认网络环境稳定

**2. 数据迁移风险**
- **风险**: 现有本地缓存数据丢失
- **缓解措施**:
  - 升级前提示用户确保网络连接
  - 自动上传本地未同步数据
  - 保留本地数据备份 7 天

#### 实施计划

**阶段一: 服务端 API 补全 (1-2天)**
1. 新增 `testers_api.py`
2. 新增 `active_tests_api.py`
3. 新增 `apk_update_api.py`
4. 测试所有 API 端点

**阶段二: Android 端重构 (3-5天)**
1. 引入 Retrofit 网络库
2. 创建 `ApiService` 接口
3. 实现 `Repository` 层
4. 改造 Activity/ViewModel 调用方式
5. 移除 SMB 相关代码

**阶段三: 测试与发布 (1-2天)**
1. 功能测试
2. 网络异常测试
3. 性能测试
4. 发布新版本 APK

#### 文件变更记录

**服务端新增文件**:
- `testers_api.py` - 测试人员管理 API
- `active_tests_api.py` - 活动测试状态 API
- `apk_update_api.py` - APK 更新检查 API

**Android 端移除文件**:
- `cache/OfflineDataCache.kt`
- `database/H2DatabaseManager.kt`
- `database/UnifiedDataManager.kt`
- `network/SMBFileManager.kt`

**Android 端新增文件**:
- `api/ApiService.kt`
- `api/ApiClient.kt`
- `repository/ProjectRepository.kt`
- `repository/TestRecordRepository.kt`
- `repository/PhotoRepository.kt`

---

### 版本 2.1 - 2025年10月21日 10:05:00

#### 需求描述
针对Windows Server 2016部署环境，调整部署方案，提供Windows专用的部署指南和自动化脚本。

#### 部署环境变更
- **原计划**: Linux NAS环境 (Nginx + Gunicorn + Systemd)
- **实际环境**: Windows Server 2016
- **需要调整**: WSGI服务器、进程管理、反向代理方案

#### 解决方案

**1. WSGI服务器选择**
- **选型**: Waitress (Python原生WSGI服务器)
- **优势**:
  - Windows原生支持，稳定性最高
  - 多线程架构，无GIL问题
  - 生产级性能和可靠性
  - 配置简单，易于维护
- **替代Gunicorn原因**: Gunicorn在Windows上支持有限

**2. 进程管理方案**
- **选型**: NSSM (Non-Sucking Service Manager)
- **功能**: 将Python应用注册为Windows服务
- **优势**:
  - 开机自启动
  - 崩溃自动重启
  - 日志管理
  - 服务级别管理

**3. 反向代理方案**
- **推荐**: IIS (Internet Information Services)
- **优势**:
  - Windows Server原生组件
  - 企业级稳定性
  - SSL/TLS支持
  - URL重写和请求过滤
  - 静态文件加速
- **备选**: Waitress独立运行(不使用反向代理)

#### 部署架构

```
Internet → IIS (反向代理/SSL) → Waitress (WSGI服务器) → Flask应用
```

#### 技术实现

**1. 核心配置文件**
- `start_waitress.py`: Waitress启动脚本
  - 配置8个工作线程
  - 监听127.0.0.1:8891 (仅本地)
  - 连接限制1000
  - 超时时间120秒

- `deploy_windows.ps1`: 自动化部署脚本
  - 一键安装服务
  - 自动配置日志
  - 服务管理命令
  - 状态检查功能

- `iis_web.config`: IIS反向代理配置
  - URL重写规则
  - 请求过滤(100MB限制)
  - 静态文件处理
  - HTTP压缩

**2. Windows服务配置**
- 服务名: QRTestScannerMES
- 启动类型: 自动
- 日志轮转: 10MB自动轮转
- 崩溃恢复: 自动重启

#### 性能优化
- 多线程并发处理
- IIS静态文件加速
- HTTP响应压缩
- 请求队列管理

#### 文件变更记录
- **新增文件**: Windows_Server_2016_部署方案.md
  - **位置**: F:\GitHub\hours\QRTestScanner\app_web\
  - **内容**: Windows Server完整部署指南
  - **原因**: 提供Windows专用部署说明

- **新增文件**: start_waitress.py
  - **位置**: F:\GitHub\hours\QRTestScanner\app_web\
  - **内容**: Waitress WSGI服务器启动脚本
  - **原因**: 替代Flask开发服务器，支持生产环境

- **新增文件**: deploy_windows.ps1
  - **位置**: F:\GitHub\hours\QRTestScanner\app_web\
  - **内容**: PowerShell自动化部署脚本
  - **原因**: 简化Windows部署流程

- **新增文件**: iis_web.config
  - **位置**: F:\GitHub\hours\QRTestScanner\app_web\
  - **内容**: IIS反向代理配置文件
  - **原因**: 配置IIS到Waitress的请求转发

#### 实施步骤
1. **安装依赖**: Python、Waitress、NSSM
2. **创建服务**: 使用NSSM注册Windows服务
3. **配置IIS**: 安装URL Rewrite和ARR模块
4. **部署验证**: 测试健康检查和功能
5. **防火墙配置**: 开放HTTP/HTTPS端口

#### 快速部署命令
```powershell
# 使用自动化脚本一键部署
.\deploy_windows.ps1 -Action install
```

### 版本 2.0 - 2025年10月21日 09:42:00

#### 需求描述
对app_web后端程序进行全面评估，查询开源代码平台上是否有更成熟的MES方案可以落地替换，评估当前Python Flask形式能否长期运行。

#### 评估范围
1. **当前系统架构分析**: 技术栈、功能模块、部署方式
2. **开源MES系统对比**: 调研开源社区的MES解决方案
3. **生产部署可行性**: Python Flask长期运行的稳定性评估
4. **部署方案优化**: 提供生产级部署建议

#### 评估结论

**1. 关于系统替换**
- **不建议替换**: 经过对比多个开源MES系统(osess/mes、smart-industry、Java系统等)，当前系统具有以下优势：
  - 功能完整度高，覆盖认证、权限、项目管理、照片管理等核心功能
  - 与群晖NAS深度集成，支持SMB/WebDAV双协议
  - 高度定制化，完全契合QR测试扫描场景
  - 已有完整的API文档和用户手册
  - 与Android移动端紧密配合
- **开源方案问题**:
  - 技术栈差异大(Django、Java、JavaScript)，迁移成本极高
  - 通用MES系统功能过重，不适合轻量场景
  - 部分项目已停止维护或开发暂停
  - 失去现有灵活性和可控性

**2. 关于长期运行**
- **当前问题严重**: 使用Flask内置开发服务器(`app.run`)不适合生产环境
  - 单进程运行，无法利用多核CPU
  - 缺乏进程管理，崩溃后无法自动重启
  - 并发能力差，受GIL限制
  - 无负载均衡，单点故障风险高
- **必须升级**: 改用生产级部署架构
  - 推荐: **Nginx + Gunicorn + Flask**
  - Gunicorn多进程/多线程模式
  - Systemd进程管理和自动重启
  - Nginx反向代理和负载均衡
  - 预期并发能力提升5-10倍

#### 实施方案

**1. 生产级部署架构**
```
Internet → Nginx (反向代理) → Gunicorn (WSGI服务器) → Flask应用
```

**2. 核心配置**
- Gunicorn配置: `gunicorn_config.py`
  - Workers数量: CPU核心数 × 2 + 1
  - Worker类型: sync (同步worker)
  - 超时时间: 120秒
  - 最大请求数: 5000 (防止内存泄漏)
  
- Systemd服务: `/etc/systemd/system/mesapp.service`
  - 自动重启策略
  - 日志管理
  - 资源限制
  
- Nginx配置: `/etc/nginx/sites-available/mesapp`
  - 反向代理到Gunicorn
  - 静态文件加速
  - 请求超时控制

**3. 性能优化**
- 数据库连接池优化
- 缓存机制(Flask-Caching)
- 日志轮转配置
- 健康检查监控

#### 技术改进
- 提升系统稳定性和可用性(99.9%)
- 增强并发处理能力(5-10倍提升)
- 标准化运维流程
- 完善监控和告警机制

#### 文件变更记录
- **新增文件**: 系统评估与部署方案_20251021.md
  - **位置**: F:\GitHub\hours\QRTestScanner\app_web\
  - **内容**: 完整的系统评估报告、部署方案、配置示例
  - **原因**: 记录评估结论和实施指南
  
- **待创建配置文件**:
  - gunicorn_config.py - Gunicorn配置
  - /etc/systemd/system/mesapp.service - Systemd服务
  - /etc/nginx/sites-available/mesapp - Nginx配置

#### 实施优先级
- **高优先级(立即)**: 安装Gunicorn、配置Systemd服务、配置Nginx
- **中优先级(1周内)**: 日志轮转、健康检查、HTTPS配置
- **低优先级(1月内)**: 缓存优化、性能测试、监控体系

### 版本 1.0 - 2025年10月21日 00:12:54

#### 问题描述
铠狮智能0.8T装载机项目下有三个产品类型，但都没有加载成功，脚本存在问题。

#### 问题分析
1. **根本原因**: Excel数据文件中的项目名称为"铠狮0.8吨装载机"，而projects.json中的项目名称为"铠狮智能0.8T装载机"
2. **具体差异**:
   - 重量单位差异: "0.8吨" vs "0.8T"
   - 修饰词差异: "铠狮" vs "铠狮智能"
3. **影响范围**: 导致项目名称无法匹配，产品类型信息无法正确加载

#### 解决方案
1. **智能匹配算法**: 在generate_project_jsons.py中添加了智能项目名称匹配功能
   - 添加normalize_project_name()函数，标准化项目名称
   - 添加find_matching_project_name()函数，实现模糊匹配
   - 支持重量单位转换（吨 ↔ T）
   - 支持修饰词忽略（如"智能"）

2. **匹配策略**:
   - 第一步：精确匹配
   - 第二步：标准化匹配
   - 第三步：部分匹配（包含关系）

#### 修复结果
成功生成铠狮智能0.8T装载机.json配置文件，包含三个产品类型：
1. 电机总成 (PCkaSLoD8A-1)
2. 油泵电机总成 (PCkaSLoD8A-2, PCkaSLoD8A-4)
3. 行走电机总成 (PCkaSLoD8A-3)

#### 技术改进
- 增强了项目名称匹配的鲁棒性
- 提高了数据源之间的兼容性
- 减少了因命名差异导致的配置失败

#### 文件变更记录
- **修改文件**: generate_project_jsons.py
  - **位置**: 第185行后添加normalize_project_name()和find_matching_project_name()函数
  - **位置**: 第152-158行修改项目名称匹配逻辑
  - **原因**: 解决项目名称不匹配问题

- **生成文件**: projects/铠狮智能0.8T装载机.json
  - **内容**: 包含3个产品类型的完整配置
  - **原因**: 修复后重新生成的项目配置文件

## 时间线

### 2025-12-03 20:52:00 - Web 用户与群组管理界面合并
- **需求提出**: 将"用户管理"和"群组管理"两个独立页面合并为统一管理中心
- **架构评估**: 调研 Keycloak、Authentik、ZITADEL、Casbin 等开源 IAM 框架
- **评估结论**: 不引入外部 IAM 框架，在现有架构上优化
- **界面方案**: B 方案 - 顶部 Tab 切换（用户 / 群组 / 权限）
- **新增功能**: 群组详情中展示"群组默认权限"概览
- **文件变更**: users.html、base.html、mesapp.py
- **状态**: 实施中

### 2025-12-03 11:46:00 - Android APP 架构重构 (REST API 方案)
- **需求提出**: 解决本地缓存与网络写入同步问题，存在数据漏写入
- **问题分析**: SMB 文件锁并发冲突、同步状态不透明、架构复杂
- **技术选型**: REST API + 服务端数据库 (C/S 架构)
- **核心改造**: 
  - 移除 Android 端 SMB 相关代码 (1659行)
  - 引入 Retrofit 网络库
  - 服务端新增 3 个 API 模块
- **照片功能**: 不受影响，服务端 `photo_api.py` 已完整实现
- **状态**: 规格设计完成，待实施

### 2025-10-21 10:05:00 - Windows Server 2016部署方案制定
- **需求变更**: 部署环境从Linux NAS改为Windows Server 2016
- **技术选型**: Waitress + IIS替代Gunicorn + Nginx
- **成果交付**: 完整Windows部署文档和自动化脚本
- **文件创建**: start_waitress.py, deploy_windows.ps1, iis_web.config
- **部署方式**: Windows服务 + IIS反向代理
- **状态**: 方案完成，可立即实施

### 2025-10-21 09:42:00 - Web后端系统评估与部署方案制定
- **需求提出**: 评估现有系统，查询是否有更成熟的开源方案可替换
- **调研分析**: 对比osess/mes、smart-industry等多个开源MES系统
- **评估结论**: 不建议替换，当前系统更契合业务需求
- **部署问题**: 发现使用Flask开发服务器存在严重的生产环境隐患
- **解决方案**: 制定Nginx + Gunicorn生产级部署架构
- **交付成果**: 完整评估报告和实施指南文档
- **状态**: 评估完成，待实施部署

### 2025-10-21 00:12:54 - 铠狮智能0.8T装载机项目修复
- **问题发现**: 用户报告三个产品类型加载失败
- **问题分析**: 发现项目名称不匹配问题
- **解决方案**: 实现智能匹配算法
- **结果验证**: 成功生成包含3个产品类型的配置文件
- **状态**: 已完成

## 配置规范

### 项目配置文件结构
```json
{
  "projectName": "项目名称",
  "projectCode": "项目代码",
  "schemaVersion": "2.1",
  "version": 1,
  "productTypes": [
    {
      "typeName": "产品类型名称",
      "modelNumber": "产品型号",
      "materials": [],
      "processSteps": []
    }
  ],
  "processSteps": [],
  "metadata": {
    "configFormat": "v2.0",
    "supportedFeatures": ["productTypes", "processSteps", "versionControl"]
  }
}
```

### 命名规范
- 项目名称支持中文和英文
- 重量单位统一使用"T"表示吨
- 产品型号格式: PC[公司代码][产品代码][规格]-[序号]

## 维护说明
- 每次重大更新都会自动创建版本备份
- 配置文件变更会记录在此文档中
- 时间线功能帮助追踪项目演进历史