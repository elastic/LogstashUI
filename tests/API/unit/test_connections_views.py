#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for API/connections_views.py — REST connection endpoints."""

import json
import pytest

from unittest.mock import patch

from django.contrib.auth.models import User
from PipelineManager.models import Connection, Policy, ApiKey
from Management.models import UserProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_key_header(test_user):
    """Return an Authorization header dict for the test admin user."""
    _token, raw = ApiKey.issue_for_user(test_user, name='test-key')
    return {'HTTP_AUTHORIZATION': f'ApiKey {raw}'}


@pytest.fixture
def centralized_connection(db):
    return Connection.objects.create(
        name='Test Centralized',
        connection_type='CENTRALIZED',
        host='https://es.example.com',
        port=9200,
        username='elastic',
        password='changeme',
    )


@pytest.fixture
def agent_policy(db):
    return Policy.objects.create(
        name='Test Policy',
        settings_path='/etc/logstash/',
        logs_path='/var/log/logstash',
        binary_path='/usr/share/logstash/bin',
        logstash_yml='http.host: "0.0.0.0"',
        jvm_options='-Xms1g\n-Xmx1g',
        log4j2_properties='logger.logstash.name = logstash',
    )


@pytest.fixture
def agent_connection(db, agent_policy):
    return Connection.objects.create(
        name='Test Agent',
        connection_type='AGENT',
        host='192.168.1.10',
        port=22,
        agent_id='test-agent-001',
        policy=agent_policy,
    )


