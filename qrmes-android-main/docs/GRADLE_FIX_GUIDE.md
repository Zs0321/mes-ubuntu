# Gradle Wrapper修复指南

## 问题描述
`ClassNotFoundException: org.gradle.wrapper.GradleWrapperMain` 错误表明gradle-wrapper.jar文件损坏或不兼容。

## 解决方案

### 方案1: 手动下载正确的gradle wrapper jar
1. 删除现有文件：
   ```cmd
   del gradle\wrapper\gradle-wrapper.jar
   ```

2. 手动下载gradle-wrapper.jar：
   - 访问：https://repo1.maven.org/maven2/org/gradle/gradle-wrapper/8.4/gradle-wrapper-8.4.jar
   - 下载文件并保存到：`gradle\wrapper\gradle-wrapper.jar`

### 方案2: 使用系统gradle重新生成wrapper
如果系统已安装gradle：
```cmd
gradle wrapper --gradle-version 8.4
```

### 方案3: 直接使用gradle构建（绕过wrapper）
如果系统已安装gradle 8.4+：
```cmd
gradle clean build
```

### 方案4: 使用Android Studio构建
1. 用Android Studio打开项目
2. 让IDE自动修复gradle wrapper
3. 使用IDE的构建功能

## 验证修复
运行以下命令验证：
```cmd
gradlew --version
gradlew clean build
```

## 备注
- 确保Java版本兼容（推荐Java 17+）
- 网络连接正常，能够下载gradle分发包
- 如果仍有问题，考虑升级到更新版本的gradle
