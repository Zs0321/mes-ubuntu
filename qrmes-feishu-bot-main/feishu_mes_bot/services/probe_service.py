from __future__ import annotations

import os
import sqlite3
import urllib.error
import urllib.request
from typing import Dict, List

from .repository_catalog import RepositoryCatalog


class ProbeService:
    def __init__(self, workspace_root: str, repository_catalog: RepositoryCatalog):
        self.workspace_root = workspace_root
        self.repository_catalog = repository_catalog

    def collect(self, targets: List[str]) -> Dict[str, dict]:
        report = {}
        for target_key in targets:
            target = self.repository_catalog.get_target(target_key)
            repo_root = os.path.join(self.workspace_root, target.repo_dir)
            report[target_key] = {
                "health": [self._probe_health(label, url) for label, url in target.health_checks],
                "scripts": [self._probe_script(repo_root, path) for path in target.script_paths],
                "files": [self._probe_file(repo_root, path) for path in target.file_paths],
            }
        return report

    def _probe_health(self, label: str, url: str) -> dict:
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=1.5) as response:
                body = response.read(240).decode("utf-8", errors="ignore")
                return {"label": label, "url": url, "ok": True, "detail": body.strip() or "http ok"}
        except urllib.error.HTTPError as exc:
            detail = exc.read(240).decode("utf-8", errors="ignore")
            return {"label": label, "url": url, "ok": False, "detail": "HTTP %s %s" % (exc.code, detail.strip())}
        except Exception as exc:
            return {"label": label, "url": url, "ok": False, "detail": str(exc)}

    def _probe_script(self, repo_root: str, relative_path: str) -> dict:
        script_path = os.path.join(repo_root, relative_path)
        exists = os.path.exists(script_path)
        executable = os.access(script_path, os.X_OK) if exists else False
        return {"path": relative_path, "exists": exists, "executable": executable}

    def _probe_file(self, repo_root: str, relative_path: str) -> dict:
        file_path = os.path.join(repo_root, relative_path)
        exists = os.path.exists(file_path)
        entry = {"path": relative_path, "exists": exists}
        if not exists:
            return entry
        entry["size"] = os.path.getsize(file_path)
        if relative_path.endswith('.log'):
            entry["kind"] = "log"
            entry["tail"] = self._tail_text(file_path)
        elif relative_path.endswith('.db'):
            entry["kind"] = "sqlite"
            entry["tables"] = self._sqlite_summary(file_path)
        return entry

    def _tail_text(self, file_path: str, max_lines: int = 20) -> str:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as fh:
                lines = fh.readlines()
        except OSError:
            return ''
        return ''.join(lines[-max_lines:]).strip()

    def _sqlite_summary(self, file_path: str) -> dict:
        summary = {}
        try:
            conn = sqlite3.connect(file_path)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            table_names = [row[0] for row in cursor.fetchall()]
            for table_name in table_names[:20]:
                try:
                    count = conn.execute('SELECT COUNT(*) FROM "%s"' % table_name.replace('"', '""')).fetchone()[0]
                except sqlite3.DatabaseError:
                    count = -1
                summary[table_name] = count
            conn.close()
        except sqlite3.DatabaseError:
            summary['__error__'] = 'invalid sqlite database'
        return summary
