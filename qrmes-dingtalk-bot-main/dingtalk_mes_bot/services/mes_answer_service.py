from __future__ import annotations

from dataclasses import dataclass

from .mes_query_service import MesQueryService, detect_serial


@dataclass(slots=True)
class MesAnswerService:
    query_service: MesQueryService

    def answer(self, text: str) -> str | None:
        content = (text or "").strip()
        if not content:
            return None

        lowered = content.lower()

        serial = detect_serial(content)
        if serial and ("serial" in lowered or "query" in lowered or "why" in lowered):
            return self.query_service.query_serial(serial)

        if "today" in lowered and ("shipment" in lowered or "summary" in lowered):
            return self.query_service.query_today_stats()

        if (
            "照片" in content
            and "项目" in content
            and any(word in content for word in ("分布", "几个项目", "每个项目", "各项目", "项目的照片量"))
        ):
            return self.query_service.query_today_photo_project_distribution()

        if any(word in content for word in ("今天", "今日")) and any(
            word in content for word in ("照片", "工序照片", "上传")
        ):
            return self.query_service.query_today_photo_uploads()

        if "项目" in content and any(word in content for word in ("多少", "几个", "数量")):
            return self.query_service.query_active_project_count()

        return None
