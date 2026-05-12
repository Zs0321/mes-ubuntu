# qrmes-kingdee-integration

QRMES split 架构中的金蝶云星空统一集成仓。

这个仓的定位不是单纯的金蝶 client，而是“金蝶同步中台”：
- 统一封装金蝶登录与 WebAPI 调用
- 统一管理 MES ↔ 金蝶 的拉取、落库、回写
- 统一对外暴露本地数据库 API，避免业务系统直接碰金蝶
- 为 `qrmes-web-core`、`qrmes-finance-service` 等 split 仓复用

## 当前状态

适用账套：`20260330测试`
账套 ID：`69ca3e07b23d85`
服务地址：`http://172.16.30.10:9010`
本地数据库：`/volume2/MES/QRMES/kingdee_sync.db`

当前完成度：
- 严格完成度：`约 86%`
- 工程完成度：约 `90%`
- 下一版增量：已补齐 8 类低风险基础主数据 dataset

## 已完全打通的数据对象

- 物料主数据：`BD_MATERIAL`
- BOM：`ENG_BOM`
- 采购订单：`PUR_PurchaseOrder`
- 生产订单：`PRD_MO`
- 生产用料清单：`PRD_PPBOM`
- 生产入库/完工入库：`PRD_INSTOCK`
- 工序计划：`SFC_OperationPlanning`
- 工序汇报：`SFC_OperationReport`
- 工艺路线：`ENG_ROUTE`
- 仓库：`BD_STOCK`
- 批次追溯基础层：`STK_INVENTORY`
- 批次追溯回写：`STK_LOTADJUST`
- 序列号主档：`BD_SerialMainFile`
- 批号序列号关系：`QT_LotSNRelation`
- 供应商：`BD_Supplier`
- 客户：`BD_Customer`
- 部门：`BD_Department`
- 员工：`BD_Empinfo`
- 计量单位：`BD_UNIT`
- 组织：`ORG_Organizations`
- 物料分类：`BD_MATERIALCATEGORY`
- 库存状态：`BD_STOCKSTATUS`

## 已部分打通的追溯能力

- 序列号追溯：`XLHZS -> QT_TraceShow + QT_TraceFilter + QT_TreeModel`
- 批号序列号综合追溯：`PHXLHZHZS -> QT_TraceShow + QT_TraceFilter + QT_TreeModel`

当前已提供桥接查询接口：
- `GET /api/local-db/trace/serial?serial_no=<序列号>&material_code=<物料编码>`

桥接接口会返回：
- 根节点命中（`serial_master`）
- 关系命中（`lot_serial_relation`）
- `trace_runtime`（`XLHZS / QT_TraceShow / QT_TraceFilter`）
- `tree_model`（`QT_TreeModel` 的核心列定义）
- `tree_nodes`（桥接树结构）

已确认的 `QT_TreeModel` 核心列：
- 树列：`FLEAFTEXT`
- 明细列：`FSeq` / `FDLOT` / `FDSERIALID`

## 当前未打通项

- 单件产品加工过程追溯：`DJCPJGGCZS`
  - 当前命中：`BOS_FreeTrailForModel`
  - 结论：当前账套下仍受模块试用/授权门槛限制，暂未开放

## 通用金蝶 WebAPI 能力

当前已支持：
- `LoginBySign`
- `ExecuteBillQuery`
- `View`
- `Save`

核心代码：
- `qrmes_kingdee_integration/client/base.py`

## 本地数据库中台 API

### 健康检查 / 查询
- `GET /health`
- `GET /api/local-db/<dataset>`

当前支持 dataset：
- `material`
- `bom`
- `purchase_order`
- `production_order`
- `production_material_list`
- `production_instock`
- `operation_planning`
- `operation_report`
- `routing`
- `warehouse`
- `batch_trace`
- `serial_master`
- `lot_serial_relation`
- `supplier`
- `customer`
- `department`
- `employee`
- `unit`
- `organization`
- `material_category`
- `stock_status`

### 拉取同步
- `POST /api/sync/materials/pull`
- `POST /api/sync/boms/pull`
- `POST /api/sync/purchase-orders/pull`
- `POST /api/sync/production-orders/pull`
- `POST /api/sync/production-material-lists/pull`
- `POST /api/sync/production-instocks/pull`
- `POST /api/sync/operation-plannings/pull`
- `POST /api/sync/operation-reports/pull`
- `POST /api/sync/routings/pull`
- `POST /api/sync/warehouses/pull`
- `POST /api/sync/batch-traces/pull`
- `POST /api/sync/serial-masters/pull`
- `POST /api/sync/lot-serial-relations/pull`
- `POST /api/sync/suppliers/pull`
- `POST /api/sync/customers/pull`
- `POST /api/sync/departments/pull`
- `POST /api/sync/employees/pull`
- `POST /api/sync/units/pull`
- `POST /api/sync/organizations/pull`
- `POST /api/sync/material-categories/pull`
- `POST /api/sync/stock-statuses/pull`

### 本地修改回写
- `POST /api/local-db/material/<business_key>`
- `POST /api/local-db/bom/<business_key>`
- `POST /api/local-db/purchase_order/<business_key>`
- `POST /api/local-db/production_order/<business_key>`
- `POST /api/local-db/routing/<business_key>`
- `POST /api/local-db/warehouse/<business_key>`
- `POST /api/local-db/batch_trace/<business_key>`

### 追溯桥接
- `GET /api/local-db/trace/serial?serial_no=<序列号>&material_code=<物料编码>`

## 目录结构

```text
qrmes-kingdee-integration/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── start.sh
├── stop.sh
├── status.sh
├── deploy.sh
├── docs/
├── scripts/
├── qrmes_kingdee_integration/
└── tests/
```

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/init_local_db.py
python3 -m pytest -q
./start.sh
```

## 自动同步

默认已支持自动同步与自动消费回写队列：
- `QRMES_KINGDEE_AUTO_SYNC=true`
- `QRMES_KINGDEE_PULL_INTERVAL_SECONDS=300`

## 部署信息

服务器常驻：
- 代码目录：`/volume2/mes_ubuntu_split_result/qrmes-kingdee-integration`
- 运行时目录：`/volume2/MES/QRMES/kingdee_sync_runtime`
- 数据库：`/volume2/MES/QRMES/kingdee_sync.db`
- 服务地址：`http://172.16.30.10:9010`

## 文档索引

- 需求开发正文：`docs/飞书文档-金蝶同步中台正式版.md`
- 进度快照：`docs/进度快照-2026-04-22-kingdee-integration.md`
- Spec：`docs/spec.md`
- 接口清单：`docs/interface-checklist.md`

## 备注

当前最核心的设计原则是：
- 第三方业务系统不直接操作金蝶
- 第三方统一走本地数据库 / 本地 API / 中台服务
- 金蝶同步、回写、队列、追溯桥接能力统一收口到本仓
