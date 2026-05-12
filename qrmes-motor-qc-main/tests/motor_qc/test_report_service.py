import pytest
from app_web.motor_qc.services.report_service import ReportService
from app_web.motor_qc.models import InspectionRecord

def test_get_defect_statistics(db_session):
    """Test defect statistics calculation"""
    # Create test data
    record1 = InspectionRecord(
        project_code="TEST001",
        process_step="焊接",
        photo_path="/test/photo1.jpg",
        inspector_id="user123",
        defects_found=["裂纹", "气孔"],
        status="completed"
    )
    record2 = InspectionRecord(
        project_code="TEST001",
        process_step="焊接",
        photo_path="/test/photo2.jpg",
        inspector_id="user123",
        defects_found=["裂纹"],
        status="completed"
    )
    db_session.add_all([record1, record2])
    db_session.commit()

    service = ReportService()
    stats = service.get_defect_statistics(project_code="TEST001")

    assert stats["total_inspections"] == 2
    assert stats["defect_types"]["裂纹"] == 2
    assert stats["defect_types"]["气孔"] == 1

def test_defect_report_endpoint(app, db_session, client_admin):
    """Test defect report API endpoint"""
    # Setup test data
    record = InspectionRecord(
        project_code="TEST001",
        process_step="焊接",
        photo_path="/test/photo.jpg",
        inspector_id="user123",
        defects_found=["裂纹"],
        status="completed"
    )
    db_session.add(record)
    db_session.commit()

    response = client_admin.get('/motor-qc/api/reports/defects/TEST001')

    assert response.status_code == 200
    data = response.get_json()
    assert data['total_inspections'] > 0
