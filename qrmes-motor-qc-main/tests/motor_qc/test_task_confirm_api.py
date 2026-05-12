def test_task_confirm_updates_status_and_feedback(app, client_admin):
    from app_web.motor_qc.models import db, QCProcessTask, QCTaskDetailItem, QCFeedbackRecord

    with app.app_context():
        task = QCProcessTask(
            task_key="P001|SN001|点胶",
            project_id="P001",
            serial_number="SN001",
            product_type="油泵电机总成",
            process_name="点胶",
            status="review",
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(
            QCTaskDetailItem(
                task_id=task.id,
                detail_key="overall",
                detail_label="工序整体",
                source="config",
                best_status="pass",
            )
        )
        db.session.commit()
        task_id = task.id

    resp = client_admin.post(
        f"/motor-qc/api/tasks/{task_id}/confirm",
        json={
            "details": [
                {"detail_key": "overall", "confirmed_status": "pass"},
            ],
            "notes": "人工确认通过",
        },
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["task"]["status"] == "confirmed"

    with app.app_context():
        updated = db.session.query(QCTaskDetailItem).filter_by(task_id=task_id, detail_key="overall").first()
        assert updated is not None
        assert updated.confirmed_status == "pass"

        feedback = db.session.query(QCFeedbackRecord).filter_by(project_id="P001", serial_number="SN001").all()
        assert len(feedback) == 1
        assert feedback[0].process_name == "点胶"
