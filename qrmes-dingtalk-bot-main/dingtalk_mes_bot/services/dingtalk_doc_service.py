from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class DocumentCreateResult:
    ok: bool
    created: bool = False
    title: str = ''
    url: str = ''
    doc_id: str = ''
    message: str = ''


@dataclass(frozen=True, slots=True)
class NodeQueryResult:
    ok: bool
    operator_union_id: str = ''
    node_id: str = ''
    node_type: str = ''
    payload: dict[str, Any] | None = None
    message: str = ''


class DingTalkDocService:
    def __init__(
        self,
        *,
        api_base_url: str,
        app_key: str,
        app_secret: str,
        workspace_id: str,
        parent_node_id: str = '',
        default_operator_id: str = '',
        state_path: str = '',
        timeout: float = 20.0,
    ) -> None:
        self.api_base_url = api_base_url.rstrip('/')
        self.app_key = app_key.strip()
        self.app_secret = app_secret.strip()
        self.workspace_id = workspace_id.strip()
        self.parent_node_id = parent_node_id.strip()
        self.default_operator_id = default_operator_id.strip()
        self.state_path = Path(state_path) if state_path else None
        self.timeout = timeout
        self._access_token = ''
        self._access_token_expires_at = 0.0
        self._union_id_cache: dict[str, str] = {}

    def create_or_get_daily_photo_doc(self, *, date_text: str, operator_id: str = '') -> DocumentCreateResult:
        if not self.workspace_id:
            return DocumentCreateResult(ok=False, message='未配置 DINGTALK_BOT_DOC_WORKSPACE_ID')

        final_operator = (operator_id or self.default_operator_id).strip()
        union_operator = self.resolve_union_id_from_staff_id(final_operator) or final_operator
        if not final_operator:
            return DocumentCreateResult(ok=False, message='未配置文档操作人，请设置 DINGTALK_BOT_DOC_OPERATOR_ID')

        title = f'MES工序照片统计 {date_text}'
        state = self._load_state()
        daily = state.get(date_text) if isinstance(state, dict) else None
        if isinstance(daily, dict):
            return DocumentCreateResult(
                ok=True,
                created=False,
                title=str(daily.get('title') or title),
                url=str(daily.get('url') or ''),
                doc_id=str(daily.get('docId') or ''),
            )

        token = self._get_access_token()
        if not token:
            return DocumentCreateResult(ok=False, message='获取钉钉 access token 失败')

        body: dict[str, Any] = {
            'name': title,
            'docType': 'DOC',
            'operatorId': union_operator,
        }
        if self.parent_node_id:
            body['parentNodeId'] = self.parent_node_id

        req = urllib.request.Request(
            f"{self.api_base_url}/v1.0/doc/workspaces/{self.workspace_id}/docs",
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={
                'Content-Type': 'application/json; charset=utf-8',
                'x-acs-dingtalk-access-token': token,
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            return DocumentCreateResult(ok=False, message=f'创建文档失败：HTTP {exc.code} {detail}')
        except Exception as exc:
            return DocumentCreateResult(ok=False, message=f'创建文档失败：{exc}')

        try:
            data = json.loads(payload) if payload else {}
        except Exception:
            data = {}

        url = str(
            data.get('url')
            or data.get('docUrl')
            or data.get('openUrl')
            or data.get('link')
            or ''
        )
        doc_id = str(
            data.get('docId')
            or data.get('docKey')
            or data.get('nodeId')
            or data.get('dentryUuid')
            or ''
        )
        self._save_state(date_text, {'title': title, 'url': url, 'docId': doc_id})
        return DocumentCreateResult(ok=True, created=True, title=title, url=url, doc_id=doc_id)

    def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._access_token_expires_at:
            return self._access_token

        body = {
            'appKey': self.app_key,
            'appSecret': self.app_secret,
        }
        req = urllib.request.Request(
            f'{self.api_base_url}/v1.0/oauth2/accessToken',
            data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=utf-8'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode('utf-8', errors='replace')
        except Exception:
            return ''

        try:
            data = json.loads(payload)
        except Exception:
            return ''

        token = str(data.get('accessToken') or data.get('access_token') or '').strip()
        expires_in = int(data.get('expireIn') or data.get('expires_in') or 7200)
        if token:
            self._access_token = token
            self._access_token_expires_at = now + max(expires_in - 60, 60)
        return token

    def resolve_union_id_from_staff_id(self, staff_id: str) -> str:
        final_staff_id = (staff_id or '').strip()
        if not final_staff_id:
            return ''
        cached = self._union_id_cache.get(final_staff_id)
        if cached:
            return cached

        token = self._get_access_token()
        if not token:
            return ''

        body = {
            'userid': final_staff_id,
            'language': 'zh_CN',
        }
        req = urllib.request.Request(
            f'https://oapi.dingtalk.com/topapi/v2/user/get?access_token={urllib.parse.quote(token)}',
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=utf-8'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode('utf-8', errors='replace')
        except Exception:
            return ''

        try:
            data = json.loads(payload) if payload else {}
        except Exception:
            return ''

        result = data.get('result') if isinstance(data, dict) else {}
        union_id = str(
            (result or {}).get('unionid')
            or (result or {}).get('unionId')
            or data.get('unionid')
            or data.get('unionId')
            or ''
        ).strip()
        if union_id:
            self._union_id_cache[final_staff_id] = union_id
        return union_id

    def query_node_by_url(self, url: str, *, operator_id: str = '') -> NodeQueryResult:
        final_url = (url or '').strip()
        if not final_url:
            return NodeQueryResult(ok=False, message='缺少钉钉节点链接')

        raw_operator = (operator_id or self.default_operator_id).strip()
        if not raw_operator:
            return NodeQueryResult(ok=False, message='缺少钉钉操作人')

        operator_union_id = self.resolve_union_id_from_staff_id(raw_operator)
        if not operator_union_id:
            return NodeQueryResult(ok=False, message='无法将 staffId 转成 unionId')

        token = self._get_access_token()
        if not token:
            return NodeQueryResult(ok=False, operator_union_id=operator_union_id, message='获取钉钉 access token 失败')

        req = urllib.request.Request(
            f'{self.api_base_url}/v2.0/wiki/nodes/queryByUrl?operatorId={urllib.parse.quote(operator_union_id)}',
            data=json.dumps({'url': final_url}, ensure_ascii=False).encode('utf-8'),
            headers={
                'Content-Type': 'application/json; charset=utf-8',
                'x-acs-dingtalk-access-token': token,
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            return NodeQueryResult(
                ok=False,
                operator_union_id=operator_union_id,
                message=f'查询节点失败：HTTP {exc.code} {detail}',
            )
        except Exception as exc:
            return NodeQueryResult(
                ok=False,
                operator_union_id=operator_union_id,
                message=f'查询节点失败：{exc}',
            )

        try:
            data = json.loads(payload) if payload else {}
        except Exception:
            data = {}

        node_payload = data.get('node') if isinstance(data, dict) and isinstance(data.get('node'), dict) else {}
        return NodeQueryResult(
            ok=True,
            operator_union_id=operator_union_id,
            node_id=str(data.get('nodeId') or data.get('id') or node_payload.get('nodeId') or ''),
            node_type=str(data.get('nodeType') or data.get('type') or node_payload.get('type') or ''),
            payload=data if isinstance(data, dict) else None,
        )

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path or not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _save_state(self, date_text: str, payload: dict[str, Any]) -> None:
        if not self.state_path:
            return
        state = self._load_state()
        state[date_text] = payload
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