# ---------------------------------------------------------------------------
# GET /api/connections/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestConnectionList:

    def test_list_returns_200(self, authenticated_client, centralized_connection):
        response = authenticated_client.get('/api/connections/')
        assert response.status_code == 200

    def test_list_returns_json_array(self, authenticated_client, centralized_connection):
        response = authenticated_client.get('/api/connections/')
        data = response.json()
        assert isinstance(data, list)

    def test_list_includes_connection(self, authenticated_client, centralized_connection):
        response = authenticated_client.get('/api/connections/')
        ids = [c['id'] for c in response.json()]
        assert centralized_connection.id in ids

    def test_list_expected_fields(self, authenticated_client, centralized_connection):
        response = authenticated_client.get('/api/connections/')
        item = next(c for c in response.json() if c['id'] == centralized_connection.id)
        for field in ('id', 'name', 'connection_type', 'host', 'port',
                      'username', 'cloud_id', 'is_active', 'created_at', 'updated_at'):
            assert field in item, f"Missing field: {field}"

    def test_list_no_credentials_in_response(self, authenticated_client, centralized_connection):
        response = authenticated_client.get('/api/connections/')
        body = response.content.decode()
        assert 'changeme' not in body
        assert 'password' not in body

    def test_list_no_auth_returns_401(self, client):
        response = client.get('/api/connections/')
        assert response.status_code == 401

    def test_list_via_api_key_header(self, client, api_key_header, centralized_connection):
        response = client.get('/api/connections/', **api_key_header)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_includes_agent_connection(self, authenticated_client, centralized_connection, agent_connection):
        response = authenticated_client.get('/api/connections/')
        ids = [c['id'] for c in response.json()]
        assert agent_connection.id in ids

    def test_list_empty_when_no_connections(self, authenticated_client):
        Connection.objects.all().delete()
        response = authenticated_client.get('/api/connections/')
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# POST /api/connections/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestConnectionCreate:

    @patch('API.connections_views.manager_views.test_connectivity')
    def test_create_success_returns_201(self, mock_test, authenticated_client):
        mock_test.return_value = (True, 'ok')
        response = authenticated_client.post(
            '/api/connections/',
            data=json.dumps({
                'name': 'New Conn',
                'connection_type': 'CENTRALIZED',
                'connection_mode': 'url',
                'auth_type': 'basic',
                'host': 'https://es.example.com',
                'port': 9200,
                'username': 'elastic',
                'password': 'changeme',
            }),
            content_type='application/json',
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert 'connection_id' in data

    @patch('API.connections_views.manager_views.test_connectivity')
    def test_create_persists_to_db(self, mock_test, authenticated_client):
        mock_test.return_value = (True, 'ok')
        authenticated_client.post(
            '/api/connections/',
            data=json.dumps({
                'name': 'Persist Test',
                'connection_type': 'CENTRALIZED',
                'connection_mode': 'url',
                'auth_type': 'basic',
                'host': 'https://es.example.com',
                'port': 9200,
                'username': 'elastic',
                'password': 'changeme',
            }),
            content_type='application/json',
        )
        assert Connection.objects.filter(name='Persist Test').exists()

    @patch('API.connections_views.manager_views.test_connectivity')
    def test_create_connectivity_fail_returns_422(self, mock_test, authenticated_client):
        mock_test.return_value = (False, 'Connection timed out')
        response = authenticated_client.post(
            '/api/connections/',
            data=json.dumps({
                'name': 'Bad Conn',
                'connection_type': 'CENTRALIZED',
                'connection_mode': 'url',
                'auth_type': 'basic',
                'host': 'https://bad.example.com',
                'port': 9200,
                'username': 'elastic',
                'password': 'changeme',
            }),
            content_type='application/json',
        )
        assert response.status_code == 422
        assert response.json()['success'] is False

    @patch('API.connections_views.manager_views.test_connectivity')
    def test_create_connectivity_fail_rolls_back_row(self, mock_test, authenticated_client):
        mock_test.return_value = (False, 'Connection timed out')
        authenticated_client.post(
            '/api/connections/',
            data=json.dumps({
                'name': 'Rollback Test',
                'connection_type': 'CENTRALIZED',
                'connection_mode': 'url',
                'auth_type': 'basic',
                'host': 'https://bad.example.com',
                'port': 9200,
                'username': 'elastic',
                'password': 'changeme',
            }),
            content_type='application/json',
        )
        assert not Connection.objects.filter(name='Rollback Test').exists()

    def test_create_invalid_form_returns_400(self, authenticated_client):
        response = authenticated_client.post(
            '/api/connections/',
            data=json.dumps({'name': '', 'connection_type': 'CENTRALIZED'}),
            content_type='application/json',
        )
        assert response.status_code == 400
        assert response.json()['success'] is False

    def test_create_no_auth_returns_401(self, client):
        response = client.post('/api/connections/', data='{}', content_type='application/json')
        assert response.status_code == 401

    def test_create_wrong_method_returns_405(self, authenticated_client):
        response = authenticated_client.put('/api/connections/', data='{}', content_type='application/json')
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# GET /api/connections/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestConnectionGet:

    def test_get_returns_200(self, authenticated_client, centralized_connection):
        response = authenticated_client.get(f'/api/connections/{centralized_connection.id}/')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['connection']['id'] == centralized_connection.id

    def test_get_returns_expected_fields(self, authenticated_client, centralized_connection):
        response = authenticated_client.get(f'/api/connections/{centralized_connection.id}/')
        conn = response.json()['connection']
        for field in ('id', 'name', 'connection_type', 'host', 'port',
                      'username', 'is_active', 'created_at', 'updated_at'):
            assert field in conn, f"Missing field: {field}"

    def test_get_no_credentials_in_response(self, authenticated_client, centralized_connection):
        response = authenticated_client.get(f'/api/connections/{centralized_connection.id}/')
        body = response.content.decode()
        assert 'changeme' not in body

    def test_get_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.get('/api/connections/99999/')
        assert response.status_code == 404
        assert response.json()['success'] is False

    def test_get_no_auth_returns_401(self, client, centralized_connection):
        response = client.get(f'/api/connections/{centralized_connection.id}/')
        assert response.status_code == 401

    def test_get_works_for_agent_connection(self, authenticated_client, agent_connection):
        response = authenticated_client.get(f'/api/connections/{agent_connection.id}/')
        assert response.status_code == 200
        assert response.json()['connection']['connection_type'] == 'AGENT'


# ---------------------------------------------------------------------------
# PUT /api/connections/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestConnectionUpdate:

    @patch('API.connections_views.manager_views.test_connectivity')
    def test_update_success(self, mock_test, authenticated_client, centralized_connection):
        mock_test.return_value = (True, 'ok')
        response = authenticated_client.put(
            f'/api/connections/{centralized_connection.id}/',
            data=json.dumps({
                'name': 'Updated Name',
                'connection_type': 'CENTRALIZED',
                'connection_mode': 'url',
                'auth_type': 'basic',
                'host': 'https://new-es.example.com',
                'port': 9200,
                'username': 'elastic',
                'password': 'newpass',
            }),
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json()['success'] is True
        centralized_connection.refresh_from_db()
        assert centralized_connection.name == 'Updated Name'

    @patch('API.connections_views.manager_views.test_connectivity')
    def test_update_connectivity_fail_returns_422_and_rolls_back(self, mock_test, authenticated_client, centralized_connection):
        mock_test.return_value = (False, 'Timed out')
        original_name = centralized_connection.name
        authenticated_client.put(
            f'/api/connections/{centralized_connection.id}/',
            data=json.dumps({
                'name': 'Should Not Stick',
                'connection_type': 'CENTRALIZED',
                'connection_mode': 'url',
                'auth_type': 'basic',
                'host': 'https://bad.example.com',
                'port': 9200,
                'username': 'elastic',
                'password': 'newpass',
            }),
            content_type='application/json',
        )
        centralized_connection.refresh_from_db()
        assert centralized_connection.name == original_name

    def test_update_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.put(
            '/api/connections/99999/',
            data=json.dumps({'name': 'x', 'connection_type': 'CENTRALIZED'}),
            content_type='application/json',
        )
        assert response.status_code == 404

    def test_update_no_auth_returns_401(self, client, centralized_connection):
        response = client.put(
            f'/api/connections/{centralized_connection.id}/',
            data='{}', content_type='application/json',
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/connections/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestConnectionDelete:

    def test_delete_success(self, authenticated_client, centralized_connection):
        conn_id = centralized_connection.id
        response = authenticated_client.delete(f'/api/connections/{conn_id}/')
        assert response.status_code == 200
        assert response.json()['success'] is True
        assert not Connection.objects.filter(id=conn_id).exists()

    def test_delete_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.delete('/api/connections/99999/')
        assert response.status_code == 404

    def test_delete_no_auth_returns_401(self, client, centralized_connection):
        response = client.delete(f'/api/connections/{centralized_connection.id}/')
        assert response.status_code == 401

    def test_delete_wrong_method_returns_405(self, authenticated_client, centralized_connection):
        response = authenticated_client.patch(f'/api/connections/{centralized_connection.id}/')
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# POST /api/connections/{id}/test/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestConnectionTest:

    @patch('API.connections_views.manager_views.test_connectivity')
    def test_test_success(self, mock_test, authenticated_client, centralized_connection):
        mock_test.return_value = (True, '{"cluster_name": "my-cluster"}')
        response = authenticated_client.post(f'/api/connections/{centralized_connection.id}/test/')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'detail' in data

    @patch('API.connections_views.manager_views.test_connectivity')
    def test_test_failure_returns_422(self, mock_test, authenticated_client, centralized_connection):
        mock_test.return_value = (False, 'Connection refused')
        response = authenticated_client.post(f'/api/connections/{centralized_connection.id}/test/')
        assert response.status_code == 422
        assert response.json()['success'] is False

    def test_test_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.post('/api/connections/99999/test/')
        assert response.status_code == 404

    def test_test_no_auth_returns_401(self, client, centralized_connection):
        response = client.post(f'/api/connections/{centralized_connection.id}/test/')
        assert response.status_code == 401

    def test_test_wrong_method_returns_405(self, authenticated_client, centralized_connection):
        response = authenticated_client.get(f'/api/connections/{centralized_connection.id}/test/')
        assert response.status_code == 405

    @patch('API.connections_views.manager_views.test_connectivity')
    def test_test_does_not_modify_connection(self, mock_test, authenticated_client, centralized_connection):
        """Connectivity test is read-only — connection row must not change."""
        mock_test.return_value = (True, 'ok')
        original_updated = centralized_connection.updated_at
        authenticated_client.post(f'/api/connections/{centralized_connection.id}/test/')
        centralized_connection.refresh_from_db()
        assert centralized_connection.updated_at == original_updated
