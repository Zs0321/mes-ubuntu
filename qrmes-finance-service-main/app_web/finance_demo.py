from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import re
from threading import Lock, Thread
from time import time
from urllib.parse import quote
from uuid import uuid4

from flask import Blueprint, Response, jsonify, redirect, render_template, request, send_from_directory
from markupsafe import Markup
from openpyxl import Workbook

from qrmes_shared_core.auth import login_required
from backend.config import load_config
from backend.server import DemoApplication
from backend.services.excel_quote_service import ExcelQuoteService
from backend.services.finance_skill_quote_service import FinanceSkillQuoteService
from qrmes_shared_core.config import config as app_config
from qrmes_shared_core.data_dir_utils import resolve_data_dir

finance_demo_bp = Blueprint("finance_demo", __name__)
_QUOTE_TASKS: dict[str, dict] = {}
_QUOTE_TASKS_LOCK = Lock()
_QUOTE_TASK_TTL_SECONDS = 3600


@lru_cache(maxsize=1)
def get_demo_application() -> DemoApplication:
    static_dir = Path(__file__).resolve().parent / "static" / "finance_demo"
    return DemoApplication(load_config(static_dir=static_dir))


def _static_dir() -> Path:
    return Path(__file__).resolve().parent / "static" / "finance_demo"


@lru_cache(maxsize=1)
def _finance_demo_markup() -> Markup:
    index_html = (_static_dir() / "index.html").read_text(encoding="utf-8-sig")
    match = re.search(r"<body[^>]*>(?P<body>.*)</body>", index_html, re.IGNORECASE | re.DOTALL)
    body = match.group("body").strip() if match else index_html
    body = re.sub(r"<script\b[^>]*>.*?</script>", "", body, flags=re.IGNORECASE | re.DOTALL)
    return Markup(body)


def _scope_selector(selector: str, scope: str) -> str:
    selector = selector.strip()
    if not selector:
        return selector
    if selector.startswith(scope):
        return selector
    if selector.startswith(":root"):
        return selector.replace(":root", scope, 1)
    if selector.startswith("body"):
        return selector.replace("body", scope, 1)
    if selector.startswith("html"):
        return selector.replace("html", scope, 1)
    return f"{scope} {selector}"


def _scope_css(css_text: str, scope: str = ".finance-demo-page") -> str:
    result: list[str] = []
    buffer: list[str] = []
    stack: list[str] = []

    for char in css_text:
        if char == "{":
            prelude = "".join(buffer)
            buffer = []
            stripped = prelude.strip()

            if stripped.startswith("@"):
                result.append(prelude)
                result.append("{")
                if stripped.startswith("@keyframes"):
                    stack.append("keyframes")
                else:
                    stack.append("at-rule")
                continue

            if "keyframes" in stack:
                result.append(prelude)
                result.append("{")
            else:
                selectors = prelude.split(",")
                scoped = ", ".join(_scope_selector(item, scope) for item in selectors)
                result.append(scoped)
                result.append("{")
            stack.append("rule")
            continue

        if char == "}":
            result.append("".join(buffer))
            result.append("}")
            buffer = []
            if stack:
                stack.pop()
            continue

        buffer.append(char)

    if buffer:
        result.append("".join(buffer))

    return "".join(result)


def _normalize_quote_mode_label(production_mode: object) -> str:
    mode = str(production_mode or "").strip().lower()
    return "量产" if mode in {"mass", "volume", "量产"} else "非量产"


def _sanitize_quote_project_label(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower().endswith(".xlsx"):
        text = text[:-5]
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text).strip("_")
    if normalized in {"粘贴表格报价", "报价结果", "报价汇总包"}:
        return ""
    return normalized


def _build_quote_download_name(model: dict | None, *, suffix: str, extension: str) -> str:
    model = model or {}
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    project_label = (
        _sanitize_quote_project_label(model.get("original_label"))
        or _sanitize_quote_project_label(model.get("label"))
        or _sanitize_quote_project_label(model.get("project_name"))
        or _sanitize_quote_project_label(model.get("product_name"))
    )
    requested_volume_label = _sanitize_quote_project_label(model.get("requested_volume_label"))
    requested_volume_match = re.search(r"(\d+)套年", requested_volume_label) if requested_volume_label else None
    annual_volume = int(float(model.get("requested_annual_volume") or model.get("annual_volume") or 0) or 0)
    volume_label = (f"{requested_volume_match.group(1)}套年" if requested_volume_match else "") or (f"{annual_volume}套年" if annual_volume > 0 else "")
    mode_label = _normalize_quote_mode_label(model.get("production_mode"))
    parts = [timestamp]
    if project_label:
        parts.append(project_label)
    if volume_label:
        parts.append(volume_label)
    parts.append(mode_label)
    parts.append(suffix)
    return "_".join(parts) + extension


