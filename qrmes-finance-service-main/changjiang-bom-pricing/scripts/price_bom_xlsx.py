
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import csv
import gzip
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

from extract_bom_xlsx import extract_sheet_rows

Z_PRODUCT = "\u4ea7\u54c1"
Z_PRODUCT_CODE = "\u4ea7\u54c1\u7f16\u7801"
Z_ITEM = "\u7269\u6599"
Z_ITEM_NAME = "\u7269\u6599\u540d\u79f0"
Z_CODE = "\u7269\u6599\u7f16\u7801"
Z_SPEC = "\u89c4\u683c\u578b\u53f7"
Z_SPEC_SHORT = "\u89c4\u683c"
Z_MATERIAL = "\u6750\u8d28"
Z_WEIGHT = "\u91cd\u91cf"
Z_WEIGHT_KG = "\u91cd\u91cfkg"
Z_WEIGHT_KG_ALT = "\u91cd\u91cf\uff08kg\uff09"
Z_PROCESS = "\u5de5\u827a"
Z_QTY = "\u6570\u91cf"
Z_STD_PRICE = "\u6807\u51c6\u4ef6\u4ef7\u683c"
Z_TAX_PRICE = "\u542b\u7a0e\u5355\u4ef7"
Z_PURCHASE_TOTAL = "\u76ee\u524d\u91c7\u8d2d\u603b\u4ef7"

Z_PRICE_TYPE = "\u57fa\u7840\u4ef7\u683c\u7c7b\u578b"
Z_PRICE_SOURCE = "\u57fa\u7840\u4ef7\u683c\u6765\u6e90"
Z_BASE_UNIT = "\u57fa\u7840\u5355\u4ef7"
Z_BASE_TOTAL = "\u57fa\u7840\u91d1\u989d"
Z_PROCESS_COMPLEXITY = "\u5de5\u827a\u590d\u6742\u5ea6"
Z_PROCESS_UNIT = "\u5de5\u827a\u5355\u4ef7"
Z_PROCESS_TOTAL = "\u5de5\u827a\u91d1\u989d"
Z_LINE_TOTAL = "\u884c\u603b\u4ef7"
Z_EXT_WEIGHT = "\u5ef6\u5c55\u91cd\u91cfkg"

KW_STATOR = ["\u5b9a\u5b50", "\u8f6c\u5b50"]
KW_STATOR_PROCESS = ["\u7ed5\u7ebf", "\u5d4c\u7ebf", "\u6d78\u6f06", "\u70d8\u5e72", "VPI", "\u771f\u7a7a\u538b\u529b\u6d78\u6f06"]
KW_STATOR_MATERIAL = ["\u6f06\u5305\u7ebf", "\u6241\u94dc\u7ebf", "\u94dc\u7ebf", "\u94dc"]
KW_STATOR_SPEC = ["\u6d78\u6f06\u5b9a\u5b50", "\u7ed5\u7ebf", "\u5d4c\u7ebf", "\u70d8\u5e72", "VPI"]
KW_STACKING = ["\u51b2\u538b\u53e0\u538b", "\u51b2\u538b\u53ca\u94c1\u82af\u53e0\u538b", "\u94c1\u82af\u53e0\u538b", "\u51b2\u7247\u53e0\u538b", "\u51b2\u538b\u53e0\u7247", "\u51b2\u538b\u53e0\u88c5"]
KW_MAGNET = ["\u6c38\u78c1\u4f53", "\u94dd\u94c1\u787c", "UH"]
KW_MACHINE = ["\u673a\u52a0\u5de5", "\u8f66\u524a", "\u78e8\u524a", "\u94e3\u524a", "\u94bb\u5b54"]
KW_SHEET_METAL = ["\u51b2\u538b", "\u6298\u5f2f", "\u6fc0\u5149\u5207\u5272", "\u6fc0\u5149\u5207\u5272+\u6298\u5f2f", "\u6fc0\u5149\u5207\u5272\u6298\u5f2f"]
KW_WELD = ["\u710a", "\u94ce\u710a"]
KW_FINISHING = ["\u6d78\u6f06", "\u70d8\u5e72", "\u7edd\u7f18", "\u88c5\u914d"]
KW_CASTING = ["\u538b\u94f8"]
KW_INJECTION = ["\u6ce8\u5851"]
KW_COLD = ["\u51b7\u9566"]
KW_SINTER = ["\u70e7\u7ed3"]

