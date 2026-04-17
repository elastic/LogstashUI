#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

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

    @patch('PipelineManager.manager_views.test_connectivity')
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

    @patch('PipelineManager.manager_views.test_connectivity')
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

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
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

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
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

        assert response.status_code == 204

        # Verify delete_pipeline was called
        mock_es.logstash.delete_pipeline.assert_called_once_with(id='test_pipeline')

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    @patch('PipelineManager.pipelines_crud.get_logstash_pipeline')
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

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
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

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
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

    @patch('PipelineManager.manager_views.test_connectivity')
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

    @patch('PipelineManager.manager_views.test_connectivity')
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
# test_connectivity() pure function
# ============================================================================

class TestConnectivityHelper:
    """Unit tests for the test_connectivity() pure helper function"""

    def test_no_connection_id_returns_false(self):
        """Empty connection_id immediately returns (False, message)"""
        from PipelineManager.manager_views import test_connectivity
        success, msg = test_connectivity("")
        assert success is False
        assert "No connection ID" in msg

    @patch('PipelineManager.manager_views.get_elastic_connection')
    @patch('PipelineManager.manager_views.test_elastic_connectivity')
    def test_success_returns_true_and_result(self, mock_test_elastic, mock_get_es):
        from PipelineManager.manager_views import test_connectivity
        mock_get_es.return_value = MagicMock()
        mock_test_elastic.return_value = "Connected!"
        success, msg = test_connectivity("42")
        assert success is True
        assert msg == "Connected!"

    @patch('PipelineManager.manager_views.get_elastic_connection', side_effect=Exception("timeout"))
    def test_exception_returns_false(self, mock_get_es):
        from PipelineManager.manager_views import test_connectivity
        success, msg = test_connectivity("42")
        assert success is False
        assert "timeout" in msg


# ============================================================================
# TestConnectivity VIEW — additional paths
# ============================================================================

@pytest.mark.django_db
class TestTestConnectivityView:
    """Tests for the TestConnectivity view"""

    def test_no_test_id_returns_400(self, authenticated_client):
        """GET without `test` param returns 400"""
        response = authenticated_client.get('/ConnectionManager/TestConnectivity')
        assert response.status_code == 400
        assert b'No connection ID' in response.content

    @patch('PipelineManager.manager_views.test_connectivity', return_value=(True, "All good!"))
    def test_success_renders_green_div(self, mock_tc, authenticated_client, test_connection):
        """Successful connection renders a green-coloured div"""
        response = authenticated_client.get(
            f'/ConnectionManager/TestConnectivity?test={test_connection.id}'
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert 'green' in content
        assert 'All good!' in content


# ============================================================================
# GetConnections VIEW
# ============================================================================

@pytest.mark.django_db
class TestGetConnections:
    """Tests for the GetConnections view"""

    def test_returns_json_list(self, authenticated_client, test_connection):
        """Returns a JSON list of connection dicts"""
        response = authenticated_client.get('/ConnectionManager/GetConnections/')
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # At least our test_connection
        ids = [c['id'] for c in data]
        assert test_connection.id in ids

    def test_returns_expected_fields(self, authenticated_client, test_connection):
        """Each connection dict has id, name, connection_type"""
        response = authenticated_client.get('/ConnectionManager/GetConnections/')
        item = response.json()[0]
        assert 'id' in item
        assert 'name' in item
        assert 'connection_type' in item


# ============================================================================
# AddConnection / DeleteConnection method guards
# ============================================================================

@pytest.mark.django_db
class TestConnectionMethodGuards:
    """Test HTTP method enforcement on connection endpoints"""

    def test_add_connection_get_returns_405(self, authenticated_client):
        """AddConnection only accepts POST — GET returns 405"""
        response = authenticated_client.get('/ConnectionManager/AddConnection')
        assert response.status_code == 405

    def test_delete_connection_get_returns_405(self, authenticated_client, test_connection):
        """DeleteConnection only accepts POST — GET returns 405"""
        response = authenticated_client.get(
            f'/ConnectionManager/DeleteConnection/{test_connection.id}/'
        )
        assert response.status_code == 405


# ============================================================================
# PipelineManager page
# ============================================================================

@pytest.mark.django_db
class TestPipelineManagerPage:
    """Tests for the PipelineManager view"""

    def test_page_loads(self, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/')
        assert response.status_code == 200

    def test_context_has_connections(self, authenticated_client, test_connection):
        response = authenticated_client.get('/ConnectionManager/')
        assert response.status_code == 200
        assert 'connections' in response.context
        assert 'has_connections' in response.context
        assert response.context['has_connections'] is True


# ============================================================================
# GetPipeline endpoint
# ============================================================================

@pytest.mark.django_db
class TestGetPipelineEndpoint:
    """Tests for the GetPipeline JSON view"""

    def test_missing_params_returns_400(self, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/GetPipeline/')
        assert response.status_code == 400
        assert 'error' in response.json()

    def test_missing_pipeline_returns_400(self, authenticated_client, test_connection):
        response = authenticated_client.get(
            f'/ConnectionManager/GetPipeline/?es_id={test_connection.id}'
        )
        assert response.status_code == 400

    @patch('PipelineManager.pipelines_crud.get_logstash_pipeline', return_value=None)
    def test_pipeline_not_found_returns_400(self, mock_glp, authenticated_client, test_connection):
        response = authenticated_client.get(
            f'/ConnectionManager/GetPipeline/?es_id={test_connection.id}&pipeline=missing'
        )
        assert response.status_code == 400
        assert 'error' in response.json()

    @patch('PipelineManager.pipelines_crud.get_logstash_pipeline')
    def test_success_returns_code(self, mock_glp, authenticated_client, test_connection):
        mock_glp.return_value = {'pipeline': 'input {} filter {} output {}'}
        response = authenticated_client.get(
            f'/ConnectionManager/GetPipeline/?es_id={test_connection.id}&pipeline=mypipe'
        )
        assert response.status_code == 200
        assert response.json()['code'] == 'input {} filter {} output {}'


# ============================================================================
# ClonePipeline error paths
# ============================================================================

@pytest.mark.django_db
class TestClonePipelineEdgeCases:
    """Tests for ClonePipeline error paths"""

    def test_invalid_source_name_returns_400(self, authenticated_client, test_connection):
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': '123bad',
            'new_pipeline': 'newpipe',
        })
        assert response.status_code == 400

    def test_invalid_new_name_returns_400(self, authenticated_client, test_connection):
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'valid_source',
            'new_pipeline': '123bad',
        })
        assert response.status_code == 400

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_source_pipeline_not_found_returns_404(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        # get_pipeline returns dict that does NOT contain source_pipeline key
        mock_es.logstash.get_pipeline.return_value = {}
        mock_get_es.return_value = mock_es
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'missing_pipe',
            'new_pipeline': 'new_pipe',
        })
        assert response.status_code == 404

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_new_pipeline_name_already_exists_returns_400(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.side_effect = [
            # First call: get source pipeline
            {'source_pipe': {'pipeline': 'input {} filter {} output {}',
                             'pipeline_settings': {}, 'description': ''}},
            # Second call: get all pipelines — new_pipe already in there
            {'source_pipe': {}, 'new_pipe': {}},
        ]
        mock_get_es.return_value = mock_es
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'source_pipe',
            'new_pipeline': 'new_pipe',
        })
        assert response.status_code == 400
        assert b'already exists' in response.content

    @patch('PipelineManager.pipelines_crud.get_elastic_connection', side_effect=Exception("ES down"))
    def test_clone_exception_returns_500(self, mock_get_es, authenticated_client, test_connection):
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'source_pipe',
            'new_pipeline': 'new_pipe',
        })
        assert response.status_code == 500


