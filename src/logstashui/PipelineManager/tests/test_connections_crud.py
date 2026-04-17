#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.test_resources import authenticated_client, test_connection, test_user
from PipelineManager.models import Connection, Policy, Pipeline

from unittest.mock import patch, MagicMock
from django.conf import settings
import json
import pytest


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_policy(db):
    """Create a test policy"""
    policy = Policy.objects.create(
        name='Test Policy',
        settings_path='/etc/logstash/',
        logs_path='/var/log/logstash',
        binary_path='/usr/share/logstash/bin',
        logstash_yml='http.host: "0.0.0.0"',
        jvm_options='-Xms1g\n-Xmx1g',
        log4j2_properties='logger.logstash.name = logstash'
    )
    return policy


@pytest.fixture
def test_agent_connection(db, test_policy):
    """Create a test agent connection"""
    connection = Connection.objects.create(
        name='Test Agent',
        connection_type='AGENT',
        host='agent.example.com',
        agent_id='test-agent-001',
        is_active=True,
        policy=test_policy
    )
    return connection


@pytest.fixture
def test_pipeline(db, test_policy):
    """Create a test pipeline"""
    pipeline = Pipeline.objects.create(
        policy=test_policy,
        name='test_pipeline',
        lscl='input { beats { port => 5044 } } filter {} output { elasticsearch { hosts => ["localhost:9200"] } }',
        description='Test pipeline description'
    )
    return pipeline


# ============================================================================
# GetConnections Tests
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

    def test_returns_all_connections(self, authenticated_client, test_connection, test_agent_connection):
        """Returns all connections regardless of type"""
        response = authenticated_client.get('/ConnectionManager/GetConnections/')
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        ids = [c['id'] for c in data]
        assert test_connection.id in ids
        assert test_agent_connection.id in ids

    def test_handles_empty_connections(self, authenticated_client):
        """Returns empty list when no connections exist"""
        Connection.objects.all().delete()
        response = authenticated_client.get('/ConnectionManager/GetConnections/')
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


# ============================================================================
# AddConnection Tests
# ============================================================================

@pytest.mark.django_db
class TestAddConnection:
    """Test Connection Create operations"""

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
        assert 'connection_id' in response_data

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

    def test_add_connection_get_returns_405(self, authenticated_client):
        """AddConnection only accepts POST — GET returns 405"""
        response = authenticated_client.get('/ConnectionManager/AddConnection')
        assert response.status_code == 405


# ============================================================================
# DeleteConnection Tests
# ============================================================================

@pytest.mark.django_db
class TestDeleteConnection:
    """Test Connection Delete operations"""

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

    def test_delete_connection_missing_id(self, authenticated_client):
        """Test deleting without connection_id"""
        response = authenticated_client.post('/ConnectionManager/DeleteConnection/')

        assert response.status_code in [400, 404]  # Either bad request or not found

    def test_delete_connection_get_returns_405(self, authenticated_client, test_connection):
        """DeleteConnection only accepts POST — GET returns 405"""
        response = authenticated_client.get(
            f'/ConnectionManager/DeleteConnection/{test_connection.id}/'
        )
        assert response.status_code == 405


# ============================================================================
# UpgradeAgent Tests
# ============================================================================