OUTPUT_HEADER = [
    Z_PRODUCT, Z_ITEM, Z_CODE, Z_MATERIAL, Z_PROCESS, Z_QTY, Z_WEIGHT_KG, Z_EXT_WEIGHT,
    Z_PRICE_TYPE, Z_PRICE_SOURCE, Z_BASE_UNIT, Z_BASE_TOTAL, Z_PROCESS_COMPLEXITY,
    Z_PROCESS_UNIT, Z_PROCESS_TOTAL, Z_LINE_TOTAL, Z_PURCHASE_TOTAL,
]

FALLBACK_SNAPSHOT = {
    "copper_1": {"unit_price_per_kg": 78.0, "source_name": "\u957f\u6c5f 1#\u7535\u89e3\u94dc", "source_url": "https://www.cjys.net/", "quoted_date": "", "note": "fallback"},
    "al_a00": {"unit_price_per_kg": 20.5, "source_name": "\u957f\u6c5f \u94ddA00", "source_url": "https://www.cjys.net/", "quoted_date": "", "note": "fallback"},
    "enameled_wire": {"unit_price_per_kg": 107.32, "source_name": "\u957f\u6c5f \u6f06\u5305\u7ebf", "source_url": "https://www.cjys.net/", "quoted_date": "", "note": "fallback"},
    "a3562": {"unit_price_per_kg": 22.6, "source_name": "\u957f\u6c5f A356.2\u94f8\u9020\u94dd\u5408\u91d1", "source_url": "https://www.cjys.net/", "quoted_date": "", "note": "fallback"},
    "prnd_metal": {"unit_price_per_kg": 890.0, "source_name": "SMM \u9568\u94d5\u91d1\u5c5e", "source_url": "https://hq.smm.cn/h5/praseodymium-neodymium-metal-price", "quoted_date": "", "note": "fallback"},
    "silicon_steel_proxy": {"unit_price_per_kg": 5.05, "source_name": "SMM \u4e0a\u6d77\u5b9d\u94a2 B50A470 \u65e0\u53d6\u5411\u7845\u94a2", "source_url": "https://hq.smm.cn/h5/SiFe-non-oriented-price", "quoted_date": "", "note": "fallback"},
}


def to_float(value: str) -> float:
    text = (value or "").strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def fmt_num(value: float) -> str:
    if abs(value) < 1e-9:
        return "0"
    return f"{value:.4f}".rstrip("0").rstrip(".")


def contains_any(text: str, keywords: list[str]) -> bool:
    base = text or ""
    return any(keyword in base for keyword in keywords)


def is_stator_winding_component(row: dict) -> bool:
    item = str(row.get("item", "") or "")
    spec = str(row.get("spec", "") or "")
    material = str(row.get("material", "") or "")
    if not contains_any(item, KW_STATOR):
        return False
    return (
        contains_any(spec, KW_STATOR_SPEC)
        or contains_any(material, KW_STATOR_MATERIAL)
        or contains_any(str(row.get("process", "") or ""), KW_STATOR_PROCESS)
    )


def is_stator_core_component(row: dict) -> bool:
    item = str(row.get("item", "") or "")
    spec = str(row.get("spec", "") or "")
    material = str(row.get("material", "") or "")
    process = str(row.get("process", "") or "")
    if not contains_any(item, ["定子", "铁芯", "转子铁芯"]):
        return False
    return (
        contains_any(material, ["35W", "硅钢", "铁芯", "B30AHV"])
        or contains_any(spec, ["35W", "硅钢", "铁芯"])
        or contains_any(process, KW_STACKING)
    )


def clean_header(value: str) -> str:
    return (value or "").strip().replace("\n", "")


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read()
        content_encoding = response.headers.get("Content-Encoding", "")
    if "gzip" in content_encoding.lower():
        data = gzip.decompress(data)
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def average_range(low: float, high: float) -> float:
    return (low + high) / 2.0


def extract_cjys_quote(html: str, label: str) -> tuple[float, str]:
    pattern = rf"{re.escape(label)}</td><td class=\"p-price\">\s*(\d+(?:\.\d+)?)~(\d+(?:\.\d+)?)</td>.*?<td class=\"p-date\">(\d{{4}}-\d{{2}}-\d{{2}})</td>"
    match = re.search(pattern, html, flags=re.S)
    if not match:
        raise ValueError(label)
    return average_range(float(match.group(1)), float(match.group(2))), match.group(3)


