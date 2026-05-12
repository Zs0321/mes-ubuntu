# Debug 版本 vs Release 版本对比

## 你当前遇到的问题

从截图看，你安装的是 **Debug 版本**，显示为 `版本: 1.1-debug`

## 两个版本的区别

| 特性 | Debug 版本 | Release 版本 |
|------|-----------|-------------|
| **包名** | `com.testcenter.qrscanner.debug` | `com.testcenter.qrscanner` |
| **版本名称** | `1.2-debug` | `1.2` |
| **versionCode** | 15 | 15 |
| **签名** | Android Studio debug 签名 | 正式签名 (PanovationQrtest.jks) |
| **构建命令** | `gradlew assembleDebug` | `gradlew assembleRelease` |
| **APK 文件名** | `Panovation MesApp v1.2_015.apk` | `Panovation_MesApp_v1.2_015.apk` |
| **安装界面显示** | `1.2-debug` | `1.2` |
| **能否同时安装** | 可以（包名不同） | - |
| **用于** | 开发测试 | 正式发布 |

## 为什么安装界面只显示 1.1-debug

Android 安装界面默认只显示 `versionName`，不显示 `versionCode`。

你看到的 `1.1-debug` 是因为：
- 这是 Debug 版本
- versionName = "1.1"
- 自动添加了 "-debug" 后缀

## 如何构建正确的 Release 版本

### 方法 1: 使用命令行

```powershell
# 清理
.\gradlew.bat clean

# 构建 Release
.\gradlew.bat assembleRelease
```

### 方法 2: 使用 Android Studio

1. 打开 Android Studio
2. 菜单: Build → Select Build Variant
3. 选择 "release"
4. 菜单: Build → Build Bundle(s) / APK(s) → Build APK(s)

### 方法 3: 使用提供的脚本

```powershell
.\build_release_only.ps1
```

## 验证是否是 Release 版本

### 检查文件名
```
✓ 正确: app\build\outputs\apk\release\Panovation_MesApp_v1.2_015.apk
✗ 错误: app\build\outputs\apk\debug\Panovation MesApp v1.2_015.apk
```

### 检查安装界面
```
✓ 正确: 版本: 1.2 (没有 -debug 后缀)
✗ 错误: 版本: 1.2-debug (有 -debug 后缀)
```

### 使用 ADB 检查包名
```powershell
# 安装后检查
adb shell pm list packages | findstr testcenter

# 应该看到:
# package:com.testcenter.qrscanner  ← Release 版本
# 而不是:
# package:com.testcenter.qrscanner.debug  ← Debug 版本
```

## 常见错误

### 错误 1: 在 Android Studio 中点击 Run 按钮
- 这会安装 Debug 版本
- 应该使用 Build → Build APK(s)

### 错误 2: 使用 gradlew assembleDebug
- 这会构建 Debug 版本
- 应该使用 `gradlew assembleRelease`

### 错误 3: 混淆 Debug 和 Release APK
- Debug APK 在 `app/build/outputs/apk/debug/` 目录
- Release APK 在 `app/build/outputs/apk/release/` 目录

## 升级场景分析

### 场景 1: 从 Release 升级到 Release ✓
```
已安装: com.testcenter.qrscanner (versionCode 14)
新版本: com.testcenter.qrscanner (versionCode 15)
结果: 可以覆盖安装
```

### 场景 2: 从 Debug 升级到 Debug ✓
```
已安装: com.testcenter.qrscanner.debug (versionCode 14)
新版本: com.testcenter.qrscanner.debug (versionCode 15)
结果: 可以覆盖安装
```

### 场景 3: 从 Release 升级到 Debug ✗
```
已安装: com.testcenter.qrscanner (versionCode 14)
新版本: com.testcenter.qrscanner.debug (versionCode 15)
结果: 作为新应用安装（包名不同）
```

### 场景 4: 从 Debug 升级到 Release ✗
```
已安装: com.testcenter.qrscanner.debug (versionCode 14)
新版本: com.testcenter.qrscanner (versionCode 15)
结果: 作为新应用安装（包名不同）
```

## 解决你的问题

### 如果手机上已安装 Release 版本

1. 构建 Release APK:
   ```powershell
   .\gradlew.bat assembleRelease
   ```

2. 安装 Release APK:
   ```powershell
   adb install -r app\build\outputs\apk\release\Panovation_MesApp_v1.2_015.apk
   ```

3. 验证安装界面显示: `版本: 1.2` (没有 -debug)

### 如果手机上已安装 Debug 版本

你有两个选择:

**选择 1: 继续使用 Debug 版本**
- 构建新的 Debug 版本
- 可以覆盖安装

**选择 2: 切换到 Release 版本**
- 先卸载 Debug 版本
- 安装 Release 版本
- 以后只发布 Release 版本

## 推荐做法

1. **开发阶段**: 使用 Debug 版本
2. **测试阶段**: 使用 Release 版本
3. **正式发布**: 只发布 Release 版本
4. **版本管理**: 每次发布递增 versionCode

## 快速检查清单

在分发 APK 之前，检查:

- [ ] APK 在 `release` 目录下
- [ ] 文件名不包含空格（`Panovation_MesApp_v1.2_015.apk`）
- [ ] 安装后版本名称不包含 `-debug`
- [ ] 包名是 `com.testcenter.qrscanner`（不带 .debug）
- [ ] versionCode 大于之前的版本
