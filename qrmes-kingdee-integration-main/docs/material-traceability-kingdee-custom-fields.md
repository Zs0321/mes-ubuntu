# 物料追溯执行：金蝶侧建议新增字段与是否新建表说明

## 1. 结论

当前不建议直接在金蝶数据库里手工新建物理表。

金蝶侧正确做法是：

1. 优先复用金蝶已有主数据和单据字段。
2. 必须补充的追溯信息，通过 BOS 在现有业务对象上新增自定义字段。
3. 只有“产品 SN ↔ 物料批次/包装码/序列件”的多对多装配追溯关系，才考虑新建一个金蝶自定义业务对象；否则先保留在 MES 本地追溯库。
4. 附件内容不建议写入金蝶普通字段，金蝶只保存附件 ID、附件链接或附件关系。

本地 MES 追溯库已经有完整表：

`/volume2/MES/QRMES/kingdee_sync.db`

金蝶正式库不要直接手工建表，避免破坏金蝶升级、权限、BOS 元数据和 WebAPI。

---

## 2. 第一阶段建议新增字段总表

| 建议字段编码 | 字段名称 | 类型建议 | 加在哪类金蝶对象 | 是否必须 | 说明 |
|---|---|---|---|---|---|
| `F_MES_BatchCode` | MES批次码 | 文本，100-200 | 收货/入库/库存批号相关对象 | 视情况 | 如果 ML 不作为金蝶正式批号，则必须新增；如果 ML 就是金蝶批号，可不加 |
| `F_MES_PackageCode` | MES包装码 | 文本，100-200 | 收货/入库/领料/序列号或批号关系对象 | 必须 | 保存 PK 包装码 |
| `F_MES_QrCode` | MES二维码内容 | 长文本 | 收货/入库/标签相关对象 | 可选 | 保存二维码字符串或追溯 URL，不建议保存过长 JSON |
| `F_MES_SupplierQrRaw` | 供应商原始二维码 | 长文本 | 收货/检验/批次相关对象 | 建议 | 保存供应商原始二维码内容 |
| `F_MES_TraceId` | MES追溯ID | 文本，100 | 需要写回的关键单据 | 建议 | 关联 MES 本地 `trace_event_log` 或追溯主记录 |
| `F_MES_PrintStatus` | 标签打印状态 | 文本，50 | 标签/收货相关对象 | 可选 | 如果金蝶需要查看打印状态才加，否则留 MES 本地 |
| `F_MES_IqcReportNo` | MES检验报告号 | 文本，100 | IQC/QMS 或采购检验相关对象 | 视情况 | 如果金蝶已有检验报告号字段，则不新增 |
| `F_MES_IqcAttachmentIds` | MES检验附件ID | 长文本 | IQC/QMS 或采购检验相关对象 | 建议 | 保存附件 ID/链接，不保存 base64 |
| `F_MES_AssemblyBindId` | MES装配绑定ID | 文本，100 | 产品序列号/生产汇报/追溯关系对象 | 可选 | 如果装配关系保留在 MES，只需保存关联 ID |

---

## 3. 字段按业务对象分配建议

### 3.1 采购收货 / 收料对象

待确认真实 FormId：

- `PUR_ReceiveBill` 或现场实际采购收料对象
- 如果现场没有收料单，也可能直接落采购入库单

建议新增字段：

| 字段编码 | 字段名称 | 必要性 | 对应 MES 字段 |
|---|---|---|---|
| `F_MES_BatchCode` | MES批次码 | 视 ML 是否等于金蝶批号 | `material_batch.batch_code` |
| `F_MES_PackageCode` | MES包装码 | 必须 | `material_package.package_code` |
| `F_MES_SupplierQrRaw` | 供应商原始二维码 | 建议 | `supplier_qr_raw` |
| `F_MES_QrCode` | MES二维码内容/追溯链接 | 可选 | `qr_payload_json` 或追溯 URL |
| `F_MES_TraceId` | MES追溯ID | 建议 | `trace_event_log.id` |

