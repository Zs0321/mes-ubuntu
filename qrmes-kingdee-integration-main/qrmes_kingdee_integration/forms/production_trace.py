from __future__ import annotations

from qrmes_kingdee_integration.client.base import KingdeeQuery

PRODUCTION_MATERIAL_LIST_FORM_ID = "PRD_PPBOM"
PRODUCTION_INSTOCK_FORM_ID = "PRD_INSTOCK"
OPERATION_PLANNING_FORM_ID = "SFC_OperationPlanning"
OPERATION_REPORT_FORM_ID = "SFC_OperationReport"


class ProductionMaterialListFormsService:
    DEFAULT_LIST_FIELDS = ",".join([
        "FID",
        "FBillNo",
        "FDocumentStatus",
        "FMaterialId.FNumber",
        "FMaterialId.FName",
        "FMaterialId.FSpecification",
        "FWorkShopID.FNumber",
        "FWorkShopID.FName",
        "FMoBillNo",
        "FQty",
        "FUnitID.FName",
        "FStockId.FNumber",
        "FLot.FNumber",
    ])

    def __init__(self, client):
        self.client = client

    def query_production_material_lists(self, limit: int = 100, keyword: str = ""):
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=PRODUCTION_MATERIAL_LIST_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=_keyword_filter(keyword, ["FBillNo", "FMoBillNo", "FMaterialId.FNumber", "FMaterialId.FName", "FLot.FNumber"]),
                order_string="FModifyDate desc",
                limit=min(max(limit, 1), 200),
            )
        )


class ProductionInstockFormsService:
    DEFAULT_LIST_FIELDS = ",".join([
        "FID",
        "FBillNo",
        "FDocumentStatus",
        "FDate",
        "FMaterialId.FNumber",
        "FMaterialId.FName",
        "FStockOrgId.FNumber",
        "FMoBillNo",
        "FQty",
        "FUnitID.FName",
        "FStockId.FNumber",
        "FLot.FNumber",
        "FSerialNo",
    ])

    def __init__(self, client):
        self.client = client

    def query_production_instocks(self, limit: int = 100, keyword: str = ""):
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=PRODUCTION_INSTOCK_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=_keyword_filter(keyword, ["FBillNo", "FMoBillNo", "FMaterialId.FNumber", "FSerialNo", "FLot.FNumber"]),
                order_string="FDate desc",
                limit=min(max(limit, 1), 200),
            )
        )


class OperationPlanningFormsService:
    DEFAULT_LIST_FIELDS = ",".join([
        "FID",
        "FBillNo",
        "FDocumentStatus",
        "FMONumber",
        "FOperNumber",
        "FOperDescription",
        "FProductId.FNumber",
        "FQualifiedQty",
        "FReworkQty",
        "FSourceBillNo",
    ])

    def __init__(self, client):
        self.client = client

    def query_operation_plannings(self, limit: int = 100, keyword: str = ""):
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=OPERATION_PLANNING_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=_keyword_filter(keyword, ["FBillNo", "FMONumber", "FProductId.FNumber", "FOperDescription", "FSourceBillNo"]),
                order_string="FModifyDate desc",
                limit=min(max(limit, 1), 200),
            )
        )


class OperationReportFormsService:
    DEFAULT_LIST_FIELDS = ",".join([
        "FID",
        "FBillNo",
        "FDocumentStatus",
        "FDate",
        "FMONumber",
        "FOperNumber",
        "FOperDescription",
        "FSerialNo",
        "FFinishQty",
        "FReworkQty",
        "FSourceBillNo",
    ])

    def __init__(self, client):
        self.client = client

    def query_operation_reports(self, limit: int = 100, keyword: str = ""):
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=OPERATION_REPORT_FORM_ID,
                field_keys=self.DEFAULT_LIST_FIELDS,
                filter_string=_keyword_filter(keyword, ["FBillNo", "FMONumber", "FSerialNo", "FOperDescription", "FSourceBillNo"]),
                order_string="FDate desc",
                limit=min(max(limit, 1), 200),
            )
        )


def _keyword_filter(keyword: str, fields: list[str]) -> str:
    keyword = (keyword or "").strip()
    if not keyword:
        return ""
    safe = keyword.replace("'", "''")
    return " or ".join(f"{field} like '%{safe}%'" for field in fields)
