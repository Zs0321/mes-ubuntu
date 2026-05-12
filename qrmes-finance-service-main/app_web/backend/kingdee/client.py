from __future__ import annotations

import sys
from pathlib import Path

_SHARED_REPO_ROOT = Path(__file__).resolve().parents[4] / 'qrmes-kingdee-integration'
if _SHARED_REPO_ROOT.exists():
    shared_repo = str(_SHARED_REPO_ROOT)
    if shared_repo not in sys.path:
        sys.path.insert(0, shared_repo)

from qrmes_kingdee_integration.client.base import (  # type: ignore
    KingdeeApiError,
    KingdeeClient,
    KingdeeConfigError,
    KingdeeQuery,
    parse_response_status,
)

__all__ = [
    'KingdeeApiError',
    'KingdeeClient',
    'KingdeeConfigError',
    'KingdeeQuery',
    'parse_response_status',
]
