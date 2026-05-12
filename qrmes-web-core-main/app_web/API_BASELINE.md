# QRTestScanner API 基线文档

> 基线服务器: `http://172.16.30.2:8891`
> 创建日期: 2026-02-14
> 用途: 前后端分离测试的 API 分界线，以下 API 为基础 API，上线新功能时必须保留

---

## 一、移动端调用的核心 API（Android App → Flask 后端）

这些 API 是手机 App 直接调用的，修改需同步更新 App 端。

### 1. 测试人员管理 `/api/testers`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/testers` | 获取测试人员列表 | `testers_api.py` |
| POST | `/api/testers` | 保存测试人员列表（批量） | `testers_api.py` |
| POST | `/api/testers/{name}` | 添加单个测试人员 | `testers_api.py` |
| DELETE | `/api/testers/{name}` | 删除单个测试人员 | `testers_api.py` |

### 2. 活动测试管理 `/api/active-tests`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/active-tests` | 获取所有活动测试 | `active_tests_api.py` |
| GET | `/api/active-tests/{serial}` | 获取指定序列号的活动测试 | `active_tests_api.py` |
| POST | `/api/active-tests` | 添加/更新活动测试 | `active_tests_api.py` |
| DELETE | `/api/active-tests/{serial}` | 删除活动测试（测试完成） | `active_tests_api.py` |
| POST | `/api/active-tests/clear` | 清空所有活动测试 | `active_tests_api.py` |

### 3. APK 更新 `/api/apk`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/apk/list` | 获取所有 APK 文件列表 | `apk_update_api.py` |
| GET | `/api/apk/latest` | 获取最新版本 APK 信息 | `apk_update_api.py` |
| GET | `/api/apk/check-update?versionCode=&versionName=&appName=` | 检查是否有更新 | `apk_update_api.py` |
| GET | `/api/apk/download/{filename}` | 下载 APK 文件 | `apk_update_api.py` |
| GET | `/api/apk/info/{filename}` | 获取指定 APK 信息 | `apk_update_api.py` |
| GET | `/api/apk/debug` | 调试：APK 目录配置 | `apk_update_api.py` |

### 4. H2 产品记录数据库 `/api/h2`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/h2/query/{product_serial}` | 查询单个产品记录 | `h2_api.py` + `mesapp.py` |
| GET | `/api/h2/project/{project_name}?limit=100` | 按项目查询记录 | `h2_api.py` + `mesapp.py` |
| GET | `/api/h2/stats` | 获取数据库统计信息 | `h2_api.py` + `mesapp.py` |
| POST | `/api/h2/save` | 保存产品记录（实时写入） | `h2_api.py` + `mesapp.py` |
| DELETE | `/api/h2/delete/{product_serial}` | 删除产品记录 | `h2_api.py` |
| GET | `/api/h2/health` | 健康检查 | `h2_api.py` + `mesapp.py` |
| GET | `/api/h2/sync/stats` | 获取同步统计信息 | `h2_api.py` |
| POST | `/api/h2/sync/trigger` | 手动触发全量同步 | `h2_api.py` |
| POST | `/api/h2/sync/to_nas` | 同步到 NAS | `mesapp.py` |
| POST | `/api/h2/sync/from_nas` | 从 NAS 同步 | `mesapp.py` |

### 5. 项目管理 `/api/projects`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/projects` | 获取项目列表 | `mesapp.py` |
| POST | `/api/projects` | 保存项目列表 | `mesapp.py` |
| DELETE | `/api/projects/{project_name}` | 删除项目 | `mesapp.py` |
| GET | `/api/projects/{project_name}/config` | 获取项目配置 | `mesapp.py` |
| POST | `/api/projects/{project_name}/product-types` | 添加产品类型 | `mesapp.py` |
| DELETE | `/api/projects/{project_name}/product-types/{type_name}` | 删除产品类型 | `mesapp.py` |
| POST | `/api/projects/{project_name}/product-types/{type_name}/materials` | 添加物料 | `mesapp.py` |
| PUT | `/api/projects/{project_name}/product-types/{type_name}/materials/{material_name}` | 更新物料 | `mesapp.py` |
| DELETE | `/api/projects/{project_name}/product-types/{type_name}/materials/{material_name}` | 删除物料 | `mesapp.py` |

