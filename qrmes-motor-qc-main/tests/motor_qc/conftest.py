import pytest
import sys
from unittest.mock import MagicMock, patch
from flask import Flask
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_WEB_DIR = REPO_ROOT / "app_web"


@pytest.fixture(scope="function", autouse=True)
def _isolate_external_deps(monkeypatch, tmp_path):
    """
    Motor QC tests used to clobber sys.modules['config'] with a MagicMock, which
    breaks the rest of the test suite that imports config.redis_config/config.secrets.
    Keep the real config package and only patch the config object fields we need.
    """
    if str(APP_WEB_DIR) not in sys.path:
        sys.path.insert(0, str(APP_WEB_DIR))

    # Stub optional third-party deps (Motor QC Claude client, etc).
    monkeypatch.setitem(sys.modules, "anthropic", MagicMock())

    # Patch config.config attributes in-place (avoid rebinding "from config import config").
    import config as config_pkg  # type: ignore

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    cfg = getattr(config_pkg, "config", None)
    if cfg is None:
        raise RuntimeError("config.config failed to load in tests")

    # Config uses @property getters backed by cfg._config. Patch that dict instead of properties.
    cfg_map = dict(getattr(cfg, "_config", {}) or {})
    cfg_map.update(
        {
            "nas_local_base_path": str(data_dir),
            "synology_api_url": "https://example.invalid",
            "synology_api_verify_ssl": False,
            "use_webdav": False,
        }
    )
    monkeypatch.setattr(cfg, "_config", cfg_map, raising=False)

    # Ensure Motor QC module-level globals follow the patched data dir even if imported earlier.
    try:
        from app_web.motor_qc import routes as motor_routes
        from app_web.motor_qc.config import MotorProjectManager
        from app_web.motor_qc.models import MotorQCDatabase

        monkeypatch.setattr(motor_routes, "DATA_DIR", data_dir, raising=False)
        monkeypatch.setattr(motor_routes, "motor_project_manager", MotorProjectManager(data_dir), raising=False)
        monkeypatch.setattr(motor_routes, "motor_qc_db", MotorQCDatabase(data_dir / "motor_qc.db"), raising=False)
    except Exception:
        # Some tests may import config without importing motor_qc; ignore.
        pass
    yield

@pytest.fixture(scope='function')
def mock_vision_service():
    """Mock vision service for testing"""
    mock_service = MagicMock()
    mock_service.analyze_image.return_value = {
        "analysis": "测试分析结果",
        "defects": ["测试缺陷1", "测试缺陷2"]
    }
    return mock_service

@pytest.fixture(scope='function', autouse=True)
def patch_vision_service(mock_vision_service):
    """Automatically patch vision service for all tests"""
    with patch('app_web.motor_qc.services.vision_api.get_vision_service', return_value=mock_vision_service):
        yield

@pytest.fixture(scope='function')
def app(tmp_path):
    """Create Flask app for testing"""
    from app_web.motor_qc.models import db
    from app_web.motor_qc import motor_qc_bp

    from app_web.synology_auth_client import SynologyAuthService
    from app_web.user_management_service import UserManagementService

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'test-secret'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WEB_USERS_DB_PATH'] = str(tmp_path / 'web_users.db')

    # Create users for permission checks (web:run_qc is ADMIN-only by default).
    synology_auth = SynologyAuthService(base_url='https://example.invalid', verify_ssl=False)
    user_service = UserManagementService(Path(app.config['WEB_USERS_DB_PATH']), synology_auth)
    admin_user = user_service.get_or_create_user_by_smb('admin', is_admin=True)
    normal_user = user_service.get_or_create_user_by_smb('user', is_admin=False)
    app.testing_users = {'admin': admin_user, 'user': normal_user}

    db.init_app(app)
    app.register_blueprint(motor_qc_bp)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client_admin(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = app.testing_users['admin'].id
        sess['username'] = app.testing_users['admin'].synology_username
    return client


@pytest.fixture(scope='function')
def client_user(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = app.testing_users['user'].id
        sess['username'] = app.testing_users['user'].synology_username
    return client

@pytest.fixture(scope='function')
def db_session(app):
    """Create database session for testing"""
    from app_web.motor_qc.models import db

    with app.app_context():
        yield db.session
