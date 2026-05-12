# 物料追溯执行：可复用金蝶已有数据库字段说明

## 1. 文档目的

本文说明“物料追溯执行 - MESAPP”里，哪些字段可以复用金蝶已有主数据、单据或业务对象字段，哪些字段需要 MES 本地保留，哪些字段后续可能需要在金蝶中新增自定义字段。

当前原则：

1. 能复用金蝶已有字段的，不重复新增字段。
2. MES 执行过程字段先落本地追溯库，保证扫码、贴标、检验、入库、配料、装配绑定可闭环。
3. 后续正式写回金蝶时，再按真实 FormId 和字段名做映射，不硬猜字段。
4. ML 批次码是否直接作为金蝶批号，是字段复用方案里的关键决策点。

当前本地追溯库：

`/volume2/MES/QRMES/kingdee_sync.db`

当前中台模式：

`local_sqlite_only`

---

## 2. 总体分类

| 类型 | 处理方式 | 示例 |
|---|---|---|
| 可直接复用金蝶已有字段 | 不新增金蝶字段，MES 本地只保存关联键或快照 | 工单号、采购单号、物料编码、供应商、单位、仓库、数量 |
| 可复用金蝶对象，但 MES 本地仍需保留执行记录 | 金蝶保存正式单据，MES 保存现场扫码/执行流水 | 收货执行号、库存移动号、检验报告号、操作员 |
| MES 追溯专用字段 | 本地保留；后续如需写回金蝶，建议加自定义字段或独立追溯对象 | ML 内部批次码、PK 包装码、二维码 payload、打印任务、装配绑定关系、事件日志 |

---

## 3. 可以直接复用金蝶已有字段的数据

### 3.1 工单号

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `work_order_no` |
| 当前使用表 | `pick_record.work_order_no` |
| 可复用金蝶对象 | `PRD_MO` 生产订单 |
| 可复用金蝶字段 | 生产订单单号，通常对应 `FBillNo` |
| 是否建议新增金蝶字段 | 不建议新增 |

说明：

金蝶本身有生产订单/工单号。物料追溯执行里的工单号应引用金蝶 `PRD_MO` 的生产订单号，不需要新增 MES 工单号字段。

后续建议：

1. 页面工单号从金蝶生产订单列表中选择或校验。
2. 本地 `work_order_no` 只保存金蝶生产订单号。
3. 如果需要内部执行批次，可以另建 MES 执行单号，但不要替代金蝶工单号。

---

### 3.2 采购单号

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `purchase_no` |
| 当前使用表 | `material_batch.purchase_no`、`receive_record.purchase_no` |
| 可复用金蝶对象 | `PUR_PurchaseOrder` 采购订单 |
| 可复用金蝶字段 | 采购订单单号，通常对应 `FBillNo` |
| 是否建议新增金蝶字段 | 不建议新增 |

说明：

收货贴标时录入的采购单号，可以直接引用金蝶采购订单号。后续收货贴标页面应能根据采购单号带出供应商、物料、采购数量等数据。

---

### 3.3 物料编码

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `material_code` |
| 当前使用表 | `material_batch`、`material_package`、`receive_record`、`inventory_stock`、`pick_record`、`assembly_bind` |
| 可复用金蝶对象 | `BD_MATERIAL` 物料主数据 |
| 可复用金蝶字段 | 物料编码、物料名称、规格型号，如 `FNumber`、`FName`、`FSpecification` |
| 是否建议新增金蝶字段 | 不建议新增 |

说明：

物料编码是金蝶已有主数据，不应在 MES 追溯里重新定义。MES 本地保存金蝶物料编码作为关联键即可。

---

### 3.4 供应商编码

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `supplier_code` |
| 当前使用表 | `material_batch.supplier_code`、`receive_record.supplier_code`、`supplier_qr_map.supplier_code` |
| 可复用金蝶对象 | `BD_Supplier` 供应商主数据 |
| 可复用金蝶字段 | 供应商编码、供应商名称，如 `FNumber`、`FName` |
| 是否建议新增金蝶字段 | 不建议新增 |

说明：

供应商是金蝶已有主数据。MES 追溯只需要保存供应商编码或供应商 ID 的关联信息。

