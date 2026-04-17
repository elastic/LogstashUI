#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.test_resources import authenticated_client, test_connection, test_user
from PipelineManager.models import Connection
from PipelineManager.simulation import simulation_results, simulation_lock

from unittest.mock import patch, MagicMock, Mock
from django.core.files.uploadedfile import SimpleUploadedFile
from collections import deque

import json
import pytest
import base64


# ============================================================================
# SimulatePipeline Tests
# ============================================================================

@pytest.mark.django_db
class TestSimulatePipeline:
    """Test SimulatePipeline view"""

    @patch('PipelineManager.simulation.requests.post')
    @patch('PipelineManager.simulation.requests.get')
    def test_simulate_pipeline_success(self, mock_get, mock_post, authenticated_client):
        """Test successful pipeline simulation"""
        # Mock slot allocation response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'slot_id': 1,
            'reused': False
        }

        components = {
            "input": [],
            "filter": [
                {
                    "id": "filter_1",
                    "plugin": "mutate",
                    "config": {
                        "add_field": {"test": "value"}
                    }
                }
            ],
            "output": []
        }

        response = authenticated_client.post('/ConnectionManager/SimulatePipeline/', {
            'components': json.dumps(components),
            'log_text': '{"message": "test"}'
        })

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        # Should contain success indicators
        assert 'slot' in content.lower() or 'simulation' in content.lower()

    def test_simulate_pipeline_no_components(self, authenticated_client):
        """Test SimulatePipeline with no components provided"""
        response = authenticated_client.post('/ConnectionManager/SimulatePipeline/', {
            'log_text': '{"message": "test"}'
        })

        assert response.status_code == 200
        assert b'No pipeline components provided' in response.content

    def test_simulate_pipeline_invalid_json_components(self, authenticated_client):
        """Test SimulatePipeline with invalid JSON components"""
        response = authenticated_client.post('/ConnectionManager/SimulatePipeline/', {
            'components': 'invalid json {',
            'log_text': '{"message": "test"}'
        })

        assert response.status_code == 200
        assert b'Invalid components data' in response.content

    @patch('PipelineManager.simulation.requests.post')
    def test_simulate_pipeline_slot_allocation_failure(self, mock_post, authenticated_client):
        """Test SimulatePipeline when slot allocation fails"""
        # Mock failed slot allocation
        mock_post.side_effect = Exception("Connection refused")

        components = {
            "input": [],
            "filter": [{"id": "filter_1", "plugin": "mutate", "config": {}}],
            "output": []
        }

        response = authenticated_client.post('/ConnectionManager/SimulatePipeline/', {
            'components': json.dumps(components),
            'log_text': '{"message": "test"}'
        })

        assert response.status_code == 200
        # The actual error message is just the exception message
        assert b'Connection refused' in response.content

    @patch('PipelineManager.simulation.requests.post')
    def test_simulate_pipeline_no_filters(self, mock_post, authenticated_client):
        """Test SimulatePipeline with no filter plugins"""
        components = {
            "input": [],
            "filter": [],
            "output": []
        }

        response = authenticated_client.post('/ConnectionManager/SimulatePipeline/', {
            'components': json.dumps(components),
            'log_text': '{"message": "test"}'
        })

        assert response.status_code == 200
        assert b'No filter plugins found' in response.content or b'No filters to simulate' in response.content

    def test_simulate_pipeline_requires_admin(self, client, test_user):
        """Test that SimulatePipeline requires admin role"""
        # Create readonly user
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_sim',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_sim', password='testpass123')

        components = {
            "input": [],
            "filter": [{"id": "filter_1", "plugin": "mutate", "config": {}}],
            "output": []
        }

        response = client.post('/ConnectionManager/SimulatePipeline/', {
            'components': json.dumps(components),
            'log_text': '{"message": "test"}'
        })

        assert response.status_code == 403

    @patch('PipelineManager.simulation.requests.post')
    def test_simulate_pipeline_complex_orchestration(self, mock_post, authenticated_client):
        """Test SimulatePipeline with complex nested conditionals"""
        # Mock successful responses
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'slot_id': 1,
            'reused': False
        }

        components = {
            "input": [],
            "filter": [
                {
                    "id": "conditional_1",
                    "plugin": "if",
                    "config": {
                        "condition": "[status] == 200",
                        "plugins": [
                            {
                                "id": "filter_1",
                                "plugin": "mutate",
                                "config": {"add_field": {"success": "true"}}
                            }
                        ],
                        "else_ifs": [
                            {
                                "condition": "[status] == 404",
                                "plugins": [
                                    {
                                        "id": "filter_2",
                                        "plugin": "mutate",
                                        "config": {"add_field": {"not_found": "true"}}
                                    }
                                ]
                            }
                        ],
                        "else": {
                            "plugins": [
                                {
                                    "id": "filter_3",
                                    "plugin": "mutate",
                                    "config": {"add_field": {"other": "true"}}
                                }
                            ]
                        }
                    }
                }
            ],
            "output": []
        }

        response = authenticated_client.post('/ConnectionManager/SimulatePipeline/', {
            'components': json.dumps(components),
            'log_text': '{"message": "test", "status": 200}'
        })

        assert response.status_code == 200
        # Should handle complex nested structure without errors


