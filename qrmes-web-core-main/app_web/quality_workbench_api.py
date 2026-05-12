from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote

from flask import jsonify, request, send_file, session
from sqlalchemy import or_

from quality_workbench_service import (
    QualityWorkbenchProcessNotFoundError,
    QualityWorkbenchRecordNotFoundError,
    QualityWorkbenchService,
)


def register_quality_workbench_api_routes(app, deps: Dict[str, Any]) -> None:
    logger = deps["logger"]
    DataManager = deps["data_manager"]
    init_h2_service = deps["init_h2_service"]
    get_h2_db_manager = deps["get_h2_db_manager"]
    data_dir = Path(deps["data_dir"])
    login_required = deps.get("login_required")
    require_permission = deps.get("require_permission")
    user_service = deps.get("user_service")
    permission_service = deps.get("permission_service")

    try:
        from motor_qc.models import InspectionRecord
    except Exception:  # pragma: no cover
        InspectionRecord = None  # type: ignore

    try:
        from test_report_api import get_service as get_test_report_service
    except Exception:  # pragma: no cover
        get_test_report_service = None  # type: ignore

    quality_workbench_service: Optional[QualityWorkbenchService] = None

    def _photos_root() -> Path:
        configured = app.config.get("PHOTOS_DIR")
        return Path(configured) if configured else (data_dir / "picture")

    def _normalize_step_key(value: Any) -> str:
        if value is None:
            return ""
        normalized = str(value).strip().lower()
        normalized = re.sub(r"[\s_-]+", "", normalized)
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
        return normalized

    def _sanitize_folder_component(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = re.sub(r'[\\/*?:"<>|.]', "_", text)
        return text.strip().strip(".")

    def _folder_matches_name(folder_name: str, target_name: str) -> bool:
        folder = str(folder_name or "").strip()
        target = str(target_name or "").strip()
        if not target:
            return True
        if not folder:
            return False
        if folder == target:
            return True

        folder_prefix_first = folder.split("_", 1)[0] if "_" in folder else folder
        folder_prefix_last = folder.rsplit("_", 1)[0] if "_" in folder else folder

        folder_candidates = {
            folder,
            folder_prefix_first,
            folder_prefix_last,
        }
        target_candidates = {
            target,
            DataManager._normalize_project_name(target),
            _sanitize_folder_component(target),
        }

        folder_keys = {_normalize_step_key(item) for item in folder_candidates if item}
        target_keys = {_normalize_step_key(item) for item in target_candidates if item}
        if folder_keys.intersection(target_keys):
            return True

        sanitized_target = _sanitize_folder_component(target)
        if sanitized_target and folder.startswith(f"{sanitized_target}_"):
            return True
        if folder.startswith(f"{target}_"):
            return True
        return False

    def _extract_process_from_filename(file_name: str, product_serial: str) -> str:
        stem = Path(file_name).stem
        prefix = f"{product_serial}_"
        if not stem.startswith(prefix):
            return ""
        remainder = stem[len(prefix):]
        if "_" not in remainder:
            return remainder

        parts = remainder.split("_")
        if len(parts) >= 4 and parts[-1].isdigit() and parts[-2].isdigit() and parts[-3].isdigit():
            if len(parts[-3]) == 8 and len(parts[-2]) == 6:
                return "_".join(parts[:-3])
        if len(parts) >= 3 and parts[-1].isdigit() and parts[-2].isdigit():
            if len(parts[-2]) == 8 and len(parts[-1]) == 6:
                return "_".join(parts[:-2])
        if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) == 14:
            return "_".join(parts[:-1])
        return remainder.rsplit("_", 1)[0]

    def _collect_serial_photo_files(project_name: str, product_type: str, product_serial: str) -> List[Path]:
        photos_root = _photos_root()
        if not photos_root.exists():
            return []

        normalized_project = DataManager._normalize_project_name(project_name or "")
        normalized_type = (product_type or "").strip()
        files: List[Path] = []

        for project_dir in photos_root.iterdir():
            if not project_dir.is_dir():
                continue
            if normalized_project and not _folder_matches_name(project_dir.name, normalized_project):
                continue
            for product_dir in project_dir.iterdir():
                if not product_dir.is_dir():
                    continue
                if normalized_type and not _folder_matches_name(product_dir.name, normalized_type):
                    continue
                serial_dir = product_dir / product_serial
                if not serial_dir.exists() or not serial_dir.is_dir():
                    continue
                for pattern in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.gif"):
                    files.extend(serial_dir.glob(pattern))

        files.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0)
        logger.info(
            "[quality-workbench] photo scan project=%s type=%s serial=%s count=%s",
            project_name,
            product_type,
            product_serial,
            len(files),
        )
        return files

    def _normalize_qc_status(value: Any) -> Optional[str]:
        raw = str(value or "").strip().lower()
        if raw in ("pass", "fail", "ng"):
            return raw
        if raw in ("ok", "success", "passed"):
            return "pass"
        if raw in ("not_pass", "notpass", "failed", "reject"):
            return "fail"
        return None

    def _normalize_defect_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
            return [text]
        text = str(value).strip()
        return [text] if text else []

    def _build_qc_defect_payload(defects: List[str]) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        for defect in defects:
            payload.append(
                {
                    "type": "defect",
                    "severity": "major",
                    "description": str(defect),
                    "location": "",
                    "confidence": 0.7,
                }
            )
        return payload

    def _project_code_candidates(project_name: str) -> List[str]:
        candidates: List[str] = []
        seen = set()

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if not text or text in seen:
                return
            seen.add(text)
            candidates.append(text)

        add(project_name)
        config = DataManager.get_project_config(project_name) or {}
        add(config.get("projectName"))
        add(config.get("projectCode"))
        return candidates

    def _format_datetime(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        text = str(value).strip()
        return text

    def _build_quality_photo_items(process_photos: List[Path]) -> List[Dict[str, str]]:
        photos_root = _photos_root().resolve()
        items: List[Dict[str, str]] = []
        for photo_path in process_photos:
            try:
                safe_relative = photo_path.resolve().relative_to(photos_root).as_posix()
            except Exception:
                logger.warning("[quality-workbench] skip photo outside root: %s", photo_path)
                continue
            encoded = quote(safe_relative)
            url = f"/api/quality-workbench/photo?path={encoded}"
            items.append(
                {
                    "name": photo_path.name,
                    "url": url,
                    "thumbnail_url": url,
                    "relative_path": safe_relative,
                }
            )
        return items

    def _get_current_local_user():
        if not user_service:
            return None

        user_id = str(session.get("user_id") or "").strip()
        if user_id:
            try:
                user = user_service.get_user_by_id(user_id)
                if user:
                    return user
            except Exception:
                logger.debug('[quality-workbench] failed to load current user by id', exc_info=True)

        session_user = session.get("user") or {}
        mobile_user = getattr(request, "mobile_user", None) or {}
        username = str(
            session_user.get("username")
            or session_user.get("synology_username")
            or mobile_user.get("username")
            or ""
        ).strip()
        if not username:
            return None
        try:
            return user_service.get_user_by_synology_username(username)
        except Exception:
            logger.debug('[quality-workbench] failed to load current user by username', exc_info=True)
            return None

    def _can_delete_quality_photos() -> bool:
        if not permission_service:
            return False
        user = _get_current_local_user()
        if not user:
            return False
        try:
            from permission_service import Permission
            return permission_service.has_permission(user, Permission.WEB_QUALITY_PHOTO_DELETE)
        except Exception:
            logger.debug('[quality-workbench] failed to evaluate delete photo permission', exc_info=True)
            return False

    def _remove_process_photo_metadata(file_path: Path) -> None:
        repo = getattr(DataManager, 'process_photo_repo', None)
        if repo is None or not hasattr(repo, 'get_connection') or not hasattr(repo, '_find_existing_photo'):
            return
        try:
            with repo.get_connection() as conn:
                existing = repo._find_existing_photo(conn, str(file_path))
                if not existing:
                    return
                conn.execute('DELETE FROM process_photos WHERE id = ?', (int(existing['id']),))
                conn.commit()
        except Exception:
            logger.warning('[quality-workbench] failed to remove photo metadata for %s', file_path, exc_info=True)

    def _build_qc_report_payload(
        *,
        product_serial: str,
        project_name: str,
        product_type: str,
        steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        photo_files = _collect_serial_photo_files(project_name, product_type, product_serial)
        step_photo_map: Dict[str, int] = {}
        for photo_file in photo_files:
            step_name = _extract_process_from_filename(photo_file.name, product_serial)
            if not step_name:
                continue
            key = _normalize_step_key(step_name)
            step_photo_map[key] = step_photo_map.get(key, 0) + 1

        results: List[Dict[str, Any]] = []
        missing_processes: List[str] = []
        fail_count = 0
        ng_count = 0
        inspected_count = 0
        project_code_candidates = _project_code_candidates(project_name)

        for step in steps:
            step_name = str(step.get("name") or "").strip()
            key = _normalize_step_key(step_name)
            photo_count = int(step_photo_map.get(key, 0))
            has_photo = photo_count > 0
            required_photo = bool(step.get("photoRequired", True))

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
            latest_inspection_time = ""

            if InspectionRecord is not None and has_photo:
                try:
                    latest_record = (
                        InspectionRecord.query.filter(
                            InspectionRecord.project_code.in_(project_code_candidates),
                            InspectionRecord.process_step == step_name,
                            or_(
                                InspectionRecord.photo_path.like(f"%/{product_serial}/%"),
                                InspectionRecord.photo_path.like(f"%qc_{product_serial}_%"),
                            ),
                        )
                        .order_by(InspectionRecord.inspected_at.desc())
                        .first()
                    )
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
                latest_inspection_time = _format_datetime(getattr(latest_record, "inspected_at", None))

                if not effective_status:
                    effective_status = "fail" if defects_found else "pass"
            elif has_photo:
                effective_status = "ng"
                effective_summary = "已上传照片，待质检分析"

            if not has_photo and required_photo:
                missing_processes.append(step_name)

            if effective_status == "fail":
                fail_count += 1
            elif effective_status == "ng":
                ng_count += 1

            defects_payload = _build_qc_defect_payload(defects_found)
            ai_defects_payload = _build_qc_defect_payload(ai_defects)
            human_defects_payload = _build_qc_defect_payload(human_defects)

            results.append(
                {
                    "process": step_name,
                    "order": int(step.get("order") or 0),
                    "status": effective_status,
                    "effective_status": effective_status,
                    "confidence": 0.9 if effective_status == "pass" else (0.7 if effective_status == "fail" else 0.0),
                    "summary": effective_summary,
                    "effective_summary": effective_summary,
                    "has_photo": has_photo,
                    "photo_required": required_photo,
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
                    "latest_inspection_time": latest_inspection_time,
                    "latest_inspection_time_formatted": latest_inspection_time,
                    "detailAvailable": bool(step_name),
                }
            )

        if fail_count > 0:
            overall_status = "fail"
        elif missing_processes or ng_count > 0:
            overall_status = "ng"
        else:
            overall_status = "pass"

        return {
            "serial_number": product_serial,
            "overall_status": overall_status,
            "project_name": project_name,
            "product_type": product_type,
            "total_processes": len(steps),
            "inspected_processes": inspected_count,
            "missing_processes": missing_processes,
            "results": results,
        }

    def _build_process_detail_payload(
        *,
        product_serial: str,
        process_name: str,
        project_name: str,
        product_type: str,
        **_: Any,
    ) -> Dict[str, Any]:
        target_key = _normalize_step_key(process_name)
        step_files = [
            file_path
            for file_path in _collect_serial_photo_files(project_name, product_type, product_serial)
            if _normalize_step_key(_extract_process_from_filename(file_path.name, product_serial)) == target_key
        ]
        step_files.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
        photos = _build_quality_photo_items(step_files)
        return {
            "photoCount": len(step_files),
            "hasPhoto": len(step_files) > 0,
            "photos": photos,
        }

    def _get_service() -> QualityWorkbenchService:
        nonlocal quality_workbench_service
        if quality_workbench_service is None:
            test_report_service = None
            if callable(get_test_report_service):
                try:
                    test_report_service = get_test_report_service()
                except Exception as exc:  # pragma: no cover
                    logger.warning("[quality-workbench] test report service unavailable: %s", exc)

            quality_workbench_service = QualityWorkbenchService(
                data_manager=DataManager,
                init_h2_service=init_h2_service,
                get_h2_db_manager=get_h2_db_manager,
                qc_report_builder=_build_qc_report_payload,
                qc_process_detail_builder=_build_process_detail_payload,
                test_report_service=test_report_service,
            )
        return quality_workbench_service

    @app.route("/api/quality-workbench/shipment-stats", methods=["GET"])
    @login_required
    def api_quality_workbench_shipment_stats():
        target_date = str(request.args.get("date") or "").strip() or None
        trend_days = request.args.get("trendDays", default=7, type=int)
        limit = request.args.get("limit", default=80, type=int)
        try:
            payload = _get_service().get_daily_shipment_stats(
                target_date,
                trend_days=trend_days,
                limit=limit,
            )
            return jsonify({"success": True, **payload})
        except Exception as exc:
            logger.exception("[quality-workbench] shipment stats failed date=%s", target_date)
            return jsonify({"success": False, "error": f"出厂统计加载失败: {exc}"}), 500

    @app.route("/api/quality-workbench/<product_serial>", methods=["GET"])
    @login_required
    def api_quality_workbench(product_serial: str):
        serial = str(product_serial or "").strip()
        if not serial:
            return jsonify({"success": False, "error": "缺少产品序列号"}), 400

        try:
            payload = _get_service().get_quality_workbench(serial)
            return jsonify({"success": True, **payload})
        except QualityWorkbenchRecordNotFoundError:
            return jsonify({"success": False, "error": "未找到该序列号对应的质量工作台数据"}), 404
        except Exception as exc:
            logger.exception("[quality-workbench] load failed serial=%s", serial)
            return jsonify({"success": False, "error": f"质量工作台加载失败: {exc}"}), 500

    @app.route("/api/quality-workbench/<product_serial>/processes/<path:process_name>", methods=["GET"])
    @login_required
    def api_quality_workbench_process_detail(product_serial: str, process_name: str):
        serial = str(product_serial or "").strip()
        process_text = str(process_name or "").strip()
        if not serial or not process_text:
            return jsonify({"success": False, "error": "缺少工序详情查询参数"}), 400

        try:
            payload = _get_service().get_process_detail(serial, process_text)
            detail = payload.get("processDetail") if isinstance(payload, dict) else None
            if isinstance(detail, dict):
                detail["canDeletePhotos"] = _can_delete_quality_photos()
            return jsonify({"success": True, **payload})
        except QualityWorkbenchRecordNotFoundError:
            return jsonify({"success": False, "error": "未找到该序列号对应的质量工作台数据"}), 404
        except QualityWorkbenchProcessNotFoundError:
            return jsonify({"success": False, "error": "未找到该工序详情"}), 404
        except Exception as exc:
            logger.exception("[quality-workbench] detail failed serial=%s process=%s", serial, process_text)
            return jsonify({"success": False, "error": f"工序详情加载失败: {exc}"}), 500

    @app.route("/api/quality-workbench/photo", methods=["GET"])
    @login_required
    def api_quality_workbench_photo():
        relative_path = (request.args.get("path") or "").strip()
        if not relative_path:
            return jsonify({"success": False, "error": "缺少图片路径"}), 400

        photos_root = _photos_root().resolve()
        candidate = (photos_root / unquote(relative_path)).resolve()
        if photos_root not in candidate.parents and candidate != photos_root:
            return jsonify({"success": False, "error": "无权访问该图片"}), 403
        if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".gif"}:
            return jsonify({"success": False, "error": "仅支持图片文件"}), 400
        if not candidate.exists() or not candidate.is_file():
            return jsonify({"success": False, "error": "图片不存在"}), 404
        return send_file(str(candidate))


    @app.route("/api/quality-workbench/photo", methods=["DELETE"])
    @login_required
    @require_permission("web:quality_photo_delete")
    def api_quality_workbench_delete_photo():
        data = request.get_json(silent=True) or {}
        relative_path = str(data.get("path") or data.get("relativePath") or "").strip()
        if not relative_path:
            return jsonify({"success": False, "error": "缺少图片路径"}), 400

        photos_root = _photos_root().resolve()
        candidate = (photos_root / unquote(relative_path)).resolve()
        if photos_root not in candidate.parents and candidate != photos_root:
            return jsonify({"success": False, "error": "无权删除该图片"}), 403
        if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".gif"}:
            return jsonify({"success": False, "error": "仅支持删除图片文件"}), 400
        if not candidate.exists() or not candidate.is_file():
            return jsonify({"success": False, "error": "图片不存在"}), 404

        try:
            from photo_api import _remove_photo_index_entry, get_thumbnail_path

            thumbnail_path = get_thumbnail_path(candidate)
            candidate.unlink()
            if thumbnail_path.exists() and thumbnail_path.is_file():
                thumbnail_path.unlink()
            _remove_process_photo_metadata(candidate)
            _remove_photo_index_entry([candidate, thumbnail_path])
            logger.info('[quality-workbench] deleted photo path=%s', candidate)
            return jsonify({
                "success": True,
                "message": "照片删除成功",
                "deleted": {
                    "name": candidate.name,
                    "relativePath": relative_path,
                },
            })
        except Exception as exc:
            logger.exception('[quality-workbench] delete photo failed path=%s', candidate)
            return jsonify({"success": False, "error": f"删除照片失败: {exc}"}), 500
