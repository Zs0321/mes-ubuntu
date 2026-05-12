from __future__ import annotations

import requests
from flask import Blueprint, jsonify, request

from qrmes_shared_core.config import config

kingdee_local_db_bp = Blueprint('kingdee_local_db_proxy_api', __name__, url_prefix='/api/kingdee-local-db')

_DATASET_PATH_MAP = {
    'material': 'material',
    'bom': 'bom',
    'purchase_order': 'purchase_order',
    'production_order': 'production_order',
}


class KingdeeLocalDbClient:
    def __init__(self, base_url: str, session: requests.Session | None = None, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.session = session or requests.Session()
        self.timeout = timeout

    def list_dataset(self, dataset: str) -> dict:
        path = _normalize_dataset_path(dataset)
        response = self.session.get(f'{self.base_url}/api/local-db/{path}', timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def update_dataset_object(self, dataset: str, business_key: str, payload: dict) -> dict:
        path = _normalize_dataset_path(dataset)
        response = self.session.post(f'{self.base_url}/api/local-db/{path}/{business_key}', json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


def _normalize_dataset_path(dataset: str) -> str:
    normalized = (dataset or '').strip()
    if normalized in _DATASET_PATH_MAP:
        return _DATASET_PATH_MAP[normalized]
    raise KeyError(f'unsupported dataset: {dataset}')


def create_kingdee_local_db_client() -> KingdeeLocalDbClient:
    base_url = str(config.get('kingdee_local_db_api_base', 'http://127.0.0.1:9010')).strip() or 'http://127.0.0.1:9010'
    timeout = int(config.get('kingdee_local_db_api_timeout_secs', 30) or 30)
    return KingdeeLocalDbClient(base_url=base_url, timeout=timeout)


@kingdee_local_db_bp.get('/<dataset>')
def proxy_list_dataset(dataset: str):
    try:
        result = create_kingdee_local_db_client().list_dataset(dataset)
    except KeyError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    return jsonify(result)


@kingdee_local_db_bp.post('/<dataset>/<business_key>')
def proxy_update_dataset(dataset: str, business_key: str):
    payload = request.get_json(silent=True) or {}
    try:
        result = create_kingdee_local_db_client().update_dataset_object(dataset, business_key, payload)
    except KeyError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    return jsonify(result)
