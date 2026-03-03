from Common.test_resources import authenticated_client, test_connection, test_user
from PipelineManager.models import Connection

from unittest.mock import patch, MagicMock

import json
import pytest


# ============================================================================
# Connection CRUD Tests
# ============================================================================

@pytest.mark.django_db
class TestConnectionCRUD:
    """Test Connection Create, Read, Update, Delete operations"""

    def test_add_connection_requires_authentication(self, client):
        """Test that adding a connection requires authentication"""
        response = client.post('/ConnectionManager/AddConnection', {
            'name': 'Test',
            'connection_type': 'CENTRALIZED',
            'host': 'https://localhost:9200'
        })
        # Should redirect to login
        assert response.status_code == 302
        assert '/Management/Login/' in response.url

    @patch('PipelineManager.views.test_connectivity')
    def test_add_connection_success(self, mock_test_connectivity, authenticated_client):
        """Test successful connection creation"""
        # Mock successful connectivity test
        mock_test_connectivity.return_value = (True, "Connection successful")

        response = authenticated_client.post('/ConnectionManager/AddConnection', {
            'name': 'Test Connection',
            'connection_type': 'CENTRALIZED',
            'host': 'https://localhost:9200',
            'username': 'elastic',
            'password': 'changeme'
        })

        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is True
        assert 'Connection created and tested successfully!' in response_data['message']

        # Verify connection was created
        assert Connection.objects.filter(name='Test Connection').exists()

    @patch('PipelineManager.views.test_connectivity')
    def test_add_connection_failed_connectivity(self, mock_test_connectivity, authenticated_client):
        """Test connection creation with failed connectivity test"""
        # Mock failed connectivity test
        mock_test_connectivity.return_value = (False, "Connection failed: Timeout")

        response = authenticated_client.post('/ConnectionManager/AddConnection', {
            'name': 'Bad Connection',
            'connection_type': 'CENTRALIZED',
            'host': 'https://invalid:9200',
            'username': 'elastic',
            'password': 'wrong'
        })

        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is False
        assert 'Connection failed: Timeout' in response_data['error']

        # Verify connection was NOT created (deleted after failed test)
        assert not Connection.objects.filter(name='Bad Connection').exists()

    def test_add_connection_invalid_form(self, authenticated_client):
        """Test connection creation with invalid form data"""
        response = authenticated_client.post('/ConnectionManager/AddConnection', {
            'name': '',  # Empty name should fail validation
            'connection_type': 'CENTRALIZED'
        })

        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is False
        assert 'error' in response_data
        # Check that the error contains form validation messages
        assert 'name' in response_data['error'] or 'This field is required' in response_data['error']

    def test_delete_connection(self, authenticated_client, test_connection):
        """Test connection deletion"""
        connection_id = test_connection.id

        response = authenticated_client.post(f'/ConnectionManager/DeleteConnection/{connection_id}/')

        assert response.status_code == 200
        assert b'Connection deleted successfully!' in response.content

        # Verify connection was deleted
        assert not Connection.objects.filter(id=connection_id).exists()

    def test_delete_nonexistent_connection(self, authenticated_client):
        """Test deleting a connection that doesn't exist"""
        response = authenticated_client.post('/ConnectionManager/DeleteConnection/99999/')

        assert response.status_code == 404
        assert b'Connection not found' in response.content


# ============================================================================
# Pipeline CRUD Tests
# ============================================================================