### 6. 工序配置管理 `/api/process-config`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/process-config/projects` | 获取所有项目列表 | `process_config_api.py` |
| POST | `/api/process-config/projects` | 创建新项目 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/config` | 获取完整项目配置 | `process_config_api.py` |
| POST | `/api/process-config/projects/{name}/config` | 保存完整项目配置 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/processes?productType=` | 获取工序配置 | `process_config_api.py` |
| POST | `/api/process-config/projects/{name}/processes` | 添加工序 | `process_config_api.py` |
| PUT | `/api/process-config/projects/{name}/processes/{id}` | 更新工序 | `process_config_api.py` |
| DELETE | `/api/process-config/projects/{name}/processes/{id}?productType=` | 删除工序 | `process_config_api.py` |
| POST | `/api/process-config/projects/{name}/processes/reorder` | 重新排序工序 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/export` | 导出项目配置 | `process_config_api.py` |
| POST | `/api/process-config/projects/{name}/import` | 导入项目配置 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/versions` | 获取配置版本历史 | `process_config_api.py` |
| POST | `/api/process-config/projects/{name}/versions/{ver}/restore` | 恢复指定版本 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/history` | 获取变更历史 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/history/{id}` | 获取变更详情 | `process_config_api.py` |
| POST | `/api/process-config/projects/{name}/migrate` | 迁移配置到新版本 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/validate-migration` | 验证迁移完整性 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/sync/status` | 获取同步状态 | `process_config_api.py` |
| POST | `/api/process-config/projects/{name}/sync/trigger` | 触发配置同步 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/compare/{` | 比较两个版本差异 | `process_config_api.py` |
| GET | `/api/process-config/projects/{name}/statistics` | 获取项目统计 | `process_config_api.py` |
| POST | `/api/process-config/maintenance/cleanup` | 清理旧记录 | `process_config_api.py` |

---

## 二、照片管理 API

### 7. 照片 API `/api/photos`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| POST | `/api/photos/upload` | 上传照片文件（multipart） | `photo_api.py` |
| POST | `/api/photos/metadata` | 保存照片元数据 | `photo_api.py` |
| GET | `/api/photos/product/{serial}` | 获取产品的所有照片 | `photo_api.py` |
| GET | `/api/photos/process/{step}` | 获取工序的所有照片 | `photo_api.py` |
| GET | `/api/photos/file/{photo_id}` | 获取照片文件 | `photo_api.py` |
| GET | `/api/photos/thumbnail/{photo_id}` | 获取照片缩略图 | `photo_api.py` |
| PUT | `/api/photos/upload-status/{photo_id}` | 更新上传状态 | `photo_api.py` |
| DELETE | `/api/photos/{photo_id}` | 删除照片 | `photo_api.py` |
| GET | `/api/photos/{photo_id}` | 获取照片详情 | `photo_api.py` |
| PUT | `/api/photos/{photo_id}/metadata` | 更新照片元数据 | `photo_api.py` |
| POST | `/api/photos/delete-file` | 通过文件路径删除照片 | `photo_api.py` |
| GET | `/api/photos/search` | 搜索照片 | `photo_api.py` |
| GET | `/api/photos/statistics` | 获取照片统计 | `photo_api.py` |
| GET | `/api/photos/scan-directory` | 扫描照片目录 | `photo_api.py` |
| GET | `/api/photos/file-direct?path=` | 直接获取照片文件 | `photo_api.py` |
| GET | `/api/photos/thumbnail-direct?path=` | 直接获取缩略图 | `photo_api.py` |
| GET | `/api/photos/compressed-direct?path=` | 获取压缩照片 | `photo_api.py` |
| GET | `/api/photos/cache/stats` | 获取缓存统计 | `photo_api.py` |
| POST | `/api/photos/cache/clear` | 清空照片缓存 | `photo_api.py` |
| DELETE | `/api/photos/{serial}/{filename}` | 删除指定照片文件 | `mesapp.py` |
| GET | `/api/photos/search` | 搜索照片（mesapp） | `mesapp.py` |

### 8. 异步照片 API `/api/photos/async`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/photos/async/list?serialNumber=` | 获取照片列表（仅元数据） | `async_photo_api.py` |
| GET | `/api/photos/async/recent?days=2&limit=200` | 获取最近照片（默认 2 天 / 200 张，基于索引，快速返回） | `async_photo_api.py` |
| GET | `/api/photos/async/thumbnail?path=` | 获取缩略图（异步） | `async_photo_api.py` |
| GET | `/api/photos/async/full?path=` | 获取压缩图（异步） | `async_photo_api.py` |
| GET | `/api/photos/async/original?path=` | 获取原始图片 | `async_photo_api.py` |
| POST | `/api/photos/async/batch-thumbnails` | 批量获取缩略图 URL | `async_photo_api.py` |
| GET | `/api/photos/async/scan-directory-async` | 异步扫描照片目录 | `async_photo_api.py` |
| GET | `/api/photos/async/cache-stats` | 获取缓存统计 | `async_photo_api.py` |

#### `/api/photos/async/recent` 契约说明

- 默认参数：`days=2`，`limit=200`
- 排序：`timestamp DESC`
- 响应字段（`photos[]`）：`id`（文件路径）, `filename`, `projectName`, `productName`, `serialNumber`, `processStep`, `thumbnailUrl`, `fullUrl`, `originalUrl`, `size`, `timestamp`（毫秒）
- 索引未就绪时：不得阻塞请求；返回空列表，并在 `cacheInfo.indexReady=false` 中标记（用于前端提示/兜底）

---

## 三、Web 后台管理 API

### 9. 认证与会话

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET/POST | `/login` | 登录页面/登录操作 | `mesapp.py` |
| GET | `/logout` | 登出 | `mesapp.py` |
| GET | `/check_auth` | 检查认证状态 | `mesapp.py` |

### 10. 权限管理 `/api/user` & `/api/admin`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/user/current-permissions` | 获取当前用户权限 | `permission_api.py` |
| POST | `/api/user/check-permission` | 检查用户是否有特定权限 | `permission_api.py` |
| GET | `/api/user/permissions-list` | 获取所有可用权限列表 | `permission_api.py` |
| GET | `/api/user/role-permissions` | 获取各角色权限配置 | `permission_api.py` |
| GET | `/api/user/current-info` | 获取当前用户信息 | `permission_api.py` |
| GET | `/api/user/{username}/permissions` | 获取指定用户权限 | `mesapp.py` |
| GET | `/api/users` | 获取所有用户列表 | `permission_api.py` |
| GET | `/api/users/{user_id}` | 获取指定用户信息 | `permission_api.py` |
| POST | `/api/users` | 创建新用户 | `permission_api.py` + `mesapp.py` |
| PUT | `/api/users/{username}` | 更新用户信息 | `permission_api.py` + `mesapp.py` |
| DELETE | `/api/users/{username}` | 删除用户 | `mesapp.py` |
| GET | `/api/admin/permissions/resources` | 获取所有权限资源 | `permission_api.py` |
| GET | `/api/admin/permissions/users/{user_id}` | 获取用户权限详情 | `permission_api.py` |
| PUT | `/api/admin/permissions/users/{user_id}` | 更新用户权限 | `permission_api.py` |
| GET | `/api/admin/permissions/groups/{group_id}` | 获取群组权限 | `permission_api.py` |
| PUT | `/api/admin/permissions/groups/{group_id}` | 更新群组权限 | `permission_api.py` |
| POST | `/api/admin/generate-permissions-file` | 生成权限文件 | `mesapp.py` |
| GET | `/api/admin/permissions-file-status` | 权限文件状态 | `mesapp.py` |

### 11. 管理后台 API `/admin/api`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| POST | `/admin/api/sync-users` | 同步用户 | `mesapp.py` |
| GET | `/admin/api/groups` | 获取群组列表 | `mesapp.py` |
| POST | `/admin/api/groups` | 创建群组 | `mesapp.py` |
| PUT | `/admin/api/groups/{group_id}` | 更新群组 | `mesapp.py` |
| DELETE | `/admin/api/groups/{group_id}` | 删除群组 | `mesapp.py` |
| GET | `/admin/api/groups/{group_id}/members` | 获取群组成员 | `mesapp.py` |
| PUT | `/admin/api/groups/{group_id}/members` | 更新群组成员 | `mesapp.py` |
| GET | `/admin/api/users/{user_id}/details` | 获取用户详情 | `mesapp.py` |
| PUT | `/admin/api/users/{user_id}` | 更新用户 | `mesapp.py` |
| POST | `/admin/api/users/{user_id}/promote` | 提升用户权限 | `mesapp.py` |
| POST | `/admin/api/users/{user_id}/demote` | 降低用户权限 | `mesapp.py` |
| DELETE | `/admin/api/users/{user_id}/delete` | 删除用户 | `mesapp.py` |
| POST | `/admin/api/users/{user_id}/test-access` | 测试用户访问 | `mesapp.py` |
| GET | `/admin/api/permissions/resources` | 获取权限资源 | `mesapp.py` |
| GET | `/admin/api/permissions/users/{user_id}` | 获取用户权限 | `mesapp.py` |
| PUT | `/admin/api/permissions/users/{user_id}` | 更新用户权限 | `mesapp.py` |
| GET | `/admin/api/permissions/groups/{group_id}` | 获取群组权限 | `mesapp.py` |
| PUT | `/admin/api/permissions/groups/{group_id}` | 更新群组权限 | `mesapp.py` |

### 12. 记录管理

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/records?project=&type=&serial=&page=&per_page=` | 查询记录列表 | `mesapp.py` |
| DELETE | `/api/records/delete/{product_serial}` | 删除记录 | `mesapp.py` |
| POST | `/api/records/export` | 导出记录 | `mesapp.py` |
| GET | `/api/stats` | 获取统计信息 | `mesapp.py` |
| GET | `/api/stats/total_records` | 获取总记录数 | `mesapp.py` |

### 13. 测试报告 `/api/test-reports`

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| POST | `/api/test-reports/scan` | 扫描并导入测试报告 | `test_report_api.py` |
| GET | `/api/test-reports?project=&result=&page=&per_page=` | 列出测试报告 | `test_report_api.py` |
| GET | `/api/test-reports/{report_id}` | 获取报告详情 | `test_report_api.py` |
| GET | `/api/test-reports/serial/{serial_number}` | 根据序列号获取报告 | `test_report_api.py` |
| GET | `/api/test-reports/statistics?project=` | 获取统计信息 | `test_report_api.py` |
| GET | `/api/test-reports/projects` | 列出所有项目 | `test_report_api.py` |
| GET | `/api/test-reports/trend?project=&days=30` | 获取趋势数据 | `test_report_api.py` |
| GET | `/api/test-reports/cpk?project=&value_name=` | CPK 分析数据 | `test_report_api.py` |
| GET | `/api/test-reports/value-names?project=` | 列出测试值名称 | `test_report_api.py` |
| POST | `/api/test-reports/generate-factory-report` | 生成出厂报告 | `test_report_api.py` |

### 14. 日志管理

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/logs?page=&per_page=&type=&user=` | 获取日志列表 | `mesapp.py` |
| POST | `/api/logs/export` | 导出日志 | `mesapp.py` |
| GET | `/api/logs/stats` | 日志统计 | `mesapp.py` |
| POST | `/api/logs/sync/all` | 同步所有日志 | `mesapp.py` |
| POST | `/api/logs/sync/{filename}` | 同步指定日志文件 | `mesapp.py` |

### 15. 系统设置

| 方法 | 路径 | 说明 | 来源文件 |
|------|------|------|----------|
| GET | `/api/settings/webdav` | 获取 WebDAV 设置 | `mesapp.py` |
| POST | `/api/settings/webdav` | 保存 WebDAV 设置 | `mesapp.py` |
| POST | `/api/settings/webdav/test` | 测试 WebDAV 连接 | `mesapp.py` |
| POST | `/api/settings/webdav/init-directories` | 初始化 WebDAV 目录 | `mesapp.py` |
| GET | `/health` | 系统健康检查 | `mesapp.py` |
| GET | `/debug_config` | 调试配置信息 | `mesapp.py` |

---

## 四、外部服务（非 172.16.30.2:8891）

这些不在 Flask 后端上，但 App 会直接调用：

| 服务 | 地址 | 用途 |
|------|------|------|
| Synology 认证 | `https://panovation.i234.me:5001` | 用户登录认证 |
| WebDAV 文件 | `https://panovation.i234.me:5006` | 文件存取 |
| SMB 文件共享 | `172.16.30.2` (share: `测试中心`) | 遗留 CSV 文件访问 |

---

## 五、API 分界规则

### 基础 API（必须保留）
上面列出的所有 API 均为基础 API。上线新功能时：
1. **不得删除**任何基础 API 端点
2. **不得修改**基础 API 的请求/响应格式（向后兼容）
3. 可以**新增字段**到响应中（不影响旧客户端）
4. 可以**新增可选参数**到请求中

### 新增 API 规范
新功能的 API 应使用新的路径前缀，建议：
- `/api/v2/xxx` — 基础 API 的升级版本
- `/api/new-feature/xxx` — 全新功能模块

### 前后端分离测试流程
1. **MES 系统更改**：只改 Web 后台页面和 `/admin/` 路径下的 API，不影响移动端
2. **手机 App 更改**：只改 App 端代码，后端 API 保持不变
3. **同时更改**：先部署后端（保持向后兼容），再发布 App 新版本

---

## 六、Android App Retrofit 接口定义

App 端的 API 接口定义在：
- `app/src/main/java/com/testcenter/qrscanner/api/ApiService.kt` — Retrofit 接口
- `app/src/main/java/com/testcenter/qrscanner/api/ApiClient.kt` — HTTP 客户端配置
- `app/src/main/java/com/testcenter/qrscanner/network/H2ApiClient.kt` — H2 数据库直连客户端

默认 Base URL: `http://172.16.30.2:8891`
可通过 `PreferencesManager.setApiBaseUrl()` 运行时修改。
