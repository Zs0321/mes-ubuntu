from io import BytesIO


def test_get_task_status_for_mobile_polling(app, client_admin):
    create_resp = client_admin.post(
        "/motor-qc/api/photos/upload",
        data={
            "file": (BytesIO(b"fake image"), "SN200_点胶_20260218_120001.jpg"),
            "project_code": "POLL001",
            "process_step": "点胶",
            "productSerial": "SN200",
        },
        content_type="multipart/form-data",
    )
    assert create_resp.status_code == 200
    task_id = create_resp.get_json().get("task_id")
    assert task_id

    resp = client_admin.get(f"/motor-qc/api/tasks/{task_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["task"]["id"] == task_id
    assert data["task"]["status"] in ("pending", "running", "review", "confirmed", "failed")
    assert isinstance(data["task"].get("photos"), list)


def test_task_runner_processes_pending_task_to_review(app):
    from app_web.motor_qc.models import db, QCProcessTask
    from app_web.motor_qc.services.task_service import QCTaskService
    from app_web.motor_qc.services.task_runner import QCTaskRunner

    class _FakeInspectionService:
        def __init__(self):
            self.persist_args = []

        def perform_inspection(self, project_code, process_step, photo_path, inspector_id, persist=True):
            self.persist_args.append(bool(persist))
            return {
                "status": "pass",
                "defects": [],
                "analysis": "通过",
                "confidence": 0.98,
            }

    with app.app_context():
        service = QCTaskService()
        task = service.upsert_task_for_photo(
            project_id="RUN001",
            serial_number="SN300",
            process_name="点胶",
            photo_path="/tmp/run-1.jpg",
        )
        assert task.status == "pending"

        fake_service = _FakeInspectionService()
        runner = QCTaskRunner(worker_id="test-runner", poll_interval=0.01, inspection_service=fake_service)
        processed = runner.process_next_pending()
        assert processed is True

        refreshed = db.session.query(QCProcessTask).filter_by(id=task.id).first()
        assert refreshed is not None
        assert refreshed.status == "review"
        assert (refreshed.best_result_json or {}).get("detail_total", 0) >= 1
        assert fake_service.persist_args == [False]


def test_task_runner_supports_legacy_inspection_signature(app):
    from app_web.motor_qc.models import db, QCProcessTask
    from app_web.motor_qc.services.task_service import QCTaskService
    from app_web.motor_qc.services.task_runner import QCTaskRunner

    class _LegacyInspectionService:
        def __init__(self):
            self.calls = []

        def perform_inspection(self, project_code, process_step, photo_path, inspector_id):
            self.calls.append(
                {
                    "project_code": project_code,
                    "process_step": process_step,
                    "photo_path": photo_path,
                    "inspector_id": inspector_id,
                }
            )
            return {
                "status": "pass",
                "defects": [],
                "analysis": "legacy-ok",
                "confidence": 0.95,
            }

    with app.app_context():
        service = QCTaskService()
        task = service.upsert_task_for_photo(
            project_id="RUN001-LEGACY",
            serial_number="SN300-L",
            process_name="点胶",
            photo_path="/tmp/run-legacy.jpg",
        )

        legacy = _LegacyInspectionService()
        runner = QCTaskRunner(worker_id="test-runner-legacy", poll_interval=0.01, inspection_service=legacy)
        assert runner.process_next_pending() is True

        refreshed = db.session.query(QCProcessTask).filter_by(id=task.id).first()
        assert refreshed is not None
        assert refreshed.status == "review"
        assert len(legacy.calls) == 1
        assert legacy.calls[0]["project_code"] == "RUN001-LEGACY"
        assert legacy.calls[0]["photo_path"] == "/tmp/run-legacy.jpg"


def test_task_runner_fallbacks_on_single_photo_timeout(app):
    from app_web.motor_qc.models import db, QCProcessTask, QCTaskDetailItem
    from app_web.motor_qc.services.task_service import QCTaskService
    from app_web.motor_qc.services.task_runner import QCTaskRunner

    class _TimeoutInspectionService:
        def perform_inspection(self, project_code, process_step, photo_path, inspector_id, persist=True):
            raise TimeoutError("vision timeout")

    with app.app_context():
        service = QCTaskService()
        task = service.upsert_task_for_photo(
            project_id="RUN002",
            serial_number="SN301",
            process_name="锁螺钉",
            photo_path="/tmp/run-timeout.jpg",
        )

        runner = QCTaskRunner(worker_id="test-timeout-runner", poll_interval=0.01, inspection_service=_TimeoutInspectionService())
        processed = runner.process_next_pending()
        assert processed is True

        refreshed = db.session.query(QCProcessTask).filter_by(id=task.id).first()
        assert refreshed is not None
        assert refreshed.status == "review"
        assert "部分照片识别失败" in str(refreshed.error_message or "")
        assert db.session.query(QCTaskDetailItem).filter_by(task_id=task.id).count() >= 1


def test_task_runner_adds_normalized_screw_detail_rows(app):
    from app_web.motor_qc.models import db, QCTaskDetailItem
    from app_web.motor_qc.services.task_service import QCTaskService
    from app_web.motor_qc.services.task_runner import QCTaskRunner

    class _ScrewInspectionService:
        def perform_inspection(self, project_code, process_step, photo_path, inspector_id, persist=True):
            return {
                "status": "fail",
                "defects": ["螺钉未拧紧，存在松动"],
                "analysis": "检测到螺丝漏装，需要返工",
                "confidence": 0.42,
            }

    with app.app_context():
        service = QCTaskService()
        task = service.upsert_task_for_photo(
            project_id="RUN003",
            serial_number="SN302",
            process_name="锁螺钉",
            photo_path="/tmp/run-screw.jpg",
        )

        runner = QCTaskRunner(worker_id="test-screw-runner", poll_interval=0.01, inspection_service=_ScrewInspectionService())
        assert runner.process_next_pending() is True

        labels = {
            item.detail_label
            for item in db.session.query(QCTaskDetailItem).filter_by(task_id=task.id).all()
        }
        assert "螺钉漏装" in labels
        assert "螺钉未到位/未拧紧" in labels
