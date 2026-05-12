from io import BytesIO


def test_upload_returns_task_id_and_pending_status(app, client_admin):
    from app_web.motor_qc.models import db, QCProcessTask

    response = client_admin.post(
        "/motor-qc/api/photos/upload",
        data={
            "file": (BytesIO(b"fake image"), "SN001_点胶_20260218_101010.jpg"),
            "project_code": "TEST001",
            "process_step": "点胶",
            "productSerial": "SN001",
            "productType": "电机",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload.get("task_id")
    assert payload.get("task_status") == "pending"

    with app.app_context():
        task = db.session.query(QCProcessTask).filter_by(id=payload["task_id"]).first()
        assert task is not None
        assert task.project_id == "TEST001"
        assert task.serial_number == "SN001"
        assert task.process_name == "点胶"