@lru_cache(maxsize=1)
def _finance_demo_styles() -> str:
    raw_css = (_static_dir() / "styles.css").read_text(encoding="utf-8-sig")
    return _scope_css(raw_css)


def _dispatch_api():
    app = get_demo_application()
    body = request.get_json(silent=True) if request.method != "GET" else None
    status, payload = app.handle_api(
        request.method,
        request.path,
        request.args.to_dict(flat=False),
        body,
    )
    return jsonify(payload), int(status)


def get_excel_quote_service() -> ExcelQuoteService:
    app = get_demo_application()
    return ExcelQuoteService(app.config, app.kingdee_service)


@lru_cache(maxsize=1)
def get_finance_skill_quote_service() -> FinanceSkillQuoteService:
    app = get_demo_application()
    return FinanceSkillQuoteService(app.config, app.kingdee_service)


def _excel_upload_root() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    data_root = resolve_data_dir(
        nas_local_base_path=getattr(app_config, "nas_local_base_path", None),
        repo_root=repo_root,
        create=True,
    )
    return data_root / "uploads" / "excel_quotes"


def _archive_excel_upload(file_bytes: bytes, original_filename: str) -> Path:
    safe_name = re.sub(r"[^\w.\u4e00-\u9fff-]+", "_", Path(original_filename or "excel_quote.xlsx").name).strip("._")
    if not safe_name.lower().endswith(".xlsx"):
        safe_name = f"{safe_name or 'excel_quote'}.xlsx"

    date_dir = _excel_upload_root() / datetime.now().strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    archived_name = f"{datetime.now().strftime('%H%M%S_%f')}_{safe_name}"
    archived_path = date_dir / archived_name
    archived_path.write_bytes(file_bytes)
    return archived_path


def _build_pasted_workbook_bytes(table_text: str) -> tuple[bytes, int]:
    raw_text = str(table_text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\ufeff \n\t")
    if not raw_text:
        raise ValueError("请先粘贴 Excel 表格数据")

    non_empty_lines = [line for line in raw_text.split("\n") if line.strip()]
    if len(non_empty_lines) < 2:
        raise ValueError("请至少粘贴表头和一行数据")

    sample = "\n".join(non_empty_lines[:5])
    delimiter = "\t" if "\t" in sample else ("," if "," in sample else None)
    if not delimiter:
        raise ValueError("未识别出表格分隔符，请直接从 Excel 复制带列头的数据区域后粘贴")

    reader = csv.reader(io.StringIO("\n".join(non_empty_lines)), delimiter=delimiter)
    rows = []
    max_width = 0
    for row in reader:
        normalized = [str(cell or "").strip() for cell in row]
        if not any(normalized):
            continue
        rows.append(normalized)
        max_width = max(max_width, len(normalized))

    if len(rows) < 2:
        raise ValueError("粘贴内容未解析出有效数据行，请确认第一行为表头，后续为明细")

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Sheet1"
    for row in rows:
        worksheet.append(row + [""] * max(0, max_width - len(row)))

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), max(len(rows) - 1, 0)


def _prune_quote_tasks_locked(now_ts: float) -> None:
    expired_ids = [
        task_id
        for task_id, task in _QUOTE_TASKS.items()
        if now_ts - float(task.get("updated_at_ts", now_ts)) > _QUOTE_TASK_TTL_SECONDS
    ]
    for task_id in expired_ids:
        _QUOTE_TASKS.pop(task_id, None)