---

### 3.5 单位

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `unit` |
| 当前使用表 | `material_batch`、`material_package`、`receive_record`、`inventory_stock`、`stock_move`、`pcba_transform` |
| 可复用金蝶对象 | `BD_UNIT` 计量单位 |
| 是否建议新增金蝶字段 | 不建议新增 |

说明：

单位应使用金蝶计量单位。MES 本地可以保存单位编码或单位名称快照。

---

### 3.6 数量

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `qty`、`bind_qty` |
| 当前使用表 | `material_batch`、`material_package`、`receive_record`、`inventory_stock`、`stock_move`、`pick_record`、`assembly_bind` |
| 可复用金蝶字段 | 各业务单据分录数量字段 |
| 是否建议新增金蝶字段 | 不建议新增普通数量字段 |

说明：

数量本身金蝶已有，不需要新增。

注意：

`package_count` 不是普通业务数量，而是 MES 拆包/分箱数量。它不等同于采购数量、入库数量或领料数量，后续如果要写回金蝶，建议作为 MES 包装数量字段单独处理。

---

### 3.7 仓库 / 库位 / 线边位置

| 项目 | 说明 |
|---|---|
| MES 本地字段 | 当前主要是 `location_code`，后续可拆为 `stock_code` / `location_code` |
| 当前使用表 | `inventory_stock.location_code`、`stock_move.location_code` |
| 可复用金蝶对象 | `BD_STOCK` 仓库 |
| 是否建议新增金蝶字段 | 仓库不建议新增；库位视金蝶是否启用库位管理决定 |

说明：

仓库可以复用金蝶仓库主数据。如果现场还要管理货架、库位、线边位置，需要确认金蝶是否启用库位管理。

处理建议：

1. 仓库编码复用金蝶 `BD_STOCK`。
2. 线边位置、临时区域、工位位置可先保留在 MES 本地 `location_code`。
3. 后续如果金蝶已有库位对象，再映射到金蝶库位字段。

---

### 3.8 库存状态

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `status`、`from_status`、`to_status` |
| 当前使用表 | `inventory_stock.status`、`stock_move.from_status`、`stock_move.to_status` |
| 可复用金蝶对象 | `BD_STOCKSTATUS` 库存状态 |
| 是否建议新增金蝶字段 | 不建议新增标准库存状态字段，但 MES 内部状态仍需本地保留 |

说明：

金蝶有库存状态，但 MES 的执行状态不一定完全等于金蝶库存状态。

可映射示例：

| MES 状态 | 可映射金蝶含义 |
|---|---|
| `available` | 可用 |
| `rejected` | 不良、冻结或退货待处理，需按金蝶实际配置确认 |
| `pending_iqc` | 待检，需确认金蝶是否已有对应库存状态 |
| `picked` | 已领用，可能不对应库存状态，而是出库/领料结果 |

建议：

金蝶库存状态用于库存账，MES `status` 用于现场追溯状态，两者可以映射，但不要强行合并成一个字段。

---

### 3.9 人员：操作员、检验员、领料人

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `operator`、`inspector`、`picker` |
| 当前使用表 | `receive_record.operator`、`iqc_record.inspector`、`stock_move.operator`、`pick_record.operator`、`assembly_bind.operator` |
| 可复用金蝶对象 | `BD_Empinfo` 员工资料 |
| 是否建议新增金蝶字段 | 不建议新增人员主数据字段 |

说明：

人员主数据可以复用金蝶员工资料。MES 本地仍建议保存操作人快照，避免员工资料后续变更影响历史追溯。

---

### 3.10 产品型号 / 产成品物料

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `product_model`，当前主要在页面选择和追溯绑定中使用 |
| 可复用金蝶对象 | `BD_MATERIAL` 产成品物料，或生产订单上的产品物料 |
| 可复用字段 | 物料编码、物料名称、规格型号 |
| 是否建议新增金蝶字段 | 通常不建议新增 |

说明：

如果“产品型号”本质是金蝶里的产成品物料编码或规格型号，就应复用金蝶物料主数据。只有现场型号不是金蝶物料资料的一部分时，才考虑 MES 自定义字段。

---