def extract_smm_table_quote(html: str, label: str) -> tuple[float, str]:
    pattern = rf">{re.escape(label)}</a></td><td class=\"ant-table-cell\".*?><span.*?>(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)</span></td><td class=\"ant-table-cell\".*?><span.*?>(\d+(?:\.\d+)?)</span></td>.*?<td class=\"ant-table-cell\".*?>(\d{{4}}-\d{{2}}-\d{{2}})</td>"
    match = re.search(pattern, html, flags=re.S)
    if not match:
        raise ValueError(label)
    return float(match.group(3)), match.group(4)


def parse_magnet_weight_from_spec(spec: str, qty: float) -> float:
    if not spec:
        return 0.0
    text = spec.replace("?", "x").replace("X", "x").replace("?", "x").replace("*", "x").replace("mm", "")
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if len(nums) < 3:
        return 0.0
    a, b, c = (float(nums[0]), float(nums[1]), float(nums[2]))
    return a * b * c * 7.5e-6 * qty


def fetch_live_market_snapshot() -> dict:
    snapshot = {key: value.copy() for key, value in FALLBACK_SNAPSHOT.items()}
    try:
        cjys_url = "https://www.cjys.net/"
        cjys_html = fetch_text(cjys_url)
        for label, key in [
            ("\u957f\u6c5f 1#\u7535\u89e3\u94dc", "copper_1"),
            ("\u957f\u6c5f \u94ddA00", "al_a00"),
            ("\u957f\u6c5f \u6f06\u5305\u7ebf", "enameled_wire"),
            ("\u957f\u6c5f A356.2\u94f8\u9020\u94dd\u5408\u91d1", "a3562"),
        ]:
            try:
                avg, qd = extract_cjys_quote(cjys_html, label)
                snapshot[key].update({"unit_price_per_kg": avg / 1000.0, "quoted_date": qd, "note": "live"})
            except Exception:
                pass
    except Exception:
        pass
    try:
        html = fetch_text("https://hq.smm.cn/h5/praseodymium-neodymium-metal-price")
        avg, qd = extract_smm_table_quote(html, "\u9568\u94d5\u91d1\u5c5e\u4ef7\u683c")
        snapshot["prnd_metal"].update({"unit_price_per_kg": avg / 1000.0, "quoted_date": qd, "note": "live"})
    except Exception:
        pass
    try:
        html = fetch_text("https://hq.smm.cn/h5/SiFe-non-oriented-price")
        avg, qd = extract_smm_table_quote(html, "B50A470\u4e0a\u6d77\u5b9d\u94a2\u7845\u94a2\u4ef7\u683c")
        snapshot["silicon_steel_proxy"].update({"unit_price_per_kg": avg / 1000.0, "quoted_date": qd, "note": "live"})
    except Exception:
        pass
    return snapshot


def normalize_rows(extracted: dict, fallback_product: str) -> list[dict]:
    headers = [clean_header(v) for v in extracted.get("header", [])]
    header_map = {name: idx for idx, name in enumerate(headers) if name}
    rows = []
    for raw in extracted.get("rows", []):
        padded = raw + [""] * max(0, len(headers) - len(raw))
        def value(*names, default=""):
            for name in names:
                if name in header_map:
                    return (padded[header_map[name]] or "").strip()
            return default
        product = value(Z_PRODUCT, default=fallback_product) or fallback_product
        product_code = value(Z_PRODUCT_CODE)
        item = value(Z_ITEM, Z_ITEM_NAME)
        code = value(Z_CODE)
        spec = value(Z_SPEC, Z_SPEC_SHORT)
        material = value(Z_MATERIAL)
        process = value(Z_PROCESS)
        qty = to_float(value(Z_QTY, default="1")) or 1.0
        weight_kg = to_float(value(Z_WEIGHT, Z_WEIGHT_KG, Z_WEIGHT_KG_ALT))
        unit_tax_price = to_float(value(Z_TAX_PRICE, Z_STD_PRICE))
        current_total = to_float(value(Z_PURCHASE_TOTAL))
        if current_total <= 0 and unit_tax_price > 0:
            current_total = unit_tax_price * qty
        if unit_tax_price <= 0 and current_total > 0 and qty > 0:
            unit_tax_price = current_total / qty
        if weight_kg <= 0 and contains_any(material, ["\u94dd\u94c1\u787c", "UH"]):
            weight_kg = parse_magnet_weight_from_spec(spec, 1.0)
        if not code and not item:
            continue
        rows.append({
            "product": product,
            "product_code": product_code,
            "item": item,
            "code": code,
            "material": material,
            "spec": spec,
            "weight_kg": weight_kg,
            "process": process,
            "std_price": unit_tax_price,
            "current_purchase_total": current_total,
            "qty": qty,
            "ext_weight_kg": weight_kg * qty,
        })
    return rows