def _coerce_progress_number(value: object, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _build_ai_route_waiting_progress(total: int, parallel_workers: int, elapsed_seconds: int) -> dict:
    waited = max(int(elapsed_seconds or 0), 1)
    return {
        "stage": "ai_pricing",
        "processed": 0,
        "total": int(total or 0),
        "message": f"AI 首批结果返回较慢，已等待 {waited} 秒",
        "percent": min(42.0 + waited * 0.35, 68.0),
        "parallel_workers": int(parallel_workers or 0),
        "mode": "parallel",
        "elapsed_seconds": waited,
        "waiting_first_result": True,
    }


def _progress_stage_label(stage: str) -> str:
    labels = {
        "queued": "任务排队",
        "preparing": "准备数据",
        "market_pricing": "在线询价",
        "rule_pricing": "规则报价",
        "pricing": "传统报价",
        "ai_supplement": "AI补充",
        "ai_pricing": "AI并行报价",
        "finalizing": "汇总导出",
        "done": "报价完成",
    }
    return labels.get(str(stage or "").strip(), "报价处理中")


def _build_progress_log_entry(progress: dict | None) -> str:
    raw = progress or {}
    stage = str(raw.get("stage") or "").strip()
    message = str(raw.get("message") or "").strip()
    hint = str(raw.get("hint") or "").strip()
    analysis = str(raw.get("analysis_log_text") or raw.get("analysisLogText") or "").strip()
    processed = int(raw.get("processed") or 0)
    total = int(raw.get("total") or 0)
    stage_label = _progress_stage_label(stage)
    timestamp = datetime.now().strftime("%H:%M:%S")
    headline = f"[{timestamp}] {stage_label}"
    if total > 0 and stage not in {"queued", "done"}:
        headline = f"{headline} ({processed}/{total})"
    parts: list[str] = []
    if message:
        parts.append(f"{headline} {message}")
    elif stage_label:
        parts.append(headline)
    if hint and hint != message:
        parts.append(f"提示：{hint}")
    if analysis:
        parts.append(analysis)
    return "\n".join(part for part in parts if part).strip()


def _append_progress_log(existing_text: str, progress: dict | None) -> str:
    existing = str(existing_text or "").strip()
    entry = _build_progress_log_entry(progress)
    if not entry:
        return existing
    if not existing:
        return entry
    if entry in existing:
        return existing
    return f"{existing}\n\n{entry}"


def _normalize_quote_progress(progress: dict | None) -> dict:
    raw = progress or {}
    stage = str(raw.get("stage") or "running")
    processed = int(raw.get("processed") or 0)
    total = int(raw.get("total") or 0)
    message = str(raw.get("message") or "")
    parallel_workers = int(raw.get("parallel_workers") or 0)
    mode = str(raw.get("mode") or ("parallel" if stage == "ai_pricing" else "serial"))
    elapsed_seconds = int(_coerce_progress_number(raw.get("elapsed_seconds"), 0))
    waiting_first_result = bool(raw.get("waiting_first_result"))
    _skill_stage_aliases = {
        "market_pricing": "在线价格查询",
        "rule_pricing": "规则报价计算",
        "ai_supplement": "AI补充复核",
    }
    ratio = min(max(processed / total, 0.0), 1.0) if total > 0 else 0.0
    stage_meta = {
        "queued": ("排队中", 0.0, 0.04),
        "preparing": ("准备 Excel 数据", 0.04, 0.14),
        "market_pricing": ("在线价格查询", 0.14, 0.32),
        "rule_pricing": ("规则报价计算", 0.32, 0.58),
        "pricing": ("生成财务传统报价", 0.14, 0.42),
        "ai_supplement": ("AI补充复核", 0.58, 0.9),
        "ai_pricing": ("并行生成 AI 报价", 0.42, 0.92),
        "finalizing": ("汇总报价结果", 0.92, 0.99),
        "done": ("报价完成", 1.0, 1.0),
        "running": ("报价处理中", 0.0, 0.95),
    }
    stage_label, percent_start, percent_end = stage_meta.get(stage, stage_meta["running"])
    explicit_percent = raw.get("percent")
    if explicit_percent not in (None, ""):
        percent = _coerce_progress_number(explicit_percent, percent_start * 100)
    elif percent_start == percent_end:
        percent = percent_end * 100
    else:
        percent = (percent_start + (percent_end - percent_start) * ratio) * 100
    if stage == "done":
        percent = 100.0
    hint = ""
    if stage == "ai_pricing" and waiting_first_result and parallel_workers > 0:
        hint = f"AI 兜底并行处理已启动 {parallel_workers} 路，正在等待首批结果返回，当前已等待 {elapsed_seconds} 秒"
    elif stage == "ai_pricing" and parallel_workers > 0:
        hint = f"AI 兜底阶段正在并行处理，当前并发 {parallel_workers} 路"
    elif stage == "market_pricing":
        hint = "正在调用 skill 原生脚本查询在线原材价格与市场快照"
    elif stage == "rule_pricing":
        hint = "正在按 skill 原生规则脚本生成传统报价与规则估算"
    elif stage == "ai_supplement" and parallel_workers > 0:
        hint = f"AI 报价补充复核阶段正在并行执行，当前并发 {parallel_workers} 路"
    elif stage == "ai_supplement":
        hint = "正在基于最新 skill 上下文补充基准报价，规则缺口时再调用 AI 兜底"
    elif stage == "pricing":
        hint = "先计算财务传统报价，再由 AI 结合 skills 知识内容生成报价"
    elif stage == "finalizing":
        hint = "正在汇总多个报价结果表，马上生成下载包"
    script_plan = raw.get("script_plan") or raw.get("skill_script_plan") or None
    analysis_log_text = str(raw.get("analysis_log_text") or raw.get("analysisLogText") or "").strip()
    return {
        "stage": stage,
        "stage_label": stage_label,
        "processed": processed,
        "total": total,
        "message": message,
        "percent": round(percent, 1),
        "parallel_workers": parallel_workers,
        "mode": mode,
        "hint": hint,
        "elapsed_seconds": elapsed_seconds,
        "waiting_first_result": waiting_first_result,
        **({"script_plan": script_plan} if script_plan else {}),
        **({"analysis_log_text": analysis_log_text} if analysis_log_text else {}),
    }


def _create_quote_task(filename: str, model_label: str, archived_path: Path) -> dict:
    now_ts = time()
    initial_progress = _normalize_quote_progress({
        "stage": "queued",
        "processed": 0,
        "total": 0,
        "message": "任务排队中",
    })
    initial_progress["analysis_log_text"] = _append_progress_log("", initial_progress)
    task = {
        "task_id": uuid4().hex,
        "status": "queued",
        "message": "报价任务已创建",
        "filename": filename,
        "model_label": model_label,
        "created_at_ts": now_ts,
        "updated_at_ts": now_ts,
        "progress": _normalize_quote_progress({
            "stage": "queued",
            "processed": 0,
            "total": 0,
            "message": "排队中",
        }),
        "payload": None,
        "error": "",
        "error_code": "",
        "archived_path": str(archived_path),
        "archived_relative_path": str(archived_path.relative_to(_excel_upload_root().parent)),
    }
    task["progress"] = initial_progress
    with _QUOTE_TASKS_LOCK:
        _prune_quote_tasks_locked(now_ts)
        _QUOTE_TASKS[task["task_id"]] = task
    return task.copy()


def _create_ai_route_task(model: dict | None, item_count: int) -> dict:
    model = model or {}
    model_label = str(model.get("label") or model.get("bom_number") or model.get("filename") or "基准报价任务").strip()
    now_ts = time()
    initial_progress = _normalize_quote_progress({
        "stage": "queued",
        "processed": 0,
        "total": int(item_count or 0),
        "message": "AI 报价任务排队中",
        "mode": "parallel",
    })
    initial_progress["analysis_log_text"] = _append_progress_log("", initial_progress)
    task = {
        "task_id": uuid4().hex,
        "quote_kind": "ai_route",
        "status": "queued",
        "message": "AI报价任务已创建",
        "filename": model_label,
        "model_label": model_label,
        "created_at_ts": now_ts,
        "updated_at_ts": now_ts,
        "progress": _normalize_quote_progress({
            "stage": "queued",
            "processed": 0,
            "total": int(item_count or 0),
            "message": "AI报价任务排队中",
            "mode": "parallel",
        }),
        "payload": None,
        "error": "",
        "error_code": "",
        "archived_path": "",
        "archived_relative_path": "",
    }
    task["progress"] = initial_progress
    with _QUOTE_TASKS_LOCK:
        _prune_quote_tasks_locked(now_ts)
        _QUOTE_TASKS[task["task_id"]] = task
    return task.copy()


def _update_quote_task(task_id: str, **updates) -> None:
    with _QUOTE_TASKS_LOCK:
        task = _QUOTE_TASKS.get(task_id)
        if not task:
            return
        task.update(updates)
        task["updated_at_ts"] = time()


def _update_quote_task_progress(task_id: str, progress: dict, status: str = "running") -> None:
    current = _get_quote_task(task_id) or {}
    current_progress = current.get("progress") or {}
    normalized_progress = _normalize_quote_progress(progress)
    if not normalized_progress.get("script_plan") and current_progress.get("script_plan"):
        normalized_progress["script_plan"] = current_progress.get("script_plan")
    normalized_progress["analysis_log_text"] = _append_progress_log(
        current_progress.get("analysis_log_text", ""),
        normalized_progress,
    )
    normalized_progress["percent"] = round(
        max(
            _coerce_progress_number(current_progress.get("percent"), 0.0),
            _coerce_progress_number(normalized_progress.get("percent"), 0.0),
        ),
        1,
    )
    _update_quote_task(
        task_id,
        status=status,
        message=str(progress.get("message") or ""),
        progress=normalized_progress,
    )


def _get_quote_task(task_id: str) -> dict | None:
    with _QUOTE_TASKS_LOCK:
        task = _QUOTE_TASKS.get(task_id)
        if not task:
            return None
        return {
            key: value
            for key, value in task.items()
            if key not in {"created_at_ts", "updated_at_ts"}
        }


def _run_quote_task(
    task_id: str,
    file_bytes: bytes,
    filename: str,
    model_label: str,
    production_mode: str = "sample",
    annual_volume: int = 0,
) -> None:
    _update_quote_task_progress(task_id, {
        "stage": "preparing",
        "processed": 0,
        "total": 0,
        "message": "正在读取 Excel",
    })
    try:
        payload = get_excel_quote_service().quote_workbook(
            file_bytes,
            filename=filename,
            model_label=model_label,
            production_mode=production_mode,
            annual_volume=annual_volume,
            progress_callback=lambda progress: _update_quote_task_progress(task_id, progress),
        )
        task = _get_quote_task(task_id) or {}
        payload.setdefault("model", {})
        payload["model"]["archived_path"] = task.get("archived_path", "")
        payload["model"]["archived_relative_path"] = task.get("archived_relative_path", "")
        payload["analysis_log_text"] = str((task.get("progress") or {}).get("analysis_log_text") or "").strip()
        completion_progress = {
            "stage": "done",
            "processed": int(payload.get("model", {}).get("item_count") or 0),
            "total": int(payload.get("model", {}).get("item_count") or 0),
            "message": "报价完成，已生成导出结果",
        }
        final_progress = _normalize_quote_progress(completion_progress)
        final_progress["analysis_log_text"] = _append_progress_log(payload.get("analysis_log_text", ""), completion_progress)
        payload["exports"] = get_excel_quote_service().describe_quote_exports(payload)
        _update_quote_task(
            task_id,
            status="succeeded",
            message="报价完成",
            progress=final_progress,
            payload=payload,
            error="",
            error_code="",
        )
    except ValueError as exc:
        failure_progress = {
            "stage": "finalizing",
            "processed": 0,
            "total": 0,
            "message": f"报价失败：{exc}",
            "hint": "请检查 Excel 模板、必填字段和报价规则后重试。",
        }
        current_task = _get_quote_task(task_id) or {}
        final_progress = _normalize_quote_progress(failure_progress)
        final_progress["analysis_log_text"] = _append_progress_log(
            str((current_task.get("progress") or {}).get("analysis_log_text") or "").strip(),
            failure_progress,
        )
        _update_quote_task(
            task_id,
            status="failed",
            message=str(exc),
            progress=final_progress,
            error=str(exc),
            error_code="INVALID_WORKBOOK",
        )
    except Exception as exc:  # pragma: no cover - defensive
        failure_progress = {
            "stage": "finalizing",
            "processed": 0,
            "total": 0,
            "message": f"报价失败：{exc}",
            "hint": "服务端执行报价时发生异常，请稍后重试。",
        }
        current_task = _get_quote_task(task_id) or {}
        final_progress = _normalize_quote_progress(failure_progress)
        final_progress["analysis_log_text"] = _append_progress_log(
            str((current_task.get("progress") or {}).get("analysis_log_text") or "").strip(),
            failure_progress,
        )
        _update_quote_task(
            task_id,
            status="failed",
            message=str(exc),
            progress=final_progress,
            error=str(exc),
            error_code="EXCEL_QUOTE_FAILED",
        )


def _run_ai_route_task(task_id: str, items: list[dict], model: dict, scenario_source: str) -> None:
    total = len(items)
    parallel_workers = min(max(total, 1), 4)
    _update_quote_task_progress(task_id, {
        "stage": "preparing",
        "processed": 0,
        "total": total,
        "message": "正在准备 AI 报价数据",
        "mode": "parallel",
    })
    _update_quote_task_progress(task_id, {
        "stage": "ai_pricing",
        "processed": 0,
        "total": total,
        "message": "正在结合 skills 知识内容生成 AI 报价",
        "parallel_workers": parallel_workers,
        "mode": "parallel",
    })
    try:
        payload = get_finance_skill_quote_service().quote_items(
            items,
            model={**(model or {}), "scenario_source": scenario_source},
            progress_callback=lambda progress: _update_quote_task_progress(task_id, progress),
        )
        payload.setdefault("model", {})
        payload["model"].setdefault("item_count", total)
        current_task = _get_quote_task(task_id) or {}
        payload["analysis_log_text"] = str((current_task.get("progress") or {}).get("analysis_log_text") or "").strip()
        completion_progress = {
            "stage": "done",
            "processed": total,
            "total": total,
            "message": "AI 报价处理完成",
            "parallel_workers": parallel_workers,
            "mode": "parallel",
        }
        final_progress = _normalize_quote_progress(completion_progress)
        final_progress["analysis_log_text"] = _append_progress_log(payload.get("analysis_log_text", ""), completion_progress)
        _update_quote_task(
            task_id,
            status="succeeded",
            message="AI报价处理完成",
            progress=final_progress,
            payload=payload,
            error="",
            error_code="",
        )
        return
    except Exception:
        pass
    try:
        progress_state = {
            "latest": {
                "stage": "ai_pricing",
                "processed": 0,
                "total": total,
                "parallel_workers": parallel_workers,
                "mode": "parallel",
            },
        }
        progress_lock = Lock()
        payload_box: dict[str, dict] = {}
        error_box: dict[str, Exception] = {}

        def on_progress(progress: dict) -> None:
            with progress_lock:
                progress_state["latest"] = dict(progress or {})
            _update_quote_task_progress(task_id, progress)

        def run_enrich() -> None:
            try:
                payload_box["payload"] = get_demo_application()._enrich_quote_payload(
                    {
                        "dataset": "ai_route_refresh",
                        "model": model,
                        "items": items,
                    },
                    items_key="items",
                    scenario_source=scenario_source,
                    include_ai=True,
                    progress_callback=on_progress,
                )
            except Exception as exc:  # pragma: no cover - worker capture
                error_box["error"] = exc

        worker = Thread(target=run_enrich, daemon=True)
        worker.start()
        ai_stage_started_at = time()
        while worker.is_alive():
            worker.join(timeout=1.0)
            if not worker.is_alive():
                break
            with progress_lock:
                latest = dict(progress_state.get("latest") or {})
            if str(latest.get("stage") or "ai_pricing") != "ai_pricing":
                continue
            if int(latest.get("processed") or 0) > 0:
                continue
            elapsed_seconds = max(int(time() - ai_stage_started_at), 1)
            _update_quote_task_progress(
                task_id,
                _build_ai_route_waiting_progress(total, parallel_workers, elapsed_seconds),
            )

        if error_box.get("error") is not None:
            raise error_box["error"]
        payload = payload_box.get("payload") or {}
        payload = payload or {}
        payload.setdefault("model", {})
        payload["model"].setdefault("label", str(model.get("label") or model.get("bom_number") or "基准报价结果"))
        payload["model"].setdefault("item_count", total)
        current_task = _get_quote_task(task_id) or {}
        payload["analysis_log_text"] = str((current_task.get("progress") or {}).get("analysis_log_text") or "").strip()
        payload["exports"] = get_excel_quote_service().describe_quote_exports(payload)
        _update_quote_task_progress(task_id, {
            "stage": "finalizing",
            "processed": total,
            "total": total,
            "message": "正在汇总 AI 报价结果",
            "parallel_workers": parallel_workers,
            "mode": "parallel",
        })
        _update_quote_task(
            task_id,
            status="succeeded",
            message="AI报价处理完成",
            progress={
                **_normalize_quote_progress({
                "stage": "done",
                "processed": total,
                "total": total,
                "message": "AI报价处理完成",
                "parallel_workers": parallel_workers,
                "mode": "parallel",
                }),
                "analysis_log_text": _append_progress_log(
                    payload.get("analysis_log_text", ""),
                    {
                        "stage": "done",
                        "processed": total,
                        "total": total,
                        "message": "AI 报价处理完成",
                        "parallel_workers": parallel_workers,
                        "mode": "parallel",
                    },
                ),
            },
            payload=payload,
            error="",
            error_code="",
        )
    except ValueError as exc:
        failure_progress = {
            "stage": "finalizing",
            "processed": 0,
            "total": total,
            "message": f"AI 报价失败：{exc}",
            "hint": "请检查 BOM 数据、AI 接口状态或脚本规则后重试。",
            "parallel_workers": parallel_workers,
            "mode": "parallel",
        }
        current_task = _get_quote_task(task_id) or {}
        final_progress = _normalize_quote_progress(failure_progress)
        final_progress["analysis_log_text"] = _append_progress_log(
            str((current_task.get("progress") or {}).get("analysis_log_text") or "").strip(),
            failure_progress,
        )
        _update_quote_task(
            task_id,
            status="failed",
            message=str(exc),
            progress=final_progress,
            error=str(exc),
            error_code="AI_ROUTE_FAILED",
        )
    except Exception as exc:  # pragma: no cover - defensive
        failure_progress = {
            "stage": "finalizing",
            "processed": 0,
            "total": total,
            "message": f"AI 报价失败：{exc}",
            "hint": "AI 报价处理时发生异常，请稍后重试。",
            "parallel_workers": parallel_workers,
            "mode": "parallel",
        }
        current_task = _get_quote_task(task_id) or {}
        final_progress = _normalize_quote_progress(failure_progress)
        final_progress["analysis_log_text"] = _append_progress_log(
            str((current_task.get("progress") or {}).get("analysis_log_text") or "").strip(),
            failure_progress,
        )
        _update_quote_task(
            task_id,
            status="failed",
            message=str(exc),
            progress=final_progress,
            error=str(exc),
            error_code="AI_ROUTE_FAILED",
        )


@finance_demo_bp.route("/finance-demo", methods=["GET"])
@login_required
def finance_demo_redirect():
    return redirect("/finance-demo/")


@finance_demo_bp.route("/finance-demo/", methods=["GET"])
@login_required
def finance_demo_index():
    return render_template("finance_demo.html", finance_demo_markup=_finance_demo_markup())


@finance_demo_bp.route("/finance-demo/styles.css", methods=["GET"])
@login_required
def finance_demo_styles():
    return Response(_finance_demo_styles(), mimetype="text/css")


@finance_demo_bp.route("/finance-demo/<path:filename>", methods=["GET"])
@login_required
def finance_demo_static(filename: str):
    return send_from_directory(_static_dir(), filename)


@finance_demo_bp.route("/api/health", methods=["GET"])
def finance_demo_health():
    return _dispatch_api()


@finance_demo_bp.route("/api/demo-data", methods=["GET"])
@login_required
def finance_demo_data():
    return _dispatch_api()


@finance_demo_bp.route("/api/kingdee/status", methods=["GET"])
@login_required
def finance_demo_kingdee_status():
    return _dispatch_api()


@finance_demo_bp.route("/api/kingdee/materials", methods=["GET"])
@login_required
def finance_demo_kingdee_materials():
    return _dispatch_api()


@finance_demo_bp.route("/api/kingdee/bom-headers", methods=["GET"])
@login_required
def finance_demo_kingdee_bom_headers():
    return _dispatch_api()


@finance_demo_bp.route("/api/kingdee/bom", methods=["GET"])
@login_required
def finance_demo_kingdee_bom():
    return _dispatch_api()


@finance_demo_bp.route("/api/kingdee/purchase-orders", methods=["GET"])
@login_required
def finance_demo_kingdee_purchase_orders():
    return _dispatch_api()


@finance_demo_bp.route("/api/kingdee/sync", methods=["POST"])
@login_required
def finance_demo_kingdee_sync():
    return _dispatch_api()


@finance_demo_bp.route("/api/quote/excel", methods=["POST"])
@login_required
def finance_demo_quote_excel():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "FILE_REQUIRED", "message": "请先选择一个 Excel 文件"}), 400

    model_label = (request.form.get("model_label") or "").strip()
    production_mode = str(request.form.get("production_mode") or "sample").strip() or "sample"
    annual_volume = int(_coerce_progress_number(request.form.get("annual_volume"), 0))
    file_bytes = uploaded.read()
    try:
        archived_path = _archive_excel_upload(file_bytes, uploaded.filename)
    except ValueError as exc:
        return jsonify({"error": "INVALID_WORKBOOK", "message": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"error": "EXCEL_QUOTE_FAILED", "message": str(exc)}), 500

    task = _create_quote_task(uploaded.filename, model_label, archived_path)
    Thread(
        target=_run_quote_task,
        args=(task["task_id"], file_bytes, uploaded.filename, model_label, production_mode, annual_volume),
        daemon=True,
    ).start()
    return jsonify({
        "task_id": task["task_id"],
        "status": task["status"],
        "message": "报价任务已开始",
        "progress": task["progress"],
        "model": {
            "filename": uploaded.filename,
            "label": model_label,
            "production_mode": production_mode,
            "annual_volume": annual_volume,
            "archived_path": task["archived_path"],
            "archived_relative_path": task["archived_relative_path"],
        },
    }), 202


