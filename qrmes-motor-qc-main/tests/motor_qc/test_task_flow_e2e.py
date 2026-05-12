from io import BytesIO


def test_task_flow_upload_review_confirmed(app, client_admin):
    from app_web.motor_qc.models import db, QCProcessTask
    from app_web.motor_qc.services.task_runner import QCTaskRunner

    class _FakeInspectionService:
        def perform_inspection(self, project_code, process_step, photo_path, inspector_id, persist=True):
            return {
                "status": "pass",
                "defects": [],
                "analysis": "通过",
                "confidence": 0.97,
            }

    create_resp = client_admin.post(
        "/motor-qc/api/photos/upload",
        data={
            "file": (BytesIO(b"fake image"), "SN900_点胶_20260218_140001.jpg"),
            "project_code": "FLOW001",
            "process_step": "点胶",
            "productSerial": "SN900",
            "productType": "电机总成",
        },
        content_type="multipart/form-data",
    )
    assert create_resp.status_code == 200
    payload = create_resp.get_json()
    assert payload["task_status"] == "pending"
    task_id = int(payload["task_id"])

    with app.app_context():
        runner = QCTaskRunner(worker_id="test-flow-runner", poll_interval=0.01, inspection_service=_FakeInspectionService())
        assert runner.process_next_pending() is True
        task = db.session.query(QCProcessTask).filter_by(id=task_id).first()
        assert task is not None
        assert task.status == "review"

    confirm_resp = client_admin.post(
        f"/motor-qc/api/tasks/{task_id}/confirm",
        json={
            "details": [{"detail_key": "overall", "confirmed_status": "pass"}],
            "notes": "e2e confirm",
        },
    )
    assert confirm_resp.status_code == 200
    confirm_payload = confirm_resp.get_json()
    assert confirm_payload["task"]["status"] == "confirmed"