def quote_label(name: str, quoted_date: str) -> str:
    return f"{name}({quoted_date})" if quoted_date else name


def material_quote(snapshot: dict, key: str, price_type: str = "material") -> dict:
    source = snapshot[key]
    return {"price_type": price_type, "price_source": quote_label(source["source_name"], source.get("quoted_date", "")), "unit_price": source["unit_price_per_kg"], "source_url": source.get("source_url", ""), "source_date": source.get("quoted_date", ""), "source_note": source.get("note", "")}


def map_material(row: dict, snapshot: dict) -> dict:
    material = row["material"]
    std_price = row["std_price"]
    qty = row["qty"]
    ext_weight = row["ext_weight_kg"]
    if is_stator_winding_component(row):
        q = material_quote(snapshot, "enameled_wire")
        return {**q, "base_total": q["unit_price"] * ext_weight}
    if is_stator_core_component(row):
        q = material_quote(snapshot, "silicon_steel_proxy")
        return {**q, "base_total": q["unit_price"] * ext_weight}
    if not material and std_price > 0:
        return {"price_type": "standard", "price_source": Z_STD_PRICE, "unit_price": std_price, "base_total": std_price * qty, "source_url": "", "source_date": "", "source_note": "BOM"}
    if contains_any(material, ["35W", "硅钢", "铁芯", "B30AHV"]):
        q = material_quote(snapshot, "silicon_steel_proxy")
        return {**q, "base_total": q["unit_price"] * ext_weight}
    if any(token in material for token in ["20CrMnTi", "40Cr", "45", "Q235", "Q235B", "SPHC", "SPAH440", "QT450-10", "钢"]):
        unit = 3.18 if "QT450-10" not in material else 4.8
        source = "钢材代理价" if "QT450-10" not in material else "球墨铸铁代理价"
        return {"price_type": "material", "price_source": source, "unit_price": unit, "base_total": unit * ext_weight, "source_url": "", "source_date": "", "source_note": "proxy"}
    if any(token in material for token in ["6063-T6", "6063-T5", "6061-T6", "6061", "6060-T6", "6060"]):
        q = material_quote(snapshot, "al_a00")
        return {**q, "base_total": q["unit_price"] * ext_weight}
    if any(token in material for token in ["ADC12", "A356-T6", "A356", "ZL101", "ZL101+T6", "ZL101+FKM", "压铸铝", "铸造铝"]):
        q = material_quote(snapshot, "a3562")
        return {**q, "base_total": q["unit_price"] * ext_weight}
    if material in {"5052+HNBR"}:
        q = material_quote(snapshot, "al_a00")
        return {**q, "base_total": q["unit_price"] * ext_weight}
    if material in {"\u7d2b\u94dc", "T2"}:
        q = material_quote(snapshot, "copper_1")
        return {**q, "base_total": q["unit_price"] * ext_weight}
    if contains_any(material, ["\u6f06\u5305\u7ebf", "\u94dc"]):
        q = material_quote(snapshot, "enameled_wire")
        return {**q, "base_total": q["unit_price"] * ext_weight}
    if material in {"40UH", "48UH"} or material.endswith("UH") or contains_any(material, ["\u94dd\u94c1\u787c"]):
        nm = material.upper()
        if "48UH" in nm:
            unit, source_name = 348.0, "\u94dd\u94c1\u787c48UH\u6bdb\u576f\u4ee3\u7406\u4ef7"
        elif "40UH" in nm:
            unit, source_name = 328.0, "\u94dd\u94c1\u787c40UH\u6bdb\u576f\u4ee3\u7406\u4ef7"
        elif nm.endswith("UH") or "UH" in nm:
            unit, source_name = 338.0, "\u94dd\u94c1\u787cUH\u6bdb\u576f\u4ee3\u7406\u4ef7"
        else:
            unit, source_name = 298.0, "\u94dd\u94c1\u787c\u6bdb\u576f\u4ee3\u7406\u4ef7"
        return {"price_type": "material", "price_source": source_name, "unit_price": unit, "base_total": unit * ext_weight, "source_url": "", "source_date": "", "source_note": "proxy"}
    if contains_any(material, ["PA66", "PPS", "GF"]):
        unit = 30.0
        return {"price_type": "material", "price_source": "\u6811\u8102\u6750\u6599\u4ee3\u7406\u4ef7", "unit_price": unit, "base_total": unit * ext_weight, "source_url": "", "source_date": "", "source_note": "proxy"}
    if material == "12Cr17Mn6Ni5N":
        unit = 13.75
        return {"price_type": "material", "price_source": "304/2B\u4ee3\u7406", "unit_price": unit, "base_total": unit * ext_weight, "source_url": "", "source_date": "", "source_note": "proxy"}
    return {"price_type": "material" if material else "unmapped", "price_source": "\u672a\u6620\u5c04", "unit_price": 0.0, "base_total": 0.0, "source_url": "", "source_date": "", "source_note": "none"}


