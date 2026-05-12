# Debug 版本调试指南

## 修复内容

### 1. 版本更新功能调试日志

在 `ApkUpdateManager.kt` 中添加了详细的调试日志：

#### 新增日志点
- **开始检查**: 显示当前版本号
- **APK 列表**: 显示服务器上所有 APK 文件的详细信息
- **版本比较**: 详细显示每个 APK 的版本比较过程
- **版本组件**: 显示版本号的解析结果
- **Build 号比较**: 当版本号相同时，显示 Build 号的比较
- **最终结果**: 显示是否找到更新

#### 日志标签
```
ApkUpdateManager
```

#### 关键日志示例
```
[版本更新] 开始检查更新
[版本更新] 当前版本: 1.2.15
[版本更新] 从服务器获取到 3 个 APK 文件
[版本更新] 发现 APK: app-release.apk, 版本: 1.2, Build: 16, 大小: 37.50 MB
[版本比较] 远程版本: 1.2 (组件: [1, 2], Build: 16)
[版本比较] 本地版本: 1.2 (组件: [1, 2], Build: 15)
[版本比较] 版本号相同，比较 Build 号: 远程=16, 本地=15, 结果=true
[版本更新] ✓ 找到最新版本: app-release.apk (V1.2.016)
```

### 2. 工序记录项目选择功能

#### 问题
项目号和项目名称的点击事件被注释掉了，导致无法选择项目。

#### 修复
1. 启用了 `tvProjectCode` 和 `tvProjectName` 的点击事件
2. 添加了详细的调试日志

#### 新增日志点
- **点击事件**: 显示用户点击了哪个元素
- **项目列表**: 显示所有可用项目
- **当前选择**: 显示当前选中的项目
- **用户选择**: 显示用户选择了哪个项目
- **对话框状态**: 显示对话框的打开和关闭

#### 日志标签
```
ProcessRecordActivity
```

#### 关键日志示例
```
[项目选择] 点击项目号，准备显示项目选择对话框
[项目选择] 开始显示项目选择对话框
[项目选择] 获取到 153 个项目
[项目选择] 当前选中项目: 柳工双20, 索引: 42
[项目选择] 项目[0]: 项目A
[项目选择] 项目[1]: 项目B
...
[项目选择] 用户选择了项目: 新项目 (索引: 10)
[项目选择] 项目切换完成，对话框关闭
```

## 构建和安装

### 方式一：使用自动化脚本（推荐）

```powershell
.\build_install_debug.ps1
```

这个脚本会：
1. 清理旧构建
2. 构建 Debug APK
3. 卸载旧版本
4. 安装新版本
5. 显示日志查看命令

### 方式二：手动构建

```powershell
# 1. 构建 Debug APK
.\gradlew clean assembleDebug

# 2. 卸载旧版本
adb uninstall com.testcenter.qrscanner
adb uninstall com.testcenter.qrscanner.debug

# 3. 安装新版本
adb install app\build\outputs\apk\debug\app-debug.apk
```

### 方式三：只构建不安装

```powershell
.\build_debug.ps1
```

## 查看日志

### 查看所有调试日志

```powershell
adb logcat -s ApkUpdateManager:D ProcessRecordActivity:D PermissionService:D AuthenticationService:D
```

### 只查看版本更新日志

```powershell
adb logcat -s ApkUpdateManager:D
```

### 只查看项目选择日志

```powershell
adb logcat -s ProcessRecordActivity:D
```

### 实时监控（推荐）

```powershell
# 清除旧日志
adb logcat -c

# 开始监控
adb logcat | Select-String -Pattern "版本更新|项目选择|权限"
```

## 测试步骤

### 测试版本更新

1. 安装 Debug 版本
2. 打开应用并登录
3. 点击菜单 → "检查更新"
4. 查看日志输出
5. 观察是否正确检测到新版本

**预期日志**：
- 显示当前版本号
- 显示服务器上的 APK 列表
- 显示版本比较过程
- 显示最终结果

### 测试项目选择

1. 安装 Debug 版本
2. 打开应用并登录
3. 切换到"工序记录"标签
4. 点击"项目号"或"项目名称"
5. 查看日志输出
6. 观察是否显示项目选择对话框

**预期日志**：
- 显示点击事件
- 显示项目列表
- 显示当前选择
- 显示用户选择

## Debug vs Release 版本区别

| 特性 | Debug 版本 | Release 版本 |
|------|-----------|-------------|
| 包名 | com.testcenter.qrscanner.debug | com.testcenter.qrscanner |
| 日志 | 完整详细日志 | 最小日志 |
| 混淆 | 无混淆 | ProGuard 混淆 |
| 签名 | Debug 签名 | Release 签名 |
| 大小 | 较大 | 较小 |
| 性能 | 较慢 | 优化 |
| 调试 | 可调试 | 不可调试 |

## 常见问题

### Q: Debug 版本和 Release 版本可以同时安装吗？
A: 可以，它们使用不同的包名（applicationIdSuffix ".debug"）

### Q: Debug 版本的日志会影响性能吗？
A: 会有轻微影响，但对于调试来说是可接受的

### Q: 如何切换回 Release 版本？
A: 卸载 Debug 版本，然后安装 Release 版本

### Q: 日志太多怎么办？
A: 使用过滤器只查看特定标签的日志

## 相关文件

- `app/src/main/java/com/testcenter/qrscanner/update/ApkUpdateManager.kt` - 版本更新管理器
- `app/src/main/java/com/testcenter/qrscanner/ProcessRecordActivity.kt` - 工序记录页面
- `build_debug.ps1` - 构建 Debug 版本脚本
- `build_install_debug.ps1` - 构建并安装 Debug 版本脚本
- `app/build.gradle` - 构建配置

## 下一步

1. 使用 Debug 版本测试版本更新功能
2. 收集日志并分析问题
3. 使用 Debug 版本测试项目选择功能
4. 确认问题修复后，构建 Release 版本
