from datetime import datetime
from pathlib import Path
import re
from typing import Dict, List, Any

from sqlalchemy.exc import IntegrityError

from ..models import db, QCProcessTask, QCTaskPhoto


_DETAIL_STATUS_RANK = {
    "pending": 0,
    "fail": 1,
    "ng": 1,
    "pass": 2,
}


def build_process_task_key(project_id: str, serial_number: str, process_name: str) -> str:
    return f"{(project_id or '').strip()}|{(serial_number or '').strip()}|{(process_name or '').strip()}"


def normalize_detail_key(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[\s._-]+", "_", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text.strip("_")


class QCTaskService:
    def upsert_task_for_photo(
        self,
        project_id: str,
        serial_number: str,
        process_name: str,
        photo_path: str,
        product_type: str = "",
        auto_commit: bool = True,
        reset_status: bool = True,
    ) -> QCProcessTask:
        task_key = build_process_task_key(project_id, serial_number, process_name)

        task = (
            db.session.query(QCProcessTask)
            .filter(QCProcessTask.task_key == task_key)
            .first()
        )

        if not task:
            try:
                with db.session.begin_nested():
                    task = QCProcessTask(
                        task_key=task_key,
                        project_id=(project_id or "").strip(),
                        serial_number=(serial_number or "").strip(),
                        process_name=(process_name or "").strip(),
                        product_type=((product_type or "").strip() or None),
                        status="pending",
                    )
                    db.session.add(task)
                    db.session.flush()
            except IntegrityError:
                # 并发创建时可能命中唯一键，回退到已存在任务继续追加照片。
                task = (
                    db.session.query(QCProcessTask)
                    .filter(QCProcessTask.task_key == task_key)
                    .first()
                )
                if not task:
                    raise
        elif product_type and not task.product_type:
            task.product_type = (product_type or "").strip()

        normalized_path = str(photo_path or "").strip()
        existing_photo = None
        photo_added = False
        if normalized_path:
            existing_photo = (
                db.session.query(QCTaskPhoto)
                .filter_by(task_id=task.id, photo_path=normalized_path)
                .first()
            )
        if normalized_path and not existing_photo:
            db.session.add(
                QCTaskPhoto(
                    task_id=task.id,
                    photo_path=normalized_path,
                    photo_name=Path(normalized_path).name or None,
                    captured_at=datetime.utcnow(),
                )
            )
            photo_added = True

        if normalized_path:
            task.latest_photo_path = normalized_path

        # 仅在“新增了照片”时重置任务状态，避免重复上传/重试同一路径时
        # 把已识别结果从 review/confirmed 意外重置回 pending。
        should_reset_status = bool(reset_status and photo_added)
        if should_reset_status:
            task.status = "pending"
            task.error_message = None
            task.claimed_by = None
            task.claimed_at = None

        if photo_added or should_reset_status:
            task.photo_count = db.session.query(QCTaskPhoto).filter(QCTaskPhoto.task_id == task.id).count()
            task.updated_at = datetime.utcnow()
        elif task.photo_count is None:
            task.photo_count = db.session.query(QCTaskPhoto).filter(QCTaskPhoto.task_id == task.id).count()

        if auto_commit:
            db.session.commit()
        return task

    def aggregate_detail_results(self, detail_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for row in detail_rows or []:
            detail_key = normalize_detail_key(
                str(row.get("detail_key") or row.get("detail") or row.get("name") or row.get("label") or "")
            )
            if not detail_key:
                continue

            status = str(row.get("status") or "pending").strip().lower()
            if status not in _DETAIL_STATUS_RANK:
                status = "pending"

            source = str(row.get("source") or "ai").strip().lower() or "ai"
            if source not in ("config", "ai"):
                source = "ai"

            label = str(row.get("detail_label") or row.get("label") or row.get("detail") or detail_key).strip()
            reason = str(row.get("reason") or "").strip()
            photo_id = row.get("photo_id")
            try:
                photo_id = int(photo_id) if photo_id is not None else None
            except (TypeError, ValueError):
                photo_id = None

            current = merged.get(detail_key)
            if not current:
                merged[detail_key] = {
                    "detail_key": detail_key,
                    "detail_label": label or detail_key,
                    "source": source,
                    "best_status": status,
                    "best_photo_id": photo_id,
                    "best_reason": reason,
                    "samples": 1,
                }
                continue

            current["samples"] = int(current.get("samples") or 0) + 1
            if source == "config":
                current["source"] = "config"
            if label and not current.get("detail_label"):
                current["detail_label"] = label

            old_rank = _DETAIL_STATUS_RANK.get(str(current.get("best_status") or "pending"), 0)
            new_rank = _DETAIL_STATUS_RANK.get(status, 0)
            if new_rank > old_rank:
                current["best_status"] = status
                current["best_photo_id"] = photo_id
                current["best_reason"] = reason
            elif reason and not str(current.get("best_reason") or "").strip():
                current["best_reason"] = reason

        return merged