@finance_demo_bp.route("/api/quote/excel-paste", methods=["POST"])
@login_required
def finance_demo_quote_excel_paste():
    payload = request.get_json(silent=True) or {}
    table_text = str(payload.get("table_text") or payload.get("tableText") or "").strip()
    if not table_text:
        return jsonify({"error": "TABLE_TEXT_REQUIRED", "message": "请先粘贴表格数据"}), 400

    model_label = (payload.get("model_label") or "").strip()
    production_mode = str(payload.get("production_mode") or "sample").strip() or "sample"
    annual_volume = int(_coerce_progress_number(payload.get("annual_volume"), 0))
    filename = f"{model_label or '粘贴表格报价'}.xlsx"
    try:
        file_bytes, row_count = _build_pasted_workbook_bytes(table_text)
        archived_path = _archive_excel_upload(file_bytes, filename)
    except ValueError as exc:
        return jsonify({"error": "INVALID_TABLE_TEXT", "message": str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"error": "EXCEL_PASTE_FAILED", "message": str(exc)}), 500

    task = _create_quote_task(filename, model_label, archived_path)
    Thread(
        target=_run_quote_task,
        args=(task["task_id"], file_bytes, filename, model_label, production_mode, annual_volume),
        daemon=True,
    ).start()
    return jsonify({
        "task_id": task["task_id"],
        "status": task["status"],
        "message": "粘贴表格报价任务已开始",
        "progress": task["progress"],
        "model": {
            "filename": filename,
            "label": model_label,
            "production_mode": production_mode,
            "annual_volume": annual_volume,
            "row_count": row_count,
            "archived_path": task["archived_path"],
            "archived_relative_path": task["archived_relative_path"],
            "source_kind": "clipboard",
        },
    }), 202