### 3.11 产品 SN / 序列号

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `product_sn`、`serial_no` |
| 当前使用表 | `pick_record.product_sn`、`assembly_bind.product_sn`、`assembly_bind.serial_no`、`trace_event_log.product_sn` |
| 可复用金蝶对象 | `BD_SerialMainFile`、`QT_LotSNRelation` |
| 是否建议新增金蝶字段 | 如果金蝶已启用序列号，则不建议新增 SN 字段 |

说明：

产品 SN 可以尽量复用金蝶序列号体系。

但产品 SN 本身可以复用金蝶；产品 SN 绑定了哪些 ML 批次、PK 包装、物料序列号，这个“装配关系”不一定能完全用金蝶已有 SN 字段表达。

---

### 3.12 批号 / 批次

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `batch_code` |
| 当前使用表 | `material_batch.batch_code`、`material_package.batch_code`、`inventory_stock.batch_code`、`stock_move.batch_code`、`assembly_bind.batch_code` |
| 可复用金蝶对象 | 库存批号、批号调整、批序关系，具体字段需按真实 FormId 确认 |
| 相关已验证对象 | `STK_INVENTORY`、`STK_LOTADJUST`、`QT_LotSNRelation` |
| 是否建议新增金蝶字段 | 取决于 ML 是否定义为金蝶正式批号 |

关键决策：

如果 ML 批次码就是金蝶正式批号：

- `batch_code` 可以直接映射金蝶批号。
- 不需要新增 `F_MES_BatchCode`。

如果金蝶已有原始供应商批号，而 ML 只是 MES 内部追溯码：

- 金蝶批号继续保存原金蝶批号或供应商批号。
- `batch_code` 需要作为 MES 自定义字段保存。
- 建议字段名：`F_MES_BatchCode`。

---

## 4. 可复用金蝶对象，但 MES 本地仍需保留的字段

### 4.1 收货执行号

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `receive_no` |
| 当前使用表 | `receive_record.receive_no` |
| 可对应金蝶对象 | 采购收料单、采购入库单 |
| 当前状态 | 金蝶真实 FormId 待确认 |
| 是否建议本地保留 | 建议保留 |

说明：

MES 的 `receive_no` 是现场收货贴标动作编号，不一定等于金蝶采购入库单号。

---

### 4.2 库存移动号

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `move_no` |
| 当前使用表 | `stock_move.move_no` |
| 可对应金蝶对象 | 采购入库单、生产领料单、库存调拨单、其他出入库单 |
| 是否建议本地保留 | 建议保留 |

说明：

MES 的库存移动号用于记录扫码动作，如入库确认、配料扫码、状态变化等。它可以关联金蝶正式单据，但不建议完全替代金蝶单据号。

---

### 4.3 检验报告号

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `report_no` |
| 当前使用表 | `iqc_record.report_no`、`test_record.report_no` |
| 可对应金蝶对象 | IQC/QMS 检验单或检验报告，真实 FormId 待确认 |
| 是否建议本地保留 | 建议保留 |

说明：

如果金蝶质量模块已启用，则报告号可映射金蝶检验单或报告号。当前金蝶 IQC/QMS 对象还未完全确认，所以本地先保留。

---

## 5. 不建议直接共用金蝶字段、应作为 MES 追溯专用字段的数据

### 5.1 PK 包装码

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `package_code` |
| 当前使用表 | `material_package`、`material_qrcode`、`label_print_task`、`inventory_stock`、`stock_move`、`pick_record`、`assembly_bind` |
| 是否可直接复用金蝶字段 | 通常不建议 |
| 建议处理 | MES 本地保留；如需写回金蝶，新增自定义字段或独立包装关系对象 |

原因：

金蝶批号解决的是批次，不一定解决每箱、每包、每个包装单元的追溯码。

建议金蝶字段：

`F_MES_PackageCode`

---

### 5.2 包装序号和包装数量

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `package_index`、`package_count` |
| 当前使用表 | `material_package.package_index`、`material_batch.package_count`、`receive_record.package_count` |
| 是否可直接复用金蝶字段 | 不建议直接复用普通数量字段 |
| 建议处理 | MES 本地保留；如需金蝶展示，新增自定义字段 |

说明：

