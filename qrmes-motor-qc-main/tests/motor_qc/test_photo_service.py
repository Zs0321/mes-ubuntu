import pytest
from io import BytesIO
from app_web.motor_qc.services.photo_service import PhotoService

def test_save_photo_returns_path(tmp_path):
    service = PhotoService(base_path=str(tmp_path))

    # Mock file upload
    file_data = BytesIO(b"fake image data")

    result = service.save_photo(
        file=file_data,
        project_code="TEST001",
        process_step="焊接",
        filename="test.jpg"
    )

    assert result["success"] is True
    assert "photo_path" in result
    assert result["photo_path"].endswith(".jpg")

def test_photo_upload_endpoint(app, client_admin):
    """Test photo upload API endpoint"""
    data = {
        'file': (BytesIO(b"fake image"), 'test.jpg'),
        'project_code': 'TEST001',
        'process_step': '焊接'
    }

    response = client_admin.post(
        '/motor-qc/api/photos/upload',
        data=data,
        content_type='multipart/form-data'
    )

    assert response.status_code == 200
    result = response.get_json()
    assert result['success'] is True
    assert 'photo_path' in result
