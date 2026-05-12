from __future__ import annotations

from dataclasses import dataclass

from qrmes_kingdee_integration.client.base import KingdeeQuery


MASTER_DATA_FORM_IDS: dict[str, str] = {
    "supplier": "BD_Supplier",
    "customer": "BD_Customer",
    "department": "BD_Department",
    "employee": "BD_Empinfo",
    "unit": "BD_UNIT",
    "organization": "ORG_Organizations",
    "material_category": "BD_MATERIALCATEGORY",
    "stock_status": "BD_STOCKSTATUS",
}

MASTER_DATA_ENDPOINTS: dict[str, str] = {
    "supplier": "suppliers",
    "customer": "customers",
    "department": "departments",
    "employee": "employees",
    "unit": "units",
    "organization": "organizations",
    "material_category": "material-categories",
    "stock_status": "stock-statuses",
}


@dataclass(frozen=True)
class MasterDataDefinition:
    dataset: str
    form_id: str
    field_keys: str = "FID,FNumber,FName,FDocumentStatus,FCreateDate,FModifyDate"
    order_string: str = "FNumber asc"


MASTER_DATA_DEFINITIONS: dict[str, MasterDataDefinition] = {
    dataset: MasterDataDefinition(dataset=dataset, form_id=form_id)
    for dataset, form_id in MASTER_DATA_FORM_IDS.items()
}


class MasterDataFormsService:
    """低风险基础主数据查询。

    字段只保留大多数基础资料常见字段，避免在未逐项实测前过度猜测明细字段。
    """

    def __init__(self, client, definitions: dict[str, MasterDataDefinition] | None = None):
        self.client = client
        self.definitions = definitions or MASTER_DATA_DEFINITIONS

    def query_master_data(self, dataset: str, keyword: str = "", limit: int = 50):
        definition = self.definitions[dataset]
        filter_string = ""
        if keyword.strip():
            safe = keyword.replace("'", "''")
            filter_string = f"FNumber like '%{safe}%' or FName like '%{safe}%'"
        return self.client.execute_bill_query(
            KingdeeQuery(
                form_id=definition.form_id,
                field_keys=definition.field_keys,
                filter_string=filter_string,
                order_string=definition.order_string,
                limit=min(max(limit, 1), 200),
            )
        )