`package_count` 表示本次收货拆成几包/几箱，不等同于采购数量或库存数量。

---

### 5.3 二维码 payload

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `qr_payload_json` |
| 当前使用表 | `material_package`、`material_qrcode`、`label_print_task` |
| 是否可直接复用金蝶字段 | 不建议 |
| 建议处理 | 本地保存为主；金蝶只存二维码字符串、追溯码或追溯链接 |

建议金蝶字段：

`F_MES_QrPayload`

如果 payload 很长，不建议直接写入金蝶字段，建议只写追溯码或追溯 URL。

---

### 5.4 供应商原始二维码

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `supplier_qr_raw` |
| 当前使用表 | `material_batch.supplier_qr_raw`、`supplier_qr_map.supplier_qr_raw` |
| 是否可直接复用金蝶字段 | 通常不建议 |
| 建议处理 | MES 本地保留；如需金蝶查看，新增自定义字段 |

建议金蝶字段：

`F_MES_SupplierQrRaw`

---

### 5.5 打印任务与打印状态

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `task_no`、`print_status`、`printer_type`、`status` |
| 当前使用表 | `material_qrcode`、`label_print_task` |
| 是否可直接复用金蝶字段 | 不建议 |
| 建议处理 | MES 本地保留 |

说明：

打印任务属于 MES 执行层，不是金蝶业务单据字段。当前也尚未直连斑马打印机，只是生成二维码数据和打印任务，并一键带入斑马物料标签页面。

---

### 5.6 IQC 附件内容

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `attachment_id`、`filename`、`content_type`、`size`、`content_base64`、`attachments_json` |
| 当前使用表 | `iqc_attachment`、`iqc_record` |
| 是否可直接复用金蝶字段 | 不建议直接把附件内容写入普通字段 |
| 建议处理 | 本地保存内容；金蝶只保存附件关系、附件 ID 或附件链接 |

说明：

`content_base64` 不建议写入金蝶普通字段。后续如果金蝶有附件服务，应走金蝶附件机制；如果没有，则金蝶只保存 MES 附件 ID 或链接。

建议金蝶字段：

`F_MES_IqcAttachmentJson` 或 `F_MES_IqcAttachmentIds`

---

### 5.7 装配绑定关系

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `bind_no`、`product_sn`、`material_code`、`batch_code`、`package_code`、`serial_no`、`bind_qty`、`position_code` |
| 当前使用表 | `assembly_bind` |
| 是否可直接复用金蝶字段 | 部分可复用，整体关系不建议硬套 |
| 建议处理 | MES 本地追溯关系表保留；必要时同步到金蝶自定义关系对象 |

说明：

产品 SN 可以复用金蝶序列号，物料编码可以复用金蝶物料，批号可以复用金蝶批号。

但是“这个产品 SN 装配时用了哪个 ML 批次、哪个 PK 包装、哪个物料序列号、哪个位置”这一整条关系，是 MES 追溯关系，不能简单靠一个金蝶字段表达。

---

### 5.8 追溯事件日志

| 项目 | 说明 |
|---|---|
| MES 本地字段 | `event_type`、`ref_code`、`batch_code`、`package_code`、`product_sn`、`payload_json` |
| 当前使用表 | `trace_event_log` |
| 是否可直接复用金蝶字段 | 不建议 |
| 建议处理 | MES 本地保留 |

说明：

追溯事件日志记录的是现场扫码和状态流转过程，例如收货贴标、IQC、入库、配料、装配绑定。金蝶一般只需要最终业务单据结果，不一定需要保存每一条扫码事件。

---

## 6. 推荐字段映射总表

