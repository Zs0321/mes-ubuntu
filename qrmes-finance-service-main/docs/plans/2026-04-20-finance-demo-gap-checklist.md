# 报价系统待完善项开发清单

> For Hermes: 如需执行本清单，优先按 P0 → P1 → P2 顺序推进；涉及线上环境时先验证 `.7` 再回写仓库文档与测试基线。

目标：把 172.16.20.7:9001 上的报价系统从“可运行的半成品工作台”推进到“金蝶可用、报价链路闭环、测试基线一致、部署稳定”的状态。

架构摘要：当前报价系统由 `finance_demo.py` 暴露页面和 API，`backend/server.py` 负责编排，`FinanceSkillQuoteService` 统一收口传统规则报价 + AI 补充报价，`ExcelQuoteService` 负责 Excel 解析与导出，`KingdeeService` 负责 live BOM / 采购价来源。

技术栈：Flask、Kingdee API、Qwen/AI route、openpyxl、前端静态页 `static/finance_demo/*`。

---

## 一、当前确认结论

### 已确认可用
- `.7` 主服务已部署到 `http://172.16.20.7:9001`
- `/health` 正常
- `/finance-demo/` 已挂到主服务并受登录保护
- `.7` 金蝶配置文件缺失问题已通过补回 `.env.finance_demo_125` 解决
- `/api/health` 已从 `kingdee_ready=false` 变为 `kingdee_ready=true`
- 通过远端 Python 直连验证：
  - `materials(limit=2)` 成功返回 live 金蝶数据
  - `bom_headers(limit=2, keyword="电机")` 成功返回 live 金蝶数据
  - `sync_bom()` 成功拉回 46 条真实 BOM 项

### 已确认未完成/存在风险
- 当前仍使用 Flask development server，不是正式 WSGI 部署
- 报价系统相关 unittest 存在 6 条失败，说明测试基线与当前实现漂移
- live BOM 虽已连通，但存在大量 `missing_weight_codes` / `missing_purchase_codes`
- 报价状态里保留大量人工复核状态，说明业务仍未完全自动闭环

---

## 二、优先级清单

## P0：确保 live 金蝶链路稳定可用

### Task P0-1：把 `.7` 金蝶配置恢复步骤文档化

目标：避免下次更新代码后再次丢失 `.env.finance_demo_125`

文件：
- 修改：`docs/17216207_DEPLOYMENT.md`
- 新增（可选）：`docs/plans/2026-04-20-finance-demo-gap-checklist.md`

执行项：
1. 在部署文档中明确说明 `.7` 依赖 `/home/aiyan/MES-TEST-aiyan/mes_ubuntu/.env.finance_demo_125`
2. 记录恢复来源：同机目录 `/home/aiyan/MES-TEST-aiyan-9005/mes_ubuntu/.env.finance_demo_125`
3. 标注该文件不入 Git，但属于运行前置条件
4. 增加启动后验证：`/api/health` 中 `kingdee_ready` 必须为 `true`

验收：
- 文档能指导他人在 5 分钟内恢复 `.7` 金蝶配置

### Task P0-2：增加 `.7` 报价系统上线后检查脚本/步骤

目标：避免只验证 `/health`，却没验证报价系统 live 能力

文件：
- 修改：`scripts/start_mesapp_17216207.sh` 或新增独立 verify 脚本
- 修改：`docs/17216207_DEPLOYMENT.md`

执行项：
1. 增加验证步骤：
   - `/api/health` → `kingdee_ready=true`
   - 远端 Python 调 `KingdeeService.materials(limit=1)`
   - 远端 Python 调 `KingdeeService.bom_headers(limit=1, keyword="电机")`
2. 失败时输出明确错误信息，而不是只看主服务是否启动

验收：
- 可以区分“服务启动成功”和“live 数据链路成功”

### Task P0-3：补齐金蝶 live 数据缺口统计页/日志

目标：把 `missing_weight_codes`、`missing_purchase_codes` 从调试信息升级为可追踪问题清单

