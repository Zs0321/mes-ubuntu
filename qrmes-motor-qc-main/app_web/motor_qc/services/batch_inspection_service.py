from typing import List, Dict, Any, Generator
from .inspection_service import InspectionService

class BatchInspectionService:
    def __init__(self, config_manager=None):
        self.inspection_service = InspectionService(config_manager=config_manager)

    def process_batch(
        self,
        project_code: str,
        photos: List[Dict[str, str]],
        inspector_id: str
    ) -> Generator[Dict[str, Any], None, None]:
        """Process multiple photos and yield results as they complete"""

        total = len(photos)

        for index, photo in enumerate(photos, 1):
            try:
                # Perform inspection
                result = self.inspection_service.perform_inspection(
                    project_code=project_code,
                    process_step=photo["process_step"],
                    photo_path=photo["path"],
                    inspector_id=inspector_id
                )

                # Yield progress update
                yield {
                    "status": "completed",
                    "progress": index / total * 100,
                    "current": index,
                    "total": total,
                    "result": result
                }

            except Exception as e:
                yield {
                    "status": "error",
                    "progress": index / total * 100,
                    "current": index,
                    "total": total,
                    "error": str(e)
                }
