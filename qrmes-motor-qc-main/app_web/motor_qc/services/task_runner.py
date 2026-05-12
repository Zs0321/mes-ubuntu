import logging
import inspect
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set

from flask import current_app

from ..models import db, QCProcessTask, QCTaskPhoto, QCTaskDetailItem
from .inspection_service import InspectionService
from .task_service import QCTaskService, normalize_detail_key

logger = logging.getLogger(__name__)

_runner_lock = threading.Lock()
_runner_instance = None

_SCREW_TERMS = (
    "螺钉",
    "螺丝",
    "螺栓",
    "螺母",
    "紧固件",
    "扭矩",
)

_SCREW_CATEGORY_KEYWORDS = {
    "missing": ("漏装", "未安装", "没安装", "少装", "缺装", "缺少", "缺失"),
    "wrong": ("错装", "装错", "装反", "规格错误", "型号错误", "位置错误", "孔位错误"),
    "not_seated": ("未拧紧", "未到位", "松动", "未锁紧", "未紧固", "扭矩不足", "浮高", "压紧不足"),
}

_SCREW_CATEGORY_LABELS = {
    "missing": "螺钉漏装",
    "wrong": "螺钉错装",
    "not_seated": "螺钉未到位/未拧紧",
}


class QCTaskRunner:
    def __init__(
        self,
        worker_id: str = "qc-runner",
        poll_interval: float = 2.0,
        inspection_service=None,
        flask_app=None,
    ):
        self.worker_id = worker_id
        self.poll_interval = poll_interval
        self.task_service = QCTaskService()
        self.inspection_service = inspection_service or InspectionService()
        self.flask_app = flask_app
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_forever, name=f"{self.worker_id}-thread", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def run_forever(self):
        if self.flask_app is not None:
            with self.flask_app.app_context():
                self._run_forever_loop()
            return
        self._run_forever_loop()

    def _run_forever_loop(self):
        logger.info("[QCTaskRunner] started worker=%s", self.worker_id)
        while not self._stop_event.is_set():
            try:
                processed = self.process_next_pending()
                if not processed:
                    time.sleep(self.poll_interval)
            except Exception as exc:
                logger.error("[QCTaskRunner] loop error: %s", exc, exc_info=True)
                time.sleep(self.poll_interval)
        logger.info("[QCTaskRunner] stopped worker=%s", self.worker_id)

    def claim_next_task(self) -> Optional[QCProcessTask]:
        candidate = (
            db.session.query(QCProcessTask)
            .filter(QCProcessTask.status == "pending")
            .order_by(QCProcessTask.updated_at.asc(), QCProcessTask.id.asc())
            .first()
        )
        if not candidate:
            return None

        updated = (
            db.session.query(QCProcessTask)
            .filter(QCProcessTask.id == candidate.id, QCProcessTask.status == "pending")
            .update(
                {
                    QCProcessTask.status: "running",
                    QCProcessTask.claimed_by: self.worker_id,
                    QCProcessTask.claimed_at: datetime.utcnow(),
                    QCProcessTask.attempt_count: (candidate.attempt_count or 0) + 1,
                    QCProcessTask.updated_at: datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            db.session.rollback()
            return None

        db.session.commit()
        return db.session.query(QCProcessTask).filter_by(id=candidate.id).first()

    def requeue_stale_running_tasks(self, stale_minutes: int = 20) -> int:
        """回收长时间卡在 running 的任务，避免队列永久堵塞。"""
        cutoff = datetime.utcnow() - timedelta(minutes=max(1, int(stale_minutes)))
        updated = (
            db.session.query(QCProcessTask)
            .filter(QCProcessTask.status == "running")
            .filter(QCProcessTask.claimed_at.isnot(None))
            .filter(QCProcessTask.claimed_at < cutoff)
            .update(
                {
                    QCProcessTask.status: "pending",
                    QCProcessTask.claimed_by: None,
                    QCProcessTask.claimed_at: None,
                    QCProcessTask.error_message: "任务超时回收，已重新入队",
                    QCProcessTask.updated_at: datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )
        if updated:
            db.session.commit()
            logger.warning("[QCTaskRunner] requeued stale running tasks=%s cutoff=%s", updated, cutoff.isoformat())
            return int(updated)
        db.session.rollback()
        return 0

    def process_next_pending(self) -> bool:
        self.requeue_stale_running_tasks(stale_minutes=20)
        task = self.claim_next_task()
        if not task:
            return False
        self.process_task(task.id)
        return True

    def process_task(self, task_id: int) -> Optional[QCProcessTask]:
        task = db.session.query(QCProcessTask).filter_by(id=task_id).first()
        if not task:
            return None

        try:
            photos = (
                db.session.query(QCTaskPhoto)
                .filter(QCTaskPhoto.task_id == task.id)
                .order_by(QCTaskPhoto.captured_at.asc(), QCTaskPhoto.id.asc())
                .all()
            )
            if not photos:
                task.status = "failed"
                task.error_message = "任务无可分析照片"
                task.updated_at = datetime.utcnow()
                db.session.commit()
                return task

            configured_sub_checks = self._load_process_sub_checks(task)
            detail_rows: List[Dict[str, Any]] = []
            analysis_errors: List[str] = []
            for photo in photos:
                if photo.analyzed_at:
                    analysis_json = photo.analysis_json or {}
                else:
                    try:
                        analysis_json = self._invoke_inspection_service(task, photo.photo_path)
                    except Exception as exc:
                        err_text = str(exc).strip() or exc.__class__.__name__
                        analysis_errors.append(f"{photo.photo_path}: {err_text}")
                        logger.warning(
                            "[QCTaskRunner] photo analyze fallback task_id=%s photo_id=%s error=%s",
                            task.id,
                            photo.id,
                            err_text,
                        )
                        analysis_json = {
                            "status": "ng",
                            "defects": [],
                            "analysis": f"识别失败，已回退人工复核: {err_text}",
                            "confidence": 0.0,
                        }
                    photo.analysis_json = analysis_json or {}
                    photo.analyzed_at = datetime.utcnow()
                if not isinstance(analysis_json, dict):
                    analysis_json = {
                        "status": "ng",
                        "defects": [],
                        "analysis": str(analysis_json),
                        "confidence": 0.0,
                    }
                    photo.analysis_json = analysis_json

                detail_rows.extend(self._extract_detail_rows(task, photo, analysis_json, configured_sub_checks))

            merged = self.task_service.aggregate_detail_results(detail_rows)
            self._persist_detail_items(task.id, merged)
            task.best_result_json = self._build_task_result_summary(merged)
            task.status = "review"
            if analysis_errors:
                task.error_message = f"部分照片识别失败（{len(analysis_errors)} 张），已回退人工复核"
            else:
                task.error_message = None
            task.last_analyzed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            db.session.commit()
            return task
        except Exception as exc:
            db.session.rollback()
            failed_task = db.session.query(QCProcessTask).filter_by(id=task_id).first()
            if failed_task:
                failed_task.status = "failed"
                failed_task.error_message = str(exc)
                failed_task.updated_at = datetime.utcnow()
                db.session.commit()
            logger.error("[QCTaskRunner] process task failed id=%s err=%s", task_id, exc, exc_info=True)
            return failed_task

    @staticmethod
    def _build_inspection_kwargs(task: QCProcessTask, photo_path: str, inspector_id: str) -> Dict[str, Any]:
        return {
            "project_code": task.project_id,
            "process_step": task.process_name,
            "photo_path": photo_path,
            "inspector_id": inspector_id,
            "product_type": task.product_type or "",
            # 由任务事务统一提交，避免识别结果和任务明细出现分裂落库。
            "persist": False,
        }

    @staticmethod
    def _filter_callable_kwargs(func: Any, call_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return dict(call_kwargs)

        params = signature.parameters
        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()):
            return dict(call_kwargs)
        return {key: value for key, value in call_kwargs.items() if key in params}

    def _invoke_inspection_service(self, task: QCProcessTask, photo_path: str) -> Dict[str, Any]:
        inspect_callable = getattr(self.inspection_service, "perform_inspection", None)
        if not callable(inspect_callable):
            raise RuntimeError("inspection_service 缺少 perform_inspection 方法")

        call_kwargs = self._build_inspection_kwargs(task, photo_path, self.worker_id)
        compatible_kwargs = self._filter_callable_kwargs(inspect_callable, call_kwargs)
        return inspect_callable(**compatible_kwargs)

    @staticmethod
    def _normalize_match_text(value: str) -> str:
        text = str(value or "").strip().lower()
        text = "".join(ch for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")
        return text

    @staticmethod
    def _contains_any_keyword(text: str, keywords: Any) -> bool:
        if not text:
            return False
        return any(k for k in keywords if k and str(k) in text)

    def _classify_screw_issue_categories(self, *texts: str) -> List[str]:
        joined = " | ".join(str(item or "").lower() for item in texts if str(item or "").strip())
        if not joined:
            return []
        has_screw_context = self._contains_any_keyword(joined, _SCREW_TERMS)
        matched: List[str] = []
        for category, keywords in _SCREW_CATEGORY_KEYWORDS.items():
            if self._contains_any_keyword(joined, keywords):
                if has_screw_context or category in ("missing", "wrong", "not_seated"):
                    matched.append(category)
        return matched

    def _append_screw_detail_rows(
        self,
        rows: List[Dict[str, Any]],
        photo: QCTaskPhoto,
        categories: List[str],
        reason: str,
        seen: Set[str],
    ) -> None:
        for category in categories:
            if category in seen:
                continue
            seen.add(category)
            rows.append(
                {
                    "detail_key": normalize_detail_key(f"screw_{category}"),
                    "detail_label": _SCREW_CATEGORY_LABELS.get(category) or f"螺钉-{category}",
                    "status": "fail",
                    "photo_id": photo.id,
                    "source": "ai",
                    "reason": reason or "",
                }
            )

    def _normalize_sub_checks(self, raw_sub_checks: Any) -> List[Dict[str, Any]]:
        rows: List[Any]
        if raw_sub_checks is None:
            rows = []
        elif isinstance(raw_sub_checks, list):
            rows = raw_sub_checks
        else:
            rows = [raw_sub_checks]

        normalized: List[Dict[str, Any]] = []
        seen = set()
        for row in rows:
            if isinstance(row, str):
                name = row.strip()
                key = normalize_detail_key(name)
                aliases: List[str] = []
                required = True
            elif isinstance(row, dict):
                name = str(
                    row.get("name")
                    or row.get("label")
                    or row.get("detailLabel")
                    or row.get("detail_label")
                    or row.get("key")
                    or ""
                ).strip()
                key = str(row.get("key") or "").strip() or normalize_detail_key(name)
                aliases_raw = row.get("aliases")
                if isinstance(aliases_raw, str):
                    aliases = [item.strip() for item in aliases_raw.split(",") if item.strip()]
                elif isinstance(aliases_raw, list):
                    aliases = [str(item).strip() for item in aliases_raw if str(item).strip()]
                else:
                    aliases = []
                required = bool(row.get("required", True))
            else:
                name = str(row or "").strip()
                key = normalize_detail_key(name)
                aliases = []
                required = True

            if not name:
                continue
            if not key:
                key = normalize_detail_key(name)
            if not key or key in seen:
                continue
            seen.add(key)
            normalized.append({
                "key": key,
                "name": name,
                "aliases": aliases,
                "required": required,
            })
        return normalized

    def _load_process_sub_checks(self, task: QCProcessTask) -> List[Dict[str, Any]]:
        getter = getattr(self.inspection_service, "get_process_step_config", None)
        if not callable(getter):
            return []

        step_config = getter(
            task.project_id,
            task.process_name,
            task.product_type or "",
        ) or {}
        raw_sub_checks = step_config.get("subChecks")
        if not raw_sub_checks:
            rules = step_config.get("rules") if isinstance(step_config, dict) else {}
            if isinstance(rules, dict):
                raw_sub_checks = rules.get("check_items")
        return self._normalize_sub_checks(raw_sub_checks)

    def _infer_sub_check_status(
        self,
        sub_check: Dict[str, Any],
        process_status: str,
        defects: List[Any],
        process_reason: str,
    ) -> Dict[str, str]:
        label = str(sub_check.get("name") or "").strip()
        alias_rows = sub_check.get("aliases") or []
        token_candidates = [label] + [str(item).strip() for item in alias_rows if str(item).strip()]
        tokens = [self._normalize_match_text(item) for item in token_candidates if self._normalize_match_text(item)]
        tokens = [item for item in tokens if len(item) >= 2]

        defect_texts: List[str] = []
        defect_reasons: List[str] = []
        for defect in defects:
            if isinstance(defect, str):
                text = defect.strip()
                if text:
                    defect_texts.append(text)
                    defect_reasons.append(text)
            elif isinstance(defect, dict):
                text = str(defect.get("type") or defect.get("description") or "").strip()
                reason = str(
                    defect.get("description")
                    or defect.get("detail")
                    or defect.get("reason")
                    or text
                ).strip()
                if text:
                    defect_texts.append(text)
                if reason:
                    defect_reasons.append(reason)

        normalized_defect_texts = [self._normalize_match_text(item) for item in defect_texts if item]
        normalized_reason = self._normalize_match_text(process_reason)

        for idx, defect_text in enumerate(normalized_defect_texts):
            if any(token and token in defect_text for token in tokens):
                return {
                    "status": "fail",
                    "reason": defect_reasons[idx] if idx < len(defect_reasons) else process_reason,
                }

        if process_status in ("fail", "ng") and tokens and any(token and token in normalized_reason for token in tokens):
            return {
                "status": "fail",
                "reason": process_reason,
            }

        if process_status == "pass" and not defects:
            return {
                "status": "pass",
                "reason": process_reason,
            }

        return {
            "status": "pending",
            "reason": "",
        }

    def _extract_detail_rows(
        self,
        task: QCProcessTask,
        photo: QCTaskPhoto,
        analysis_json: Dict[str, Any],
        configured_sub_checks: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        defects = analysis_json.get("defects") or []
        if not isinstance(defects, list):
            defects = []
        screw_categories_seen: Set[str] = set()

        status = str(analysis_json.get("status") or "").strip().lower()
        if status not in ("pass", "fail", "ng"):
            status = "fail" if defects else "pass"
        process_reason = str(analysis_json.get("analysis") or analysis_json.get("summary") or "").strip()

        # 工序整体结论（默认配置项）
        overall_key = normalize_detail_key("overall")
        rows.append(
            {
                "detail_key": overall_key,
                "detail_label": "工序整体",
                "status": status,
                "photo_id": photo.id,
                "source": "config",
                "reason": process_reason,
            }
        )

        # 子项模板（配置项）：优先使用 subChecks，没有配置时保持旧行为
        for sub_check in (configured_sub_checks or []):
            inferred = self._infer_sub_check_status(sub_check, status, defects, process_reason)
            detail_key = normalize_detail_key(sub_check.get("key") or sub_check.get("name") or "")
            if not detail_key:
                continue
            rows.append(
                {
                    "detail_key": detail_key,
                    "detail_label": str(sub_check.get("name") or detail_key),
                    "status": inferred.get("status") or "pending",
                    "photo_id": photo.id,
                    "source": "config",
                    "reason": inferred.get("reason") or "",
                }
            )

        # AI补充缺陷细节
        for defect in defects:
            if isinstance(defect, str):
                label = defect.strip()
            elif isinstance(defect, dict):
                label = str(defect.get("type") or defect.get("description") or "").strip()
            else:
                label = ""

            if not label:
                continue
            detail_key = normalize_detail_key(label)
            if not detail_key:
                continue
            defect_reason = process_reason
            if isinstance(defect, dict):
                defect_reason = str(
                    defect.get("description")
                    or defect.get("detail")
                    or defect.get("reason")
                    or process_reason
                ).strip()
            rows.append(
                {
                    "detail_key": detail_key,
                    "detail_label": label,
                    "status": "fail",
                    "photo_id": photo.id,
                    "source": "ai",
                    "reason": defect_reason,
                }
            )

            screw_categories = self._classify_screw_issue_categories(label, defect_reason, process_reason)
            self._append_screw_detail_rows(rows, photo, screw_categories, defect_reason or process_reason, screw_categories_seen)

        if process_reason:
            extra_categories = self._classify_screw_issue_categories(process_reason)
            self._append_screw_detail_rows(rows, photo, extra_categories, process_reason, screw_categories_seen)
        return rows

    def _persist_detail_items(self, task_id: int, merged: Dict[str, Dict[str, Any]]):
        existing_items = (
            db.session.query(QCTaskDetailItem)
            .filter(QCTaskDetailItem.task_id == task_id)
            .all()
        )
        item_by_key = {item.detail_key: item for item in existing_items}

        for detail_key, payload in merged.items():
            item = item_by_key.get(detail_key)
            if not item:
                item = QCTaskDetailItem(
                    task_id=task_id,
                    detail_key=detail_key,
                    detail_label=payload.get("detail_label") or detail_key,
                    source=payload.get("source") or "ai",
                    best_status=payload.get("best_status") or "pending",
                    best_photo_id=payload.get("best_photo_id"),
                )
                db.session.add(item)
                continue

            item.detail_label = payload.get("detail_label") or item.detail_label
            item.source = payload.get("source") or item.source
            item.best_status = payload.get("best_status") or item.best_status
            item.best_photo_id = payload.get("best_photo_id")
            item.updated_at = datetime.utcnow()

    def _build_task_result_summary(self, merged: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        details = list(merged.values())
        total = len(details)
        passed = sum(1 for d in details if (d.get("best_status") or "").lower() == "pass")
        failed = sum(1 for d in details if (d.get("best_status") or "").lower() in ("fail", "ng"))
        pending = max(total - passed - failed, 0)
        overall_status = "pass" if failed == 0 and pending == 0 and total > 0 else ("fail" if failed > 0 else "pending")
        failed_labels = []
        reason_texts = []
        for row in details:
            status = str(row.get("best_status") or "").lower()
            if status in ("fail", "ng"):
                label = str(row.get("detail_label") or row.get("detail_key") or "").strip()
                if label and label != "工序整体":
                    failed_labels.append(label)
            reason = str(row.get("best_reason") or "").strip()
            if reason:
                reason_texts.append(reason)

        if failed_labels:
            summary = f"检测到异常细节: {', '.join(failed_labels[:3])}" + (" ..." if len(failed_labels) > 3 else "")
        elif overall_status == "pass":
            summary = "AI识别完成，未发现明显异常"
        elif pending > 0:
            summary = "AI识别未完成，请人工确认"
        else:
            summary = "等待识别结果"

        primary_reason = reason_texts[0] if reason_texts else ""
        return {
            "overall_status": overall_status,
            "detail_total": total,
            "detail_passed": passed,
            "detail_failed": failed,
            "detail_pending": pending,
            "summary": summary,
            "primary_reason": primary_reason,
            "details": details,
        }


def get_or_start_qc_task_runner(worker_id: str = "qc-runner", poll_interval: float = 2.0) -> QCTaskRunner:
    global _runner_instance
    with _runner_lock:
        if _runner_instance is None:
            app_obj = None
            try:
                app_obj = current_app._get_current_object()
            except Exception:
                app_obj = None
            _runner_instance = QCTaskRunner(
                worker_id=worker_id,
                poll_interval=poll_interval,
                flask_app=app_obj,
            )
            _runner_instance.start()
        return _runner_instance
