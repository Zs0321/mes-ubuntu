"""QC runtime routes (check/analyze/confirm/report)."""

from __future__ import annotations

import base64
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import jsonify, request, session
from sqlalchemy import or_


def register_qc_runtime_routes(app, deps: Dict[str, Any]) -> None:
    """Register runtime QC routes."""
    login_required = deps["login_required"]
    logger = deps["logger"]
    motor_qc_db = deps["motor_qc_db"]
    init_h2_service = deps["init_h2_service"]
    get_h2_db_manager = deps["get_h2_db_manager"]

    _get_qc_policy_from_project = deps["get_qc_policy_from_project"]
    _resolve_project_identity = deps["resolve_project_identity"]
    _normalize_qc_vision_mode = deps["normalize_qc_vision_mode"]
    _normalize_dual_primary = deps["normalize_dual_primary"]
    _normalize_openai_base_url = deps["normalize_openai_base_url"]
    _resolve_qwen_base_url = deps["resolve_qwen_base_url"]
    _resolve_qwen_api_key = deps["resolve_qwen_api_key"]
    _resolve_secondary_qwen_base_url = deps["resolve_secondary_qwen_base_url"]
    _resolve_secondary_qwen_api_key = deps["resolve_secondary_qwen_api_key"]
    _resolve_local_qwen_base_url = deps["resolve_local_qwen_base_url"]
    _resolve_local_qwen_api_key = deps["resolve_local_qwen_api_key"]

    _get_project_process_steps = deps["get_project_process_steps"]
    _collect_serial_photo_files = deps["collect_serial_photo_files"]
    _normalize_step_key = deps["normalize_step_key"]
    _extract_process_from_filename = deps["extract_process_from_filename"]
    _normalize_qc_status = deps["normalize_qc_status"]
    _normalize_defect_list = deps["normalize_defect_list"]
    _build_qc_defect_payload = deps["build_qc_defect_payload"]

    def _api_qc_check_previous_impl(product_serial: str):
        process_index = request.args.get('processIndex', type=int) or request.args.get('currentProcessIndex', type=int)
        project_name = (request.args.get('projectName') or '').strip()
        product_type = (request.args.get('productType') or '').strip()

        if not process_index or not project_name:
            return jsonify({
                "success": False,
                "error": "缺少必要参数 processIndex/projectName"
            }), 400

        steps = _get_project_process_steps(project_name, product_type)
        previous_steps = [
            s for s in steps
            if int(s.get('order') or 0) < process_index and bool(s.get('photoRequired', True))
        ]
        photo_files = _collect_serial_photo_files(project_name, product_type, product_serial)

        photo_step_counts: Dict[str, int] = {}
        for photo_file in photo_files:
            process_name = _extract_process_from_filename(photo_file.name, product_serial)
            if process_name:
                key = _normalize_step_key(process_name)
                photo_step_counts[key] = photo_step_counts.get(key, 0) + 1

        step_statuses = []
        missing = []
        for step in previous_steps:
            step_name = step.get('name', '')
            key = _normalize_step_key(step_name)
            count = photo_step_counts.get(key, 0)
            has_photo = count > 0
            if not has_photo:
                missing.append(step_name)
            step_statuses.append({
                "process_name": step_name,
                "order": int(step.get('order') or 0),
                "has_photo": has_photo,
                "photo_count": count,
                "qc_status": None,
            })

        return jsonify({
            "success": True,
            "current_process_index": process_index,
            "previous_steps": step_statuses,
            "all_passed": len(missing) == 0,
            "missing_photos": missing,
            "failed_steps": [],
            "ng_steps": [],
        })

    @app.route('/api/qc/check-previous/<product_serial>', methods=['GET'])
    @login_required
    def api_qc_check_previous(product_serial: str):
        product_serial = (product_serial or '').strip()
        if not product_serial:
            return jsonify({"success": False, "error": "缺少产品序列号"}), 400
        return _api_qc_check_previous_impl(product_serial)

    @app.route('/api/qc/check-previous', methods=['GET'])
    @login_required
    def api_qc_check_previous_legacy():
        product_serial = (
            request.args.get('serialNumber')
            or request.args.get('productSerial')
            or request.args.get('serial')
            or ''
        ).strip()
        if not product_serial:
            return jsonify({"success": False, "error": "缺少产品序列号 serialNumber"}), 400
        return _api_qc_check_previous_impl(product_serial)

    @app.route('/api/qc/analyze', methods=['POST'])
    @login_required
    def api_qc_analyze():
        data = request.get_json() or {}
        raw_project_name = str(data.get('project_name') or '').strip()
        raw_project_code = str(data.get('projectCode') or data.get('project_code') or '').strip()
        project_name, resolved_project_code = _resolve_project_identity(raw_project_name, raw_project_code)
        process_name = (data.get('process_name') or '').strip()
        product_serial = (data.get('product_serial') or '').strip()
        product_type = (data.get('product_type') or '').strip()
        process_context = data.get('process_context')
        if not isinstance(process_context, dict):
            process_context = {}
        source_text = str(data.get("source") or "").strip()
        upload_mode_text = str(data.get("upload_mode") or data.get("uploadMode") or "").strip()
        station_id_text = str(data.get("station_id") or data.get("stationId") or "").strip()
        if source_text and not process_context.get("source"):
            process_context["source"] = source_text
        if upload_mode_text and not process_context.get("upload_mode"):
            process_context["upload_mode"] = upload_mode_text
        if station_id_text and not (process_context.get("station_id") or process_context.get("stationId")):
            process_context["station_id"] = station_id_text
        pre_prompt = str(
            data.get('pre_prompt')
            or data.get('prompt_override')
            or ''
        ).strip()
        photo_base64_list = data.get('photo_base64') or []

        if not project_name or not process_name or not isinstance(photo_base64_list, list) or not photo_base64_list:
            return jsonify({
                "success": False,
                "status": "ng",
                "summary": "缺少必要参数 project_name/process_name/photo_base64",
                "error": "bad_request"
            }), 400

        if (not raw_project_name) and raw_project_code and project_name != raw_project_code:
            logger.info(
                "[qc-analyze] projectCode 已映射项目名 code=%s -> name=%s",
                raw_project_code,
                project_name,
            )
        elif raw_project_code and resolved_project_code and project_name == raw_project_code:
            logger.info("[qc-analyze] 使用 projectCode 作为项目标识 code=%s", raw_project_code)

        policy = _get_qc_policy_from_project(project_name)
        if not policy.get("qc_enabled") or not policy.get("realtime_qc_enabled"):
            return jsonify({
                "success": False,
                "status": "ng",
                "confidence": 0.0,
                "summary": "QC 未启用或未开启实时质检",
                "findings": [],
                "checklist": {},
                "error": "qc_disabled",
            })

        temp_files: List[Path] = []
        analysis_results: List[Dict[str, Any]] = []
        all_defects: List[str] = []

        try:
            from motor_qc.services.inspection_service import InspectionService
            from motor_qc.models import InspectionRecord

            service = InspectionService()
            requested_mode = _normalize_qc_vision_mode(
                data.get("vision_mode") or data.get("visionMode") or policy.get("vision_mode"),
                default="online",
            )
            requested_model = str(
                data.get("vision_model")
                or data.get("visionModel")
                or data.get("online_model")
                or data.get("onlineModel")
                or policy.get("vision_model")
                or ""
            ).strip()
            requested_local_model = str(
                data.get("local_vision_model")
                or data.get("localVisionModel")
                or data.get("local_model")
                or data.get("localModel")
                or policy.get("local_vision_model")
                or ""
            ).strip()
            requested_secondary_online_model = str(
                data.get("secondary_online_model")
                or data.get("secondaryOnlineModel")
                or data.get("secondary_model")
                or data.get("secondaryModel")
                or policy.get("secondary_online_model")
                or ""
            ).strip()
            requested_secondary_online_base_url = _normalize_openai_base_url(
                data.get("secondary_online_base_url")
                or data.get("secondaryOnlineBaseUrl")
                or data.get("secondary_base_url")
                or data.get("secondaryBaseUrl")
                or policy.get("secondary_online_base_url")
                or _resolve_secondary_qwen_base_url()
                or _resolve_qwen_base_url(),
                _resolve_qwen_base_url(),
            )
            requested_secondary_online_api_key = str(
                data.get("secondary_online_api_key")
                or data.get("secondaryOnlineApiKey")
                or data.get("secondary_api_key")
                or data.get("secondaryApiKey")
                or policy.get("secondary_online_api_key")
                or _resolve_secondary_qwen_api_key()
                or ""
            ).strip()
            requested_online_base_url = _resolve_qwen_base_url()
            requested_online_api_key = str(_resolve_qwen_api_key() or "").strip()
            requested_local_base_url = _normalize_openai_base_url(
                data.get("local_vision_base_url")
                or data.get("localVisionBaseUrl")
                or data.get("local_base_url")
                or data.get("localBaseUrl")
                or policy.get("local_vision_base_url")
                or _resolve_local_qwen_base_url(),
                _resolve_local_qwen_base_url(),
            )
            requested_dual_primary = _normalize_dual_primary(
                data.get("dual_primary") or data.get("dualPrimary") or policy.get("dual_primary"),
                default="online",
            )
            requested_local_api_key = str(
                data.get("local_vision_api_key")
                or data.get("localVisionApiKey")
                or data.get("local_api_key")
                or data.get("localApiKey")
                or _resolve_local_qwen_api_key()
                or ""
            ).strip()
            if requested_mode in ("local", "dual") and not requested_local_model:
                return jsonify({
                    "success": False,
                    "status": "ng",
                    "confidence": 0.0,
                    "summary": "当前识别模式需要 local_vision_model",
                    "findings": [],
                    "checklist": {},
                    "error": "local_model_missing",
                }), 400
            if requested_mode == "dual_online" and not requested_secondary_online_model:
                return jsonify({
                    "success": False,
                    "status": "ng",
                    "confidence": 0.0,
                    "summary": "当前双在线识别模式需要 secondary_online_model",
                    "findings": [],
                    "checklist": {},
                    "error": "secondary_online_model_missing",
                }), 400
            if requested_mode == "dual_online" and not requested_secondary_online_api_key:
                return jsonify({
                    "success": False,
                    "status": "ng",
                    "confidence": 0.0,
                    "summary": "当前双在线识别模式需要第二在线模型 API Key",
                    "findings": [],
                    "checklist": {},
                    "error": "secondary_online_api_key_missing",
                }), 400
            inspector_id = session.get("username") or getattr(getattr(request, 'mobile_user', None), 'get', lambda *_: None)('username') or "mobile"
            record_updates: List[Dict[str, Any]] = []

            step_photo_paths: List[Path] = []
            try:
                serial_photos = _collect_serial_photo_files(project_name, product_type, product_serial)
                target_step_key = _normalize_step_key(process_name)
                for photo_file in serial_photos:
                    parsed_step = _extract_process_from_filename(photo_file.name, product_serial)
                    if _normalize_step_key(parsed_step or '') == target_step_key:
                        step_photo_paths.append(photo_file)
                step_photo_paths.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
            except Exception as ex:
                logger.warning("[QC分析] 预加载工序照片路径失败: %s", ex)

            safe_serial_token = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", str(product_serial or "").strip()).strip("-") or "unknown"
            safe_process_token = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", str(process_name or "").strip()).strip("-") or "process"
            while "__" in safe_serial_token:
                safe_serial_token = safe_serial_token.replace("__", "-")
            while "__" in safe_process_token:
                safe_process_token = safe_process_token.replace("__", "-")
            decoded_jobs: List[Dict[str, Any]] = []
            for idx, photo_base64 in enumerate(photo_base64_list):
                if not isinstance(photo_base64, str) or not photo_base64.strip():
                    continue

                raw_bytes = base64.b64decode(photo_base64, validate=False)
                with tempfile.NamedTemporaryFile(
                    prefix=f"qc__{safe_serial_token}__{safe_process_token}__{idx}_",
                    suffix=".jpg",
                    delete=False,
                ) as fp:
                    fp.write(raw_bytes)
                    temp_path = Path(fp.name)
                    temp_files.append(temp_path)

                if idx < len(step_photo_paths):
                    persisted_path = str(step_photo_paths[idx])
                else:
                    persisted_path = f"/qc-temp/{project_name}/{product_serial}/{process_name}/photo_{idx + 1}.jpg"

                decoded_jobs.append({
                    "position": len(decoded_jobs),
                    "index": idx,
                    "temp_path": temp_path,
                    "persisted_path": persisted_path,
                })

            if not decoded_jobs:
                return jsonify({
                    "success": False,
                    "status": "ng",
                    "confidence": 0.0,
                    "summary": "鏈敹鍒版湁鏁堢収鐗囨暟鎹?",
                    "findings": [],
                    "checklist": {},
                    "error": "no_valid_photo",
                })

            split_dual_online = requested_mode == "dual_online" and len(decoded_jobs) > 1

            def _resolve_dual_online_assignment(position: int) -> Dict[str, str]:
                use_secondary = bool(position % 2)
                if use_secondary:
                    return {
                        "provider": "qwen_secondary",
                        "label": "secondary_online",
                        "model": requested_secondary_online_model or "qwen3.5-plus",
                        "base_url": requested_secondary_online_base_url,
                        "api_key": requested_secondary_online_api_key,
                    }
                return {
                    "provider": "qwen",
                    "label": "online",
                    "model": requested_model,
                    "base_url": requested_online_base_url,
                    "api_key": requested_online_api_key,
                }

            def _resolve_single_dual_online_assignment() -> Dict[str, str]:
                if requested_dual_primary == "secondary_online":
                    return {
                        "provider": "qwen_secondary",
                        "label": "secondary_online",
                        "model": requested_secondary_online_model or "qwen3.5-plus",
                        "base_url": requested_secondary_online_base_url,
                        "api_key": requested_secondary_online_api_key,
                    }
                return {
                    "provider": "qwen",
                    "label": "online",
                    "model": requested_model,
                    "base_url": requested_online_base_url,
                    "api_key": requested_online_api_key,
                }

            def _run_photo_job(job: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
                assignment: Optional[Dict[str, str]] = None
                inspection_kwargs: Dict[str, Any] = {
                    "project_code": project_name,
                    "process_step": process_name,
                    "photo_path": str(job["temp_path"]),
                    "inspector_id": inspector_id,
                    "serial_number": product_serial,
                    "product_type": product_type,
                    "prompt_override": pre_prompt,
                    "process_context": process_context,
                    "vision_model": requested_model,
                    "vision_mode": requested_mode,
                    "secondary_online_model": requested_secondary_online_model,
                    "secondary_online_base_url": requested_secondary_online_base_url,
                    "secondary_online_api_key": requested_secondary_online_api_key,
                    "local_vision_model": requested_local_model,
                    "local_vision_base_url": requested_local_base_url,
                    "local_vision_api_key": requested_local_api_key,
                    "dual_primary": requested_dual_primary,
                }
                if requested_mode == "dual_online":
                    assignment = _resolve_dual_online_assignment(job["position"]) if split_dual_online else _resolve_single_dual_online_assignment()
                    inspection_kwargs.update({
                        "online_provider": assignment["provider"],
                        "online_vision_base_url": assignment["base_url"],
                        "online_vision_api_key": assignment["api_key"],
                        "vision_model": assignment["model"],
                    })
                if split_dual_online:
                    inspection_kwargs["persist"] = False

                result = service.perform_inspection(**inspection_kwargs)
                if assignment:
                    result["mode"] = requested_mode
                    result["assignment"] = assignment["label"]
                    result["distribution_strategy"] = "photo_split" if split_dual_online else "single_provider"
                return job, result

            if split_dual_online:
                future_map = {}
                ordered_results_raw: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = []
                with ThreadPoolExecutor(max_workers=min(2, len(decoded_jobs))) as executor:
                    for job in decoded_jobs:
                        future = executor.submit(_run_photo_job, job)
                        future_map[future] = job["position"]
                    for future in as_completed(future_map):
                        job, result = future.result()
                        ordered_results_raw.append((future_map[future], job, result))
                ordered_results_raw.sort(key=lambda item: item[0])
                ordered_results = [(job, result) for _, job, result in ordered_results_raw]
            else:
                ordered_results = [_run_photo_job(job) for job in decoded_jobs]

            pending_records: List[Dict[str, Any]] = []
            for job, result in ordered_results:
                analysis_results.append(result)
                result_status = _normalize_qc_status(result.get("status")) or "pass"
                result_summary = str(result.get("analysis") or "").strip()
                defects = _normalize_defect_list(result.get("defects"))

                if split_dual_online:
                    pending_records.append({
                        "job": job,
                        "result": result,
                        "status": result_status,
                        "summary": result_summary,
                        "defects": defects,
                    })
                else:
                    record_id_raw = result.get("record_id")
                    try:
                        record_id = int(record_id_raw) if record_id_raw is not None else 0
                    except (TypeError, ValueError):
                        record_id = 0
                    if record_id > 0:
                        record_updates.append({
                            "record_id": record_id,
                            "photo_path": job["persisted_path"],
                            "ai_status": result_status,
                            "ai_summary": result_summary,
                            "ai_defects": defects,
                        })

                all_defects.extend(defects)

            if split_dual_online and pending_records:
                try:
                    for item in pending_records:
                        record = InspectionRecord(
                            project_code=project_name,
                            process_step=process_name,
                            photo_path=item["job"]["persisted_path"],
                            inspector_id=inspector_id,
                            inspection_result=item["summary"],
                            defects_found=item["defects"],
                            status=item["status"],
                            inspected_at=datetime.utcnow(),
                        )
                        record.ai_status = item["status"]
                        record.ai_summary = item["summary"]
                        record.ai_defects = item["defects"]
                        motor_qc_db.session.add(record)
                        motor_qc_db.session.flush()
                        item["result"]["record_id"] = record.id
                    motor_qc_db.session.commit()
                except Exception as ex:
                    motor_qc_db.session.rollback()
                    logger.error("[QC鍒嗘瀽] 鍙屽湪绾垮垎娴?InspectionRecord 淇濆瓨澶辫触: %s", ex, exc_info=True)

            if record_updates:
                try:
                    for item in record_updates:
                        record = InspectionRecord.query.get(item["record_id"])
                        if record is not None:
                            record.photo_path = item["photo_path"]
                            record.ai_status = item["ai_status"]
                            record.ai_summary = item["ai_summary"]
                            record.ai_defects = item["ai_defects"]
                            record.status = item["ai_status"]
                            record.inspection_result = item["ai_summary"]
                            record.defects_found = item["ai_defects"]
                    motor_qc_db.session.commit()
                except Exception as ex:
                    motor_qc_db.session.rollback()
                    logger.error("[QC分析] 修正 InspectionRecord.photo_path 失败: %s", ex, exc_info=True)

            if not analysis_results:
                return jsonify({
                    "success": False,
                    "status": "ng",
                    "confidence": 0.0,
                    "summary": "未收到有效照片数据",
                    "findings": [],
                    "checklist": {},
                    "error": "no_valid_photo",
                })

            findings = [{
                "type": "defect",
                "severity": "major",
                "description": defect,
                "location": "",
                "confidence": 0.7,
            } for defect in all_defects]

            statuses: List[str] = []
            confidences: List[float] = []
            detail_lines: List[str] = []
            analysis_details: List[Dict[str, Any]] = []
            compare_total = 0
            compare_status_match = 0
            compare_defect_overlap_sum = 0.0
            for idx, item in enumerate(analysis_results):
                raw_status = str(item.get("status") or "").strip().lower()
                analysis = str(item.get("analysis") or "").strip()
                defects = item.get("defects") or []
                if not isinstance(defects, list):
                    defects = []

                if raw_status not in ("pass", "fail", "ng"):
                    raw_status = "fail" if defects else "pass"

                try:
                    conf = float(item.get("confidence", 0.0))
                except (TypeError, ValueError):
                    conf = 0.0

                statuses.append(raw_status)
                confidences.append(conf)
                if analysis:
                    detail_lines.append(f"图{idx + 1}（{raw_status}）：{analysis}")
                elif defects:
                    detail_lines.append(f"图{idx + 1}（{raw_status}）：发现 {len(defects)} 个问题")
                else:
                    detail_lines.append(f"图{idx + 1}（{raw_status}）：无详细分析文本")

                analysis_details.append({
                    "index": idx + 1,
                    "status": raw_status,
                    "confidence": conf,
                    "analysis": analysis,
                    "defects": [str(x) for x in defects if x],
                    "mode": str(item.get("mode") or requested_mode),
                    "provider": str(item.get("provider") or ""),
                    "model": str(item.get("model") or ""),
                    "assignment": str(item.get("assignment") or ""),
                    "distribution_strategy": str(item.get("distribution_strategy") or ""),
                    "model_outputs": item.get("model_outputs") if isinstance(item.get("model_outputs"), dict) else {},
                    "comparison": item.get("comparison") if isinstance(item.get("comparison"), dict) else {},
                })

                comparison = item.get("comparison")
                if isinstance(comparison, dict):
                    compare_total += 1
                    if bool(comparison.get("status_match")):
                        compare_status_match += 1
                    try:
                        compare_defect_overlap_sum += float(comparison.get("defect_overlap", 0.0))
                    except (TypeError, ValueError):
                        pass

            if "fail" in statuses:
                status = "fail"
            elif "ng" in statuses:
                status = "ng"
            else:
                status = "pass"

            if status == "fail":
                confidence = min(confidences) if confidences else 0.7
            elif status == "ng":
                confidence = 0.0
            else:
                confidence = min(confidences) if confidences else 0.9

            if findings:
                summary = f"发现 {len(findings)} 个问题"
                if detail_lines:
                    summary += "；" + "；".join(detail_lines[:3])
                    if len(detail_lines) > 3:
                        summary += f"；另有 {len(detail_lines) - 3} 张照片结果"
            else:
                summary = "；".join(detail_lines[:4]) if detail_lines else ("QC 检查通过" if status == "pass" else "需要人工复核")

            def _context_list(value) -> List[str]:
                if isinstance(value, list):
                    rows = value
                else:
                    rows = re.split(r"[,，;；\n]+", str(value or ""))
                return [str(item).strip() for item in rows if str(item).strip()]

            def _extract_screw_progress(text: str, fallback_target: int) -> Tuple[Optional[int], Optional[int]]:
                joined = str(text or "")
                matched = re.search(r"螺钉[^0-9]{0,8}(\d{1,3})\s*[/|]\s*目标[^0-9]{0,6}(\d{1,3})", joined, flags=re.I)
                if matched:
                    return int(matched.group(1)), int(matched.group(2))
                matched = re.search(r"螺钉[^0-9]{0,8}(\d{1,3})\s*[/|]\s*(\d{1,3})", joined, flags=re.I)
                if matched:
                    return int(matched.group(1)), int(matched.group(2))
                actual_match = re.search(r"螺钉[^0-9]{0,8}(\d{1,3})", joined, flags=re.I)
                target_match = re.search(r"目标[^0-9]{0,6}(\d{1,3})", joined, flags=re.I)
                actual = int(actual_match.group(1)) if actual_match else None
                if target_match:
                    return actual, int(target_match.group(1))
                return actual, (int(fallback_target) if fallback_target > 0 else None)

            text_rows: List[str] = []
            if summary:
                text_rows.append(summary)
            for row in analysis_details:
                text_rows.append(str(row.get("analysis") or ""))
                for defect in (row.get("defects") or []):
                    text_rows.append(str(defect))
            joined_text = " | ".join([str(item).strip() for item in text_rows if str(item).strip()])

            checklist_results: List[Dict[str, Any]] = []
            expected_screw_count = 0
            try:
                expected_screw_count = int(process_context.get("expected_screw_count") or 0)
            except (TypeError, ValueError):
                expected_screw_count = 0
            actual_screw, target_screw = _extract_screw_progress(joined_text, expected_screw_count)
            if expected_screw_count > 0 or actual_screw is not None:
                target = int(target_screw or expected_screw_count or 0)
                screw_status = "pending"
                if actual_screw is not None and target > 0:
                    screw_status = "pass" if int(actual_screw) >= target else "fail"
                checklist_results.append({
                    "key": "screw_count",
                    "label": "螺钉数量",
                    "status": screw_status,
                    "current": "" if actual_screw is None else int(actual_screw),
                    "target": target if target > 0 else "",
                    "detail": f"目标 {target} 个" if target > 0 else "",
                })

            special_processes = _context_list(process_context.get("special_processes"))
            extra_focus = _context_list(process_context.get("extra_focus"))
            glue_required = any(re.search(r"点胶|涂胶|上胶|胶路|胶线", item) for item in (special_processes + extra_focus))
            if glue_required:
                has_glue_text = bool(re.search(r"点胶|涂胶|上胶|胶路|胶线", joined_text))
                has_glue_fail = bool(re.search(r"未点胶|漏胶|断胶|胶路不连续|胶线中断|点胶不足|胶量不足|胶路异常|点胶异常", joined_text))
                has_glue_pass = bool(re.search(r"点胶完成|点胶到位|胶路连续|胶线连续|胶量均匀|点胶合格|胶路合格", joined_text))
                glue_done_status = "pending"
                glue_quality_status = "pending"
                if has_glue_fail:
                    glue_done_status = "fail"
                    glue_quality_status = "fail"
                elif has_glue_pass:
                    glue_done_status = "pass"
                    glue_quality_status = "pass"
                elif has_glue_text and status == "pass":
                    glue_done_status = "pass"
                    glue_quality_status = "pass"

                checklist_results.append({
                    "key": "glue_done",
                    "label": "点胶完成",
                    "status": glue_done_status,
                    "current": "已完成" if glue_done_status == "pass" else ("未完成/异常" if glue_done_status == "fail" else "待确认"),
                    "target": "",
                    "detail": "",
                })
                checklist_results.append({
                    "key": "glue_quality",
                    "label": "点胶效果",
                    "status": glue_quality_status,
                    "current": "合格" if glue_quality_status == "pass" else ("异常" if glue_quality_status == "fail" else "待确认"),
                    "target": "",
                    "detail": "检测到漏胶/断胶/不连续风险" if has_glue_fail else "",
                })

            checklist_payload = {
                "targets": {
                    "expected_screw_count": expected_screw_count if expected_screw_count > 0 else 0,
                    "special_processes": special_processes,
                    "special_parts": _context_list(process_context.get("special_parts")),
                    "extra_focus": extra_focus,
                },
                "results": checklist_results,
            }
            legacy_checklist: Dict[str, bool] = {}
            for row in checklist_results:
                key = str(row.get("key") or "").strip()
                if not key:
                    continue
                status_text = str(row.get("status") or "").strip().lower()
                if status_text in ("pass", "ok", "done", "completed", "true", "yes", "1"):
                    legacy_checklist[key] = True
                elif status_text in ("fail", "ng", "error", "false", "no", "0", "missing", "incomplete"):
                    legacy_checklist[key] = False

            comparison_summary: Dict[str, Any] = {
                "enabled": requested_mode == "dual",
                "total": compare_total,
                "status_match_count": compare_status_match,
                "status_match_rate": round(compare_status_match / compare_total, 4) if compare_total > 0 else None,
                "avg_defect_overlap": round(compare_defect_overlap_sum / compare_total, 4) if compare_total > 0 else None,
            }

            return jsonify({
                "success": True,
                "status": status,
                "confidence": confidence,
                "summary": summary,
                "findings": findings,
                "analysis_details": analysis_details,
                "model_execution": {
                    "mode": requested_mode,
                    "strategy": "photo_split" if split_dual_online else ("single_provider" if requested_mode == "dual_online" else "default"),
                    "dual_primary": requested_dual_primary,
                    "online_model": requested_model,
                    "secondary_online_model": requested_secondary_online_model,
                    "local_model": requested_local_model,
                    "local_base_url": requested_local_base_url,
                },
                "comparison_summary": comparison_summary,
                "checklist": legacy_checklist,
                "checklist_detail": checklist_payload,
                "error": None,
            })
        except Exception as e:
            logger.error(f"[QC分析] 异常: {e}", exc_info=True)
            return jsonify({
                "success": False,
                "status": "ng",
                "confidence": 0.0,
                "summary": f"QC 分析异常: {str(e)}",
                "findings": [],
                "checklist": {},
                "error": str(e),
            }), 500
        finally:
            for f in temp_files:
                try:
                    if f.exists():
                        f.unlink()
                except OSError:
                    pass

    @app.route('/api/qc/confirm', methods=['POST'])
    @login_required
    def api_qc_confirm():
        data = request.get_json() or {}
        project_name = (data.get('project_name') or '').strip()
        process_name = (data.get('process_name') or '').strip()
        product_serial = (data.get('product_serial') or '').strip()
        product_type = (data.get('product_type') or '').strip()
        human_status = str(data.get('human_status') or '').strip().lower()
        human_summary = str(data.get('human_summary') or '').strip()

        if not project_name or not process_name or not product_serial:
            return jsonify({
                "success": False,
                "error": "缺少必要参数 project_name/process_name/product_serial"
            }), 400
        if human_status not in ("pass", "fail", "ng"):
            return jsonify({
                "success": False,
                "error": "human_status 仅支持 pass/fail/ng"
            }), 400

        try:
            from motor_qc.models import InspectionRecord
        except Exception as e:
            logger.error(f"[QC确认] 导入模型失败: {e}", exc_info=True)
            return jsonify({
                "success": False,
                "error": "QC 模块不可用"
            }), 500

        try:
            photo_files = _collect_serial_photo_files(project_name, product_type, product_serial)
            target_key = _normalize_step_key(process_name)
            step_files: List[Path] = []
            for file_path in photo_files:
                step_from_name = _extract_process_from_filename(file_path.name, product_serial)
                if _normalize_step_key(step_from_name or '') == target_key:
                    step_files.append(file_path)

            latest_photo_path = None
            if step_files:
                step_files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
                latest_photo_path = str(step_files[0])

            latest_record = InspectionRecord.query.filter(
                InspectionRecord.project_code == project_name,
                InspectionRecord.process_step == process_name,
                or_(
                    InspectionRecord.photo_path.like(f"%/{product_serial}/%"),
                    InspectionRecord.photo_path.like(f"%qc_{product_serial}_%"),
                )
            ).order_by(InspectionRecord.inspected_at.desc()).first()

            if not latest_photo_path and latest_record is None:
                return jsonify({
                    "success": False,
                    "error": "未找到该工序照片，无法提交人工确认"
                }), 404

            inspector_id = (
                session.get("username")
                or session.get("user_id")
                or "mobile"
            )
            final_summary = human_summary or ("人工确认通过" if human_status == "pass" else "人工确认不通过")
            defects = [] if human_status == "pass" else [human_summary or "人工复核判定不通过"]

            record = latest_record
            if record is None:
                record = InspectionRecord(
                    project_code=project_name,
                    process_step=process_name,
                    photo_path=latest_photo_path or "",
                    inspector_id=inspector_id,
                )
                motor_qc_db.session.add(record)
            else:
                if latest_photo_path:
                    record.photo_path = latest_photo_path
                record.inspector_id = inspector_id

            if not record.ai_status:
                record.ai_status = _normalize_qc_status(record.status)
            if not (record.ai_summary or "").strip():
                record.ai_summary = str(record.inspection_result or "").strip()
            if not _normalize_defect_list(record.ai_defects):
                record.ai_defects = _normalize_defect_list(record.defects_found)

            record.human_status = human_status
            record.human_summary = final_summary
            record.human_defects = defects
            record.human_confirmed_by = inspector_id
            record.human_confirmed_at = datetime.utcnow()

            record.status = human_status
            record.defects_found = defects
            record.inspection_result = final_summary
            record.inspected_at = record.human_confirmed_at

            motor_qc_db.session.commit()
            return jsonify({
                "success": True,
                "message": "人工确认已保存",
                "data": {
                    "effective_status": human_status,
                    "effective_summary": final_summary,
                    "ai_status": record.ai_status,
                    "ai_summary": record.ai_summary,
                    "human_status": record.human_status,
                    "human_summary": record.human_summary,
                }
            })
        except Exception as e:
            motor_qc_db.session.rollback()
            logger.error(f"[QC确认] 保存失败: {e}", exc_info=True)
            return jsonify({
                "success": False,
                "error": f"保存失败: {str(e)}"
            }), 500

    @app.route('/api/qc/report/<product_serial>', methods=['GET'])
    @login_required
    def api_qc_report(product_serial: str):
        h2_db_manager = get_h2_db_manager()
        if not h2_db_manager:
            init_h2_service()
            h2_db_manager = get_h2_db_manager()

        h2_record = h2_db_manager.get_record(product_serial) if h2_db_manager else None
        project_name = ((h2_record or {}).get('project_name') or request.args.get('projectName') or '').strip()
        product_type = ((h2_record or {}).get('product_type') or request.args.get('productType') or '').strip()

        if not project_name:
            return jsonify({
                "success": False,
                "error": "未找到该序列号对应的项目配置"
            }), 404

        steps = _get_project_process_steps(project_name, product_type)
        if not steps:
            return jsonify({
                "success": False,
                "error": "该项目暂无可用工序配置"
            }), 404

        photo_files = _collect_serial_photo_files(project_name, product_type, product_serial)
        step_photo_map: Dict[str, int] = {}
        for photo_file in photo_files:
            step_name = _extract_process_from_filename(photo_file.name, product_serial)
            if not step_name:
                continue
            key = _normalize_step_key(step_name)
            step_photo_map[key] = step_photo_map.get(key, 0) + 1

        try:
            from motor_qc.models import InspectionRecord
        except Exception:
            InspectionRecord = None

        results = []
        missing_processes = []
        pass_count = 0
        fail_count = 0
        ng_count = 0
        inspected_count = 0

        for step in steps:
            step_name = step.get('name', '')
            key = _normalize_step_key(step_name)
            photo_count = int(step_photo_map.get(key, 0))
            has_photo = photo_count > 0
            required_photo = bool(step.get('photoRequired', True))

            if has_photo:
                inspected_count += 1

            latest_record = None
            ai_status: Optional[str] = None
            ai_summary = ""
            ai_defects: List[str] = []
            human_status: Optional[str] = None
            human_summary = ""
            human_defects: List[str] = []
            effective_status: Optional[str] = None
            effective_summary = ""
            defects_found: List[str] = []

            if InspectionRecord is not None and has_photo:
                try:
                    latest_record = InspectionRecord.query.filter(
                        InspectionRecord.project_code == project_name,
                        InspectionRecord.process_step == step_name,
                        or_(
                            InspectionRecord.photo_path.like(f"%/{product_serial}/%"),
                            InspectionRecord.photo_path.like(f"%qc_{product_serial}_%"),
                        )
                    ).order_by(InspectionRecord.inspected_at.desc()).first()
                except Exception:
                    latest_record = None

            if latest_record is not None:
                legacy_status = _normalize_qc_status(latest_record.status)
                legacy_summary = str(latest_record.inspection_result or "").strip()
                legacy_defects = _normalize_defect_list(latest_record.defects_found)

                ai_status = _normalize_qc_status(getattr(latest_record, "ai_status", None))
                ai_summary = str(getattr(latest_record, "ai_summary", None) or "").strip()
                ai_defects = _normalize_defect_list(getattr(latest_record, "ai_defects", None))

                human_status = _normalize_qc_status(getattr(latest_record, "human_status", None))
                human_summary = str(getattr(latest_record, "human_summary", None) or "").strip()
                human_defects = _normalize_defect_list(getattr(latest_record, "human_defects", None))

                if not ai_status and not human_status:
                    ai_status = legacy_status
                if not ai_summary and not human_summary and legacy_summary:
                    ai_summary = legacy_summary
                if not ai_defects and not human_defects and legacy_defects:
                    ai_defects = legacy_defects

                effective_status = human_status or ai_status or legacy_status
                defects_found = human_defects if human_status else (ai_defects or legacy_defects)
                if effective_status == "pass":
                    defects_found = []
                effective_summary = human_summary or ai_summary or legacy_summary

                if not effective_status:
                    effective_status = "fail" if defects_found else "pass"
            elif has_photo:
                effective_status = "ng"
                effective_summary = "已上传照片，待质检分析"

            if not has_photo and required_photo:
                missing_processes.append(step_name)

            if effective_status == "pass":
                pass_count += 1
            elif effective_status == "fail":
                fail_count += 1
            elif effective_status == "ng":
                ng_count += 1

            defects_payload = _build_qc_defect_payload(defects_found)
            ai_defects_payload = _build_qc_defect_payload(ai_defects)
            human_defects_payload = _build_qc_defect_payload(human_defects)

            results.append({
                "process": step_name,
                "order": int(step.get('order') or 0),
                "status": effective_status,
                "effective_status": effective_status,
                "confidence": 0.9 if effective_status == "pass" else (0.7 if effective_status == "fail" else 0.0),
                "summary": effective_summary,
                "effective_summary": effective_summary,
                "has_photo": has_photo,
                "photo_count": photo_count,
                "defect_count": len(defects_payload),
                "defects": defects_payload,
                "ai_status": ai_status,
                "ai_summary": ai_summary,
                "ai_defect_count": len(ai_defects_payload),
                "ai_defects": ai_defects_payload,
                "human_status": human_status,
                "human_summary": human_summary,
                "human_defect_count": len(human_defects_payload),
                "human_defects": human_defects_payload,
            })

        if fail_count > 0:
            overall_status = "fail"
        elif missing_processes or ng_count > 0:
            overall_status = "ng"
        else:
            overall_status = "pass"

        return jsonify({
            "success": True,
            "serial_number": product_serial,
            "overall_status": overall_status,
            "project_name": project_name,
            "product_type": product_type,
            "total_processes": len(steps),
            "inspected_processes": inspected_count,
            "missing_processes": missing_processes,
            "results": results,
        })