def choose_machine_complexity(row: dict) -> tuple[str, float]:
    item = row["item"]
    material = row["material"]
    weight = row["ext_weight_kg"]
    if contains_any(item, ["\u7535\u673a\u8f74", "\u8f6c\u8f74"]) or material == "20CrMnTi":
        return "\u590d\u6742", 120.0
    if weight >= 1.0 or contains_any(item, ["\u7aef\u76d6", "\u673a\u5ea7", "\u673a\u58f3"]):
        return "\u4e2d\u7b49", 30.0
    return "\u7b80\u5355", 20.0


def estimate_stator_bundle(row: dict, context_rows: list[dict]) -> tuple[str, float, float]:
    copper_rows = [s for s in context_rows if s["code"] != row["code"] and contains_any(s["material"], KW_STATOR_MATERIAL)]
    stator_rows = [s for s in context_rows if s["code"] != row["code"] and contains_any(s["item"], ["\u5b9a\u5b50", "\u9aa8\u67b6", "\u94c1\u82af"])]
    silicon_rows = [s for s in stator_rows if contains_any(s["material"], ["35W", "\u7845\u94a2", "\u94c1\u82af", "B30AHV"])]

    if is_stator_winding_component(row):
        stator_rows = [row] + stator_rows
        if contains_any(str(row.get("material", "") or ""), KW_STATOR_MATERIAL):
            copper_rows = [row] + copper_rows

    copper_ext_weight = sum(s["ext_weight_kg"] for s in copper_rows)
    copper_base_total = sum(s.get("base_total", 0.0) for s in copper_rows)
    stator_ext_weight = sum(s["ext_weight_kg"] for s in stator_rows)
    silicon_ext_weight = sum(s["ext_weight_kg"] for s in silicon_rows)
    silicon_correction = max(0.0, (9.50 - 5.05) * silicon_ext_weight)
    winding_embedding = copper_ext_weight * 85.0
    auxiliaries = copper_base_total * 0.10 + stator_ext_weight * 6.0
    assembly_test_fixed = 80.0 if copper_ext_weight > 0 else 120.0
    total = silicon_correction + winding_embedding + auxiliaries + assembly_test_fixed
    return ("\u5b9a\u5b50\u6210\u54c1\u5de5\u5e8f\u5305", 1.0, total)


def normalize_process_label(process: str, item: str, material: str, spec: str) -> str:
    normalized = (process or "").strip()
    row_like = {"item": item, "material": material, "spec": spec, "process": normalized}
    if is_stator_winding_component(row_like):
        return "\u5b9a\u5b50\u6210\u54c1\u5de5\u5e8f\u5305"
    if is_stator_core_component(row_like):
        return "\u51b2\u538b\u53e0\u538b"
    if contains_any(normalized, KW_STACKING):
        return "\u51b2\u538b\u53e0\u538b"
    if contains_any(normalized, ["\u51b2\u538b", "\u6298\u5f2f"]) and (("\u3001" in normalized) or ("+" in normalized)):
        return "\u51b2\u538b\u3001\u6298\u5f2f\u7b49"
    return normalized


