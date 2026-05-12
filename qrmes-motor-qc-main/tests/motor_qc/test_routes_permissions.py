import pytest
from pathlib import Path
import json
from datetime import datetime
import hashlib
import time


@pytest.fixture
def users_db(tmp_path):
    # Create isolated users db and two users.
    from app_web.user_management_service import UserManagementService
    from app_web.synology_auth_client import SynologyAuthService

    db_path = tmp_path / 'web_users.db'
    synology_auth = SynologyAuthService(base_url='https://example.invalid', verify_ssl=False)
    user_service = UserManagementService(Path(db_path), synology_auth)

    admin = user_service.get_or_create_user_by_smb('admin', is_admin=True)
    user = user_service.get_or_create_user_by_smb('user', is_admin=False)

    return str(db_path), admin, user


def test_motor_qc_projects_requires_run_qc_permission(app, users_db):
    db_path, _admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    client = app.test_client()

    # No login
    resp = client.get('/motor-qc/api/projects')
    assert resp.status_code == 401


def test_motor_qc_projects_forbidden_without_permission(app, users_db):
    db_path, _admin, user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = user.id

    resp = client.get('/motor-qc/api/projects')
    assert resp.status_code == 403


def test_motor_qc_projects_allowed_for_admin(app, users_db):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = admin.id

    resp = client.get('/motor-qc/api/projects')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'projects' in data


def test_motor_qc_review_page_allowed_for_admin(app, users_db, monkeypatch):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes
    monkeypatch.setattr(
        motor_routes,
        "_load_project_or_404",
        lambda _project_id: {"name": "测试项目", "project_id": "test-project"},
    )
    monkeypatch.setattr(
        motor_routes,
        "render_template",
        lambda template_name, **kwargs: f"{template_name}|{kwargs.get('project_id')}",
    )

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = admin.id

    resp = client.get('/motor-qc/review/test-project')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'motor_qc/review.html' in html
    assert 'test-project' in html


def test_motor_qc_tasks_page_without_project_allowed_for_admin(app, users_db, monkeypatch):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes
    monkeypatch.setattr(
        motor_routes,
        "_safe_load_project",
        lambda _project_id: {"name": "测试项目", "project_id": "test-project"},
    )
    monkeypatch.setattr(
        motor_routes,
        "render_template",
        lambda template_name, **kwargs: (
            f"{template_name}|{kwargs.get('project_id')}|{kwargs.get('project_name')}"
        ),
    )

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = admin.id

    resp = client.get('/motor-qc/tasks?project_id=test-project')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'motor_qc/tasks.html' in body
    assert 'test-project' in body


