#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.test_resources import authenticated_client, test_user
from PipelineManager.models import Connection, Policy, Pipeline, Keystore, EnrollmentToken

from unittest.mock import patch
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
def test_policy_with_pipelines(db):
    """Create a test policy with pipelines"""
    policy = Policy.objects.create(
        name='Policy With Pipelines',
        settings_path='/etc/logstash/',
        logs_path='/var/log/logstash',
        binary_path='/usr/share/logstash/bin',
        logstash_yml='http.host: "0.0.0.0"',
        jvm_options='-Xms1g\n-Xmx1g',
        log4j2_properties='logger.logstash.name = logstash'
    )
    
    # Create pipelines
    Pipeline.objects.create(
        policy=policy,
        name='pipeline1',
        lscl='input {} filter {} output {}'
    )
    Pipeline.objects.create(
        policy=policy,
        name='pipeline2',
        lscl='input {} filter {} output {}'
    )
    
    # Create keystore entries
    Keystore.objects.create(
        policy=policy,
        key_name='key1',
        key_value='value1'
    )
    
    return policy


@pytest.fixture
def test_enrollment_token(db, test_policy):
    """Create a test enrollment token"""
    token = EnrollmentToken.objects.create(
        policy=test_policy,
        name='test_token',
        token='test_token_value_123'
    )
    return token


# ============================================================================
# GetPolicies Tests
# ============================================================================

@pytest.mark.django_db
class TestGetPolicies:
    """Tests for the get_policies endpoint"""

    def test_get_policies_success(self, authenticated_client, test_policy):
        """Test successful retrieval of policies"""
        response = authenticated_client.get('/ConnectionManager/GetPolicies/')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'policies' in data
        assert len(data['policies']) >= 1
        
        # Find our test policy
        policy_names = [p['name'] for p in data['policies']]
        assert 'Test Policy' in policy_names

    def test_get_policies_includes_connection_count(self, authenticated_client, test_policy):
        """Test that policies include connection count"""
        # Create an agent connection
        Connection.objects.create(
            name='Test Agent',
            connection_type='AGENT',
            host='agent.example.com',
            agent_id='test-001',
            is_active=True,
            policy=test_policy
        )

        response = authenticated_client.get('/ConnectionManager/GetPolicies/')

        assert response.status_code == 200
        data = response.json()
        
        # Find our test policy
        test_policy_data = next(p for p in data['policies'] if p['name'] == 'Test Policy')
        assert test_policy_data['connection_count'] == 1

    def test_get_policies_empty(self, authenticated_client):
        """Test getting policies when none exist"""
        Policy.objects.all().delete()
        
        response = authenticated_client.get('/ConnectionManager/GetPolicies/')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['policies']) == 0


# ============================================================================
# AddPolicy Tests
# ============================================================================

