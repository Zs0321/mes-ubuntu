def test_upsert_task_merges_unfinished_task(app):
    from app_web.motor_qc.models import db, QCProcessTask, QCTaskPhoto
    from app_web.motor_qc.services.task_service import QCTaskService

    with app.app_context():
        service = QCTaskService()
        task1 = service.upsert_task_for_photo(
            project_id="P1",
            serial_number="S1",
            process_name="点胶",
            photo_path="/tmp/a.jpg",
        )
        task2 = service.upsert_task_for_photo(
            project_id="P1",
            serial_number="S1",
            process_name="点胶",
            photo_path="/tmp/b.jpg",
        )

        assert task1.id == task2.id
        assert task2.status == "pending"

        db.session.refresh(task2)
        assert task2.photo_count == 2
        assert db.session.query(QCTaskPhoto).filter_by(task_id=task2.id).count() == 2
        assert db.session.query(QCProcessTask).count() == 1


def test_best_detail_result_prefers_any_pass(app):
    from app_web.motor_qc.services.task_service import QCTaskService

    with app.app_context():
        service = QCTaskService()
        merged = service.aggregate_detail_results(
            [
                {"detail_key": "seal", "detail_label": "密封", "status": "fail", "photo_id": 1, "source": "config"},
                {"detail_key": "seal", "detail_label": "密封", "status": "pass", "photo_id": 2, "source": "ai"},
                {"detail_key": "glue", "detail_label": "胶量", "status": "pending", "photo_id": 3, "source": "ai"},
            ]
        )

        assert merged["seal"]["best_status"] == "pass"
        assert merged["seal"]["best_photo_id"] == 2
        assert merged["seal"]["source"] == "config"
        assert merged["glue"]["best_status"] == "pending"


def test_upsert_task_reuses_confirmed_row_and_resets_on_new_photo(app):
    from app_web.motor_qc.models import db, QCProcessTask, QCTaskPhoto
    from app_web.motor_qc.services.task_service import QCTaskService

    with app.app_context():
        service = QCTaskService()
        task = service.upsert_task_for_photo(
            project_id="P2",
            serial_number="S2",
            process_name="锁螺钉",
            photo_path="/tmp/first.jpg",
        )
        task.status = "confirmed"
        db.session.commit()

        reused = service.upsert_task_for_photo(
            project_id="P2",
            serial_number="S2",
            process_name="锁螺钉",
            photo_path="/tmp/second.jpg",
        )

        assert reused.id == task.id
        assert reused.status == "pending"
        assert db.session.query(QCProcessTask).count() == 1
        assert db.session.query(QCTaskPhoto).filter_by(task_id=task.id).count() == 2


def test_upsert_same_photo_path_keeps_review_status(app):
    from app_web.motor_qc.models import db, QCTaskPhoto
    from app_web.motor_qc.services.task_service import QCTaskService

    with app.app_context():
        service = QCTaskService()
        task = service.upsert_task_for_photo(
            project_id="P3",
            serial_number="S3",
            process_name="点胶",
            photo_path="/tmp/same.jpg",
        )
        task.status = "review"
        db.session.commit()

        reused = service.upsert_task_for_photo(
            project_id="P3",
            serial_number="S3",
            process_name="点胶",
            photo_path="/tmp/same.jpg",
        )

        assert reused.id == task.id
        assert reused.status == "review"
        assert db.session.query(QCTaskPhoto).filter_by(task_id=task.id).count() == 1
