from __future__ import annotations

from pathlib import Path
import os
import sys
from typing import Iterable


_DEFAULT_SIBLING_APP_WEB_DIRS = (
    ("qrmes-motor-qc", "app_web"),
    ("qrmes-finance-service", "app_web"),
)


def candidate_runtime_paths(repo_root: Path) -> list[Path]:
    repo_root = repo_root.resolve()
    candidates = [repo_root / "app_web", repo_root]
    for sibling in _DEFAULT_SIBLING_APP_WEB_DIRS:
        candidates.append(repo_root.parent.joinpath(*sibling))
    return candidates



def _dedupe_paths(paths: Iterable[Path | str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(Path(path).resolve()) if isinstance(path, Path) else str(path)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result



def build_pythonpath(repo_root: Path, existing_pythonpath: str | None = None) -> str:
    existing_entries = [entry for entry in (existing_pythonpath or "").split(os.pathsep) if entry]
    runtime_paths = [path for path in candidate_runtime_paths(repo_root) if path.exists()]
    return os.pathsep.join(_dedupe_paths([*runtime_paths, *existing_entries]))



def ensure_runtime_sys_path(repo_root: Path | None = None) -> list[str]:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    pythonpath = build_pythonpath(repo_root, existing_pythonpath=os.environ.get("PYTHONPATH"))
    inserted: list[str] = []
    for entry in reversed(pythonpath.split(os.pathsep)):
        if entry and entry not in sys.path:
            sys.path.insert(0, entry)
            inserted.append(entry)
    os.environ["PYTHONPATH"] = pythonpath
    return list(reversed(inserted))
