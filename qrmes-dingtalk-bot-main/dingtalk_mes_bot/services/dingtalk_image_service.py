from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..models import DownloadedImage


@dataclass(slots=True)
class DingTalkImageService:
    client_id: str
    client_secret: str
    robot_code: str
    timeout: float = 20.0

    def download_images(self, download_codes: tuple[str, ...]) -> list[DownloadedImage]:
        images: list[DownloadedImage] = []
        token = self._get_access_token()
        if not token:
            return images
        for download_code in download_codes:
            url = self._get_download_url(token, download_code)
            if not url:
                continue
            data, mime_type = self._download_file(url)
            if not data:
                continue
            images.append(
                DownloadedImage(
                    download_code=download_code,
                    mime_type=mime_type or mimetypes.guess_type(download_code)[0] or "image/jpeg",
                    data=data,
                )
            )
        return images

    def _get_access_token(self) -> str:
        payload = {"appKey": self.client_id, "appSecret": self.client_secret}
        req = urllib.request.Request(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return ""
        token = data.get("accessToken")
        return str(token).strip() if token else ""

    def _get_download_url(self, access_token: str, download_code: str) -> str:
        payload = {"robotCode": self.client_id, "downloadCode": download_code}
        req = urllib.request.Request(
            "https://api.dingtalk.com/v1.0/robot/messageFiles/download",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "*/*",
                "x-acs-dingtalk-access-token": access_token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return ""
        download_url = data.get("downloadUrl")
        return str(download_url).strip() if download_url else ""

    def _download_file(self, url: str) -> tuple[bytes, str]:
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
                mime_type = resp.headers.get_content_type()
                return data, mime_type
        except urllib.error.HTTPError:
            return b"", ""
        except Exception:
            return b"", ""