def price_process(row: dict, context_rows: list[dict]) -> dict:
    item = row["item"]
    material = row["material"]
    spec = str(row.get("spec") or "")
    process = normalize_process_label(row["process"], item, material, spec)
    qty = row["qty"]
    ext_weight = row["ext_weight_kg"]
    if not process:
        stator_bundle_seed = contains_any(item, KW_STATOR) and (contains_any(spec, KW_STATOR_SPEC) or contains_any(material, KW_STATOR_MATERIAL))
        if stator_bundle_seed:
            _, _, total = estimate_stator_bundle(row, context_rows)
            return {"complexity": "\u6210\u54c1\u53e3\u5f84", "process_unit_label": "\u5b9a\u5b50\u6210\u54c1\u5de5\u5e8f\u5305", "process_total": total, "process_note": "\u5b9a\u5b50\u6210\u54c1\u5de5\u5e8f\u6253\u5305\u4f30\u7b97"}
        if contains_any(item, ["\u6c38\u78c1\u4f53"]) or contains_any(material, ["\u94dd\u94c1\u787c", "UH"]):
            unit = 20.40
            return {"complexity": "", "process_unit_label": "20.40 \u5143/kg", "process_total": ext_weight * unit, "process_note": "\u78c1\u6750\u70e7\u7ed3\u516c\u65a4\u4ef7"}
        return {"complexity": "", "process_unit_label": "", "process_total": 0.0, "process_note": ""}
    if process == "\u5b9a\u5b50\u6210\u54c1\u5de5\u5e8f\u5305":
        _, _, total = estimate_stator_bundle(row, context_rows)
        return {"complexity": "\u6210\u54c1\u53e3\u5f84", "process_unit_label": "\u5b9a\u5b50\u6210\u54c1\u5de5\u5e8f\u5305", "process_total": total, "process_note": "\u5b9a\u5b50\u6210\u54c1\u5de5\u5e8f\u6253\u5305\u4f30\u7b97"}
    if process == "\u51b2\u538b\u53e0\u538b":
        unit = 6.50
        return {"complexity": "\u4e2d\u7b49", "process_unit_label": "6.50 \u5143/kg", "process_total": ext_weight * unit, "process_note": "\u51b2\u538b\u53e0\u538b\u94c1\u82af\u5de5\u827a\u8d39"}
    if contains_any(process, KW_CASTING):
        unit = 8.0
        return {"complexity": "\u4e2d\u7b49", "process_unit_label": "8.00 \u5143/kg", "process_total": ext_weight * unit, "process_note": "\u538b\u94f8\u5de5\u827a\u8d39"}
    if contains_any(process, KW_INJECTION):
        unit = 8.0
        return {"complexity": "\u7b80\u5355", "process_unit_label": "8.00 \u5143/\u4ef6", "process_total": qty * unit, "process_note": "\u6ce8\u5851\u5de5\u827a\u8d39"}
    if contains_any(process, KW_COLD):
        unit = 0.8
        return {"complexity": "\u7b80\u5355", "process_unit_label": "0.80 \u5143/\u4ef6", "process_total": qty * unit, "process_note": "\u51b7\u9566\u5de5\u827a\u8d39"}
    if contains_any(process, KW_SINTER):
        unit = 20.40
        return {"complexity": "\u4e2d\u7b49", "process_unit_label": "20.40 \u5143/kg", "process_total": ext_weight * unit, "process_note": "\u70e7\u7ed3\u5de5\u827a\u8d39"}
    if contains_any(process, KW_MACHINE):
        complexity, unit = choose_machine_complexity(row)
        return {"complexity": complexity, "process_unit_label": f"{fmt_num(unit)} \u5143/kg", "process_total": ext_weight * unit, "process_note": "\u673a\u52a0\u5de5\u5de5\u827a\u8d39"}
    if contains_any(process, KW_SHEET_METAL):
        unit = 6.50
        return {"complexity": "\u4e2d\u7b49", "process_unit_label": "6.50 \u5143/kg", "process_total": ext_weight * unit, "process_note": "\u677f\u91d1\u5de5\u827a\u8d39"}
    if contains_any(process, KW_WELD):
        unit = 12.0
        return {"complexity": "\u4e2d\u7b49", "process_unit_label": "12.00 \u5143/kg", "process_total": ext_weight * unit, "process_note": "\u710a\u63a5\u5de5\u827a\u8d39"}
    if contains_any(process, KW_FINISHING):
        unit = 10.0
        return {"complexity": "\u4e2d\u7b49", "process_unit_label": "10.00 \u5143/kg", "process_total": ext_weight * unit, "process_note": "\u88c5\u914d/\u7edd\u7f18/\u6d78\u6f06\u5de5\u827a\u8d39"}
    return {"complexity": "", "process_unit_label": "", "process_total": 0.0, "process_note": "\u672a\u547d\u4e2d\u5de5\u827a\u89c4\u5219"}