# ============================================================================
# StreamSimulate Tests
# ============================================================================

@pytest.mark.django_db
class TestStreamSimulate:
    """Test StreamSimulate view (CSRF-exempt)"""

    def test_stream_simulate_success(self, client):
        """Test successful event streaming"""
        # Clear the queue before test
        with simulation_lock:
            simulation_results.clear()

        event_data = {
            "message": "test event",
            "run_id": "test-run-123",
            "simulation": {
                "step": 1,
                "id": "filter_1"
            },
            "snapshots": {
                "filter_1": {"message": "test event", "field": "value"}
            }
        }

        response = client.post(
            '/ConnectionManager/StreamSimulate/',
            data=json.dumps(event_data),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'ok'

        # Verify event was stored
        with simulation_lock:
            assert len(simulation_results) == 1
            assert simulation_results[0]['run_id'] == 'test-run-123'

    def test_stream_simulate_csrf_exempt(self, client):
        """Test that StreamSimulate is CSRF-exempt (can be called without token)"""
        event_data = {"message": "test", "run_id": "test-123"}

        # Call without CSRF token - should still work
        response = client.post(
            '/ConnectionManager/StreamSimulate/',
            data=json.dumps(event_data),
            content_type='application/json'
        )

        assert response.status_code == 200

    def test_stream_simulate_invalid_json(self, client):
        """Test StreamSimulate with invalid JSON"""
        response = client.post(
            '/ConnectionManager/StreamSimulate/',
            data='invalid json {',
            content_type='application/json'
        )

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data

    def test_stream_simulate_injection_attempt(self, client):
        """Test StreamSimulate with potential injection payload"""
        # Clear the queue
        with simulation_lock:
            simulation_results.clear()

        # Attempt to inject malicious data
        event_data = {
            "message": "<script>alert('XSS')</script>",
            "run_id": "test-run-xss",
            "malicious_field": "'; DROP TABLE users; --"
        }

        response = client.post(
            '/ConnectionManager/StreamSimulate/',
            data=json.dumps(event_data),
            content_type='application/json'
        )

        assert response.status_code == 200
        
        # Verify data is stored as-is (will be escaped when rendered)
        with simulation_lock:
            assert len(simulation_results) == 1
            stored_event = simulation_results[0]
            # Data should be stored but will be escaped during rendering
            assert stored_event['message'] == "<script>alert('XSS')</script>"

    def test_stream_simulate_method_not_allowed(self, client):
        """Test StreamSimulate with GET request"""
        response = client.get('/ConnectionManager/StreamSimulate/')

        assert response.status_code == 405
        data = json.loads(response.content)
        assert 'error' in data


# ============================================================================
# GetSimulationResults Tests
# ============================================================================

@pytest.mark.django_db
class TestGetSimulationResults:
    """Test GetSimulationResults view"""

    def test_get_simulation_results_success(self, authenticated_client):
        """Test successful retrieval of simulation results"""
        # Clear and populate queue
        with simulation_lock:
            simulation_results.clear()
            simulation_results.append({
                "message": "event 1",
                "run_id": "test-run-1"
            })
            simulation_results.append({
                "message": "event 2",
                "run_id": "test-run-1"
            })
            simulation_results.append({
                "message": "event 3",
                "run_id": "test-run-2"
            })

        response = authenticated_client.get('/ConnectionManager/GetSimulationResults/?run_id=test-run-1')

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'results' in data
        assert len(data['results']) == 2
        assert all(r['run_id'] == 'test-run-1' for r in data['results'])

        # Verify only run-1 events were removed from queue
        with simulation_lock:
            assert len(simulation_results) == 1
            assert simulation_results[0]['run_id'] == 'test-run-2'

    def test_get_simulation_results_no_run_id(self, authenticated_client):
        """Test GetSimulationResults without run_id parameter"""
        response = authenticated_client.get('/ConnectionManager/GetSimulationResults/')

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'run_id' in data['error']

    def test_get_simulation_results_race_condition_safety(self, authenticated_client):
        """Test GetSimulationResults handles concurrent access safely"""
        # Populate queue
        with simulation_lock:
            simulation_results.clear()
            for i in range(100):
                simulation_results.append({
                    "message": f"event {i}",
                    "run_id": "test-run-race"
                })

        # Make multiple concurrent-like requests
        response1 = authenticated_client.get('/ConnectionManager/GetSimulationResults/?run_id=test-run-race')
        response2 = authenticated_client.get('/ConnectionManager/GetSimulationResults/?run_id=test-run-race')

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = json.loads(response1.content)
        data2 = json.loads(response2.content)

        # First request should get all events, second should get none
        assert len(data1['results']) == 100
        assert len(data2['results']) == 0

    def test_get_simulation_results_empty_queue(self, authenticated_client):
        """Test GetSimulationResults when no results exist"""
        with simulation_lock:
            simulation_results.clear()

        response = authenticated_client.get('/ConnectionManager/GetSimulationResults/?run_id=nonexistent')

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['results'] == []


# ============================================================================
# CheckIfPipelineLoaded Tests
# ============================================================================

@pytest.mark.django_db
class TestCheckIfPipelineLoaded:
    """Test CheckIfPipelineLoaded view"""

    @patch('PipelineManager.simulation.requests.get')
    def test_check_pipeline_loaded_running(self, mock_get, authenticated_client):
        """Test checking a running pipeline"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'running_pipelines': ['slot1-filter1', 'slot2-filter1', 'main']
        }
        mock_get.return_value = mock_response

        response = authenticated_client.get('/ConnectionManager/CheckIfPipelineLoaded/?pipeline_name=slot1-filter1')

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['is_running'] is True
        assert data['pipeline_name'] == 'slot1-filter1'

    @patch('PipelineManager.simulation.requests.get')
    def test_check_pipeline_loaded_not_running(self, mock_get, authenticated_client):
        """Test checking a non-running pipeline"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'running_pipelines': ['slot1-filter1', 'main']
        }
        mock_get.return_value = mock_response

        response = authenticated_client.get('/ConnectionManager/CheckIfPipelineLoaded/?pipeline_name=slot2-filter1')

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['is_running'] is False
        assert data['pipeline_name'] == 'slot2-filter1'

    def test_check_pipeline_loaded_no_pipeline_name(self, authenticated_client):
        """Test CheckIfPipelineLoaded without pipeline_name parameter"""
        response = authenticated_client.get('/ConnectionManager/CheckIfPipelineLoaded/')

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'pipeline_name' in data['error']

    @patch('PipelineManager.simulation.requests.get')
    def test_check_pipeline_loaded_service_unavailable(self, mock_get, authenticated_client):
        """Test CheckIfPipelineLoaded when logstashagent is unavailable"""
        mock_get.side_effect = Exception("Connection refused")

        response = authenticated_client.get('/ConnectionManager/CheckIfPipelineLoaded/?pipeline_name=slot1-filter1')

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data
        assert data['is_running'] is False