@finance_demo_bp.route("/api/quote/excel/tasks/<task_id>", methods=["GET"])
@login_required
def finance_demo_quote_excel_task(task_id: str):
    task = _get_quote_task(task_id)
    if not task:
        return jsonify({"error": "TASK_NOT_FOUND", "message": "报价任务不存在或已过期"}), 404
    return jsonify(task), 200


@finance_demo_bp.route("/api/quote/ai-route", methods=["POST"])
@login_required
def finance_demo_quote_ai_route():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"error": "ITEMS_REQUIRED", "message": "请先加载 BOM 后再启动 AI 报价"}), 400

    model = payload.get("model") or {}
    scenario_source = str(payload.get("scenario_source") or "金蝶导入")
    task = _create_ai_route_task(model, len(items))
    Thread(
        target=_run_ai_route_task,
        args=(task["task_id"], items, model, scenario_source),
        daemon=True,
    ).start()
    return jsonify({
        "task_id": task["task_id"],
        "status": task["status"],
        "message": "AI 报价任务已开始",
        "progress": task["progress"],
        "model": model,
        "scenario_source": scenario_source,
    }), 202


@finance_demo_bp.route("/api/quote/ai-route/tasks/<task_id>", methods=["GET"])
@login_required
def finance_demo_quote_ai_route_task(task_id: str):
    task = _get_quote_task(task_id)
    if not task:
        return jsonify({"error": "TASK_NOT_FOUND", "message": "AI 报价任务不存在或已过期"}), 404
    return jsonify(task), 200