def build_context_map(rows: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get("product", "")].append(row)
    return grouped


def price_rows(rows: list[dict], snapshot: dict) -> list[dict]:
    context_map = build_context_map(rows)
    priced = []
    for row in rows:
        material_info = map_material(row, snapshot)
        process_info = price_process({**row, "base_total": material_info.get("base_total", 0.0)}, context_map.get(row.get("product", ""), rows))
        purchase_total = row.get("current_purchase_total") or 0.0
        line_total = material_info.get("base_total", 0.0) + process_info.get("process_total", 0.0)
        priced.append({
            **row,
            **material_info,
            **process_info,
            "base_unit_price": (material_info.get("base_total", 0.0) / row["qty"]) if row["qty"] > 0 else material_info.get("base_total", 0.0),
            "line_total": line_total,
            "purchase_total": purchase_total,
        })
    return priced


def build_grouped_rows(priced_rows: list[dict]) -> list[dict]:
    grouped = {}
    order = []
    for row in priced_rows:
        code = row.get("code", "")
        if code not in grouped:
            grouped[code] = {Z_PRODUCT: row.get("product", ""), Z_ITEM: row.get("item", ""), Z_CODE: code, "\u57fa\u7840\u4f30\u7b97\u603b\u4ef7": 0.0, "\u57fa\u7840\u6750\u6599\u5408\u8ba1": 0.0, "\u57fa\u7840\u5de5\u827a\u5408\u8ba1": 0.0, "\u603b\u91cd\u91cfkg": 0.0, Z_EXT_WEIGHT: 0.0, Z_PURCHASE_TOTAL: row.get("purchase_total", 0.0), "\u4e3b\u8981\u6750\u8d28/\u5de5\u827a\u660e\u7ec6": []}
            order.append(code)
        g = grouped[code]
        g["\u57fa\u7840\u4f30\u7b97\u603b\u4ef7"] += row.get("line_total", 0.0)
        g["\u57fa\u7840\u6750\u6599\u5408\u8ba1"] += row.get("base_total", 0.0)
        g["\u57fa\u7840\u5de5\u827a\u5408\u8ba1"] += row.get("process_total", 0.0)
        g["\u603b\u91cd\u91cfkg"] += row.get("weight_kg", 0.0)
        g[Z_EXT_WEIGHT] += row.get("ext_weight_kg", 0.0)
        mat = row.get("material", "") or "\u672a\u8bc6\u522b"
        pro = row.get("process", "") or "\u65e0\u5de5\u827a"
        g["\u4e3b\u8981\u6750\u8d28/\u5de5\u827a\u660e\u7ec6"].append(f"{mat} / {pro}")
    result = []
    for code in order:
        g = grouped[code]
        seen = []
        for text in g["\u4e3b\u8981\u6750\u8d28/\u5de5\u827a\u660e\u7ec6"]:
            if text not in seen:
                seen.append(text)
        g["\u4e3b\u8981\u6750\u8d28/\u5de5\u827a\u660e\u7ec6"] = "\uff1b".join(seen)
        result.append(g)
    return result


