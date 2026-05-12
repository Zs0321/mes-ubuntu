from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import posixpath
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.config import AppConfig, load_config
from backend.services.demo_data_service import DemoDataService
from backend.services.excel_quote_service import ExcelQuoteService
from backend.services.kingdee_service import KingdeeService


class DemoApplication:
    def __init__(self, config: AppConfig):
        self.config = config
        self.demo_data_service = DemoDataService(config)
        self.kingdee_service = KingdeeService(config.kingdee)
        self.excel_quote_service = ExcelQuoteService(config, self.kingdee_service)

    def handle_api(self, method: str, path: str, query: dict, body: dict | None):
        if method == "GET" and path == "/api/health":
            return HTTPStatus.OK, {
                "ok": True,
                "service": "ai-finance-demo-backend",
                "kingdee_ready": self.config.kingdee.is_ready,
                "ai_quote_skill": self.excel_quote_service.ai_route_service.SKILL_NAME,
            }

        if method == "GET" and path == "/api/demo-data":
            status = self.kingdee_service.status().data
            payload = self.demo_data_service.build_payload(status)
            payload.setdefault("backend", {})
            payload["backend"]["ai_quote_skill"] = self.excel_quote_service.ai_route_service.SKILL_NAME
            payload["backend"]["ai_quote_source"] = self.excel_quote_service.ai_route_service.SOURCE_NAME
            payload["rules_source"] = self.excel_quote_service.RULES_SOURCE
            payload["rules_path"] = str(self.excel_quote_service.rules_path)
            payload["rules_available"] = self.excel_quote_service.rules_path.exists()
            return HTTPStatus.OK, payload

        if method == "GET" and path == "/api/kingdee/status":
            result = self.kingdee_service.status()
            return HTTPStatus(result.status_code), result.data

        if method == "GET" and path == "/api/kingdee/materials":
            limit = int((query.get("limit") or ["50"])[0])
            result = self.kingdee_service.materials(limit=limit)
            return HTTPStatus(result.status_code), result.data

        if method == "GET" and path == "/api/kingdee/bom-headers":
            keyword = (query.get("keyword") or [""])[0]
            limit = int((query.get("limit") or ["20"])[0])
            offset = int((query.get("offset") or ["0"])[0])
            result = self.kingdee_service.bom_headers(limit=limit, keyword=keyword, offset=offset)
            return HTTPStatus(result.status_code), result.data

        if method == "GET" and path == "/api/kingdee/bom":
            material_code = (query.get("material_code") or [""])[0]
            limit = int((query.get("limit") or ["200"])[0])
            result = self.kingdee_service.bom(material_code=material_code, limit=limit)
            return HTTPStatus(result.status_code), result.data

        if method == "GET" and path == "/api/kingdee/purchase-orders":
            material_code = (query.get("material_code") or [""])[0]
            limit = int((query.get("limit") or ["100"])[0])
            result = self.kingdee_service.purchase_orders(material_code=material_code, limit=limit)
            return HTTPStatus(result.status_code), result.data

        if method == "POST" and path == "/api/kingdee/sync":
            bom_number = (body or {}).get("bom_number", "")
            model_label = (body or {}).get("model_label", "")
            result = self.kingdee_service.sync_bom(bom_number=bom_number, model_label=model_label)
            if not result.ok:
                return HTTPStatus(result.status_code), result.data
            return HTTPStatus(result.status_code), self._enrich_quote_payload(
                result.data,
                items_key="items",
                scenario_source="金蝶导入",
                include_ai=False,
            )

        if method == "POST" and path == "/api/quote/ai-route":
            items = (body or {}).get("items") or []
            if not isinstance(items, list) or not items:
                return HTTPStatus.BAD_REQUEST, {"error": "ITEMS_REQUIRED", "message": "items is required."}
            payload = {
                "dataset": "ai_route_refresh",
                "model": (body or {}).get("model") or {},
                "items": items,
            }
            scenario_source = (body or {}).get("scenario_source") or "金蝶导入"
            return HTTPStatus.OK, self._enrich_quote_payload(
                payload,
                items_key="items",
                scenario_source=str(scenario_source),
                include_ai=True,
            )

        return HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND", "path": path}

    def _enrich_quote_payload(
        self,
        payload: dict,
        *,
        items_key: str,
        scenario_source: str,
        include_ai: bool = True,
        progress_callback=None,
    ) -> dict:
        enriched = copy.deepcopy(payload or {})
        raw_items = enriched.get(items_key) or []
        if not raw_items:
            enriched.setdefault("rules_source", self.excel_quote_service.RULES_SOURCE)
            enriched.setdefault("rules_path", str(self.excel_quote_service.rules_path))
            enriched.setdefault("rules_available", self.excel_quote_service.rules_path.exists())
            return enriched

        priced_items = self._price_items(
            raw_items,
            scenario_source=scenario_source,
            include_ai=include_ai,
            progress_callback=progress_callback,
        )
        enriched[items_key] = priced_items
        enriched["summary"] = self.excel_quote_service._build_summary(priced_items)
        enriched["rules_source"] = self.excel_quote_service.RULES_SOURCE
        enriched["rules_path"] = str(self.excel_quote_service.rules_path)
        enriched["rules_available"] = self.excel_quote_service.rules_path.exists()
        enriched.setdefault("backend", {})
        enriched["backend"]["ai_quote_skill"] = self.excel_quote_service.ai_route_service.SKILL_NAME
        enriched["backend"]["ai_quote_source"] = self.excel_quote_service.ai_route_service.SOURCE_NAME
        return enriched

    def _price_items(self, raw_items: list[dict], *, scenario_source: str, include_ai: bool = True, progress_callback=None) -> list[dict]:
        service = self.excel_quote_service
        items = [self._normalize_item(item, scenario_source=scenario_source) for item in raw_items]
        purchase_refs = service._fetch_purchase_refs([service._to_text(item.get("code")) for item in items if service._to_text(item.get("code"))])

        for item in items:
            code = service._to_text(item.get("code"))
            purchase = purchase_refs.get(code, {})
            if purchase:
                item["kingdee_reference_price"] = service._to_number(item.get("kingdee_reference_price")) or service._to_number(purchase.get("price"))
                item["kingdee_reference_tax_price"] = service._to_number(item.get("kingdee_reference_tax_price")) or service._to_number(purchase.get("tax_price"))
                item["kingdee_supplier_name"] = service._to_text(item.get("kingdee_supplier_name")) or service._to_text(purchase.get("supplier_name"))
                item["kingdee_bill_no"] = service._to_text(item.get("kingdee_bill_no")) or service._to_text(purchase.get("bill_no"))
                item["kingdee_reference_date"] = service._to_text(item.get("kingdee_reference_date")) or service._to_text(purchase.get("date"))
                if not service._to_text(item.get("vendor")):
                    item["vendor"] = service._to_text(purchase.get("supplier_name"))

            if scenario_source == "金蝶导入" and service._to_number(item.get("kingdee_reference_price")) <= 0 and service._to_number(item.get("current_unit_price")) > 0:
                item["kingdee_reference_price"] = service._to_number(item.get("current_unit_price"))
                item["current_unit_price"] = 0.0

            route = service._estimate_changjiang_route(item)
            item.update(route)

            finance_unit_price, finance_source, finance_has_reference = service._pick_finance_route(item)
            item["reference_unit_price"] = finance_unit_price
            item["reference_source"] = finance_source
            item["finance_route_unit_price"] = finance_unit_price
            item["finance_route_source"] = finance_source
            item["finance_route_has_reference"] = finance_has_reference
            item["finance_route_status"] = "传统参考命中" if finance_has_reference else "缺传统参考"
            item["source_tag"] = service._to_text(item.get("source_tag")) or scenario_source

        if include_ai:
            ai_route_results = service._estimate_ai_routes(items, progress_callback=progress_callback)
        else:
            ai_route_results = []
            for _ in items:
                pending = service._empty_ai_route_result("AI报价正在由 changjiang-bom-pricing 计算，结果会稍后刷新")
                pending["ai_route_status"] = "AI计算中"
                ai_route_results.append(pending)

        for item, ai_result in zip(items, ai_route_results):
            item.update(ai_result)
            finance_unit_price = service._to_number(item.get("finance_route_unit_price"))
            ai_unit_price = service._to_number(item.get("ai_route_unit_price"))
            qty = service._to_number(item.get("qty")) or 1.0
            item["route_gap_unit_price"] = ai_unit_price - finance_unit_price
            item["route_gap_total"] = (ai_unit_price - finance_unit_price) * qty
            item["comparison_reason_summary"] = (
                service._analyze_price_gap(item)
                if include_ai
                else "AI报价正在由 changjiang-bom-pricing 计算，稍后将自动刷新对比结果。"
            )
            item["status"] = service._item_status(item) if include_ai else "AI计算中"
        return items

    def _normalize_item(self, item: dict, *, scenario_source: str) -> dict:
        service = self.excel_quote_service
        normalized = copy.deepcopy(item or {})
        normalized["code"] = service._to_text(normalized.get("code"))
        normalized["name"] = service._to_text(normalized.get("name")) or normalized["code"] or "未命名物料"
        normalized["spec"] = service._to_text(normalized.get("spec"))
        normalized["vendor"] = service._to_text(normalized.get("vendor"))
        normalized["qty"] = service._to_number(normalized.get("qty")) or 1.0
        normalized["unit"] = service._to_text(normalized.get("unit")) or "Pcs"
        normalized["current_unit_price"] = service._to_number(normalized.get("current_unit_price"))
        normalized["target_unit_price"] = service._to_number(normalized.get("target_unit_price"))
        normalized["weight_kg"] = service._to_number(normalized.get("weight_kg") or normalized.get("weight"))
        normalized["extra"] = service._to_number(normalized.get("extra"))
        normalized["source_tag"] = service._to_text(normalized.get("source_tag")) or scenario_source

        material_text = service._to_text(normalized.get("material"))
        process_text = service._to_text(normalized.get("process"))
        inferred_process, inferred_material = service._infer_process_and_material(
            normalized["name"],
            normalized["spec"],
            material_text,
            process_text,
        )
        normalized["process"] = process_text or inferred_process
        material_alias = service._to_text(normalized.get("material_alias")) or service._material_alias(material_text)
        if not material_alias or material_alias == "未识别":
            material_alias = inferred_material or service._material_alias(" ".join(part for part in (normalized["name"], normalized["spec"], normalized["process"]) if part))
        normalized["material_original"] = service._to_text(normalized.get("material_original")) or material_text or material_alias or "未识别"
        normalized["material_alias"] = material_alias or ""
        normalized["material"] = normalized["material_original"]

        defaults = service.PROCESS_DEFAULTS.get(normalized["process"], {"lossRate": 0.05, "processFactor": 1.1})
        normalized["loss"] = service._to_ratio(normalized.get("loss"), defaults["lossRate"])
        normalized["material_price"] = service._to_number(normalized.get("material_price"))

        market_lookup = service._latest_raw_price(material_text or normalized["material"] or normalized["name"])
        if service._to_number(normalized.get("material_price_used")) > 0:
            normalized["material_price_used"] = service._to_number(normalized.get("material_price_used"))
            normalized["material_price_source"] = service._to_text(normalized.get("material_price_source")) or "provided"
        elif normalized["material_price"] > 0:
            normalized["material_price_used"] = normalized["material_price"]
            normalized["material_price_source"] = "provided"
        else:
            normalized["material_price_used"] = service._to_number(market_lookup.get("price"))
            normalized["material_price_source"] = market_lookup.get("source", "pending")

        normalized["material_cost_est"] = service._to_number(normalized.get("material_cost_est"))
        normalized["process_cost_est"] = service._to_number(normalized.get("process_cost_est"))
        normalized["kingdee_reference_price"] = service._to_number(normalized.get("kingdee_reference_price"))
        normalized["kingdee_reference_tax_price"] = service._to_number(normalized.get("kingdee_reference_tax_price"))
        normalized["kingdee_supplier_name"] = service._to_text(normalized.get("kingdee_supplier_name"))
        normalized["kingdee_bill_no"] = service._to_text(normalized.get("kingdee_bill_no"))
        normalized["kingdee_reference_date"] = service._to_text(normalized.get("kingdee_reference_date"))
        return normalized

    def resolve_static_file(self, request_path: str) -> Path:
        relative = request_path or "/"
        if relative == "/":
            relative = "/index.html"
        safe_path = posixpath.normpath(relative).lstrip("/")
        candidate = (self.config.static_dir / safe_path).resolve()
        static_root = self.config.static_dir.resolve()
        if static_root not in candidate.parents and candidate != static_root:
            raise FileNotFoundError(relative)
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.exists():
            raise FileNotFoundError(relative)
        return candidate


class DemoRequestHandler(BaseHTTPRequestHandler):
    app: DemoApplication | None = None

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def _handle(self, method: str) -> None:
        assert self.app is not None
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            body = self._read_json_body() if method == "POST" else None
            status, payload = self.app.handle_api(method, parsed.path, parse_qs(parsed.query), body)
            self._write_json(status, payload)
            return

        try:
            file_path = self.app.resolve_static_file(parsed.path)
        except FileNotFoundError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "STATIC_FILE_NOT_FOUND"})
            return
        self._write_file(file_path)

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return None
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return None
        return json.loads(raw)

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_file(self, file_path: Path) -> None:
        content = file_path.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(file_path))
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", f"{mime_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def create_server(host: str, port: int, config: AppConfig) -> ThreadingHTTPServer:
    app = DemoApplication(config)
    DemoRequestHandler.app = app
    return ThreadingHTTPServer((host, port), DemoRequestHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI finance demo backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--static-dir", default="")
    args = parser.parse_args()

    static_dir = Path(args.static_dir).resolve() if args.static_dir else None
    config = load_config(static_dir=static_dir)
    server = create_server(args.host, args.port, config)
    print(f"Serving demo on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
