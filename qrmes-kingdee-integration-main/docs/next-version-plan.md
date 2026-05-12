# 下一版本推进计划

## 当前已完成

- 金蝶同步中台已常驻目标服务：`http://172.16.30.10:9010`。
- 已完成通用能力：`LoginBySign`、`ExecuteBillQuery`、`View`、`Save`。
- 已打通核心业务数据集：物料、BOM、采购订单、生产订单、生产用料清单、生产入库、工序计划、工序汇报、工艺路线、仓库、批次追溯基础层、序列号主档、批号序列号关系。
- 已提供序列号追溯本地桥接接口：`GET /api/local-db/trace/serial?serial_no=...&material_code=...`。
- 本版本新增低风险基础主数据拉取落库：供应商、客户、部门、员工、计量单位、组织、物料分类、库存状态。

## 本版本已落地的新增 dataset

| dataset | 金蝶对象 | 拉取接口 |
| --- | --- | --- |
| supplier | BD_Supplier | POST /api/sync/suppliers/pull |
| customer | BD_Customer | POST /api/sync/customers/pull |
| department | BD_Department | POST /api/sync/departments/pull |
| employee | BD_Empinfo | POST /api/sync/employees/pull |
| unit | BD_UNIT | POST /api/sync/units/pull |
| organization | ORG_Organizations | POST /api/sync/organizations/pull |
| material_category | BD_MATERIALCATEGORY | POST /api/sync/material-categories/pull |
| stock_status | BD_STOCKSTATUS | POST /api/sync/stock-statuses/pull |

字段口径先保持保守：`FID,FNumber,FName,FDocumentStatus,FCreateDate,FModifyDate`。后续真实业务需要更细字段时，再按单对象逐项补充字段和测试，避免一次性猜测过多字段导致 WebAPI 报错。

## 下一轮优先级

1. 远端 9010 部署并逐个真实 pull 新增基础主数据，记录每个 dataset 的真实返回条数和样例。
2. 若某个基础资料对象字段不存在，按对象单独调整字段清单，保留 pytest 覆盖。
3. 给 `/api/local-db/<dataset>` 增加分页、keyword 过滤和 dataset 白名单，避免数据变大后一次性返回过多。
4. 继续完善本地追溯树：基于 `serial_master + lot_serial_relation + production_instock + operation_report` 拼更完整的序列号生产链路。
5. 通用 WebAPI 后续再补：`Submit`、`Audit`、`UnAudit`、`Delete`、`Push`、`BatchSave`，但必须先确认具体业务对象需要，避免开放高风险写操作。

## 暂缓 / 不做

- 暂不切 `qrmes-web-core` 调中台本地 API；中台未完全打通前不触碰 8891。
- 暂不硬做 `DJCPJGGCZS` 单件产品加工过程追溯；当前账套命中 `BOS_FreeTrailForModel`，属于模块试用/授权门槛。
- 暂不把 `QT_TraceShow / QT_TraceFilter` 当普通 `ExecuteBillQuery` dataset；它们是页面运行态对象，继续走本地桥接和浏览器 XHR 反查路线。

## 验证命令

本地验证：

```bash
cd /Volumes/172.16.30.10/volume2/mes_ubuntu_split_result/qrmes-kingdee-integration
python3 -m pytest -q
```

远端部署验证建议：

```bash
ssh -p 9909 aiyan@172.16.30.10 "cd /volume2/mes_ubuntu_split_result/qrmes-kingdee-integration && QRMES_KINGDEE_RUNTIME_DIR=/volume2/MES/QRMES/kingdee_sync_runtime ./deploy.sh"
curl -s http://172.16.30.10:9010/health
curl -s -X POST 'http://172.16.30.10:9010/api/sync/suppliers/pull?limit=20'
curl -s 'http://172.16.30.10:9010/api/local-db/supplier'
```
