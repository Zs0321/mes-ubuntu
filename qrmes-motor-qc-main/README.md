# qrmes-motor-qc

独立后的 Motor QC 业务仓。

包含：
- app_web/motor_qc
- motor_qc 静态资源与模板
- tests/motor_qc
- qrmes_shared_core

快速启动：
1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. 按需复制 `.env.example`
4. `./run.sh`

当前状态：
- 已具备独立入口 `app_web/run_motor_qc.py`
- 已接入 `qrmes_shared_core`
- 已补齐 `app_web/test_report_service.py`

如与 `qrmes-shared-core` 同级放置，可先执行 `scripts/install_shared_core.sh` 安装共享层。

可用 `scripts/healthcheck.sh` 做本地健康检查。