文件：
- 修改：`app_web/backend/services/kingdee_service.py`
- 修改：`app_web/finance_demo.py`
- 修改：`app_web/static/finance_demo/app.js`

执行项：
1. 在 BOM 同步结果中保留缺失统计
2. 前端显式展示：
   - 缺重量数量
   - 缺采购价数量
   - 前 N 个物料编码
3. 导出复核清单时将这些缺口项纳入导出

验收：
- 财务可直接看到“这次 live BOM 还有哪些字段缺失，为什么不能完全自动报价”

---

## P1：修复“实现已变、测试未同步”的基线漂移

### Task P1-1：统一 `finance_demo.py` 的导出包契约

目标：确认 `export-package` 是否必须包含 `skill_outputs`

文件：
- 修改：`app_web/finance_demo.py`
- 修改：`app_web/backend/services/finance_skill_quote_service.py`
- 修改：`tests/test_finance_demo_skill_quote_routes.py`

现状：
- 测试要求 `skill_outputs`
- 当前 `finance_demo.py` 文本契约里看不到这个字段

执行项：
1. 判断导出 zip 是否应包含 skill 原始产物
2. 若应包含：补回接口/字段/注释
3. 若不再需要：更新测试到新契约

验收：
- `test_finance_demo_export_package_mentions_skill_outputs` 通过

### Task P1-2：统一 AI 超时默认值与测试预期

目标：修复 `PRICING_QWEN_TIMEOUT` 测试漂移

文件：
- 修改：`app_web/backend/services/ai_route_quote_service.py`
- 修改：`tests/test_finance_demo_simplified_home.py`

现状：
- 实现默认值是 `90`
- 旧测试仍断言 `45`

执行项：
1. 确认当前业务默认值到底应该是多少
2. 若 `90` 是新基线，则更新测试
3. 若应回退为 `45`，则改实现并验证超时策略

验收：
- `test_ai_route_service_uses_longer_pricing_timeout_and_retry_defaults` 通过

### Task P1-3：统一 finance demo 首页模板与文案测试

目标：修复 UI 改版后的模板/文案测试漂移

文件：
- 修改：`app_web/templates/finance_demo.html`
- 修改：`app_web/static/finance_demo/index.html`
- 修改：`app_web/static/finance_demo/app.js`
- 修改：`tests/test_finance_demo_simplified_home.py`

现状：
- 模板已改为更宽布局（不是 `max-width: 1360px`）
- 测试仍在断言旧布局/旧文案
- 单物料模块主体存在，但测试与当前结构仍有漂移

执行项：
1. 决定以“当前 UI”为基线还是“旧 UI 测试”为基线
2. 更新以下断言的一致性：
   - 财务首页文案
   - 容器宽度/布局类名
   - 单物料模块关键 DOM
   - “报价明细与异常清单”等首页文案
3. 为改版后的 UI 固化更稳定的测试锚点（例如 `data-testid`）

验收：
- finance demo 相关 6 条失败测试全部通过

---

## P1：提升线上部署稳定性

### Task P1-4：把 `.7` 从 Flask dev server 升级到正式 WSGI

目标：避免长任务 + 多线程报价在开发服务器上运行

文件：
- 修改：`scripts/start_mesapp_17216207.sh`
- 新增/修改：WSGI 启动配置（gunicorn/waitress 二选一）
- 修改：`docs/17216207_DEPLOYMENT.md`

执行项：
1. 选定运行方式：
   - Linux 优先 gunicorn
   - 若依赖简单则也可 waitress
2. 保留现有 env 加载逻辑
3. 启动后验证：
   - `/health`
   - `/api/health`
   - 报价任务异步轮询不受影响

验收：
- 日志里不再出现 “This is a development server” 警告

---

## P2：把“半自动报价工作台”推进成更完整闭环

### Task P2-1：新增型号 → 金蝶同步闭环

目标：把“工程师新增型号，待后续同步到金蝶”变成真正闭环

文件：
- 修改：`app_web/static/finance_demo/app.js`
- 修改：`app_web/finance_demo.py`
- 修改：`app_web/backend/server.py`
- 修改：`app_web/backend/services/kingdee_service.py`

