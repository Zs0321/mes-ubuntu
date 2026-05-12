import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from pathlib import Path
from app_web.motor_qc.services.inspection_service import InspectionService
from app_web.motor_qc.models import InspectionRecord
from app_web.project_config_manager import ProjectConfigManager

def test_perform_inspection_creates_record(db_session, mock_vision_service):
    service = InspectionService(vision_service=mock_vision_service)
    result = service.perform_inspection(
        project_code="TEST001",
        process_step="焊接",
        photo_path="/path/to/photo.jpg",
        inspector_id="user123"
    )

    # Mock returns defects -> default status should be fail unless provider sets explicit status.
    assert result["status"] == "fail"
    assert result["record_id"] is not None
    assert "defects" in result

def test_inspection_api_endpoint(app, client_admin):
    """Test inspection API endpoint"""
    # Create a mock vision service
    mock_service = MagicMock()
    mock_service.analyze_image.return_value = {
        "analysis": "测试分析结果",
        "defects": ["测试缺陷1", "测试缺陷2"]
    }

    # Patch get_vision_service to return our mock
    with patch('app_web.motor_qc.services.inspection_service.get_vision_service', return_value=mock_service):
        response = client_admin.post('/motor-qc/api/inspect', json={
            'project_code': 'TEST001',
            'process_step': '焊接',
            'photo_path': '/test/photo.jpg',
            'inspector_id': 'user123'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'fail'
        assert 'record_id' in data
        assert 'defects' in data


def test_inspection_service_recognizes_photo_process(db_session, mock_vision_service, tmp_path):
    """Test that photo process calls Vision API"""
    # Create project config with photo process
    config_manager = ProjectConfigManager(tmp_path)
    config = {
        "projectName": "TestProject",
        "projectCode": "TEST001",
        "productTypes": [{
            "typeName": "Motor",
            "processSteps": [{
                "id": "p1",
                "name": "焊接",
                "attachmentType": "photo"
            }]
        }]
    }
    config_manager.save_project_config("TestProject", config)

    # Create service with config manager
    service = InspectionService(
        vision_service=mock_vision_service,
        config_manager=config_manager
    )

    # Perform inspection
    result = service.perform_inspection(
        project_code="TEST001",
        process_step="焊接",
        photo_path="/test/photo.jpg",
        inspector_id="user123"
    )

    # Vision API should be called
    assert mock_vision_service.analyze_image.called
    assert result["status"] == "fail"
    assert "defects" in result


def test_inspection_service_skips_pdf_process(db_session, mock_vision_service, tmp_path):
    """Test that PDF process skips Vision API"""
    # Create project config with PDF process
    config_manager = ProjectConfigManager(tmp_path)
    config = {
        "projectName": "TestProject",
        "projectCode": "TEST001",
        "productTypes": [{
            "typeName": "Motor",
            "processSteps": [{
                "id": "p2",
                "name": "质量报告",
                "attachmentType": "pdf"
            }]
        }]
    }
    config_manager.save_project_config("TestProject", config)

    # Create service
    service = InspectionService(
        vision_service=mock_vision_service,
        config_manager=config_manager
    )

    # Perform inspection
    result = service.perform_inspection(
        project_code="TEST001",
        process_step="质量报告",
        photo_path="/test/report.pdf",
        inspector_id="user123"
    )

    # Vision API should NOT be called
    assert not mock_vision_service.analyze_image.called
    assert result["status"] == "pass"
    assert result["defects"] == []
    assert "PDF" in result["analysis"]


def test_inspection_service_both_uses_file_extension(db_session, mock_vision_service, tmp_path):
    """attachmentType=both should route by actual file extension (.pdf vs image)"""
    config_manager = ProjectConfigManager(tmp_path)
    config = {
        "projectName": "TestProject",
        "projectCode": "TEST001",
        "productTypes": [{
            "typeName": "Motor",
            "processSteps": [{
                "id": "p3",
                "name": "质量报告",
                "attachmentType": "both"
            }]
        }]
    }
    config_manager.save_project_config("TestProject", config)

    service = InspectionService(
        vision_service=mock_vision_service,
        config_manager=config_manager
    )

    # PDF input should NOT call Vision API.
    result = service.perform_inspection(
        project_code="TEST001",
        process_step="质量报告",
        photo_path="/test/report.pdf",
        inspector_id="user123"
    )

    assert not mock_vision_service.analyze_image.called
    assert result["status"] == "pass"
    assert result["defects"] == []
    assert "PDF" in result["analysis"]


def test_inspection_service_defaults_to_photo(db_session, mock_vision_service, tmp_path):
    """Test backward compatibility - missing attachmentType defaults to photo"""
    config_manager = ProjectConfigManager(tmp_path)
    config = {
        "projectName": "OldProject",
        "projectCode": "OLD001",
        "productTypes": [{
            "typeName": "Motor",
            "processSteps": [{
                "id": "p1",
                "name": "Assembly"
                # No attachmentType field
            }]
        }]
    }
    config_manager.save_project_config("OldProject", config)

    service = InspectionService(
        vision_service=mock_vision_service,
        config_manager=config_manager
    )

    result = service.perform_inspection(
        project_code="OLD001",
        process_step="Assembly",
        photo_path="/test/photo.jpg",
        inspector_id="user123"
    )

    # Should default to photo - Vision API called
    assert mock_vision_service.analyze_image.called


def test_validate_photo_file_type(db_session, mock_vision_service, tmp_path):
    """Test that photo process validates image file types"""
    config_manager = ProjectConfigManager(tmp_path)
    config = {
        "projectName": "Test",
        "projectCode": "T001",
        "productTypes": [{
            "typeName": "Motor",
            "processSteps": [{
                "name": "焊接",
                "attachmentType": "photo"
            }]
        }]
    }
    config_manager.save_project_config("Test", config)

    service = InspectionService(
        vision_service=mock_vision_service,
        config_manager=config_manager
    )

    # Try to inspect with PDF file for photo process
    with pytest.raises(ValueError, match="Expected photo file"):
        service.perform_inspection(
            project_code="T001",
            process_step="焊接",
            photo_path="/test/document.pdf",
            inspector_id="user123"
        )


def test_validate_pdf_file_type(db_session, mock_vision_service, tmp_path):
    """Test that PDF process validates PDF file types"""
    config_manager = ProjectConfigManager(tmp_path)
    config = {
        "projectName": "Test",
        "projectCode": "T001",
        "productTypes": [{
            "typeName": "Motor",
            "processSteps": [{
                "name": "质量报告",
                "attachmentType": "pdf"
            }]
        }]
    }
    config_manager.save_project_config("Test", config)

    service = InspectionService(
        vision_service=mock_vision_service,
        config_manager=config_manager
    )

    # Try to inspect with image file for PDF process
    with pytest.raises(ValueError, match="Expected PDF file"):
        service.perform_inspection(
            project_code="T001",
            process_step="质量报告",
            photo_path="/test/photo.jpg",
            inspector_id="user123"
        )


def test_extract_serial_from_qc_temp_name_preserves_hyphen():
    serial = InspectionService._extract_serial_from_photo_path(
        "/tmp/qc__TZ310D-06A20002__后端盖打胶__0_abcd1234.jpg"
    )
    assert serial == "TZ310D-06A20002"
