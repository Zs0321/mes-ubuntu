from io import BytesIO
from unittest.mock import patch, MagicMock

def test_full_inspection_workflow(app, client_admin):
    """Test complete workflow: upload photo -> inspect -> get report"""
    # Create a mock vision service
    mock_service = MagicMock()
    mock_service.analyze_image.return_value = {
        "analysis": "测试分析结果",
        "defects": ["测试缺陷1", "测试缺陷2"]
    }

    # Patch get_vision_service to return our mock
    with patch('app_web.motor_qc.services.inspection_service.get_vision_service', return_value=mock_service):
        # Step 1: Upload photo
        upload_response = client_admin.post(
            '/motor-qc/api/photos/upload',
            data={
                'file': (BytesIO(b"fake image data"), 'test.jpg'),
                'project_code': 'TEST001',
                'process_step': '焊接'
            },
            content_type='multipart/form-data'
        )

        assert upload_response.status_code == 200
        photo_data = upload_response.get_json()
        photo_path = photo_data['photo_path']

        # Step 2: Perform inspection
        inspect_response = client_admin.post(
            '/motor-qc/api/inspect',
            json={
                'project_code': 'TEST001',
                'process_step': '焊接',
                'photo_path': photo_path,
                'inspector_id': 'test_user'
            }
        )

        assert inspect_response.status_code == 200
        inspect_data = inspect_response.get_json()
        assert inspect_data['status'] == 'fail'

        # Step 3: Get defect report
        report_response = client_admin.get('/motor-qc/api/reports/defects/TEST001')

        assert report_response.status_code == 200
        report_data = report_response.get_json()
        assert report_data['total_inspections'] >= 1

def test_batch_inspection_workflow(app, client_admin):
    """Test batch inspection with multiple photos"""
    # Create a mock vision service
    mock_service = MagicMock()
    mock_service.analyze_image.return_value = {
        "analysis": "测试分析结果",
        "defects": ["测试缺陷1"]
    }

    # Patch get_vision_service to return our mock
    with patch('app_web.motor_qc.services.inspection_service.get_vision_service', return_value=mock_service):
        # Upload multiple photos
        photos = []
        for i in range(3):
            response = client_admin.post(
                '/motor-qc/api/photos/upload',
                data={
                    'file': (BytesIO(f"image {i}".encode()), f'test{i}.jpg'),
                    'project_code': 'BATCH001',
                    'process_step': '焊接'
                },
                content_type='multipart/form-data'
            )
            photo_data = response.get_json()
            photos.append({
                'path': photo_data['photo_path'],
                'process_step': '焊接'
            })

        # Perform batch inspection
        response = client_admin.post(
            '/motor-qc/api/inspect/batch',
            json={
                'project_code': 'BATCH001',
                'photos': photos,
                'inspector_id': 'test_user'
            }
        )

        assert response.status_code == 200
        assert response.mimetype == 'text/event-stream'
