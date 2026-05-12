from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_WEB_ROOT = REPO_ROOT / 'app_web'
for candidate in (REPO_ROOT, APP_WEB_ROOT):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
