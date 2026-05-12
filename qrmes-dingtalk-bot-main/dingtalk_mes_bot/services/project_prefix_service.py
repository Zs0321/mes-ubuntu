from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..models import PrefixMatch


def _normalize_serial_rule_value(value: str) -> str:
    normalized = str(value or "").strip()
    for old in ("-", "_", " "):
        normalized = normalized.replace(old, "")
    return normalized.lower()


@dataclass(slots=True)
class ProjectPrefixService:
    db_path: str

    def resolve_for_query(self, serial: str) -> tuple[str, tuple[PrefixMatch, ...]]:
        exact_matches = self.resolve(serial)
        if exact_matches:
            return serial, exact_matches

        compact_serial = _compact_serial_value(serial)
        normalized_serial = compact_serial.lower()
        if not normalized_serial or not self.db_path.strip():
            return serial, ()

        matches: list[tuple[str, PrefixMatch, int, int]] = []
        for project_name, product_type, prefix, normalized_prefix in self._iter_rules():
            canonical_prefix = _compact_serial_value(prefix)
            normalized_prefix = str(normalized_prefix or "").strip().lower()
            if not canonical_prefix or not normalized_prefix:
                continue
            fuzzy = _match_fuzzy_prefix(normalized_serial, normalized_prefix)
            if fuzzy is None:
                continue
            consumed, distance = fuzzy
            matches.append(
                (
                    canonical_prefix,
                    PrefixMatch(
                        project_name=str(project_name or "").strip(),
                        product_type=str(product_type or "").strip(),
                        prefix=str(prefix or "").strip(),
                        length=len(normalized_prefix),
                    ),
                    consumed,
                    distance,
                )
            )

        if not matches:
            return serial, ()

        matches.sort(key=lambda item: (item[3], -item[1].length, item[1].project_name, item[1].product_type))
        best_distance = matches[0][3]
        best_length = matches[0][1].length
        filtered = [item for item in matches if item[3] == best_distance and item[1].length == best_length]
        canonical_prefix, _, consumed, _ = filtered[0]
        corrected_serial = canonical_prefix + compact_serial[consumed:]

        deduped: list[PrefixMatch] = []
        seen: set[tuple[str, str]] = set()
        for _, match, _, _ in filtered:
            key = (match.project_name.lower(), match.product_type.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(match)
        return corrected_serial, tuple(deduped)

    def resolve(self, serial: str) -> tuple[PrefixMatch, ...]:
        normalized_serial = _normalize_serial_rule_value(serial)
        if not normalized_serial or not self.db_path.strip():
            return ()

        matches: list[PrefixMatch] = []
        for project_name, product_type, prefix, normalized_prefix in self._iter_rules():
            normalized_prefix = str(normalized_prefix or "").strip().lower()
            if not normalized_prefix:
                continue
            if normalized_serial.startswith(normalized_prefix):
                matches.append(
                    PrefixMatch(
                        project_name=str(project_name or "").strip(),
                        product_type=str(product_type or "").strip(),
                        prefix=str(prefix or "").strip(),
                        length=len(normalized_prefix),
                    )
                )

        if not matches:
            return ()
        max_length = max(item.length for item in matches)
        deduped: list[PrefixMatch] = []
        seen: set[tuple[str, str]] = set()
        for item in sorted(matches, key=lambda x: (x.project_name, x.product_type)):
            if item.length != max_length:
                continue
            key = (item.project_name.lower(), item.product_type.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return tuple(deduped)

    def _iter_rules(self):
        query = """
        SELECT p.project_name, pt.type_name, sr.rule_prefix, sr.normalized_prefix
        FROM serial_rules sr
        JOIN product_types pt ON pt.id = sr.product_type_id
        JOIN projects p ON p.id = pt.project_id
        """
        try:
            conn = sqlite3.connect(self.db_path)
        except Exception:
            return ()
        try:
            cur = conn.cursor()
            cur.execute(query)
            rows = cur.fetchall()
        except Exception:
            conn.close()
            return ()
        conn.close()
        return rows


def _compact_serial_value(value: str) -> str:
    compact = str(value or "").strip()
    for old in ("-", "_", " "):
        compact = compact.replace(old, "")
    return compact


def _match_fuzzy_prefix(normalized_serial: str, normalized_prefix: str) -> tuple[int, int] | None:
    if len(normalized_serial) < max(8, len(normalized_prefix) - 1):
        return None
    prefix_head = normalized_prefix[:6]
    for candidate_length in range(max(1, len(normalized_prefix) - 1), min(len(normalized_serial), len(normalized_prefix) + 1) + 1):
        candidate = normalized_serial[:candidate_length]
        if candidate[:6] != prefix_head[: min(6, len(candidate))]:
            continue
        distance = _edit_distance_at_most_one(candidate, normalized_prefix)
        if distance <= 1:
            return candidate_length, distance
    return None


def _edit_distance_at_most_one(left: str, right: str) -> int:
    if left == right:
        return 0
    if abs(len(left) - len(right)) > 1:
        return 2

    i = 0
    j = 0
    edits = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return edits
        if len(left) == len(right):
            i += 1
            j += 1
        elif len(left) > len(right):
            i += 1
        else:
            j += 1
    if i < len(left) or j < len(right):
        edits += 1
    return edits