# ============================================================================
# DeletePipeline — additional paths
# ============================================================================

@pytest.mark.django_db
class TestDeletePipelineEdgeCases:
    """Extra DeletePipeline tests"""

    def test_invalid_pipeline_name_returns_400(self, authenticated_client, test_connection):
        response = authenticated_client.post('/ConnectionManager/DeletePipeline/', {
            'es_id': test_connection.id,
            'pipeline': '123invalid',
        })
        assert response.status_code == 400


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.django_db
class TestIntegration:
    """Integration tests for complete workflows"""

    @patch('PipelineManager.manager_views.test_connectivity')
    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
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
        assert delete_response.status_code == 204

        # Step 4: Delete connection
        delete_conn_response = authenticated_client.post(f'/ConnectionManager/DeleteConnection/{connection.id}/')
        assert delete_conn_response.status_code == 200
        assert not Connection.objects.filter(id=connection.id).exists()


# ============================================================================
# CreatePipeline — simulate path and default config
# ============================================================================

@pytest.mark.django_db
class TestCreatePipelineAdditional:
    """Additional CreatePipeline tests"""

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_creates_default_empty_config_when_no_pipeline_config(
            self, mock_get_es, authenticated_client, test_connection):
        """When no pipeline_config is given, the default 'input {} filter {} output {}' is used"""
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': 'default_pipe',
            # no pipeline_config
        })
        assert response.status_code == 200
        call_body = mock_es.logstash.put_pipeline.call_args[1]['body']
        assert 'input {}' in call_body['pipeline']

    @patch('PipelineManager.pipelines_crud.requests.put')
    def test_simulate_mode_success(self, mock_put, authenticated_client, settings):
        """CreatePipeline in simulate=True mode sends a PUT to logstashagent"""
        settings.LOGSTASH_AGENT_URL = 'http://localhost:8080'
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_put.return_value = mock_response

        from PipelineManager.pipelines_crud import CreatePipeline
        from django.test import RequestFactory
        from django.contrib.auth.models import User

        rf = RequestFactory()
        user = User.objects.get(username='testuser')
        request = rf.get('/')
        request.user = user

        response = CreatePipeline(
            request,
            simulate=True,
            pipeline_name='sim_pipe',
            pipeline_config='input {} filter {} output {}'
        )
        assert response.status_code == 200
        assert b'Simulation pipeline created successfully' in response.content

    @patch('PipelineManager.pipelines_crud.requests.put',
           side_effect=__import__('requests').exceptions.ConnectionError("agent down"))
    def test_simulate_mode_failure_returns_500(self, mock_put, authenticated_client, settings):
        """CreatePipeline simulate=True with agent failure returns 500.

        The view only catches requests.exceptions.RequestException — a generic
        Exception would propagate uncaught, so we use a concrete subclass here.
        """
        settings.LOGSTASH_AGENT_URL = 'http://localhost:8080'

        from PipelineManager.pipelines_crud import CreatePipeline
        from django.test import RequestFactory
        from django.contrib.auth.models import User

        rf = RequestFactory()
        user = User.objects.get(username='testuser')
        request = rf.get('/')
        request.user = user

        response = CreatePipeline(
            request,
            simulate=True,
            pipeline_name='sim_pipe',
            pipeline_config='input {} filter {} output {}'
        )
        assert response.status_code == 500
