from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import IncomingMessage
from .dingtalk_doc_service import DingTalkDocService
from .mes_query_service import MesQueryService


@dataclass(slots=True)
class DocActionService:
    mes_query_service: MesQueryService
    doc_service: DingTalkDocService

    def maybe_handle(self, message: IncomingMessage) -> str | None:
        text = (message.text or '').strip()
        if not self._is_today_photo_doc_request(text):
            return None

        total_summary = self.mes_query_service.query_today_photo_uploads()
        distribution_summary = self.mes_query_service.query_today_photo_project_distribution()
        date_text = datetime.now().strftime('%Y-%m-%d')
        result = self.doc_service.create_or_get_daily_photo_doc(
            date_text=date_text,
            operator_id=message.sender_staff_id,
        )
        if not result.ok:
            return (
                f"今天工序照片统计已查询完成，但创建钉钉文档失败：{result.message}\n"
                f"{total_summary}\n"
                f"{distribution_summary}"
            )

        status_text = '已新建钉钉文档' if result.created else '已复用今日钉钉文档'
        lines = [f"{status_text}：{result.title}"]
        if result.url:
            lines.append(f"文档链接：{result.url}")
        lines.append(total_summary)
        lines.append(distribution_summary)
        lines.append('当前第一阶段会自动建文档并返回统计结果，文档正文自动写入后续再补。')
        return '\n'.join(lines)

    @staticmethod
    def _is_today_photo_doc_request(text: str) -> bool:
        if not text:
            return False
        return (
            any(word in text for word in ('今天', '今日'))
            and any(word in text for word in ('照片', '工序照片'))
            and any(word in text for word in ('文档', '日报', '统计到'))
        )