@pytest.mark.django_db
class TestUpgradeAgent:
    """Tests for the UpgradeAgent endpoint"""

    def test_upgrade_agent_success(self, authenticated_client, test_agent_connection):
        """Test successful agent upgrade request"""
        response = authenticated_client.post(
            f'/ConnectionManager/UpgradeAgent/{test_agent_connection.id}/'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'upgrade' in data['message'].lower()

        # Verify desired_agent_version was set
        test_agent_connection.refresh_from_db()
        assert test_agent_connection.desired_agent_version == settings.__PREFERRED_LS_AGENT_VERSION__

    def test_upgrade_agent_missing_id(self, authenticated_client):
        """Test upgrade without connection_id"""
        response = authenticated_client.post('/ConnectionManager/UpgradeAgent/')

        assert response.status_code in [400, 404]
        if response.status_code == 400:
            data = response.json()
            assert data['success'] is False
            assert 'Connection ID is required' in data['error']

    def test_upgrade_agent_nonexistent(self, authenticated_client):
        """Test upgrade for non-existent connection"""
        response = authenticated_client.post('/ConnectionManager/UpgradeAgent/99999/')

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Connection not found' in data['error']

    def test_upgrade_agent_centralized_connection(self, authenticated_client, test_connection):
        """Test that centralized connections cannot be upgraded"""
        response = authenticated_client.post(
            f'/ConnectionManager/UpgradeAgent/{test_connection.id}/'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Only agent connections can be upgraded' in data['error']

    def test_upgrade_agent_wrong_method(self, authenticated_client, test_agent_connection):
        """Test that GET requests are rejected"""
        response = authenticated_client.get(
            f'/ConnectionManager/UpgradeAgent/{test_agent_connection.id}/'
        )

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']


# ============================================================================
# ChangeConnectionPolicy Tests
# ============================================================================

@pytest.mark.django_db
class TestChangeConnectionPolicy:
    """Tests for the change_connection_policy endpoint"""

    def test_change_policy_success(self, authenticated_client, test_agent_connection, test_policy):
        """Test successful policy change"""
        # Create a new policy
        new_policy = Policy.objects.create(
            name='New Policy',
            settings_path='/etc/logstash/',
            logs_path='/var/log/logstash',
            binary_path='/usr/share/logstash/bin',
            logstash_yml='http.host: "127.0.0.1"',
            jvm_options='-Xms2g\n-Xmx2g',
            log4j2_properties='logger.logstash.name = logstash'
        )

        response = authenticated_client.post('/ConnectionManager/ChangeConnectionPolicy/', {
            'connection_id': test_agent_connection.id,
            'policy_id': new_policy.id
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify policy was changed
        test_agent_connection.refresh_from_db()
        assert test_agent_connection.policy == new_policy

    def test_change_policy_missing_connection_id(self, authenticated_client, test_policy):
        """Test policy change without connection_id"""
        response = authenticated_client.post('/ConnectionManager/ChangeConnectionPolicy/', {
            'policy_id': test_policy.id
        })

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'connection not found' in data['error'].lower()

    def test_change_policy_missing_policy_id(self, authenticated_client, test_agent_connection):
        """Test policy change without policy_id"""
        response = authenticated_client.post('/ConnectionManager/ChangeConnectionPolicy/', {
            'connection_id': test_agent_connection.id
        })

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']

    def test_change_policy_nonexistent_connection(self, authenticated_client, test_policy):
        """Test policy change for non-existent connection"""
        response = authenticated_client.post('/ConnectionManager/ChangeConnectionPolicy/', {
            'connection_id': 99999,
            'policy_id': test_policy.id
        })

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'connection not found' in data['error'].lower()

    def test_change_policy_nonexistent_policy(self, authenticated_client, test_agent_connection):
        """Test policy change to non-existent policy"""
        response = authenticated_client.post('/ConnectionManager/ChangeConnectionPolicy/', {
            'connection_id': test_agent_connection.id,
            'policy_id': 99999
        })

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']

    def test_change_policy_centralized_connection(self, authenticated_client, test_connection, test_policy):
        """Test that centralized connections cannot have policy changed"""
        response = authenticated_client.post('/ConnectionManager/ChangeConnectionPolicy/', {
            'connection_id': test_connection.id,
            'policy_id': test_policy.id
        })

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False

    def test_change_policy_wrong_method(self, authenticated_client, test_agent_connection, test_policy):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/ChangeConnectionPolicy/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']


# ============================================================================
# RestartLogstash Tests
# ============================================================================

@pytest.mark.django_db
class TestRestartLogstash:
    """Tests for the restart_logstash endpoint"""

    def test_restart_logstash_success(self, authenticated_client, test_agent_connection):
        """Test successful restart request"""
        response = authenticated_client.post('/ConnectionManager/RestartLogstash/', {
            'connection_id': test_agent_connection.id
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify restart flag was set
        test_agent_connection.refresh_from_db()
        assert test_agent_connection.restart_on_next_checkin is True

    def test_restart_logstash_missing_connection_id(self, authenticated_client):
        """Test restart without connection_id"""
        response = authenticated_client.post('/ConnectionManager/RestartLogstash/', {})

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'connection not found' in data['error'].lower()

    def test_restart_logstash_nonexistent_connection(self, authenticated_client):
        """Test restart for non-existent connection"""
        response = authenticated_client.post('/ConnectionManager/RestartLogstash/', {
            'connection_id': 99999
        })

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'connection not found' in data['error'].lower()

    def test_restart_logstash_centralized_connection(self, authenticated_client, test_connection):
        """Test that centralized connections cannot be restarted"""
        response = authenticated_client.post('/ConnectionManager/RestartLogstash/', {
            'connection_id': test_connection.id
        })

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False

    def test_restart_logstash_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/RestartLogstash/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']


# ============================================================================
# GetPipelines Tests
# ============================================================================

@pytest.mark.django_db
class TestGetPipelines:
    """Tests for the GetPipelines endpoint"""

    @patch('PipelineManager.connections_crud.get_elastic_connection')
    def test_get_pipelines_centralized_success(self, mock_get_es, authenticated_client, test_connection):
        """Test getting pipelines for centralized connection"""
        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'test_pipeline': {
                'description': 'Test pipeline',
                'last_modified': '2025-01-14T12:00:00.000Z'
            }
        }
        mock_get_es.return_value = mock_es

        response = authenticated_client.get(f'/ConnectionManager/GetPipelines/{test_connection.id}/')

        assert response.status_code == 200
        assert b'test_pipeline' in response.content

    def test_get_pipelines_agent_success(self, authenticated_client, test_agent_connection, test_pipeline):
        """Test getting pipelines for agent connection"""
        response = authenticated_client.get(f'/ConnectionManager/GetPipelines/{test_agent_connection.id}/')

        assert response.status_code == 200
        assert b'test_pipeline' in response.content
        assert b'Test pipeline description' in response.content

    def test_get_pipelines_agent_no_policy(self, authenticated_client):
        """Test getting pipelines for agent without policy"""
        agent = Connection.objects.create(
            name='No Policy Agent',
            connection_type='AGENT',
            host='nopolicy.example.com',
            agent_id='nopolicy-001',
            is_active=True,
            policy=None
        )

        response = authenticated_client.get(f'/ConnectionManager/GetPipelines/{agent.id}/')

        assert response.status_code == 200
        # Should return empty pipelines list

    def test_get_pipelines_nonexistent_connection(self, authenticated_client):
        """Test getting pipelines for non-existent connection"""
        response = authenticated_client.get('/ConnectionManager/GetPipelines/99999/')

        assert response.status_code == 404
        assert b'Connection not found' in response.content

    @patch('PipelineManager.connections_crud.get_elastic_connection')
    def test_get_pipelines_centralized_connection_error(self, mock_get_es, authenticated_client, test_connection):
        """Test handling of Elasticsearch connection errors"""
        # Mock connection error
        mock_get_es.side_effect = Exception("Connection failed")

        response = authenticated_client.get(f'/ConnectionManager/GetPipelines/{test_connection.id}/')

        # Should still return 200 but with empty pipelines
        assert response.status_code == 200


# ============================================================================
# GetPolicyPipelines Tests
# ============================================================================

@pytest.mark.django_db
class TestGetPolicyPipelines:
    """Tests for the GetPolicyPipelines endpoint"""

    def test_get_policy_pipelines_success(self, authenticated_client, test_policy, test_pipeline):
        """Test getting pipelines for a policy"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyPipelines/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['pipelines']) == 1
        assert data['pipelines'][0]['name'] == 'test_pipeline'
        assert data['pipelines'][0]['description'] == 'Test pipeline description'

    def test_get_policy_pipelines_empty(self, authenticated_client, test_policy):
        """Test getting pipelines when policy has none"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyPipelines/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['pipelines']) == 0

    def test_get_policy_pipelines_missing_policy_id(self, authenticated_client):
        """Test getting pipelines without policy_id"""
        response = authenticated_client.get('/ConnectionManager/GetPolicyPipelines/')

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy ID is required' in data['error']

    def test_get_policy_pipelines_nonexistent_policy(self, authenticated_client):
        """Test getting pipelines for non-existent policy"""
        response = authenticated_client.get('/ConnectionManager/GetPolicyPipelines/?policy_id=99999')

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['error']

    def test_get_policy_pipelines_multiple(self, authenticated_client, test_policy):
        """Test getting multiple pipelines for a policy"""
        # Create multiple pipelines
        Pipeline.objects.create(
            policy=test_policy,
            name='pipeline1',
            lscl='input {} filter {} output {}',
            description='Pipeline 1'
        )
        Pipeline.objects.create(
            policy=test_policy,
            name='pipeline2',
            lscl='input {} filter {} output {}',
            description='Pipeline 2'
        )

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyPipelines/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['pipelines']) == 2
        names = [p['name'] for p in data['pipelines']]
        assert 'pipeline1' in names
        assert 'pipeline2' in names
