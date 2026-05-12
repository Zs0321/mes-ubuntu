# QRMES 金蝶集成仓需求开发文档（Spec Kit）

详见外部规划文件：
- `.hermes/plans/2026-04-22_144500-qrmes-kingdee-integration-spec.md`

本仓执行时以该文档为主，并逐步拆分为：
- `docs/interface-checklist.md`
- `docs/field-mapping/*.md`
- `docs/runbooks/*.md`
- `docs/material-traceability-spec.md`

当前初始化范围：
- 新仓骨架
- 基础配置/签名/客户端代码
- 后续将继续接入表单领域模块与同步编排

## 已验证环境
- 登录地址：`http://jindie.panovation.tech:8088/k3cloud`
- 已验证账套：`20260330测试`
- 已验证高权限账号：`AI`
- 已验证组织：`100 创崎新能源技术（上海）有限公司`

## 已在 20260330测试 中确认的菜单编码 / FormId 候选
说明：以下编码来自账套内“全部应用搜索”结果，已可作为当前阶段开发的真实候选 FormId；后续仍应在接口联调时再做一次 View / Query 实测确认。

### 生产工单 / 用料主线
- `SCDD`：生产订单
- `SCDDLB`：生产订单列表
- `SCYLQDLB`：生产用料清单列表
- `SCYLQDBGD`：生产用料清单变更单
- `SCYLQDBGDLB`：生产用料清单变更单列表

### 工艺路线 / 工序
- `GYLX`：工艺路线
- `GYLXLB`：工艺路线列表
- `GYLXCX`：工艺路线（产线）
- `GYLXCXLB`：工艺路线（产线）列表
- `GXHB`：工序汇报
- `GXHBLB`：工序汇报列表
- `GXJHLB`：工序计划列表
- `GXZYD`：工序转移单
- `GXKZM`：工序控制码
- `GXKZMLB`：工序控制码列表

### 仓库 / 仓位
- `CK`：仓库列表
- `CWZJ`：仓位值集列表
- `WWCKSZ`：委外仓库设置

### 批次 / 追溯
- `PHZS`：批号追溯
- `PHXLHZHZS`：批号序列号综合追溯
- `PHXLHGX`：批号序列号关系
- `PHXLHGXLB`：批号序列号关系列表
- `XLHZS`：序列号追溯
- `DJCPJGGCZS`：单件产品加工过程追溯（智慧车间MES）

## 当前开发结论
1. `生产工单/制造订单同步` 不应再暂按 `PRD_MO` 作为唯一主表单假设，当前账套中可直接看到面向业务菜单的 `SCDD / SCDDLB`。
2. `工艺路线/工序同步` 已可先按 `GYLX*`、`GX*` 系列编码建模块骨架。
3. `仓库/库位基础信息同步` 当前至少可先落 `CK` 与 `CWZJ` 两类入口。
4. `批次追溯同步` 当前应优先围绕 `PHZS`、`PHXLHZHZS`、`XLHZS` 建追溯查询封装。
5. 新仓内已落地并通过测试的通用能力包括：`LoginBySign`、`View`、`Save`、`ExecuteBillQuery`、响应状态解析，以及生产工单/工艺路线/仓库/批次追溯四类表单服务骨架。
7. 已落地本地双向同步基础设施：
   - 本地 SQLite 数据库默认路径：`/Volumes/172.16.30.10/volume2/MES/QRMES/kingdee_sync.db`（服务器实际运行使用 `/volume2/MES/QRMES/kingdee_sync.db`）
   - 入站同步：从金蝶拉取并写入本地库
   - 出站同步：本地修改入队后由仓库服务调用金蝶 `Save` 回写
   - 已完成真实联通的数据集：`material` / `bom` / `purchase_order` / `production_order` / `production_material_list` / `production_instock` / `operation_planning` / `operation_report` / `routing` / `warehouse` / `batch_trace` / `serial_master` / `lot_serial_relation`
   - 下一版已补低风险基础主数据集：`supplier` / `customer` / `department` / `employee` / `unit` / `organization` / `material_category` / `stock_status`
   - 本地 API：`/api/local-db/<dataset>`、`/api/sync/materials/pull`、`/api/sync/boms/pull`、`/api/sync/purchase-orders/pull`、`/api/sync/production-orders/pull`、`/api/sync/production-material-lists/pull`、`/api/sync/production-instocks/pull`、`/api/sync/operation-plannings/pull`、`/api/sync/operation-reports/pull`、`/api/sync/routings/pull`、`/api/sync/warehouses/pull`、`/api/sync/batch-traces/pull`、`/api/sync/serial-masters/pull`、`/api/sync/lot-serial-relations/pull`、`/api/local-db/material/<business_key>`、`/api/local-db/bom/<business_key>`、`/api/local-db/purchase_order/<business_key>`、`/api/local-db/production_order/<business_key>`、`/api/local-db/routing/<business_key>`、`/api/local-db/warehouse/<business_key>`、`/api/local-db/batch_trace/<business_key>`
   - 自动同步 watcher：服务启动后会按 `QRMES_KINGDEE_PULL_INTERVAL_SECONDS` 定时拉取，并自动消费待回写队列
8. 已确认页面菜单编码不等于可直接用于 WebAPI 的 FormId：例如 `SCDD / SCDDLB` 为界面菜单编码，但真实可用于 API 查询的生产订单表单为 `PRD_MO`；工艺路线真实可用表单为 `ENG_ROUTE`；仓库真实可用表单为 `BD_STOCK`。
9. 批次追溯当前已确认基础查询表单为 `STK_INVENTORY`、回写表单为 `STK_LOTADJUST`；同时已验证 `PRD_PPBOM`、`PRD_INSTOCK` 可作为后续扩展生产追溯链路的相关表单。
10. 细追溯层新结论：
   - `XLHZD` 菜单实际落到 `BD_SerialMainFile`，已打通为 `serial_master` 数据集，并在历史环境实测拉取 100 条。
   - `PHXLHGX / PHXLHGXLB` 菜单实际落到 `QT_LotSNRelation`，已打通为 `lot_serial_relation` 数据集，当前测试账套实测返回 0 条。
   - `XLHZS / PHXLHZHZS` 菜单实际落到 `QT_TraceShow + QT_TraceFilter`，已确认不是普通单据型 WebAPI；当前已补一层本地桥接查询接口 `/api/local-db/trace/serial`，按前端必填条件 `FMATERIALID + FSERIALID` 返回本地根节点与已落库关系数据，并附带 `QT_TreeModel` 的核心列定义（`FLEAFTEXT` / `FSeq` / `FDLOT` / `FDSERIALID`）。
   - `DJCPJGGCZS` 当前实际命中 `BOS_FreeTrailForModel`，属于智慧车间模块试用/授权门槛页，当前账套未开放。
11. 远端常驻服务已部署在 `172.16.30.10:9010`，运行时目录为 `/volume2/MES/QRMES/kingdee_sync_runtime`；`qrmes-web-core` 调用中台本地 API 仅保留为后续接入方案，当前金蝶中台尚未完全打通，暂不切换 Web 端，也不重启 8891 正式服务。
12. 若业务决定将“物料编码 + 序列号”提升为金蝶正式字段，当前推荐先在 `BD_SerialMainFile` 上新增 `F_MES_MaterialSerialKey`，第一阶段优先采用显示/公式型实现；详细方案见 `docs/kingdee-material-serial-key-plan.md`。
13. 物料追溯执行页面和本地闭环的专项完整 spec 已独立到 `docs/material-traceability-spec.md`；该页面应按四个并列模块卡片呈现，不应作为从上到下的线性步骤页。
