from pathlib import Path

def test_shared_core_key_modules_exist():
    base = Path(__file__).resolve().parents[1] / 'qrmes_shared_core'
    assert (base / 'config.py').exists()
    assert (base / 'auth.py').exists()
    assert (base / 'permission_guard.py').exists()
