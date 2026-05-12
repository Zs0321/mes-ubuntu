from __future__ import annotations

import json
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DingTalkMesUserResolver:
    app_key: str
    app_secret: str
    web_users_db_path: str
    user_aliases_path: str = ""
    timeout: float = 15.0
    api_base_url: str = "https://api.dingtalk.com"
    _access_token: str = field(init=False, default="")
    _access_token_expires_at: float = field(init=False, default=0.0)

    def resolve_mes_username(self, sender_staff_id: str, sender_nick: str) -> dict:
        profile = self._fetch_dingtalk_profile(sender_staff_id)
        real_name = str(profile.get("name") or "").strip()
        effective_name = real_name or str(sender_nick or "").strip()

        if not effective_name:
            return {
                "status": "not_found",
                "name": "",
                "candidates": [],
            }

        exact_candidates = self._dedupe_preserve_order(
            self._find_alias_matches(effective_name) + self._find_users_by_display_name(effective_name, fuzzy=False)
        )
        if len(exact_candidates) == 1:
            username = exact_candidates[0]
            source = "real_name_alias" if username in self._find_alias_matches(effective_name) else "real_name_exact"
            return {
                "status": "matched",
                "username": username,
                "source": source,
                "name": effective_name,
            }
        if len(exact_candidates) > 1:
            return {
                "status": "multiple_exact",
                "name": effective_name,
                "candidates": exact_candidates,
            }

        fuzzy_candidates = self._find_users_by_display_name(effective_name, fuzzy=True)
        if fuzzy_candidates:
            return {
                "status": "fuzzy_candidates",
                "name": effective_name,
                "candidates": fuzzy_candidates,
            }

        return {
            "status": "not_found",
            "name": effective_name,
            "candidates": [],
        }

    def _find_alias_matches(self, real_name: str) -> list[str]:
        final_name = str(real_name or "").strip()
        if not final_name or not self.user_aliases_path.strip():
            return []

        try:
            payload = json.loads(Path(self.user_aliases_path).read_text(encoding="utf-8"))
        except Exception:
            return []

        raw_value = payload.get(final_name)
        if isinstance(raw_value, str):
            candidates = [raw_value]
        elif isinstance(raw_value, list):
            candidates = [str(item or "").strip() for item in raw_value]
        else:
            candidates = []

        return self._filter_active_usernames(candidates)

    def _filter_active_usernames(self, usernames: list[str]) -> list[str]:
        deduped = self._dedupe_preserve_order([str(item or "").strip() for item in usernames if str(item or "").strip()])
        if not deduped or not self.web_users_db_path.strip():
            return []

        placeholders = ",".join("?" for _ in deduped)
        try:
            conn = sqlite3.connect(self.web_users_db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT synology_username
                FROM users
                WHERE coalesce(is_active, 1) = 1
                  AND lower(synology_username) IN ({placeholders})
                """,
                tuple(item.lower() for item in deduped),
            ).fetchall()
            conn.close()
        except Exception:
            return []

        matched = {str(row["synology_username"] or "").strip().lower(): str(row["synology_username"] or "").strip() for row in rows}
        return [matched[item.lower()] for item in deduped if item.lower() in matched]

    def _fetch_dingtalk_profile(self, sender_staff_id: str) -> dict:
        final_staff_id = str(sender_staff_id or "").strip()
        if not final_staff_id:
            return {}

        token = self._get_access_token()
        if not token:
            return {}

        body = {
            "userid": final_staff_id,
            "language": "zh_CN",
        }
        req = urllib.request.Request(
            f"https://oapi.dingtalk.com/topapi/v2/user/get?access_token={urllib.parse.quote(token)}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return {}

        try:
            data = json.loads(payload) if payload else {}
        except Exception:
            return {}
        result = data.get("result") if isinstance(data, dict) and isinstance(data.get("result"), dict) else {}
        return result if isinstance(result, dict) else {}

    def _find_users_by_display_name(self, display_name: str, *, fuzzy: bool) -> list[str]:
        final_name = str(display_name or "").strip()
        if not final_name or not self.web_users_db_path.strip():
            return []

        try:
            conn = sqlite3.connect(self.web_users_db_path)
            conn.row_factory = sqlite3.Row
            if fuzzy:
                cursor = conn.execute(
                    """
                    SELECT synology_username
                    FROM users
                    WHERE coalesce(is_active, 1) = 1
                      AND lower(coalesce(display_name, '')) LIKE lower(?)
                    ORDER BY synology_username
                    """,
                    (f"%{final_name}%",),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT synology_username
                    FROM users
                    WHERE coalesce(is_active, 1) = 1
                      AND lower(coalesce(display_name, '')) = lower(?)
                    ORDER BY synology_username
                    """,
                    (final_name,),
                )
            rows = [str(row["synology_username"] or "").strip() for row in cursor.fetchall()]
            conn.close()
        except Exception:
            return []

        return self._dedupe_preserve_order(rows)

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expires_at:
            return self._access_token

        body = {
            "appKey": self.app_key,
            "appSecret": self.app_secret,
        }
        req = urllib.request.Request(
            f"{self.api_base_url.rstrip('/')}/v1.0/oauth2/accessToken",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

        try:
            data = json.loads(payload) if payload else {}
        except Exception:
            return ""

        token = str(data.get("accessToken") or data.get("access_token") or "").strip()
        expires_in = int(data.get("expireIn") or data.get("expires_in") or 7200)
        if token:
            self._access_token = token
            self._access_token_expires_at = now + max(expires_in - 60, 60)
        return token

    @staticmethod
    def _dedupe_preserve_order(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            final_value = str(value or "").strip()
            if not final_value:
                continue
            key = final_value.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(final_value)
        return result
