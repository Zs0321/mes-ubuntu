from __future__ import annotations

from typing import Any


VERIFIED_API_FORMIDS: list[dict[str, Any]] = [
    {"form_id": "BD_MATERIAL", "name": "物料", "usage": "物料编码、名称、规格和追溯方式基础资料。"},
    {"form_id": "ENG_BOM", "name": "BOM", "usage": "配料扫码时校验物料是否属于生产 BOM。"},
    {"form_id": "PUR_PurchaseOrder", "name": "采购订单", "usage": "收货贴标来源单据。"},
    {"form_id": "PRD_MO", "name": "生产订单", "usage": "配料、装配绑定的生产来源。"},
    {"form_id": "PRD_PPBOM", "name": "生产用料清单", "usage": "生产投料与 BOM 展开。"},
    {"form_id": "PRD_INSTOCK", "name": "生产入库", "usage": "PCBA/半成品转换入库候选链路。"},
    {"form_id": "SFC_OperationPlanning", "name": "工序计划", "usage": "工序执行链路。"},
    {"form_id": "SFC_OperationReport", "name": "工序汇报", "usage": "工序执行结果。"},
    {"form_id": "BD_STOCK", "name": "仓库", "usage": "库存落点和仓库基础资料。"},
    {"form_id": "STK_INVENTORY", "name": "即时库存", "usage": "本地批次库存基础查询。"},
    {"form_id": "STK_LOTADJUST", "name": "批号调整单", "usage": "后续批次追溯字段回写候选。"},
    {"form_id": "BD_Supplier", "name": "供应商", "usage": "供应商编码与供应商二维码来源。"},
    {"form_id": "BD_Customer", "name": "客户", "usage": "出货追溯客户侧基础资料。"},
    {"form_id": "BD_Department", "name": "部门", "usage": "执行责任部门。"},
    {"form_id": "BD_Empinfo", "name": "员工", "usage": "操作员/检验员基础资料。"},
    {"form_id": "BD_UNIT", "name": "计量单位", "usage": "数量单位校验。"},
    {"form_id": "ORG_Organizations", "name": "组织", "usage": "账套组织维度。"},
    {"form_id": "BD_MATERIALCATEGORY", "name": "物料分类", "usage": "标签默认单位和追溯策略。"},
    {"form_id": "BD_STOCKSTATUS", "name": "库存状态", "usage": "待检、可用、冻结等状态映射。"},
    {"form_id": "BD_SerialMainFile", "name": "序列号主档", "usage": "单件 SN 追溯基础资料。"},
    {"form_id": "QT_LotSNRelation", "name": "批号序列号关系", "usage": "批号与序列号关系查询。"},
]


RUNTIME_BRIDGE_FORMIDS: list[dict[str, Any]] = [
    {
        "form_id": "QT_TraceShow",
        "name": "追溯展示运行态",
        "usage": "不是普通 ExecuteBillQuery 数据集；当前通过本地桥接查询返回追溯树。",
    },
    {
        "form_id": "QT_TraceFilter",
        "name": "追溯过滤运行态",
        "usage": "追溯页面筛选对象；需与 QT_TraceShow 一起桥接。",
    },
    {
        "form_id": "QT_TreeModel",
        "name": "追溯树模型",
        "usage": "追溯页面树/明细列定义，当前仅用于桥接输出说明。",
    },
]


UI_MENU_CODES: list[dict[str, Any]] = [
    {"code": "SCDD", "name": "生产订单", "note": "UI 菜单编码，不是 WebAPI FormId。"},
    {"code": "GYLX", "name": "工艺路线", "note": "UI 菜单编码，不是 WebAPI FormId。"},
    {"code": "CK", "name": "仓库", "note": "UI 菜单编码，不是 WebAPI FormId。"},
    {"code": "PHZS", "name": "批号追溯", "note": "UI 菜单编码，不是 WebAPI FormId。"},
    {"code": "XLHZD", "name": "序列号主档菜单", "note": "菜单入口已对应到 BD_SerialMainFile。"},
    {"code": "XLHZS", "name": "序列号追溯", "note": "运行态追溯入口，不是普通数据集。"},
    {"code": "PHXLHGX", "name": "批号序列号关系", "note": "菜单入口已对应到 QT_LotSNRelation。"},
    {"code": "PHXLHGXLB", "name": "批号序列号关系列表", "note": "UI 菜单编码。"},
    {"code": "PHXLHZHZS", "name": "批号序列号综合追溯", "note": "运行态追溯入口。"},
    {"code": "DJCPJGGCZS", "name": "单件产品加工过程追溯", "note": "当前可能受授权/试用限制。"},
]


RESTRICTED_FORMIDS: list[dict[str, Any]] = [
    {
        "form_id": "BOS_FreeTrailForModel",
        "name": "智慧车间试用/授权门槛",
        "usage": "DJCPJGGCZS 当前可能落到该限制页，不能作为已可用追溯 API。",
        "status": "restricted_or_trial_limited",
    }
]


PENDING_FORMIDS: list[dict[str, Any]] = [
    {
        "form_id": "PUR_ReceiveBill",
        "name": "采购收料/收货通知",
        "usage": "收货贴标结果写回、批次码/包装码字段落点。",
        "status": "pending_confirmation",
    },
    {
        "form_id": "STK_InStock",
        "name": "采购入库单",
        "usage": "合格入库后是否生成/更新采购入库单，字段映射待确认。",
        "status": "pending_confirmation",
    },
    {
        "form_id": "IQC_OR_QMS_FORM",
        "name": "来料检/IQC 对象",
        "usage": "来料检报告、判定结果、附件与批次绑定；真实 FormId 待账套/XHR 确认。",
        "status": "pending_confirmation",
    },
    {
        "form_id": "STK_TransferDirect_OR_STK_MISCELLANEOUS",
        "name": "库存移动/调拨/出库对象",
        "usage": "配料出库、线边余料回仓、冻结/解冻等库存动作；真实对象和字段待确认。",
        "status": "pending_confirmation",
    },
    {
        "form_id": "SAL_OUTSTOCK_OR_SAL_DELIVERY",
        "name": "销售出库/出货对象",
        "usage": "箱码、产品 SN 与出货单绑定；真实 API FormId 待确认。",
        "status": "pending_confirmation",
    },
    {
        "form_id": "PACKING_BOX_RELATION",
        "name": "箱码/包装关系对象",
        "usage": "箱码、包装码、产品 SN 的关系写回；金蝶标准或自定义对象待确认。",
        "status": "pending_confirmation",
    },
]


def formid_registry() -> dict[str, Any]:
    return {
        "mode": "local_sqlite_first_kingdee_writeback_later",
        "verified_api": VERIFIED_API_FORMIDS,
        "runtime_bridge": RUNTIME_BRIDGE_FORMIDS,
        "ui_menu": UI_MENU_CODES,
        "restricted": RESTRICTED_FORMIDS,
        "pending": PENDING_FORMIDS,
    }


def legacy_formid_plan_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in VERIFIED_API_FORMIDS:
        items.append({**item, "status": "verified_api"})
    for item in RUNTIME_BRIDGE_FORMIDS:
        items.append({**item, "status": "runtime_bridge"})
    for item in PENDING_FORMIDS:
        items.append(item)
    for item in RESTRICTED_FORMIDS:
        items.append(item)
    return items
