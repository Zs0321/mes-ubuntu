import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from app_web.motor_qc.services.batch_inspection_service import BatchInspectionService
from app_web.project_config_manager import ProjectConfigManager

def test_batch_inspection_processes_multiple_photos(db_session, mock_vision_service):
    """Test batch inspection processes multiple photos"""
    service = BatchInspectionService()
    service.inspection_service.vision_service = mock_vision_service

    photos = [
        {"path": "/test/photo1.jpg", "process_step": "焊接"},
        {"path": "/test/photo2.jpg", "process_step": "组装"}
    ]

    results = list(service.process_batch(
        project_code="TEST001",
        photos=photos,
        inspector_id="user123"
    ))

    assert len(results) == 2
    assert all(r["status"] in ["completed", "error"] for r in results)
    # Check that all completed successfully
    assert all(r["status"] == "completed" for r in results)

def test_batch_inspection_sse_endpoint(app, client_admin):
    """Test batch inspection SSE endpoint"""
    # Create a mock vision service
    mock_service = MagicMock()
    mock_service.analyze_image.return_value = {
        "analysis": "测试分析结果",
        "defects": ["测试缺陷1"]
    }

    # Patch get_vision_service to return our mock
    with patch('app_web.motor_qc.services.inspection_service.get_vision_service', return_value=mock_service):
        response = client_admin.post('/motor-qc/api/inspect/batch', json={
            'project_code': 'TEST001',
            'photos': [
                {'path': '/test/photo1.jpg', 'process_step': '焊接'}
            ],
            'inspector_id': 'user123'
        })

    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'


def test_batch_inspection_handles_mixed_types(db_session, mock_vision_service, tmp_path):
    """Test batch inspection with mixed photo and PDF processes"""
    config_manager = ProjectConfigManager(tmp_path)
    config = {
        "projectName": "Test",
        "projectCode": "T001",
        "productTypes": [{
            "typeName": "Motor",
            "processSteps": [
                {"name": "焊接", "attachmentType": "photo"},
                {"name": "质量报告", "attachmentType": "pdf"}
            ]
        }]
    }
    config_manager.save_project_config("Test", config)

    service = BatchInspectionService(config_manager=config_manager)
    service.inspection_service.vision_service = mock_vision_service

    photos = [
        {"path": "/test/photo1.jpg", "process_step": "焊接"},
        {"path": "/test/report.pdf", "process_step": "质量报告"}
    ]

    results = list(service.process_batch(
        project_code="T001",
        photos=photos,
        inspector_id="user123"
    ))

    assert len(results) == 2
    assert all(r["status"] == "completed" for r in results)

    # Vision API should only be called once (for photo)
    assert mock_vision_service.analyze_image.call_count == 1
