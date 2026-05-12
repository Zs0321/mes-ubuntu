import pytest
from sqlalchemy.exc import IntegrityError


def test_qc_process_task_unique_key(app):
    from app_web.motor_qc.models import db, QCProcessTask

    with app.app_context():
        task1 = QCProcessTask(
            task_key="P|S|STEP",
            project_id="P",
            serial_number="S",
            process_name="STEP",
        )
        db.session.add(task1)
        db.session.commit()

        task2 = QCProcessTask(
            task_key="P|S|STEP",
            project_id="P",
            serial_number="S",
            process_name="STEP",
        )
        db.session.add(task2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_qc_task_detail_item_unique_per_task(app):
    from app_web.motor_qc.models import db, QCProcessTask, QCTaskDetailItem

    with app.app_context():
        task = QCProcessTask(
            task_key="P|S|STEP2",
            project_id="P",
            serial_number="S",
            process_name="STEP2",
        )
        db.session.add(task)
        db.session.commit()

        item1 = QCTaskDetailItem(
            task_id=task.id,
            detail_key="seal_position",
            detail_label="密封位置",
            source="config",
        )
        db.session.add(item1)
        db.session.commit()

        item2 = QCTaskDetailItem(
            task_id=task.id,
            detail_key="seal_position",
            detail_label="密封位置",
            source="ai",
        )
        db.session.add(item2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
