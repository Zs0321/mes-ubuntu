from __future__ import annotations

import copy
import csv
import io
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from openpyxl import Workbook

from backend.config import AppConfig
from backend.services.ai_route_quote_service import AIRouteQuoteService
from backend.services.kingdee_service import KingdeeService


class FinanceSkillQuoteService:
    SOURCE_NAME = "changjiang-bom-pricing"
    DEFAULT_TAX_RATE = 0.13
    INFERENCE_CONFIDENCE_THRESHOLD = AIRouteQuoteService.INFERENCE_CONFIDENCE_THRESHOLD
    WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD = AIRouteQuoteService.WEIGHT_INFERENCE_CONFIDENCE_THRESHOLD
    DEFAULT_NAME_SPEC_PRICE_BANDS = (
        {"category": "轴承", "keywords": ("轴承",), "low": 20.0, "high": 80.0, "basis": "电机常用轴承单件区间"},
        {"category": "油泵", "keywords": ("油泵",), "low": 250.0, "high": 950.0, "basis": "电机辅件油泵单件区间"},
        {"category": "换热器", "keywords": ("换热器",), "low": 180.0, "high": 700.0, "basis": "电机/电控散热换热件单件区间"},
        {"category": "过滤器", "keywords": ("过滤器", "滤芯"), "low": 15.0, "high": 80.0, "basis": "电机辅件过滤件单件区间"},
        {"category": "导电环", "keywords": ("导电环",), "low": 45.0, "high": 120.0, "basis": "电机导电环/滑环类单件区间"},
        {"category": "连接器", "keywords": ("连接器", "插头", "插座"), "low": 20.0, "high": 80.0, "basis": "电控连接器件单件区间"},
        {"category": "接线组件", "keywords": ("接线座组件", "接线盒组件", "端子座组件", "接线座", "接线盒", "端子座"), "low": 120.0, "high": 900.0, "basis": "电机接线组件/端子座组件单件区间"},
        {"category": "密封件", "keywords": ("密封圈", "双唇密封圈", "油封", "密封垫", "o型圈", "O型圈"), "low": 2.0, "high": 20.0, "basis": "电机常用密封件单件区间"},
        {"category": "透气阀", "keywords": ("透气阀", "防水透气阀"), "low": 10.0, "high": 60.0, "basis": "电机防水透气阀单件区间"},
        {"category": "线束", "keywords": ("线束",), "low": 18.0, "high": 120.0, "basis": "电机/电控线束单件区间"},
        {"category": "弹簧", "keywords": ("波形弹簧", "弹簧"), "low": 8.0, "high": 35.0, "basis": "电机弹簧件单件区间"},
    )
    DEFAULT_NAME_SPEC_WEIGHT_BANDS = (
        {"category": "轴承", "keywords": ("轴承",), "low": 0.08, "high": 1.8, "default": 0.35, "basis": "电机常用轴承单件重量区间"},
        {"category": "油泵", "keywords": ("油泵",), "low": 0.8, "high": 6.5, "default": 2.2, "basis": "电机辅件油泵单件重量区间"},
        {"category": "换热器", "keywords": ("换热器",), "low": 0.5, "high": 8.0, "default": 2.8, "basis": "电机/电控散热换热件单件重量区间"},
        {"category": "过滤器", "keywords": ("过滤器", "滤芯"), "low": 0.03, "high": 1.5, "default": 0.18, "basis": "电机辅件过滤件单件重量区间"},
        {"category": "导电环", "keywords": ("导电环",), "low": 0.08, "high": 1.2, "default": 0.25, "basis": "电机导电环/滑环类单件重量区间"},
        {"category": "连接器", "keywords": ("连接器", "插头", "插座"), "low": 0.02, "high": 0.8, "default": 0.12, "basis": "电控连接器件单件重量区间"},
        {"category": "接线组件", "keywords": ("接线座组件", "接线盒组件", "端子座组件", "接线座", "接线盒", "端子座"), "low": 0.3, "high": 3.0, "default": 1.2, "basis": "电机接线组件/端子座组件单件重量区间"},
        {"category": "密封件", "keywords": ("密封圈", "双唇密封圈", "油封", "密封垫", "o型圈", "O型圈"), "low": 0.002, "high": 0.12, "default": 0.02, "basis": "电机常用密封件单件重量区间"},
        {"category": "透气阀", "keywords": ("透气阀", "防水透气阀"), "low": 0.005, "high": 0.08, "default": 0.02, "basis": "电机防水透气阀单件重量区间"},
        {"category": "线束", "keywords": ("线束",), "low": 0.05, "high": 3.5, "default": 0.45, "basis": "电机/电控线束单件重量区间"},
        {"category": "弹簧", "keywords": ("波形弹簧", "弹簧"), "low": 0.01, "high": 0.25, "default": 0.06, "basis": "电机弹簧件单件重量区间"},
        {"category": "法兰", "keywords": ("法兰", "轴法兰"), "low": 0.08, "high": 3.0, "default": 0.45, "basis": "电机连接法兰/轴法兰单件重量区间"},
        {"category": "电机转子挡板", "keywords": ("转子挡板",), "low": 0.08, "high": 0.8, "default": 0.22, "basis": "电机转子挡板/挡片类铝件单件重量区间"},
        {"category": "电机轴套", "keywords": ("轴套", "转子轴套"), "low": 0.05, "high": 0.6, "default": 0.18, "basis": "电机轴套/衬套类单件重量区间"},
        {"category": "电机压盖", "keywords": ("压盖", "轴承压盖"), "low": 0.05, "high": 0.8, "default": 0.2, "basis": "电机压盖类零件单件重量区间"},
        {"category": "电机盖板", "keywords": ("盖板", "上盖板", "后盖板", "三相盖板"), "low": 0.05, "high": 1.2, "default": 0.28, "basis": "电机盖板类零件单件重量区间"},
        {"category": "电机接线板", "keywords": ("接线板", "端子板"), "low": 0.05, "high": 0.6, "default": 0.18, "basis": "电机接线板/端子板单件重量区间"},
        {"category": "电机连接器件", "keywords": ("连接器", "插件保护罩", "端子", "格兰头", "堵头"), "low": 0.01, "high": 0.3, "default": 0.06, "basis": "电机连接器/保护件单件重量区间"},
        {"category": "堵头", "keywords": ("堵头", "橡胶堵头"), "low": 0.01, "high": 0.3, "default": 0.05, "basis": "电机堵头/护塞单件重量区间"},
        {"category": "紧固件", "keywords": ("内六角", "螺母", "螺钉", "螺栓", "螺杆"), "low": 0.003, "high": 0.15, "default": 0.02, "basis": "电机常用紧固件单件重量区间"},
    )

    PRECISION_SHAFT_NAME_KEYWORDS = ("电机轴", "主轴", "转轴", "输出轴", "输入轴", "花键轴", "轴类", "传动轴", "轴")
    PRECISION_SHAFT_EXCLUDE_KEYWORDS = ("轴承", "轴套", "轴瓦")
    PRECISION_SHAFT_MATERIAL_KEYWORDS = ("20crmntih", "20crmnti", "42crmo", "40cr", "20cr")
    PRECISION_SHAFT_HEAT_TREATMENT_KEYWORDS = ("渗碳淬火", "渗碳", "淬火", "热处理", "高频淬火")
    PRECISION_SHAFT_GRINDING_KEYWORDS = ("磨削", "精磨", "外圆磨", "内圆磨", "磨齿")
    PRECISION_SHAFT_SPLINE_KEYWORDS = ("花键", "键槽", "键宽", "键深")
    PRECISION_SHAFT_PROCESS_KEYWORDS = ("机加工", "粗车", "精车", "车削", "磨削", "铣削", "滚齿", "插齿")
    PRECISION_SHAFT_LENGTH_PATTERN = re.compile(r"(?:^|[^0-9a-z])l\s*[:=?]?\s*(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)
    PRECISION_SHAFT_ANY_LENGTH_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)

    PRECISION_END_COVER_NAME_KEYWORDS = ("前端盖", "后端盖", "端盖")
    PRECISION_END_COVER_EXCLUDE_KEYWORDS = ("盖板", "端子盖", "接线盒盖", "接线盖")
    PRECISION_END_COVER_MATERIAL_KEYWORDS = ("a356-t6", "a356t6", "a356", "铝合金", "铝")
    PRECISION_END_COVER_CASTING_KEYWORDS = ("高压铸造", "低压铸造", "压铸", "铸造", "hpdc", "lpdc")
    PRECISION_END_COVER_CNC_KEYWORDS = ("cnc", "机加工", "精加工", "轴承位", "轴承室", "止口", "安装面", "螺纹孔")
    PRECISION_END_COVER_SEALING_KEYWORDS = ("密封", "密封槽", "气密", "喷涂", "阳极氧化", "极化")
    PRECISION_END_COVER_DIAMETER_PATTERN = re.compile(r"(?:[o0]?d)\s*(\d+(?:\.\d+)?)(?:\s*mm)?", re.IGNORECASE)
    PRECISION_END_COVER_SUFFIX_DIAMETER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)(?:\s*mm)?\s*外径", re.IGNORECASE)

    PRECISION_HOUSING_NAME_KEYWORDS = ("\u673a\u58f3", "\u5916\u58f3", "\u58f3\u4f53")
    PRECISION_HOUSING_EXCLUDE_KEYWORDS = ("\u63a5\u7ebf\u76d2", "\u63a5\u7ebf\u76d2\u76d6", "\u7aef\u76d6", "\u76d6\u677f")
    PRECISION_HOUSING_MATERIAL_KEYWORDS = ("6063-t5", "6063t5", "6063", "6061", "\u94dd\u5408\u91d1", "\u94dd")
    PRECISION_HOUSING_FORMING_KEYWORDS = ("\u62c9\u4f38", "\u6324\u538b", "\u578b\u6750")
    PRECISION_HOUSING_CNC_KEYWORDS = ("cnc", "\u673a\u52a0\u5de5", "\u673a\u68b0\u52a0\u5de5", "\u540e\u7eed\u673a\u68b0\u52a0\u5de5", "\u7cbe\u52a0\u5de5", "\u7aef\u9762", "\u6570\u63a7\u8f66\u524a", "\u8f66\u524a", "\u7cbe\u8f66", "\u7cbe\u8f66\u52a0\u5de5", "\u8f66\u52a0\u5de5", "\u5207\u65ad", "\u94bb\u5b54", "\u653b\u4e1d", "\u94bb\u5b54\u653b\u4e1d", "\u87ba\u7eb9")
    PRECISION_HOUSING_BEARING_KEYWORDS = ("\u8f74\u627f\u5ba4", "\u8f74\u627f\u4f4d", "\u6b62\u53e3")
    PRECISION_HOUSING_SURFACE_KEYWORDS = ("\u9633\u6781\u6c27\u5316", "\u55b7\u6d82", "\u8868\u9762\u5904\u7406", "\u6781\u5316", "\u55b7\u7c89")
    PRECISION_HOUSING_DIAMETER_PATTERN = re.compile(r"(?:[o0]?d)\s*(\d+(?:\.\d+)?)(?:\s*mm)?", re.IGNORECASE)
    PRECISION_HOUSING_SUFFIX_DIAMETER_PATTERN = re.compile(r"(\d+(?:\.\d+)?)(?:\s*mm)?\s*\u5916\u5f84", re.IGNORECASE)
    PRECISION_HOUSING_LENGTH_PATTERN = re.compile(r"(?:^|[^0-9a-z])l\s*[:=?]?\s*(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)

    MOTOR_HARNESS_NAME_KEYWORDS = ("线束", "电缆总成", "引接线", "连接线", "线缆总成")
    MOTOR_HARNESS_PROCESS_KEYWORDS = ("压接", "端子", "剥皮", "护套", "热缩", "包扎", "装配", "铜鼻子")
    MOTOR_HARNESS_LENGTH_PATTERN = re.compile(r"(?:l\s*[:=]?\s*)?(\d+(?:\.\d+)?)\s*m(?!m)", re.IGNORECASE)
    MOTOR_HARNESS_LENGTH_MM_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*mm", re.IGNORECASE)
    MOTOR_HARNESS_LENGTH_CONTEXT_PATTERN = re.compile(r"(?:线长|长度|l\s*[:=]?)", re.IGNORECASE)
    MOTOR_HARNESS_CROSS_SECTION_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*mm\s*[²2]", re.IGNORECASE)
    MOTOR_HARNESS_BRANCH_PATTERN = re.compile(r"(\d+)\s*(?:分支|支路|支)")

    MOTOR_SHELL_NAME_KEYWORDS = ("接线盒", "接线盒体", "盖板", "后盖板", "三相盖板", "上盖板", "端子盖")
    MOTOR_SHELL_CASTING_KEYWORDS = ("压铸", "高压压铸", "低压铸造", "铸造", "铸件")
    MOTOR_SHELL_MACHINING_KEYWORDS = ("cnc", "机加工", "钻孔", "攻丝", "螺纹", "精加工")
    MOTOR_SHELL_SURFACE_KEYWORDS = ("喷涂", "喷粉", "表处", "表面处理", "阳极氧化")
    MOTOR_SHELL_BLANK_KEYWORDS = ("毛坯", "铸坯", "压铸毛坯", "未机加")
    MOTOR_SHELL_FINISHED_KEYWORDS = ("成品", "机加工", "钻孔", "攻丝", "喷涂", "喷粉", "表面处理")
    MOTOR_SHELL_DIAMETER_PATTERN = re.compile(r"(?:[o0]?d|外径)\s*(\d+(?:\.\d+)?)(?:\s*mm)?", re.IGNORECASE)
    MOTOR_SHELL_HOLE_PATTERN = re.compile(r"(\d+)\s*孔")


    def __init__(
        self,
        config: AppConfig | None = None,
        kingdee_service: KingdeeService | None = None,
        ai_route_service: AIRouteQuoteService | None = None,
        *,
        skill_root: Path | None = None,
    ):
        self.config = config
        self.skill_root = skill_root or Path(__file__).resolve().parents[3] / "changjiang-bom-pricing"
        self.name_spec_price_band_path = self.skill_root / "references" / "motor-accessory-price-bands.json"
        self.training_reference_path = Path(__file__).resolve().parents[1] / "data" / "liugong_motor_training_reference.json"
        self._training_reference_rows: list[dict] | None = None
        self.kingdee_service = kingdee_service or (KingdeeService(config.kingdee) if config else None)
        self.ai_route_service = ai_route_service or AIRouteQuoteService(skill_root=self.skill_root)

    def get_name_spec_price_bands(self) -> list[dict]:
        return self._load_name_spec_price_bands()

    def find_training_reference(self, item: dict | None) -> dict | None:
        normalized_code = self._normalize_training_key((item or {}).get("code"))
        normalized_name = self._normalize_training_key((item or {}).get("name"))
        normalized_spec = self._normalize_training_key((item or {}).get("spec"))
        normalized_name_spec = f"{normalized_name}||{normalized_spec}" if normalized_name or normalized_spec else ""
        candidates = self._load_training_reference_rows()
        if normalized_code:
            for row in candidates:
                if row.get("match_keys", {}).get("code") == normalized_code:
                    return dict(row)
        if normalized_name_spec:
            for row in candidates:
                if row.get("match_keys", {}).get("name_spec") == normalized_name_spec:
                    return dict(row)
        if normalized_name:
            named = [row for row in candidates if row.get("match_keys", {}).get("name") == normalized_name]
            if len(named) == 1:
                return dict(named[0])
        return None

    def _load_training_reference_rows(self) -> list[dict]:
        if self._training_reference_rows is None:
            if not self.training_reference_path.exists():
                self._training_reference_rows = []
            else:
                self._training_reference_rows = json.loads(self.training_reference_path.read_text(encoding="utf-8"))
        return list(self._training_reference_rows or [])

    @staticmethod
    def _normalize_training_key(value: object) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        return "".join(text.replace("（", "(").replace("）", ")").split())

    @classmethod
    def allocate_tax_inclusive_prices(cls, rows: list[dict], *, price_field: str, tax_rate: float | None = None) -> list[dict]:
        divisor = 1.0 + max(cls._to_number(tax_rate if tax_rate is not None else cls.DEFAULT_TAX_RATE), 0.0)
        allocated: list[dict] = []
        for row in rows:
            enriched = dict(row)
            qty = cls._to_number(enriched.get("qty")) or 1.0
            inclusive_unit = cls._to_number(enriched.get(price_field))
            if inclusive_unit <= 0 or divisor <= 0:
                enriched["tax_rate"] = max(divisor - 1.0, 0.0)
                enriched["tax_inclusive_unit_price"] = inclusive_unit
                enriched["tax_exclusive_unit_price"] = inclusive_unit
                enriched["tax_amount_unit_price"] = 0.0
                enriched["tax_inclusive_total_price"] = inclusive_unit * qty
                enriched["tax_exclusive_total_price"] = inclusive_unit * qty
                enriched["tax_amount_total_price"] = 0.0
                allocated.append(enriched)
                continue
            exclusive_total = round((inclusive_unit * qty) / divisor, 2)
            inclusive_total = round(inclusive_unit * qty, 2)
            tax_total = round(inclusive_total - exclusive_total, 2)
            exclusive_unit = round(exclusive_total / qty, 6) if qty > 0 else round(inclusive_unit / divisor, 6)
            tax_unit = round(inclusive_unit - exclusive_unit, 6)
            enriched["tax_rate"] = round(divisor - 1.0, 4)
            enriched["tax_inclusive_unit_price"] = round(inclusive_unit, 6)
            enriched["tax_exclusive_unit_price"] = exclusive_unit
            enriched["tax_amount_unit_price"] = tax_unit
            enriched["tax_inclusive_total_price"] = inclusive_total
            enriched["tax_exclusive_total_price"] = exclusive_total
            enriched["tax_amount_total_price"] = tax_total
            allocated.append(enriched)
        return allocated

    @classmethod
    def annotate_price_tax_breakdown(cls, rows: list[dict], *, price_field: str, prefix: str, tax_rate: float | None = None) -> list[dict]:
        for row, tax_row in zip(rows, cls.allocate_tax_inclusive_prices(rows, price_field=price_field, tax_rate=tax_rate)):
            row[f"{prefix}_tax_rate"] = tax_row["tax_rate"]
            row[f"{prefix}_tax_inclusive_unit_price"] = tax_row["tax_inclusive_unit_price"]
            row[f"{prefix}_tax_exclusive_unit_price"] = tax_row["tax_exclusive_unit_price"]
            row[f"{prefix}_tax_amount_unit_price"] = tax_row["tax_amount_unit_price"]
            row[f"{prefix}_tax_inclusive_total_price"] = tax_row["tax_inclusive_total_price"]
            row[f"{prefix}_tax_exclusive_total_price"] = tax_row["tax_exclusive_total_price"]
            row[f"{prefix}_tax_amount_total_price"] = tax_row["tax_amount_total_price"]
        return rows

    def save_name_spec_price_bands(self, rows: list[dict]) -> list[dict]:
        normalized = self._normalize_name_spec_price_bands(rows)
        self.name_spec_price_band_path.parent.mkdir(parents=True, exist_ok=True)
        self.name_spec_price_band_path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return normalized

    def quote_items(
        self,
        items: list[dict],
        *,
        model: dict | None = None,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        if not items:
            raise ValueError("请先提供 BOM 条目")

        model = dict(model or {})
        production_mode = self._normalize_production_mode(model.get("production_mode"))
        annual_volume = self._to_int(model.get("annual_volume"))
        model["production_mode"] = production_mode
        model["annual_volume"] = annual_volume

        normalized_items = self._prepare_items(items)
        purchase_refs = self._fetch_purchase_refs([item.get("code", "") for item in normalized_items])
        for item in normalized_items:
            purchase = purchase_refs.get(item.get("code", ""), {})
            if purchase:
                item["kingdee_reference_price"] = self._to_number(purchase.get("price"))
                item["kingdee_reference_tax_price"] = self._to_number(purchase.get("tax_price"))
                item["kingdee_supplier_name"] = purchase.get("supplier_name", "")
                item["kingdee_reference_date"] = purchase.get("date", "")
                if not item.get("vendor"):
                    item["vendor"] = purchase.get("supplier_name", "")

        runtime_items, display_source_items = self._prepare_ai_staged_skill_items(
            normalized_items,
            progress_callback=progress_callback,
            production_mode=production_mode,
            annual_volume=annual_volume,
        )
        display_items = self._merge_composite_items(display_source_items)
        runtime_display_items = self._merge_composite_items(runtime_items)

        script_plan = self._plan_skill_scripts(
            normalized_items,
            production_mode=production_mode,
            annual_volume=annual_volume,
        )
        selected_scripts = set(script_plan.get("selected_scripts") or [])
        self._notify_progress(
            progress_callback,
            stage="preparing",
            processed=0,
            total=len(normalized_items),
            message="千问已生成本次 skills 脚本计划",
            production_mode=production_mode,
            annual_volume=annual_volume,
            script_plan=script_plan,
        )

        with tempfile.TemporaryDirectory(prefix="finance_skill_quote_") as temp_dir:
            workdir = Path(temp_dir)
            input_xlsx = self._write_skill_input_workbook(runtime_items, self._model_label(model), workdir / "input.xlsx")

            self._notify_progress(
                progress_callback,
                stage="market_pricing",
                processed=0,
                total=len(normalized_items),
                message="正在查询在线价格",
                production_mode=production_mode,
                annual_volume=annual_volume,
            )
            line_csv, grouped_csv, summary_md, snapshot_json = self._run_price_bom(input_xlsx, workdir)

            self._notify_progress(
                progress_callback,
                stage="rule_pricing",
                processed=len(display_items),
                total=len(display_items),
                message="正在执行规则报价计算",
                production_mode=production_mode,
                annual_volume=annual_volume,
                analysis_log_text=self._build_rule_pricing_log_text(
                    items=runtime_display_items,
                    line_csv=line_csv,
                    grouped_csv=grouped_csv,
                    script_plan=script_plan,
                    production_mode=production_mode,
                    annual_volume=annual_volume,
                ),
            )
            gap_csv = gap_xlsx = gap_md = None
            if "analyze_pricing_gaps.py" in selected_scripts:
                gap_csv, gap_xlsx, gap_md = self._run_gap_analysis(line_csv, workdir)

            formatted_xlsx = None
            if "format_estimate_workbook.py" in selected_scripts:
                formatted_xlsx = self._run_format_workbook(line_csv, grouped_csv, summary_md, workdir)

            volume_outputs = {}
            if "model_volume_pricing.py" in selected_scripts and production_mode == "mass" and annual_volume > 0:
                try:
                    volume_outputs = self._run_volume_pricing(line_csv, workdir, annual_volume)
                except RuntimeError as exc:
                    volume_outputs = {}
                    script_plan.setdefault("warnings", []).append(str(exc))
            ai_skill_context_map = self._build_ai_skill_context_map(
                items=runtime_display_items,
                line_csv=line_csv,
                grouped_csv=grouped_csv,
                snapshot_json=snapshot_json,
                volume_outputs=volume_outputs,
                production_mode=production_mode,
                annual_volume=annual_volume,
                script_plan=script_plan,
            )

            self._notify_progress(
                progress_callback,
                stage="ai_supplement",
                processed=0,
                total=len(display_items),
                message="正在整理 AI 报价所需 skills 知识与输入",
                production_mode=production_mode,
                annual_volume=annual_volume,
            )
            ai_results = self._estimate_ai_routes(
                runtime_display_items,
                progress_callback,
                production_mode,
                annual_volume,
                ai_skill_context_map,
            )

            self._notify_progress(
                progress_callback,
                stage="finalizing",
                processed=len(display_items),
                total=len(display_items),
                message="正在汇总导出",
                production_mode=production_mode,
                annual_volume=annual_volume,
            )
            payload = self._build_payload(
                items=display_items,
                model=model,
                ai_results=ai_results,
                line_csv=line_csv,
                grouped_csv=grouped_csv,
                gap_csv=gap_csv,
                gap_xlsx=gap_xlsx,
                gap_md=gap_md,
                formatted_xlsx=formatted_xlsx,
                snapshot_json=snapshot_json,
                volume_outputs=volume_outputs,
                script_plan=script_plan,
            )
            self._notify_progress(
                progress_callback,
                stage="finalizing",
                processed=len(display_items),
                total=len(display_items),
                message="正在汇总导出",
                production_mode=production_mode,
                annual_volume=annual_volume,
                analysis_log_text=str(payload.get("analysis_log_text") or "").strip(),
                script_plan=script_plan,
            )
            return payload

    def build_export_package(self, skill_outputs: dict) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            manifest: list[dict] = []
            for key, value in (skill_outputs or {}).items():
                path = Path(str(value))
                if not path.exists() or not path.is_file():
                    continue
                archive.write(path, arcname=path.name)
                manifest.append({"id": key, "filename": path.name})
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        buffer.seek(0)
        return buffer.getvalue()

    def _prepare_items(self, items: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for index, item in enumerate(items):
            training_hit = self.find_training_reference(item)
            material_text = str(item.get("material_original") or item.get("material") or training_hit.get("material") if training_hit else "").strip()
            if not material_text and training_hit:
                material_text = str(training_hit.get("material") or "").strip()
            material_alias = str(item.get("material_alias") or "").strip() or self._material_alias(material_text)
            raw_weight_kg = self._to_number(item.get("weight_kg"))
            if raw_weight_kg <= 0 and training_hit:
                raw_weight_kg = self._to_number(training_hit.get("weight_kg"))
            process_text = str(item.get("process") or item.get("process_original") or training_hit.get("process") if training_hit else "").strip()
            unit_price = self._to_number(item.get("current_unit_price"))
            if unit_price <= 0 and training_hit:
                unit_price = self._to_number(training_hit.get("current_unit_price"))
            loss = max(0.0, self._to_number(item.get("loss")))
            effective_weight_kg = raw_weight_kg * (1.0 + loss) if raw_weight_kg > 0 and loss > 0 else raw_weight_kg
            ct = max(0.0, self._to_number(item.get("ct")))
            rate = max(0.0, self._to_number(item.get("rate")))
            manual_process_unit = (ct / 60.0) * rate if ct > 0 and rate > 0 else 0.0
            extra = self._to_number(item.get("extra"))
            normalized.append({
                "source_row_order": index,
                "code": str(item.get("code") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "spec": str(item.get("spec") or "").strip(),
                "material": material_text,
                "material_original": material_text,
                "material_alias": material_alias,
                "weight_kg": raw_weight_kg,
                "effective_weight_kg": effective_weight_kg,
                "process": process_text,
                "process_original": str(item.get("process_original") or process_text).strip(),
                "process_inferred": bool(item.get("process_inferred")),
                "process_inference_note": str(item.get("process_inference_note") or ("柳工训练表回填" if training_hit and process_text else "")).strip(),
                "qty": self._to_number(item.get("qty")) or 1.0,
                "vendor": str(item.get("vendor") or "").strip(),
                "current_unit_price": unit_price,
                "target_unit_price": self._to_number(item.get("target_unit_price")),
                "material_price": self._to_number(item.get("material_price")),
                "extra": extra,
                "loss": loss,
                "ct": ct,
                "rate": rate,
                "manual_process_unit": manual_process_unit,
                "manual_extra_unit": extra,
                "manual_surcharge_unit": manual_process_unit + extra,
                "unit": str(item.get("unit") or "Pcs"),
                "component_materials": [material_text] if material_text else [],
                "component_specs": [str(item.get("spec") or "").strip()] if str(item.get("spec") or "").strip() else [],
                "component_processes": [process_text] if process_text else [],
                "training_reference_hit": bool(training_hit),
                "training_reference_product": str(training_hit.get("product") or "").strip() if training_hit else "",
                "training_reference_sheet": str(training_hit.get("sheet_name") or "").strip() if training_hit else "",
                "product_spec": str(item.get("product_spec") or item.get("product_context") or "").strip(),
                "product_context": str(item.get("product_context") or item.get("product_spec") or "").strip(),
            })
        return normalized

    def _prepare_ai_staged_skill_items(
        self,
        items: list[dict],
        *,
        progress_callback: Callable[[dict], None] | None,
        production_mode: str,
        annual_volume: int,
    ) -> tuple[list[dict], list[dict]]:
        runtime_items: list[dict] = []
        display_items: list[dict] = []
        total = len(items)
        completed = 0
        for item in items:
            display_item = dict(item)
            runtime_item = dict(item)
            runtime_item["production_mode"] = production_mode
            runtime_item["annual_volume"] = annual_volume
            runtime_item["ai_name_spec_fallback"] = self._is_name_based_ai_fallback_eligible(runtime_item)
            runtime_item["name_spec_price_band"] = self._resolve_name_spec_price_band(runtime_item)
            runtime_item["name_spec_weight_band"] = self._resolve_name_spec_weight_band(runtime_item)
            estimated_weight_kg, estimated_weight_note = self._estimate_similar_weight(runtime_item, items)
            estimated_weight_kg, estimated_weight_note = self._apply_name_spec_weight_band(
                runtime_item,
                estimated_weight_kg,
                estimated_weight_note,
            )
            if estimated_weight_kg > 0 and self._to_number(runtime_item.get("weight_kg")) <= 0:
                runtime_item["ai_estimated_weight_kg"] = estimated_weight_kg
                runtime_item["ai_estimated_weight_note"] = estimated_weight_note
                display_item["ai_estimated_weight_kg"] = estimated_weight_kg
                display_item["ai_estimated_weight_note"] = estimated_weight_note
            if self.ai_route_service.is_ready:
                staged = self.ai_route_service.prepare_staged_pricing_input(runtime_item)
                runtime_item = self._refresh_runtime_input_item(staged.get("pricing_item") or runtime_item)
                if staged.get("used"):
                    confidence = self._to_number(staged.get("confidence"))
                    process_guess = str(staged.get("process_guess") or "").strip()
                    material_guess = str(staged.get("material_guess") or "").strip()
                    inferred_weight_kg = self._to_number(staged.get("estimated_weight_kg"))
                    if process_guess:
                        display_item["ai_inferred_process_reference"] = process_guess
                        runtime_item["ai_inferred_process_reference"] = process_guess
                        display_item["process"] = process_guess
                    if material_guess:
                        display_item["ai_inferred_material_reference"] = material_guess
                        runtime_item["ai_inferred_material_reference"] = material_guess
                        display_item["material"] = material_guess
                        display_item["material_original"] = material_guess
                    if inferred_weight_kg > 0:
                        display_item["ai_inferred_weight_reference"] = inferred_weight_kg
                        runtime_item["ai_inferred_weight_reference"] = inferred_weight_kg
                        if self._to_number(display_item.get("weight_kg")) <= 0:
                            display_item["weight_kg"] = inferred_weight_kg
                            display_item["effective_weight_kg"] = inferred_weight_kg
                    display_item["ai_inference_confidence"] = confidence
                    runtime_item["ai_inference_confidence"] = confidence
                    display_item["ai_second_stage_used"] = True
                    runtime_item["ai_second_stage_used"] = True
                    display_item["ai_preinferred_for_skills"] = True
                    runtime_item["ai_preinferred_for_skills"] = True
            self._apply_skills_input_reference(display_item, runtime_item, source_item=item)
            runtime_items.append(runtime_item)
            display_items.append(display_item)
            completed += 1
            self._notify_progress(
                progress_callback,
                stage="ai_preinference",
                processed=completed,
                total=total,
                message=f"正在预处理 AI 报价输入项 {completed} / {total}",
                production_mode=production_mode,
                annual_volume=annual_volume,
            )
        return runtime_items, display_items

    @classmethod
    def _apply_skills_input_reference(cls, display_item: dict, runtime_item: dict, *, source_item: dict) -> None:
        process_value = str(runtime_item.get("process") or display_item.get("process") or source_item.get("process") or "").strip()
        material_value = cls._normalize_material_for_skills(
            runtime_item.get("material") or display_item.get("material") or source_item.get("material") or ""
        )
        weight_value = cls._to_number(
            runtime_item.get("weight_kg")
            or runtime_item.get("ai_inferred_weight_reference")
            or runtime_item.get("ai_estimated_weight_kg")
            or display_item.get("weight_kg")
            or source_item.get("weight_kg")
        )
        process_source = "原始BOM工艺"
        material_source = "原始BOM材质"
        weight_source = "原始BOM重量"
        if str(runtime_item.get("ai_inferred_process_reference") or "").strip():
            process_source = "AI高置信工艺覆盖原始工艺"
        elif str(runtime_item.get("process_inference_note") or "").strip():
            process_source = str(runtime_item.get("process_inference_note") or "").strip()
        if str(runtime_item.get("ai_inferred_material_reference") or "").strip():
            material_source = "AI高置信材质覆盖原始材质"
        if cls._to_number(source_item.get("weight_kg")) <= 0:
            if cls._to_number(runtime_item.get("ai_inferred_weight_reference")) > 0:
                weight_source = "AI高置信重量覆盖原始缺失重量"
            elif cls._to_number(runtime_item.get("ai_estimated_weight_kg")) > 0:
                weight_source = str(runtime_item.get("ai_estimated_weight_note") or "AI估重参与skills输入").strip()
        for target in (display_item, runtime_item):
            target["skills_input_process"] = process_value
            target["skills_input_material"] = material_value
            target["skills_input_weight_kg"] = weight_value
            target["skills_input_process_source"] = process_source
            target["skills_input_material_source"] = material_source
            target["skills_input_weight_source"] = weight_source

    def _refresh_runtime_input_item(self, item: dict) -> dict:
        refreshed = dict(item)
        material_text = str(refreshed.get("material") or refreshed.get("material_original") or "").strip()
        raw_weight_kg = self._to_number(refreshed.get("weight_kg"))
        loss = max(0.0, self._to_number(refreshed.get("loss")))
        refreshed["material"] = material_text
        refreshed["material_alias"] = str(refreshed.get("material_alias") or "").strip() or self._material_alias(material_text)
        refreshed["weight_kg"] = raw_weight_kg
        refreshed["effective_weight_kg"] = raw_weight_kg * (1.0 + loss) if raw_weight_kg > 0 and loss > 0 else raw_weight_kg
        refreshed["process"] = str(refreshed.get("process") or "").strip()
        return refreshed

    def _merge_composite_items(self, items: list[dict]) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        ordered_keys: list[str] = []
        for item in items:
            key = self._composite_group_key(item)
            if key not in grouped:
                grouped[key] = []
                ordered_keys.append(key)
            grouped[key].append(item)

        merged_items: list[dict] = []
        for key in ordered_keys:
            group = grouped.get(key) or []
            if not group:
                continue
            if not self._should_merge_composite_group(group):
                merged_items.extend(group)
                continue
            merged_items.append(self._merge_composite_group(group))

        merged_items.sort(key=lambda row: self._to_int(row.get("source_row_order")))
        return merged_items

    @staticmethod
    def _composite_group_key(item: dict) -> str:
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        if code and name:
            return f"{code}||{name}"
        return f"row::{FinanceSkillQuoteService._to_int(item.get('source_row_order'))}"

    @staticmethod
    def _join_unique_values(values: list[str], *, separator: str = " + ") -> str:
        ordered: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = str(raw or "").strip()
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            ordered.append(value)
        return separator.join(ordered)

    def _should_merge_composite_group(self, group: list[dict]) -> bool:
        if len(group) <= 1:
            return False
        materials = {
            str(item.get("material") or "").strip().lower()
            for item in group
            if str(item.get("material") or "").strip()
        }
        return len(materials) > 1

    def _merge_composite_group(self, group: list[dict]) -> dict:
        base = dict(sorted(group, key=lambda row: self._to_int(row.get("source_row_order")))[0])
        materials = [str(item.get("material") or "").strip() for item in group]
        specs = [str(item.get("spec") or "").strip() for item in group]
        processes = [str(item.get("process") or "").strip() for item in group if str(item.get("process") or "").strip()]
        aliases = [str(item.get("material_alias") or "").strip() for item in group if str(item.get("material_alias") or "").strip()]
        vendors = [str(item.get("vendor") or "").strip() for item in group if str(item.get("vendor") or "").strip()]
        qty_values = [self._to_number(item.get("qty")) or 1.0 for item in group]
        qty = qty_values[0] if qty_values else 1.0
        if any(abs(value - qty) > 1e-6 for value in qty_values[1:]):
            qty = max(qty_values)

        base["composite_component"] = True
        base["component_count"] = len(group)
        base["component_rows"] = [dict(item) for item in group]
        base["component_materials"] = [value for value in materials if value]
        base["component_specs"] = [value for value in specs if value]
        base["component_processes"] = [value for value in processes if value]
        base["material"] = self._join_unique_values(materials, separator=" + ")
        base["material_original"] = base["material"]
        base["spec"] = self._join_unique_values(specs, separator=" + ")
        base["process"] = self._join_unique_values(processes, separator=" + ")
        unique_aliases = self._join_unique_values(aliases, separator="+")
        base["material_alias"] = unique_aliases if "+" not in unique_aliases else "复合组件"
        base["vendor"] = self._join_unique_values(vendors, separator=" / ")
        base["qty"] = qty
        base["weight_kg"] = sum(self._to_number(item.get("weight_kg")) for item in group)
        base["effective_weight_kg"] = sum(self._to_number(item.get("effective_weight_kg") or item.get("weight_kg")) for item in group)
        base["current_unit_price"] = sum(self._to_number(item.get("current_unit_price")) for item in group)
        base["target_unit_price"] = sum(self._to_number(item.get("target_unit_price")) for item in group)
        base["material_price"] = sum(self._to_number(item.get("material_price")) for item in group)
        base["extra"] = sum(self._to_number(item.get("extra")) for item in group)
        base["ct"] = sum(self._to_number(item.get("ct")) for item in group)
        base["rate"] = max(self._to_number(item.get("rate")) for item in group)
        base["manual_process_unit"] = sum(self._to_number(item.get("manual_process_unit")) for item in group)
        base["manual_extra_unit"] = sum(self._to_number(item.get("manual_extra_unit")) for item in group)
        base["manual_surcharge_unit"] = base["manual_process_unit"] + base["manual_extra_unit"]
        base["composite_merge_note"] = "已按相同物料编码+物料名称的多材质子项合并为复合组件报价。"
        return base

    def _write_skill_input_workbook(self, items: list[dict], model_label: str, output_path: Path) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "BOM"
        sheet.append(["产品", "物料", "物料编码", "规格型号", "材质", "重量kg", "工艺", "数量", "目前采购总价"])
        for item in items:
            qty = self._to_number(item.get("qty")) or 1.0
            product_label = str(model_label or "").strip()
            product_spec = str(item.get("product_spec") or item.get("product_context") or "").strip()
            if product_spec:
                product_label = f"{product_label}｜{product_spec}" if product_label else product_spec
            sheet.append([
                product_label,
                item.get("name", ""),
                item.get("code", ""),
                item.get("spec", ""),
                item.get("skills_input_material") or item.get("material", ""),
                self._to_number(item.get("skills_input_weight_kg") or item.get("effective_weight_kg") or item.get("weight_kg")),
                item.get("skills_input_process") or item.get("process", ""),
                qty,
                self._to_number(item.get("current_unit_price")) * qty,
            ])
        workbook.save(output_path)
        return output_path

    def _run_script(self, script_name: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(self.skill_root / "scripts" / script_name), *args]
        try:
            return subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, check=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            detail = stderr or stdout or f"退出码 {exc.returncode}"
            if "Non-UTF-8 code" in detail:
                detail = "Skill 脚本文件编码异常，请重新同步 UTF-8 版本脚本后重试"
            raise RuntimeError(f"Skill 脚本 {script_name} 执行失败：{detail}") from exc

    def _run_price_bom(self, input_xlsx: Path, workdir: Path) -> tuple[Path, Path, Path, Path]:
        line_csv = workdir / "skill_line.csv"
        grouped_csv = workdir / "skill_grouped.csv"
        summary_md = workdir / "skill_summary.md"
        snapshot_json = workdir / "skill_market_snapshot.json"
        self._run_script(
            "price_bom_xlsx.py",
            [
                str(input_xlsx),
                "--output-csv",
                str(line_csv),
                "--output-grouped-csv",
                str(grouped_csv),
                "--output-summary-md",
                str(summary_md),
                "--output-market-snapshot",
                str(snapshot_json),
            ],
            workdir,
        )
        return line_csv, grouped_csv, summary_md, snapshot_json

    def _run_gap_analysis(self, line_csv: Path, workdir: Path) -> tuple[Path, Path, Path]:
        gap_csv = workdir / "skill_gap_summary.csv"
        gap_xlsx = workdir / "skill_gap_review.xlsx"
        gap_md = workdir / "skill_gap_summary.md"
        self._run_script(
            "analyze_pricing_gaps.py",
            [
                str(line_csv),
                "--export-summary",
                str(gap_csv),
                "--export-xlsx-by-product",
                str(gap_xlsx),
                "--export-summary-doc",
                str(gap_md),
            ],
            workdir,
        )
        return gap_csv, gap_xlsx, gap_md

    def _run_format_workbook(self, line_csv: Path, grouped_csv: Path, summary_md: Path, workdir: Path) -> Path:
        output_xlsx = workdir / "skill_estimate_workbook.xlsx"
        self._run_script(
            "format_estimate_workbook.py",
            [str(line_csv), str(grouped_csv), str(summary_md), "--output-xlsx", str(output_xlsx)],
            workdir,
        )
        return output_xlsx

    def _run_volume_pricing(self, line_csv: Path, workdir: Path, annual_volume: int) -> dict:
        output_dir = workdir / "volume_pricing"
        output_dir.mkdir(parents=True, exist_ok=True)
        self._run_script(
            "model_volume_pricing.py",
            [str(line_csv), "--annual-volume", str(annual_volume), "--output-dir", str(output_dir)],
            workdir,
        )
        outputs = {}
        for file in output_dir.iterdir():
            if file.is_file():
                outputs[file.stem] = str(file)
        return outputs

    def _estimate_ai_routes(
        self,
        items: list[dict],
        progress_callback: Callable[[dict], None] | None,
        production_mode: str,
        annual_volume: int,
        ai_skill_context_map: dict[str, dict],
    ) -> list[dict]:
        if not items:
            return []

        results: list[dict | None] = [None for _ in items]
        total = len(items)
        completed = 0
        max_workers = min(self.ai_route_service.max_workers, total) or 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict = {}
            for index, item in enumerate(items):
                prompt_item, estimate_note = self._build_ai_prompt_item(
                    item,
                    items,
                    production_mode,
                    annual_volume,
                    ai_skill_context_map,
                )
                missing_reason, missing_status = self._classify_ai_missing_context(prompt_item)
                if missing_reason:
                    results[index] = self._empty_ai_result(
                        missing_reason,
                        status=missing_status,
                        estimated_weight_kg=self._to_number(prompt_item.get("ai_estimated_weight_kg")),
                        estimated_weight_note=str(prompt_item.get("ai_estimated_weight_note") or ""),
                    )
                    completed += 1
                    self._notify_progress(
                        progress_callback,
                        stage="ai_supplement",
                        processed=completed,
                        total=total,
                        message=f"正在检查 AI 报价条件，已处理 {completed} / {total}",
                        parallel_workers=max_workers,
                        mode="parallel",
                        production_mode=production_mode,
                        annual_volume=annual_volume,
                    )
                    continue
                if not self.ai_route_service.is_ready:
                    results[index] = self._empty_ai_result(
                        "未配置 AI 接口 key，无法基于 skills 知识内容生成 AI 报价",
                        status="AI未配置",
                        estimated_weight_kg=self._to_number(prompt_item.get("ai_estimated_weight_kg")),
                        estimated_weight_note=str(prompt_item.get("ai_estimated_weight_note") or ""),
                    )
                    completed += 1
                    self._notify_progress(
                        progress_callback,
                        stage="ai_supplement",
                        processed=completed,
                        total=total,
                        message=f"等待 AI 报价条件补齐，已处理 {completed} / {total}",
                        parallel_workers=max_workers,
                        mode="parallel",
                        production_mode=production_mode,
                        annual_volume=annual_volume,
                    )
                    continue
                futures[executor.submit(self.ai_route_service.estimate_item, prompt_item)] = (index, estimate_note, prompt_item)
            for future in as_completed(futures):
                index, estimate_note, prompt_item = futures[future]
                try:
                    ai_result = future.result()
                    script_fallback = self._script_first_ai_fallback(prompt_item)
                    ai_unit_price = self._to_number(ai_result.get("unit_price"))
                    ai_reasoning = str(ai_result.get("reasoning") or "").strip()
                    if estimate_note:
                        ai_reasoning = f"{estimate_note} {ai_reasoning}".strip()
                    context = prompt_item.get("ai_skill_context") or {}
                    reliable_preinference = self._has_reliable_ai_preinference(prompt_item)
                    prefer_name_spec_formula = self._should_prefer_name_spec_formula(prompt_item)
                    if script_fallback is not None and not prefer_name_spec_formula:
                        ai_unit_price = self._to_number(script_fallback.get("ai_route_unit_price"))
                        ai_reasoning = self._merge_script_first_reasoning(
                            str(script_fallback.get("ai_route_reasoning") or ""),
                            ai_reasoning,
                            append_ai_reason=self._should_append_ai_supplement(ai_reasoning),
                        )
                    elif bool(prompt_item.get("ai_name_spec_fallback")) and (
                        prefer_name_spec_formula
                        or not reliable_preinference
                        or self._is_outside_name_spec_price_band(prompt_item, ai_unit_price)
                    ):
                        ai_unit_price, ai_reasoning = self._apply_name_spec_price_band(
                            prompt_item,
                            ai_unit_price,
                            ai_reasoning,
                        )
                    ai_status, ai_reasoning = self._classify_ai_result(ai_unit_price, ai_reasoning)
                    if (
                        ai_unit_price > 0
                        and script_fallback is None
                        and bool(prompt_item.get("ai_name_spec_fallback"))
                        and not reliable_preinference
                    ):
                        ai_status = "名称规格推断报价"
                        if "公式报价" not in ai_reasoning:
                            ai_reasoning = f"按物料名称/规格推断类别并报价。{ai_reasoning}".strip()
                    if (
                        self._to_number(prompt_item.get("ai_estimated_weight_kg")) > 0
                        and ai_unit_price > 0
                        and ai_status != "名称规格推断报价"
                    ):
                        ai_status = "估重待复核"
                    inferred_weight_kg = self._to_number(ai_result.get("estimated_weight_kg"))
                    prompt_estimated_weight_kg = self._to_number(prompt_item.get("ai_estimated_weight_kg"))
                    if inferred_weight_kg <= 0:
                        inferred_weight_kg = prompt_estimated_weight_kg
                    results[index] = {
                        "ai_route_unit_price": ai_unit_price,
                        "ai_route_confidence": self._to_number(ai_result.get("confidence")),
                        "ai_route_reasoning": f"AI报价（基于skills知识）：{ai_reasoning}".strip(),
                        "ai_route_status": "AI报价" if ai_unit_price > 0 and ai_status == "AI可用" else ai_status,
                        "ai_route_source": (
                            str(script_fallback.get("ai_route_source") or "").strip()
                            if script_fallback is not None
                            else str(ai_result.get("source") or "Qwen+skills").strip()
                        ),
                        "ai_route_process_guess": str(ai_result.get("process_guess") or "").strip(),
                        "ai_route_material_guess": str(ai_result.get("material_guess") or "").strip(),
                        "ai_estimated_weight_kg": inferred_weight_kg,
                        "ai_estimated_weight_note": str(prompt_item.get("ai_estimated_weight_note") or ""),
                        "ai_inferred_process_reference": str(ai_result.get("process_guess") or "").strip(),
                        "ai_inferred_material_reference": str(ai_result.get("material_guess") or "").strip(),
                        "ai_inferred_weight_reference": inferred_weight_kg,
                        "ai_inference_confidence": self._to_number(ai_result.get("inference_confidence")),
                        "ai_second_stage_used": bool(ai_result.get("staged_inference_used")),
                        "ai_second_stage_override_used": bool(ai_result.get("second_stage_override_used")),
                        "ai_second_stage_override_note": str(ai_result.get("second_stage_override_note") or "").strip(),
                        "ai_material_cost_reference": self._to_number(context.get("material_cost")),
                        "ai_process_cost_reference": self._to_number(context.get("process_cost")),
                        "ai_process_rule_reference": str(context.get("process_rule") or "").strip(),
                        "ai_process_rule_label": str(context.get("process_unit_label") or "").strip(),
                    }
                except Exception as exc:  # pragma: no cover
                    script_fallback = self._script_first_ai_fallback(prompt_item)
                    if script_fallback is not None:
                        reason = str(script_fallback.get("ai_route_reasoning") or "")
                        if estimate_note:
                            reason = f"{estimate_note} {reason}".strip()
                        results[index] = {
                            **script_fallback,
                            "ai_route_reasoning": reason,
                            "ai_estimated_weight_kg": self._to_number(prompt_item.get("ai_estimated_weight_kg")),
                            "ai_estimated_weight_note": str(prompt_item.get("ai_estimated_weight_note") or ""),
                            "ai_inferred_process_reference": "",
                            "ai_inferred_material_reference": "",
                            "ai_inferred_weight_reference": 0.0,
                            "ai_inference_confidence": 0.0,
                            "ai_second_stage_used": False,
                        }
                        completed += 1
                        self._notify_progress(
                            progress_callback,
                            stage="ai_supplement",
                            processed=completed,
                            total=total,
                            message=f"正在生成 AI 报价，已处理 {completed} / {total}",
                            parallel_workers=max_workers,
                            mode="parallel",
                            production_mode=production_mode,
                            annual_volume=annual_volume,
                        )
                        continue
                    reason, status = self._classify_ai_exception(str(exc))
                    if estimate_note:
                        reason = f"{estimate_note} {reason}".strip()
                    results[index] = self._empty_ai_result(
                        reason,
                        status=status,
                        estimated_weight_kg=self._to_number(prompt_item.get("ai_estimated_weight_kg")),
                        estimated_weight_note=str(prompt_item.get("ai_estimated_weight_note") or ""),
                    )
                completed += 1
                self._notify_progress(
                    progress_callback,
                    stage="ai_supplement",
                    processed=completed,
                    total=total,
                    message=f"正在生成 AI 报价，已处理 {completed} / {total}",
                    parallel_workers=max_workers,
                    mode="parallel",
                    production_mode=production_mode,
                    annual_volume=annual_volume,
                )
        return [item or self._empty_ai_result("待AI报价：未形成有效报价", status="待AI报价") for item in results]

    def _build_payload(
        self,
        *,
        items: list[dict],
        model: dict,
        ai_results: list[dict],
        line_csv: Path,
        grouped_csv: Path,
        gap_csv: Path | None,
        gap_xlsx: Path | None,
        gap_md: Path | None,
        formatted_xlsx: Path | None,
        snapshot_json: Path,
        volume_outputs: dict,
        script_plan: dict,
    ) -> dict:
        grouped_rows = self._read_csv_dicts(grouped_csv)
        grouped_by_code = {str(row.get("物料编码") or "").strip(): row for row in grouped_rows if str(row.get("物料编码") or "").strip()}
        line_rows = self._read_csv_dicts(line_csv)
        line_rows_by_code: dict[str, list[dict]] = {}
        for row in line_rows:
            code = str(row.get("物料编码") or "").strip()
            if not code:
                continue
            line_rows_by_code.setdefault(code, []).append(row)
        snapshot = self._read_json(snapshot_json)
        volume_detail_rows = self._read_volume_detail_rows(volume_outputs)
        volume_by_code = {str(row.get("物料编码") or "").strip(): row for row in volume_detail_rows if str(row.get("物料编码") or "").strip()}
        volume_by_name = {str(row.get("物料") or "").strip(): row for row in volume_detail_rows if str(row.get("物料") or "").strip()}

        payload_items: list[dict] = []
        for item, ai_result in zip(items, ai_results):
            grouped = grouped_by_code.get(item.get("code", ""), {})
            qty = self._to_number(item.get("qty")) or 1.0
            finance_price, finance_source, finance_has_reference = self._pick_finance_route(item)
            rule_total = self._to_number(grouped.get("基础估算总价"))
            rule_material = self._to_number(grouped.get("基础材料合计"))
            rule_process = self._to_number(grouped.get("基础工艺合计"))
            rule_unit = (rule_total / qty) if qty > 0 else rule_total
            ai_price = self._to_number(ai_result.get("ai_route_unit_price"))
            manual_process_unit = self._to_number(item.get("manual_process_unit"))
            manual_extra_unit = self._to_number(item.get("manual_extra_unit"))
            manual_surcharge_unit = self._to_number(item.get("manual_surcharge_unit"))
            display_rule_process = rule_process + (manual_process_unit * qty)
            display_rule_unit = rule_unit + manual_surcharge_unit if rule_unit > 0 else 0.0
            display_ai_price = ai_price + manual_surcharge_unit if ai_price > 0 else 0.0
            merged = {
                **item,
                **ai_result,
                "finance_route_unit_price": finance_price,
                "finance_route_total_price": finance_price * qty,
                "finance_route_source": finance_source,
                "finance_route_has_reference": finance_has_reference,
                "finance_route_status": "传统参考命中" if finance_has_reference else "缺传统参考",
                "changjiang_route_unit_price": display_rule_unit,
                "changjiang_material_cost": rule_material,
                "changjiang_process_cost": display_rule_process,
                "manual_process_unit": manual_process_unit,
                "manual_extra_unit": manual_extra_unit,
                "manual_surcharge_unit": manual_surcharge_unit,
                "effective_weight_kg": self._to_number(item.get("effective_weight_kg") or item.get("weight_kg")),
                "route_gap_unit_price": display_ai_price - finance_price,
                "route_gap_total": (display_ai_price - finance_price) * qty,
                "ai_route_unit_price": display_ai_price,
                "ai_route_total_price": display_ai_price * qty,
                "production_mode": self._normalize_production_mode(model.get("production_mode")),
                "annual_volume": self._to_int(model.get("annual_volume")),
            }
            if self._should_lock_skill_primary(merged):
                adjusted_locked_price = 0.0
                locked_adjust_parts: list[str] = []
                winding_locked_price, winding_adjust_reason = self._resolve_stator_winding_locked_price(merged)
                if winding_locked_price > 0:
                    adjusted_locked_price = max(adjusted_locked_price, winding_locked_price)
                if winding_adjust_reason:
                    locked_adjust_parts.append(winding_adjust_reason)
                stator_core_locked_price, stator_core_adjust_reason = self._resolve_stator_core_locked_price(merged)
                if stator_core_locked_price > 0:
                    adjusted_locked_price = max(adjusted_locked_price, stator_core_locked_price)
                if stator_core_adjust_reason:
                    locked_adjust_parts.append(stator_core_adjust_reason)
                locked_reason = self._build_locked_skill_reasoning(merged)
                if adjusted_locked_price > 0:
                    display_rule_unit = adjusted_locked_price
                if locked_adjust_parts:
                    locked_reason = f"{locked_reason} {' '.join(locked_adjust_parts)}".strip()
                merged["ai_route_unit_price"] = display_rule_unit
                merged["ai_route_total_price"] = display_rule_unit * qty
                merged["route_gap_unit_price"] = display_rule_unit - finance_price
                merged["route_gap_total"] = (display_rule_unit - finance_price) * qty
                merged["ai_route_status"] = "AI报价"
                merged["ai_route_source"] = "skills-locked-primary"
                merged["ai_route_reasoning"] = self._merge_script_first_reasoning(
                    locked_reason,
                    str(merged.get("ai_route_reasoning") or ""),
                    append_ai_reason=False,
                )
            volume_row = volume_by_code.get(str(item.get("code") or "").strip()) or volume_by_name.get(str(item.get("name") or "").strip())
            tooling_quote = {}
            if merged.get("production_mode") == "mass":
                tooling_quote = self._resolve_precision_shaft_mass_production_quote(merged)
                if not tooling_quote:
                    tooling_quote = self._resolve_stator_winding_mass_production_quote(merged)
                if not tooling_quote:
                    tooling_quote = self._resolve_rotor_assembly_mass_production_quote(merged)
                if not tooling_quote:
                    tooling_quote = self._resolve_stator_core_mass_production_quote(merged)
                if not tooling_quote:
                    tooling_quote = self._resolve_precision_end_cover_mass_production_quote(merged)
                if not tooling_quote:
                    tooling_quote = self._resolve_precision_housing_mass_production_quote(merged)
                if not tooling_quote:
                    tooling_quote = self._resolve_motor_shell_mass_production_quote(merged)
                if tooling_quote:
                    mass_unit = self._to_number(tooling_quote.get("unit_price"))
                    if mass_unit > 0:
                        merged["sample_machining_unit_price"] = self._to_number(tooling_quote.get("sample_machining_unit_price"))
                        merged["mass_tooling_unit_price"] = mass_unit
                        merged["tooling_cost"] = self._to_number(tooling_quote.get("tooling_cost"))
                        merged["mass_break_even_volume"] = self._to_int(tooling_quote.get("break_even_volume"))
                        merged["mass_process_route"] = str(tooling_quote.get("mass_process_route") or "开模工艺").strip() or "开模工艺"
                        merged["ai_route_unit_price"] = mass_unit
                        merged["ai_route_total_price"] = mass_unit * qty
                        merged["route_gap_unit_price"] = mass_unit - finance_price
                        merged["route_gap_total"] = (mass_unit - finance_price) * qty
                        merged["ai_route_status"] = "AI报价"
                        merged["ai_route_source"] = "mass-tooling-route"
                        merged["ai_route_reasoning"] = str(tooling_quote.get("note") or merged.get("ai_route_reasoning") or "").strip()
            merged["volume_baseline_unit_price"] = self._to_number(merged.get("ai_route_unit_price")) or display_ai_price
            merged["volume_conservative_unit_price"] = 0.0
            merged["volume_aggressive_unit_price"] = 0.0
            mass_volume_prices = None
            if volume_row:
                baseline_total = self._to_number(volume_row.get("基准总价"))
                conservative_total = self._to_number(volume_row.get("保守总价"))
                aggressive_total = self._to_number(volume_row.get("激进总价"))
                skill_baseline_unit = (baseline_total / qty) if qty > 0 else baseline_total
                conservative_unit = (conservative_total / qty) if qty > 0 else conservative_total
                aggressive_unit = (aggressive_total / qty) if qty > 0 else aggressive_total
                merged["volume_baseline_unit_price"] = self._to_number(merged.get("ai_route_unit_price")) or display_ai_price
                effective_ai_unit = self._to_number(merged.get("ai_route_unit_price")) or ai_price
                conservative_ratio = conservative_unit / skill_baseline_unit if skill_baseline_unit > 0 else 0.0
                aggressive_ratio = aggressive_unit / skill_baseline_unit if skill_baseline_unit > 0 else 0.0
                mass_volume_prices = self._derive_mass_volume_prices(
                    baseline_unit=effective_ai_unit,
                    annual_volume=self._to_int(merged.get("annual_volume")),
                    conservative_ratio=conservative_ratio,
                    aggressive_ratio=aggressive_ratio,
                    manual_surcharge_unit=manual_surcharge_unit,
                )
                merged["volume_conservative_unit_price"] = self._to_number(mass_volume_prices.get("conservative_unit_price"))
                merged["volume_aggressive_unit_price"] = self._to_number(mass_volume_prices.get("aggressive_unit_price"))
                merged["volume_conservative_discount"] = self._to_number(volume_row.get("保守材料折扣")) or self._to_number(mass_volume_prices.get("conservative_discount"))
                merged["volume_conservative_process_discount"] = self._to_number(volume_row.get("保守工艺折扣"))
                merged["volume_aggressive_discount"] = self._to_number(volume_row.get("激进材料折扣")) or self._to_number(mass_volume_prices.get("aggressive_discount"))
                merged["volume_aggressive_process_discount"] = self._to_number(volume_row.get("激进工艺折扣"))
                merged["volume_baseline_total_price"] = merged["volume_baseline_unit_price"] * qty
                merged["volume_conservative_total_price"] = merged["volume_conservative_unit_price"] * qty
                merged["volume_aggressive_total_price"] = merged["volume_aggressive_unit_price"] * qty
                if effective_ai_unit > 0:
                    volume_tier_label = self._describe_volume_tier_label(merged.get("annual_volume"))
                    merged["volume_tier_label"] = volume_tier_label
                    base_summary = (
                        f"量产口径（{merged['annual_volume']}套/年，{volume_tier_label}档）："
                        f"基准 {merged['volume_baseline_unit_price']:.2f} / 保守 {merged['volume_conservative_unit_price']:.2f} / 激进 {merged['volume_aggressive_unit_price']:.2f} 元"
                    )
                    tooling_summary = str(tooling_quote.get("volume_pricing_summary") or "").strip()
                    tooling_note = str(tooling_quote.get("note") or "").strip()
                    merged["volume_pricing_summary"] = tooling_summary or (f"{base_summary}；{tooling_note}" if tooling_note else base_summary)
            elif tooling_quote:
                effective_ai_unit = self._to_number(merged.get("ai_route_unit_price"))
                mass_volume_prices = self._derive_mass_volume_prices(
                    baseline_unit=effective_ai_unit,
                    annual_volume=self._to_int(merged.get("annual_volume")),
                    manual_surcharge_unit=0.0,
                )
                merged["volume_baseline_unit_price"] = self._to_number(mass_volume_prices.get("baseline_unit_price"))
                merged["volume_conservative_unit_price"] = self._to_number(mass_volume_prices.get("conservative_unit_price"))
                merged["volume_aggressive_unit_price"] = self._to_number(mass_volume_prices.get("aggressive_unit_price"))
                merged["volume_conservative_discount"] = self._to_number(mass_volume_prices.get("conservative_discount"))
                merged["volume_aggressive_discount"] = self._to_number(mass_volume_prices.get("aggressive_discount"))
                merged["volume_baseline_total_price"] = merged["volume_baseline_unit_price"] * qty
                merged["volume_conservative_total_price"] = merged["volume_conservative_unit_price"] * qty
                merged["volume_aggressive_total_price"] = merged["volume_aggressive_unit_price"] * qty
                volume_tier_label = self._describe_volume_tier_label(merged.get("annual_volume"))
                merged["volume_tier_label"] = volume_tier_label
                merged["volume_pricing_summary"] = str(tooling_quote.get("volume_pricing_summary") or "").strip() or (
                    f"量产口径（{merged['annual_volume']}套/年，{volume_tier_label}档）："
                    f"基准 {merged['volume_baseline_unit_price']:.2f} / 保守 {merged['volume_conservative_unit_price']:.2f} / 激进 {merged['volume_aggressive_unit_price']:.2f} 元；"
                    f"{str(tooling_quote.get('note') or '').strip()}"
                ).strip("；")
            elif merged.get("production_mode") == "mass":
                effective_ai_unit = self._to_number(merged.get("ai_route_unit_price")) or display_ai_price
                if effective_ai_unit > 0:
                    mass_volume_prices = self._derive_mass_volume_prices(
                        baseline_unit=effective_ai_unit,
                        annual_volume=self._to_int(merged.get("annual_volume")),
                        manual_surcharge_unit=manual_surcharge_unit,
                    )
                    merged["volume_baseline_unit_price"] = self._to_number(mass_volume_prices.get("baseline_unit_price"))
                    merged["volume_conservative_unit_price"] = self._to_number(mass_volume_prices.get("conservative_unit_price"))
                    merged["volume_aggressive_unit_price"] = self._to_number(mass_volume_prices.get("aggressive_unit_price"))
                    merged["volume_conservative_discount"] = self._to_number(mass_volume_prices.get("conservative_discount"))
                    merged["volume_aggressive_discount"] = self._to_number(mass_volume_prices.get("aggressive_discount"))
                    merged["volume_baseline_total_price"] = merged["volume_baseline_unit_price"] * qty
                    merged["volume_conservative_total_price"] = merged["volume_conservative_unit_price"] * qty
                    merged["volume_aggressive_total_price"] = merged["volume_aggressive_unit_price"] * qty
                    volume_tier_label = self._describe_volume_tier_label(merged.get("annual_volume"))
                    merged["volume_tier_label"] = volume_tier_label
                    merged["volume_pricing_summary"] = (
                        f"量产口径（{merged['annual_volume']}套/年，{volume_tier_label}档）："
                        f"基准 {merged['volume_baseline_unit_price']:.2f} / 保守 {merged['volume_conservative_unit_price']:.2f} / 激进 {merged['volume_aggressive_unit_price']:.2f} 元"
                    )
            self._ensure_mass_volume_prices(merged, qty=qty, manual_surcharge_unit=manual_surcharge_unit)
            merged["comparison_reason_summary"] = self._analyze_price_gap(merged)
            merged["status"] = self._item_status(merged)
            merged["source_tag"] = self._source_tag(merged)
            merged["analysis_log_text"] = self._build_item_analysis_log(
                item=merged,
                line_rows=line_rows_by_code.get(str(item.get("code") or "").strip(), []),
                script_plan=script_plan,
                production_mode=self._normalize_production_mode(model.get("production_mode")),
                annual_volume=self._to_int(model.get("annual_volume")),
            )
            payload_items.append(merged)

        self.annotate_price_tax_breakdown(payload_items, price_field="ai_route_unit_price", prefix="ai_route")
        for item in payload_items:
            selected_unit = self._to_number(item.get("ai_route_unit_price")) or self._to_number(item.get("finance_route_unit_price"))
            item["selected_quote_unit_price"] = selected_unit
            item["selected_quote_source"] = "AI报价" if self._to_number(item.get("ai_route_unit_price")) > 0 else "财务传统报价"
        self.annotate_price_tax_breakdown(payload_items, price_field="selected_quote_unit_price", prefix="selected_quote")

        summary = self._build_summary(payload_items)
        summary["market_snapshot_count"] = len(snapshot or {})
        summary["skill_rule_total"] = sum(self._to_number(item.get("changjiang_route_unit_price")) * (self._to_number(item.get("qty")) or 1.0) for item in payload_items)
        summary["dual_quote_ready_count"] = sum(
            1 for item in payload_items
            if self._to_number(item.get("finance_route_unit_price")) > 0 and self._to_number(item.get("ai_route_unit_price")) > 0
        )
        payload = {
            "dataset": "skill_quote",
            "source": self.SOURCE_NAME,
            "model": {
                **model,
                "label": self._model_label(model),
                "item_count": len(payload_items),
            },
            "summary": summary,
            "items": payload_items,
            "analysis_log_text": self._build_analysis_log_text(payload_items, script_plan),
            "skill_outputs": {
                "line_csv": str(line_csv),
                "grouped_csv": str(grouped_csv),
                "market_snapshot_json": str(snapshot_json),
                **({"gap_csv": str(gap_csv)} if gap_csv else {}),
                **({"gap_xlsx": str(gap_xlsx)} if gap_xlsx else {}),
                **({"gap_md": str(gap_md)} if gap_md else {}),
                **({"formatted_xlsx": str(formatted_xlsx)} if formatted_xlsx else {}),
                **{f"volume_{key}": value for key, value in volume_outputs.items()},
            },
            "market_snapshot": snapshot,
            "backend": {
                "ai_quote_skill": str(self.skill_root),
                "ai_orchestration_mode": "qwen-script-planner+script-first-ai-supplement",
                "skill_script_registry": list(script_plan.get("registry") or []),
                "skill_script_plan": script_plan,
            },
        }
        payload["exports"] = self.describe_skill_exports(payload)
        return payload

    def reproject_mass_payload_for_volume(
        self,
        payload: dict,
        annual_volume: int,
        requested_volume_label: str | None = None,
    ) -> dict:
        next_payload = copy.deepcopy(payload or {})
        annual_volume = self._to_int(annual_volume)
        if annual_volume <= 0:
            return next_payload

        model = dict(next_payload.get("model") or {})
        model["production_mode"] = "mass"
        model["annual_volume"] = annual_volume
        model["requested_annual_volume"] = annual_volume
        if requested_volume_label:
            model["requested_volume_label"] = str(requested_volume_label).strip()
        next_payload["model"] = model

        items = list(next_payload.get("items") or [])
        for item in items:
            item["production_mode"] = "mass"
            item["annual_volume"] = annual_volume
            qty = self._to_number(item.get("qty")) or 1.0
            manual_surcharge_unit = self._to_number(item.get("manual_surcharge_unit"))
            baseline_unit = self._to_number(item.get("volume_baseline_unit_price") or item.get("ai_route_unit_price"))
            prices = self._derive_mass_volume_prices(
                baseline_unit=baseline_unit,
                annual_volume=annual_volume,
                manual_surcharge_unit=manual_surcharge_unit,
            ) if baseline_unit > 0 else {}
            if baseline_unit > 0:
                item["volume_baseline_unit_price"] = baseline_unit
                item["volume_conservative_unit_price"] = self._to_number(prices.get("conservative_unit_price"))
                item["volume_aggressive_unit_price"] = self._to_number(prices.get("aggressive_unit_price"))
                item["volume_conservative_discount"] = self._to_number(prices.get("conservative_discount"))
                item["volume_aggressive_discount"] = self._to_number(prices.get("aggressive_discount"))
                item["volume_baseline_total_price"] = baseline_unit * qty
                item["volume_conservative_total_price"] = self._to_number(item.get("volume_conservative_unit_price")) * qty
                item["volume_aggressive_total_price"] = self._to_number(item.get("volume_aggressive_unit_price")) * qty
            else:
                self._ensure_mass_volume_prices(item, qty=qty, manual_surcharge_unit=manual_surcharge_unit)
            item["volume_tier_label"] = self._describe_volume_tier_label(annual_volume)
            item["volume_pricing_summary"] = self._build_reprojected_volume_pricing_summary(item, annual_volume)
            item["ai_route_reasoning"] = self._append_mass_reproject_reasoning(
                str(item.get("ai_route_reasoning") or ""),
                annual_volume=annual_volume,
                volume_summary=str(item.get("volume_pricing_summary") or "").strip(),
            )
        next_payload["items"] = items
        next_payload["summary"] = self._build_summary(items)
        next_payload["exports"] = self.describe_skill_exports(next_payload)
        return next_payload

    @classmethod
    def _build_reprojected_volume_pricing_summary(cls, item: dict, annual_volume: int) -> str:
        tier_label = cls._describe_volume_tier_label(annual_volume)
        baseline = cls._to_number(item.get("volume_baseline_unit_price"))
        conservative = cls._to_number(item.get("volume_conservative_unit_price"))
        aggressive = cls._to_number(item.get("volume_aggressive_unit_price"))
        summary = (
            f"量产口径（{annual_volume}套/年，{tier_label}档）："
            f"基准 {baseline:.2f} / 保守 {conservative:.2f} / 激进 {aggressive:.2f} 元"
        )
        if cls._to_number(item.get("tooling_cost")) > 0 and cls._to_number(item.get("sample_machining_unit_price")) > 0:
            tooling_note = (
                f"当前单件按开模/工装后工艺计 {baseline:.2f} 元，不把开模费 {cls._to_number(item.get('tooling_cost')):.2f} 元并入当前产品总价；"
                f"样品/小批路线单价约 {cls._to_number(item.get('sample_machining_unit_price')):.2f} 元，"
                f"平衡点约 {cls._to_int(item.get('mass_break_even_volume'))} 套/年。"
            )
            return f"{summary}；{tooling_note}"
        return summary

    @classmethod
    def _append_mass_reproject_reasoning(cls, reasoning: str, *, annual_volume: int, volume_summary: str) -> str:
        marker = "量产档位已沿用同一基准AI结果重算"
        tier_label = cls._describe_volume_tier_label(annual_volume)
        prefix = f"{marker}：当前档位 {annual_volume}套/年（{tier_label}档）。"
        cleaned = str(reasoning or "").strip()
        if marker in cleaned:
            cleaned = re.sub(rf"{marker}：当前档位 .*?档）。", prefix, cleaned, count=1)
        elif cleaned:
            cleaned = f"{prefix}\n{volume_summary}\n{cleaned}"
        else:
            cleaned = f"{prefix}\n{volume_summary}"
        return cleaned.strip()

    def _build_analysis_log_text(self, items: list[dict], script_plan: dict) -> str:
        lines = ["=== AI 报价分析流程日志 ==="]
        selected = [str(name).strip() for name in (script_plan.get("selected_scripts") or []) if str(name).strip()]
        registry = [str(name).strip() for name in (script_plan.get("registry") or []) if str(name).strip()]
        if selected:
            lines.append(f"本次脚本计划: {' -> '.join(selected)}")
        if registry:
            lines.append(f"白名单脚本: {', '.join(registry)}")
        reason = str(script_plan.get("reason") or "").strip()
        if reason:
            lines.append(f"脚本计划原因: {reason}")
        if lines:
            lines.append("")
        for index, item in enumerate(items, start=1):
            block = str(item.get("analysis_log_text") or "").strip()
            if not block:
                continue
            if index > 1:
                lines.append("")
            lines.append(block)
        return "\n".join(lines).strip()

    def _build_rule_pricing_log_text(
        self,
        *,
        items: list[dict],
        line_csv: Path,
        grouped_csv: Path,
        script_plan: dict,
        production_mode: str,
        annual_volume: int,
    ) -> str:
        grouped_rows = self._read_csv_dicts(grouped_csv)
        grouped_by_code = {
            str(row.get("物料编码") or "").strip(): row
            for row in grouped_rows
            if str(row.get("物料编码") or "").strip()
        }
        line_rows = self._read_csv_dicts(line_csv)
        line_rows_by_code: dict[str, list[dict]] = {}
        for row in line_rows:
            code = str(row.get("物料编码") or "").strip()
            if not code:
                continue
            line_rows_by_code.setdefault(code, []).append(row)

        lines = ["=== skills 规则报价实时日志 ==="]
        selected = [str(name).strip() for name in (script_plan.get("selected_scripts") or []) if str(name).strip()]
        if selected:
            lines.append(f"当前脚本链路: {' -> '.join(selected)}")
        reason = str(script_plan.get("reason") or "").strip()
        if reason:
            lines.append(f"脚本计划原因: {reason}")
        lines.append("")

        for index, item in enumerate(items, start=1):
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or "").strip() or "-"
            qty = self._to_number(item.get("qty")) or 1.0
            weight_kg = self._to_number(item.get("weight_kg"))
            grouped = grouped_by_code.get(code, {})
            line_total = self._to_number(grouped.get("基础估算总价"))
            line_unit = (line_total / qty) if qty > 0 else line_total
            if index > 1:
                lines.append("")
            lines.append(f"[{code or '-'}] {name}")
            if bool(item.get("composite_component")):
                lines.append(
                    "组件合并: 已按相同物料编码+物料名称合并多材质子项；材质构成={materials}；规格构成={specs}".format(
                        materials=self._join_unique_values(list(item.get("component_materials") or []), separator=" + ") or "-",
                        specs=self._join_unique_values(list(item.get("component_specs") or []), separator=" + ") or "-",
                    )
                )
            process_display = str(item.get("process") or "").strip() or "未填写"
            process_inference_note = str(item.get("process_inference_note") or "").strip()
            if process_inference_note:
                process_display = f"{process_display}（默认推断）"
            lines.append(
                "输入字段: 材质={material}；工艺={process}；数量={qty:.2f}；单件重量={weight:.4f}kg".format(
                    material=str(item.get("material") or "").strip() or "-",
                    process=process_display,
                    qty=qty,
                    weight=weight_kg,
                )
            )
            if process_inference_note:
                lines.append(f"工艺提示: {process_inference_note}")
            estimated_weight_kg = self._to_number(item.get("ai_estimated_weight_kg"))
            estimated_weight_note = str(item.get("ai_estimated_weight_note") or "").strip()
            if estimated_weight_kg > 0:
                lines.append(f"重量提示: {estimated_weight_note or f'已按 AI 估重 {estimated_weight_kg:.4f}kg 参与报价'}")
            if production_mode == "mass":
                lines.append(f"报价模式: 量产；年产量={annual_volume}")
            else:
                lines.append("报价模式: 样品/小批")
            rows = line_rows_by_code.get(code, [])
            if not rows:
                lines.append("脚本行级日志: 正在等待 rules 输出。")
            else:
                for row_idx, row in enumerate(rows, start=1):
                    process_unit_label = str(row.get("工艺单价") or "").strip()
                    lines.append(
                        "脚本行#{idx}: 材料来源={mat_source}；材料单价={mat_unit}；材料金额={mat_total}；工艺识别={process}；工艺单价={proc_unit}；工艺金额={proc_total}；行总价={line_total}".format(
                            idx=row_idx,
                            mat_source=str(row.get("基础价格来源") or "").strip() or "未识别",
                            mat_unit=self._format_log_number(row.get("基础单价")),
                            mat_total=self._format_log_money(row.get("基础金额")),
                            process=self._describe_process_recognition(
                                item=item,
                                row_process=str(row.get("工艺") or "").strip(),
                                process_unit_label=process_unit_label,
                            ),
                            proc_unit=process_unit_label or "未识别",
                            proc_total=self._format_log_money(row.get("工艺金额")),
                            line_total=self._format_log_money(row.get("行总价")),
                        )
                    )
            lines.append(
                "实时结果: 财务传统报价={finance}；脚本基准报价={rule}".format(
                    finance=self._format_log_money(self._pick_finance_route(item)[0]),
                    rule=self._format_log_money(line_unit),
                )
            )
        return "\n".join(lines).strip()

    def _build_item_analysis_log(
        self,
        *,
        item: dict,
        line_rows: list[dict],
        script_plan: dict,
        production_mode: str,
        annual_volume: int,
    ) -> str:
        code = str(item.get("code") or "").strip() or "-"
        name = str(item.get("name") or "").strip() or "-"
        material = str(item.get("material") or "").strip() or "-"
        qty = self._to_number(item.get("qty")) or 1.0
        weight_kg = self._to_number(item.get("weight_kg"))
        ai_price = self._to_number(item.get("ai_route_unit_price"))
        finance_price = self._to_number(item.get("finance_route_unit_price"))
        process_display = str(item.get("process") or "").strip() or "未填写"
        process_inference_note = str(item.get("process_inference_note") or "").strip()
        if process_inference_note:
            process_display = f"{process_display}（默认推断）"
        lines = [f"[{code}] {name}"]
        if bool(item.get("composite_component")):
            lines.append(
                "组件合并: 已按相同物料编码+物料名称合并多材质子项；材质构成={materials}；规格构成={specs}".format(
                    materials=self._join_unique_values(list(item.get("component_materials") or []), separator=" + ") or "-",
                    specs=self._join_unique_values(list(item.get("component_specs") or []), separator=" + ") or "-",
                )
            )
        lines.append(
            "输入字段: 材质={material}；工艺={process}；数量={qty:.2f}；单件重量={weight:.4f}kg".format(
                material=material,
                process=process_display,
                qty=qty,
                weight=weight_kg,
            )
        )
        if process_inference_note:
            lines.append(f"工艺提示: {process_inference_note}")
        skill_input_reference = self._build_skill_input_reference_text(item)
        if skill_input_reference:
            lines.append(skill_input_reference)
        estimated_weight_kg = self._to_number(item.get("ai_estimated_weight_kg"))
        estimated_weight_note = str(item.get("ai_estimated_weight_note") or "").strip()
        if estimated_weight_kg > 0:
            lines.append(f"重量提示: {estimated_weight_note or f'已按 AI 估重 {estimated_weight_kg:.4f}kg 参与报价'}")
        loss = self._to_number(item.get("loss"))
        effective_weight_kg = self._to_number(item.get("effective_weight_kg"))
        if loss > 0 and effective_weight_kg > 0:
            lines.append(f"损耗处理: 损耗率 {loss:.2%}，计价重量按 {effective_weight_kg:.4f}kg 参与材料测算")
        manual_process_unit = self._to_number(item.get("manual_process_unit"))
        manual_extra_unit = self._to_number(item.get("manual_extra_unit"))
        if manual_process_unit > 0:
            lines.append(f"工艺附加: 节拍 × 费率折算 {manual_process_unit:.2f} 元/件")
        if manual_extra_unit > 0:
            lines.append(f"采购/外协附加: {manual_extra_unit:.2f} 元/件")
        if production_mode == "mass":
            lines.append(f"报价模式: 量产；年产量={annual_volume}")
        else:
            lines.append("报价模式: 样品/小批")
        selected = [str(name).strip() for name in (script_plan.get("selected_scripts") or []) if str(name).strip()]
        if selected:
            lines.append(f"脚本执行链路: {' -> '.join(selected)}")

        if not line_rows:
            lines.append("脚本行级日志: 未找到对应的 skills 行级输出。")
        else:
            for idx, row in enumerate(line_rows, start=1):
                row_process = str(row.get("工艺") or "").strip()
                process_unit_label = str(row.get("工艺单价") or "").strip()
                process_note = self._describe_process_recognition(
                    item=item,
                    row_process=row_process,
                    process_unit_label=process_unit_label,
                )
                lines.append(
                    "脚本行#{idx}: 材料来源={mat_source}；材料单价={mat_unit}；材料金额={mat_total}；工艺识别={process_note}；工艺单价={proc_unit}；工艺金额={proc_total}；行总价={line_total}".format(
                        idx=idx,
                        mat_source=str(row.get("基础价格来源") or "").strip() or "未识别",
                        mat_unit=self._format_log_number(row.get("基础单价")),
                        mat_total=self._format_log_money(row.get("基础金额")),
                        process_note=process_note,
                        proc_unit=process_unit_label or "未识别",
                        proc_total=self._format_log_money(row.get("工艺金额")),
                        line_total=self._format_log_money(row.get("行总价")),
                    )
                )

        lines.append(
            "结果汇总: 财务传统报价={finance}；基准报价={ai}；价差={gap}".format(
                finance=self._format_log_money(finance_price),
                ai=self._format_log_money(ai_price),
                gap=self._format_log_money(ai_price - finance_price, signed=True),
            )
        )
        reason = str(item.get("ai_route_reasoning") or "").strip()
        if reason:
            lines.append(f"基准说明: {reason}")
        return "\n".join(lines)

    @classmethod
    def _build_skill_input_reference_text(cls, item: dict) -> str:
        process = str(item.get("skills_input_process") or "").strip()
        material = str(item.get("skills_input_material") or "").strip()
        weight = cls._to_number(item.get("skills_input_weight_kg"))
        process_source = str(item.get("skills_input_process_source") or "").strip()
        material_source = str(item.get("skills_input_material_source") or "").strip()
        weight_source = str(item.get("skills_input_weight_source") or "").strip()
        parts: list[str] = []
        if process:
            parts.append(f"工艺={process}")
        if material:
            parts.append(f"材质={material}")
        if weight > 0:
            parts.append(f"重量={weight:.4f}kg")
        sources = [value for value in (process_source, material_source, weight_source) if value]
        source_text = "；".join(dict.fromkeys(sources))
        if source_text:
            parts.append(f"来源={source_text}")
        if not parts:
            return ""
        return f"skills实际采用输入：{'；'.join(parts)}"

    @staticmethod
    def _format_log_number(value: object) -> str:
        text = str(value or "").strip()
        if not text:
            return "0"
        return text

    @classmethod
    def _format_log_money(cls, value: object, *, signed: bool = False) -> str:
        amount = cls._to_number(value)
        if signed:
            return f"{amount:+.2f} 元"
        return f"{amount:.2f} 元"

    @classmethod
    def _describe_process_recognition(cls, *, item: dict, row_process: str, process_unit_label: str) -> str:
        if row_process:
            return row_process
        name = str(item.get("name") or "").strip()
        material = str(item.get("material") or "").strip()
        if process_unit_label and process_unit_label.endswith("元/kg") and ("永磁体" in name or "UH" in material or "钕铁硼" in material):
            return "烧结(按永磁体默认工艺)"
        return "未识别"

    def describe_skill_exports(self, payload: dict) -> list[dict]:
        items = payload.get("items") or []
        outputs = payload.get("skill_outputs") or {}
        exports = []
        mapping = [
            ("line_csv", "Skill行级报价"),
            ("grouped_csv", "Skill分组汇总"),
            ("gap_csv", "Skill差异复核明细"),
            ("gap_md", "Skill差异复核说明"),
            ("gap_xlsx", "差异复核工作簿"),
            ("formatted_xlsx", "Skill格式化报价表"),
        ]
        for key, label in mapping:
            raw = outputs.get(key)
            if not raw:
                continue
            path = Path(str(raw))
            exports.append({
                "id": key,
                "label": label,
                "filename": path.name,
                "item_count": len(items),
            })
        for key, raw in outputs.items():
            if not str(key).startswith("volume_"):
                continue
            path = Path(str(raw))
            if not path.exists() or not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix == ".xlsx":
                label = "量产降本对比"
            elif "明细" in path.stem:
                label = "量产降本明细"
            elif "汇总" in path.stem:
                label = "量产降本汇总"
            elif suffix == ".md":
                label = "量产降本说明"
            else:
                label = "量产测算文件"
            exports.append({
                "id": key,
                "label": label,
                "filename": path.name,
                "item_count": len(items),
            })
        return exports

    def _read_volume_detail_rows(self, volume_outputs: dict) -> list[dict]:
        for raw in (volume_outputs or {}).values():
            path = Path(str(raw))
            if path.suffix.lower() != ".csv" or "明细" not in path.stem:
                continue
            rows = self._read_csv_dicts(path)
            if rows:
                return rows
        return []

    def _fetch_purchase_refs(self, material_codes: list[str]) -> dict[str, dict]:
        refs: dict[str, dict] = {}
        if not self.kingdee_service or not self.config or not getattr(self.config, "kingdee", None) or not self.config.kingdee.is_ready:
            return refs
        for code in list(dict.fromkeys(material_codes))[:80]:
            if not code:
                continue
            try:
                result = self.kingdee_service.purchase_orders(code, limit=1)
            except Exception:
                continue
            if result.ok and result.data.get("rows"):
                refs[code] = dict(result.data["rows"][0])
        return refs

    @staticmethod
    def _pick_finance_route(item: dict) -> tuple[float, str, bool]:
        extra = FinanceSkillQuoteService._to_number(item.get("extra"))
        uploaded_price = FinanceSkillQuoteService._to_number(item.get("current_unit_price"))
        if uploaded_price > 0:
            return uploaded_price + extra, "Excel表格采购价", True
        kingdee_price = FinanceSkillQuoteService._to_number(item.get("kingdee_reference_price"))
        if kingdee_price > 0:
            return kingdee_price + extra, "金蝶最近采购价", True
        target_price = FinanceSkillQuoteService._to_number(item.get("target_unit_price"))
        if target_price > 0:
            return target_price + extra, "Excel目标价", True
        return 0.0, "待补传统参考", False

    @staticmethod
    def _build_summary(items: list[dict]) -> dict:
        total_weight = sum(FinanceSkillQuoteService._to_number(item.get("weight_kg")) * (FinanceSkillQuoteService._to_number(item.get("qty")) or 1.0) for item in items)
        finance_total = sum(FinanceSkillQuoteService._to_number(item.get("finance_route_unit_price")) * (FinanceSkillQuoteService._to_number(item.get("qty")) or 1.0) for item in items)
        ai_total = sum(FinanceSkillQuoteService._to_number(item.get("ai_route_unit_price")) * (FinanceSkillQuoteService._to_number(item.get("qty")) or 1.0) for item in items)
        selected_total = sum(FinanceSkillQuoteService._to_number(item.get("selected_quote_unit_price")) * (FinanceSkillQuoteService._to_number(item.get("qty")) or 1.0) for item in items)
        volume_baseline_total = sum(FinanceSkillQuoteService._to_number(item.get("volume_baseline_unit_price")) * (FinanceSkillQuoteService._to_number(item.get("qty")) or 1.0) for item in items)
        volume_conservative_total = sum(FinanceSkillQuoteService._to_number(item.get("volume_conservative_unit_price")) * (FinanceSkillQuoteService._to_number(item.get("qty")) or 1.0) for item in items)
        volume_aggressive_total = sum(FinanceSkillQuoteService._to_number(item.get("volume_aggressive_unit_price")) * (FinanceSkillQuoteService._to_number(item.get("qty")) or 1.0) for item in items)
        has_mass_items = any(FinanceSkillQuoteService._normalize_production_mode(item.get("production_mode")) == "mass" for item in items)
        if has_mass_items and volume_baseline_total > 0:
            ai_total = volume_baseline_total
        return {
            "total_weight": total_weight,
            "finance_total": finance_total,
            "ai_total": ai_total,
            "selected_quote_total": selected_total,
            "volume_baseline_total": volume_baseline_total,
            "volume_conservative_total": volume_conservative_total,
            "volume_aggressive_total": volume_aggressive_total,
            "ai_total_tax_inclusive": sum(FinanceSkillQuoteService._to_number(item.get("ai_route_tax_inclusive_total_price")) for item in items),
            "ai_total_tax_exclusive": sum(FinanceSkillQuoteService._to_number(item.get("ai_route_tax_exclusive_total_price")) for item in items),
            "ai_total_tax_amount": sum(FinanceSkillQuoteService._to_number(item.get("ai_route_tax_amount_total_price")) for item in items),
            "selected_quote_total_tax_inclusive": sum(FinanceSkillQuoteService._to_number(item.get("selected_quote_tax_inclusive_total_price")) for item in items),
            "selected_quote_total_tax_exclusive": sum(FinanceSkillQuoteService._to_number(item.get("selected_quote_tax_exclusive_total_price")) for item in items),
            "selected_quote_total_tax_amount": sum(FinanceSkillQuoteService._to_number(item.get("selected_quote_tax_amount_total_price")) for item in items),
            "route_gap_total": ai_total - finance_total,
            "finance_reference_count": sum(1 for item in items if FinanceSkillQuoteService._to_number(item.get("finance_route_unit_price")) > 0),
            "finance_missing_count": sum(1 for item in items if FinanceSkillQuoteService._to_number(item.get("finance_route_unit_price")) <= 0),
            "ai_ready_count": sum(1 for item in items if FinanceSkillQuoteService._to_number(item.get("ai_route_unit_price")) > 0),
            "ai_unavailable_count": sum(1 for item in items if FinanceSkillQuoteService._to_number(item.get("ai_route_unit_price")) <= 0),
            "pending_count": sum(
                1 for item in items
                if str(item.get("status") or "") in {"待补参数", "缺传统参考", "待AI报价", "缺重量", "缺材质", "模型超时", "AI未配置", "AI接口异常", "估重待复核", "名称规格推断报价"}
            ),
            "high_gap_count": sum(
                1 for item in items
                if FinanceSkillQuoteService._to_number(item.get("finance_route_unit_price")) > 0
                and FinanceSkillQuoteService._to_number(item.get("ai_route_unit_price")) > 0
                and abs(FinanceSkillQuoteService._to_number(item.get("route_gap_unit_price"))) / max(
                    FinanceSkillQuoteService._to_number(item.get("finance_route_unit_price")),
                    FinanceSkillQuoteService._to_number(item.get("ai_route_unit_price")),
                    1.0,
                ) >= 0.15
            ),
        }

    @staticmethod
    def _analyze_price_gap(item: dict) -> str:
        volume_summary = str(item.get("volume_pricing_summary") or "").strip()
        finance_unit = FinanceSkillQuoteService._to_number(item.get("finance_route_unit_price"))
        ai_unit = FinanceSkillQuoteService._to_number(item.get("ai_route_unit_price"))
        if finance_unit <= 0 and ai_unit <= 0:
            base = "传统参考和基准报价都未形成有效价格。"
            return f"{volume_summary}；{base}" if volume_summary else base
        if finance_unit <= 0:
            base = "传统路线缺少采购参考，当前由 AI 结合 skills 知识内容生成报价补位。"
            return f"{volume_summary}；{base}" if volume_summary else base
        if ai_unit <= 0:
            ai_status = str(item.get("ai_route_status") or "").strip()
            ai_reason = str(item.get("ai_route_reasoning") or "").strip()
            if ai_status in {"缺重量", "缺材质", "模型超时", "AI未配置", "AI接口异常"}:
                base = f"基准报价当前未形成有效结果：{ai_reason or ai_status}。"
                return f"{volume_summary}；{base}" if volume_summary else base
            if ai_reason:
                base = f"基准报价当前未形成有效结果：{ai_reason}"
                return f"{volume_summary}；{base}" if volume_summary else base
            base = "基准报价当前未形成有效结果。"
            return f"{volume_summary}；{base}" if volume_summary else base
        if FinanceSkillQuoteService._to_number(item.get("ai_estimated_weight_kg")) > 0:
            base = "基准报价已按相近物料估重后形成，建议优先补齐原始重量再复核。"
            return f"{volume_summary}；{base}" if volume_summary else base
        gap_ratio = abs(ai_unit - finance_unit) / max(finance_unit, ai_unit, 1.0)
        if gap_ratio < 0.08:
            base = "传统报价与基准报价接近。"
            return f"{volume_summary}；{base}" if volume_summary else base
        base = "传统报价与基准报价存在明显差异，建议复核。"
        return f"{volume_summary}；{base}" if volume_summary else base

    @staticmethod
    def _item_status(item: dict) -> str:
        finance_unit = FinanceSkillQuoteService._to_number(item.get("finance_route_unit_price"))
        ai_unit = FinanceSkillQuoteService._to_number(item.get("ai_route_unit_price"))
        if finance_unit <= 0 and ai_unit <= 0:
            return "待补参数"
        if finance_unit <= 0:
            return "缺传统参考"
        if ai_unit <= 0:
            ai_status = str(item.get("ai_route_status") or "").strip()
            if ai_status in {"缺重量", "缺材质", "模型超时", "AI未配置", "AI接口异常"}:
                return ai_status
            return "待AI报价"
        ai_status = str(item.get("ai_route_status") or "").strip()
        if ai_status == "名称规格推断报价":
            return ai_status
        if FinanceSkillQuoteService._to_number(item.get("ai_estimated_weight_kg")) > 0:
            return "双路线可比" if FinanceSkillQuoteService._is_piece_pricing_eligible(item) else "估重待复核"
        gap_ratio = abs(ai_unit - finance_unit) / max(finance_unit, ai_unit, 1.0)
        return "价差待复核" if gap_ratio >= 0.15 else "双路线可比"

    @staticmethod
    def _is_stator_winding_component(item: dict) -> bool:
        combined = " ".join(
            str(item.get(field) or "").strip().lower()
            for field in ("name", "spec", "material", "material_original", "process")
        )
        if not combined:
            return False
        has_stator_assembly_name = any(keyword in combined for keyword in ("定子组件", "定子总成", "浸漆定子", "定子绕组"))
        has_winding_traits = any(keyword in combined for keyword in ("漆包线", "铜线", "扁铜线", "铜", "绕线", "嵌线", "vpi", "浸漆"))
        if has_stator_assembly_name and has_winding_traits:
            return True
        if any(keyword in combined for keyword in ("定子总成", "定子组件", "浸漆定子")):
            return True
        return False

    @staticmethod
    def _is_stator_core_component(item: dict) -> bool:
        combined = " ".join(
            str(item.get(field) or "").strip().lower()
            for field in ("name", "spec", "material", "material_original", "process")
        )
        if not combined:
            return False
        if any(keyword in combined for keyword in ("定子总成", "定子组件", "转子总成", "转子组件", "浸漆定子", "定子绕组")):
            return False
        return (
            any(keyword in combined for keyword in ("定子铁芯", "转子铁芯", "铁芯"))
            and any(keyword in combined for keyword in ("35w", "硅钢", "b30ahv"))
        )

    @staticmethod
    def _is_rotor_assembly_component(item: dict) -> bool:
        combined = " ".join(
            str(item.get(field) or "").strip().lower()
            for field in ("name", "spec", "material", "material_original", "process")
        )
        if not combined:
            return False
        if any(keyword in combined for keyword in ("转子总成", "转子组件", "磁钢转子")):
            return True
        return (
            any(keyword in combined for keyword in ("转子总成", "转子组件", "磁钢转子", "转子"))
            and any(keyword in combined for keyword in ("磁钢", "钕铁硼", "动平衡", "铸铝", "嵌铜", "转轴", "钢轴"))
        )

    @classmethod
    def _should_lock_skill_primary(cls, item: dict) -> bool:
        rule_unit = cls._to_number(item.get("changjiang_route_unit_price"))
        if rule_unit <= 0:
            return False
        return cls._is_stator_winding_component(item) or cls._is_stator_core_component(item)

    @classmethod
    def _resolve_stator_winding_wire_variant(cls, item: dict) -> str:
        combined = cls._build_item_matching_text(item)
        if any(keyword in combined for keyword in ("扁线", "扁铜线", "hairpin")):
            return "flat"
        if any(keyword in combined for keyword in ("圆线", "漆包圆线", "铜线", "漆包线")):
            return "round"
        return "round"

    @classmethod
    def _resolve_stator_winding_locked_price(cls, item: dict) -> tuple[float, str]:
        rule_unit = cls._to_number(item.get("changjiang_route_unit_price"))
        if rule_unit <= 0 or not cls._is_stator_winding_component(item):
            return rule_unit, ""
        material_cost = cls._to_number(item.get("changjiang_material_cost"))
        process_cost = cls._to_number(item.get("changjiang_process_cost"))
        if material_cost <= 0 and process_cost <= 0:
            return rule_unit, ""
        if material_cost <= 0:
            material_cost = rule_unit * 0.45
        if process_cost <= 0:
            process_cost = max(rule_unit - material_cost, 0.0)
        wire_variant = cls._resolve_stator_winding_wire_variant(item)
        process_multiplier = 1.12 if wire_variant == "round" else 1.0
        adjusted = round(material_cost + process_cost * process_multiplier, 4)
        if adjusted <= 0:
            adjusted = rule_unit
        label = "圆线" if wire_variant == "round" else "扁线"
        note = f"定子总成按{label}工艺口径重算：材料 {material_cost:.2f} + 工艺 {process_cost:.2f} × {process_multiplier:.2f} = {adjusted:.2f} 元"
        return adjusted, note

    @classmethod
    def _resolve_stator_winding_mass_production_quote(cls, item: dict) -> dict:
        if not cls._is_stator_winding_component(item):
            return {}
        annual_volume = cls._to_int(item.get("annual_volume"))
        if annual_volume <= 0:
            return {}
        combined = cls._build_item_matching_text(item)
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_name_spec_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if actual_weight <= 0:
            actual_weight = 4.8
        sample_unit = cls._to_number(item.get("ai_route_unit_price") or item.get("changjiang_route_unit_price"))
        if sample_unit <= 0:
            sample_unit = max(680.0, actual_weight * 118.0 + 260.0)

        diameter_mm = cls._extract_precision_housing_diameter_mm(item)
        length_mm = cls._extract_precision_housing_length_mm(item)
        normalized_material = cls._normalize_material_for_skills(item.get("material"))
        uses_copper = any(token in combined for token in ("铜", "铜线", "漆包线", "扁铜线")) or "铜" in normalized_material
        has_vpi = any(token in combined for token in ("vpi", "浸漆", "真空压力浸漆"))
        has_insertion = any(token in combined for token in ("嵌线", "绕线", "线圈"))
        has_stamping = any(token in combined for token in ("冲片", "叠压", "铁芯"))
        wire_variant = cls._resolve_stator_winding_wire_variant(item)
        winding_process_multiplier = 1.12 if wire_variant == "round" else 1.0

        material_rate = 41.0 if uses_copper else 34.0
        material_fee = actual_weight * material_rate
        winding_fee = (78.0 + actual_weight * 20.0) * winding_process_multiplier
        insertion_fee = (46.0 + actual_weight * 12.0 if has_insertion else 32.0 + actual_weight * 8.0) * winding_process_multiplier
        vpi_fee = 38.0 + actual_weight * 8.5 if has_vpi else 16.0 + actual_weight * 4.5
        core_pack_fee = 22.0 + actual_weight * 5.5 if has_stamping else 0.0
        feature_fee = 0.0
        tooling_cost = 68000.0 + actual_weight * 3600.0
        if diameter_mm >= 180:
            feature_fee += 18.0
            tooling_cost += 12000.0
        if length_mm >= 120:
            feature_fee += 12.0
            tooling_cost += 8000.0
        if has_vpi:
            tooling_cost += 9000.0
        if has_insertion:
            tooling_cost += 6000.0

        raw_unit_price = round(material_fee + winding_fee + insertion_fee + vpi_fee + core_pack_fee + feature_fee, 4)
        unit_price, adjusted_for_advantage = cls._ensure_mass_tooling_advantage(sample_unit, raw_unit_price, 0.82)
        tooling_cost = round(tooling_cost, 4)
        unit_saving = max(sample_unit - unit_price, 0.0)
        break_even_volume = 0
        if unit_saving > 0:
            break_even_volume = max(1, int(tooling_cost / unit_saving))
            if tooling_cost > break_even_volume * unit_saving:
                break_even_volume += 1
        advantage_text = ""
        if adjusted_for_advantage:
            advantage_text = f"；已按量产单价需显著低于样品/小批口径压至样品价的 {unit_price / sample_unit:.0%}"
        conservative_discount, aggressive_discount = cls._mass_tooling_discount_fallback(annual_volume)
        conservative_unit = round(unit_price * (1.0 - conservative_discount), 4)
        aggressive_unit = round(unit_price * (1.0 - aggressive_discount), 4)
        volume_tier_label = cls._describe_volume_tier_label(annual_volume)
        wire_variant_label = "圆线" if wire_variant == "round" else "扁线"
        volume_pricing_summary = (
            f"量产口径（{annual_volume}套/年，{volume_tier_label}档）："
            f"基准 {unit_price:.2f} / 保守 {conservative_unit:.2f} / 激进 {aggressive_unit:.2f} 元"
        )
        note = (
            f"定子绕组/总成量产工装口径（{annual_volume}套/年，{wire_variant_label}）：当前单件按绕线工装、嵌线治具、VPI批量化后工艺计 {unit_price:.2f} 元，"
            f"不把开模费 {tooling_cost:.2f} 元并入当前产品总价；样品/小批口径单价约 {sample_unit:.2f} 元，"
            f"当年产量大于 {break_even_volume} 套时，量产累计收益开始大于样品/小批，量产方案整体更划算{advantage_text}。"
        )
        return {
            "unit_price": unit_price,
            "mass_tooling_unit_price": unit_price,
            "tooling_cost": tooling_cost,
            "break_even_volume": break_even_volume,
            "sample_machining_unit_price": round(sample_unit, 4),
            "mass_process_route": "绕线工装+嵌线/VPI治具",
            "volume_pricing_summary": volume_pricing_summary,
            "basis": f"定子总成按{wire_variant_label}铜耗+绕线嵌线+VPI浸漆烘干+工装治具批量化测算，开模费单列展示",
            "wire_variant": wire_variant,
            "note": note,
        }

    @classmethod
    def _resolve_rotor_assembly_mass_production_quote(cls, item: dict) -> dict:
        if not cls._is_rotor_assembly_component(item):
            return {}
        annual_volume = cls._to_int(item.get("annual_volume"))
        if annual_volume <= 0:
            return {}
        combined = cls._build_item_matching_text(item)
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_name_spec_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if actual_weight <= 0:
            actual_weight = 8.5
        sample_unit = cls._to_number(item.get("ai_route_unit_price") or item.get("changjiang_route_unit_price"))
        if sample_unit <= 0:
            sample_unit = max(620.0, actual_weight * 28.0 + 320.0)

        has_magnet = any(token in combined for token in ("磁钢", "钕铁硼"))
        has_casting = any(token in combined for token in ("铸铝", "嵌铜"))
        has_balance = any(token in combined for token in ("动平衡", "平衡校正"))
        has_core = any(token in combined for token in ("冲压", "叠压", "硅钢"))
        diameter_mm = cls._extract_precision_housing_diameter_mm(item)

        material_fee = actual_weight * 18.5
        core_fee = 26.0 + actual_weight * 3.6 if has_core else 0.0
        casting_fee = 32.0 + actual_weight * 4.2 if has_casting else 14.0 + actual_weight * 2.5
        magnet_fee = 48.0 + actual_weight * 5.4 if has_magnet else 0.0
        balance_fee = 18.0 + actual_weight * 1.8 if has_balance else 8.0
        assembly_fee = 24.0 + actual_weight * 2.4
        feature_fee = 0.0
        tooling_cost = 52000.0 + actual_weight * 2400.0
        if diameter_mm >= 180:
            feature_fee += 12.0
            tooling_cost += 10000.0
        if has_magnet:
            tooling_cost += 12000.0
        if has_casting:
            tooling_cost += 9000.0
        if has_balance:
            tooling_cost += 5000.0

        raw_unit_price = round(material_fee + core_fee + casting_fee + magnet_fee + balance_fee + assembly_fee + feature_fee, 4)
        unit_price, adjusted_for_advantage = cls._ensure_mass_tooling_advantage(sample_unit, raw_unit_price, 0.78)
        tooling_cost = round(tooling_cost, 4)
        unit_saving = max(sample_unit - unit_price, 0.0)
        break_even_volume = 0
        if unit_saving > 0:
            break_even_volume = max(1, int(tooling_cost / unit_saving))
            if tooling_cost > break_even_volume * unit_saving:
                break_even_volume += 1
        conservative_discount, aggressive_discount = cls._mass_tooling_discount_fallback(annual_volume)
        conservative_unit = round(unit_price * (1.0 - conservative_discount), 4)
        aggressive_unit = round(unit_price * (1.0 - aggressive_discount), 4)
        volume_tier_label = cls._describe_volume_tier_label(annual_volume)
        advantage_text = ""
        if adjusted_for_advantage:
            advantage_text = f"；已按量产单价需显著低于样品/小批口径压至样品价的 {unit_price / sample_unit:.0%}"
        note = (
            f"转子总成量产工装口径（{annual_volume}套/年）：当前单件按转子压铸/嵌铜、磁钢装配、动平衡校正后工艺计 {unit_price:.2f} 元，"
            f"不把开模费 {tooling_cost:.2f} 元并入当前产品总价；样品/小批口径单价约 {sample_unit:.2f} 元，"
            f"当年产量大于 {break_even_volume} 套时，量产累计收益开始大于样品/小批，量产方案整体更划算{advantage_text}。"
        )
        return {
            "unit_price": unit_price,
            "mass_tooling_unit_price": unit_price,
            "tooling_cost": tooling_cost,
            "break_even_volume": break_even_volume,
            "sample_machining_unit_price": round(sample_unit, 4),
            "mass_process_route": "转子压铸/嵌铜+磁钢装配治具",
            "volume_pricing_summary": (
                f"量产口径（{annual_volume}套/年，{volume_tier_label}档）："
                f"基准 {unit_price:.2f} / 保守 {conservative_unit:.2f} / 激进 {aggressive_unit:.2f} 元"
            ),
            "basis": "转子总成按硅钢叠压+压铸/嵌铜+磁钢装配+动平衡校正+工装治具批量化测算，开模费单列展示",
            "note": note,
        }

    @classmethod
    def _resolve_stator_core_mass_production_quote(cls, item: dict) -> dict:
        if not cls._is_stator_core_component(item) or cls._is_stator_winding_component(item):
            return {}
        annual_volume = cls._to_int(item.get("annual_volume"))
        if annual_volume <= 0:
            return {}
        combined = cls._build_item_matching_text(item)
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_name_spec_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if actual_weight <= 0:
            return {}
        sample_unit = cls._to_number(item.get("ai_route_unit_price") or item.get("changjiang_route_unit_price"))
        if sample_unit <= 0:
            if "定子铁芯" in combined:
                sample_unit = max(38.0, actual_weight * 8.6 + 12.0)
            elif "转子铁芯" in combined:
                sample_unit = max(24.0, actual_weight * 10.8 + 7.5)
            else:
                sample_unit = max(28.0, actual_weight * 9.4 + 10.0)
        material_text = cls._normalize_material_for_skills(item.get("material"))
        if "B30AHV1500" in combined.upper() or "B30AHV1500" in material_text.upper():
            silicon_rate = 18.5
        elif any(token in combined.upper() for token in ("50WW", "35WW", "电工钢", "硅钢")) or "硅钢" in material_text:
            silicon_rate = 12.8
        else:
            silicon_rate = 10.5
        stamping_fee = 6.0 + actual_weight * 2.6
        stacking_fee = 4.5 + actual_weight * 1.9
        feature_fee = 0.0
        tooling_cost = 26000.0 + actual_weight * 1800.0
        if "V+1" in combined or "双V" in combined or "V＋1" in combined:
            feature_fee += 6.0 + actual_weight * 0.5
            tooling_cost += 9000.0
        if "定子铁芯" in combined:
            stacking_fee += 5.0
            tooling_cost += 8000.0
        if "转子铁芯" in combined:
            feature_fee += 4.0
            tooling_cost += 5000.0
        if "铆接" in combined or "焊接" in combined:
            feature_fee += 3.0
            tooling_cost += 3000.0
        material_fee = actual_weight * silicon_rate
        unit_price = round(material_fee + stamping_fee + stacking_fee + feature_fee, 4)
        unit_price, adjusted_for_advantage = cls._ensure_mass_tooling_advantage(sample_unit, unit_price, 0.72)
        tooling_cost = round(tooling_cost, 4)
        unit_saving = max(sample_unit - unit_price, 0.0)
        break_even_volume = 0
        if unit_saving > 0:
            break_even_volume = max(1, int(tooling_cost / unit_saving))
            if tooling_cost > break_even_volume * unit_saving:
                break_even_volume += 1
        part_label = "定子铁芯" if "定子铁芯" in combined else "转子铁芯" if "转子铁芯" in combined else "铁芯"
        advantage_text = ""
        if adjusted_for_advantage:
            advantage_text = f"；已按量产单价需显著低于样品冲压叠压口径压至样品价的 {unit_price / sample_unit:.0%}"
        volume_tier_label = cls._describe_volume_tier_label(annual_volume)
        volume_pricing_summary = (
            f"量产口径（{annual_volume}套/年，{volume_tier_label}档）："
            f"基准 {unit_price:.2f} / 保守 {round(unit_price * 0.96, 4):.2f} / 激进 {round(unit_price * 0.92, 4):.2f} 元"
        )
        note = (
            f"{part_label}量产冲压模口径（{annual_volume}套/年）：当前单件按冲压模/叠压模后工艺计 {unit_price:.2f} 元，"
            f"不把开模费 {tooling_cost:.2f} 元并入当前产品总价；样品/小批冲压叠压单价约 {sample_unit:.2f} 元，"
            f"当年产量大于 {break_even_volume} 套时，量产累计收益开始大于样品冲压叠压，量产方案整体更划算{advantage_text}。"
        )
        return {
            "unit_price": unit_price,
            "mass_tooling_unit_price": unit_price,
            "tooling_cost": tooling_cost,
            "break_even_volume": break_even_volume,
            "sample_machining_unit_price": round(sample_unit, 4),
            "mass_process_route": "冲压模+叠压",
            "volume_pricing_summary": volume_pricing_summary,
            "basis": f"{part_label}按硅钢材料费+冲压费+叠压固化费+结构附加费测算，开模费单列展示",
            "note": note,
        }

    @classmethod
    def _resolve_stator_core_locked_price(cls, item: dict) -> tuple[float, str]:
        rule_unit = cls._to_number(item.get("changjiang_route_unit_price"))
        if rule_unit <= 0 or not cls._is_stator_core_component(item):
            return rule_unit, ""
        combined = cls._build_item_matching_text(item)
        weight = cls._to_number(item.get("effective_weight_kg") or item.get("weight_kg"))
        diameter_mm = cls._extract_precision_housing_diameter_mm(item)
        length_mm = cls._extract_precision_housing_length_mm(item)
        if weight <= 0:
            return rule_unit, ""
        if "b30ahv1500" not in combined:
            return rule_unit, ""
        if diameter_mm < 190 and length_mm < 120 and "双v" not in combined:
            return rule_unit, ""
        premium_rate = 19.6
        if diameter_mm >= 190:
            premium_rate += 0.6
        if length_mm >= 120:
            premium_rate += 0.5
        if "双v" in combined or "双v" in str(item.get("spec") or "").lower():
            premium_rate += 0.35
        if weight >= 10:
            premium_rate += 0.25
        adjusted = round(max(rule_unit, weight * premium_rate), 4)
        if adjusted <= rule_unit:
            return rule_unit, ""
        reason = (
            f"B30AHV1500 大规格双V铁芯按高牌号硅钢+大吨位冲压叠压口径重估："
            f"{weight:.4f}kg × {premium_rate:.2f} 元/kg = {adjusted:.2f} 元"
        )
        return adjusted, reason

    @classmethod
    def _build_locked_skill_reasoning(cls, item: dict) -> str:
        material_cost = cls._to_number(item.get("changjiang_material_cost"))
        process_cost = cls._to_number(item.get("changjiang_process_cost"))
        rule_unit = cls._to_number(item.get("changjiang_route_unit_price"))
        process_rule = str(item.get("ai_process_rule_reference") or item.get("ai_process_rule_label") or "").strip()
        process_rule_label = str(item.get("ai_process_rule_label") or "").strip()
        weight = cls._to_number(item.get("effective_weight_kg") or item.get("weight_kg"))
        qty = cls._to_number(item.get("qty")) or 1.0
        if cls._is_stator_winding_component(item):
            component_label = '定子绕组组件'
        elif cls._is_stator_core_component(item):
            component_label = '铁芯组件'
        else:
            component_label = '电机组件'
        parts = [
            f'锁定{component_label}优先采用 skills 规则价 {rule_unit:.2f} 元',
            f'规则拆分 {rule_unit:.2f} = 材料 {material_cost:.2f} + 工艺 {process_cost:.2f}（按脚本输出）',
        ]
        if qty > 1:
            parts.append(f'数量 {qty:.4g} 件：{rule_unit:.2f} × {qty:.4g} = {rule_unit * qty:.2f} 元')
        if weight > 0:
            parts.append(f'计价重量 {weight:.4f} kg。')
        if process_rule:
            rule_text = f'工艺规则：{process_rule}'
            if process_rule_label and process_rule_label != process_rule:
                rule_text += f'（单价标签：{process_rule_label}）'
            parts.append(f"{rule_text}?")
        return " ".join(parts)

    @staticmethod
    def _source_tag(item: dict) -> str:
        tags: list[str] = []
        finance_refs: list[str] = []

        if FinanceSkillQuoteService._to_number(item.get("current_unit_price")) > 0:
            finance_refs.append("Excel采购参考")
        if FinanceSkillQuoteService._to_number(item.get("kingdee_reference_price")) > 0:
            finance_refs.append("金蝶采购参考")
        if FinanceSkillQuoteService._to_number(item.get("target_unit_price")) > 0:
            finance_refs.append("目标价参考")
        if finance_refs:
            tags.extend(finance_refs)

        if FinanceSkillQuoteService._to_number(item.get("ai_route_unit_price")) > 0:
            tags.append("AI基准报价")
        if FinanceSkillQuoteService._to_number(item.get("ai_estimated_weight_kg")) > 0:
            tags.append("AI估重")

        return " / ".join(tags) if tags else "-"

    def _build_ai_prompt_item(
        self,
        item: dict,
        items: list[dict],
        production_mode: str,
        annual_volume: int,
        ai_skill_context_map: dict[str, dict],
    ) -> tuple[dict, str]:
        merged = dict(item)
        merged["production_mode"] = production_mode
        merged["annual_volume"] = annual_volume
        context_key = str(item.get("code") or "").strip() or str(item.get("name") or "").strip()
        if context_key and context_key in ai_skill_context_map:
            merged["ai_skill_context"] = dict(ai_skill_context_map.get(context_key) or {})
        estimated_weight_kg, estimated_weight_note = self._estimate_similar_weight(item, items)
        merged["ai_name_spec_fallback"] = self._is_name_based_ai_fallback_eligible(merged)
        merged["name_spec_price_band"] = self._resolve_name_spec_price_band(merged)
        merged["name_spec_weight_band"] = self._resolve_name_spec_weight_band(merged)
        estimated_weight_kg, estimated_weight_note = self._apply_name_spec_weight_band(
            merged,
            estimated_weight_kg,
            estimated_weight_note,
        )
        if estimated_weight_kg > 0 and self._to_number(merged.get("weight_kg")) <= 0:
            merged["weight_kg"] = estimated_weight_kg
            merged["ai_estimated_weight_kg"] = estimated_weight_kg
            merged["ai_estimated_weight_note"] = estimated_weight_note
        return merged, estimated_weight_note

    def _build_ai_skill_context_map(
        self,
        *,
        items: list[dict],
        line_csv: Path,
        grouped_csv: Path,
        snapshot_json: Path,
        volume_outputs: dict,
        production_mode: str,
        annual_volume: int,
        script_plan: dict,
    ) -> dict[str, dict]:
        grouped_rows = self._read_csv_dicts(grouped_csv)
        grouped_by_code = {
            str(row.get('物料编码') or "").strip(): row
            for row in grouped_rows
            if str(row.get('物料编码') or "").strip()
        }
        line_rows = self._read_csv_dicts(line_csv)
        line_meta_by_code: dict[str, dict[str, list[str]]] = {}
        for row in line_rows:
            code = str(row.get('物料编码') or "").strip()
            if not code:
                continue
            meta = line_meta_by_code.setdefault(code, {"process_rules": [], "process_units": []})
            process_rule = str(row.get('工艺') or "").strip()
            process_unit = str(row.get('工艺单价') or "").strip()
            if process_rule and process_rule not in meta["process_rules"]:
                meta["process_rules"].append(process_rule)
            if process_unit and process_unit not in meta["process_units"]:
                meta["process_units"].append(process_unit)
        snapshot = self._read_json(snapshot_json)
        volume_detail_rows = self._read_volume_detail_rows(volume_outputs)
        volume_by_code = {
            str(row.get('物料编码') or "").strip(): row
            for row in volume_detail_rows
            if str(row.get('物料编码') or "").strip()
        }
        volume_by_name = {
            str(row.get('物料') or "").strip(): row
            for row in volume_detail_rows
            if str(row.get('物料') or "").strip()
        }
        registry = list(script_plan.get("selected_scripts") or script_plan.get("registry") or self._build_script_registry(production_mode, annual_volume))

        context_map: dict[str, dict] = {}
        for item in items:
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or "").strip()
            key = code or name
            if not key:
                continue
            grouped = grouped_by_code.get(code, {})
            line_meta = line_meta_by_code.get(code, {})
            qty = self._to_number(item.get("qty")) or 1.0
            rule_total = self._to_number(grouped.get('基础估算总价'))
            material_cost = self._to_number(grouped.get('基础材料合计'))
            process_cost = self._to_number(grouped.get('基础工艺合计'))
            rule_unit = (rule_total / qty) if qty > 0 else rule_total
            volume_row = volume_by_code.get(code) or volume_by_name.get(name) or {}
            baseline_total = self._to_number(volume_row.get('基准总价'))
            conservative_total = self._to_number(volume_row.get('保守总价'))
            aggressive_total = self._to_number(volume_row.get('激进总价'))
            context_map[key] = {
                "script_registry": registry,
                "script_plan_reason": str(script_plan.get("reason") or "").strip(),
                "rule_unit_price": rule_unit,
                "material_cost": material_cost,
                "process_cost": process_cost,
                "process_rule": " / ".join(line_meta.get("process_rules") or []),
                "process_unit_label": " / ".join(line_meta.get("process_units") or []),
                "excel_current_unit_price": self._to_number(item.get("current_unit_price")),
                "excel_target_unit_price": self._to_number(item.get("target_unit_price")),
                "market_snapshot_count": len(snapshot) if isinstance(snapshot, dict) else 0,
                "volume_baseline_unit_price": (baseline_total / qty) if qty > 0 else baseline_total,
                "volume_conservative_unit_price": (conservative_total / qty) if qty > 0 else conservative_total,
                "volume_aggressive_unit_price": (aggressive_total / qty) if qty > 0 else aggressive_total,
            }
        return context_map

    def _plan_skill_scripts(
        self,
        items: list[dict],
        *,
        production_mode: str,
        annual_volume: int,
    ) -> dict:
        registry = self._build_script_registry(production_mode, annual_volume)
        default_selected = list(registry)
        plan_input = {
            "registry": registry,
            "production_mode": production_mode,
            "annual_volume": annual_volume,
            "item_count": len(items),
            "need_gap": True,
            "need_format": True,
            "need_volume": production_mode == "mass" and annual_volume > 0,
            "workflow_hint": self.ai_route_service.load_skill_workflow_hint(),
        }
        try:
            planned = self.ai_route_service.plan_script_usage(plan_input)
        except Exception as exc:
            planned = {
                "selected_scripts": default_selected,
                "reason": f"脚本规划器异常，已回退默认脚本链路：{exc}",
                "source": "heuristic-fallback",
            }

        selected = [str(name).strip() for name in (planned.get("selected_scripts") or []) if str(name).strip() in registry]
        if "price_bom_xlsx.py" not in selected:
            selected.insert(0, "price_bom_xlsx.py")
        if production_mode == "mass" and annual_volume > 0 and "model_volume_pricing.py" not in selected:
            selected.append("model_volume_pricing.py")

        ordered_selected = [name for name in registry if name in selected]
        if not ordered_selected:
            ordered_selected = default_selected

        reason = str(planned.get("reason") or "").strip()
        if not reason:
            reason = "已按默认脚本白名单执行报价链路"
        return {
            "registry": registry,
            "selected_scripts": ordered_selected,
            "reason": reason,
            "source": str(planned.get("source") or "heuristic-fallback").strip(),
        }

    @staticmethod
    def _build_script_registry(production_mode: str, annual_volume: int) -> list[str]:
        registry = [
            "price_bom_xlsx.py",
            "analyze_pricing_gaps.py",
            "format_estimate_workbook.py",
        ]
        if production_mode == "mass" and annual_volume > 0:
            registry.append("model_volume_pricing.py")
        return registry

    @staticmethod
    def _empty_ai_result(
        reason: str,
        *,
        status: str = "待AI报价",
        estimated_weight_kg: float = 0.0,
        estimated_weight_note: str = "",
    ) -> dict:
        return {
            "ai_route_unit_price": 0.0,
            "ai_route_confidence": 0.0,
            "ai_route_reasoning": reason,
            "ai_route_status": status,
            "ai_route_process_guess": "",
            "ai_route_material_guess": "",
            "ai_estimated_weight_kg": estimated_weight_kg,
            "ai_estimated_weight_note": estimated_weight_note,
            "ai_inferred_process_reference": "",
            "ai_inferred_material_reference": "",
            "ai_inferred_weight_reference": 0.0,
            "ai_inference_confidence": 0.0,
            "ai_second_stage_used": False,
            "ai_material_cost_reference": 0.0,
            "ai_process_cost_reference": 0.0,
            "ai_process_rule_reference": "",
            "ai_process_rule_label": "",
        }

    @classmethod
    def _script_first_ai_fallback(cls, item: dict) -> dict | None:
        context = item.get("ai_skill_context") or {}
        rule_unit_price = cls._to_number(context.get("rule_unit_price"))
        if rule_unit_price <= 0:
            return None
        band = item.get("name_spec_price_band") or {}
        band_low = cls._to_number(band.get("low"))
        if band_low > 0 and rule_unit_price < band_low:
            return None
        reasoning_parts = [f'优先采用 skills 规则报价 {rule_unit_price:.2f} 元。']
        process_inference_note = str(item.get("process_inference_note") or "").strip()
        if process_inference_note:
            reasoning_parts.append(f"{process_inference_note}?")
        material_cost = cls._to_number(context.get("material_cost"))
        process_cost = cls._to_number(context.get("process_cost"))
        if cls._to_number(context.get("volume_baseline_unit_price")) > 0:
            reasoning_parts.append(
                '量产参考：'
                f"{cls._to_number(context.get('volume_baseline_unit_price')):.2f}/"
                f"{cls._to_number(context.get('volume_conservative_unit_price')):.2f}/"
                f"{cls._to_number(context.get('volume_aggressive_unit_price')):.2f} \u5143"
            )
        return {
            "ai_route_unit_price": rule_unit_price,
            "ai_route_confidence": 0.9,
            "ai_route_reasoning": "".join(reasoning_parts),
            "ai_route_status": "AI报价",
            "ai_route_source": "skills-script-first",
            "ai_route_process_guess": "",
            "ai_route_material_guess": "",
            "ai_inferred_process_reference": "",
            "ai_inferred_material_reference": "",
            "ai_inferred_weight_reference": 0.0,
            "ai_inference_confidence": 0.0,
            "ai_second_stage_used": False,
            "ai_material_cost_reference": material_cost,
            "ai_process_cost_reference": process_cost,
            "ai_process_rule_reference": str(context.get("process_rule") or "").strip(),
            "ai_process_rule_label": str(context.get("process_unit_label") or "").strip(),
        }

    @staticmethod
    def _merge_script_first_reasoning(base_reason: str, ai_reason: str, *, append_ai_reason: bool = True) -> str:
        base_text = str(base_reason or "").strip()
        ai_text = str(ai_reason or "").strip()
        if base_text and ai_text and append_ai_reason:
            return f"{base_text} AI补充：{ai_text}".strip()
        return base_text or ai_text

    @staticmethod
    def _should_append_ai_supplement(ai_reason: str) -> bool:
        text = str(ai_reason or "").strip()
        lower = text.lower()
        if not text:
            return False
        blocked_keywords = (
            "未找到",
            "无法基于现有数据",
            "请补充",
            "缺重量",
            "缺材质",
            "输入内容为空",
            "缺少具体的 bom",
            "未提供具体的 bom",
            "bom 行项目详情",
            "缺少物料名称",
            "无法进行准确估价",
            "无法进行成本测算",
            "无法执行计价逻辑",
            "ai接口",
            "接口异常",
            "模型超时",
            "格式异常",
            "未返回有效价格",
            "待ai报价",
        )
        return not any(keyword in text or keyword in lower for keyword in blocked_keywords)

    @staticmethod
    def _classify_ai_missing_context(item: dict) -> tuple[str, str]:
        has_weight = FinanceSkillQuoteService._to_number(item.get("weight_kg")) > 0
        has_material = bool(str(item.get("material") or "").strip())
        if not has_weight and not has_material:
            if FinanceSkillQuoteService._is_name_based_ai_fallback_eligible(item):
                return "", ""
            return "缺重量、缺材质：未找到可用于 AI 估价的基础字段，请补充重量和材质后重新核算", "缺重量"
        if not has_weight:
            if FinanceSkillQuoteService._is_piece_pricing_eligible(item):
                return "", ""
            return "缺重量：未找到同材质相近物料可估重，请在金蝶维护净重/毛重或在 Excel 补重量后重新核算", "缺重量"
        if not has_material:
            if FinanceSkillQuoteService._is_name_based_ai_fallback_eligible(item):
                return "", ""
            return "缺材质：未找到可识别材质，请补充材质字段后重新核算", "缺材质"
        return "", ""

    @staticmethod
    def _is_piece_pricing_eligible(item: dict) -> bool:
        context = item.get("ai_skill_context") or {}
        rule_unit_price = FinanceSkillQuoteService._to_number(context.get("rule_unit_price"))
        material_cost = FinanceSkillQuoteService._to_number(context.get("material_cost"))
        process_cost = FinanceSkillQuoteService._to_number(context.get("process_cost"))
        if rule_unit_price > 0 and process_cost > 0 and material_cost <= 0:
            return True

        combined = " ".join(
            str(item.get(field) or "").strip().lower()
            for field in ("name", "spec", "process", "material")
        )
        piece_keywords = (
            "标准件", "轴承", "螺钉", "螺母", "螺栓", "螺杆", "螺帽", "垫片", "垫圈", "卡簧", "挡圈",
            "护套", "密封圈", "o型圈", "油封", "密封垫", "波形弹簧", "弹簧", "线束", "导电环",
            "过滤器", "滤芯", "堵头", "橡胶堵头", "法兰", "轴法兰", "内六角", "内六角圆柱",
            "圆柱头", "圆柱销", "螺钉螺母", "机加工", "注塑", "激光切割", "线切割", "表面处理", "折弯",
        )
        return any(keyword in combined for keyword in piece_keywords)

    @classmethod
    def _has_reliable_ai_preinference(cls, item: dict) -> bool:
        confidence = cls._to_number(item.get("ai_inference_confidence"))
        if confidence < cls.INFERENCE_CONFIDENCE_THRESHOLD:
            return False
        if bool(item.get("ai_second_stage_used")) or bool(item.get("ai_preinferred_for_skills")):
            return True
        return any(
            str(item.get(field) or "").strip()
            for field in ("ai_inferred_process_reference", "ai_inferred_material_reference")
        ) or cls._to_number(item.get("ai_inferred_weight_reference")) > 0

    @classmethod
    def _should_prefer_name_spec_formula(cls, item: dict) -> bool:
        band = item.get("name_spec_price_band") or {}
        category = str(band.get("category") or "").strip()
        return category in {"电机精密拉伸机壳", "电机精密结构端盖", "高精轴类机加工件", "电机大线径线束", "电机壳体盖板类结构件"}

    @classmethod
    def _normalize_material_for_skills(cls, value: object) -> str:
        text = str(value or "").strip()
        lower = text.lower()
        if not text:
            return ""
        if "20crmnti" in lower:
            return "20CrMnTi"
        if "42crmo" in lower:
            return "42CrMo"
        if "40cr" in lower:
            return "40Cr"
        if "q235" in lower:
            return "Q235"
        if "qt450-10" in lower:
            return "QT450-10"
        if "gcr15" in lower:
            return "GCr15"
        if "adc12" in lower or "压铸铝" in text:
            return "ADC12"
        if "a356" in lower:
            return "A356"
        if "6063" in lower:
            return "6063-T5"
        if "6061" in lower:
            return "6061"
        if "b30ahv1500" in lower:
            return "B30AHV1500"
        if "b30ahv" in lower:
            return "B30AHV"
        if "35w" in lower:
            return "35W300"
        if "硅钢" in text:
            return "硅钢"
        if "304" in lower or "不锈钢" in text:
            return "304"
        if "pa66" in lower:
            return "PA66"
        if "pps" in lower:
            return "PPS"
        if "丁腈" in text or "nbr" in lower:
            return "NBR"
        if "氟橡胶" in text or "fkm" in lower:
            return "FKM"
        if "钕铁硼" in text or "ndfeb" in lower:
            return "钕铁硼"
        return text

    @staticmethod
    def _is_name_based_ai_fallback_eligible(item: dict) -> bool:
        name = str(item.get("name") or "").strip()
        spec = str(item.get("spec") or "").strip()
        code = str(item.get("code") or "").strip()
        material = str(item.get("material") or "").strip()
        process = str(item.get("process") or "").strip()
        non_empty = [value for value in (name, spec, code, material, process) if value and value != "未识别"]
        if len(non_empty) >= 2:
            return True
        combined = " ".join(non_empty).lower()
        fallback_keywords = (
            "弹簧", "线束", "过滤器", "滤芯", "密封", "垫", "护套", "卡簧", "挡圈",
            "机壳", "铁芯", "转子", "定子", "接线盒", "端盖", "油封", "胶圈",
            "导电环", "法兰", "轴法兰", "堵头", "橡胶堵头", "内六角", "圆柱", "口板", "盖板",
            "螺母", "螺钉", "螺栓", "螺杆",
        )
        return any(keyword in combined for keyword in fallback_keywords)


    @classmethod
    def _build_item_matching_text(cls, item: dict) -> str:
        return " ".join(
            str(item.get(field) or "").strip().lower()
            for field in ("name", "spec", "code", "material", "process", "product_spec", "product_context")
        )

    @classmethod
    def _extract_precision_shaft_length_mm(cls, item: dict) -> float:
        text = " ".join(
            str(item.get(field) or "").strip()
            for field in ("spec", "name", "process")
        )
        if not text:
            return 0.0
        match = cls.PRECISION_SHAFT_LENGTH_PATTERN.search(text)
        if match:
            return cls._to_number(match.group(1))
        values = [cls._to_number(value) for value in cls.PRECISION_SHAFT_ANY_LENGTH_PATTERN.findall(text)]
        values = [value for value in values if value >= 80.0]
        return max(values) if values else 0.0


    @staticmethod
    def _dedupe_overlapping_keywords(keywords: list[str]) -> list[str]:
        ordered = sorted({str(keyword).strip() for keyword in keywords if str(keyword).strip()}, key=len, reverse=True)
        kept: list[str] = []
        for keyword in ordered:
            if any(keyword in existing for existing in kept):
                continue
            kept.append(keyword)
        return kept

    @classmethod
    def _resolve_precision_shaft_traits(cls, item: dict) -> dict:
        combined = cls._build_item_matching_text(item)
        if not combined:
            return {}
        if any(keyword in combined for keyword in cls.PRECISION_SHAFT_EXCLUDE_KEYWORDS):
            return {}
        shaft_hit = any(keyword in combined for keyword in cls.PRECISION_SHAFT_NAME_KEYWORDS)
        if not shaft_hit:
            return {}

        length_mm = cls._extract_precision_shaft_length_mm(item)
        traits = {
            "material": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_SHAFT_MATERIAL_KEYWORDS if keyword in combined]),
            "heat_treatment": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_SHAFT_HEAT_TREATMENT_KEYWORDS if keyword in combined]),
            "grinding": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_SHAFT_GRINDING_KEYWORDS if keyword in combined]),
            "spline": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_SHAFT_SPLINE_KEYWORDS if keyword in combined]),
            "process": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_SHAFT_PROCESS_KEYWORDS if keyword in combined]),
            "length_mm": round(length_mm, 3) if length_mm > 0 else 0.0,
        }
        score = 0
        score += 2 if traits["material"] else 0
        score += 1 if traits["heat_treatment"] else 0
        score += 1 if traits["grinding"] else 0
        score += 1 if traits["spline"] else 0
        score += 1 if traits["process"] else 0
        score += 1 if length_mm >= 180 else 0
        if score < 3:
            return {}
        return traits

    @classmethod
    def _build_precision_shaft_basis(cls, traits: dict) -> str:
        parts: list[str] = []
        if traits.get("material"):
            parts.append(f"材质特征 {'/'.join(traits['material'])}")
        if traits.get("heat_treatment"):
            parts.append(f"热处理特征 {'/'.join(traits['heat_treatment'])}")
        if traits.get("grinding"):
            parts.append(f"磨削特征 {'/'.join(traits['grinding'])}")
        if traits.get("spline"):
            parts.append(f"花键/键槽特征 {'/'.join(traits['spline'])}")
        length_mm = cls._to_number(traits.get("length_mm"))
        if length_mm > 0:
            parts.append(f"长度约 {length_mm:.1f}mm")
        return "，".join(parts)

    @classmethod
    def _resolve_precision_shaft_price_band(cls, item: dict) -> dict:
        traits = cls._resolve_precision_shaft_traits(item)
        if not traits:
            return {}
        length_mm = cls._to_number(traits.get("length_mm"))
        if length_mm >= 240:
            low, high = 95.0, 165.0
        elif length_mm >= 180:
            low, high = 75.0, 140.0
        else:
            low, high = 55.0, 110.0
        basis = cls._build_precision_shaft_basis(traits)
        if basis:
            basis = f"识别为高精轴类机加工件：{basis}"
        else:
            basis = "识别为高精轴类机加工件"
        return {
            "category": "高精轴类机加工件",
            "low": round(low, 4),
            "high": round(high, 4),
            "basis": basis,
        }

    @classmethod
    def _resolve_precision_shaft_weight_band(cls, item: dict) -> dict:
        traits = cls._resolve_precision_shaft_traits(item)
        if not traits:
            return {}
        length_mm = cls._to_number(traits.get("length_mm"))
        if length_mm >= 240:
            low, high, default = 0.8, 4.0, 1.6
        elif length_mm >= 180:
            low, high, default = 0.45, 2.8, 1.1
        else:
            low, high, default = 0.2, 1.8, 0.65
        basis = cls._build_precision_shaft_basis(traits)
        if basis:
            basis = f"识别为高精轴类机加工件：{basis}"
        else:
            basis = "识别为高精轴类机加工件"
        return {
            "category": "高精轴类机加工件",
            "low": round(low, 4),
            "high": round(high, 4),
            "default": round(default, 4),
            "basis": basis,
        }

    @classmethod
    def _extract_precision_end_cover_diameter_mm(cls, item: dict) -> float:
        text = " ".join(
            str(item.get(field) or "").strip()
            for field in ("spec", "name", "process")
        )
        if not text:
            return 0.0
        normalized_text = re.sub(r"[\u03a6\u03c6\u00d8\u00f8]", "OD", text)
        for pattern in (cls.PRECISION_END_COVER_DIAMETER_PATTERN, cls.PRECISION_END_COVER_SUFFIX_DIAMETER_PATTERN):
            match = pattern.search(normalized_text)
            if match:
                value = cls._to_number(match.group(1))
                if value >= 80.0:
                    return value
        values = [cls._to_number(value) for value in cls.PRECISION_SHAFT_ANY_LENGTH_PATTERN.findall(normalized_text)]
        values = [value for value in values if value >= 100.0]
        return max(values) if values else 0.0

    @classmethod
    def _resolve_precision_end_cover_traits(cls, item: dict) -> dict:
        combined = cls._build_item_matching_text(item)
        if not combined:
            return {}
        if any(keyword in combined for keyword in cls.PRECISION_END_COVER_EXCLUDE_KEYWORDS):
            return {}
        if not any(keyword in combined for keyword in cls.PRECISION_END_COVER_NAME_KEYWORDS):
            return {}
        role = "后端盖" if "后端盖" in combined else "前端盖" if "前端盖" in combined else "端盖"
        diameter_mm = cls._extract_precision_end_cover_diameter_mm(item)
        traits = {
            "role": role,
            "material": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_END_COVER_MATERIAL_KEYWORDS if keyword in combined]),
            "casting": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_END_COVER_CASTING_KEYWORDS if keyword in combined]),
            "cnc": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_END_COVER_CNC_KEYWORDS if keyword in combined]),
            "sealing": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_END_COVER_SEALING_KEYWORDS if keyword in combined]),
            "diameter_mm": round(diameter_mm, 3) if diameter_mm > 0 else 0.0,
        }
        score = 2
        score += 2 if traits["material"] else 0
        score += 1 if traits["casting"] else 0
        score += 1 if traits["cnc"] else 0
        score += 1 if traits["sealing"] else 0
        score += 1 if diameter_mm >= 150 else 0
        if score < 5:
            sparse_but_clear_end_cover = (
                role in ("前端盖", "后端盖")
                and diameter_mm >= 180
                and bool(traits["casting"])
            )
            if not sparse_but_clear_end_cover:
                return {}
            traits["defaulted_precision_end_cover"] = True
        return traits

    @classmethod
    def _build_precision_end_cover_basis(cls, traits: dict) -> str:
        parts: list[str] = []
        role = str(traits.get("role") or "").strip()
        if role:
            parts.append(role)
        if traits.get("material"):
            parts.append(f"材质特征 {'/'.join(traits['material'])}")
        if traits.get("casting"):
            parts.append(f"铸造特征 {'/'.join(traits['casting'])}")
        if traits.get("cnc"):
            parts.append(f"精加工特征 {'/'.join(traits['cnc'])}")
        if traits.get("sealing"):
            parts.append(f"密封/表面处理特征 {'/'.join(traits['sealing'])}")
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        if diameter_mm > 0:
            parts.append(f"外径约 {diameter_mm:.1f}mm")
        if traits.get("defaulted_precision_end_cover"):
            parts.append("按前后端盖名称+大直径+铸造特征默认识别精密端盖")
        return "，".join(parts)

    @classmethod
    def _resolve_precision_end_cover_price_band(cls, item: dict) -> dict:
        traits = cls._resolve_precision_end_cover_traits(item)
        if not traits:
            return {}
        role = str(traits.get("role") or "端盖")
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        if role == "后端盖":
            low, high = 165.0, 255.0
        elif role == "前端盖":
            low, high = 135.0, 210.0
        else:
            low, high = 120.0, 190.0
        if diameter_mm >= 180:
            low += 12.0
            high += 25.0
        if traits.get("sealing"):
            low += 8.0
            high += 15.0
        if len(traits.get("cnc") or []) >= 2:
            low += 10.0
            high += 18.0
        basis = cls._build_precision_end_cover_basis(traits)
        basis = f"识别为电机精密结构端盖：{basis}" if basis else "识别为电机精密结构端盖"
        return {
            "category": "电机精密结构端盖",
            "low": round(low, 4),
            "high": round(high, 4),
            "basis": basis,
        }

    @classmethod
    def _resolve_precision_end_cover_weight_band(cls, item: dict) -> dict:
        traits = cls._resolve_precision_end_cover_traits(item)
        if not traits:
            return {}
        role = str(traits.get("role") or "端盖")
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        if role == "后端盖":
            low, high, default = 1.2, 4.2, 2.2
        elif role == "前端盖":
            low, high, default = 0.9, 3.4, 1.7
        else:
            low, high, default = 0.7, 3.0, 1.4
        if diameter_mm >= 180:
            low += 0.2
            high += 0.6
            default += 0.2
        basis = cls._build_precision_end_cover_basis(traits)
        basis = f"识别为电机精密结构端盖：{basis}" if basis else "识别为电机精密结构端盖"
        return {
            "category": "电机精密结构端盖",
            "low": round(low, 4),
            "high": round(high, 4),
            "default": round(default, 4),
            "basis": basis,
        }


    @classmethod
    def _resolve_precision_end_cover_formula_quote(cls, item: dict) -> dict:
        traits = cls._resolve_precision_end_cover_traits(item)
        if not traits:
            return {}
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_precision_end_cover_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if actual_weight <= 0:
            return {}

        role = str(traits.get("role") or "端盖")
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        casting_fee = 42.0 + actual_weight * 18.0 + diameter_mm * 0.16
        machining_fee = 36.0 + actual_weight * 16.0 + diameter_mm * 0.09
        sealing_fee = 0.0
        if traits.get("sealing"):
            sealing_fee = 14.0 + actual_weight * 4.5 + diameter_mm * 0.025
        feature_bonus = 0.0
        cnc_tokens = tuple(traits.get("cnc") or ())
        if "轴承室" in cnc_tokens:
            feature_bonus += 18.0
        if "止口" in cnc_tokens:
            feature_bonus += 12.0
        if "安装面" in cnc_tokens:
            feature_bonus += 8.0
        if "螺纹孔" in cnc_tokens:
            feature_bonus += 10.0
        if role == "后端盖":
            feature_bonus += 22.0
            casting_fee += 10.0
            machining_fee += 12.0
        elif role == "前端盖":
            feature_bonus += 10.0
        material_tokens = tuple(traits.get("material") or ())
        if any("a356" in token for token in material_tokens):
            material_rate = 26.0
        else:
            material_rate = 22.0
        material_fee = actual_weight * material_rate
        total_price = round(material_fee + casting_fee + machining_fee + sealing_fee + feature_bonus, 4)
        note_parts = [
            f"{role}公式报价（重量 {actual_weight:.4f}kg，外径 {diameter_mm:.1f}mm）",
            f"材料费 {material_fee:.2f}",
            f"低压铸造/铸造毛坯 {casting_fee:.2f}",
            f"轴承室/止口/安装面/螺纹孔机加工 {machining_fee:.2f}",
        ]
        if sealing_fee > 0:
            note_parts.append(f"密封槽/喷涂 {sealing_fee:.2f}")
        if feature_bonus > 0:
            feature_desc = []
            for key in ("轴承室", "止口", "安装面", "螺纹孔"):
                if key in cnc_tokens:
                    feature_desc.append(key)
            if traits.get("sealing"):
                feature_desc.extend([token for token in traits.get("sealing") or [] if token not in feature_desc])
            feature_text = "、".join(feature_desc) if feature_desc else role
            note_parts.append(f"复杂度加成 {feature_bonus:.2f}（{feature_text}）")
        note = " + ".join(note_parts[1:])
        note = f"{note_parts[0]}：{note} = {total_price:.2f} 元。"
        return {
            "price": total_price,
            "note": note,
        }

    @classmethod
    def _ensure_mass_tooling_advantage(cls, sample_unit: float, unit_price: float, max_ratio: float) -> tuple[float, bool]:
        sample_value = cls._to_number(sample_unit)
        tooling_value = cls._to_number(unit_price)
        ratio_limit = cls._to_number(max_ratio)
        if sample_value <= 0 or tooling_value <= 0 or ratio_limit <= 0:
            return round(tooling_value, 4), False
        capped_price = round(sample_value * ratio_limit, 4)
        if tooling_value <= capped_price:
            return round(tooling_value, 4), False
        return capped_price, True

    @classmethod
    def _resolve_precision_end_cover_mass_production_quote(cls, item: dict) -> dict:
        traits = cls._resolve_precision_end_cover_traits(item)
        if not traits:
            return {}
        annual_volume = cls._to_int(item.get("annual_volume"))
        if annual_volume <= 0:
            return {}
        sample_quote = cls._resolve_precision_end_cover_formula_quote(item)
        sample_unit = cls._to_number(sample_quote.get("price"))
        if sample_unit <= 0:
            return {}
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_precision_end_cover_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if actual_weight <= 0:
            return {}
        role = str(traits.get("role") or "端盖")
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        material_tokens = tuple(traits.get("material") or ())
        material_rate = 18.5 if any("a356" in token for token in material_tokens) else 16.5
        material_fee = actual_weight * material_rate
        cast_unit_fee = 18.0 + actual_weight * 8.0 + diameter_mm * 0.05
        finish_unit_fee = 12.0 + actual_weight * 5.0 + diameter_mm * 0.03
        if role == "后端盖":
            finish_unit_fee += 8.0
        tooling_cost = 28000.0 + diameter_mm * 75.0
        if role == "后端盖":
            tooling_cost += 8000.0
        if traits.get("sealing"):
            tooling_cost += 5000.0
        if len(traits.get("cnc") or ()) >= 3:
            tooling_cost += 7000.0
        tooling_cost = round(tooling_cost, 4)
        raw_unit_price = round(material_fee + cast_unit_fee + finish_unit_fee, 4)
        unit_price, adjusted_for_advantage = cls._ensure_mass_tooling_advantage(sample_unit, raw_unit_price, 0.55)
        unit_saving = max(sample_unit - unit_price, 0.0)
        break_even_volume = 0
        if unit_saving > 0:
            break_even_volume = max(1, int(tooling_cost / unit_saving))
            if tooling_cost > break_even_volume * unit_saving:
                break_even_volume += 1
        advantage_text = ""
        if adjusted_for_advantage:
            advantage_text = f"；已按量产单价需显著低于机加工口径压至样品价的 {unit_price / sample_unit:.0%}"
        note = (
            f"{role}量产开模口径（{annual_volume}套/年）：当前单件按开模后工艺计 {unit_price:.2f} 元，"
            f"不把开模费 {tooling_cost:.2f} 元并入当前产品总价；样品/小批机加工单价约 {sample_unit:.2f} 元，"
            f"当年产量大于 {break_even_volume} 套时，量产累计收益开始大于机加工，量产方案整体更划算{advantage_text}。"
        )
        return {
            "unit_price": unit_price,
            "tooling_cost": tooling_cost,
            "break_even_volume": break_even_volume,
            "sample_machining_unit_price": round(sample_unit, 4),
            "note": note,
        }

    @classmethod
    def _extract_precision_housing_diameter_mm(cls, item: dict) -> float:
        text = " ".join(
            str(item.get(field) or "").strip()
            for field in ("spec", "name", "process")
        )
        if not text:
            return 0.0
        normalized_text = re.sub(r"[\u03a6\u03c6\u00d8\u00f8]", "OD", text)
        for pattern in (cls.PRECISION_HOUSING_DIAMETER_PATTERN, cls.PRECISION_HOUSING_SUFFIX_DIAMETER_PATTERN):
            match = pattern.search(normalized_text)
            if match:
                value = cls._to_number(match.group(1))
                if value >= 80.0:
                    return value
        return 0.0

    @classmethod
    def _extract_precision_housing_length_mm(cls, item: dict) -> float:
        text = " ".join(
            str(item.get(field) or "").strip()
            for field in ("spec", "name", "process")
        )
        if not text:
            return 0.0
        match = cls.PRECISION_HOUSING_LENGTH_PATTERN.search(text)
        if match:
            value = cls._to_number(match.group(1))
            if value >= 40.0:
                return value
        values = [cls._to_number(value) for value in cls.PRECISION_SHAFT_ANY_LENGTH_PATTERN.findall(text)]
        values = [value for value in values if 40.0 <= value <= 600.0]
        return max(values) if values else 0.0

    @classmethod
    def _resolve_precision_housing_traits(cls, item: dict) -> dict:
        combined = cls._build_item_matching_text(item)
        if not combined:
            return {}
        if any(keyword in combined for keyword in cls.PRECISION_HOUSING_EXCLUDE_KEYWORDS):
            return {}
        if not any(keyword in combined for keyword in cls.PRECISION_HOUSING_NAME_KEYWORDS):
            return {}
        diameter_mm = cls._extract_precision_housing_diameter_mm(item)
        length_mm = cls._extract_precision_housing_length_mm(item)
        traits = {
            "material": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_HOUSING_MATERIAL_KEYWORDS if keyword in combined]),
            "forming": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_HOUSING_FORMING_KEYWORDS if keyword in combined]),
            "cnc": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_HOUSING_CNC_KEYWORDS if keyword in combined]),
            "bearing": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_HOUSING_BEARING_KEYWORDS if keyword in combined]),
            "surface": cls._dedupe_overlapping_keywords([keyword for keyword in cls.PRECISION_HOUSING_SURFACE_KEYWORDS if keyword in combined]),
            "diameter_mm": round(diameter_mm, 3) if diameter_mm > 0 else 0.0,
            "length_mm": round(length_mm, 3) if length_mm > 0 else 0.0,
        }
        score = 2
        score += 2 if traits["forming"] else 0
        score += 1 if traits["material"] else 0
        score += 1 if traits["cnc"] else 0
        score += 1 if traits["bearing"] else 0
        score += 1 if traits["surface"] else 0
        score += 1 if diameter_mm >= 140 else 0
        score += 1 if length_mm >= 120 else 0
        if score < 5:
            return {}
        return traits

    @classmethod
    def _build_precision_housing_basis(cls, traits: dict) -> str:
        parts: list[str] = []
        if traits.get("material"):
            parts.append(f"\u6750\u8d28\u7279\u5f81 {'/'.join(traits['material'])}")
        if traits.get("forming"):
            parts.append(f"\u6210\u5f62\u7279\u5f81 {'/'.join(traits['forming'])}")
        if traits.get("cnc"):
            parts.append(f"\u7cbe\u52a0\u5de5\u7279\u5f81 {'/'.join(traits['cnc'])}")
        if traits.get("bearing"):
            parts.append(f"\u8f74\u627f\u5b9a\u4f4d\u7279\u5f81 {'/'.join(traits['bearing'])}")
        if traits.get("surface"):
            parts.append(f"\u8868\u9762\u5904\u7406\u7279\u5f81 {'/'.join(traits['surface'])}")
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        length_mm = cls._to_number(traits.get("length_mm"))
        if diameter_mm > 0:
            parts.append(f"\u5916\u5f84\u7ea6 {diameter_mm:.1f}mm")
        if length_mm > 0:
            parts.append(f"\u957f\u5ea6\u7ea6 {length_mm:.1f}mm")
        return "\uff0c".join(parts)

    @classmethod
    def _resolve_precision_housing_price_band(cls, item: dict) -> dict:
        traits = cls._resolve_precision_housing_traits(item)
        if not traits:
            return {}
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        length_mm = cls._to_number(traits.get("length_mm"))
        if diameter_mm >= 180:
            low, high = 110.0, 170.0
        elif diameter_mm >= 140:
            low, high = 88.0, 145.0
        else:
            low, high = 68.0, 118.0
        if length_mm >= 150:
            low += 6.0
            high += 12.0
        elif length_mm >= 100:
            low += 3.0
            high += 7.0
        if traits.get("material"):
            low += 3.0
            high += 6.0
        if traits.get("forming"):
            low += 5.0
            high += 8.0
        if traits.get("cnc"):
            low += 7.0
            high += 12.0
        if traits.get("bearing"):
            low += 8.0
            high += 14.0
        if traits.get("surface"):
            low += 3.0
            high += 6.0
        basis = cls._build_precision_housing_basis(traits)
        basis = f"\u8bc6\u522b\u4e3a\u7535\u673a\u7cbe\u5bc6\u62c9\u4f38\u673a\u58f3\uff1a{basis}" if basis else "\u8bc6\u522b\u4e3a\u7535\u673a\u7cbe\u5bc6\u62c9\u4f38\u673a\u58f3"
        return {
            "category": "\u7535\u673a\u7cbe\u5bc6\u62c9\u4f38\u673a\u58f3",
            "low": round(low, 4),
            "high": round(high, 4),
            "basis": basis,
        }

    @classmethod
    def _resolve_precision_housing_weight_band(cls, item: dict) -> dict:
        traits = cls._resolve_precision_housing_traits(item)
        if not traits:
            return {}
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        length_mm = cls._to_number(traits.get("length_mm"))
        if diameter_mm >= 180:
            low, high, default = 2.2, 5.8, 3.3
        elif diameter_mm >= 140:
            low, high, default = 1.5, 4.6, 2.5
        else:
            low, high, default = 0.9, 3.2, 1.7
        if length_mm >= 150:
            low += 0.25
            high += 0.8
            default += 0.35
        elif length_mm >= 100:
            low += 0.1
            high += 0.4
            default += 0.18
        basis = cls._build_precision_housing_basis(traits)
        basis = f"\u8bc6\u522b\u4e3a\u7535\u673a\u7cbe\u5bc6\u62c9\u4f38\u673a\u58f3\uff1a{basis}" if basis else "\u8bc6\u522b\u4e3a\u7535\u673a\u7cbe\u5bc6\u62c9\u4f38\u673a\u58f3"
        return {
            "category": "\u7535\u673a\u7cbe\u5bc6\u62c9\u4f38\u673a\u58f3",
            "low": round(low, 4),
            "high": round(high, 4),
            "default": round(default, 4),
            "basis": basis,
        }

    @classmethod
    def _resolve_precision_housing_anchor_price(cls, item: dict, low: float, high: float) -> tuple[float, str]:
        traits = cls._resolve_precision_housing_traits(item)
        if not traits:
            return round((low + high) / 2.0, 4), "\u53d6\u533a\u95f4\u4e2d\u503c"
        ratio = 0.14
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        length_mm = cls._to_number(traits.get("length_mm"))
        if diameter_mm >= 180:
            ratio += 0.015
        elif diameter_mm >= 140:
            ratio += 0.01
        if length_mm >= 150:
            ratio += 0.015
        elif length_mm >= 100:
            ratio += 0.01
        if traits.get("forming"):
            ratio += 0.01
        if traits.get("cnc"):
            ratio += 0.015
        if traits.get("bearing"):
            ratio += 0.01
        if traits.get("surface"):
            ratio += 0.02

        weight_note = ""
        actual_weight = cls._to_number(item.get("weight_kg"))
        if actual_weight > 0:
            weight_band = cls._resolve_precision_housing_weight_band(item)
            weight_low = cls._to_number(weight_band.get("low"))
            weight_high = cls._to_number(weight_band.get("high"))
            weight_default = cls._to_number(weight_band.get("default"))
            if weight_high > weight_low > 0 and weight_default > 0:
                weight_span = max(weight_high - weight_low, 0.001)
                weight_delta_ratio = (actual_weight - weight_default) / weight_span
                ratio += max(min(weight_delta_ratio * 0.08, 0.05), -0.05)
                weight_note = f"\u5df2\u6309\u5b9e\u9645\u91cd\u91cf {actual_weight:.2f}kg \u5bf9\u951a\u70b9\u8fdb\u884c\u5c0f\u5e45\u6821\u6b63"

        ratio = min(max(ratio, 0.14), 0.42)
        price = low + (high - low) * ratio
        note = f"\u6309\u673a\u58f3\u7ed3\u6784\u590d\u6742\u5ea6\u951a\u5b9a\u533a\u95f4 {ratio:.0%} \u4f4d\u7f6e"
        if weight_note:
            note = f"{note}\uff0c{weight_note}"
        return round(price, 4), note

    @classmethod
    def _resolve_precision_housing_formula_weight(cls, item: dict) -> tuple[float, str]:
        candidates = (
            (cls._to_number(item.get("weight_kg")), "原始重量"),
            (cls._to_number(item.get("effective_weight_kg")), "计价重量"),
            (cls._to_number(item.get("ai_estimated_weight_kg")), "AI估重"),
            (cls._to_number(item.get("ai_inferred_weight_reference")), "AI推断重量"),
        )
        for value, label in candidates:
            if value > 0:
                return value, label
        band = cls._resolve_precision_housing_weight_band(item)
        default_weight = cls._to_number(band.get("default"))
        if default_weight > 0:
            return default_weight, "规则默认重量"
        return 0.0, ""

    @classmethod
    def _resolve_precision_housing_formula_quote(cls, item: dict) -> dict:
        traits = cls._resolve_precision_housing_traits(item)
        actual_weight, weight_source = cls._resolve_precision_housing_formula_weight(item)
        if not traits or actual_weight <= 0:
            return {}

        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        length_mm = cls._to_number(traits.get("length_mm"))
        material_tokens = tuple(traits.get("material") or ())
        assumed_large_housing_postprocess = bool(
            traits.get("forming") and diameter_mm >= 180 and length_mm >= 180 and actual_weight >= 4.5
        )
        if any("6063" in token for token in material_tokens):
            material_rate = 21.5
        elif any("6061" in token for token in material_tokens):
            material_rate = 20.8
        elif assumed_large_housing_postprocess:
            material_rate = 20.8
        else:
            material_rate = 19.5

        material_fee = actual_weight * material_rate
        forming_fee = 0.0
        if traits.get("forming"):
            forming_fee = 10.0 + diameter_mm * 0.06 + length_mm * 0.03 + actual_weight * 1.8

        cnc_fee = 0.0
        cnc_source = "明确机加工"
        if traits.get("cnc") or traits.get("bearing") or assumed_large_housing_postprocess:
            cnc_fee = 8.0 + diameter_mm * 0.05 + length_mm * 0.02 + actual_weight * 3.2
            if traits.get("cnc"):
                cnc_fee += 12.0
            if traits.get("bearing"):
                cnc_fee += 10.0
            if assumed_large_housing_postprocess and not (traits.get("cnc") or traits.get("bearing")):
                cnc_fee += 10.0
                cnc_source = "大型拉伸机壳默认后续机加工"

        surface_fee = 0.0
        surface_source = "明确表处"
        if traits.get("surface") or (traits.get("forming") and (traits.get("cnc") or traits.get("bearing") or assumed_large_housing_postprocess)):
            surface_fee = 7.0 + diameter_mm * 0.035 + actual_weight * 1.6
            if length_mm >= 150:
                surface_fee += 2.0
            if not traits.get("surface"):
                surface_source = "电机拉伸机壳默认表处"

        total_price = round(material_fee + forming_fee + cnc_fee + surface_fee, 4)
        note = (
            f"机壳公式报价（{weight_source} {actual_weight:.4f}kg）：材料费 {material_fee:.2f} + 拉伸成形费 {forming_fee:.2f} + "
            f"CNC/钻孔攻丝/轴承室加工费 {cnc_fee:.2f}（{cnc_source}） + 表面处理费 {surface_fee:.2f}（{surface_source}）= {total_price:.2f} 元。"
        )

        return {
            "price": total_price,
            "note": note,
            "components": {
                "material_fee": round(material_fee, 4),
                "forming_fee": round(forming_fee, 4),
                "cnc_fee": round(cnc_fee, 4),
                "surface_fee": round(surface_fee, 4),
                "material_rate": round(material_rate, 4),
                "weight_kg": round(actual_weight, 4),
                "weight_source": weight_source,
            },
        }

    @classmethod
    def _resolve_precision_shaft_formula_quote(cls, item: dict) -> dict:
        traits = cls._resolve_precision_shaft_traits(item)
        if not traits:
            return {}
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_precision_shaft_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if actual_weight <= 0:
            return {}

        length_mm = cls._to_number(traits.get("length_mm"))
        material_rate = 20.0
        material_tokens = tuple(traits.get("material") or ())
        if any("20crmnti" in token for token in material_tokens):
            material_rate = 23.5
        elif any("42crmo" in token for token in material_tokens):
            material_rate = 22.0
        elif any("40cr" in token for token in material_tokens):
            material_rate = 19.5

        material_fee = actual_weight * material_rate
        forging_fee = 85.0 + actual_weight * 18.0 + max(length_mm - 180.0, 0.0) * 0.18
        turning_fee = 95.0 + actual_weight * 24.0 + max(length_mm - 200.0, 0.0) * 0.28
        heat_treatment_fee = 0.0
        if traits.get("heat_treatment"):
            heat_treatment_fee = 80.0 + actual_weight * 12.0 + max(length_mm - 180.0, 0.0) * 0.08
        grinding_fee = 0.0
        grinding_note = ""
        if traits.get("grinding"):
            grinding_fee = 75.0 + actual_weight * 14.0 + max(length_mm - 180.0, 0.0) * 0.12
            grinding_note = "/".join(traits.get("grinding") or ())
        spline_fee = 0.0
        if traits.get("spline"):
            spline_fee = 55.0 + len(traits.get("spline") or ()) * 14.0 + max(length_mm - 180.0, 0.0) * 0.05

        total_price = round(material_fee + forging_fee + turning_fee + heat_treatment_fee + grinding_fee + spline_fee, 4)
        note = (
            f"高精轴公式报价（长度 {length_mm:.1f}mm，重量 {actual_weight:.4f}kg）：材料费 {material_fee:.2f} + 锻造毛坯 {forging_fee:.2f} + "
            f"粗精车/花键预加工 {turning_fee:.2f} + 渗碳淬火 {heat_treatment_fee:.2f} + "
            f"{(grinding_note or '磨削')} {grinding_fee:.2f} + 花键/键槽精加工 {spline_fee:.2f} = {total_price:.2f} 元。"
        )
        return {
            "price": total_price,
            "note": note,
        }

    @classmethod
    def _resolve_precision_housing_mass_production_quote(cls, item: dict) -> dict:
        traits = cls._resolve_precision_housing_traits(item)
        if not traits:
            return {}
        annual_volume = cls._to_int(item.get("annual_volume"))
        if annual_volume <= 0:
            return {}
        sample_quote = cls._resolve_precision_housing_formula_quote(item)
        sample_unit = cls._to_number(sample_quote.get("price"))
        if sample_unit <= 0:
            return {}
        actual_weight, _ = cls._resolve_precision_housing_formula_weight(item)
        if actual_weight <= 0:
            return {}
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        length_mm = cls._to_number(traits.get("length_mm"))
        material_tokens = tuple(traits.get("material") or ())
        if any("6063" in token for token in material_tokens):
            material_rate = 16.5
        elif any("6061" in token for token in material_tokens):
            material_rate = 16.0
        else:
            material_rate = 15.0
        material_fee = actual_weight * material_rate
        mold_forming_fee = 16.0 + actual_weight * 6.0 + diameter_mm * 0.035 + length_mm * 0.02
        finish_fee = 10.0 + actual_weight * 4.5 + diameter_mm * 0.025 + length_mm * 0.018
        if traits.get("cnc"):
            finish_fee += 8.0
        if traits.get("bearing"):
            finish_fee += 10.0
        if traits.get("surface"):
            finish_fee += 6.0
        unit_price = round(material_fee + mold_forming_fee + finish_fee, 4)
        unit_price, adjusted_for_advantage = cls._ensure_mass_tooling_advantage(sample_unit, unit_price, 0.58)
        tooling_cost = 32000.0 + diameter_mm * 65.0 + length_mm * 42.0 + actual_weight * 2800.0
        if traits.get("bearing"):
            tooling_cost += 8000.0
        if traits.get("surface"):
            tooling_cost += 4000.0
        tooling_cost = round(tooling_cost, 4)
        unit_saving = max(sample_unit - unit_price, 0.0)
        break_even_volume = 0
        if unit_saving > 0:
            break_even_volume = max(1, int(tooling_cost / unit_saving))
            if tooling_cost > break_even_volume * unit_saving:
                break_even_volume += 1
        advantage_text = ""
        if adjusted_for_advantage:
            advantage_text = f"；已按量产单价需显著低于机加工口径压至样品价的 {unit_price / sample_unit:.0%}"
        note = (
            f"机壳量产开模口径（{annual_volume}套/年）：当前单件按开模后工艺计 {unit_price:.2f} 元，"
            f"不把开模费 {tooling_cost:.2f} 元并入当前产品总价；样品/小批机加工单价约 {sample_unit:.2f} 元，"
            f"当年产量大于 {break_even_volume} 套时，量产累计收益开始大于机加工，量产方案整体更划算{advantage_text}。"
        )
        return {
            "unit_price": unit_price,
            "tooling_cost": tooling_cost,
            "break_even_volume": break_even_volume,
            "sample_machining_unit_price": round(sample_unit, 4),
            "note": note,
        }

    @classmethod
    def _resolve_precision_shaft_mass_production_quote(cls, item: dict) -> dict:
        traits = cls._resolve_precision_shaft_traits(item)
        if not traits:
            return {}
        annual_volume = cls._to_int(item.get("annual_volume"))
        if annual_volume <= 0:
            return {}
        sample_quote = cls._resolve_precision_shaft_formula_quote(item)
        sample_unit = cls._to_number(sample_quote.get("price"))
        if sample_unit <= 0:
            return {}
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_precision_shaft_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if actual_weight <= 0:
            return {}

        length_mm = cls._to_number(traits.get("length_mm"))
        material_tokens = tuple(traits.get("material") or ())
        material_rate = 17.2
        if any("20crmnti" in token for token in material_tokens):
            material_rate = 18.8
        elif any("42crmo" in token for token in material_tokens):
            material_rate = 18.2
        elif any("40cr" in token for token in material_tokens):
            material_rate = 17.6

        material_fee = actual_weight * material_rate
        mold_forming_fee = 12.0 + actual_weight * 8.0 + max(length_mm - 180.0, 0.0) * 0.03
        finish_fee = 10.0 + actual_weight * 5.0 + max(length_mm - 180.0, 0.0) * 0.015
        heat_treatment_fee = 0.0
        if traits.get("heat_treatment"):
            heat_treatment_fee = 12.0 + actual_weight * 3.5 + max(length_mm - 180.0, 0.0) * 0.01
        grinding_fee = 0.0
        if traits.get("grinding"):
            grinding_fee = 8.0 + actual_weight * 2.8 + max(length_mm - 180.0, 0.0) * 0.008
        spline_fee = 0.0
        if traits.get("spline"):
            spline_fee = 8.0 + len(traits.get("spline") or ()) * 6.0 + max(length_mm - 180.0, 0.0) * 0.005
        unit_price = round(material_fee + mold_forming_fee + finish_fee + heat_treatment_fee + grinding_fee + spline_fee, 4)
        unit_price, adjusted_for_advantage = cls._ensure_mass_tooling_advantage(sample_unit, unit_price, 0.4)

        tooling_cost = 35000.0 + max(length_mm - 180.0, 0.0) * 90.0
        if traits.get("heat_treatment"):
            tooling_cost += 8000.0
        if traits.get("grinding"):
            tooling_cost += 6000.0
        if traits.get("spline"):
            tooling_cost += 12000.0
        tooling_cost = round(tooling_cost, 4)
        unit_saving = max(sample_unit - unit_price, 0.0)
        break_even_volume = 0
        if unit_saving > 0:
            break_even_volume = max(1, int(tooling_cost / unit_saving))
            if tooling_cost > (break_even_volume * unit_saving):
                break_even_volume += 1
        advantage_text = ""
        if adjusted_for_advantage:
            advantage_text = f"；已按量产单价需显著低于机加工口径压至样品价的 {unit_price / sample_unit:.0%}"
        note = (
            f"量产开模口径（{annual_volume}套/年）：当前单件按开模后工艺计 {unit_price:.2f} 元，"
            f"不把开模费 {tooling_cost:.2f} 元并入当前产品总价；样品/小批机加工单价约 {sample_unit:.2f} 元，"
            f"当年产量大于 {break_even_volume} 套时，量产累计收益开始大于机加工，量产方案整体更划算{advantage_text}。"
        )
        return {
            "unit_price": unit_price,
            "tooling_cost": tooling_cost,
            "break_even_volume": break_even_volume,
            "sample_machining_unit_price": round(sample_unit, 4),
            "note": note,
        }

    @classmethod
    def _resolve_motor_harness_formula_quote(cls, item: dict) -> dict:
        combined = cls._build_item_matching_text(item)
        if not combined or not any(keyword in combined for keyword in cls.MOTOR_HARNESS_NAME_KEYWORDS):
            return {}
        cross_sections = [cls._to_number(value) for value in cls.MOTOR_HARNESS_CROSS_SECTION_PATTERN.findall(combined)]
        cross_section_mm2 = max(cross_sections) if cross_sections else 0.0
        lengths_m = [cls._to_number(value) for value in cls.MOTOR_HARNESS_LENGTH_PATTERN.findall(combined)]
        length_context_match = cls.MOTOR_HARNESS_LENGTH_CONTEXT_PATTERN.search(combined)
        mm_search_area = combined[length_context_match.start():] if length_context_match else ""
        lengths_mm = [cls._to_number(value) / 1000.0 for value in cls.MOTOR_HARNESS_LENGTH_MM_PATTERN.findall(mm_search_area)]
        total_length_m = sum(value for value in lengths_m if value > 0) + sum(value for value in lengths_mm if value > 0)
        branch_match = cls.MOTOR_HARNESS_BRANCH_PATTERN.search(combined)
        branch_count = max(int(branch_match.group(1)) if branch_match else 1, 1)
        process_hits = [keyword for keyword in cls.MOTOR_HARNESS_PROCESS_KEYWORDS if keyword in combined]
        if cross_section_mm2 < 16.0 and total_length_m < 3.0 and branch_count <= 1:
            return {}

        copper_factor = max(cross_section_mm2 / 35.0, 0.35)
        copper_fee = total_length_m * copper_factor * 16.5
        insulation_fee = total_length_m * (2.8 + cross_section_mm2 * 0.035)
        terminal_fee = branch_count * (12.0 + cross_section_mm2 * 0.38)
        assembly_fee = 16.0 + total_length_m * 4.0 + branch_count * 6.0 + len(process_hits) * 2.0
        accessory_fee = 10.0 if any(keyword in combined for keyword in ("护套", "热缩", "铜鼻子")) else 0.0
        total_price = round(copper_fee + insulation_fee + terminal_fee + assembly_fee + accessory_fee, 4)
        note = (
            f"大线径线束公式报价（{cross_section_mm2:.0f}mm²，总长 {total_length_m:.2f}m，{branch_count}分支）：铜耗 {copper_fee:.2f} + "
            f"绝缘护套 {insulation_fee:.2f} + 压接端子 {terminal_fee:.2f} + 分支包扎装配 {assembly_fee:.2f} + 附件 {accessory_fee:.2f} = {total_price:.2f} 元。"
        )
        return {
            "price": total_price,
            "note": note,
        }

    @classmethod
    def _is_generic_large_metal_mass_tooling_candidate(cls, item: dict) -> bool:
        combined = cls._build_item_matching_text(item)
        if not combined:
            return False
        exclude_keywords = (
            "定子组件", "定子绕组", "浸漆定子", "旋转变压器", "线束", "永磁体", "磁钢",
            "油封", "o型圈", "O型圈", "密封圈", "密封胶", "磁钢胶", "螺纹胶", "接线板", "连接器",
            "端子", "堵头", "锁扣", "格兰头", "热缩", "木箱", "铭牌", "波形弹簧", "弹簧垫圈",
            "螺钉", "螺母", "螺栓", "螺杆", "垫圈", "卡簧", "挡圈",
        )
        if any(keyword in combined for keyword in exclude_keywords):
            return False
        if "轴承" in combined and "压盖" not in combined:
            return False
        generic_keywords = ("转子挡板", "挡板", "压盖", "轴套", "吊耳", "法兰", "口板")
        if not any(keyword in combined for keyword in generic_keywords):
            return False
        material_text = f"{cls._normalize_material_for_skills(item.get('material'))} {combined}"
        non_metal_keywords = ("橡胶", "尼龙", "PA66", "工程塑料", "塑料", "硅胶", "FKM", "NBR", "BMC")
        if any(keyword.lower() in material_text.lower() for keyword in non_metal_keywords):
            return False
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_name_spec_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if "轴套" in combined:
            return actual_weight >= 0.05
        return actual_weight >= 0.08

    @classmethod
    def _resolve_motor_shell_formula_quote(cls, item: dict) -> dict:
        combined = cls._build_item_matching_text(item)
        is_generic_metal = cls._is_generic_large_metal_mass_tooling_candidate(item)
        if not combined or (not any(keyword in combined for keyword in cls.MOTOR_SHELL_NAME_KEYWORDS) and not is_generic_metal):
            return {}
        diameter_match = cls.MOTOR_SHELL_DIAMETER_PATTERN.search(combined)
        diameter_mm = cls._to_number(diameter_match.group(1)) if diameter_match else 0.0
        hole_match = cls.MOTOR_SHELL_HOLE_PATTERN.search(combined)
        hole_count = max(cls._to_int(hole_match.group(1)) if hole_match else 0, 0)
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_name_spec_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if actual_weight <= 0:
            return {}

        material = cls._normalize_material_for_skills(item.get("material"))
        if material == "ADC12":
            material_rate = 18.0
        elif material == "QT450-10":
            material_rate = 12.5
        else:
            material_rate = 14.0
        material_fee = actual_weight * material_rate
        casting_fee = 32.0 + actual_weight * 18.0 + diameter_mm * 0.12
        machining_fee = 0.0
        surface_label = "默认防护"
        surface_fee = 0.0
        is_blank = any(keyword in combined for keyword in cls.MOTOR_SHELL_BLANK_KEYWORDS) and not any(
            keyword in combined for keyword in cls.MOTOR_SHELL_FINISHED_KEYWORDS
        )
        machining_hits = any(keyword in combined for keyword in cls.MOTOR_SHELL_MACHINING_KEYWORDS)
        surface_hits = any(keyword in combined for keyword in cls.MOTOR_SHELL_SURFACE_KEYWORDS)
        simple_cast_only_box = (
            "接线盒" in combined
            and not is_blank
            and not machining_hits
            and not surface_hits
            and not any(keyword in combined for keyword in cls.MOTOR_SHELL_FINISHED_KEYWORDS)
            and hole_count <= 0
            and actual_weight <= 0.8
        )
        simple_cast_only_cover_plate = (
            any(keyword in combined for keyword in ("后盖板", "三相盖板", "上盖板", "盖板"))
            and not is_blank
            and not machining_hits
            and not surface_hits
            and not any(keyword in combined for keyword in cls.MOTOR_SHELL_FINISHED_KEYWORDS)
            and hole_count <= 0
            and actual_weight <= 0.7
            and "止口" not in combined
        )
        if simple_cast_only_box or simple_cast_only_cover_plate:
            casting_fee = 14.0 + actual_weight * 22.0 + diameter_mm * 0.02
            machining_fee = 4.0 + actual_weight * 3.0
            surface_label = "铸态去毛刺"
            surface_fee = 0.0
        elif not is_blank:
            machining_fee = 24.0 + actual_weight * 13.0 + diameter_mm * 0.08
            if machining_hits:
                machining_fee += 18.0
            if hole_count > 0:
                machining_fee += hole_count * 3.6
            if "止口" in combined:
                machining_fee += 10.0
            if surface_hits:
                surface_fee = 20.0 + actual_weight * 4.5
                surface_label = "喷涂/喷粉"
            elif "接线盒" in combined or "盖板" in combined:
                surface_fee = 12.0 + actual_weight * 2.5
        else:
            surface_label = "毛坯态无表处"

        total_price = round(material_fee + casting_fee + machining_fee + surface_fee, 4)
        feature_parts: list[str] = []
        if hole_count > 0:
            feature_parts.append(f"{hole_count}孔")
        if "止口" in combined:
            feature_parts.append("止口")
        if is_blank:
            feature_parts.append("毛坯")
        feature_text = f"，特征 {'/'.join(feature_parts)}" if feature_parts else ""
        category_label = "大金属结构件" if is_generic_metal and not any(keyword in combined for keyword in cls.MOTOR_SHELL_NAME_KEYWORDS) else "壳体盖板"
        note = (
            f"{category_label}公式报价（材质 {material or '通用铸件'}，重量 {actual_weight:.4f}kg{feature_text}）：材料费 {material_fee:.2f} + "
            f"压铸/铸造 {casting_fee:.2f} + 机加工/钻孔攻丝 {machining_fee:.2f} + {surface_label} {surface_fee:.2f} = {total_price:.2f} 元。"
        )
        return {
            "price": total_price,
            "note": note,
        }

    @classmethod
    def _resolve_motor_shell_mass_production_quote(cls, item: dict) -> dict:
        sample_quote = cls._resolve_motor_shell_formula_quote(item)
        sample_unit = cls._to_number(sample_quote.get("price"))
        annual_volume = cls._to_int(item.get("annual_volume"))
        if sample_unit <= 0 or annual_volume <= 0:
            return {}
        combined = cls._build_item_matching_text(item)
        is_generic_metal = cls._is_generic_large_metal_mass_tooling_candidate(item)
        if not any(keyword in combined for keyword in cls.MOTOR_SHELL_NAME_KEYWORDS) and not is_generic_metal:
            return {}
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight <= 0:
            weight_band = cls._resolve_name_spec_weight_band(item)
            actual_weight = cls._to_number(weight_band.get("default"))
        if actual_weight <= 0:
            return {}
        hole_match = cls.MOTOR_SHELL_HOLE_PATTERN.search(combined)
        hole_count = max(cls._to_int(hole_match.group(1)) if hole_match else 0, 0)
        machining_hits = any(keyword in combined for keyword in cls.MOTOR_SHELL_MACHINING_KEYWORDS)
        surface_hits = any(keyword in combined for keyword in cls.MOTOR_SHELL_SURFACE_KEYWORDS)
        is_blank = any(keyword in combined for keyword in cls.MOTOR_SHELL_BLANK_KEYWORDS) and not any(
            keyword in combined for keyword in cls.MOTOR_SHELL_FINISHED_KEYWORDS
        )
        simple_cast_only_box = (
            "接线盒" in combined
            and not is_blank
            and not machining_hits
            and not surface_hits
            and not any(keyword in combined for keyword in cls.MOTOR_SHELL_FINISHED_KEYWORDS)
            and hole_count <= 0
            and actual_weight <= 0.8
        )
        simple_cast_only_cover_plate = (
            any(keyword in combined for keyword in ("后盖板", "三相盖板", "上盖板", "盖板"))
            and not is_blank
            and not machining_hits
            and not surface_hits
            and not any(keyword in combined for keyword in cls.MOTOR_SHELL_FINISHED_KEYWORDS)
            and hole_count <= 0
            and actual_weight <= 0.7
            and "止口" not in combined
        )
        lightweight_box_or_cover = simple_cast_only_box or simple_cast_only_cover_plate
        diameter_match = cls.MOTOR_SHELL_DIAMETER_PATTERN.search(combined)
        diameter_mm = cls._to_number(diameter_match.group(1)) if diameter_match else 0.0
        material = cls._normalize_material_for_skills(item.get("material"))
        if material == "ADC12":
            material_rate = 15.0
        elif material == "QT450-10":
            material_rate = 10.5
        else:
            material_rate = 12.0
        material_fee = actual_weight * material_rate
        mold_cast_unit_fee = 12.0 + actual_weight * 6.0 + diameter_mm * 0.03
        finish_unit_fee = 8.0 + actual_weight * 4.0 + diameter_mm * 0.02
        if lightweight_box_or_cover:
            mold_cast_unit_fee = 8.0 + actual_weight * 5.0 + diameter_mm * 0.015
            finish_unit_fee = 4.0 + actual_weight * 2.2
        if "止口" in combined:
            finish_unit_fee += 5.0
        if hole_count > 0:
            finish_unit_fee += hole_count * 1.6
        if surface_hits:
            finish_unit_fee += 6.0
        unit_price = round(material_fee + mold_cast_unit_fee + finish_unit_fee, 4)
        unit_price, adjusted_for_advantage = cls._ensure_mass_tooling_advantage(sample_unit, unit_price, 0.6)
        tooling_cost = 22000.0 + diameter_mm * 55.0 + actual_weight * 3000.0
        if lightweight_box_or_cover:
            tooling_cost = 18000.0 + diameter_mm * 20.0 + actual_weight * 1800.0
        if material == "QT450-10":
            tooling_cost += 12000.0
        if hole_count > 0:
            tooling_cost += hole_count * 1200.0
        if "止口" in combined:
            tooling_cost += 5000.0
        tooling_cost = round(tooling_cost, 4)
        unit_saving = max(sample_unit - unit_price, 0.0)
        break_even_volume = 0
        if unit_saving > 0:
            break_even_volume = max(1, int(tooling_cost / unit_saving))
            if tooling_cost > break_even_volume * unit_saving:
                break_even_volume += 1
        advantage_text = ""
        if adjusted_for_advantage:
            advantage_text = f"；已按量产单价需显著低于机加工口径压至样品价的 {unit_price / sample_unit:.0%}"
        note_prefix = "接线盒" if "接线盒" in combined else ("轴套" if "轴套" in combined else ("大金属结构件" if is_generic_metal and not any(keyword in combined for keyword in cls.MOTOR_SHELL_NAME_KEYWORDS) else "壳体盖板"))
        note = (
            f"{note_prefix}量产开模口径（{annual_volume}套/年）：当前单件按开模后工艺计 {unit_price:.2f} 元，"
            f"不把开模费 {tooling_cost:.2f} 元并入当前产品总价；样品/小批机加工单价约 {sample_unit:.2f} 元，"
            f"当年产量大于 {break_even_volume} 套时，量产累计收益开始大于机加工，量产方案整体更划算{advantage_text}。"
        )
        return {
            "unit_price": unit_price,
            "mass_tooling_unit_price": unit_price,
            "tooling_cost": tooling_cost,
            "break_even_volume": break_even_volume,
            "sample_machining_unit_price": round(sample_unit, 4),
            "mass_process_route": "压铸/铸造开模",
            "note": note,
        }

    @classmethod
    def _extract_bearing_series_traits(cls, item: dict) -> dict:
        combined = cls._build_item_matching_text(item)
        if "轴承" not in combined:
            return {}
        spec = str(item.get("spec") or "").upper().replace(" ", "")
        code = str(item.get("code") or "").upper().replace(" ", "")
        match = re.search(r"(?<!\d)(6[234])(\d{2})(?!\d)", spec or code)
        if not match:
            return {}
        series = match.group(1)
        bore_code = cls._to_int(match.group(2))
        suffix_text = (spec[match.end():] if spec else "")
        special_suffix_keywords = ("AEM3", "EM3", "C3GJN", "GJN", "VL", "INS", "P5", "P6")
        special_suffix_hits = [keyword for keyword in special_suffix_keywords if keyword in suffix_text]
        actual_weight = cls._to_number(item.get("weight_kg") or item.get("effective_weight_kg"))
        return {
            "series": series,
            "bore_code": bore_code,
            "suffix_text": suffix_text,
            "special_suffix_hits": special_suffix_hits,
            "actual_weight": actual_weight,
        }

    @classmethod
    def _build_bearing_basis(cls, traits: dict) -> str:
        parts = [f"识别为 {traits.get('series', '')} 系列深沟球轴承"]
        bore_code = cls._to_int(traits.get("bore_code"))
        if bore_code > 0:
            parts.append(f"规格码 {bore_code:02d}")
        actual_weight = cls._to_number(traits.get("actual_weight"))
        if actual_weight > 0:
            parts.append(f"实际重量 {actual_weight:.2f}kg")
        suffix_hits = [str(hit).strip() for hit in (traits.get("special_suffix_hits") or []) if str(hit).strip()]
        if suffix_hits:
            parts.append(f"特殊后缀 {'/'.join(suffix_hits)}")
        return "，".join(parts)

    @classmethod
    def _resolve_bearing_price_band(cls, item: dict) -> dict:
        traits = cls._extract_bearing_series_traits(item)
        if not traits:
            return {}
        series = str(traits.get("series") or "")
        if series == "62":
            low, high = 20.0, 65.0
        elif series == "63":
            low, high = 72.0, 145.0
        elif series == "64":
            low, high = 95.0, 185.0
        else:
            low, high = 20.0, 80.0
        bore_code = cls._to_int(traits.get("bore_code"))
        if series == "62" and bore_code >= 8:
            low += 12.0
            high += 20.0
        elif series == "63" and bore_code >= 8:
            low += 20.0
            high += 35.0
        elif series == "64" and bore_code >= 8:
            low += 25.0
            high += 40.0
        actual_weight = cls._to_number(traits.get("actual_weight"))
        if actual_weight >= 0.3:
            low += 10.0
            high += 18.0
        suffix_hits = traits.get("special_suffix_hits") or []
        if suffix_hits:
            low += 25.0
            high += 45.0
        return {
            "category": "轴承",
            "low": round(low, 4),
            "high": round(high, 4),
            "basis": cls._build_bearing_basis(traits),
        }

    @classmethod
    def _resolve_bearing_anchor_price(cls, item: dict, low: float, high: float) -> tuple[float, str]:
        traits = cls._extract_bearing_series_traits(item)
        if not traits:
            return round((low + high) / 2.0, 4), "按轴承价格区间中值"
        series = str(traits.get("series") or "")
        if series == "62":
            ratio = 0.34
        elif series == "63":
            ratio = 0.46
        elif series == "64":
            ratio = 0.52
        else:
            ratio = 0.4
        bore_code = cls._to_int(traits.get("bore_code"))
        if bore_code >= 8:
            ratio += 0.08
        if cls._to_number(traits.get("actual_weight")) >= 0.3:
            ratio += 0.05
        if traits.get("special_suffix_hits"):
            ratio += 0.12
        ratio = min(max(ratio, 0.18), 0.88)
        price = low + (high - low) * ratio
        return round(price, 4), f"按轴承规格与后缀复杂度锚定区间 {ratio:.0%} 位置"

    @classmethod
    def _resolve_motor_harness_price_band(cls, item: dict) -> dict:
        quote = cls._resolve_motor_harness_formula_quote(item)
        price = cls._to_number(quote.get("price"))
        if price <= 0:
            return {}
        low = max(price * 0.72, 90.0)
        high = max(price * 1.2, low + 40.0)
        return {
            "category": "电机大线径线束",
            "low": round(low, 4),
            "high": round(high, 4),
            "basis": str(quote.get("note") or "").strip(),
        }

    @classmethod
    def _resolve_motor_shell_price_band(cls, item: dict) -> dict:
        quote = cls._resolve_motor_shell_formula_quote(item)
        price = cls._to_number(quote.get("price"))
        if price <= 0:
            return {}
        low = max(price * 0.75, 80.0)
        high = max(price * 1.22, low + 35.0)
        return {
            "category": "电机壳体盖板类结构件",
            "low": round(low, 4),
            "high": round(high, 4),
            "basis": str(quote.get("note") or "").strip(),
        }

    @classmethod
    def _resolve_name_spec_price_band(cls, item: dict) -> dict:
        precision_housing_band = cls._resolve_precision_housing_price_band(item)
        if precision_housing_band:
            return precision_housing_band
        precision_end_cover_band = cls._resolve_precision_end_cover_price_band(item)
        if precision_end_cover_band:
            return precision_end_cover_band
        precision_shaft_band = cls._resolve_precision_shaft_price_band(item)
        if precision_shaft_band:
            return precision_shaft_band
        motor_harness_band = cls._resolve_motor_harness_price_band(item)
        if motor_harness_band:
            return motor_harness_band
        motor_shell_band = cls._resolve_motor_shell_price_band(item)
        if motor_shell_band:
            return motor_shell_band
        bearing_band = cls._resolve_bearing_price_band(item)
        if bearing_band:
            return bearing_band
        combined = cls._build_item_matching_text(item)
        for band in cls.DEFAULT_NAME_SPEC_PRICE_BANDS:
            if any(str(keyword).lower() in combined for keyword in band.get("keywords", ())):
                low = cls._to_number(band.get("low"))
                high = cls._to_number(band.get("high"))
                if low > 0 and high >= low:
                    return {
                        "category": str(band.get("category") or "").strip(),
                        "low": round(low, 4),
                        "high": round(high, 4),
                        "basis": str(band.get("basis") or "").strip(),
                    }
        return {}

    @classmethod
    def _load_name_spec_price_bands(cls) -> list[dict]:
        path = Path(__file__).resolve().parents[3] / "changjiang-bom-pricing" / "references" / "motor-accessory-price-bands.json"
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                loaded = None
            if isinstance(loaded, list):
                normalized = cls._normalize_name_spec_price_bands(loaded)
                if normalized:
                    return normalized
        return cls._normalize_name_spec_price_bands(list(cls.DEFAULT_NAME_SPEC_PRICE_BANDS))

    @classmethod
    def _normalize_name_spec_price_bands(cls, rows: list[dict] | tuple[dict, ...]) -> list[dict]:
        normalized: list[dict] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            category = str(row.get("category") or "").strip()
            raw_keywords = row.get("keywords") or []
            if isinstance(raw_keywords, str):
                raw_keywords = [part.strip() for part in re.split(r"[，,、/\\|]+", raw_keywords) if part.strip()]
            keywords = [str(keyword).strip() for keyword in raw_keywords if str(keyword).strip()]
            low = cls._to_number(row.get("low"))
            high = cls._to_number(row.get("high"))
            if not category or not keywords or low <= 0 or high < low:
                continue
            normalized.append(
                {
                    "category": category,
                    "keywords": keywords,
                    "low": round(low, 4),
                    "high": round(high, 4),
                    "basis": str(row.get("basis") or "").strip(),
                }
            )
        return normalized

    @classmethod
    def _resolve_precision_end_cover_anchor_price(cls, item: dict, low: float, high: float) -> tuple[float, str]:
        traits = cls._resolve_precision_end_cover_traits(item)
        if not traits:
            return round((low + high) / 2.0, 4), "取区间中值"
        role = str(traits.get("role") or "端盖")
        ratio = 0.5
        if role == "前端盖":
            ratio = 0.58
        elif role == "后端盖":
            ratio = 0.68
        diameter_mm = cls._to_number(traits.get("diameter_mm"))
        if diameter_mm >= 180:
            ratio += 0.04
        elif diameter_mm >= 150:
            ratio += 0.02
        if traits.get("sealing"):
            ratio += 0.03
        if len(traits.get("cnc") or []) >= 2:
            ratio += 0.03
        ratio = min(max(ratio, 0.18), 0.85)
        price = low + (high - low) * ratio
        return round(price, 4), f"按{role}复杂度锚定区间 {ratio:.0%} 位置"

    @classmethod
    def _is_outside_name_spec_price_band(cls, item: dict, unit_price: float) -> bool:
        band = item.get("name_spec_price_band") or {}
        low = cls._to_number(band.get("low"))
        high = cls._to_number(band.get("high"))
        current = cls._to_number(unit_price)
        if low <= 0 or high < low or current <= 0:
            return False
        return current < low or current > high

    @classmethod
    def _apply_name_spec_price_band(cls, item: dict, unit_price: float, reasoning: str) -> tuple[float, str]:
        band = item.get("name_spec_price_band") or {}
        low = cls._to_number(band.get("low"))
        high = cls._to_number(band.get("high"))
        if low <= 0 or high < low:
            return unit_price, reasoning

        category = str(band.get("category") or "名称型物料").strip()
        basis = str(band.get("basis") or "").strip()
        current = cls._to_number(unit_price)
        special_anchor_note = ""
        if category == "电机精密结构端盖":
            formula_quote = cls._resolve_precision_end_cover_formula_quote(item)
            if formula_quote:
                note = str(formula_quote.get("note") or "").strip()
                return cls._to_number(formula_quote.get("price")), note
            formula_quote = cls._resolve_motor_shell_formula_quote(item)
            if formula_quote and any(keyword in cls._build_item_matching_text(item) for keyword in ("接线盒", "盖板")):
                note = str(formula_quote.get("note") or "").strip()
                return cls._to_number(formula_quote.get("price")), note
            anchor_price, special_anchor_note = cls._resolve_precision_end_cover_anchor_price(item, low, high)
        elif category == "电机精密拉伸机壳":
            formula_quote = cls._resolve_precision_housing_formula_quote(item)
            if formula_quote:
                note = str(formula_quote.get("note") or "").strip()
                return cls._to_number(formula_quote.get("price")), note
            anchor_price, special_anchor_note = cls._resolve_precision_housing_anchor_price(item, low, high)
        elif category == "高精轴类机加工件":
            formula_quote = cls._resolve_precision_shaft_formula_quote(item)
            if formula_quote:
                note = str(formula_quote.get("note") or "").strip()
                return cls._to_number(formula_quote.get("price")), note
            anchor_price = round((low + high) / 2.0, 4)
        elif category == "电机大线径线束":
            formula_quote = cls._resolve_motor_harness_formula_quote(item)
            if formula_quote:
                note = str(formula_quote.get("note") or "").strip()
                return cls._to_number(formula_quote.get("price")), note
            anchor_price = round((low + high) / 2.0, 4)
        elif category == "电机壳体盖板类结构件":
            formula_quote = cls._resolve_motor_shell_formula_quote(item)
            if formula_quote:
                note = str(formula_quote.get("note") or "").strip()
                return cls._to_number(formula_quote.get("price")), note
            anchor_price = round((low + high) / 2.0, 4)
        elif category == "轴承":
            anchor_price, special_anchor_note = cls._resolve_bearing_anchor_price(item, low, high)
        else:
            anchor_price = round((low + high) / 2.0, 4)

        if current <= 0:
            current = anchor_price
            note = f"按电机/电控常见{category}区间推断单件价 {low:.2f}-{high:.2f} 元，当前取 {current:.2f} 元。"
        elif current < low:
            current = anchor_price if category == "轴承" and anchor_price >= low else low
            if category == "轴承" and current > low:
                note = f"AI 初始报价低于电机/电控常见{category}区间 {low:.2f}-{high:.2f} 元，已按轴承规格锚定到 {current:.2f} 元。"
            else:
                note = f"AI 初始报价低于电机/电控常见{category}区间 {low:.2f}-{high:.2f} 元，已按区间下限修正。"
        elif current > high:
            current = high
            note = f"AI 初始报价高于电机/电控常见{category}区间 {low:.2f}-{high:.2f} 元，已按区间上限修正。"
        else:
            if category in ("电机精密结构端盖", "电机精密拉伸机壳"):
                current = anchor_price
                note = f'AI 初始报价落在电机/电控常见{category}区间 {low:.2f}-{high:.2f} 元，已按结构复杂度锚定到 {current:.2f} 元。'
            else:
                note = f'AI 初始报价落在电机/电控常见{category}区间 {low:.2f}-{high:.2f} 元内。'

        if special_anchor_note:
            note = f"{note} {special_anchor_note}。".strip()
        if basis:
            note = f"{note} 依据：{basis}"
        merged_reasoning = f"{note} {str(reasoning or '').strip()}".strip()
        return current, merged_reasoning

    @staticmethod
    def _tokenize_similarity_text(*parts: object) -> set[str]:
        text = " ".join(str(part or "").strip().lower() for part in parts if str(part or "").strip())
        if not text:
            return set()
        return {
            token for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text)
            if len(token) >= 2 or re.search(r"[\u4e00-\u9fff]", token)
        }

    @classmethod
    def _estimate_similar_weight(cls, item: dict, items: list[dict]) -> tuple[float, str]:
        if cls._to_number(item.get("weight_kg")) > 0:
            return 0.0, ""
        material = str(item.get("material_alias") or item.get("material") or "").strip()
        if not material or material == "未识别":
            return 0.0, ""

        target_process = str(item.get("process") or "").strip()
        target_name = str(item.get("name") or "").strip()
        target_spec = str(item.get("spec") or "").strip()
        target_tokens = cls._tokenize_similarity_text(target_name, target_spec)
        candidates: list[tuple[float, float, str]] = []

        for candidate in items:
            if candidate is item:
                continue
            weight_kg = cls._to_number(candidate.get("weight_kg"))
            if weight_kg <= 0:
                continue
            candidate_material = str(candidate.get("material_alias") or candidate.get("material") or "").strip()
            if not candidate_material or candidate_material == "未识别":
                continue

            score = 0.0
            if candidate_material == material:
                score += 6.0
            elif material in candidate_material or candidate_material in material:
                score += 4.0
            else:
                continue

            candidate_process = str(candidate.get("process") or "").strip()
            if target_process and candidate_process == target_process:
                score += 2.5
            elif target_process and candidate_process and (target_process in candidate_process or candidate_process in target_process):
                score += 1.5

            candidate_tokens = cls._tokenize_similarity_text(candidate.get("name"), candidate.get("spec"))
            token_overlap = len(target_tokens & candidate_tokens)
            score += min(token_overlap, 4) * 0.7

            if target_name and target_name == str(candidate.get("name") or "").strip():
                score += 1.2
            if target_spec and target_spec == str(candidate.get("spec") or "").strip():
                score += 1.2

            candidates.append((score, weight_kg, str(candidate.get("code") or "").strip()))

        if not candidates:
            return 0.0, ""

        candidates.sort(key=lambda row: (row[0], -abs(row[1])), reverse=True)
        selected = candidates[: min(3, len(candidates))]
        estimated_weight_kg = float(statistics.median([row[1] for row in selected]))
        ref_codes = "、".join(code for _, _, code in selected if code) or "相近物料"
        note = f"原始重量缺失，已按同材质相近物料估重 {estimated_weight_kg:.4f}kg（参考 {ref_codes}）参与 AI 估价，请复核。"
        return estimated_weight_kg, note

    @classmethod
    def _resolve_name_spec_weight_band(cls, item: dict) -> dict:
        precision_housing_band = cls._resolve_precision_housing_weight_band(item)
        if precision_housing_band:
            return precision_housing_band
        precision_end_cover_band = cls._resolve_precision_end_cover_weight_band(item)
        if precision_end_cover_band:
            return precision_end_cover_band
        precision_shaft_band = cls._resolve_precision_shaft_weight_band(item)
        if precision_shaft_band:
            return precision_shaft_band
        combined = cls._build_item_matching_text(item)
        for band in cls.DEFAULT_NAME_SPEC_WEIGHT_BANDS:
            if any(str(keyword).lower() in combined for keyword in band.get("keywords", ())):
                low = cls._to_number(band.get("low"))
                high = cls._to_number(band.get("high"))
                default = cls._to_number(band.get("default"))
                if low > 0 and high >= low and default >= low and default <= high:
                    return {
                        "category": str(band.get("category") or "").strip(),
                        "low": round(low, 4),
                        "high": round(high, 4),
                        "default": round(default, 4),
                        "basis": str(band.get("basis") or "").strip(),
                    }
        return {}

    @classmethod
    def _apply_name_spec_weight_band(cls, item: dict, estimated_weight_kg: float, note: str) -> tuple[float, str]:
        band = item.get("name_spec_weight_band") or {}
        low = cls._to_number(band.get("low"))
        high = cls._to_number(band.get("high"))
        default = cls._to_number(band.get("default"))
        if low <= 0 or high < low or default <= 0:
            return estimated_weight_kg, note

        category = str(band.get("category") or "名称型物料").strip()
        basis = str(band.get("basis") or "").strip()
        normalized_note = str(note or "").strip()
        actual_weight = cls._to_number(item.get("weight_kg")) or cls._to_number(item.get("effective_weight_kg"))
        if actual_weight > 0:
            return estimated_weight_kg, note

        if estimated_weight_kg <= 0:
            adjusted = default
            prefix = (
                f"原始重量缺失，已按电机/电控常见{category}重量区间 "
                f"{low:.4f}-{high:.4f}kg 推断单件重量 {adjusted:.4f}kg。"
            )
        elif estimated_weight_kg < low or estimated_weight_kg > high:
            adjusted = default
            prefix = (
                f"原始重量缺失，名称型配件初始估重 {estimated_weight_kg:.4f}kg 超出电机/电控常见{category}重量区间 "
                f"{low:.4f}-{high:.4f}kg，已按更合理的单件重量 {adjusted:.4f}kg 修正。"
            )
        else:
            return estimated_weight_kg, note

        if basis:
            prefix = f"{prefix} 依据：{basis}"
        merged_note = f"{prefix} {normalized_note}".strip()
        return round(adjusted, 4), merged_note

    @staticmethod
    def _classify_ai_exception(message: str) -> tuple[str, str]:
        text = str(message or "").strip()
        lower = text.lower()
        if any(keyword in lower for keyword in ("timeout", "timed out", "readtimeout", "connecttimeout", "httpsconnectionpool", "read timed out")):
            return "模型超时：千问接口未在限定时间内返回结果，可重试本次报价", "模型超时"
        if any(keyword in lower for keyword in ("proxyerror", "sslerror", "max retries exceeded", "newconnectionerror", "connection aborted", "connection reset")):
            return "AI接口异常：千问接口当前连接不稳定，请稍后重试", "AI接口异常"
        if any(keyword in lower for keyword in ("invalid chat format", "invalid_request_error", "expected 'text' field", "qwen pricing api error 400")):
            return "AI接口请求格式异常：服务已调整，请重新报价", "AI接口异常"
        if "api key" in lower or "未配置" in text:
            return "AI未配置：未配置千问 API key，已跳过 AI 报价", "AI未配置"
        return (f"待AI报价：{text}" if text else "待AI报价：未形成有效报价", "待AI报价")

    @staticmethod
    def _classify_ai_result(unit_price: float, reasoning: str) -> tuple[str, str]:
        text = str(reasoning or "").strip()
        lower = text.lower()
        if unit_price > 0:
            return "AI可用", text or "AI 已返回有效报价"
        if "缺重量" in text:
            return "缺重量", text
        if "缺材质" in text:
            return "缺材质", text
        if any(keyword in lower for keyword in ("timeout", "timed out", "readtimeout", "connecttimeout", "httpsconnectionpool", "read timed out")):
            return "模型超时", text or "模型超时：千问接口未在限定时间内返回结果，可重试本次报价"
        if any(keyword in lower for keyword in ("proxyerror", "sslerror", "max retries exceeded", "newconnectionerror", "connection aborted", "connection reset")):
            return "AI接口异常", text or "AI接口异常：千问接口当前连接不稳定，请稍后重试"
        if any(keyword in lower for keyword in ("invalid chat format", "invalid_request_error", "expected 'text' field", "qwen pricing api error 400")):
            return "AI接口异常", "AI接口请求格式异常：服务已调整，请重新报价"
        if "api key" in lower or "未配置" in text:
            return "AI未配置", text or "AI未配置：未配置千问 API key，已跳过 AI 报价"
        return "待AI报价", text or "待AI报价：模型未返回有效价格"

    @staticmethod
    def _read_csv_dicts(path: Path) -> list[dict]:
        for encoding in ("utf-8-sig", "gb18030", "gbk"):
            try:
                with path.open("r", encoding=encoding, newline="") as handle:
                    return list(csv.DictReader(handle))
            except Exception:
                continue
        return []

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _notify_progress(
        progress_callback: Callable[[dict], None] | None,
        *,
        stage: str,
        processed: int,
        total: int,
        message: str,
        **extra: object,
    ) -> None:
        if progress_callback is None:
            return
        payload = {"stage": stage, "processed": processed, "total": total, "message": message}
        payload.update(extra)
        progress_callback(payload)

    @staticmethod
    def _material_alias(text: str) -> str:
        normalized = str(text or "").lower()
        if not normalized.strip():
            return ""
        if "铜" in normalized:
            return "铜"
        if any(token in normalized for token in ("硅钢", "35w", "b30")):
            return "硅钢"
        if "铝" in normalized:
            return "铝"
        if any(token in normalized for token in ("镨钕", "钕铁硼", "n35", "n38", "n40", "n42", "n45", "n48", "n50", "n52", "磁")):
            return "磁材"
        if any(token in normalized for token in ("20cr", "钢")):
            return "钢材"
        return "未识别"

    @staticmethod
    def _to_number(value) -> float:
        if value is None or value == "":
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "").replace("，", "")
        text = text.replace("¥", "").replace("元", "")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else 0.0

    @staticmethod
    def _to_int(value) -> int:
        return int(FinanceSkillQuoteService._to_number(value) or 0)

    @staticmethod
    def _describe_volume_tier_label(annual_volume) -> str:
        volume = FinanceSkillQuoteService._to_int(annual_volume)
        if volume <= 300:
            return "<=300"
        if volume <= 1000:
            return "301-1000"
        if volume <= 3000:
            return "1001-3000"
        if volume <= 5000:
            return "3001-5000"
        if volume <= 8000:
            return "5001-8000"
        if volume <= 10000:
            return "8001-10000"
        if volume <= 20000:
            return "10001-20000"
        if volume <= 50000:
            return "20001-50000"
        return ">50000"

    @staticmethod
    def _derive_mass_volume_prices(
        *,
        baseline_unit: float,
        annual_volume: int,
        conservative_ratio: float = 0.0,
        aggressive_ratio: float = 0.0,
        manual_surcharge_unit: float = 0.0,
    ) -> dict:
        baseline_value = FinanceSkillQuoteService._to_number(baseline_unit)
        surcharge_value = FinanceSkillQuoteService._to_number(manual_surcharge_unit)
        conservative_ratio_value = FinanceSkillQuoteService._to_number(conservative_ratio)
        aggressive_ratio_value = FinanceSkillQuoteService._to_number(aggressive_ratio)
        conservative_discount = 0.0
        aggressive_discount = 0.0

        if baseline_value > 0 and conservative_ratio_value > 0:
            conservative_unit_price = baseline_value * conservative_ratio_value + surcharge_value
            conservative_discount = max(0.0, 1.0 - conservative_ratio_value)
        elif baseline_value > 0:
            conservative_discount, aggressive_discount = FinanceSkillQuoteService._mass_tooling_discount_fallback(annual_volume)
            conservative_unit_price = round(baseline_value * (1.0 - conservative_discount), 4)
        else:
            conservative_unit_price = 0.0

        if baseline_value > 0 and aggressive_ratio_value > 0:
            aggressive_unit_price = baseline_value * aggressive_ratio_value + surcharge_value
            aggressive_discount = max(0.0, 1.0 - aggressive_ratio_value)
        elif baseline_value > 0:
            if aggressive_discount <= 0:
                _, aggressive_discount = FinanceSkillQuoteService._mass_tooling_discount_fallback(annual_volume)
            aggressive_unit_price = round(baseline_value * (1.0 - aggressive_discount), 4)
        else:
            aggressive_unit_price = 0.0

        return {
            "baseline_unit_price": round(baseline_value, 4),
            "conservative_unit_price": round(conservative_unit_price, 4),
            "aggressive_unit_price": round(aggressive_unit_price, 4),
            "conservative_discount": round(conservative_discount, 4),
            "aggressive_discount": round(aggressive_discount, 4),
        }

    @classmethod
    def _ensure_mass_volume_prices(cls, item: dict, *, qty: float = 1.0, manual_surcharge_unit: float = 0.0) -> None:
        if cls._normalize_production_mode(item.get("production_mode")) != "mass":
            return
        baseline_unit = cls._to_number(item.get("volume_baseline_unit_price") or item.get("ai_route_unit_price"))
        conservative_unit = cls._to_number(item.get("volume_conservative_unit_price"))
        aggressive_unit = cls._to_number(item.get("volume_aggressive_unit_price"))
        if baseline_unit <= 0:
            return
        if conservative_unit > 0 and aggressive_unit > 0:
            return
        prices = cls._derive_mass_volume_prices(
            baseline_unit=baseline_unit,
            annual_volume=cls._to_int(item.get("annual_volume")),
            manual_surcharge_unit=manual_surcharge_unit,
        )
        item["volume_baseline_unit_price"] = baseline_unit
        item["volume_conservative_unit_price"] = cls._to_number(prices.get("conservative_unit_price"))
        item["volume_aggressive_unit_price"] = cls._to_number(prices.get("aggressive_unit_price"))
        item["volume_conservative_discount"] = cls._to_number(item.get("volume_conservative_discount")) or cls._to_number(prices.get("conservative_discount"))
        item["volume_aggressive_discount"] = cls._to_number(item.get("volume_aggressive_discount")) or cls._to_number(prices.get("aggressive_discount"))
        qty_value = cls._to_number(qty) or 1.0
        item["volume_baseline_total_price"] = cls._to_number(item.get("volume_baseline_unit_price")) * qty_value
        item["volume_conservative_total_price"] = cls._to_number(item.get("volume_conservative_unit_price")) * qty_value
        item["volume_aggressive_total_price"] = cls._to_number(item.get("volume_aggressive_unit_price")) * qty_value
        volume_tier_label = cls._describe_volume_tier_label(item.get("annual_volume"))
        item["volume_tier_label"] = volume_tier_label
        volume_summary = str(item.get("volume_pricing_summary") or "").strip()
        prefix = (
            f"量产口径（{cls._to_int(item.get('annual_volume'))}套/年，{volume_tier_label}档）："
            f"基准 {cls._to_number(item.get('volume_baseline_unit_price')):.2f} / 保守 {cls._to_number(item.get('volume_conservative_unit_price')):.2f} / 激进 {cls._to_number(item.get('volume_aggressive_unit_price')):.2f} 元"
        )
        if volume_summary:
            parts = volume_summary.split("；", 1)
            item["volume_pricing_summary"] = f"{prefix}；{parts[1]}" if len(parts) > 1 else prefix
        else:
            item["volume_pricing_summary"] = prefix

    @staticmethod
    def _mass_tooling_discount_fallback(annual_volume: int) -> tuple[float, float]:
        volume = FinanceSkillQuoteService._to_int(annual_volume)
        if volume <= 300:
            return 0.01, 0.03
        if volume <= 1000:
            return 0.02, 0.04
        if volume <= 3000:
            return 0.03, 0.06
        if volume <= 5000:
            return 0.04, 0.08
        if volume <= 8000:
            return 0.05, 0.10
        if volume <= 10000:
            return 0.06, 0.12
        if volume <= 20000:
            return 0.07, 0.14
        if volume <= 50000:
            return 0.08, 0.16
        return 0.10, 0.18

    @staticmethod
    def _normalize_production_mode(value: object) -> str:
        text = str(value or "").strip().lower()
        return "mass" if text in {"mass", "volume", "量产"} else "sample"

    @staticmethod
    def _model_label(model: dict | None) -> str:
        model = model or {}
        return str(model.get("label") or model.get("bom_number") or model.get("filename") or "Skill报价").strip()