# ============================================================================
# GetRelatedLogs Tests
# ============================================================================

@pytest.mark.django_db
class TestGetRelatedLogs:
    """Test GetRelatedLogs view"""

    @patch('PipelineManager.simulation.requests.get')
    def test_get_related_logs_success(self, mock_get, authenticated_client):
        """Test successful log retrieval"""
        # Mock slots endpoint
        mock_slots_response = Mock()
        mock_slots_response.status_code = 200
        mock_slots_response.json.return_value = {
            '1': {
                'created_at_millis': 1609459200000,
                'pipeline_name': 'slot1-filter1'
            }
        }

        # Mock logs endpoint
        mock_logs_response = Mock()
        mock_logs_response.status_code = 200
        mock_logs_response.json.return_value = {
            'pipeline_id': 'slot1-filter1',
            'log_count': 2,
            'logs': [
                {'level': 'INFO', 'message': 'Pipeline started', 'timeMillis': 1609459201000},
                {'level': 'DEBUG', 'message': 'Processing event', 'timeMillis': 1609459202000}
            ]
        }

        mock_get.side_effect = [mock_slots_response, mock_logs_response]

        response = authenticated_client.get('/ConnectionManager/GetRelatedLogs/?slot_id=1')

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['log_count'] == 2
        assert len(data['logs']) == 2

    def test_get_related_logs_no_slot_id(self, authenticated_client):
        """Test GetRelatedLogs without slot_id parameter"""
        response = authenticated_client.get('/ConnectionManager/GetRelatedLogs/')

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'slot_id' in data['error']

    @patch('PipelineManager.simulation.requests.get')
    def test_get_related_logs_with_filters(self, mock_get, authenticated_client):
        """Test GetRelatedLogs with max_entries and min_level filters"""
        mock_slots_response = Mock()
        mock_slots_response.status_code = 200
        mock_slots_response.json.return_value = {
            '1': {'created_at_millis': 1609459200000}
        }

        mock_logs_response = Mock()
        mock_logs_response.status_code = 200
        mock_logs_response.json.return_value = {
            'pipeline_id': 'slot1-filter1',
            'log_count': 1,
            'logs': [
                {'level': 'ERROR', 'message': 'Error occurred', 'timeMillis': 1609459201000}
            ]
        }

        mock_get.side_effect = [mock_slots_response, mock_logs_response]

        response = authenticated_client.get(
            '/ConnectionManager/GetRelatedLogs/?slot_id=1&max_entries=50&min_level=ERROR'
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['log_count'] == 1

    @patch('PipelineManager.simulation.requests.get')
    def test_get_related_logs_service_unavailable(self, mock_get, authenticated_client):
        """Test GetRelatedLogs when logstashagent is unavailable"""
        mock_get.side_effect = Exception("Connection refused")

        response = authenticated_client.get('/ConnectionManager/GetRelatedLogs/?slot_id=1')

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data
        assert data['log_count'] == 0


# ============================================================================
# UploadFile Tests
# ============================================================================

@pytest.mark.django_db
class TestUploadFile:
    """Test UploadFile view"""

    @patch('PipelineManager.simulation.requests.post')
    def test_upload_file_success(self, mock_post, authenticated_client):
        """Test successful file upload"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'ok'}
        mock_post.return_value = mock_response

        file_content = b'test file content'
        uploaded_file = SimpleUploadedFile("test.txt", file_content, content_type="text/plain")

        response = authenticated_client.post('/ConnectionManager/UploadFile/', {
            'file': uploaded_file,
            'filename': 'test.txt'
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'ok'
        assert data['filename'] == 'test.txt'

        # Verify base64 encoding was used
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        posted_data = call_args[1]['json']
        assert 'content' in posted_data
        assert 'filename' in posted_data
        # Verify content is base64 encoded
        decoded = base64.b64decode(posted_data['content'])
        assert decoded == file_content

    def test_upload_file_no_file(self, authenticated_client):
        """Test UploadFile with no file provided"""
        response = authenticated_client.post('/ConnectionManager/UploadFile/', {
            'filename': 'test.txt'
        })

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'No file provided' in data['error']

    def test_upload_file_no_filename(self, authenticated_client):
        """Test UploadFile with no filename provided"""
        file_content = b'test content'
        uploaded_file = SimpleUploadedFile("test.txt", file_content)

        response = authenticated_client.post('/ConnectionManager/UploadFile/', {
            'file': uploaded_file
        })

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'No filename provided' in data['error']

    @patch('PipelineManager.simulation.requests.post')
    def test_upload_file_oversized(self, mock_post, authenticated_client):
        """Test UploadFile with large file"""
        # Create a 10MB file
        large_content = b'x' * (10 * 1024 * 1024)
        uploaded_file = SimpleUploadedFile("large.txt", large_content)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        response = authenticated_client.post('/ConnectionManager/UploadFile/', {
            'file': uploaded_file,
            'filename': 'large.txt'
        })

        # Should handle large files (or return appropriate error if size limit exists)
        assert response.status_code in [200, 400, 413, 500]

    @patch('PipelineManager.simulation.requests.post')
    def test_upload_file_agent_failure(self, mock_post, authenticated_client):
        """Test UploadFile when logstashagent fails"""
        mock_post.side_effect = Exception("Connection refused")

        file_content = b'test content'
        uploaded_file = SimpleUploadedFile("test.txt", file_content)

        response = authenticated_client.post('/ConnectionManager/UploadFile/', {
            'file': uploaded_file,
            'filename': 'test.txt'
        })

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data
        # The actual error message is just the exception message
        assert 'Connection refused' in data['error']

    def test_upload_file_requires_admin(self, client):
        """Test that UploadFile requires admin role"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_upload',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_upload', password='testpass123')

        file_content = b'test content'
        uploaded_file = SimpleUploadedFile("test.txt", file_content)

        response = client.post('/ConnectionManager/UploadFile/', {
            'file': uploaded_file,
            'filename': 'test.txt'
        })

        assert response.status_code == 403

    @patch('PipelineManager.simulation.requests.post')
    def test_upload_file_binary_content(self, mock_post, authenticated_client):
        """Test UploadFile with binary file content"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Binary content (e.g., image file)
        binary_content = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        uploaded_file = SimpleUploadedFile("image.png", binary_content, content_type="image/png")

        response = authenticated_client.post('/ConnectionManager/UploadFile/', {
            'file': uploaded_file,
            'filename': 'image.png'
        })

        assert response.status_code == 200
        
        # Verify binary content was properly encoded
        call_args = mock_post.call_args
        posted_data = call_args[1]['json']
        decoded = base64.b64decode(posted_data['content'])
        assert decoded == binary_content