| MES 字段 | 含义 | 建议复用金蝶对象/字段 | 是否需要新增金蝶字段 | 备注 |
|---|---|---|---|---|
| `work_order_no` | 工单号 | `PRD_MO.FBillNo` | 否 | 金蝶已有工单/生产订单号 |
| `purchase_no` | 采购单号 | `PUR_PurchaseOrder.FBillNo` | 否 | 金蝶已有采购订单号 |
| `material_code` | 物料编码 | `BD_MATERIAL.FNumber` | 否 | 金蝶已有物料主数据 |
| `supplier_code` | 供应商编码 | `BD_Supplier.FNumber` | 否 | 金蝶已有供应商主数据 |
| `unit` | 单位 | `BD_UNIT` | 否 | 金蝶已有计量单位 |
| `qty` | 数量 | 对应单据分录数量字段 | 否 | 普通数量不新增 |
| `operator` | 操作员 | `BD_Empinfo` | 否 | 本地保留快照 |
| `inspector` | 检验员 | `BD_Empinfo` | 否 | 本地保留快照 |
| `picker` / `operator` | 领料人 | `BD_Empinfo` | 否 | 本地保留快照 |
| `location_code` | 仓库/库位/线边位置 | `BD_STOCK`，库位对象待确认 | 视情况 | 仓库可复用，线边位置可能本地保留 |
| `status` | MES 库存状态 | `BD_STOCKSTATUS` 部分映射 | 视情况 | MES 状态不一定等于金蝶库存状态 |
| `product_model` | 产品型号 | `BD_MATERIAL.FNumber/FSpecification` | 通常否 | 优先复用产成品物料 |
| `product_sn` | 产品 SN | `BD_SerialMainFile`、`QT_LotSNRelation` | 通常否 | 若金蝶启用序列号 |
| `batch_code` | ML 批次码 | 金蝶批号字段 | 视 ML 定义 | 如果 ML 是正式批号，则不新增 |
| `receive_no` | MES 收货执行号 | 采购收料/采购入库单号待确认 | 视情况 | 本地建议保留 |
| `move_no` | MES 库存移动号 | 入库/领料/调拨单据号 | 视情况 | 本地建议保留 |
| `report_no` | 检验报告号 | IQC/QMS 对象待确认 | 视情况 | 质量对象未确认前本地保留 |
| `package_code` | PK 包装码 | 无稳定标准字段 | 是 | 建议 `F_MES_PackageCode` |
| `package_index` | 包装序号 | 无稳定标准字段 | 是 | 建议 MES 自定义 |
| `package_count` | 包装数量/箱数 | 不等同普通数量 | 是或本地保留 | 不建议映射普通数量 |
| `qr_payload_json` | 二维码 JSON | 无 | 是或本地保留 | 建议只写追溯码/链接到金蝶 |
| `supplier_qr_raw` | 供应商原始二维码 | 无 | 是 | 建议 `F_MES_SupplierQrRaw` |
| `print_status` | 打印状态 | 无 | 否 | MES 本地保留 |
| `task_no` | 打印任务号 | 无 | 否 | MES 本地保留 |
| `attachment_id` | 附件 ID | 金蝶附件机制待确认 | 视情况 | 金蝶可保存附件 ID/链接 |
| `content_base64` | 附件内容 | 不建议 | 否 | 不写金蝶普通字段 |
| `bind_no` | 装配绑定号 | 无稳定标准字段 | 是或本地保留 | 建议 MES 关系表 |
| `position_code` | 装配位置 | BOM 用量位置可参考，实际需确认 | 视情况 | 可与 BOM 位置做关联 |
| `event_type` | 追溯事件类型 | 无 | 否 | MES 本地事件日志 |
| `payload_json` | 原始执行 payload | 无 | 否 | MES 本地审计用 |

---

## 7. 建议第一阶段不要新增的字段

以下字段金蝶已有，第一阶段不要新增：

1. 工单号：复用 `PRD_MO`。
2. 采购单号：复用 `PUR_PurchaseOrder`。
3. 物料编码：复用 `BD_MATERIAL`。
4. 供应商：复用 `BD_Supplier`。
5. 单位：复用 `BD_UNIT`。
6. 仓库：复用 `BD_STOCK`。
7. 员工/检验员/操作员：复用 `BD_Empinfo`。
8. 普通数量：复用各单据分录数量字段。
9. 产品 SN：优先复用金蝶序列号体系。
10. 产品型号：优先复用产成品物料编码和规格型号。

---

## 8. 建议第一阶段新增或本地保留的字段

如果要从本地闭环推进到金蝶正式写回，建议优先处理以下 MES 追溯字段：

