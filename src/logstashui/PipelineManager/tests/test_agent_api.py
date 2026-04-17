#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.test_resources import test_user
from PipelineManager.models import (
    ApiKey, Connection, EnrollmentToken, Keystore, Pipeline, Policy
)

from datetime import datetime, timezone
from unittest.mock import patch
import base64
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
        log4j2_properties='logger.logstash.name = logstash',
        keystore_password='test_password'
    )
    return policy


@pytest.fixture
def test_enrollment_token(db, test_policy):
    """Create a test enrollment token"""
    token = EnrollmentToken.objects.create(
        policy=test_policy,
        name='test_token',
        token='test_enrollment_token_12345'
    )
    return token


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
def test_api_key(db, test_agent_connection):
    """Create a test API key for agent authentication"""
    raw_key = 'test_api_key_12345'
    api_key = ApiKey.objects.create(
        connection=test_agent_connection,
        api_key=raw_key
    )
    return raw_key


@pytest.fixture
def test_pipeline(db, test_policy):
    """Create a test pipeline"""
    pipeline = Pipeline.objects.create(
        policy=test_policy,
        name='test_pipeline',
        lscl='input { beats { port => 5044 } } filter {} output { elasticsearch { hosts => ["localhost:9200"] } }',
        pipeline_workers=2,
        pipeline_batch_size=256
    )
    return pipeline


@pytest.fixture
def test_keystore_entry(db, test_policy):
    """Create a test keystore entry"""
    entry = Keystore.objects.create(
        policy=test_policy,
        key_name='test_key',
        key_value='test_value'
    )
    return entry


# ============================================================================
# Enroll Endpoint Tests
# ============================================================================