可直接复用金蝶字段：

| MES 字段 | 复用金蝶字段 |
|---|---|
| `purchase_no` | 采购订单号 |
| `material_code` | 物料编码 |
| `supplier_code` | 供应商 |
| `qty` | 收货数量 |
| `unit` | 单位 |
| `operator` | 员工/制单人/操作人，视金蝶对象字段而定 |

---

### 3.2 采购入库对象

待确认真实 FormId：

- `STK_InStock`
- 或现场使用的采购入库单对象

建议新增字段：

| 字段编码 | 字段名称 | 必要性 | 对应 MES 字段 |
|---|---|---|---|
| `F_MES_BatchCode` | MES批次码 | 视情况 | `batch_code` |
| `F_MES_PackageCode` | MES包装码 | 必须 | `package_code` |
| `F_MES_TraceId` | MES追溯ID | 建议 | `trace_event_log.id` |
| `F_MES_QrCode` | MES二维码内容/追溯链接 | 可选 | `qr_payload_json` 或追溯 URL |

可直接复用金蝶字段：

| MES 字段 | 复用金蝶字段 |
|---|---|
| `material_code` | 物料编码 |
| `qty` | 入库数量 |
| `unit` | 单位 |
| `warehouse` / `location_code` | 仓库/库位，按金蝶配置确认 |
| `stock_status` | 库存状态，按金蝶配置确认 |

---

### 3.3 IQC / QMS 检验对象

待确认真实 FormId：

- IQC/QMS 质量检验对象还需要从现场金蝶确认

建议新增字段：

| 字段编码 | 字段名称 | 必要性 | 对应 MES 字段 |
|---|---|---|---|
| `F_MES_BatchCode` | MES批次码 | 视情况 | `iqc_record.batch_code` |
| `F_MES_PackageCode` | MES包装码 | 可选 | 如果检验按包装码记录则写入 |
| `F_MES_IqcReportNo` | MES检验报告号 | 视金蝶是否已有报告号字段 | `iqc_record.report_no` |
| `F_MES_IqcAttachmentIds` | MES检验附件ID | 建议 | `iqc_attachment.attachment_id` |
| `F_MES_TraceId` | MES追溯ID | 建议 | `trace_event_log.id` |

不建议写入金蝶普通字段：

| MES 字段 | 原因 |
|---|---|
| `content_base64` | 附件内容太大，不适合普通字段 |
| 完整 `attachments_json` 大对象 | 可保存 ID/链接，不建议保存完整 base64 |

可直接复用金蝶字段：

| MES 字段 | 复用金蝶字段 |
|---|---|
| `inspector` | 员工资料 |
| `result` | 检验结果，需映射金蝶质量结果枚举 |
| `report_no` | 如果金蝶已有检验报告号字段，则直接复用 |

---

### 3.4 生产领料 / 用料对象

可能相关对象：

- `PRD_MO` 生产订单
- `PRD_PPBOM` 生产用料清单
- 生产领料单真实 FormId 待确认

建议新增字段：

| 字段编码 | 字段名称 | 必要性 | 对应 MES 字段 |
|---|---|---|---|
| `F_MES_BatchCode` | MES批次码 | 视情况 | `pick_record.batch_code` |
| `F_MES_PackageCode` | MES包装码 | 必须 | `pick_record.package_code` |
| `F_MES_TraceId` | MES追溯ID | 建议 | `trace_event_log.id` |

可直接复用金蝶字段：

| MES 字段 | 复用金蝶字段 |
|---|---|
| `work_order_no` | `PRD_MO` 生产订单号/工单号 |
| `material_code` | 用料物料编码 |
| `qty` | 领料数量 |
| `unit` | 单位 |
| `operator` / `picker` | 员工资料 |

说明：

