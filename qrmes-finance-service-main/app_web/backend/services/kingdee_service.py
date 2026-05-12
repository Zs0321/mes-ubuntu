from __future__ import annotations

from dataclasses import dataclass

from backend.config import KingdeeConfig
from backend.kingdee.client import KingdeeApiError, KingdeeClient, KingdeeConfigError, KingdeeQuery


@dataclass(frozen=True)
class ServiceResult:
    ok: bool
    data: dict
    status_code: int = 200


def _material_name(material_obj: dict | None) -> str:
    if not material_obj:
        return ""
    names = material_obj.get("Name") or []
    if names and isinstance(names, list):
        value = names[0].get("Value")
        if value:
            return value
    return ""


def _material_spec(material_obj: dict | None) -> str:
    if not material_obj:
        return ""
    specs = material_obj.get("Specification") or []
    if specs and isinstance(specs, list):
        value = specs[0].get("Value")
        if value:
            return value
    return ""


def _material_vendor(material_obj: dict | None) -> str:
    if not material_obj:
        return ""
    purchase = (material_obj.get("MaterialPurchase") or [{}])[0]
    vendor = purchase.get("DefaultVendor")
    return _material_name(vendor)


class KingdeeService:
    MATERIAL_FIELDS = ",".join([
        "FNumber",
        "FName",
        "FSpecification",
        "F_PZUW_Text_83g_uky",
        "FGROSSWEIGHT",
        "FNETWEIGHT",
    ])
    MATERIAL_DETAIL_FIELDS = ",".join([
        "FNumber",
        "FName",
        "FSpecification",
        "FGROSSWEIGHT",
        "FNETWEIGHT",
    ])
    BOM_HEADER_FIELDS = ",".join([
        "FNumber",
        "FName",
        "FMATERIALID",
        "FITEMNAME",
        "FITEMMODEL",
    ])
    BOM_LINE_FIELDS = ",".join([
        "FNumber",
        "FMATERIALID",
        "FMATERIALIDCHILD",
        "FMATERIALIDCHILD.FNumber",
        "FCHILDITEMNAME",
        "FCHILDITEMMODEL",
        "FNUMERATOR",
        "FDENOMINATOR",
        "FSCRAPRATE",
        "FPROCESSID",
    ])
    PURCHASE_LINE_FIELDS = ",".join([
        "FBillNo",
        "FDate",
        "FSupplierId",
        "FSupplierId.FName",
        "FMaterialId",
        "FMaterialId.FNumber",
        "FMaterialName",
        "FQty",
        "FPrice",
        "FTaxPrice",
        "FBomId",
    ])

    def __init__(self, config: KingdeeConfig, client: KingdeeClient | None = None):
        self.config = config
        self.client = client or KingdeeClient(config)

    def status(self) -> ServiceResult:
        return ServiceResult(
            ok=True,
            data={
                "ready": self.config.is_ready,
                "config": self.config.public_summary,
                "forms": [
                    {"name": "materials", "form_id": "BD_MATERIAL"},
                    {"name": "bom_headers", "form_id": "ENG_BOM"},
                    {"name": "bom_sync", "form_id": "ENG_BOM"},
                    {"name": "purchase_orders", "form_id": "PUR_PurchaseOrder"},
                ],
            },
        )

    def materials(self, limit: int = 50) -> ServiceResult:
        result = self._query(
            KingdeeQuery("BD_MATERIAL", self.MATERIAL_FIELDS, filter_string="", limit=min(limit, 200)),
            "materials",
        )
        if not result.ok:
            return result
        rows = [
            self._map_material_row(row)
            for row in result.data["rows"]
            if isinstance(row, list) and len(row) >= 6
        ]
        return ServiceResult(ok=True, data={"dataset": "materials", "rows": rows})

    def bom_headers(self, limit: int = 20, keyword: str = "", offset: int = 0) -> ServiceResult:
        filter_string = ""
        if keyword:
            safe = keyword.replace("'", "''")
            filter_string = f"FNumber like '%{safe}%' or FITEMNAME like '%{safe}%' or FITEMMODEL like '%{safe}%'"
        safe_limit = min(max(int(limit or 20), 1), 100)
        safe_offset = max(int(offset or 0), 0)
        result = self._query(
            KingdeeQuery(
                "ENG_BOM",
                self.BOM_HEADER_FIELDS,
                filter_string=filter_string,
                order_string="FNumber asc",
                start_row=safe_offset,
                limit=safe_limit,
            ),
            "bom_headers",
        )
        if not result.ok:
            return result
        rows = [
            self._map_bom_header_row(row)
            for row in result.data["rows"]
            if isinstance(row, list) and len(row) >= 5
        ]
        return ServiceResult(ok=True, data={
            "dataset": "bom_headers",
            "rows": rows,
            "limit": safe_limit,
            "offset": safe_offset,
            "next_offset": safe_offset + len(rows),
            "has_more": len(rows) >= safe_limit,
            "keyword": keyword,
        })

    def bom(self, material_code: str, limit: int = 200) -> ServiceResult:
        filter_string = ""
        if material_code:
            filter_string = f"FNumber='{material_code}'"
        result = self._query(
            KingdeeQuery("ENG_BOM", self.BOM_LINE_FIELDS, filter_string=filter_string, limit=min(limit, 500)),
            "bom",
        )
        if not result.ok:
            return result
        rows = [
            self._map_bom_line_row(row)
            for row in result.data["rows"]
            if isinstance(row, list) and len(row) >= 10
        ]
        return ServiceResult(ok=True, data={"dataset": "bom", "rows": rows})

    def purchase_orders(self, material_code: str, limit: int = 100) -> ServiceResult:
        filter_string = ""
        if material_code:
            filter_string = f"FMaterialId.FNumber='{material_code}'"
        result = self._query(
            KingdeeQuery(
                "PUR_PurchaseOrder",
                self.PURCHASE_LINE_FIELDS,
                filter_string=filter_string,
                order_string="FDate desc",
                limit=min(limit, 200),
            ),
            "purchase_orders",
        )
        if not result.ok:
            return result
        rows = [
            self._map_purchase_row(row)
            for row in result.data["rows"]
            if isinstance(row, list) and len(row) >= 11
        ]
        return ServiceResult(ok=True, data={"dataset": "purchase_orders", "rows": rows})

    def sync_bom(self, bom_number: str, model_label: str = "") -> ServiceResult:
        if not bom_number.strip():
            return ServiceResult(
                ok=False,
                status_code=400,
                data={"error": "BOM_NUMBER_REQUIRED", "message": "bom_number is required."},
            )

        detail_result = self._view("ENG_BOM", {"Number": bom_number}, "bom_view")
        if not detail_result.ok:
            return detail_result

        bom_result = self.bom(bom_number, limit=500)
        if not bom_result.ok:
            return bom_result

        bom_detail = detail_result.data["row"]
        bom_lines = bom_result.data["rows"]
        material_codes = [row["code"] for row in bom_lines if row["code"]]
        material_details = self._fetch_material_details(material_codes)
        purchase_refs = self._fetch_purchase_refs(material_codes)

        normalized_items = []
        for line in bom_lines:
            detail = material_details.get(line["code"], {})
            purchase = purchase_refs.get(line["code"], {})
            weight = detail.get("net_weight") or detail.get("gross_weight") or 0
            normalized_items.append({
                "code": line["code"],
                "name": line["name"],
                "spec": detail.get("spec") or line["spec"],
                "vendor": detail.get("vendor") or purchase.get("supplier_name") or "",
                "qty": line["qty"],
                "unit": "Pcs",
                "current_unit_price": purchase.get("price", 0),
                "target_unit_price": purchase.get("tax_price", purchase.get("price", 0)),
                "material": "",
                "material_price": 0,
                "weight_kg": weight,
                "process": line["process"],
                "material_cost_est": 0,
                "material_price_used": 0,
                "material_price_source": "pending",
                "source_tag": "金蝶导入",
            })

        model_name = (
            model_label
            or _material_name(bom_detail.get("MATERIALID"))
            or bom_detail.get("ITEMNAME")
            or bom_detail.get("Name")
            or bom_number
        )
        payload = {
            "dataset": "bom_sync",
            "model": {
                "bom_number": bom_number,
                "label": model_name,
                "parent_material_id": bom_detail.get("MATERIALID_Id") or bom_detail.get("MATERIALID", {}).get("Id"),
                "item_count": len(normalized_items),
            },
            "items": normalized_items,
            "missing_weight_codes": [item["code"] for item in normalized_items if not item["weight_kg"]],
            "missing_purchase_codes": [item["code"] for item in normalized_items if not item["current_unit_price"]],
        }
        return ServiceResult(ok=True, data=payload)

    def _fetch_material_details(self, material_codes: list[str]) -> dict[str, dict]:
        details: dict[str, dict] = {}
        if not material_codes:
            return details
        unique_codes = list(dict.fromkeys(material_codes))
        clauses = []
        for code in unique_codes[:80]:
            safe_code = code.replace("'", "''")
            clauses.append(f"FNumber='{safe_code}'")
        result = self._query(
            KingdeeQuery("BD_MATERIAL", self.MATERIAL_DETAIL_FIELDS, filter_string=" or ".join(clauses), limit=min(len(unique_codes), 200)),
            "material_details",
        )
        if not result.ok:
            return details
        for row in result.data["rows"]:
            if isinstance(row, list) and len(row) >= 6:
                mapped = self._map_material_row(row)
                details[mapped["code"]] = mapped
        return details

    def _fetch_purchase_refs(self, material_codes: list[str]) -> dict[str, dict]:
        refs: dict[str, dict] = {}
        for code in list(dict.fromkeys(material_codes))[:80]:
            result = self.purchase_orders(code, limit=1)
            if result.ok and result.data["rows"]:
                refs[code] = result.data["rows"][0]
        return refs

    def _query(self, query: KingdeeQuery, dataset: str) -> ServiceResult:
        if not self.config.is_ready:
            return ServiceResult(
                ok=False,
                status_code=503,
                data={
                    "error": "KINGDEE_CONFIG_MISSING",
                    "message": "Kingdee config is incomplete; fill the missing env vars before live sync.",
                    "dataset": dataset,
                    "missing": self.config.public_summary["missing"],
                },
            )
        try:
            result = self.client.execute_bill_query(query)
        except (KingdeeConfigError, KingdeeApiError) as exc:
            return ServiceResult(
                ok=False,
                status_code=502,
                data={"error": "KINGDEE_UPSTREAM_ERROR", "message": str(exc), "dataset": dataset},
            )
        except Exception as exc:  # pragma: no cover - defensive
            return ServiceResult(
                ok=False,
                status_code=500,
                data={"error": "UNEXPECTED_ERROR", "message": str(exc), "dataset": dataset},
            )
        upstream_error = self._extract_bill_query_error(result)
        if upstream_error:
            return ServiceResult(
                ok=False,
                status_code=502,
                data={"error": "KINGDEE_UPSTREAM_ERROR", "message": upstream_error, "dataset": dataset},
            )
        return ServiceResult(ok=True, data={"dataset": dataset, "rows": result})

    def _view(self, form_id: str, data: dict, dataset: str) -> ServiceResult:
        if not self.config.is_ready:
            return ServiceResult(
                ok=False,
                status_code=503,
                data={"error": "KINGDEE_CONFIG_MISSING", "dataset": dataset, "missing": self.config.public_summary["missing"]},
            )
        try:
            result = self.client.view(form_id, data)
        except (KingdeeConfigError, KingdeeApiError) as exc:
            return ServiceResult(ok=False, status_code=502, data={"error": "KINGDEE_UPSTREAM_ERROR", "message": str(exc), "dataset": dataset})
        except Exception as exc:  # pragma: no cover - defensive
            return ServiceResult(ok=False, status_code=500, data={"error": "UNEXPECTED_ERROR", "message": str(exc), "dataset": dataset})

        response_status = result.get("Result", {}).get("ResponseStatus", {})
        if response_status and not response_status.get("IsSuccess", False):
            return ServiceResult(ok=False, status_code=502, data={"error": "KINGDEE_VIEW_FAILED", "dataset": dataset, "detail": result})
        return ServiceResult(ok=True, data={"dataset": dataset, "row": result.get("Result", {}).get("Result", {})})

    @staticmethod
    def _map_material_row(row: list) -> dict:
        return {
            "code": row[0],
            "name": row[1],
            "spec": row[2],
            "version": row[3] or "",
            "gross_weight": row[4] or 0,
            "net_weight": row[5] or 0,
            "vendor": "",
        }

    @staticmethod
    def _map_bom_header_row(row: list) -> dict:
        return {
            "bom_number": row[0],
            "bom_name": row[1] or "",
            "parent_material_id": row[2],
            "parent_name": row[3] or "",
            "parent_spec": row[4] or "",
        }

    @staticmethod
    def _map_bom_line_row(row: list) -> dict:
        return {
            "bom_number": row[0],
            "parent_material_id": row[1],
            "material_id": row[2],
            "code": row[3] or "",
            "name": row[4] or "",
            "spec": row[5] or "",
            "qty": row[6] or 0,
            "denominator": row[7] or 1,
            "scrap_rate": row[8] or 0,
            "process": row[9] or "",
        }

    @staticmethod
    def _map_purchase_row(row: list) -> dict:
        return {
            "bill_no": row[0],
            "date": row[1],
            "supplier_id": row[2],
            "supplier_name": row[3] or "",
            "material_id": row[4],
            "material_code": row[5] or "",
            "material_name": row[6] or "",
            "qty": row[7] or 0,
            "price": row[8] or 0,
            "tax_price": row[9] or 0,
            "bom_id": row[10] or 0,
        }

    @staticmethod
    def _extract_bill_query_error(result) -> str:
        if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
            return ""
        response_status = ((result[0].get("Result") or {}).get("ResponseStatus") or {})
        if response_status and not response_status.get("IsSuccess", False):
            messages = [
                str(item.get("Message") or "").strip()
                for item in (response_status.get("Errors") or [])
                if str(item.get("Message") or "").strip()
            ]
            return "; ".join(messages) or "Kingdee bill query failed"
        return ""
