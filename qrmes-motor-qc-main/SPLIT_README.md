# qrmes-motor-qc

来源仓库：mes_ubuntu

说明：Motor QC 业务域初始拆分仓。当前仍依赖共享权限/项目配置/照片索引能力。

这是从 monorepo 自动抽取的首轮拆分结果，主要目标是把目录和依赖边界先拉开。
是否可直接独立运行，仍取决于后续共享配置、部署、测试与 import 路径改造。

已复制来源路径：
- app_web/motor_qc
- app_web/templates/motor_qc
- app_web/static/js/motor_qc
- app_web/static/css/motor_qc
- tests/motor_qc
- scripts/build_edge_station_test_bundle.sh
- scripts/edge_camera_bridge.py
- scripts/edge_local_bridge_stub.py
- scripts/edge_local_frontend_regression.py
- scripts/edge_ui
- docs/experience/qc-error-lessons.md
- docs/QC_API_CONTRACT.md


后续增强：
- 已补充 `qrmes_shared_core/`、顶层 shim 模块、缺失的 `test_report_service.py`，以及 `app_web/run_motor_qc.py` 独立入口。

- 已把 motor_qc 核心文件的共享依赖导入切到 `qrmes_shared_core.*`，并将启动方式统一为 `python -m app_web.run_motor_qc`。