def test_motor_qc_projects_fallback_to_system_configs(app, users_db):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes
    base_dir = Path(motor_routes.DATA_DIR)
    motor_projects_dir = base_dir / 'motor_projects'
    projects_dir = base_dir / 'projects'
    motor_projects_dir.mkdir(parents=True, exist_ok=True)
    projects_dir.mkdir(parents=True, exist_ok=True)

    # 确保 motor_projects 为空，触发回退逻辑
    for f in motor_projects_dir.glob('*.json'):
        f.unlink()

    project_stem = 'fallback_project'
    (projects_dir / f'{project_stem}.json').write_text(
        json.dumps(
            {
                "projectName": "回退项目",
                "projectCode": "FB001",
                "productTypes": [
                    {
                        "typeName": "电机总成",
                        "modelNumber": "MODEL-001",
                        "processSteps": [
                            {
                                "id": "p1",
                                "name": "压装",
                                "order": 1,
                                "photoRequired": True,
                                "attachmentType": "photo",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = admin.id

    resp = client.get('/motor-qc/api/projects')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'projects' in data
    matched = [p for p in data['projects'] if p.get('project_id') == project_stem]
    assert matched, data
    assert matched[0].get('name') == '回退项目'
    assert len(matched[0].get('processes', [])) == 1


def test_motor_qc_projects_includes_system_project_without_processes(app, users_db):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes
    base_dir = Path(motor_routes.DATA_DIR)
    projects_dir = base_dir / 'projects'
    projects_dir.mkdir(parents=True, exist_ok=True)

    project_stem = 'fallback_project_without_processes'
    (projects_dir / f'{project_stem}.json').write_text(
        json.dumps(
            {
                "projectName": "无工序项目",
                "projectCode": "FB000",
                "productTypes": [],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = admin.id

    resp = client.get('/motor-qc/api/projects')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'projects' in data
    matched = [p for p in data['projects'] if p.get('project_id') == project_stem]
    assert matched, data
    assert matched[0].get('name') == '无工序项目'
    assert matched[0].get('processes') == []


def test_motor_qc_inspect_page_exists_for_valid_project(app, users_db, monkeypatch):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes

    monkeypatch.setattr(
        motor_routes.motor_project_manager,
        'load_project',
        lambda project_id: {"project_id": project_id, "name": "测试项目", "processes": []}
    )
    monkeypatch.setattr(
        motor_routes,
        'render_template',
        lambda *_args, **_kwargs: 'ok'
    )

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = admin.id

    resp = client.get('/motor-qc/inspect/test-project')
    assert resp.status_code == 200


def test_motor_qc_report_deduplicates_processes_by_serial_product_type(app, users_db, monkeypatch, tmp_path):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes

    project = {
        "project_id": "test-project",
        "name": "测试项目",
        "processes": [
            {"name": "转子动平衡", "order": 1, "photoRequired": True, "product_type": "电机"},
            {"name": "前端盖打胶", "order": 2, "photoRequired": True, "product_type": "电机"},
            {"name": "转子动平衡", "order": 1, "photoRequired": True, "product_type": "电机控制器"},
            {"name": "前端盖打胶", "order": 2, "photoRequired": True, "product_type": "电机控制器"},
        ],
    }

    photos_project_dir = tmp_path / "picture_project"
    serial_dir = photos_project_dir / "电机_PTYPEA" / "SN001"
    serial_dir.mkdir(parents=True, exist_ok=True)
    (serial_dir / "SN001_转子动平衡_20260217_101010.jpg").write_bytes(b"test")

    monkeypatch.setattr(motor_routes, "_load_project_or_404", lambda _project_id: project)
    monkeypatch.setattr(motor_routes, "_get_project_photo_dirs", lambda _project: [photos_project_dir])

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.get("/motor-qc/api/projects/test-project/report/SN001")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["success"] is True
    assert data["total_processes"] == 2
    assert data.get("product_type") == "电机"
    process_names = [row.get("process") for row in data.get("results", [])]
    assert process_names.count("转子动平衡") == 1
    assert process_names.count("前端盖打胶") == 1


def test_motor_qc_inspect_deduplicates_processes_without_product_type(app, users_db, monkeypatch, tmp_path):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes

    project = {
        "project_id": "test-project",
        "name": "测试项目",
        "processes": [
            {"name": "转子动平衡", "order": 1, "photoRequired": True, "product_type": "电机"},
            {"name": "前端盖打胶", "order": 2, "photoRequired": True, "product_type": "电机"},
            {"name": "转子动平衡", "order": 1, "photoRequired": True, "product_type": "电机控制器"},
            {"name": "前端盖打胶", "order": 2, "photoRequired": True, "product_type": "电机控制器"},
        ],
    }

    photos_project_dir = tmp_path / "picture_project"
    photos_project_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(motor_routes, "_load_project_or_404", lambda _project_id: project)
    monkeypatch.setattr(motor_routes, "_get_project_photo_dirs", lambda _project: [photos_project_dir])

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.post("/motor-qc/api/projects/test-project/inspect/SN001", json={})
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["success"] is True
    assert data["total_processes"] == 2
    process_names = [row.get("process") for row in data.get("results", [])]
    assert process_names.count("转子动平衡") == 1
    assert process_names.count("前端盖打胶") == 1


def test_motor_qc_motors_matches_sanitized_project_folder_name(app, users_db, monkeypatch, tmp_path):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes

    project = {
        "project_id": "test-project",
        "name": "徐工3.0-3.8吨153.6V叉车",
        "processes": [],
    }

    picture_root = tmp_path / "picture"
    serial_dir = (
        picture_root
        / "徐工3_0-3_8吨153_6V叉车_PCXuGFL25B"
        / "油泵电机总成_TZ1800"
        / "TZ180081A26010011"
    )
    serial_dir.mkdir(parents=True, exist_ok=True)
    (serial_dir / "TZ180081A26010011_点胶_20260217_111111.jpg").write_bytes(b"test")

    monkeypatch.setattr(motor_routes, "_load_project_or_404", lambda _project_id: project)
    monkeypatch.setattr(motor_routes, "DATA_DIR", tmp_path)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.get("/motor-qc/api/projects/test-project/motors")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["total"] == 1
    assert data["motors"][0]["serial_number"] == "TZ180081A26010011"


def test_motor_qc_report_includes_latest_photo_url(app, users_db, monkeypatch, tmp_path):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes

    project = {
        "project_id": "test-project",
        "name": "测试项目",
        "processes": [
            {"name": "点胶", "order": 1, "photoRequired": True, "product_type": "电机"},
        ],
    }

    data_dir = tmp_path / "data"
    photos_project_dir = data_dir / "picture" / "picture_project"
    serial_dir = photos_project_dir / "电机_A" / "SN001"
    serial_dir.mkdir(parents=True, exist_ok=True)
    (serial_dir / "SN001_点胶_20260217_111111.jpg").write_bytes(b"test")
    (serial_dir / "SN001_点胶_20260217_111112.jpg").write_bytes(b"test")

    monkeypatch.setattr(motor_routes, "DATA_DIR", data_dir)
    monkeypatch.setattr(motor_routes, "_load_project_or_404", lambda _project_id: project)
    monkeypatch.setattr(motor_routes, "_get_project_photo_dirs", lambda _project: [photos_project_dir])

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.get("/motor-qc/api/projects/test-project/report/SN001")
    assert resp.status_code == 200
    data = resp.get_json()
    rows = data.get("results") or []
    assert rows
    assert rows[0].get("latest_photo_url")
    assert isinstance(rows[0].get("photos"), list)
    assert len(rows[0]["photos"]) == 2
    assert all(item.get("url") for item in rows[0]["photos"])


def test_motor_qc_inspect_stream_returns_progress_events(app, users_db, monkeypatch, tmp_path):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes

    project = {
        "project_id": "test-project",
        "name": "测试项目",
        "processes": [
            {"name": "点胶", "order": 1, "photoRequired": True, "product_type": "电机"},
            {"name": "装配", "order": 2, "photoRequired": True, "product_type": "电机"},
        ],
    }

    data_dir = tmp_path / "data"
    photos_project_dir = data_dir / "picture" / "picture_project"
    serial_dir = photos_project_dir / "电机_A" / "SN001"
    serial_dir.mkdir(parents=True, exist_ok=True)
    (serial_dir / "SN001_点胶_20260217_111111.jpg").write_bytes(b"test")
    (serial_dir / "SN001_装配_20260217_111112.jpg").write_bytes(b"test")

    class _FakeInspectionService:
        def perform_inspection(self, project_code, process_step, photo_path, inspector_id):
            return {
                "status": "pass",
                "defects": [],
                "analysis": f"{process_step}通过",
                "confidence": 0.95,
            }

    monkeypatch.setattr(motor_routes, "DATA_DIR", data_dir)
    monkeypatch.setattr(motor_routes, "_load_project_or_404", lambda _project_id: project)
    monkeypatch.setattr(motor_routes, "_get_project_photo_dirs", lambda _project: [photos_project_dir])
    monkeypatch.setattr(motor_routes, "InspectionService", _FakeInspectionService)

    client = app.test_client()
    user_agent = "pytest-stream-client"
    nonce = "nonce-123"
    binding = hashlib.sha256(f"{admin.id}||{user_agent}".encode("utf-8")).hexdigest()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["motor_qc_stream_nonce_map"] = {
            "test-project": {
                "nonce": nonce,
                "issued_at": int(time.time()),
                "binding": binding,
            }
        }

    resp = client.get(
        f"/motor-qc/api/projects/test-project/inspect-stream/SN001?nonce={nonce}",
        headers={
            "User-Agent": user_agent,
            "Origin": "http://localhost",
            "Referer": "http://localhost/motor-qc/inspect/test-project",
        },
    )
    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    payload_text = resp.get_data(as_text=True)
    assert '"event": "start"' in payload_text
    assert '"event": "step_result"' in payload_text
    assert '"event": "done"' in payload_text
    assert '"photos"' in payload_text


def test_motor_qc_inspect_stream_requires_nonce(app, users_db, monkeypatch, tmp_path):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes

    project = {
        "project_id": "test-project",
        "name": "测试项目",
        "processes": [
            {"name": "点胶", "order": 1, "photoRequired": True, "product_type": "电机"},
        ],
    }

    photos_project_dir = tmp_path / "picture_project"
    serial_dir = photos_project_dir / "电机_A" / "SN001"
    serial_dir.mkdir(parents=True, exist_ok=True)
    (serial_dir / "SN001_点胶_20260217_111111.jpg").write_bytes(b"test")

    monkeypatch.setattr(motor_routes, "_load_project_or_404", lambda _project_id: project)
    monkeypatch.setattr(motor_routes, "_get_project_photo_dirs", lambda _project: [photos_project_dir])

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.get("/motor-qc/api/projects/test-project/inspect-stream/SN001")
    assert resp.status_code == 403
    data = resp.get_json()
    assert data["success"] is False


def test_motor_qc_report_maps_inferred_product_type_to_config_name(app, users_db, monkeypatch, tmp_path):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes

    project = {
        "project_id": "test-project",
        "name": "测试项目",
        "processes": [
            {"name": "铁芯压装", "order": 1, "photoRequired": True, "product_type": "油泵电机转子总成"},
            {"name": "插磁钢", "order": 2, "photoRequired": True, "product_type": "油泵电机转子总成"},
        ],
    }

    # 注意目录产品类型名是“油泵转子总成”，与配置“油泵电机转子总成”不完全一致
    photos_project_dir = tmp_path / "picture_project"
    serial_dir = photos_project_dir / "油泵转子总成_A" / "SN001"
    serial_dir.mkdir(parents=True, exist_ok=True)
    (serial_dir / "SN001_铁芯压装_20260217_111111.jpg").write_bytes(b"test")
    (serial_dir / "SN001_插磁钢_20260217_111112.jpg").write_bytes(b"test")

    monkeypatch.setattr(motor_routes, "_load_project_or_404", lambda _project_id: project)
    monkeypatch.setattr(motor_routes, "_get_project_photo_dirs", lambda _project: [photos_project_dir])

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.get("/motor-qc/api/projects/test-project/report/SN001")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["success"] is True
    assert data["total_processes"] == 2
    assert data.get("product_type") == "油泵电机转子总成"
    process_names = [row.get("process") for row in data.get("results", [])]
    assert process_names == ["铁芯压装", "插磁钢"]


def test_motor_qc_report_infers_product_type_by_process_overlap_when_counts_tie(app, users_db, monkeypatch, tmp_path):
    db_path, admin, _user = users_db
    app.config['WEB_USERS_DB_PATH'] = db_path

    from app_web.motor_qc import routes as motor_routes

    project = {
        "project_id": "test-project",
        "name": "测试项目",
        "processes": [
            {"name": "转子动平衡", "order": 1, "photoRequired": True, "product_type": "电机"},
            {"name": "前端盖打胶", "order": 2, "photoRequired": True, "product_type": "电机"},
            {"name": "点胶", "order": 1, "photoRequired": True, "product_type": "电机控制器"},
            {"name": "插磁钢", "order": 2, "photoRequired": True, "product_type": "电机控制器"},
        ],
    }

    photos_project_dir = tmp_path / "picture_project"
    serial_dir_motor = photos_project_dir / "电机_A" / "SN001"
    serial_dir_controller = photos_project_dir / "电机控制器_A" / "SN001"
    serial_dir_motor.mkdir(parents=True, exist_ok=True)
    serial_dir_controller.mkdir(parents=True, exist_ok=True)

    # 与“电机”配置工序不匹配，但计数参与 tie
    (serial_dir_motor / "SN001_无关工序1_20260217_111111.jpg").write_bytes(b"test")
    (serial_dir_motor / "SN001_无关工序2_20260217_111112.jpg").write_bytes(b"test")
    # 与“电机控制器”配置工序匹配
    (serial_dir_controller / "SN001_点胶_20260217_111113.jpg").write_bytes(b"test")
    (serial_dir_controller / "SN001_插磁钢_20260217_111114.jpg").write_bytes(b"test")

    monkeypatch.setattr(motor_routes, "_load_project_or_404", lambda _project_id: project)
    monkeypatch.setattr(motor_routes, "_get_project_photo_dirs", lambda _project: [photos_project_dir])

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.get("/motor-qc/api/projects/test-project/report/SN001")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["success"] is True
    assert data.get("product_type") == "电机控制器"
    assert data["total_processes"] == 2
    process_names = [row.get("process") for row in data.get("results", [])]
    assert process_names == ["点胶", "插磁钢"]


def test_motor_qc_experience_context_uses_bucket_precedence(app, users_db):
    db_path, admin, _user = users_db
    app.config["WEB_USERS_DB_PATH"] = db_path

    from app_web.motor_qc.models import (
        db,
        QCExperienceBucket,
        QCExperienceRule,
    )

    with app.app_context():
        bucket_global = QCExperienceBucket(
            scope_level="global",
            cooling_type="OIL",
            is_active=True,
        )
        bucket_cooling = QCExperienceBucket(
            scope_level="cooling",
            cooling_type="OIL",
            is_active=True,
        )
        bucket_platform = QCExperienceBucket(
            scope_level="platform",
            stator_platform="TZ180",
            cooling_type="OIL",
            is_active=True,
        )
        bucket_model = QCExperienceBucket(
            scope_level="model",
            model_code="TZ180-OIL-001",
            stator_platform="TZ180",
            cooling_type="OIL",
            is_active=True,
        )
        db.session.add_all([bucket_global, bucket_cooling, bucket_platform, bucket_model])
        db.session.flush()
        db.session.add(
            QCExperienceRule(
                bucket_id=bucket_model.id,
                process_name="点胶",
                rule_type="prompt",
                rule_payload={"text": "模型级规则"},
                confidence=0.9,
                is_active=True,
            )
        )
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.get(
        "/motor-qc/api/experience/context"
        "?project_id=test-project"
        "&serial=TZ180081A26010004"
        "&model_code=TZ180-OIL-001"
        "&cooling_type=OIL"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["context"]["stator_platform"] == "TZ180"
    assert data["context"]["cooling_type"] == "OIL"
    assert data["selected_bucket"]["scope_level"] == "model"
    assert data["selected_bucket"]["model_code"] == "TZ180-OIL-001"
    assert len(data["rules"]) == 1
    assert data["rules"][0]["process_name"] == "点胶"


def test_motor_qc_experience_context_model_scope_matches_platform_and_cooling(app, users_db):
    db_path, admin, _user = users_db
    app.config["WEB_USERS_DB_PATH"] = db_path

    from app_web.motor_qc.models import db, QCExperienceBucket

    with app.app_context():
        bucket_expected = QCExperienceBucket(
            scope_level="model",
            model_code="TZ-MODEL-SHARED",
            stator_platform="TZ180",
            cooling_type="OIL",
            is_active=True,
        )
        bucket_other = QCExperienceBucket(
            scope_level="model",
            model_code="TZ-MODEL-SHARED",
            stator_platform="TZ200",
            cooling_type="WATER",
            is_active=True,
        )
        db.session.add_all([bucket_expected, bucket_other])
        db.session.commit()
        expected_id = bucket_expected.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.get(
        "/motor-qc/api/experience/context"
        "?project_id=test-project"
        "&model_code=TZ-MODEL-SHARED"
        "&stator_platform=TZ180"
        "&cooling_type=OIL"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["selected_bucket"] is not None
    assert data["selected_bucket"]["id"] == expected_id
    assert data["selected_bucket"]["stator_platform"] == "TZ180"
    assert data["selected_bucket"]["cooling_type"] == "OIL"


def test_motor_qc_feedback_confirm_creates_record(app, users_db):
    db_path, admin, _user = users_db
    app.config["WEB_USERS_DB_PATH"] = db_path

    from app_web.motor_qc.models import db, QCExperienceBucket, QCFeedbackRecord

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.post(
        "/motor-qc/api/feedback/confirm",
        json={
            "project_id": "test-project",
            "serial_number": "TZ180081A26010004",
            "process_name": "点胶",
            "ai_result": "fail",
            "human_result": "pass",
            "defect_tags": ["胶量偏少"],
            "image_refs": [{"name": "a.jpg"}],
            "cooling_type": "OIL",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["record"]["serial_number"] == "TZ180081A26010004"
    assert data["bucket"]["scope_level"] == "platform"
    assert data["bucket"]["stator_platform"] == "TZ180"

    with app.app_context():
        bucket = db.session.query(QCExperienceBucket).filter_by(scope_level="platform").one()
        record = db.session.query(QCFeedbackRecord).filter_by(bucket_id=bucket.id).one()
        assert record.process_name == "点胶"
        assert record.human_result == "pass"


def test_motor_qc_experience_stats_returns_bucket_summary(app, users_db):
    db_path, admin, _user = users_db
    app.config["WEB_USERS_DB_PATH"] = db_path

    from app_web.motor_qc.models import db, QCExperienceBucket, QCFeedbackRecord

    with app.app_context():
        bucket = QCExperienceBucket(
            scope_level="platform",
            stator_platform="TZ180",
            cooling_type="OIL",
            is_active=True,
        )
        db.session.add(bucket)
        db.session.flush()
        db.session.add_all([
            QCFeedbackRecord(
                bucket_id=bucket.id,
                project_id="p1",
                serial_number="TZ180A",
                process_name="点胶",
                ai_result="pass",
                human_result="pass",
                defect_tags=[],
                image_refs=[],
                created_by="admin",
            ),
            QCFeedbackRecord(
                bucket_id=bucket.id,
                project_id="p1",
                serial_number="TZ180B",
                process_name="点胶",
                ai_result="fail",
                human_result="pass",
                defect_tags=["胶量偏少"],
                image_refs=[],
                created_by="admin",
            ),
        ])
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.get("/motor-qc/api/experience/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["total_feedback"] == 2
    assert data["total_buckets"] >= 1
    assert data["buckets"][0]["feedback_count"] >= 2


def test_motor_qc_feedback_without_context_goes_to_unknown_bucket(app, users_db):
    db_path, admin, _user = users_db
    app.config["WEB_USERS_DB_PATH"] = db_path

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.post(
        "/motor-qc/api/feedback/confirm",
        json={
            "project_id": "test-project",
            "serial_number": "SN-UNKNOWN-001",
            "process_name": "点胶",
            "ai_result": "pass",
            "human_result": "fail",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["success"] is True
    assert data["bucket"]["scope_level"] == "unknown"
    assert data["bucket"]["bucket_key"] == "unknown"


def test_motor_qc_promote_rejects_unknown_bucket(app, users_db):
    db_path, admin, _user = users_db
    app.config["WEB_USERS_DB_PATH"] = db_path

    from app_web.motor_qc.models import db, QCExperienceBucket

    with app.app_context():
        unknown_bucket = QCExperienceBucket(
            scope_level="unknown",
            bucket_key="unknown",
            is_active=True,
        )
        db.session.add(unknown_bucket)
        db.session.commit()
        unknown_id = unknown_bucket.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    resp = client.post(
        "/motor-qc/api/experience/promote",
        json={
            "from_bucket_id": unknown_id,
            "to_scope": "cooling",
        },
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "unknown" in data["error"]


def test_motor_qc_promote_is_idempotent_for_existing_rule(app, users_db):
    db_path, admin, _user = users_db
    app.config["WEB_USERS_DB_PATH"] = db_path

    from app_web.motor_qc.models import (
        db,
        QCExperienceBucket,
        QCExperienceRule,
        QCFeedbackRecord,
    )

    with app.app_context():
        from_bucket = QCExperienceBucket(
            scope_level="platform",
            stator_platform="TZ180",
            cooling_type="OIL",
            bucket_key="platform:TZ180:OIL",
            is_active=True,
        )
        db.session.add(from_bucket)
        db.session.flush()
        db.session.add(
            QCExperienceRule(
                bucket_id=from_bucket.id,
                process_name="点胶",
                rule_type="prompt",
                rule_payload={"text": "平台规则"},
                confidence=0.8,
                is_active=True,
            )
        )
        rows = []
        for idx in range(30):
            rows.append(
                QCFeedbackRecord(
                    bucket_id=from_bucket.id,
                    project_id="p1",
                    serial_number=f"TZ180{idx:03d}",
                    process_name="点胶",
                    ai_result="pass",
                    human_result="pass",
                    defect_tags=[],
                    image_refs=[],
                    created_by="admin",
                )
            )
        db.session.add_all(rows)
        db.session.commit()
        from_bucket_id = from_bucket.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    first = client.post(
        "/motor-qc/api/experience/promote",
        json={
            "from_bucket_id": from_bucket_id,
            "to_scope": "cooling",
        },
    )
    assert first.status_code == 200
    first_data = first.get_json()
    assert first_data["success"] is True
    assert first_data["cloned_rules"] == 1

    second = client.post(
        "/motor-qc/api/experience/promote",
        json={
            "from_bucket_id": from_bucket_id,
            "to_scope": "cooling",
        },
    )
    assert second.status_code == 200
    second_data = second.get_json()
    assert second_data["success"] is True
    assert second_data["cloned_rules"] == 0
    assert second_data["updated_rules"] >= 1

    with app.app_context():
        cooling_bucket = (
            db.session.query(QCExperienceBucket)
            .filter_by(scope_level="cooling", cooling_type="OIL")
            .first()
        )
        assert cooling_bucket is not None
        active_rules = (
            db.session.query(QCExperienceRule)
            .filter_by(
                bucket_id=cooling_bucket.id,
                process_name="点胶",
                rule_type="prompt",
                is_active=True,
            )
            .all()
        )
        assert len(active_rules) == 1


def test_motor_qc_promote_rejects_invalid_threshold_values(app, users_db):
    db_path, admin, _user = users_db
    app.config["WEB_USERS_DB_PATH"] = db_path

    from app_web.motor_qc.models import db, QCExperienceBucket

    with app.app_context():
        bucket = QCExperienceBucket(
            scope_level="platform",
            stator_platform="TZ180",
            cooling_type="OIL",
            is_active=True,
        )
        db.session.add(bucket)
        db.session.commit()
        from_bucket_id = bucket.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id

    bad_samples = client.post(
        "/motor-qc/api/experience/promote",
        json={
            "from_bucket_id": from_bucket_id,
            "to_scope": "cooling",
            "min_samples": "abc",
        },
    )
    assert bad_samples.status_code == 400

    bad_quality = client.post(
        "/motor-qc/api/experience/promote",
        json={
            "from_bucket_id": from_bucket_id,
            "to_scope": "cooling",
            "min_quality": "oops",
        },
    )
    assert bad_quality.status_code == 400


def test_qc_bucket_update_keeps_legacy_dedupe_key_when_semantic_unchanged(app):
    from app_web.motor_qc.models import db, QCExperienceBucket
    from sqlalchemy import text

    with app.app_context():
        now = datetime.utcnow()
        db.session.execute(
            text(
                "INSERT INTO qc_experience_buckets "
                "(scope_level, bucket_key, stator_platform, cooling_type, model_code, is_active, created_at, updated_at) "
                "VALUES (:scope_level, :bucket_key, :stator_platform, :cooling_type, :model_code, :is_active, :created_at, :updated_at)"
            ),
            {
                "scope_level": "global",
                "bucket_key": "global#9",
                "stator_platform": None,
                "cooling_type": None,
                "model_code": None,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        )
        db.session.commit()

        bucket = db.session.query(QCExperienceBucket).filter_by(bucket_key="global#9").one()
        bucket.is_active = False
        db.session.commit()

        refreshed = db.session.query(QCExperienceBucket).filter_by(id=bucket.id).one()
        assert refreshed.bucket_key == "global#9"
