# qrmes-finance-service

来源仓库：mes_ubuntu

说明：报价/财务服务初始拆分仓。当前仍依赖主仓部分共享配置与认证模块。

这是从 monorepo 自动抽取的首轮拆分结果，主要目标是把目录和依赖边界先拉开。
是否可直接独立运行，仍取决于后续共享配置、部署、测试与 import 路径改造。

已复制来源路径：
- app_web/backend
- app_web/finance_demo.py
- app_web/requirements.txt
- changjiang-bom-pricing
- tests/test_finance_demo_skill_quote_routes.py
- tests/test_finance_demo_simplified_home.py
- tests/test_finance_motor_weight_rules.py
- tests/test_finance_quote_training_and_tax.py
- tests/test_finance_skill_quote_service.py
- tests/test_analyze_pricing_gaps.py
- tests/test_extract_bom_xlsx.py
- tests/test_format_estimate_workbook.py
- tests/test_model_volume_pricing.py
- docs/reports/2026-04-20-liugong-motor-quote-routes.md
- docs/plans/2026-04-20-finance-demo-gap-checklist.md


后续增强：
- 已补充 `qrmes_shared_core/`、顶层 shim 模块，以及 `app_web/run_finance_demo.py` 独立入口。

- 已把 finance_demo 的共享依赖导入切到 `qrmes_shared_core.*`，并将启动方式统一为 `python -m app_web.run_finance_demo`。