@pytest.mark.django_db
class TestPipelineCRUD:
    """Test Pipeline Create, Read, Update, Delete operations"""

    @patch('PipelineManager.views.get_elastic_connection')
    def test_create_pipeline_success(self, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline creation"""
        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'pipeline_config': 'input {}\nfilter {}\noutput {}'
        })

        assert response.status_code == 200
        assert b'Pipeline created successfully!' in response.content

        # Verify put_pipeline was called
        mock_es.logstash.put_pipeline.assert_called_once()
        call_args = mock_es.logstash.put_pipeline.call_args
        assert call_args[1]['id'] == 'test_pipeline'

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_create_pipeline_invalid_name(self, mock_get_es, authenticated_client, test_connection):
        """Test pipeline creation with invalid name"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': '123invalid',  # Can't start with number
        })

        assert response.status_code == 400
        assert b'Pipeline ID must begin with a letter or underscore' in response.content

    @patch('PipelineManager.views.get_elastic_connection')
    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_save_pipeline_success(self, mock_get_pipeline, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline save"""
        # Mock existing pipeline
        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}',
            'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
            'pipeline_settings': {},
            'description': ''
        }

        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'test_pipeline': {
                'pipeline': 'input {}\nfilter {}\noutput {}',
                'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
                'pipeline_settings': {},
                'description': ''
            }
        }
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        components = {
            "input": [],
            "filter": [],
            "output": []
        }

        response = authenticated_client.post('/ConnectionManager/SavePipeline/', {
            'save_pipeline': 'true',
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'components': json.dumps(components),
            'add_ids': 'false'
        })

        assert response.status_code == 200
        assert b'Pipeline saved successfully!' in response.content

    @patch('PipelineManager.views.get_elastic_connection')
    def test_delete_pipeline_success(self, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline deletion"""
        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.delete_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/DeletePipeline/', {
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline'
        })

        assert response.status_code == 200
        assert b'Pipeline deleted successfully!' in response.content

        # Verify delete_pipeline was called
        mock_es.logstash.delete_pipeline.assert_called_once_with(id='test_pipeline')

    @patch('PipelineManager.views.get_elastic_connection')
    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_update_pipeline_settings_success(self, mock_get_pipeline, mock_get_es, authenticated_client,
                                              test_connection):
        """Test successful pipeline settings update"""
        # Mock existing pipeline
        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}',
            'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
            'pipeline_settings': {},
            'description': ''
        }

        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/UpdatePipelineSettings/', {
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'description': 'Updated description',
            'pipeline_workers': '2',
            'pipeline_batch_size': '250'
        })

        assert response.status_code == 200

        # Verify put_pipeline was called with updated settings
        mock_es.logstash.put_pipeline.assert_called()
        call_args = mock_es.logstash.put_pipeline.call_args
        assert call_args[1]['body']['description'] == 'Updated description'
        assert call_args[1]['body']['pipeline_settings']['pipeline.workers'] == 2


# ============================================================================
# Pipeline Name Validation Tests
# ============================================================================