@finance_demo_bp.route("/api/quote/single-bom", methods=["POST"])
@login_required
def finance_demo_quote_single_bom():
    payload = request.get_json(silent=True) or {}
    item = payload.get("item") or payload
    if not isinstance(item, dict) or not (item.get("code") or item.get("name")):
        return jsonify({"error": "ITEM_REQUIRED", "message": "请先填写单物料 BOM 信息"}), 400

    model = payload.get("model") or {
        "label": "单物料试算",
        "production_mode": payload.get("production_mode"),
        "annual_volume": payload.get("annual_volume"),
    }
    result = get_finance_skill_quote_service().quote_items([item], model=model)
    return jsonify(result), 200


@finance_demo_bp.route("/api/quote/name-spec-bands", methods=["GET"])
@login_required
def finance_demo_get_name_spec_bands():
    service = get_finance_skill_quote_service()
    return jsonify(
        {
            "rows": service.get_name_spec_price_bands(),
            "config_path": str(service.name_spec_price_band_path),
        }
    ), 200


@finance_demo_bp.route("/api/quote/name-spec-bands", methods=["POST"])
@login_required
def finance_demo_save_name_spec_bands():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return jsonify({"error": "ROWS_REQUIRED", "message": "请提供可保存的价格区间配置"}), 400
    service = get_finance_skill_quote_service()
    saved = service.save_name_spec_price_bands(rows)
    return jsonify(
        {
            "ok": True,
            "rows": saved,
            "config_path": str(service.name_spec_price_band_path),
            "message": "名称型物料价格区间已保存",
        }
    ), 200


