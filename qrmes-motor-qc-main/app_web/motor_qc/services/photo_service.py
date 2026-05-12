import os
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, BinaryIO, Union
from werkzeug.utils import secure_filename

class PhotoService:
    def __init__(self, base_path: Union[str, Path] = "uploads/motor_qc"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_dir_component(value: str, *, prefix: str) -> str:
        """
        Make a filesystem-safe directory segment while keeping human-readable names.
        Prevents path traversal by removing separators and dot segments.
        """
        raw = (value or "").strip()
        # Disallow any path separators.
        cleaned = re.sub(r"[\\\\/]+", "_", raw)
        cleaned = cleaned.replace("..", "_").strip().strip(".")
        cleaned = re.sub(r"\\s+", " ", cleaned).strip()
        # Keep it reasonably short.
        if len(cleaned) > 80:
            cleaned = cleaned[:80].rstrip()
        if not cleaned:
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12] if raw else "unknown"
            return f"{prefix}_{digest}"
        return cleaned

    def _resolve_under_base(self, *parts: str) -> Path:
        base = self.base_path.resolve()
        target = (self.base_path.joinpath(*parts)).resolve()
        try:
            target.relative_to(base)
        except Exception as exc:
            raise ValueError("Invalid path") from exc
        return target

    def save_photo(
        self,
        file: BinaryIO,
        project_code: str,
        process_step: str,
        filename: str
    ) -> Dict[str, Any]:
        """Save uploaded photo to organized directory structure"""

        if not project_code or not process_step:
            raise ValueError("Missing project_code or process_step")

        safe_project = self._safe_dir_component(project_code, prefix="project")
        safe_step = self._safe_dir_component(process_step, prefix="step")

        # Create directory structure: <base>/{project_code}/{process_step}/
        project_dir = self._resolve_under_base(safe_project, safe_step)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = secure_filename(filename)
        if not safe_filename:
            safe_filename = "upload.bin"
        unique_filename = f"{timestamp}_{safe_filename}"

        # Save file
        file_path = project_dir / unique_filename
        with open(file_path, 'wb') as f:
            f.write(file.read())

        return {
            "success": True,
            "photo_path": str(file_path),
            "filename": unique_filename
        }

    def get_photo(self, photo_path: str) -> bytes:
        """Retrieve photo by path"""
        with open(photo_path, 'rb') as f:
            return f.read()

    def delete_photo(self, photo_path: str) -> bool:
        """Delete photo file"""
        try:
            os.remove(photo_path)
            return True
        except FileNotFoundError:
            return False
