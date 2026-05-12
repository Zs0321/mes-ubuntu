from typing import Dict, Any, List, Optional
from collections import Counter
from datetime import datetime
import re
from sqlalchemy import func
from ..models import InspectionRecord, db

_DATE_ONLY_RE = re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")


def _parse_datetime(value: str, *, end_of_day: bool) -> Optional[datetime]:
    if not value:
        return None
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if _DATE_ONLY_RE.match(raw):
            dt = datetime.strptime(raw, "%Y-%m-%d")
            if end_of_day:
                return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            return dt
        # Accept ISO-like strings: 2026-02-16T22:54:57, with/without timezone.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


class ReportService:
    def get_defect_statistics(
        self,
        project_code: str,
        start_date: str = None,
        end_date: str = None
    ) -> Dict[str, Any]:
        """Get defect statistics for a project"""

        query = db.session.query(InspectionRecord).filter(
            InspectionRecord.project_code == project_code,
            InspectionRecord.status.in_(["pass", "fail", "ng", "completed"])
        )

        start_dt = _parse_datetime(start_date, end_of_day=False) if start_date else None
        end_dt = _parse_datetime(end_date, end_of_day=True) if end_date else None
        if start_dt:
            query = query.filter(InspectionRecord.inspected_at >= start_dt)
        if end_dt:
            query = query.filter(InspectionRecord.inspected_at <= end_dt)

        records = query.all()

        # Count defects
        all_defects = []
        for record in records:
            all_defects.extend(record.defects_found or [])

        defect_counts = Counter(all_defects)

        return {
            "total_inspections": len(records),
            "total_defects": len(all_defects),
            "defect_types": dict(defect_counts),
            "defect_rate": len([r for r in records if r.defects_found]) / len(records) if records else 0
        }

    def get_process_step_report(self, project_code: str) -> List[Dict[str, Any]]:
        """Get inspection summary by process step"""

        results = db.session.query(
            InspectionRecord.process_step,
            func.count(InspectionRecord.id).label('count')
        ).filter(
            InspectionRecord.project_code == project_code
        ).group_by(
            InspectionRecord.process_step
        ).all()

        return [
            {
                "process_step": r.process_step,
                "inspection_count": r.count
            }
            for r in results
        ]