| 建议字段 | 来源字段 | 用途 | 建议方式 |
|---|---|---|---|
| `F_MES_BatchCode` | `batch_code` | MES 内部 ML 批次码 | 如果 ML 不等于金蝶正式批号，则新增 |
| `F_MES_PackageCode` | `package_code` | PK 包装码 | 建议新增或建包装关系对象 |
| `F_MES_PackageIndex` | `package_index` | 包装序号 | 建议新增或本地保留 |
| `F_MES_QrPayload` | `qr_payload_json` | 二维码 payload | 不建议存太长；可存追溯链接 |
| `F_MES_SupplierQrRaw` | `supplier_qr_raw` | 供应商原始二维码 | 建议新增或本地保留 |
| `F_MES_IqcAttachmentJson` | `attachments_json` | IQC 附件关系 | 建议保存附件 ID/链接，不保存 base64 |
| `F_MES_TraceEventId` | `trace_event_log.id` | MES 追溯事件关联 | 可选 |
| `F_MES_AssemblyBindJson` | `assembly_bind` | 产品 SN 与物料批次/包装绑定关系 | 更建议独立关系对象 |

---

## 9. ML 批次码的关键选择

后续写回金蝶前，必须确认：

`ML 批次码是否作为金蝶正式批号？`

### 方案 A：ML 就是金蝶正式批号

优点：

1. 字段少。
2. 金蝶库存批号、批号追溯可以直接利用。
3. `batch_code` 可直接映射金蝶批号。

缺点：

1. 如果供应商已有批号，可能会和 ML 内部码冲突。
2. 需要明确供应商批号保存在哪里。

适合场景：

MES 全面接管批次编码，金蝶批号也使用 MES 生成的 ML。

### 方案 B：ML 是 MES 内部追溯批次码，金蝶批号仍保存原批号

优点：

1. 不破坏金蝶原有批号体系。
2. 供应商批号、金蝶批号、MES 批次码可以并存。

缺点：

1. 需要新增 `F_MES_BatchCode`。
2. 后续查询需要同时处理金蝶批号和 MES 批次码。

适合场景：

供应商批号、金蝶批号已经在现场稳定使用，不希望被 ML 替换。

当前建议：

先采用方案 B 的保守设计：

- 本地保留 `batch_code`。
- 金蝶批号字段暂不强行覆盖。
- 等确认现场批号规则后，再决定是否把 ML 映射为正式金蝶批号。

---

## 10. 结论

物料追溯执行中，可以共用金蝶已有数据库字段的数据主要是：

1. 工单号：共用金蝶生产订单 `PRD_MO`。
2. 采购单号：共用金蝶采购订单 `PUR_PurchaseOrder`。
3. 物料编码：共用金蝶物料主数据 `BD_MATERIAL`。
4. 供应商：共用金蝶供应商 `BD_Supplier`。
5. 单位：共用金蝶计量单位 `BD_UNIT`。
6. 仓库：共用金蝶仓库 `BD_STOCK`。
7. 库存状态：部分共用金蝶库存状态 `BD_STOCKSTATUS`。
8. 人员：共用金蝶员工资料 `BD_Empinfo`。
9. 产品型号：优先共用产成品物料编码和规格型号。
10. 产品 SN：优先共用金蝶序列号体系。
11. 数量：共用各业务单据分录数量字段。
12. 批号：如果 ML 被定义为正式批号，可以共用金蝶批号字段。

不建议直接共用金蝶已有字段、应作为 MES 追溯专用字段的数据主要是：

1. PK 包装码。
2. 包装序号和包装数量。
3. 二维码 payload。
4. 供应商原始二维码。
5. 打印任务和打印状态。
6. IQC 附件内容。
7. 产品 SN 与物料 ML/PK 的装配绑定关系。
8. 追溯事件日志。

第一阶段建议：

先复用金蝶已有主数据和单据字段，把新增字段控制在 MES 追溯必须的最小集合：

1. `F_MES_BatchCode`，仅当 ML 不等于金蝶正式批号时需要。
2. `F_MES_PackageCode`。
3. `F_MES_QrPayload` 或追溯链接。
4. `F_MES_SupplierQrRaw`。
5. `F_MES_IqcAttachmentJson`。
6. `F_MES_TraceEventId`。

这样可以避免重复造字段，也能保证物料追溯执行闭环后续能平滑写回金蝶。
