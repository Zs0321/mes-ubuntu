# 物料追溯执行专项 Spec

## 背景

物料追溯执行用于把采购来料、收货贴标、来料检、入库、生产领料、装配绑定和追溯查询串成一条本地可查的链路。当前阶段优先在 `qrmes-kingdee-integration` 的本地 SQLite 中台跑通闭环，暂不对未确认的金蝶对象强写回。

## 当前边界

- 金蝶中台服务：`http://172.16.30.10:9010`
- Web 验证页面：`http://172.16.30.10:8899/material-trace`
- 本地数据库：`/volume2/MES/QRMES/kingdee_sync.db`
- 当前打印状态：未直连斑马打印机。页面只生成二维码 payload、二维码预览和 `label_print_task`，需要人工复制到斑马物料标签打印页确认打印。
- 当前不切换 8891 正式服务，不把 web-core 正式链路强依赖到未完全确认的金蝶写回。

## 页面模块

页面必须是卡片式工作台，不做“从上到下”的线性长流程。四个模块并列展示，各模块按业务角色进入。

### 模块一：来料收货与标签

目标：
- 仓库收货时生成内部追溯身份。
- 生成 ML 批次码、PK 包装码、二维码 payload 和待打印任务。

输入：
- 采购单号
- 物料编码
- 供应商编码
- 收货日期
- 数量、单位、包装数
- 操作员
- 供应商原始二维码，可选

输出/落库：
- `material_batch`
- `material_package`
- `receive_record`
- `inventory_stock`，初始状态 `pending_iqc`
- `material_qrcode`
- `label_print_task`，状态 `pending`
- `trace_event_log`

接口：
- `POST /api/traceability/receive-label`

### 模块二：质量检验与入库

目标：
- 质量人员按 ML 批次码绑定 IQC 结果。
- 仓库按 PK 包装码确认入库仓位与数量。

输入：
- 批次码
- IQC 结论：合格、让步接收、不合格
- 报告号、检验员、备注
- 包装码或批次码、仓位、入库数量、操作员

输出/落库：
- `iqc_record`
- 更新 `material_batch`、`material_package`、`inventory_stock` 状态
- `stock_move`
- `trace_event_log`

接口：
- `POST /api/traceability/iqc`
- `POST /api/traceability/putaway`

规则：
- 不合格批次不能继续正常入库和配料。
- 合格或让步接收后才可放行到可用库存。

### 模块三：生产领料与装配

目标：
- 生产现场扫码领料。
- 建立产品 SN 与物料批次、包装码、单件序列号的关系。

输入：
- 工单号
- 产品 SN
- 物料编码
- ML 批次码或 PK 包装码
- 数量
- 安装位置
- 操作员

输出/落库：
- `pick_record`
- `stock_move`
- `assembly_bind`
- `trace_event_log`

接口：
- `POST /api/traceability/pick`
- `POST /api/traceability/assembly-bind`

### 模块四：追溯查询与打印任务

目标：
- 按 ML、PK 或产品 SN 查询正反向追溯链。
- 查看金蝶 FormId 计划。
- 明确当前打印任务状态。

输入：
- ML 批次码
- PK 包装码
- 产品 SN

输出/读取：
- 批次、包装、IQC、库存移动、配料、装配绑定链路
- `material_qrcode`
- `label_print_task`
- FormId 计划

接口：
- `GET /api/traceability/trace/<code>`
- `GET /api/traceability/formid-plan`

## 编码规则

批次码：

```text
ML|{物料编码}|{供应商编码}|{到货日期YYYYMMDD}|{4位流水号}
```

包装码：

```text
PK|{批次码}|{2位包装序号}
```

单件序列号：

```text
SN|{物料编码}|{日期YYYYMMDD}|{6位流水号}
```

## 当前已实现接口

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

## 金蝶写回计划

第一阶段：
- 只写本地 SQLite，完成扫码、编码、二维码打印数据和追溯查询闭环。

第二阶段：
- 确认 `PUR_ReceiveBill` 和 `STK_InStock` 字段后，将收货和入库结果进入 change queue，由中台统一写回。

第三阶段：
- 确认 IQC 质量对象真实 FormId 后，将 `iqc_record` 绑定到金蝶检验单或检验报告。

第四阶段：
- 若二维码需要永久留在金蝶，新增自定义字段：内部批次码、包装码、二维码 JSON、供应商原始二维码、MES 追溯事件 ID。

## 验收标准

- 页面四个模块以卡片工作台形式呈现，不使用纵向步骤条作为主结构。
- 收货贴标可生成 ML、PK、二维码 payload，并写入本地 SQLite。
- 来料检、入库、配料、装配均可写入对应本地表。
- 按 ML、PK、产品 SN 可查询追溯链。
- 页面清楚说明当前打印未直连斑马打印机。
- 未确认的金蝶对象不做强写回，只在 FormId 计划中列为待确认项。