金蝶有工单号，所以 `work_order_no` 不要新增字段，直接引用 `PRD_MO`。

---

### 3.5 产品 SN / 序列号 / 批序关系对象

已验证或相关对象：

- `BD_SerialMainFile`
- `QT_LotSNRelation`

建议新增字段：

| 字段编码 | 字段名称 | 必要性 | 对应 MES 字段 |
|---|---|---|---|
| `F_MES_BatchCode` | MES批次码 | 视情况 | `assembly_bind.batch_code` |
| `F_MES_PackageCode` | MES包装码 | 建议 | `assembly_bind.package_code` |
| `F_MES_AssemblyBindId` | MES装配绑定ID | 建议 | `assembly_bind.bind_no` 或 `assembly_bind.id` |
| `F_MES_TraceId` | MES追溯ID | 建议 | `trace_event_log.id` |

可直接复用金蝶字段：

| MES 字段 | 复用金蝶字段 |
|---|---|
| `product_sn` | 金蝶序列号 |
| `serial_no` | 金蝶序列号或组件序列号 |
| `material_code` | 金蝶物料编码 |
| `batch_code` | 如果 ML 是金蝶正式批号，可复用批号 |

说明：

产品 SN 本身可以共用金蝶序列号体系；但“产品 SN 用了哪个物料 ML/PK”的装配关系，金蝶标准字段未必能完整表达。

---

## 4. 是否需要新建表 / 新建对象

### 4.1 不建议手工新建金蝶物理表

不建议直接在金蝶数据库里执行 SQL 建表。

原因：

1. 金蝶对象由 BOS 元数据管理，手工建表不等于金蝶业务对象。
2. 手工表无法自然进入金蝶权限、单据、WebAPI、审计和升级体系。
3. 后续版本升级或服务补丁可能出现兼容问题。

正确方式：

- 用 BOS 新增自定义字段。
- 或用 BOS 新建自定义业务对象/基础资料对象。
- MES 本地继续用 SQLite 保存追溯明细。

---

### 4.2 第一阶段不建议在金蝶新建表

第一阶段建议只加少量自定义字段，不新建金蝶自定义表。

原因：

1. 当前 MES 本地追溯库已经能保存完整闭环。
2. 金蝶侧先承载关键追溯码和关联 ID 即可。
3. 减少金蝶改造范围，降低上线风险。

第一阶段建议：

- 收货/入库/领料/IQC 对象上增加必要字段。
- MES 本地继续保存完整 `material_batch`、`material_package`、`assembly_bind`、`trace_event_log`。
- 金蝶只保存关键码和关联 ID。

---

### 4.3 什么情况下需要新建金蝶自定义对象

如果后续要求“在金蝶里也能完整查询产品 SN 到所有物料批次/包装码的多级追溯链”，则建议新建金蝶自定义业务对象。

建议对象：

| 建议对象编码 | 对象名称 | 用途 |
|---|---|---|
| `MES_TraceBind` | MES装配追溯绑定关系 | 保存产品 SN 与物料 ML/PK/组件序列号的多对多关系 |
| `MES_LabelPrintTask` | MES标签打印任务 | 如要求金蝶直接管理打印队列，可建；否则不建议 |
| `MES_TraceEvent` | MES追溯事件日志 | 如要求金蝶完整保存扫码事件，可建；否则不建议 |

第一优先级：

`MES_TraceBind`

原因：

装配追溯绑定是最难塞进现有金蝶字段的多对多关系。

---

## 5. 推荐方案

### 5.1 最小上线方案

不新建金蝶自定义表，只新增少量字段。

必加或建议加：

1. `F_MES_PackageCode`
2. `F_MES_TraceId`
3. `F_MES_SupplierQrRaw`
4. `F_MES_IqcAttachmentIds`
5. `F_MES_QrCode`，可选
6. `F_MES_BatchCode`，仅当 ML 不等于金蝶正式批号时加

