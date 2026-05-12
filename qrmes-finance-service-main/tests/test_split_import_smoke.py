import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_WEB = REPO_ROOT / 'app_web'
RUN_FILE = APP_WEB / 'run_finance_demo.py'
if str(APP_WEB) not in sys.path:
    sys.path.insert(0, str(APP_WEB))

def test_finance_demo_module_importable():
    import finance_demo  # noqa: F401


def test_run_finance_demo_exposes_login_route_for_local_session_bootstrap():
    text = RUN_FILE.read_text(encoding='utf-8')
    assert '/login' in text
    assert 'session["user"]' in text or "session['user']" in text


def test_finance_demo_base_template_exists_for_standalone_runtime():
    base_template = REPO_ROOT / 'app_web' / 'templates' / 'base.html'
    assert base_template.exists()
