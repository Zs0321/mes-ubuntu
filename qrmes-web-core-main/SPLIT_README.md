# qrmes-web-core

来源仓库：mes_ubuntu

说明：MES Web 主后端核心仓。已剥离 finance backend 与 motor_qc 域代码。

这是从 monorepo 自动抽取的首轮拆分结果，主要目标是把目录和依赖边界先拉开。
是否可直接独立运行，仍取决于后续共享配置、部署、测试与 import 路径改造。

已复制来源路径：
- app_web/requirements.txt
- scripts/start_mesapp_17216207.sh
- scripts/stop_mesapp_17216207.sh
- scripts/deploy_from_gitlab.sh
- scripts/gitlab_ci_deploy.sh
- scripts/deploy_test_in_mes.sh
- scripts/deploy_test_to_nas.sh
- docs/ARCHITECTURE.md
- docs/DEPLOY_GUIDE.md
- docs/DEVELOPER_GUIDE.md
- docs/MAINTENANCE_GUIDE.md
- README.md
- app_web (filtered)
- tests (filtered)


后续增强：
- 已把多份共享基础模块替换为指向本仓 `qrmes_shared_core/` 的 shim，减少重复维护。

- 已继续清理部分历史共享导入，逐步从 shim 过渡到直接 `qrmes_shared_core.*` 导入。
