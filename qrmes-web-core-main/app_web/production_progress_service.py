from __future__ import annotations

import json
import mimetypes
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from werkzeug.utils import secure_filename

from qrmes_shared_core.config import config
from qrmes_shared_core.data_dir_utils import resolve_data_dir
from qrmes_shared_core.project_config_manager import ProjectConfigManager


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
FINISH_PRODUCTION_STEP_KEYWORDS = (
    "完成生产",
    # Historical MES photo steps do not use the new "完成生产拍照" name yet.
    # Treat final packaging/shipping evidence as production completion for
    # backfilled records, otherwise historical dashboards show 0 completed.
    "出货报告",
    "出货软件测试报告",
    "包装发运",
    "打包装箱",
)


@dataclass(frozen=True)
class StepConfig:
    name: str
    order: int = 0


def current_millis() -> int:
    return int(time.time() * 1000)


def parse_timestamp(value: Any, default: Optional[int] = None) -> int:
    if value in (None, ""):
        return current_millis() if default is None else default
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return current_millis() if default is None else default
    try:
        return int(float(text))
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return int(parsed.timestamp() * 1000)
    except ValueError:
        return current_millis() if default is None else default


def human_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return ""
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, sec = divmod(rem, 60)
    parts: List[str] = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes:
        parts.append(f"{minutes}分钟")
    if sec or not parts:
        parts.append(f"{sec}秒")
    return "".join(parts)


def _photo_event_time(photo: Dict[str, Any]) -> Optional[int]:
    candidates = []
    for key in ("captured_at", "uploaded_at"):
        value = photo.get(key)
        if value in (None, ""):
            continue
        try:
            timestamp = int(value)
        except (TypeError, ValueError):
            continue
        if timestamp > 0:
            candidates.append(timestamp)
    return max(candidates) if candidates else None


def _is_finish_production_step(process_step: str) -> bool:
    step = str(process_step or "")
    return any(keyword in step for keyword in FINISH_PRODUCTION_STEP_KEYWORDS)


def _safe_segment(value: str, fallback: str) -> str:
    cleaned = secure_filename(str(value or "").strip())
    return cleaned or fallback