@pytest.mark.django_db
class TestEnrollEndpoint:
    """Tests for the /enroll agent API endpoint"""

    def test_enroll_success(self, client, test_enrollment_token):
        """Test successful agent enrollment"""
        token_payload = {'enrollment_token': test_enrollment_token.token}
        encoded_token = base64.b64encode(json.dumps(token_payload).encode()).decode()

        response = client.post(
            '/ConnectionManager/Enroll/',
            data=json.dumps({
                'enrollment_token': encoded_token,
                'host': 'new-agent.example.com',
                'agent_id': 'new-agent-001'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'api_key' in data
        assert data['policy_id'] == test_enrollment_token.policy.id
        assert 'connection_id' in data
        assert 'policy_config' in data

        # Verify connection was created
        assert Connection.objects.filter(agent_id='new-agent-001').exists()
        connection = Connection.objects.get(agent_id='new-agent-001')
        assert connection.name == 'new-agent.example.com'
        assert connection.host == 'new-agent.example.com'
        assert connection.connection_type == 'AGENT'
        assert connection.policy == test_enrollment_token.policy

        # Verify API key was created
        assert connection.api_keys.exists()

    def test_enroll_reenrollment_deletes_old_connection(self, client, test_enrollment_token, test_agent_connection):
        """Test that re-enrolling an agent deletes the old connection"""
        old_connection_id = test_agent_connection.id
        agent_id = test_agent_connection.agent_id

        token_payload = {'enrollment_token': test_enrollment_token.token}
        encoded_token = base64.b64encode(json.dumps(token_payload).encode()).decode()

        response = client.post(
            '/ConnectionManager/Enroll/',
            data=json.dumps({
                'enrollment_token': encoded_token,
                'host': 'updated-agent.example.com',
                'agent_id': agent_id
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Old connection should be deleted
        assert not Connection.objects.filter(id=old_connection_id).exists()

        # New connection should exist with same agent_id
        assert Connection.objects.filter(agent_id=agent_id).exists()
        new_connection = Connection.objects.get(agent_id=agent_id)
        assert new_connection.id != old_connection_id
        assert new_connection.host == 'updated-agent.example.com'

    def test_enroll_missing_enrollment_token(self, client):
        """Test enrollment with missing enrollment_token"""
        response = client.post(
            '/ConnectionManager/Enroll/',
            data=json.dumps({
                'host': 'agent.example.com',
                'agent_id': 'agent-001'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Missing required fields' in data['error']

    def test_enroll_missing_host(self, client, test_enrollment_token):
        """Test enrollment with missing host"""
        token_payload = {'enrollment_token': test_enrollment_token.token}
        encoded_token = base64.b64encode(json.dumps(token_payload).encode()).decode()

        response = client.post(
            '/ConnectionManager/Enroll/',
            data=json.dumps({
                'enrollment_token': encoded_token,
                'agent_id': 'agent-001'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Missing required fields' in data['error']

    def test_enroll_missing_agent_id(self, client, test_enrollment_token):
        """Test enrollment with missing agent_id"""
        token_payload = {'enrollment_token': test_enrollment_token.token}
        encoded_token = base64.b64encode(json.dumps(token_payload).encode()).decode()

        response = client.post(
            '/ConnectionManager/Enroll/',
            data=json.dumps({
                'enrollment_token': encoded_token,
                'host': 'agent.example.com'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Missing required fields' in data['error']

    def test_enroll_invalid_json(self, client):
        """Test enrollment with invalid JSON"""
        response = client.post(
            '/ConnectionManager/Enroll/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']

    def test_enroll_invalid_token_format(self, client):
        """Test enrollment with invalid base64 token format"""
        response = client.post(
            '/ConnectionManager/Enroll/',
            data=json.dumps({
                'enrollment_token': 'not-valid-base64!!!',
                'host': 'agent.example.com',
                'agent_id': 'agent-001'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid enrollment token format' in data['error']

    def test_enroll_invalid_token_payload(self, client):
        """Test enrollment with token missing enrollment_token field"""
        token_payload = {'wrong_field': 'value'}
        encoded_token = base64.b64encode(json.dumps(token_payload).encode()).decode()

        response = client.post(
            '/ConnectionManager/Enroll/',
            data=json.dumps({
                'enrollment_token': encoded_token,
                'host': 'agent.example.com',
                'agent_id': 'agent-001'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid token payload' in data['error']

    def test_enroll_nonexistent_token(self, client):
        """Test enrollment with non-existent enrollment token"""
        token_payload = {'enrollment_token': 'nonexistent_token'}
        encoded_token = base64.b64encode(json.dumps(token_payload).encode()).decode()

        response = client.post(
            '/ConnectionManager/Enroll/',
            data=json.dumps({
                'enrollment_token': encoded_token,
                'host': 'agent.example.com',
                'agent_id': 'agent-001'
            }),
            content_type='application/json'
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'Invalid enrollment token' in data['error']

    def test_enroll_wrong_http_method(self, client):
        """Test that GET requests are rejected"""
        response = client.get('/ConnectionManager/Enroll/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']


# ============================================================================
# CheckIn Endpoint Tests
# ============================================================================

@pytest.mark.django_db
class TestCheckInEndpoint:
    """Tests for the /check-in agent API endpoint"""

    def test_checkin_success(self, client, test_agent_connection, test_api_key):
        """Test successful agent check-in"""
        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({
                'connection_id': test_agent_connection.id
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['message'] == 'Check-in successful'
        assert 'timestamp' in data
        assert data['current_revision_number'] == test_agent_connection.policy.current_revision_number
        assert data['settings_path'] == test_agent_connection.policy.settings_path
        assert data['restart'] is False

        # Verify last_check_in was updated
        test_agent_connection.refresh_from_db()
        assert test_agent_connection.last_check_in is not None

    def test_checkin_with_status_blob(self, client, test_agent_connection, test_api_key):
        """Test check-in with status blob update"""
        status_blob = {
            'logstash_api': {'accessible': True, 'status': 'green'},
            'health_report': {'status': 'green'}
        }

        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'status_blob': status_blob
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify status_blob was saved
        test_agent_connection.refresh_from_db()
        assert test_agent_connection.status_blob == status_blob

    def test_checkin_restart_flag(self, client, test_agent_connection, test_api_key):
        """Test check-in with restart flag set"""
        test_agent_connection.restart_on_next_checkin = True
        test_agent_connection.save()

        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({
                'connection_id': test_agent_connection.id
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['restart'] is True

        # Verify restart flag was cleared
        test_agent_connection.refresh_from_db()
        assert test_agent_connection.restart_on_next_checkin is False

    def test_checkin_missing_authorization_header(self, client, test_agent_connection):
        """Test check-in without Authorization header"""
        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({
                'connection_id': test_agent_connection.id
            }),
            content_type='application/json'
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'Missing or invalid Authorization header' in data['error']

    def test_checkin_invalid_authorization_format(self, client, test_agent_connection):
        """Test check-in with invalid Authorization header format"""
        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({
                'connection_id': test_agent_connection.id
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer invalid_format'
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'Missing or invalid Authorization header' in data['error']

    def test_checkin_empty_api_key(self, client, test_agent_connection):
        """Test check-in with empty API key"""
        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({
                'connection_id': test_agent_connection.id
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION='ApiKey '
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'API key is empty' in data['error']

    def test_checkin_missing_connection_id(self, client, test_api_key):
        """Test check-in without connection_id"""
        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Missing connection_id' in data['error']

    def test_checkin_invalid_connection_id(self, client, test_api_key):
        """Test check-in with non-existent connection_id"""
        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({
                'connection_id': 99999
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'Invalid connection_id' in data['error']

    def test_checkin_invalid_api_key(self, client, test_agent_connection):
        """Test check-in with wrong API key"""
        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({
                'connection_id': test_agent_connection.id
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION='ApiKey wrong_api_key'
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'Invalid API key' in data['error']

    def test_checkin_no_policy_assigned(self, client, test_api_key):
        """Test check-in when connection has no policy"""
        # Create connection without policy
        connection = Connection.objects.create(
            name='No Policy Agent',
            connection_type='AGENT',
            host='nopolicy.example.com',
            agent_id='nopolicy-001',
            is_active=True,
            policy=None
        )
        raw_key = 'nopolicy_api_key'
        ApiKey.objects.create(connection=connection, api_key=raw_key)

        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({
                'connection_id': connection.id
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {raw_key}'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'No policy assigned' in data['error']

    def test_checkin_wrong_http_method(self, client):
        """Test that GET requests are rejected"""
        response = client.get('/ConnectionManager/CheckIn/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_checkin_invalid_json(self, client, test_api_key):
        """Test check-in with invalid JSON"""
        response = client.post(
            '/ConnectionManager/CheckIn/',
            data='not valid json',
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# GetConfigChanges Endpoint Tests
# ============================================================================

@pytest.mark.django_db
class TestGetConfigChangesEndpoint:
    """Tests for the /get-config-changes agent API endpoint"""

    def test_get_config_changes_no_changes(self, client, test_agent_connection, test_api_key, test_policy):
        """Test config changes when everything is in sync"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': test_policy.logstash_yml_hash,
                'jvm_options_hash': test_policy.jvm_options_hash,
                'log4j2_properties_hash': test_policy.log4j2_properties_hash,
                'settings_path': test_policy.settings_path,
                'logs_path': test_policy.logs_path,
                'binary_path': test_policy.binary_path,
                'keystore_password_hash': test_policy.keystore_password_hash,
                'keystore': {},
                'pipelines': {}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['logstash_yml'] is False
        assert data['changes']['jvm_options'] is False
        assert data['changes']['log4j2_properties'] is False
        assert data['changes']['settings_path'] is False
        assert data['changes']['logs_path'] is False
        assert data['changes']['binary_path'] is False
        assert data['changes']['keystore'] is False
        assert data['changes']['pipelines'] is False

    def test_get_config_changes_logstash_yml_changed(self, client, test_agent_connection, test_api_key, test_policy):
        """Test detection of logstash.yml changes"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': 'wrong_hash',
                'jvm_options_hash': test_policy.jvm_options_hash,
                'log4j2_properties_hash': test_policy.log4j2_properties_hash,
                'settings_path': test_policy.settings_path,
                'logs_path': test_policy.logs_path,
                'binary_path': test_policy.binary_path,
                'keystore_password_hash': test_policy.keystore_password_hash,
                'keystore': {},
                'pipelines': {}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['logstash_yml'] == test_policy.logstash_yml
        assert data['changes']['jvm_options'] is False

    def test_get_config_changes_all_config_files_changed(self, client, test_agent_connection, test_api_key, test_policy):
        """Test detection of all config file changes"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': 'wrong1',
                'jvm_options_hash': 'wrong2',
                'log4j2_properties_hash': 'wrong3',
                'settings_path': test_policy.settings_path,
                'logs_path': test_policy.logs_path,
                'binary_path': test_policy.binary_path,
                'keystore_password_hash': test_policy.keystore_password_hash,
                'keystore': {},
                'pipelines': {}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['logstash_yml'] == test_policy.logstash_yml
        assert data['changes']['jvm_options'] == test_policy.jvm_options
        assert data['changes']['log4j2_properties'] == test_policy.log4j2_properties

    def test_get_config_changes_paths_changed(self, client, test_agent_connection, test_api_key, test_policy):
        """Test detection of path changes"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': test_policy.logstash_yml_hash,
                'jvm_options_hash': test_policy.jvm_options_hash,
                'log4j2_properties_hash': test_policy.log4j2_properties_hash,
                'settings_path': '/wrong/settings',
                'logs_path': '/wrong/logs',
                'binary_path': '/wrong/binary',
                'keystore_password_hash': test_policy.keystore_password_hash,
                'keystore': {},
                'pipelines': {}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['settings_path'] == test_policy.settings_path
        assert data['changes']['logs_path'] == test_policy.logs_path
        assert data['changes']['binary_path'] == test_policy.binary_path

    def test_get_config_changes_keystore_new_entry(self, client, test_agent_connection, test_api_key, test_policy, test_keystore_entry):
        """Test detection of new keystore entry"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': test_policy.logstash_yml_hash,
                'jvm_options_hash': test_policy.jvm_options_hash,
                'log4j2_properties_hash': test_policy.log4j2_properties_hash,
                'settings_path': test_policy.settings_path,
                'logs_path': test_policy.logs_path,
                'binary_path': test_policy.binary_path,
                'keystore_password_hash': test_policy.keystore_password_hash,
                'keystore': {},
                'pipelines': {}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['keystore'] is not False
        assert 'test_key' in data['changes']['keystore']['set']
        assert len(data['changes']['keystore']['delete']) == 0

    def test_get_config_changes_keystore_delete_entry(self, client, test_agent_connection, test_api_key, test_policy):
        """Test detection of keystore entry to delete"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': test_policy.logstash_yml_hash,
                'jvm_options_hash': test_policy.jvm_options_hash,
                'log4j2_properties_hash': test_policy.log4j2_properties_hash,
                'settings_path': test_policy.settings_path,
                'logs_path': test_policy.logs_path,
                'binary_path': test_policy.binary_path,
                'keystore_password_hash': test_policy.keystore_password_hash,
                'keystore': {'old_key': 'some_hash'},
                'pipelines': {}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['keystore'] is not False
        assert 'old_key' in data['changes']['keystore']['delete']

    def test_get_config_changes_keystore_password_changed(self, client, test_agent_connection, test_api_key, test_policy, test_keystore_entry):
        """Test detection of keystore password change"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': test_policy.logstash_yml_hash,
                'jvm_options_hash': test_policy.jvm_options_hash,
                'log4j2_properties_hash': test_policy.log4j2_properties_hash,
                'settings_path': test_policy.settings_path,
                'logs_path': test_policy.logs_path,
                'binary_path': test_policy.binary_path,
                'keystore_password_hash': 'wrong_password_hash',
                'keystore': {},
                'pipelines': {}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['keystore_password'] is not False
        # When password changes, all keystore entries are re-encrypted
        assert data['changes']['keystore'] is not False

    def test_get_config_changes_pipeline_new(self, client, test_agent_connection, test_api_key, test_policy, test_pipeline):
        """Test detection of new pipeline"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': test_policy.logstash_yml_hash,
                'jvm_options_hash': test_policy.jvm_options_hash,
                'log4j2_properties_hash': test_policy.log4j2_properties_hash,
                'settings_path': test_policy.settings_path,
                'logs_path': test_policy.logs_path,
                'binary_path': test_policy.binary_path,
                'keystore_password_hash': test_policy.keystore_password_hash,
                'keystore': {},
                'pipelines': {}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['pipelines'] is not False
        assert 'test_pipeline' in data['changes']['pipelines']['set']
        assert data['changes']['pipelines']['set']['test_pipeline']['lscl'] == test_pipeline.lscl

    def test_get_config_changes_pipeline_delete(self, client, test_agent_connection, test_api_key, test_policy):
        """Test detection of pipeline to delete"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': test_policy.logstash_yml_hash,
                'jvm_options_hash': test_policy.jvm_options_hash,
                'log4j2_properties_hash': test_policy.log4j2_properties_hash,
                'settings_path': test_policy.settings_path,
                'logs_path': test_policy.logs_path,
                'binary_path': test_policy.binary_path,
                'keystore_password_hash': test_policy.keystore_password_hash,
                'keystore': {},
                'pipelines': {'old_pipeline': {'config_hash': 'some_hash'}}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['pipelines'] is not False
        assert 'old_pipeline' in data['changes']['pipelines']['delete']

    def test_get_config_changes_pipeline_updated(self, client, test_agent_connection, test_api_key, test_policy, test_pipeline):
        """Test detection of pipeline config change"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id,
                'logstash_yml_hash': test_policy.logstash_yml_hash,
                'jvm_options_hash': test_policy.jvm_options_hash,
                'log4j2_properties_hash': test_policy.log4j2_properties_hash,
                'settings_path': test_policy.settings_path,
                'logs_path': test_policy.logs_path,
                'binary_path': test_policy.binary_path,
                'keystore_password_hash': test_policy.keystore_password_hash,
                'keystore': {},
                'pipelines': {'test_pipeline': {'config_hash': 'wrong_hash'}}
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['changes']['pipelines'] is not False
        assert 'test_pipeline' in data['changes']['pipelines']['set']

    def test_get_config_changes_missing_connection_id(self, client, test_api_key):
        """Test get-config-changes without connection_id"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Connection ID is required' in data['error']

    def test_get_config_changes_missing_authorization(self, client, test_agent_connection):
        """Test get-config-changes without Authorization header"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id
            }),
            content_type='application/json'
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'Invalid authorization header' in data['error']

    def test_get_config_changes_invalid_authorization_format(self, client, test_agent_connection):
        """Test get-config-changes with invalid Authorization format"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer wrong_format'
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'Invalid authorization header' in data['error']

    def test_get_config_changes_invalid_connection_id(self, client, test_api_key):
        """Test get-config-changes with non-existent connection_id"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': 99999
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Connection not found' in data['error']

    def test_get_config_changes_invalid_api_key(self, client, test_agent_connection):
        """Test get-config-changes with wrong API key"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': test_agent_connection.id
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION='ApiKey wrong_key'
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'Invalid API key' in data['error']

    def test_get_config_changes_no_policy(self, client, test_api_key):
        """Test get-config-changes when connection has no policy"""
        connection = Connection.objects.create(
            name='No Policy Agent',
            connection_type='AGENT',
            host='nopolicy.example.com',
            agent_id='nopolicy-002',
            is_active=True,
            policy=None
        )
        raw_key = 'nopolicy_api_key_2'
        ApiKey.objects.create(connection=connection, api_key=raw_key)

        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': connection.id
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {raw_key}'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'No policy assigned' in data['error']

    def test_get_config_changes_wrong_http_method(self, client):
        """Test that GET requests are rejected"""
        response = client.get('/ConnectionManager/GetConfigChanges/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_get_config_changes_invalid_json(self, client, test_api_key):
        """Test get-config-changes with invalid JSON"""
        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data='not valid json',
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {test_api_key}'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# Helper Function Tests
# ============================================================================

@pytest.mark.django_db
class TestEncryptForAgent:
    """Tests for the _encrypt_for_agent helper function"""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption/decryption works correctly"""
        from PipelineManager.agent_api import _encrypt_for_agent
        from cryptography.fernet import Fernet
        import hashlib

        raw_api_key = 'test_key_12345'
        plaintext = 'secret_value'

        encrypted = _encrypt_for_agent(raw_api_key, plaintext)

        # Decrypt using same key
        key = base64.urlsafe_b64encode(hashlib.sha256(raw_api_key.encode('utf-8')).digest())
        decrypted = Fernet(key).decrypt(encrypted.encode('utf-8')).decode('utf-8')

        assert decrypted == plaintext

    def test_different_keys_produce_different_ciphertext(self):
        """Test that different API keys produce different ciphertext"""
        from PipelineManager.agent_api import _encrypt_for_agent

        plaintext = 'secret_value'
        encrypted1 = _encrypt_for_agent('key1', plaintext)
        encrypted2 = _encrypt_for_agent('key2', plaintext)

        assert encrypted1 != encrypted2