@pytest.mark.django_db
class TestAddPolicy:
    """Tests for the add_policy endpoint"""

    def test_add_policy_success(self, authenticated_client):
        """Test successful policy creation"""
        response = authenticated_client.post(
            '/ConnectionManager/AddPolicy/',
            data=json.dumps({
                'name': 'New Policy',
                'settings_path': '/etc/logstash/',
                'logs_path': '/var/log/logstash',
                'binary_path': '/usr/share/logstash/bin',
                'logstash_yml': 'http.host: "0.0.0.0"',
                'jvm_options': '-Xms1g\n-Xmx1g',
                'log4j2_properties': 'logger.logstash.name = logstash'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'policy_id' in data
        assert data['policy_name'] == 'New Policy'

        # Verify policy was created
        assert Policy.objects.filter(name='New Policy').exists()

        # Verify enrollment token was created
        policy = Policy.objects.get(name='New Policy')
        assert EnrollmentToken.objects.filter(policy=policy, name='default').exists()

    def test_add_policy_with_defaults(self, authenticated_client):
        """Test policy creation with default values"""
        response = authenticated_client.post(
            '/ConnectionManager/AddPolicy/',
            data=json.dumps({
                'name': 'Minimal Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify policy was created with defaults
        policy = Policy.objects.get(name='Minimal Policy')
        assert policy.settings_path == '/etc/logstash/'
        assert policy.logs_path == '/var/log/logstash'
        assert policy.binary_path == '/usr/share/logstash/bin'
        assert len(policy.logstash_yml) > 0  # Should have default config
        assert len(policy.jvm_options) > 0
        assert len(policy.log4j2_properties) > 0

    def test_add_policy_missing_name(self, authenticated_client):
        """Test policy creation without name"""
        response = authenticated_client.post(
            '/ConnectionManager/AddPolicy/',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy name is required' in data['error']

    def test_add_policy_duplicate_name(self, authenticated_client, test_policy):
        """Test creating policy with duplicate name"""
        response = authenticated_client.post(
            '/ConnectionManager/AddPolicy/',
            data=json.dumps({
                'name': 'Test Policy'  # Already exists
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'already exists' in data['error']

    def test_add_policy_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/AddPolicy/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_add_policy_invalid_json(self, authenticated_client):
        """Test policy creation with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/AddPolicy/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# UpdatePolicy Tests
# ============================================================================

@pytest.mark.django_db
class TestUpdatePolicy:
    """Tests for the update_policy endpoint"""

    def test_update_policy_success(self, authenticated_client, test_policy):
        """Test successful policy update"""
        response = authenticated_client.post(
            '/ConnectionManager/UpdatePolicy/',
            data=json.dumps({
                'policy_name': 'Test Policy',
                'settings_path': '/new/settings',
                'logstash_yml': 'http.host: "127.0.0.1"'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify policy was updated
        test_policy.refresh_from_db()
        assert test_policy.settings_path == '/new/settings'
        assert test_policy.logstash_yml == 'http.host: "127.0.0.1"'

    def test_update_policy_partial_update(self, authenticated_client, test_policy):
        """Test updating only some fields"""
        original_logs_path = test_policy.logs_path

        response = authenticated_client.post(
            '/ConnectionManager/UpdatePolicy/',
            data=json.dumps({
                'policy_name': 'Test Policy',
                'settings_path': '/updated/settings'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200

        # Verify only specified field was updated
        test_policy.refresh_from_db()
        assert test_policy.settings_path == '/updated/settings'
        assert test_policy.logs_path == original_logs_path  # Unchanged

    def test_update_policy_missing_name(self, authenticated_client):
        """Test updating policy without name"""
        response = authenticated_client.post(
            '/ConnectionManager/UpdatePolicy/',
            data=json.dumps({
                'settings_path': '/new/settings'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy name is required' in data['error']

    def test_update_policy_nonexistent(self, authenticated_client):
        """Test updating non-existent policy"""
        response = authenticated_client.post(
            '/ConnectionManager/UpdatePolicy/',
            data=json.dumps({
                'policy_name': 'Nonexistent Policy',
                'settings_path': '/new/settings'
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['error']

    def test_update_policy_default_policy_forbidden(self, authenticated_client):
        """Test that Default Policy cannot be updated"""
        # Create Default Policy
        Policy.objects.create(
            name='Default Policy',
            settings_path='/etc/logstash/',
            logs_path='/var/log/logstash',
            binary_path='/usr/share/logstash/bin'
        )

        response = authenticated_client.post(
            '/ConnectionManager/UpdatePolicy/',
            data=json.dumps({
                'policy_name': 'Default Policy',
                'settings_path': '/new/settings'
            }),
            content_type='application/json'
        )

        assert response.status_code == 403
        data = response.json()
        assert data['success'] is False
        assert 'Cannot update Default Policy' in data['error']

    def test_update_policy_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/UpdatePolicy/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_update_policy_invalid_json(self, authenticated_client):
        """Test policy update with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/UpdatePolicy/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# DeletePolicy Tests
# ============================================================================

@pytest.mark.django_db
class TestDeletePolicy:
    """Tests for the delete_policy endpoint"""

    def test_delete_policy_success(self, authenticated_client, test_policy):
        """Test successful policy deletion"""
        response = authenticated_client.post(
            '/ConnectionManager/DeletePolicy/',
            data=json.dumps({
                'policy_name': 'Test Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify policy was deleted
        assert not Policy.objects.filter(name='Test Policy').exists()

    def test_delete_policy_missing_name(self, authenticated_client):
        """Test deleting policy without name"""
        response = authenticated_client.post(
            '/ConnectionManager/DeletePolicy/',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy name is required' in data['error']

    def test_delete_policy_nonexistent(self, authenticated_client):
        """Test deleting non-existent policy"""
        response = authenticated_client.post(
            '/ConnectionManager/DeletePolicy/',
            data=json.dumps({
                'policy_name': 'Nonexistent Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['error']

    def test_delete_policy_default_policy_forbidden(self, authenticated_client):
        """Test that Default Policy cannot be deleted"""
        # Create Default Policy
        Policy.objects.create(
            name='Default Policy',
            settings_path='/etc/logstash/',
            logs_path='/var/log/logstash',
            binary_path='/usr/share/logstash/bin'
        )

        response = authenticated_client.post(
            '/ConnectionManager/DeletePolicy/',
            data=json.dumps({
                'policy_name': 'Default Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 403
        data = response.json()
        assert data['success'] is False
        assert 'Cannot delete Default Policy' in data['error']

    def test_delete_policy_in_use(self, authenticated_client, test_policy):
        """Test that policy in use cannot be deleted"""
        # Create a connection using this policy
        Connection.objects.create(
            name='Test Agent',
            connection_type='AGENT',
            host='agent.example.com',
            agent_id='test-001',
            is_active=True,
            policy=test_policy
        )

        response = authenticated_client.post(
            '/ConnectionManager/DeletePolicy/',
            data=json.dumps({
                'policy_name': 'Test Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'currently assigned to' in data['error']

        # Verify policy was not deleted
        assert Policy.objects.filter(name='Test Policy').exists()

    def test_delete_policy_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/DeletePolicy/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_delete_policy_invalid_json(self, authenticated_client):
        """Test policy deletion with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/DeletePolicy/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# ClonePolicy Tests
# ============================================================================

@pytest.mark.django_db
class TestClonePolicy:
    """Tests for the clone_policy endpoint"""

    def test_clone_policy_success(self, authenticated_client, test_policy_with_pipelines):
        """Test successful policy cloning"""
        response = authenticated_client.post(
            '/ConnectionManager/ClonePolicy/',
            data=json.dumps({
                'source_policy_id': test_policy_with_pipelines.id,
                'new_policy_name': 'Cloned Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'policy_id' in data
        assert data['policy_name'] == 'Cloned Policy'

        # Verify new policy was created
        cloned_policy = Policy.objects.get(name='Cloned Policy')
        assert cloned_policy.settings_path == test_policy_with_pipelines.settings_path
        assert cloned_policy.logstash_yml == test_policy_with_pipelines.logstash_yml

        # Verify pipelines were cloned
        assert Pipeline.objects.filter(policy=cloned_policy).count() == 2
        assert Pipeline.objects.filter(policy=cloned_policy, name='pipeline1').exists()
        assert Pipeline.objects.filter(policy=cloned_policy, name='pipeline2').exists()

        # Verify keystore entries were cloned
        assert Keystore.objects.filter(policy=cloned_policy).count() == 1
        assert Keystore.objects.filter(policy=cloned_policy, key_name='key1').exists()

        # Verify enrollment token was created
        assert EnrollmentToken.objects.filter(policy=cloned_policy, name='default').exists()

    def test_clone_policy_missing_source_id(self, authenticated_client):
        """Test cloning without source policy ID"""
        response = authenticated_client.post(
            '/ConnectionManager/ClonePolicy/',
            data=json.dumps({
                'new_policy_name': 'Cloned Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Source policy ID is required' in data['error']

    def test_clone_policy_missing_new_name(self, authenticated_client, test_policy):
        """Test cloning without new policy name"""
        response = authenticated_client.post(
            '/ConnectionManager/ClonePolicy/',
            data=json.dumps({
                'source_policy_id': test_policy.id
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'New policy name is required' in data['error']

    def test_clone_policy_duplicate_name(self, authenticated_client, test_policy):
        """Test cloning to existing policy name"""
        # Create another policy
        Policy.objects.create(
            name='Existing Policy',
            settings_path='/etc/logstash/',
            logs_path='/var/log/logstash',
            binary_path='/usr/share/logstash/bin'
        )

        response = authenticated_client.post(
            '/ConnectionManager/ClonePolicy/',
            data=json.dumps({
                'source_policy_id': test_policy.id,
                'new_policy_name': 'Existing Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'already exists' in data['error']

    def test_clone_policy_nonexistent_source(self, authenticated_client):
        """Test cloning non-existent source policy"""
        response = authenticated_client.post(
            '/ConnectionManager/ClonePolicy/',
            data=json.dumps({
                'source_policy_id': 99999,
                'new_policy_name': 'Cloned Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Source policy not found' in data['error']

    def test_clone_policy_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/ClonePolicy/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_clone_policy_invalid_json(self, authenticated_client):
        """Test policy cloning with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/ClonePolicy/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# GetEnrollmentTokens Tests
# ============================================================================

@pytest.mark.django_db
class TestGetEnrollmentTokens:
    """Tests for the get_enrollment_tokens endpoint"""

    def test_get_enrollment_tokens_success(self, authenticated_client, test_policy, test_enrollment_token):
        """Test successful retrieval of enrollment tokens"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetEnrollmentTokens/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['tokens']) >= 1
        
        # Verify token data
        token_data = next(t for t in data['tokens'] if t['name'] == 'test_token')
        assert token_data['raw_token'] == 'test_token_value_123'
        assert 'encoded_token' in token_data

    def test_get_enrollment_tokens_empty(self, authenticated_client, test_policy):
        """Test getting tokens when none exist"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetEnrollmentTokens/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['tokens']) == 0

    def test_get_enrollment_tokens_missing_policy_id(self, authenticated_client):
        """Test getting tokens without policy_id"""
        response = authenticated_client.get('/ConnectionManager/GetEnrollmentTokens/')

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy ID is required' in data['error']

    def test_get_enrollment_tokens_nonexistent_policy(self, authenticated_client):
        """Test getting tokens for non-existent policy"""
        response = authenticated_client.get('/ConnectionManager/GetEnrollmentTokens/?policy_id=99999')

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']


# ============================================================================
# AddEnrollmentToken Tests
# ============================================================================

@pytest.mark.django_db
class TestAddEnrollmentToken:
    """Tests for the add_enrollment_token endpoint"""

    def test_add_enrollment_token_success(self, authenticated_client, test_policy):
        """Test successful enrollment token creation"""
        response = authenticated_client.post(
            '/ConnectionManager/AddEnrollmentToken/',
            data=json.dumps({
                'policy_id': test_policy.id,
                'name': 'new_token'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'token_id' in data

        # Verify token was created
        assert EnrollmentToken.objects.filter(policy=test_policy, name='new_token').exists()

    def test_add_enrollment_token_default_name(self, authenticated_client, test_policy):
        """Test token creation with default name"""
        response = authenticated_client.post(
            '/ConnectionManager/AddEnrollmentToken/',
            data=json.dumps({
                'policy_id': test_policy.id
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify token was created with default name
        assert EnrollmentToken.objects.filter(policy=test_policy, name='default').exists()

    def test_add_enrollment_token_missing_policy_id(self, authenticated_client):
        """Test token creation without policy_id"""
        response = authenticated_client.post(
            '/ConnectionManager/AddEnrollmentToken/',
            data=json.dumps({
                'name': 'new_token'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy ID is required' in data['error']

    def test_add_enrollment_token_nonexistent_policy(self, authenticated_client):
        """Test token creation for non-existent policy"""
        response = authenticated_client.post(
            '/ConnectionManager/AddEnrollmentToken/',
            data=json.dumps({
                'policy_id': 99999,
                'name': 'new_token'
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']

    def test_add_enrollment_token_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/AddEnrollmentToken/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_add_enrollment_token_invalid_json(self, authenticated_client):
        """Test token creation with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/AddEnrollmentToken/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# DeleteEnrollmentToken Tests
# ============================================================================

@pytest.mark.django_db
class TestDeleteEnrollmentToken:
    """Tests for the delete_enrollment_token endpoint"""

    def test_delete_enrollment_token_success(self, authenticated_client, test_enrollment_token):
        """Test successful enrollment token deletion"""
        token_id = test_enrollment_token.id

        response = authenticated_client.post(
            '/ConnectionManager/DeleteEnrollmentToken/',
            data=json.dumps({
                'token_id': token_id
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify token was deleted
        assert not EnrollmentToken.objects.filter(id=token_id).exists()

    def test_delete_enrollment_token_missing_token_id(self, authenticated_client):
        """Test deleting token without token_id"""
        response = authenticated_client.post(
            '/ConnectionManager/DeleteEnrollmentToken/',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Token ID is required' in data['error']

    def test_delete_enrollment_token_nonexistent(self, authenticated_client):
        """Test deleting non-existent token"""
        response = authenticated_client.post(
            '/ConnectionManager/DeleteEnrollmentToken/',
            data=json.dumps({
                'token_id': 99999
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Enrollment token not found' in data['error']

    def test_delete_enrollment_token_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/DeleteEnrollmentToken/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_delete_enrollment_token_invalid_json(self, authenticated_client):
        """Test token deletion with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/DeleteEnrollmentToken/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']
