"""AI usage summary API routes."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import jsonify, request

try:
    from qrmes_shared_core.config import config as runtime_config
except Exception:  # pragma: no cover
    runtime_config = None


def register_ai_usage_api_routes(app, deps: Dict[str, Any]) -> None:
    """Register AI usage related routes."""
    require_permission = deps["require_permission"]
    logger = deps["logger"]
    system_logs_db_path = deps["system_logs_db_path"]

    @app.route('/api/logs/ai-usage', methods=['GET'])
    @require_permission('web:view_logs')
    def api_get_ai_usage_summary():
        """AI token usage summary and cost estimation."""
        try:
            import system_logs_db
            system_logs_db.ensure_system_logs_db(system_logs_db_path)

            def _safe_float(v: Optional[str], default: float) -> float:
                try:
                    return float(v)
                except Exception:
                    return default

            def _safe_int(v: Any, default: int = 0) -> int:
                try:
                    return int(v)
                except Exception:
                    return default

            def _to_ms(date_str: str, end_of_day: bool = False) -> Optional[int]:
                if not date_str:
                    return None
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if end_of_day:
                        return int((dt.timestamp() + 24 * 3600 - 1) * 1000)
                    return int(dt.timestamp() * 1000)
                except Exception:
                    return None

            date_from = (request.args.get("dateFrom") or "").strip()
            date_to = (request.args.get("dateTo") or "").strip()
            provider_filter = (request.args.get("provider") or "").strip().lower()
            model_filter = (request.args.get("model") or "").strip().lower()
            limit = _safe_int(request.args.get("limit"), 2000)
            limit = max(1, min(limit, 20000))

            input_price = _safe_float(
                request.args.get("inputPricePer1k"),
                _safe_float(
                    os.getenv("AI_INPUT_PRICE_PER_1K_USD")
                    or (runtime_config.get("ai_input_price_per_1k_usd", "") if runtime_config else "")
                    or os.getenv("QWEN_INPUT_PRICE_PER_1K_USD")
                    or (runtime_config.get("qwen_input_price_per_1k_usd", "") if runtime_config else "")
                    or "0.008",
                    0.008,
                ),
            )
            output_price = _safe_float(
                request.args.get("outputPricePer1k"),
                _safe_float(
                    os.getenv("AI_OUTPUT_PRICE_PER_1K_USD")
                    or (runtime_config.get("ai_output_price_per_1k_usd", "") if runtime_config else "")
                    or os.getenv("QWEN_OUTPUT_PRICE_PER_1K_USD")
                    or (runtime_config.get("qwen_output_price_per_1k_usd", "") if runtime_config else "")
                    or "0.024",
                    0.024,
                ),
            )

            from_ts = _to_ms(date_from, end_of_day=False)
            to_ts = _to_ms(date_to, end_of_day=True)

            where_sql = ["action = ?"]
            sql_args: List[Any] = ["AI_VISION_USAGE"]
            if from_ts is not None:
                where_sql.append("ts >= ?")
                sql_args.append(from_ts)
            if to_ts is not None:
                where_sql.append("ts <= ?")
                sql_args.append(to_ts)

            sql = (
                "SELECT ts, details_json "
                "FROM system_logs "
                f"WHERE {' AND '.join(where_sql)} "
                "ORDER BY ts DESC, id DESC"
            )

            conn = sqlite3.connect(str(system_logs_db_path), timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA busy_timeout=2000;")
                rows = [dict(r) for r in conn.execute(sql, sql_args).fetchall()]
            finally:
                conn.close()

            usage_items: List[Dict[str, Any]] = []
            total_calls = 0
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_tokens_all = 0
            total_cost_usd = 0.0

            for row in rows:
                details_raw = row.get("details_json")
                details: Dict[str, Any] = {}
                if isinstance(details_raw, str) and details_raw:
                    try:
                        details = json.loads(details_raw)
                    except Exception:
                        details = {}
                elif isinstance(details_raw, dict):
                    details = details_raw

                provider = str(details.get("provider") or "").strip().lower()
                model = str(details.get("model") or "").strip().lower()

                if provider_filter and provider != provider_filter:
                    continue
                if model_filter and model_filter not in model:
                    continue

                prompt_tokens = _safe_int(details.get("prompt_tokens"))
                if prompt_tokens <= 0:
                    prompt_tokens = _safe_int(details.get("input_tokens"))
                completion_tokens = _safe_int(details.get("completion_tokens"))
                if completion_tokens <= 0:
                    completion_tokens = _safe_int(details.get("output_tokens"))
                row_total_tokens = _safe_int(details.get("total_tokens"))
                if row_total_tokens <= 0:
                    row_total_tokens = max(0, prompt_tokens + completion_tokens)

                cost_usd = (prompt_tokens / 1000.0) * input_price + (completion_tokens / 1000.0) * output_price
                total_calls += 1
                total_prompt_tokens += prompt_tokens
                total_completion_tokens += completion_tokens
                total_tokens_all += row_total_tokens
                total_cost_usd += cost_usd

                if len(usage_items) >= limit:
                    continue
                item = {
                    "ts": _safe_int(row.get("ts")),
                    "timestamp": datetime.fromtimestamp(_safe_int(row.get("ts")) / 1000).isoformat() if row.get("ts") else "",
                    "provider": provider or "unknown",
                    "model": details.get("model") or "",
                    "serial_number": details.get("serial_number") or "",
                    "process_step": details.get("process_step") or "",
                    "image_name": details.get("image_name") or "",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": row_total_tokens,
                    "latency_ms": _safe_int(details.get("latency_ms")),
                    "image_size_bytes": _safe_int(details.get("image_size_bytes")),
                    "success": bool(details.get("success", True)),
                    "error_message": details.get("error_message") or "",
                    "cost_usd": round(cost_usd, 8),
                }
                usage_items.append(item)

            avg_tokens_per_photo = (total_tokens_all / total_calls) if total_calls else 0.0
            avg_cost_per_photo = (total_cost_usd / total_calls) if total_calls else 0.0
            estimated_cost_100 = avg_cost_per_photo * 100.0

            item_rows = usage_items[:200]
            return jsonify({
                "success": True,
                "summary": {
                    "photos_analyzed": total_calls,
                    "total_prompt_tokens": total_prompt_tokens,
                    "total_completion_tokens": total_completion_tokens,
                    "total_tokens": total_tokens_all,
                    "total_cost_usd": round(total_cost_usd, 6),
                    "avg_tokens_per_photo": round(avg_tokens_per_photo, 2),
                    "avg_cost_per_photo_usd": round(avg_cost_per_photo, 6),
                    "estimated_cost_100_photos_usd": round(estimated_cost_100, 6),
                    "input_price_per_1k_usd": input_price,
                    "output_price_per_1k_usd": output_price,
                },
                "filters": {
                    "date_from": date_from,
                    "date_to": date_to,
                    "provider": provider_filter,
                    "model": model_filter,
                    "limit": limit,
                },
                "items": item_rows,
                "items_total": total_calls,
                "items_returned": len(item_rows),
                "items_truncated": total_calls > len(item_rows),
                "message": (
                    "当前筛选范围内暂无AI token日志，请先执行质检生成数据。"
                    if not total_calls
                    else ("明细列表已截断显示前 200 条，汇总统计为全量结果。" if len(usage_items) > len(item_rows) else "")
                ),
            })
        except Exception as e:
            logger.error(f"[AI用量] 获取统计失败: {e}")
            return jsonify({"success": False, "message": f"获取AI用量失败: {str(e)}"}), 500

