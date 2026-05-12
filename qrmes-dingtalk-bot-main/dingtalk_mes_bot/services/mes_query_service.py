from __future__ import annotations

import json
import re
import sqlite3
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ..models import PrefixMatch, SerialQueryResult

@dataclass(slots=True)
class MesQueryService:
    base_url: str
    timeout: float = 8.0
    unified_db_path: str = "/volume2/MES/QRMES/unified.db"
    project_config_db_path: str = "/volume2/MES/QRMES/projects/project_configs.db"

    def _get(self, path: str) -> tuple[int, dict | None]:
        url = f"{self.base_url.rstrip('/')}" + path
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
                data = json.loads(payload) if payload else None
                return int(resp.status), data if isinstance(data, dict) else None
        except Exception:
            return 0, None

    def query_serial(self, serial: str) -> str:
        quoted = urllib.parse.quote(serial.strip())
        status, data = self._get(f"/api/process-config/resolve-serial-rule?serial={quoted}")
        if status == 200 and data:
            matches = data.get("matches")
            if isinstance(matches, list) and matches:
                top = matches[0] if isinstance(matches[0], dict) else {}
                return f"serial={serial} project={top.get('project', '-')}, productType={top.get('productType', '-')}"
            return f"serial={serial} no serial-rule match"
        if status:
            return f"serial query failed: HTTP {status}"
        return "serial query failed: network or server unavailable"

    def query_today_stats(self) -> str:
        status, data = self._get("/api/quality-workbench/today-summary")
        if status == 200 and data:
            return f"today summary: {data}"
        if status:
            return f"today summary failed: HTTP {status}"
        return "today summary failed: network or server unavailable"

    def query_today_photo_uploads(self) -> str:
        status, data = self._get("/api/photos/statistics")
        if status == 200 and data:
            stats = data.get("statistics") if isinstance(data.get("statistics"), dict) else {}
            by_date = stats.get("byDate") if isinstance(stats.get("byDate"), list) else []
            today = datetime.now().strftime("%Y-%m-%d")
            today_count = 0
            for row in by_date:
                if not isinstance(row, dict):
                    continue
                if str(row.get("date") or "").strip() == today:
                    try:
                        today_count = int(row.get("count") or 0)
                    except Exception:
                        today_count = 0
                    break
            return f"今天已上传工序照片 {today_count} 张。"
        if status:
            return f"今日工序照片统计查询失败：HTTP {status}"
        return "今日工序照片统计查询失败：网络或服务暂时不可用"

    def query_today_photo_project_distribution(self) -> str:
        db_path = Path(self.unified_db_path)
        if not db_path.exists():
            return f"今日工序照片项目分布查询失败：数据库不存在（{db_path}）"

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        start_ms = int(today_start.timestamp() * 1000)
        end_ms = int(tomorrow_start.timestamp() * 1000)

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT captured_at, metadata
                FROM process_photos
                WHERE captured_at >= ? AND captured_at < ?
                """,
                (start_ms, end_ms),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception as exc:
            return f"今日工序照片项目分布查询失败：{exc}"

        project_counts: dict[str, int] = {}
        total = 0
        for row in rows:
            metadata_text = row["metadata"] if isinstance(row, sqlite3.Row) else None
            try:
                metadata = json.loads(metadata_text) if metadata_text else {}
            except Exception:
                metadata = {}

            project_name = str(metadata.get("projectName") or "").strip()
            project_code = str(metadata.get("projectCode") or "").strip()
            display_name = project_name or project_code or "未标注项目"
            project_counts[display_name] = project_counts.get(display_name, 0) + 1
            total += 1

        if not project_counts:
            return "今天暂时还没有工序照片上传记录。"

        ordered = sorted(project_counts.items(), key=lambda item: (-item[1], item[0]))
        lines = [f"今天工序照片共分布在 {len(ordered)} 个项目，共 {total} 张。"]
        for index, (project_name, count) in enumerate(ordered, start=1):
            lines.append(f"{index}. {project_name}：{count} 张")
        return "\n".join(lines)

    def query_active_project_count(self) -> str:
        db_path = Path(self.project_config_db_path)
        if not db_path.exists():
            return f"启用项目数量查询失败：数据库不存在（{db_path}）"

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM projects
                WHERE lower(coalesce(project_status, 'active')) = 'active'
                  AND coalesce(is_archived, 0) = 0
                """
            )
            row = cursor.fetchone()
            conn.close()
        except Exception as exc:
            return f"启用项目数量查询失败：{exc}"

        total = int((row or [0])[0] or 0)
        return f"当前启用项目共 {total} 个。"

    def query_serial_database(self, serial: str, prefix_matches: tuple[PrefixMatch, ...] = ()) -> SerialQueryResult:
        quoted = urllib.parse.quote(serial.strip())
        status, data = self._get(f"/api/quality-workbench/{quoted}")
        if status == 200 and data:
            project_name = str(data.get("projectName") or "").strip()
            product_type = str(data.get("productType") or "").strip()
            associations = data.get("associations") if isinstance(data.get("associations"), dict) else {}
            if not project_name:
                project_name = str(associations.get("matchedSerialRuleProject") or "").strip()
            if not product_type:
                product_type = str(associations.get("matchedSerialRuleProductType") or "").strip()
            process_status = data.get("processStatus") if isinstance(data.get("processStatus"), dict) else {}
            quality_conclusion = data.get("qualityConclusion") if isinstance(data.get("qualityConclusion"), dict) else {}
            missing_photo_count = int(process_status.get("missingPhotoCount") or 0)
            inspected_processes = int(process_status.get("inspectedProcesses") or 0)
            total_processes = int(process_status.get("totalProcesses") or 0)
            quality_summary = str(quality_conclusion.get("summary") or quality_conclusion.get("label") or "").strip()
            process_summary = f"已检 {inspected_processes} 道工序，缺少 {missing_photo_count} 道照片"
            found = bool(
                project_name
                or product_type
                or total_processes > 0
                or (quality_summary and quality_summary != "未找到产品记录")
            )
            return SerialQueryResult(
                serial=serial,
                found=found,
                project_name=project_name,
                product_type=product_type,
                quality_summary=quality_summary,
                process_summary=process_summary,
                prefix_matches=prefix_matches,
            )
        if prefix_matches:
            top = prefix_matches[0]
            return SerialQueryResult(
                serial=serial,
                found=False,
                project_name=top.project_name,
                product_type=top.product_type,
                quality_summary="数据库未查到该序列号记录",
                process_summary="仅命中前缀规则，暂无质量工作台数据",
                prefix_matches=prefix_matches,
            )
        return SerialQueryResult(
            serial=serial,
            found=False,
            quality_summary=f"数据库查询失败: HTTP {status}" if status else "数据库未查到该序列号记录",
            process_summary="未命中产品前缀规则",
            prefix_matches=prefix_matches,
        )


SERIAL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_]{7,}")


def detect_serial(text: str) -> str | None:
    m = SERIAL_RE.search(text)
    return m.group(0) if m else None
