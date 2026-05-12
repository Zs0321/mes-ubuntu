"""
日志文件管理器

用于将本地 logs 目录下的日志文件同步到 NAS 数据目录（DATA_DIR/log）。
实现目标：
- 提供给 mesapp.py 的 /api/logs/sync/* 端点调用
- 逻辑尽量独立，避免依赖 mesapp.py
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional


class LogFileManager:
    def __init__(
        self,
        *,
        local_logs_dir: Optional[Path] = None,
        nas_logs_dir: Optional[Path] = None,
    ):
        self.local_logs_dir = Path(local_logs_dir) if local_logs_dir else Path("logs")
        self.nas_logs_dir = Path(nas_logs_dir) if nas_logs_dir else Path("log")

    def _ensure_dirs(self) -> None:
        self.local_logs_dir.mkdir(parents=True, exist_ok=True)
        self.nas_logs_dir.mkdir(parents=True, exist_ok=True)

    def _iter_local_log_files(self) -> List[Path]:
        if not self.local_logs_dir.exists():
            return []
        # Keep behavior narrow: only sync .log files by default.
        return sorted([p for p in self.local_logs_dir.glob("*.log") if p.is_file()])

    def get_log_stats(self) -> Dict[str, Any]:
        self._ensure_dirs()

        def summarize(dir_path: Path) -> Dict[str, Any]:
            files = [p for p in dir_path.glob("*.log") if p.is_file()] if dir_path.exists() else []
            total_size = 0
            for p in files:
                try:
                    total_size += p.stat().st_size
                except OSError:
                    continue
            return {"count": len(files), "total_size_bytes": total_size}

        return {"local": summarize(self.local_logs_dir), "nas": summarize(self.nas_logs_dir)}

    def sync_log_to_nas(self, log_file: Path) -> bool:
        self._ensure_dirs()

        src = Path(log_file)
        if not src.exists() or not src.is_file():
            return False
        try:
            dst = self.nas_logs_dir / src.name
            shutil.copy2(src, dst)
            return True
        except Exception:
            return False

    def sync_all_logs_to_nas(self) -> Dict[str, Any]:
        self._ensure_dirs()

        files = self._iter_local_log_files()
        total = len(files)
        ok = 0
        failed: List[str] = []

        for f in files:
            if self.sync_log_to_nas(f):
                ok += 1
            else:
                failed.append(f.name)

        return {
            "success": len(failed) == 0,
            "message": f"同步完成：{ok}/{total}",
            "total_files": total,
            "success_files": ok,
            "failed_files": len(failed),
            "failed_list": failed,
        }