优点：

- 改造小。
- 风险低。
- 可以先把金蝶关键单据和 MES 追溯库打通。

缺点：

- 金蝶内只能看到关键追溯码。
- 完整追溯链仍以 MES 本地查询为主。

---

### 5.2 完整追溯方案

在最小字段基础上，新建一个金蝶自定义对象：

`MES_TraceBind`：MES装配追溯绑定关系

建议字段：

| 字段编码 | 字段名称 | 类型 |
|---|---|---|
| `F_MES_ProductSn` | 产品SN | 文本 |
| `F_MES_ProductMaterial` | 产品物料编码 | 基础资料/文本 |
| `F_MES_WorkOrderNo` | 工单号 | 文本，关联 `PRD_MO` |
| `F_MES_ComponentMaterial` | 组件物料编码 | 基础资料/文本 |
| `F_MES_BatchCode` | MES批次码 | 文本 |
| `F_MES_PackageCode` | MES包装码 | 文本 |
| `F_MES_ComponentSn` | 组件序列号 | 文本 |
| `F_MES_BindQty` | 绑定数量 | 数量 |
| `F_MES_PositionCode` | 装配位置 | 文本 |
| `F_MES_BindNo` | MES绑定单号 | 文本 |
| `F_MES_BindTime` | 绑定时间 | 日期时间 |
| `F_MES_Operator` | 操作员 | 员工/文本 |
| `F_MES_SourcePayload` | MES原始数据 | 长文本 |

优点：

- 金蝶里也能保存完整产品 SN 用料追溯关系。
- 方便金蝶侧报表或审计。

缺点：

- BOS 改造范围更大。
- WebAPI 写回和权限配置更复杂。
- 需要明确对象生命周期、单据编号、审核策略。

---

## 6. 推荐当前决策

当前建议采用“两阶段”：

### 阶段一：不新建金蝶表，只加关键字段

加字段：

1. `F_MES_PackageCode`
2. `F_MES_TraceId`
3. `F_MES_SupplierQrRaw`
4. `F_MES_IqcAttachmentIds`
5. `F_MES_QrCode`
6. `F_MES_BatchCode`，视 ML 是否等于金蝶批号决定

不加字段：

1. 工单号，不加，复用 `PRD_MO`。
2. 采购单号，不加，复用采购订单。
3. 物料编码，不加，复用 `BD_MATERIAL`。
4. 供应商，不加，复用 `BD_Supplier`。
5. 数量，不加，复用单据分录数量。
6. 单位，不加，复用 `BD_UNIT`。
7. 员工，不加，复用 `BD_Empinfo`。

### 阶段二：如需金蝶完整查询追溯链，再建自定义对象

优先只建一个：

`MES_TraceBind`：MES装配追溯绑定关系

暂不建议新建：

1. `MES_LabelPrintTask`
2. `MES_TraceEvent`
3. `MES_IqcAttachment`

这些先保留在 MES 本地库更合适。

---

## 7. 最终回答

现在金蝶具体要加的字段，建议先控制在：

1. `F_MES_PackageCode`：MES包装码 / PK码。
2. `F_MES_TraceId`：MES追溯ID。
3. `F_MES_SupplierQrRaw`：供应商原始二维码。
4. `F_MES_IqcAttachmentIds`：IQC附件ID或附件链接。
5. `F_MES_QrCode`：MES二维码内容或追溯链接。
6. `F_MES_BatchCode`：MES批次码；仅当 ML 不作为金蝶正式批号时新增。

现在不建议直接新建金蝶数据库物理表。

如果后续要求金蝶也完整保存“产品 SN 用了哪些物料批次/包装码”的多级装配追溯链，再通过 BOS 新建一个自定义业务对象：

`MES_TraceBind`：MES装配追溯绑定关系。

第一阶段以“现有金蝶对象加少量自定义字段 + MES 本地追溯库保存完整明细”为最稳。