@finance_demo_bp.route("/api/quote/reproject-volume", methods=["POST"])
@login_required
def finance_demo_reproject_quote_volume():
    payload = request.get_json(silent=True) or {}
    quote_payload = payload.get("payload") or {}
    annual_volume = int(_coerce_progress_number(payload.get("annual_volume"), 0))
    requested_volume_label = str(payload.get("requested_volume_label") or "").strip()
    if not quote_payload.get("items"):
        return jsonify({"error": "ITEMS_REQUIRED", "message": "当前没有可重算的 AI 报价结果"}), 400
    if annual_volume <= 0:
        return jsonify({"error": "ANNUAL_VOLUME_REQUIRED", "message": "请提供有效的量产年产量"}), 400

    result = get_finance_skill_quote_service().reproject_mass_payload_for_volume(
        quote_payload,
        annual_volume=annual_volume,
        requested_volume_label=requested_volume_label or None,
    )
    return jsonify(result), 200


@finance_demo_bp.route("/api/quote/export", methods=["POST"])
@login_required
def finance_demo_export_quote():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    if not items:
        return jsonify({"error": "ITEMS_REQUIRED", "message": "当前没有可导出的报价结果"}), 400

    file_bytes = get_excel_quote_service().export_quote_workbook(payload)
    model = payload.get("model", {})
    filename = _build_quote_download_name(model, suffix="报价清单", extension=".xlsx")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
    }
    return Response(
        file_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@finance_demo_bp.route("/api/quote/export-package", methods=["POST"])
@login_required
def finance_demo_export_quote_package():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    if not items:
        return jsonify({"error": "ITEMS_REQUIRED", "message": "当前没有可下载的 AI 报价结果"}), 400

    file_bytes = get_excel_quote_service().export_quote_package(payload)
    model = payload.get("model", {})
    filename = _build_quote_download_name(model, suffix="报价汇总包", extension=".zip")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
    }
    return Response(
        file_bytes,
        mimetype="application/zip",
        headers=headers,
    )


@finance_demo_bp.route("/api/quote/export-package-batch", methods=["POST"])
@login_required
def finance_demo_export_quote_package_batch():
    payload = request.get_json(silent=True) or {}
    payloads = payload.get("payloads") or []
    valid_payloads = [item for item in payloads if isinstance(item, dict) and (item.get("items") or [])]
    if not valid_payloads:
        return jsonify({"error": "ITEMS_REQUIRED", "message": "当前没有可下载的 AI 报价结果"}), 400

    file_bytes = get_excel_quote_service().export_quote_package_batch(valid_payloads)
    primary_model = valid_payloads[-1].get("model", {})
    filename = _build_quote_download_name(primary_model, suffix="多量产报价汇总包", extension=".zip")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
    }
    return Response(
        file_bytes,
        mimetype="application/zip",
        headers=headers,
    )