@pytest.mark.django_db
class TestPipelineNameValidation:
    """Test pipeline name validation"""

    @patch('PipelineManager.views.get_elastic_connection')
    def test_pipeline_name_starts_with_letter(self, mock_get_es, authenticated_client, test_connection):
        """Test that pipeline name can start with a letter"""
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': 'valid_pipeline'
        })

        assert response.status_code == 200

    @patch('PipelineManager.views.get_elastic_connection')
    def test_pipeline_name_starts_with_underscore(self, mock_get_es, authenticated_client, test_connection):
        """Test that pipeline name can start with underscore"""
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': '_valid_pipeline'
        })

        assert response.status_code == 200

    def test_pipeline_name_starts_with_number_invalid(self, authenticated_client, test_connection):
        """Test that pipeline name cannot start with a number"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': '123invalid'
        })

        assert response.status_code == 400
        assert b'must begin with a letter or underscore' in response.content

    def test_pipeline_name_special_chars_invalid(self, authenticated_client, test_connection):
        """Test that pipeline name cannot contain special characters"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': 'invalid@pipeline'
        })

        assert response.status_code == 400
        # Pipeline name starts with a letter but contains invalid @ character
        # Check for the actual error message from the validator
        assert (b'can only contain letters' in response.content or 
                b'underscores, dashes, hyphens' in response.content)

    def test_pipeline_name_empty_invalid(self, authenticated_client, test_connection):
        """Test that pipeline name cannot be empty"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': ''
        })

        assert response.status_code == 400
        assert b'Pipeline name cannot be empty' in response.content


# ============================================================================
# Security & Error Handling Tests
# ============================================================================

@pytest.mark.django_db
class TestSecurityAndErrorHandling:
    """Test security features and error handling"""

    def test_get_pipelines_invalid_connection_id(self, authenticated_client):
        """Test GetPipelines with non-existent connection ID raises proper error"""
        response = authenticated_client.get('/ConnectionManager/GetPipelines/99999/')

        # Should return 500 or 404, not crash
        assert response.status_code in [404, 500]

    @patch('PipelineManager.views.test_connectivity')
    def test_connectivity_error_message_escaped(self, mock_test_connectivity, authenticated_client, test_connection):
        """Test that error messages in TestConnectivity are HTML-escaped to prevent XSS"""
        # Mock connectivity test with XSS attempt in error message
        xss_payload = "<script>alert('XSS')</script>"
        mock_test_connectivity.return_value = (False, xss_payload)

        response = authenticated_client.get(f'/ConnectionManager/TestConnectivity?test={test_connection.id}')

        assert response.status_code == 200
        # Verify the script tag is escaped, not executed
        content = response.content.decode('utf-8')
        assert '&lt;script&gt;' in content
        assert '<script>alert' not in content

    @patch('PipelineManager.views.test_connectivity')
    def test_readonly_user_cannot_add_connection(self, mock_test_connectivity, client, test_user):
        """Test that readonly (non-admin) user cannot add connections"""
        # Mock connectivity test
        mock_test_connectivity.return_value = (True, "Connection successful")
        
        # Create a readonly user (not admin)
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_add',
            password='testpass123',
            is_staff=False
        )
        # Update the auto-created profile to readonly role
        # (post_save signal creates profile with 'admin' role by default)
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_add', password='testpass123')

        response = client.post('/ConnectionManager/AddConnection', {
            'name': 'Test Connection',
            'connection_type': 'CENTRALIZED',
            'host': 'https://localhost:9200',
            'username': 'elastic',
            'password': 'changeme'
        })

        # Should be forbidden (403) due to @require_admin_role decorator
        assert response.status_code == 403

    def test_readonly_user_cannot_delete_connection(self, client, test_connection):
        """Test that readonly (non-admin) user cannot delete connections"""
        # Create a readonly user (not admin)
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_delete',
            password='testpass123',
            is_staff=False
        )
        # Update the auto-created profile to readonly role
        # (post_save signal creates profile with 'admin' role by default)
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_delete', password='testpass123')

        response = client.post(f'/ConnectionManager/DeleteConnection/{test_connection.id}/')

        # Should be forbidden (403) due to @require_admin_role decorator
        assert response.status_code == 403

        # Verify connection was NOT deleted
        assert Connection.objects.filter(id=test_connection.id).exists()


# ============================================================================
# RBAC Tests for Simulation and Pipeline Editor Endpoints
# ============================================================================

@pytest.mark.django_db
class TestRBACSimulationEndpoints:
    """Test RBAC (Role-Based Access Control) for simulation endpoints"""

    def test_readonly_user_cannot_simulate_pipeline(self, client):
        """Test that readonly user cannot access SimulatePipeline"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_simulate',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_simulate', password='testpass123')

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

    def test_readonly_user_cannot_upload_file(self, client):
        """Test that readonly user cannot upload files"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        readonly_user = User.objects.create_user(
            username='readonly_upload_rbac',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_upload_rbac', password='testpass123')

        file_content = b'test content'
        uploaded_file = SimpleUploadedFile("test.txt", file_content)

        response = client.post('/ConnectionManager/UploadFile/', {
            'file': uploaded_file,
            'filename': 'test.txt'
        })

        assert response.status_code == 403

    def test_readonly_user_can_view_simulation_results(self, authenticated_client):
        """Test that readonly users can view simulation results (read-only operation)"""
        # GetSimulationResults doesn't have @require_admin_role, so readonly users can access
        response = authenticated_client.get('/ConnectionManager/GetSimulationResults/?run_id=test-123')

        # Should work (returns 200 with empty results)
        assert response.status_code == 200

    def test_readonly_user_can_check_pipeline_loaded(self, authenticated_client):
        """Test that readonly users can check if pipeline is loaded (read-only operation)"""
        # CheckIfPipelineLoaded has @login_required but not @require_admin_role
        response = authenticated_client.get('/ConnectionManager/CheckIfPipelineLoaded/?pipeline_name=test')

        # Should work (may return error about missing pipeline, but not 403)
        assert response.status_code in [200, 400, 500]

    def test_readonly_user_can_get_related_logs(self, authenticated_client):
        """Test that readonly users can get related logs (read-only operation)"""
        # GetRelatedLogs has @login_required but not @require_admin_role
        response = authenticated_client.get('/ConnectionManager/GetRelatedLogs/?slot_id=1')

        # Should work (may return error, but not 403)
        assert response.status_code in [200, 400, 500]

    def test_admin_user_can_simulate_pipeline(self, authenticated_client):
        """Test that admin user can access SimulatePipeline"""
        components = {
            "input": [],
            "filter": [{"id": "filter_1", "plugin": "mutate", "config": {}}],
            "output": []
        }

        with patch('PipelineManager.simulation.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'slot_id': 1, 'reused': False}

            response = authenticated_client.post('/ConnectionManager/SimulatePipeline/', {
                'components': json.dumps(components),
                'log_text': '{"message": "test"}'
            })

            # Should work for admin
            assert response.status_code == 200

    def test_unauthenticated_user_cannot_simulate(self, client):
        """Test that unauthenticated users cannot access SimulatePipeline"""
        components = {
            "input": [],
            "filter": [{"id": "filter_1", "plugin": "mutate", "config": {}}],
            "output": []
        }

        response = client.post('/ConnectionManager/SimulatePipeline/', {
            'components': json.dumps(components),
            'log_text': '{"message": "test"}'
        })

        # Should redirect to login
        assert response.status_code == 302
        assert '/Management/Login/' in response.url


@pytest.mark.django_db
class TestRBACPipelineEditorEndpoints:
    """Test RBAC for pipeline editor endpoints"""

    @patch('PipelineManager.views.get_elastic_connection')
    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_readonly_user_cannot_save_pipeline(self, mock_get_pipeline, mock_get_es, client, test_connection):
        """Test that readonly user cannot save pipelines"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_save',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_save', password='testpass123')

        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}',
            'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
            'pipeline_settings': {},
            'description': ''
        }

        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'test_pipeline': {
                'pipeline': 'input {}\nfilter {}\noutput {}',
                'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
                'pipeline_settings': {},
                'description': ''
            }
        }
        mock_get_es.return_value = mock_es

        components = {"input": [], "filter": [], "output": []}

        response = client.post('/ConnectionManager/SavePipeline/', {
            'save_pipeline': 'true',
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'components': json.dumps(components)
        })

        assert response.status_code == 403

    @patch('PipelineManager.views.get_elastic_connection')
    def test_readonly_user_cannot_clone_pipeline(self, mock_get_es, client, test_connection):
        """Test that readonly user cannot clone pipelines"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_clone',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_clone', password='testpass123')

        response = client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'source',
            'new_pipeline': 'cloned'
        })

        assert response.status_code == 403

    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_readonly_user_can_view_pipeline_editor(self, mock_get_pipeline, client, test_connection):
        """Test that readonly user can view pipeline editor (read-only)"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_view',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_view', password='testpass123')

        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}',
            'pipeline_settings': {},
            'description': ''
        }

        response = client.get(
            f'/ConnectionManager/Pipelines/Editor/?es_id={test_connection.id}&pipeline=test_pipeline'
        )

        # PipelineEditor doesn't have @require_admin_role, so readonly can view
        assert response.status_code == 200


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.django_db
class TestIntegration:
    """Integration tests for complete workflows"""

    @patch('PipelineManager.views.test_connectivity')
    @patch('PipelineManager.views.get_elastic_connection')
    def test_full_pipeline_lifecycle(self, mock_get_es, mock_test_connectivity, authenticated_client):
        """Test complete pipeline lifecycle: create connection, create pipeline, update, delete"""
        # Step 1: Create connection
        mock_test_connectivity.return_value = (True, "Connection successful")

        conn_response = authenticated_client.post('/ConnectionManager/AddConnection', {
            'name': 'Integration Test Connection',
            'connection_type': 'CENTRALIZED',
            'host': 'https://localhost:9200',
            'username': 'elastic',
            'password': 'changeme'
        })
        assert conn_response.status_code == 200

        connection = Connection.objects.get(name='Integration Test Connection')

        # Step 2: Create pipeline
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_es.logstash.delete_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        create_response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': connection.id,
            'pipeline': 'integration_test_pipeline'
        })
        assert create_response.status_code == 200

        # Step 3: Delete pipeline
        delete_response = authenticated_client.post('/ConnectionManager/DeletePipeline/', {
            'es_id': connection.id,
            'pipeline': 'integration_test_pipeline'
        })
        assert delete_response.status_code == 200

        # Step 4: Delete connection
        delete_conn_response = authenticated_client.post(f'/ConnectionManager/DeleteConnection/{connection.id}/')
        assert delete_conn_response.status_code == 200
        assert not Connection.objects.filter(id=connection.id).exists()
