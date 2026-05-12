# qrmes-finance-service

独立后的报价/财务服务仓。

包含：
- app_web/backend
- app_web/finance_demo.py
- changjiang-bom-pricing
- qrmes_shared_core

快速启动：
1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. 按需复制 `.env.example`
4. `./run.sh`

当前状态：
- 已具备独立入口 `app_web/run_finance_demo.py`
- 已接入 `qrmes_shared_core`
- 仍建议后续继续清理历史 import 与部署脚本

如与 `qrmes-shared-core` 同级放置，可先执行 `scripts/install_shared_core.sh` 安装共享层。

可用 `scripts/healthcheck.sh` 做本地健康检查。
