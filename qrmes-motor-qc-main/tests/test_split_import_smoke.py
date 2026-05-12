import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_WEB = REPO_ROOT / 'app_web'
if str(APP_WEB) not in sys.path:
    sys.path.insert(0, str(APP_WEB))

def test_motor_qc_routes_importable():
    import motor_qc.routes  # noqa: F401
