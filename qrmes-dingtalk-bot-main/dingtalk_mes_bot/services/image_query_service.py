from __future__ import annotations

from dataclasses import dataclass

from ..models import SerialQueryResult, VisionRecognitionResult


@dataclass(slots=True)
class ImageQueryService:
    image_downloader: object
    vision_service: object
    prefix_service: object
    mes_query_service: object

    def reply_for_images(self, download_codes: tuple[str, ...], user_text: str = "") -> str:
        images = self.image_downloader.download_images(download_codes)
        if not images:
            return "\u56fe\u7247\u4e0b\u8f7d\u5931\u8d25\uff0c\u6682\u65f6\u65e0\u6cd5\u8bc6\u522b\u4e8c\u7ef4\u7801\u6807\u7b7e\u3002\u8bf7\u7a0d\u540e\u91cd\u8bd5\uff0c\u6216\u8865\u53d1\u6e05\u6670\u56fe\u7247\u3002"

        recognition = self.vision_service.recognize(images, user_text=user_text)
        serials = tuple(dict.fromkeys(recognition.serial_numbers))
        if not serials:
            return self._build_no_serial_reply(recognition)

        kept_results: list[tuple[str, SerialQueryResult]] = []
        ignored_values: list[str] = []
        for serial in serials:
            query_serial, prefix_matches = self.prefix_service.resolve_for_query(serial)
            result = self.mes_query_service.query_serial_database(query_serial, prefix_matches=prefix_matches)
            if not result.found and not result.prefix_matches:
                ignored_values.append(serial)
                continue
            kept_results.append((serial, result))

        if not kept_results:
            return self._build_no_serial_reply(recognition)

        return self._build_serial_reply(recognition, kept_results, tuple(ignored_values))

    @staticmethod
    def _build_no_serial_reply(recognition: VisionRecognitionResult) -> str:
        parts = [
            "\u6211\u5df2\u7ecf\u8bc6\u522b\u4e86\u8fd9\u5f20\u6807\u7b7e\u56fe\uff0c\u4f46\u6682\u65f6\u6ca1\u6709\u63d0\u53d6\u5230\u53ef\u67e5\u8be2\u7684\u5b8c\u6574\u5e8f\u5217\u53f7\u3002"
        ]
        if recognition.product_type_names:
            parts.append(
                "\u8bc6\u522b\u5230\u7684\u4ea7\u54c1\u7c7b\u578b\uff1a" + "\u3001".join(recognition.product_type_names)
            )
        if recognition.raw_qr_texts:
            parts.append(
                "\u8bc6\u522b\u5230\u7684\u4e8c\u7ef4\u7801\u6587\u672c\uff1a" + "\uff1b".join(recognition.raw_qr_texts)
            )
        if recognition.notes:
            parts.append("\u8865\u5145\u8bf4\u660e\uff1a" + "\uff1b".join(recognition.notes))
        return "\n".join(parts)

    @staticmethod
    def _build_serial_reply(
        recognition: VisionRecognitionResult,
        results: list[tuple[str, SerialQueryResult]],
        ignored_values: tuple[str, ...] = (),
    ) -> str:
        lines = [f"\u8bc6\u522b\u5230 {len(results)} \u4e2a\u5e8f\u5217\u53f7\uff0c\u5df2\u6309\u5e8f\u9010\u4e2a\u67e5\u8be2\uff1a"]
        if recognition.product_type_names:
            lines.append(
                "\u8bc6\u522b\u5230\u7684\u4ea7\u54c1\u7c7b\u578b\uff1a" + "\u3001".join(recognition.product_type_names)
            )
        for index, (original_serial, result) in enumerate(results, 1):
            if original_serial != result.serial:
                lines.append(
                    f"{index}. \u5e8f\u5217\u53f7\uff1a{result.serial}\uff08\u8bc6\u522b\u539f\u6587\uff1a{original_serial}\uff09"
                )
            else:
                lines.append(f"{index}. \u5e8f\u5217\u53f7\uff1a{result.serial}")
            if result.project_name or result.product_type:
                lines.append(
                    f"   \u524d\u7f00\u547d\u4e2d\uff1a{result.project_name or '-'} / {result.product_type or '-'}"
                )
            elif result.prefix_matches:
                top = result.prefix_matches[0]
                lines.append(f"   \u524d\u7f00\u547d\u4e2d\uff1a{top.project_name or '-'} / {top.product_type or '-'}")
            else:
                lines.append("   \u524d\u7f00\u547d\u4e2d\uff1a\u672a\u547d\u4e2d\u4ea7\u54c1\u914d\u7f6e")
            status_text = '\u5df2\u627e\u5230\u8bb0\u5f55' if result.found else '\u672a\u627e\u5230\u8bb0\u5f55'
            lines.append(f"   \u6570\u636e\u5e93\u7ed3\u679c\uff1a{status_text}")
            if result.quality_summary:
                lines.append(f"   \u8d28\u91cf\u72b6\u6001\uff1a{result.quality_summary}")
            if result.process_summary:
                lines.append(f"   \u5de5\u5e8f\u6458\u8981\uff1a{result.process_summary}")
        if recognition.notes:
            lines.append("\u8865\u5145\u8bf4\u660e\uff1a" + "\uff1b".join(recognition.notes))
        return "\n".join(lines)
