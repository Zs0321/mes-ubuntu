# qrmes-android

来源仓库：mes_ubuntu

说明：Android 客户端独立仓。已带走 Gradle 工程、图标、APK 发布脚本及部分 Android 文档。

这是从 monorepo 自动抽取的首轮拆分结果，主要目标是把目录和依赖边界先拉开。
是否可直接独立运行，仍取决于后续共享配置、部署、测试与 import 路径改造。

已复制来源路径：
- app
- gradle
- gradlew
- gradlew.bat
- build.gradle
- settings.gradle
- gradle.properties
- icons
- PanovationQrtest
- PanovationQrtest.jks
- apk-builds
- scripts/deploy_apk_to_qrmes_apk.sh
- docs/ANDROID_DATABASE_UNIFICATION.md
- docs/ANDROID_STUDIO_LAYOUT_GUIDE.md
- docs/APP_BRANDING_UPDATE.md
- docs/DEBUG_VERSION_GUIDE.md
- docs/DEBUG_VS_RELEASE_VERSIONS.md
- docs/GRADLE_FIX_GUIDE.md
- docs/APK-UPDATE