执行项：
1. 明确新增型号在前端的保存位置
2. 增加“提交到金蝶/标记待同步/同步状态回写”流程
3. 给财务视图一个“新型号已进入正式库/仍是草稿”的状态

验收：
- 新增型号不再长期停留在前端草稿态

### Task P2-2：把人工复核状态收敛成可操作工作流

目标：让“待补参数/缺重量/缺材质/模型超时”等状态有明确下一步动作

文件：
- 修改：`app_web/static/finance_demo/app.js`
- 修改：`app_web/backend/services/excel_quote_service.py`
- 修改：`app_web/backend/services/finance_skill_quote_service.py`

执行项：
1. 为各状态定义标准动作：
   - 缺重量 → 去补重量来源
   - 缺传统参考 → 去补采购价或规则库
   - 模型超时 → 可重试 AI
   - 名称规格推断报价 → 人工确认区间规则
2. 在前端表格和导出工作簿里显示“建议动作”列
3. 汇总页把这些状态分桶展示

验收：
- 财务看到异常后，不需要靠经验猜下一步做什么

### Task P2-3：补全 live 报价监控指标

目标：让报价系统可被运维和业务追踪

文件：
- 修改：`app_web/finance_demo.py`
- 修改：`app_web/backend/server.py`
- 修改：`app_web/backend/services/*quote*.py`

执行项：
1. 增加指标：
   - Excel 报价成功率
   - AI 报价超时率
   - 缺重量率
   - 缺采购价率
   - 高价差率
2. 输出到日志或可查询接口
3. 后续接系统日志页面或运维看板

验收：
- 能回答“最近一周 live 报价最常失败在哪一步”

---

## 三、建议执行顺序

1. 先做 P0-1 / P0-2
   - 固化 `.7` live 金蝶配置恢复与验证流程
2. 再做 P1-1 / P1-2 / P1-3
   - 把当前实现和测试基线重新对齐
3. 然后做 P1-4
   - 升级正式 WSGI 部署
4. 最后推进 P2
   - 真正提升业务闭环和可运维性

---

## 四、已知现场事实（本次验证）

- `.7` 当前代码目录：`/home/aiyan/MES-TEST-aiyan/mes_ubuntu`
- `.7` 运行数据目录：`/home/aiyan/QRMES`
- `.7` 当前进程脚本：`scripts/start_mesapp_17216207.sh`
- `.7` 缺失的关键文件曾为：`/home/aiyan/MES-TEST-aiyan/mes_ubuntu/.env.finance_demo_125`
- 可恢复来源：`/home/aiyan/MES-TEST-aiyan-9005/mes_ubuntu/.env.finance_demo_125`
- live 金蝶验证样例：
  - `materials(limit=2)` 成功
  - `bom_headers(limit=2, keyword="电机")` 成功
  - `sync_bom("Genesis-Motor-AP-12-B_V1.0")` 成功，返回 46 条 BOM 项

---

## 五、建议补的回归验证命令

本地文本契约测试：
```bash
python3 -m unittest \
  mes_ubuntu.tests.test_finance_demo_skill_quote_routes \
  mes_ubuntu.tests.test_finance_skill_quote_service \
  mes_ubuntu.tests.test_finance_demo_simplified_home
```

`.7` 线上验证：
```bash
python3 - <<'PY'
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:9001/health', timeout=10).read().decode())
print(urllib.request.urlopen('http://127.0.0.1:9001/api/health', timeout=10).read().decode())
PY
```

金蝶 live 数据验证：
```bash
cd /home/aiyan/MES-TEST-aiyan/mes_ubuntu/app_web
set -a
. ../.env.finance_demo_125
set +a
python3 - <<'PY'
from backend.config import load_config
from backend.services.kingdee_service import KingdeeService
cfg = load_config(static_dir=None)
svc = KingdeeService(cfg.kingdee)
print(svc.materials(limit=1).data)
print(svc.bom_headers(limit=1, keyword='电机').data)
PY
```
