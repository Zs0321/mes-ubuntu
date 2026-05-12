# 物料追溯与来料检查 FormId 计划

本计划用于“收货贴标 -> 来料检绑定 -> 入库 -> 配料 -> 装配绑定 -> 后续写回金蝶”的分阶段实施。

## 当前阶段

当前先在 `qrmes-kingdee-integration` 的本地 SQLite 数据库 `/volume2/MES/QRMES/kingdee_sync.db` 中打通最小闭环，不对未知金蝶对象做强写回。

已新增本地表：

- `material_batch`：物料批次，生成 `ML|物料|供应商|日期|流水`。
- `material_package`：包装单元，生成 `PK|批次码|包装序号`。
- `supplier_qr_map`：供应商原始二维码与内部批次映射。
- `receive_record`：收货记录。
- `iqc_record`：来料检记录。
- `inventory_stock`：库存台账，区分待检/可用/不合格等状态。
- `stock_move`：入库、配料、移动记录。
- `pick_record`：配料扫码记录。
- `assembly_bind`：产品 SN 与物料批次/包装/序列号绑定。
- `trace_event_log`：所有扫码/状态事件。
- `material_qrcode`：批次码、包装码二维码 payload 与打印状态。

## 已确认或已使用对象

| FormId | 作用 | 当前状态 |
| --- | --- | --- |
| `PUR_PurchaseOrder` | 采购订单来源 | 已有本地同步，可作为收货来源 |
| `BD_MATERIAL` | 物料主数据 | 已有本地同步 |
| `BD_Supplier` | 供应商主数据 | 已接入基础主数据，但字段仍需逐项校准 |
| `BD_STOCK` | 仓库基础资料 | 已有仓库同步，仓位/待检区字段需继续确认 |
| `STK_INVENTORY` | 即时库存/批次库存基础查询 | 已用于批次追溯基础层 |
| `STK_LOTADJUST` | 批次调整/回写候选 | 已有基础回写能力，但字段需按二维码场景校准 |

## 需要继续确认的金蝶写回对象

| 候选 FormId | 目标业务 | 需要确认的问题 |
| --- | --- | --- |
| `PUR_ReceiveBill` | 采购收料/收料通知 | 是否作为收货贴标写回主单；明细是否可增加内部批次码、包装码、供应商原始码字段 |
| `STK_InStock` | 采购入库 | 合格入库时是否生成/更新采购入库单；批次/包装二维码字段落在哪个明细字段 |
| 质量/来料检对象（待确认） | IQC 来料检记录 | 需要通过账套搜索或 XHR 抓取确认真实 FormId，不能硬猜 |
| 自定义字段 | 二维码写回 | 建议优先加在采购收料/入库明细或批次/序列号主档上 |

## 建议写回策略

1. 第一阶段：只写本地表，完成扫码、编码、二维码打印和追溯查询。
2. 第二阶段：确认 `PUR_ReceiveBill` 和 `STK_InStock` 字段后，加入本地 change queue，仍由中台统一写回。
3. 第三阶段：确认 IQC 质量对象后，将 `iqc_record` 与金蝶检验单/检验报告绑定。
4. 第四阶段：如果要二维码永久留在金蝶，新增自定义字段：
   - 内部批次码
   - 包装码
   - 二维码 JSON
   - 供应商原始二维码
   - MES 追溯事件 ID

## 当前可用接口

- `GET /api/traceability/health`
- `GET /api/traceability/purchase-orders`
- `POST /api/traceability/receive-label`
- `GET /api/traceability/batches/<batch_code>`
- `POST /api/traceability/iqc`
- `POST /api/traceability/putaway`
- `POST /api/traceability/pick`
- `POST /api/traceability/assembly-bind`
- `GET /api/traceability/trace/<code>`
- `GET /api/traceability/formid-plan`
