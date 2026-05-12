# 接口完成勾选清单

说明：实现后在对应项打勾，并补充实现文件、测试文件、验证方式。

## 通用 WebAPI
- [x] LoginBySign 登录验证
- [x] View 查看表单数据
- [x] Save 保存表单数据
- [ ] BatchSave 批量保存
- [ ] Submit 提交
- [ ] Audit 审核
- [ ] UnAudit 反审核
- [ ] Delete 删除
- [x] ExecuteBillQuery 表单数据查询
- [ ] Custom WebAPI 自定义接口
- [ ] LoginWithKick 登录带踢人
- [ ] Draft 暂存
- [ ] Allocate 分配
- [ ] Push 下推
- [ ] GroupSave 分组保存
- [ ] FlexSave 弹性域保存
- [ ] SendMsg 发送消息
- [ ] Logout 登出
- [ ] ExcuteOperation 通用操作
- [ ] SwitchOrg 切换默认组织
- [ ] WorkflowAudit 工作流审批

## ERP → MES 主线
- [x] 物料主数据同步（BD_MATERIAL，已支持真实拉取 + 本地回写 API）
- [x] BOM 数据同步（ENG_BOM，已支持真实拉取 + 本地回写 API）
- [x] 工艺路线/工序同步（已确认页面候选：GYLX / GYLXLB / GYLXCX / GYLXCXLB；真实 API 表单：ENG_ROUTE；已支持真实拉取 + 本地回写 API）
- [x] 生产工单/制造订单同步（已确认候选：SCDD / SCDDLB；真实 API 表单：PRD_MO；已支持真实拉取 + 本地回写 API）
- [x] 生产用料清单同步（真实 API 表单：PRD_PPBOM；已支持真实拉取 + 本地落库 API）
- [x] 生产入库/完工入库同步（真实 API 表单：PRD_INSTOCK；已支持真实拉取 + 本地落库 API）
- [x] 工序计划同步（真实 API 表单：SFC_OperationPlanning；已支持真实拉取 + 本地落库 API）
- [x] 工序汇报同步（真实 API 表单：SFC_OperationReport；已支持真实拉取 + 本地落库 API）
- [x] 仓库/库位基础信息同步（已确认页面候选：CK / CWZJ / WWCKSZ；真实 API 表单：BD_STOCK；仓库已支持真实拉取 + 本地回写 API）
- [x] 批次追溯基础数据同步（已确认页面候选：PHZS；真实基础 API：STK_INVENTORY；回写表单：STK_LOTADJUST；已支持真实拉取 + 本地回写 API）
- [x] 序列号主档同步（菜单编码：XLHZD；真实 API / 页面对象：BD_SerialMainFile；已支持真实拉取 API）
- [x] 批号序列号关系同步（菜单编码：PHXLHGX / PHXLHGXLB；真实 API / 页面对象：QT_LotSNRelation；已支持真实拉取 API，当前测试账套返回 0 条）
- [ ] 序列号追溯 / 批号序列号综合追溯（菜单编码：XLHZS / PHXLHZHZS；实际页面对象：QT_TraceShow + QT_TraceFilter；已确认不是普通单据型 WebAPI；当前已提供本地桥接查询接口 `/api/local-db/trace/serial`，可按前端必填条件 `FMATERIALID + FSERIALID` 返回本地根节点/关系列据，并附带 `QT_TreeModel` 树列定义 `FLEAFTEXT / FSeq / FDLOT / FDSERIALID`）
- [ ] 单件产品加工过程追溯（菜单编码：DJCPJGGCZS；当前命中 BOS_FreeTrailForModel 试用/授权门槛页，账套能力未开放）
- [x] 采购订单同步（PUR_PurchaseOrder，已支持真实拉取 + 本地回写 API）
- [x] 供应商基础资料同步（BD_Supplier，下一版低风险基础主数据，已支持拉取落库 API）
- [x] 客户基础资料同步（BD_Customer，下一版低风险基础主数据，已支持拉取落库 API）
- [x] 部门基础资料同步（BD_Department，下一版低风险基础主数据，已支持拉取落库 API）
- [x] 员工基础资料同步（BD_Empinfo，下一版低风险基础主数据，已支持拉取落库 API）
- [x] 计量单位同步（BD_UNIT，下一版低风险基础主数据，已支持拉取落库 API）
- [x] 组织同步（ORG_Organizations，下一版低风险基础主数据，已支持拉取落库 API）
- [x] 物料分类同步（BD_MATERIALCATEGORY，下一版低风险基础主数据，已支持拉取落库 API）
- [x] 库存状态同步（BD_STOCKSTATUS，下一版低风险基础主数据，已支持拉取落库 API）
