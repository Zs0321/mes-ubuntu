#!/usr/bin/env python3
import argparse
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
DOCREL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def col_to_num(col: str) -> int:
    n = 0
    for c in col:
        n = n * 26 + (ord(c) - 64)
    return n


def parse_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(t.text or "" for t in si.iter(f"{{{NS['main']}}}t"))
        for si in root.findall("main:si", NS)
    ]


def workbook_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {r.attrib["Id"]: r.attrib["Target"] for r in rels.findall("rel:Relationship", NS)}
    out = []
    for s in wb.find("main:sheets", NS):
        rid = s.attrib[f"{{{DOCREL}}}id"]
        target = rel_map[rid].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        out.append((s.attrib["name"], target))
    return out


def cell_value(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value = cell.find("main:v", NS)
    if cell_type == "s" and value is not None:
        return shared[int(value.text)]
    if cell_type == "inlineStr":
        inline = cell.find("main:is", NS)
        if inline is None:
            return ""
        return "".join(t.text or "" for t in inline.iter(f"{{{NS['main']}}}t"))
    return value.text if value is not None else ""


def extract_sheet_rows(path: Path, sheet_name: str | None) -> dict:
    with zipfile.ZipFile(path) as zf:
        shared = parse_shared_strings(zf)
        sheets = workbook_sheets(zf)
        if not sheets:
            raise ValueError("No sheets found in workbook")
        if sheet_name is None:
            name, target = sheets[0]
        else:
            matches = [s for s in sheets if s[0] == sheet_name]
            if not matches:
                raise ValueError(f"Sheet not found: {sheet_name}")
            name, target = matches[0]

        root = ET.fromstring(zf.read(target))
        data = root.find("main:sheetData", NS)
        rows = []
        max_col = 0
        for row in data.findall("main:row", NS):
            row_vals = {}
            for cell in row.findall("main:c", NS):
                match = re.match(r"([A-Z]+)(\d+)", cell.attrib.get("r", ""))
                if not match:
                    continue
                col = col_to_num(match.group(1))
                max_col = max(max_col, col)
                row_vals[col] = cell_value(cell, shared)
            if row_vals:
                rows.append([row_vals.get(i, "") for i in range(1, max_col + 1)])
        header = rows[0] if rows else []
        body = rows[1:] if len(rows) > 1 else []
        return {"sheet": name, "header": header, "rows": body, "row_count": len(body)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract rows from a BOM .xlsx file without openpyxl.")
    parser.add_argument("xlsx_path", help="Path to the .xlsx file")
    parser.add_argument("--sheet", help="Sheet name to extract; defaults to the first sheet")
    args = parser.parse_args()
    result = extract_sheet_rows(Path(args.xlsx_path), args.sheet)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