def write_line_csv(path: Path, priced_rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(OUTPUT_HEADER)
        for row in priced_rows:
            writer.writerow([
                row.get("product", ""), row.get("item", ""), row.get("code", ""), row.get("material", ""), row.get("process", ""),
                fmt_num(row.get("qty", 0.0)), fmt_num(row.get("weight_kg", 0.0)), fmt_num(row.get("ext_weight_kg", 0.0)),
                row.get("price_type", ""), row.get("price_source", ""), fmt_num(row.get("base_unit_price", 0.0)), fmt_num(row.get("base_total", 0.0)),
                row.get("complexity", ""), row.get("process_unit_label", ""), fmt_num(row.get("process_total", 0.0)), fmt_num(row.get("line_total", 0.0)), fmt_num(row.get("purchase_total", 0.0)),
            ])


def write_grouped_csv(path: Path, grouped_rows: list[dict]) -> None:
    header = [Z_PRODUCT, Z_ITEM, Z_CODE, "\u57fa\u7840\u4f30\u7b97\u603b\u4ef7", "\u57fa\u7840\u6750\u6599\u5408\u8ba1", "\u57fa\u7840\u5de5\u827a\u5408\u8ba1", "\u603b\u91cd\u91cfkg", Z_EXT_WEIGHT, Z_PURCHASE_TOTAL, "\u4e3b\u8981\u6750\u8d28/\u5de5\u827a\u660e\u7ec6"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for row in grouped_rows:
            writer.writerow({
                **row,
                "\u57fa\u7840\u4f30\u7b97\u603b\u4ef7": fmt_num(row.get("\u57fa\u7840\u4f30\u7b97\u603b\u4ef7", 0.0)),
                "\u57fa\u7840\u6750\u6599\u5408\u8ba1": fmt_num(row.get("\u57fa\u7840\u6750\u6599\u5408\u8ba1", 0.0)),
                "\u57fa\u7840\u5de5\u827a\u5408\u8ba1": fmt_num(row.get("\u57fa\u7840\u5de5\u827a\u5408\u8ba1", 0.0)),
                "\u603b\u91cd\u91cfkg": fmt_num(row.get("\u603b\u91cd\u91cfkg", 0.0)),
                Z_EXT_WEIGHT: fmt_num(row.get(Z_EXT_WEIGHT, 0.0)),
                Z_PURCHASE_TOTAL: fmt_num(row.get(Z_PURCHASE_TOTAL, 0.0)),
            })


def write_summary_md(path: Path, grouped_rows: list[dict], snapshot: dict) -> None:
    total_estimate = sum(row.get("\u57fa\u7840\u4f30\u7b97\u603b\u4ef7", 0.0) for row in grouped_rows)
    total_material = sum(row.get("\u57fa\u7840\u6750\u6599\u5408\u8ba1", 0.0) for row in grouped_rows)
    total_process = sum(row.get("\u57fa\u7840\u5de5\u827a\u5408\u8ba1", 0.0) for row in grouped_rows)
    lines = [
        "## \u4f30\u4ef7\u6458\u8981",
        f"- \u4f30\u4ef7\u603b\u989d\uff1a{fmt_num(total_estimate)} \u5143",
        f"- \u6750\u6599\u5408\u8ba1\uff1a{fmt_num(total_material)} \u5143",
        f"- \u5de5\u827a\u5408\u8ba1\uff1a{fmt_num(total_process)} \u5143",
        "",
        "## \u5e02\u573a\u5feb\u7167",
    ]
    for value in snapshot.values():
        lines.append(f"- {value['source_name']}\uff1a{fmt_num(value['unit_price_per_kg'])} \u5143/kg")
    lines.extend(["", "## \u89c4\u5219\u8bf4\u660e", "- \u7535\u673a/\u7535\u63a7\u914d\u4ef6\u4f18\u5148\u6309 skills \u89c4\u5219\u6620\u5c04\u6750\u8d28\u4e0e\u5de5\u827a\u3002", "- AI \u9ad8\u7f6e\u4fe1\u5ea6\u9884\u63a8\u65ad\u7ed3\u679c\u4f1a\u5148\u56de\u586b\u5230 skills \u8f93\u5165\u518d\u8ba1\u4ef7\u3002"])
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def write_market_snapshot(path: Path, snapshot: dict) -> None:
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Price BOM workbook with skill rules")
    parser.add_argument("xlsx_path")
    parser.add_argument("--sheet")
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--output-grouped-csv", required=True)
    parser.add_argument("--output-summary-md", required=True)
    parser.add_argument("--output-market-snapshot", required=True)
    parser.add_argument("--fallback-product", default="BOM\u62a5\u4ef7")
    args = parser.parse_args()
    extracted = extract_sheet_rows(Path(args.xlsx_path), args.sheet)
    rows = normalize_rows(extracted, args.fallback_product)
    snapshot = fetch_live_market_snapshot()
    priced_rows = price_rows(rows, snapshot)
    grouped_rows = build_grouped_rows(priced_rows)
    write_line_csv(Path(args.output_csv), priced_rows)
    write_grouped_csv(Path(args.output_grouped_csv), grouped_rows)
    write_summary_md(Path(args.output_summary_md), grouped_rows, snapshot)
    write_market_snapshot(Path(args.output_market_snapshot), snapshot)


if __name__ == "__main__":
    main()