def _json_loads(value: Any) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _dedupe_steps(steps: Iterable[StepConfig]) -> List[StepConfig]:
    seen = set()
    result: List[StepConfig] = []
    for step in steps:
        name = str(step.name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(StepConfig(name=name, order=int(step.order or 0)))
    result.sort(key=lambda item: (item.order, item.name))
    return result


class ProductionProgressService:
    def __init__(
        self,
        data_dir: Optional[Path | str] = None,
        db_path: Optional[Path | str] = None,
        photo_db_path: Optional[Path | str] = None,
    ):
        self.data_dir = Path(data_dir) if data_dir else resolve_data_dir(
            nas_local_base_path=getattr(config, "nas_local_base_path", None),
            repo_root=Path(__file__).resolve().parent.parent,
        )
        self.db_path = Path(db_path) if db_path else self.data_dir / "production_progress.db"
        # Existing MES process photos live in DATA_DIR/unified.db.  The first
        # version pointed at web_users.db, which made the board look empty even
        # though historical process photos already existed.
        self.photo_db_path = Path(photo_db_path) if photo_db_path else self.data_dir / "unified.db"
        self.upload_root = self.data_dir / "production_progress_uploads"
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_progress_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serial TEXT NOT NULL,
                    project_name TEXT,
                    product_type TEXT,
                    process_step TEXT NOT NULL,
                    process_order INTEGER DEFAULT 0,
                    event_type TEXT NOT NULL CHECK (event_type IN ('scan','complete')),
                    operator TEXT,
                    occurred_at INTEGER NOT NULL,
                    source TEXT DEFAULT 'web',
                    metadata TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_progress_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    serial TEXT NOT NULL,
                    process_step TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    content_type TEXT,
                    uploaded_by TEXT,
                    uploaded_at INTEGER NOT NULL,
                    metadata TEXT
                )
                """
            )
            self._ensure_serial_column(conn, "production_progress_events")
            self._ensure_serial_column(conn, "production_progress_documents")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pp_events_serial ON production_progress_events(serial)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pp_events_step ON production_progress_events(process_step)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pp_events_time ON production_progress_events(occurred_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pp_documents_serial_step ON production_progress_documents(serial, process_step)"
            )
            conn.commit()

    def _ensure_serial_column(self, conn: sqlite3.Connection, table_name: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        if "serial" in columns:
            return
        if "product_serial" not in columns:
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN serial TEXT")
        conn.execute(f"UPDATE {table_name} SET serial = product_serial WHERE serial IS NULL OR serial = ''")

    def record_event(
        self,
        product_serial: str,
        process_step: str,
        event_type: str,
        project_name: str = "",
        product_type: str = "",
        process_order: int = 0,
        operator: str = "",
        occurred_at: Any = None,
        source: str = "web",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        serial = str(product_serial or "").strip()
        step = str(process_step or "").strip()
        event = str(event_type or "").strip()
        if not serial:
            raise ValueError("product_serial is required")
        if not step:
            raise ValueError("process_step is required")
        if event not in {"scan", "complete"}:
            raise ValueError("event_type must be scan or complete")
        occurred = parse_timestamp(occurred_at)
        payload = json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO production_progress_events (
                    serial, project_name, product_type, process_step, process_order,
                    event_type, operator, occurred_at, source, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    serial,
                    str(project_name or "").strip(),
                    str(product_type or "").strip(),
                    step,
                    int(process_order or 0),
                    event,
                    str(operator or "").strip(),
                    occurred,
                    str(source or "web").strip() or "web",
                    payload,
                ),
            )
            conn.commit()
            event_id = int(cursor.lastrowid)
        return {
            "id": event_id,
            "product_serial": serial,
            "process_step": step,
            "event_type": event,
            "occurred_at": occurred,
        }

    def get_board(
        self,
        serial: str = "",
        project: str = "",
        product_type: str = "",
        status: str = "",
        limit: int = 100,
        now: Optional[int] = None,
    ) -> Dict[str, Any]:
        conditions = ["event_type = 'scan'"]
        params: List[Any] = []
        if serial:
            conditions.append("serial LIKE ?")
            params.append(f"%{serial.strip()}%")
        if project:
            conditions.append("project_name = ?")
            params.append(project.strip())
        if product_type:
            conditions.append("product_type = ?")
            params.append(product_type.strip())
        where = f"WHERE {' AND '.join(conditions)}"
        limit = min(max(int(limit or 100), 1), 500)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT serial, MAX(occurred_at) AS last_event_at
                FROM production_progress_events
                {where}
                GROUP BY serial
                ORDER BY last_event_at DESC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()

        serials: Dict[str, int] = {str(row["serial"]): int(row["last_event_at"] or 0) for row in rows}
        # Backfill the live board from existing MES process photos.  This keeps
        # the page useful before the new scan/complete API is wired into every
        # scanner client: photographed products already have serial, process and
        # captured_at data, so they can be treated as in-progress production
        # evidence.
        for photo_row in self._load_photo_serial_rows(serial=serial, limit=limit):
            photo_serial = str(photo_row["product_serial"] or "").strip()
            if not photo_serial:
                continue
            serials[photo_serial] = max(serials.get(photo_serial, 0), int(photo_row["last_event_at"] or 0))

        ordered_serials = [item[0] for item in sorted(serials.items(), key=lambda item: item[1], reverse=True)[:limit]]
        items = [self.get_detail(item_serial, now=now, include_timeline=False) for item_serial in ordered_serials]
        if project:
            items = [item for item in items if item.get("project_name") == project.strip()]
        if product_type:
            items = [item for item in items if item.get("product_type") == product_type.strip()]
        if status:
            items = [item for item in items if item.get("status") == status]
        summary = None if project or product_type else self._photo_board_summary(serial=serial, status=status)
        if not summary:
            completed_count = len([item for item in items if item.get("status") == "completed"])
            in_progress_count = len([item for item in items if item.get("status") == "in_progress"])
            summary = {
                "total": len(items),
                "displayed": len(items),
                "completed": completed_count,
                "in_progress": in_progress_count,
                "not_started": max(0, len(items) - completed_count - in_progress_count),
                "limit": limit,
            }
        else:
            summary["displayed"] = len(items)
            summary["limit"] = limit
        return {"items": items, "total": summary.get("total", len(items)), "summary": summary}

    def get_detail(self, product_serial: str, now: Optional[int] = None, include_timeline: bool = True) -> Dict[str, Any]:
        serial = str(product_serial or "").strip()
        if not serial:
            raise ValueError("product_serial is required")
        now_ms = int(now if now is not None else current_millis())
        events = self._load_events(serial)
        if not events:
            photo_timeline = self._build_photo_only_timeline(serial, now_ms)
            if photo_timeline:
                first_scan = min(step["scan_at"] for step in photo_timeline if step.get("scan_at") is not None)
                last_event = max(step["last_scan_at"] or step["scan_at"] or first_scan for step in photo_timeline)
                completion = self._completion_photo_from_timeline(photo_timeline)
                final_complete = completion["photo_at"] if completion else None
                if completion:
                    self._apply_completion_photo_to_timeline(photo_timeline, completion["process_step"], final_complete)
                current_step = max(photo_timeline, key=lambda step: (step.get("last_scan_at") or 0, step.get("process_order") or 0))
                if completion:
                    current_step = self._timeline_step_by_name(photo_timeline, completion["process_step"]) or current_step
                payload = {
                    "product_serial": serial,
                    "status": "completed" if completion else "in_progress",
                    "project_name": "",
                    "product_type": "",
                    "first_scan_at": first_scan,
                    "final_complete_at": final_complete,
                    "completion_photo_at": final_complete,
                    "completion_basis": "finish_production_photo" if completion else "",
                    "last_event_at": max(last_event, final_complete or 0),
                    "current_step": current_step,
                    "total_duration": self._duration_payload(((final_complete or now_ms) - first_scan) // 1000),
                    "attachments": self._load_attachments(serial),
                }
                if include_timeline:
                    payload["timeline"] = photo_timeline
                return payload
            return {
                "product_serial": serial,
                "status": "not_started",
                "project_name": "",
                "product_type": "",
                "first_scan_at": None,
                "final_complete_at": None,
                "completion_photo_at": None,
                "completion_basis": "",
                "last_event_at": None,
                "current_step": None,
                "total_duration": self._duration_payload(None),
                "timeline": [] if include_timeline else None,
                "attachments": {"photos": [], "documents": []},
            }

        project_name = self._latest_non_empty(events, "project_name")
        product_type = self._latest_non_empty(events, "product_type")
        timeline = self._build_timeline(serial, events, project_name, product_type, now_ms)
        current_step = self._choose_current_step(timeline)
        status = "not_started"
        if current_step:
            status = current_step["status"]
            if status == "not_started":
                status = "in_progress"
        first_scan = min(
            (int(event["occurred_at"]) for event in events if event["event_type"] == "scan"),
            default=None,
        )
        if first_scan is None:
            first_scan = min(
                (int(step["scan_at"]) for step in timeline if step.get("scan_at") is not None),
                default=None,
            )
        scanned_steps = [step for step in timeline if step["scan_at"] is not None]
        final_complete = None
        completion_basis = ""
        completion_photo_at = None
        completion = self._completion_photo_from_timeline(timeline)
        if completion:
            completion_photo_at = completion["photo_at"]
            final_complete = completion_photo_at
            completion_basis = "finish_production_photo"
            self._apply_completion_photo_to_timeline(timeline, completion["process_step"], final_complete)
            status = "completed"
            current_step = self._timeline_step_by_name(timeline, completion["process_step"]) or current_step
        elif scanned_steps and all(step["complete_at"] is not None for step in scanned_steps):
            final_complete = max(step["complete_at"] for step in scanned_steps if step["complete_at"] is not None)
            completion_basis = "scan_complete_events"
            status = "completed"
        total_duration = self._duration_payload(None if first_scan is None else ((final_complete or now_ms) - first_scan) // 1000)
        attachments = self._load_attachments(serial)
        payload = {
            "product_serial": serial,
            "status": status,
            "project_name": project_name,
            "product_type": product_type,
            "first_scan_at": first_scan,
            "final_complete_at": final_complete,
            "completion_photo_at": completion_photo_at,
            "completion_basis": completion_basis,
            "last_event_at": max(max(int(event["occurred_at"]) for event in events), final_complete or 0),
            "current_step": current_step,
            "total_duration": total_duration,
            "attachments": attachments,
        }
        if include_timeline:
            payload["timeline"] = timeline
        return payload

    def save_attachment(
        self,
        product_serial: str,
        process_step: str,
        source_path: Path | str,
        file_name: str,
        content_type: str = "",
        uploaded_by: str = "",
        uploaded_at: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        serial = str(product_serial or "").strip()
        step = str(process_step or "").strip()
        if not serial:
            raise ValueError("product_serial is required")
        if not step:
            raise ValueError("process_step is required")
        source = Path(source_path)
        safe_name = _safe_segment(Path(str(file_name or source.name)).name, "attachment.bin")
        target_dir = self.upload_root / _safe_segment(serial, "serial") / _safe_segment(step, "process")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = self._unique_target_path(target_dir / safe_name)
        shutil.copyfile(source, target)
        return self._insert_attachment(
            product_serial=serial,
            process_step=step,
            target_path=target,
            file_name=target.name,
            content_type=content_type,
            uploaded_by=uploaded_by,
            uploaded_at=uploaded_at,
            metadata=metadata,
        )

    def save_file_storage(
        self,
        product_serial: str,
        process_step: str,
        storage: Any,
        uploaded_by: str = "",
        uploaded_at: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        safe_name = _safe_segment(Path(storage.filename or "attachment.bin").name, "attachment.bin")
        serial = str(product_serial or "").strip()
        step = str(process_step or "").strip()
        target_dir = self.upload_root / _safe_segment(serial, "serial") / _safe_segment(step, "process")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = self._unique_target_path(target_dir / safe_name)
        storage.save(str(target))
        content_type = storage.mimetype or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if self._is_image(target, content_type):
            return self._insert_process_photo(serial, step, target, content_type, uploaded_by, uploaded_at, metadata)
        return self._insert_attachment(serial, step, target, target.name, content_type, uploaded_by, uploaded_at, metadata)

    def resolve_document_path(self, attachment_id: int) -> Path:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT file_path FROM production_progress_documents WHERE id = ?",
                (int(attachment_id),),
            ).fetchone()
        if row is None:
            raise FileNotFoundError("attachment not found")
        candidate = Path(str(row["file_path"])).resolve()
        root = self.upload_root.resolve()
        if root not in [candidate, *candidate.parents]:
            raise PermissionError("attachment path is outside upload root")
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError("attachment file not found")
        return candidate

    def list_options(self) -> Dict[str, List[str]]:
        projects = set()
        product_types = set()
        steps = set()
        with self._connect() as conn:
            for row in conn.execute(
                """
                SELECT project_name, product_type, process_step
                FROM production_progress_events
                ORDER BY occurred_at DESC
                LIMIT 1000
                """
            ).fetchall():
                if row["project_name"]:
                    projects.add(str(row["project_name"]))
                if row["product_type"]:
                    product_types.add(str(row["product_type"]))
                if row["process_step"]:
                    steps.add(str(row["process_step"]))
        try:
            manager = ProjectConfigManager(self.data_dir)
            for project_name in manager.list_projects():
                projects.add(str(project_name))
                config_data = manager.get_project_config(project_name) or {}
                for product_type in config_data.get("productTypes", []) or []:
                    product_name = str(product_type.get("typeName") or "").strip()
                    if product_name:
                        product_types.add(product_name)
                    for step in product_type.get("processSteps", []) or []:
                        if isinstance(step, dict) and step.get("name"):
                            steps.add(str(step["name"]))
                for step in config_data.get("processAttributes", []) or []:
                    if isinstance(step, dict) and step.get("name"):
                        steps.add(str(step["name"]))
        except Exception:
            pass
        for step in self._load_process_configurations():
            steps.add(step.name)
        return {
            "projects": sorted(projects),
            "product_types": sorted(product_types),
            "process_steps": sorted(steps),
        }

    def _load_events(self, serial: str) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT *
                FROM production_progress_events
                WHERE serial = ?
                ORDER BY occurred_at ASC, id ASC
                """,
                (serial,),
            ).fetchall()

    def _build_timeline(
        self,
        serial: str,
        events: List[sqlite3.Row],
        project_name: str,
        product_type: str,
        now_ms: int,
    ) -> List[Dict[str, Any]]:
        configured = self._load_configured_steps(project_name, product_type)
        photos_by_step = self._load_photos_by_step(serial)
        documents_by_step = self._load_documents_by_step(serial)
        event_steps = [
            StepConfig(name=str(event["process_step"]), order=int(event["process_order"] or 0))
            for event in events
        ]
        attachment_steps = [
            StepConfig(name=step_name, order=0)
            for step_name in [*photos_by_step.keys(), *documents_by_step.keys()]
        ]
        steps = _dedupe_steps([*configured, *event_steps, *attachment_steps])
        grouped: Dict[str, List[sqlite3.Row]] = {}
        for event in events:
            grouped.setdefault(str(event["process_step"]), []).append(event)
        timeline = []
        for index, step in enumerate(steps, start=1):
            rows = grouped.get(step.name, [])
            scans = [int(row["occurred_at"]) for row in rows if row["event_type"] == "scan"]
            completes = [int(row["occurred_at"]) for row in rows if row["event_type"] == "complete"]
            photo_times = [_photo_event_time(item) for item in photos_by_step.get(step.name, [])]
            doc_times = [int(item.get("uploaded_at") or 0) for item in documents_by_step.get(step.name, [])]
            observed_attachment_times = [ts for ts in [*photo_times, *doc_times] if ts]
            scan_at = max(scans, default=None)
            if scan_at is None and observed_attachment_times:
                scan_at = min(observed_attachment_times)
            complete_at = None
            if scan_at is not None:
                complete_at = min((ts for ts in completes if ts >= scan_at), default=None)
            step_status = "not_started"
            duration_seconds = None
            if scan_at is not None and complete_at is None:
                step_status = "in_progress"
                duration_seconds = (now_ms - scan_at) // 1000
            elif scan_at is not None and complete_at is not None:
                step_status = "completed"
                duration_seconds = (complete_at - scan_at) // 1000
            timeline.append(
                {
                    "process_step": step.name,
                    "process_order": step.order or index,
                    "status": step_status,
                    "scan_at": scan_at,
                    "last_scan_at": scan_at,
                    "complete_at": complete_at,
                    "duration_seconds": None if duration_seconds is None else max(0, int(duration_seconds)),
                    "human_duration": human_duration(duration_seconds),
                    "attachments": {
                        "photos": photos_by_step.get(step.name, []),
                        "documents": documents_by_step.get(step.name, []),
                    },
                }
            )
        return timeline

    def _choose_current_step(self, timeline: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        in_progress = [step for step in timeline if step["status"] == "in_progress"]
        if in_progress:
            return max(in_progress, key=lambda step: (step.get("last_scan_at") or 0, step.get("process_order") or 0))
        completed = [step for step in timeline if step["status"] == "completed"]
        if completed:
            return max(completed, key=lambda step: (step.get("complete_at") or 0, step.get("process_order") or 0))
        return None

    def _completion_photo_from_timeline(self, timeline: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        latest: Optional[Dict[str, Any]] = None
        for step in timeline:
            process_step = str(step.get("process_step") or "")
            if not _is_finish_production_step(process_step):
                continue
            for photo in ((step.get("attachments") or {}).get("photos") or []):
                photo_at = _photo_event_time(photo)
                if photo_at is None:
                    continue
                if latest is None or photo_at > latest["photo_at"]:
                    latest = {
                        "process_step": process_step,
                        "photo_at": photo_at,
                        "photo": photo,
                    }
        return latest

    def _apply_completion_photo_to_timeline(
        self,
        timeline: List[Dict[str, Any]],
        process_step: str,
        final_complete_at: Optional[int],
    ) -> None:
        if final_complete_at is None:
            return
        step = self._timeline_step_by_name(timeline, process_step)
        if not step:
            return
        if step.get("scan_at") is None:
            step["scan_at"] = final_complete_at
            step["last_scan_at"] = final_complete_at
        step["complete_at"] = final_complete_at
        step["status"] = "completed"
        duration_seconds = max(0, int((final_complete_at - int(step.get("scan_at") or final_complete_at)) // 1000))
        step["duration_seconds"] = duration_seconds
        step["human_duration"] = human_duration(duration_seconds)
        step["completion_basis"] = "finish_production_photo"

    def _timeline_step_by_name(
        self,
        timeline: List[Dict[str, Any]],
        process_step: str,
    ) -> Optional[Dict[str, Any]]:
        for step in timeline:
            if step.get("process_step") == process_step:
                return step
        return None

    def _load_configured_steps(self, project_name: str, product_type: str) -> List[StepConfig]:
        steps: List[StepConfig] = []
        if project_name:
            try:
                manager = ProjectConfigManager(self.data_dir)
                if product_type:
                    steps.extend(self._convert_process_rows(manager.get_product_type_processes(project_name, product_type)))
                if not steps:
                    config_data = manager.get_project_config(project_name) or {}
                    for item in config_data.get("productTypes", []) or []:
                        if product_type and item.get("typeName") != product_type:
                            continue
                        steps.extend(self._convert_process_rows(item.get("processSteps", [])))
                if not steps:
                    steps.extend(self._convert_process_rows(manager.get_process_attributes(project_name)))
            except Exception:
                steps = []
        if not steps:
            steps.extend(self._load_process_configurations())
        return _dedupe_steps(steps)

    def _load_process_configurations(self) -> List[StepConfig]:
        if not self.photo_db_path.exists():
            return []
        try:
            with sqlite3.connect(self.photo_db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='process_configurations'"
                ).fetchone()
                if not exists:
                    return []
                return [
                    StepConfig(name=str(row["name"]), order=int(row["order_index"] or 0))
                    for row in conn.execute(
                        "SELECT name, order_index FROM process_configurations ORDER BY order_index ASC, name ASC"
                    ).fetchall()
                ]
        except sqlite3.DatabaseError:
            return []

    def _convert_process_rows(self, rows: Iterable[Dict[str, Any]]) -> List[StepConfig]:
        result = []
        for index, row in enumerate(rows or [], start=1):
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("process_step") or "").strip()
            if not name:
                continue
            result.append(StepConfig(name=name, order=int(row.get("order") or row.get("step_order") or index)))
        return result

    def _load_attachments(self, serial: str) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "photos": [item for values in self._load_photos_by_step(serial).values() for item in values],
            "documents": [item for values in self._load_documents_by_step(serial).values() for item in values],
        }

    def _load_documents_by_step(self, serial: str) -> Dict[str, List[Dict[str, Any]]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM production_progress_documents
                WHERE serial = ?
                ORDER BY uploaded_at DESC, id DESC
                """,
                (serial,),
            ).fetchall()
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            item = self._document_payload(row)
            result.setdefault(str(row["process_step"]), []).append(item)
        return result

    def _photo_board_summary(self, serial: str = "", status: str = "") -> Dict[str, int]:
        if not self.photo_db_path.exists():
            return {}
        try:
            with sqlite3.connect(self.photo_db_path, timeout=10) as conn:
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='process_photos'"
                ).fetchone()
                if not exists:
                    return {}
                serial_condition = ""
                serial_params: List[Any] = []
                if serial:
                    serial_condition = "WHERE product_serial LIKE ?"
                    serial_params.append(f"%{serial.strip()}%")
                total = int(
                    conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM (
                            SELECT product_serial
                            FROM process_photos
                            {serial_condition}
                            GROUP BY product_serial
                        )
                        """,
                        serial_params,
                    ).fetchone()[0]
                    or 0
                )
                finish_clause = " OR ".join(["process_step LIKE ?" for _ in FINISH_PRODUCTION_STEP_KEYWORDS])
                completed_conditions = []
                completed_params: List[Any] = []
                if serial:
                    completed_conditions.append("product_serial LIKE ?")
                    completed_params.append(f"%{serial.strip()}%")
                completed_conditions.append(f"({finish_clause})")
                completed_params.extend([f"%{keyword}%" for keyword in FINISH_PRODUCTION_STEP_KEYWORDS])
                completed_where = f"WHERE {' AND '.join(completed_conditions)}"
                completed = int(
                    conn.execute(
                        f"""
                        SELECT COUNT(DISTINCT product_serial)
                        FROM process_photos
                        {completed_where}
                        """,
                        completed_params,
                    ).fetchone()[0]
                    or 0
                )
        except sqlite3.DatabaseError:
            return {}
        in_progress = max(0, total - completed)
        if status == "completed":
            total_for_status = completed
        elif status == "in_progress":
            total_for_status = in_progress
        elif status == "not_started":
            total_for_status = 0
        else:
            total_for_status = total
        return {
            "total": total_for_status,
            "all_products": total,
            "completed": completed if status in ("", "completed") else 0,
            "in_progress": in_progress if status in ("", "in_progress") else 0,
            "not_started": 0,
        }

    def _load_photo_serial_rows(self, serial: str = "", limit: int = 100) -> List[sqlite3.Row]:
        if not self.photo_db_path.exists():
            return []
        try:
            with sqlite3.connect(self.photo_db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='process_photos'"
                ).fetchone()
                if not exists:
                    return []
                conditions = []
                params: List[Any] = []
                if serial:
                    conditions.append("product_serial LIKE ?")
                    params.append(f"%{serial.strip()}%")
                where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                return conn.execute(
                    f"""
                    SELECT
                        product_serial,
                        MAX(
                            CASE
                                WHEN uploaded_at IS NOT NULL AND uploaded_at > captured_at THEN uploaded_at
                                ELSE captured_at
                            END
                        ) AS last_event_at
                    FROM process_photos
                    {where}
                    GROUP BY product_serial
                    ORDER BY last_event_at DESC
                    LIMIT ?
                    """,
                    [*params, min(max(int(limit or 100), 1), 500)],
                ).fetchall()
        except sqlite3.DatabaseError:
            return []

    def _build_photo_only_timeline(self, serial: str, now_ms: int) -> List[Dict[str, Any]]:
        photos_by_step = self._load_photos_by_step(serial)
        documents_by_step = self._load_documents_by_step(serial)
        step_names = list(dict.fromkeys([*photos_by_step.keys(), *documents_by_step.keys()]))
        timeline: List[Dict[str, Any]] = []
        for index, step_name in enumerate(step_names, start=1):
            photo_times = [int(item.get("captured_at") or item.get("uploaded_at") or 0) for item in photos_by_step.get(step_name, [])]
            doc_times = [int(item.get("uploaded_at") or 0) for item in documents_by_step.get(step_name, [])]
            observed = [ts for ts in [*photo_times, *doc_times] if ts > 0]
            if not observed:
                continue
            scan_at = min(observed)
            last_scan_at = max(observed)
            timeline.append(
                {
                    "process_step": step_name,
                    "process_order": index,
                    "status": "in_progress",
                    "scan_at": scan_at,
                    "last_scan_at": last_scan_at,
                    "complete_at": None,
                    "duration_seconds": max(0, int((now_ms - scan_at) // 1000)),
                    "human_duration": human_duration((now_ms - scan_at) // 1000),
                    "attachments": {
                        "photos": photos_by_step.get(step_name, []),
                        "documents": documents_by_step.get(step_name, []),
                    },
                    "inferred_from_photos": True,
                }
            )
        timeline.sort(key=lambda step: (step.get("scan_at") or 0, step.get("process_order") or 0))
        return timeline

    def _load_photos_by_step(self, serial: str) -> Dict[str, List[Dict[str, Any]]]:
        if not self.photo_db_path.exists():
            return {}
        try:
            with sqlite3.connect(self.photo_db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='process_photos'"
                ).fetchone()
                if not exists:
                    return {}
                rows = conn.execute(
                    """
                    SELECT *
                    FROM process_photos
                    WHERE product_serial = ?
                    ORDER BY captured_at DESC, id DESC
                    """,
                    (serial,),
                ).fetchall()
        except sqlite3.DatabaseError:
            return {}
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            item = {
                "id": int(row["id"]),
                "product_serial": str(row["product_serial"]),
                "process_step": str(row["process_step"]),
                "file_name": str(row["file_name"] or ""),
                "file_size": row["file_size"],
                "captured_by": str(row["captured_by"] or ""),
                "captured_at": row["captured_at"],
                "uploaded_at": row["uploaded_at"],
                "metadata": _json_loads(row["metadata"]),
                "preview_url": f"/api/photos/file/{int(row['id'])}",
            }
            result.setdefault(str(row["process_step"]), []).append(item)
        return result

    def _insert_attachment(
        self,
        product_serial: str,
        process_step: str,
        target_path: Path,
        file_name: str,
        content_type: str = "",
        uploaded_by: str = "",
        uploaded_at: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        uploaded = parse_timestamp(uploaded_at)
        file_size = target_path.stat().st_size if target_path.exists() else 0
        guessed_type = content_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO production_progress_documents (
                    serial, process_step, file_path, file_name, file_size,
                    content_type, uploaded_by, uploaded_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_serial,
                    process_step,
                    str(target_path),
                    file_name,
                    file_size,
                    guessed_type,
                    str(uploaded_by or "").strip(),
                    uploaded,
                    json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            conn.commit()
            attachment_id = int(cursor.lastrowid)
        return {
            "id": attachment_id,
            "product_serial": product_serial,
            "process_step": process_step,
            "file_name": file_name,
            "file_size": file_size,
            "content_type": guessed_type,
            "uploaded_by": str(uploaded_by or "").strip(),
            "uploaded_at": uploaded,
            "download_url": f"/api/production-progress/attachment/{attachment_id}",
            "kind": "document",
        }

    def _insert_process_photo(
        self,
        product_serial: str,
        process_step: str,
        target_path: Path,
        content_type: str = "",
        uploaded_by: str = "",
        uploaded_at: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        uploaded = parse_timestamp(uploaded_at)
        self.photo_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.photo_db_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS process_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_serial TEXT NOT NULL,
                    process_step TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    captured_by TEXT,
                    captured_at INTEGER NOT NULL,
                    uploaded_at INTEGER,
                    metadata TEXT
                )
                """
            )
            cursor = conn.execute(
                """
                INSERT INTO process_photos (
                    product_serial, process_step, file_path, file_name, file_size,
                    captured_by, captured_at, uploaded_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_serial,
                    process_step,
                    str(target_path),
                    target_path.name,
                    target_path.stat().st_size if target_path.exists() else 0,
                    str(uploaded_by or "").strip(),
                    uploaded,
                    uploaded,
                    json.dumps(
                        {
                            "source": "production_progress_upload",
                            "contentType": content_type,
                            **(metadata or {}),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
            )
            conn.commit()
            photo_id = int(cursor.lastrowid)
        return {
            "id": photo_id,
            "product_serial": product_serial,
            "process_step": process_step,
            "file_name": target_path.name,
            "file_size": target_path.stat().st_size if target_path.exists() else 0,
            "content_type": content_type,
            "uploaded_by": str(uploaded_by or "").strip(),
            "uploaded_at": uploaded,
            "preview_url": f"/api/photos/file/{photo_id}",
            "kind": "photo",
        }

    def _document_payload(self, row: sqlite3.Row) -> Dict[str, Any]:
        attachment_id = int(row["id"])
        return {
            "id": attachment_id,
            "product_serial": str(row["serial"]),
            "process_step": str(row["process_step"]),
            "file_name": str(row["file_name"] or ""),
            "file_size": row["file_size"],
            "content_type": str(row["content_type"] or ""),
            "uploaded_by": str(row["uploaded_by"] or ""),
            "uploaded_at": row["uploaded_at"],
            "metadata": _json_loads(row["metadata"]),
            "download_url": f"/api/production-progress/attachment/{attachment_id}",
        }

    def _duration_payload(self, seconds: Optional[int]) -> Dict[str, Any]:
        return {
            "duration_seconds": None if seconds is None else max(0, int(seconds)),
            "human_duration": human_duration(seconds),
        }

    def _latest_non_empty(self, events: List[sqlite3.Row], field: str) -> str:
        for event in reversed(events):
            value = str(event[field] or "").strip()
            if value:
                return value
        return ""

    def _unique_target_path(self, target: Path) -> Path:
        if not target.exists():
            return target
        stem = target.stem
        suffix = target.suffix
        for index in range(1, 1000):
            candidate = target.with_name(f"{stem}_{index}{suffix}")
            if not candidate.exists():
                return candidate
        return target.with_name(f"{stem}_{current_millis()}{suffix}")

    def _is_image(self, path: Path, content_type: str) -> bool:
        return str(content_type or "").lower().startswith("image/") or path.suffix.lower() in IMAGE_SUFFIXES
