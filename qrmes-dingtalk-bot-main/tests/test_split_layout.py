from pathlib import Path

def test_bot_layout_has_entrypoints():
    base = Path(__file__).resolve().parents[1]
    assert (base / 'dingtalk_mes_bot' / 'bot_app.py').exists()
    assert (base / 'run.sh').exists()
