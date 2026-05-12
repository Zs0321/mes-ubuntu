"""Project name normalization helpers.

This module centralizes project name canonicalization so the app treats
visually-identical names as the same logical project.
"""

from __future__ import annotations

import unicodedata
from typing import Iterable, List, Optional


# Common invisible characters that often come from copy/paste.
_INVISIBLE_CHARS = {
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\ufeff",  # zero width no-break space / BOM
    "\u2060",  # word joiner
}


def normalize_project_name(name: str) -> str:
    """Normalize a project name for display/storage."""
    if not isinstance(name, str):
        return ""
    value = unicodedata.normalize("NFKC", name)
    value = "".join(ch for ch in value if ch not in _INVISIBLE_CHARS)
    return value.strip()


def project_name_key(name: str) -> str:
    """Normalize a project name for equality checks."""
    normalized = normalize_project_name(name)
    normalized = "".join(ch for ch in normalized if not ch.isspace())
    return normalized.casefold()


def dedupe_project_names(projects: Iterable[str]) -> List[str]:
    """Deduplicate project names by normalized key and keep latest occurrence."""
    items = list(projects or [])
    deduped_reversed: List[str] = []
    seen = set()
    for item in reversed(items):
        normalized = normalize_project_name(item)
        if not normalized:
            continue
        key = project_name_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        deduped_reversed.append(normalized)
    deduped_reversed.reverse()
    return deduped_reversed


def resolve_project_config_stem(project_name: str, candidates: Iterable[str]) -> Optional[str]:
    """Resolve the best-matching config stem from candidate names.

    Candidates may be bare stems or file names ending with `.json`.
    Returns normalized project name as fallback when no match is found.
    """
    normalized = normalize_project_name(project_name)
    if not normalized:
        return None

    stems: List[str] = []
    for item in candidates or []:
        text = str(item or "").strip()
        if not text:
            continue
        lower = text.casefold()
        if lower.endswith(".json"):
            stem = text[:-5].strip()
        else:
            stem = text
        if stem:
            stems.append(stem)

    for stem in stems:
        if normalize_project_name(stem) == normalized:
            return stem

    target_key = project_name_key(normalized)
    for stem in stems:
        if project_name_key(stem) == target_key:
            return stem

    return normalized
