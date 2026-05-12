# 金蝶同步中台进度快照

更新时间：2026-04-22
仓库：`mes_ubuntu_split_result/qrmes-kingdee-integration`
服务：`http://172.16.30.10:9010`
账套：`20260330测试`
账套ID：`69ca3e07b23d85`

## 一、当前已完成主线

已完全打通：
- 物料主数据：`BD_MATERIAL`
- BOM：`ENG_BOM`
- 采购订单：`PUR_PurchaseOrder`
- 生产订单：`PRD_MO`
- 工艺路线：`ENG_ROUTE`
- 仓库：`BD_STOCK`
- 批次追溯基础层：`STK_INVENTORY`（回写：`STK_LOTADJUST`）
- 序列号主档：`BD_SerialMainFile`
- 批号序列号关系：`QT_LotSNRelation`

已部分打通：
- 序列号追溯：`XLHZS -> QT_TraceShow + QT_TraceFilter + QT_TreeModel`
- 批号序列号综合追溯：`PHXLHZHZS -> QT_TraceShow + QT_TraceFilter + QT_TreeModel`

未打通：
- 单件产品加工过程追溯：`DJCPJGGCZS`（当前命中 `BOS_FreeTrailForModel`，属于模块试用/授权门槛页）

## 二、当前已支持 API（按中台侧）

### 通用 WebAPI 能力
- `LoginBySign`
- `ExecuteBillQuery`
- `View`
- `Save`

### 本地 DB API
- `GET /health`
- `GET /api/local-db/<dataset>`
- `POST /api/sync/materials/pull`
- `POST /api/sync/boms/pull`
- `POST /api/sync/purchase-orders/pull`
- `POST /api/sync/production-orders/pull`
- `POST /api/sync/routings/pull`
- `POST /api/sync/warehouses/pull`
- `POST /api/sync/batch-traces/pull`
- `POST /api/sync/serial-masters/pull`
- `POST /api/sync/lot-serial-relations/pull`
- `GET /api/local-db/trace/serial?serial_no=<序列号>&material_code=<物料编码>`
- `POST /api/local-db/material/<business_key>`
- `POST /api/local-db/bom/<business_key>`
- `POST /api/local-db/purchase_order/<business_key>`
- `POST /api/local-db/production_order/<business_key>`
- `POST /api/local-db/routing/<business_key>`
- `POST /api/local-db/warehouse/<business_key>`
- `POST /api/local-db/batch_trace/<business_key>`

## 三、关键细追溯结论
- `XLHZD` 实际对象：`BD_SerialMainFile`
- `PHXLHGX / PHXLHGXLB` 实际对象：`QT_LotSNRelation`
- `XLHZS / PHXLHZHZS` 实际对象：`QT_TraceShow + QT_TraceFilter`
- 追溯树展示对象：`QT_TreeModel`
- `QT_TreeModel` 已确认核心列：
  - 树列：`FLEAFTEXT`
  - 明细列：`FSeq` / `FDLOT` / `FDSERIALID`

## 四、当前完成度
- 严格完成度：`9 / 11 = 81.82%`
- 工程完成度（含已桥接的追溯树能力）：约 `87.27%`

## 五、当前阻塞点
- `QT_LotSNRelation` 在当前测试账套下实测返回 0 条，导致追溯树桥接当前只有根节点，没有真实关系子节点。
- `DJCPJGGCZS` 受模块授权/试用门槛影响，当前无法进入真实业务页继续打通。

## 七、Web 端接入边界

`qrmes-web-core` 后端通过 HTTP 调 `qrmes-kingdee-integration` 本地 API，是后续接入方案，不作为当前阶段实施内容。

当前要求：
- 金蝶同步中台尚未完全打通前，暂不切换 Web 端；
- 不重启、不改动 8891 正式服务；
- 优先继续完成中台自身的数据集、追溯树、回写闭环和稳定性验证；
- 等中台验收后，再单独评估 `qrmes-web-core` 代理或客户端接入。

## 八、已同步更新的文档
- `docs/spec.md`
- `docs/interface-checklist.md`
- `docs/飞书文档-金蝶同步中台正式版.md`
- `docs/kingdee-material-serial-key-plan.md`
