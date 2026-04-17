#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.test_resources import authenticated_client, test_user
from PipelineManager.models import Connection, Keystore, Pipeline, Policy, Revision

from datetime import datetime, timezone
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
        log4j2_properties='logger.logstash.name = logstash',
        keystore_password='test_password'
    )
    return policy


@pytest.fixture
def test_policy_with_revision(db, test_user):
    """Create a test policy with an existing revision"""
    policy = Policy.objects.create(
        name='Policy With Revision',
        settings_path='/etc/logstash/',
        logs_path='/var/log/logstash',
        binary_path='/usr/share/logstash/bin',
        logstash_yml='http.host: "0.0.0.0"',
        jvm_options='-Xms1g\n-Xmx1g',
        log4j2_properties='logger.logstash.name = logstash',
        current_revision_number=1
    )
    
    # Create a revision
    Revision.objects.create(
        policy=policy,
        revision_number=1,
        snapshot_json={
            'logstash_yml': 'http.host: "0.0.0.0"',
            'jvm_options': '-Xms1g\n-Xmx1g',
            'log4j2_properties': 'logger.logstash.name = logstash',
            'settings_path': '/etc/logstash/',
            'logs_path': '/var/log/logstash',
            'binary_path': '/usr/share/logstash/bin',
            'pipelines': [],
            'keystore': [],
            'keystore_password_hash': ''
        },
        created_by=test_user.username
    )
    
    return policy


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


# ============================================================================
# Generate Enrollment Token Tests
# ============================================================================

@pytest.mark.django_db
class TestGenerateEnrollmentToken:
    """Tests for the generate_enrollment_token endpoint"""

    def test_generate_enrollment_token_success(self, authenticated_client):
        """Test successful enrollment token generation"""
        response = authenticated_client.post(
            '/ConnectionManager/GenerateEnrollmentToken/',
            data=json.dumps({
                'policy_name': 'Test Policy'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'enrollment_token' in data
        assert len(data['enrollment_token']) > 0

    def test_generate_enrollment_token_default_policy(self, authenticated_client):
        """Test enrollment token generation with default policy name"""
        response = authenticated_client.post(
            '/ConnectionManager/GenerateEnrollmentToken/',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'enrollment_token' in data

    def test_generate_enrollment_token_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/GenerateEnrollmentToken/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_generate_enrollment_token_invalid_json(self, authenticated_client):
        """Test enrollment token generation with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/GenerateEnrollmentToken/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']

    def test_generate_enrollment_token_requires_auth(self, client):
        """Test that authentication is required"""
        response = client.post(
            '/ConnectionManager/GenerateEnrollmentToken/',
            data=json.dumps({'policy_name': 'Test'}),
            content_type='application/json'
        )

        # Should redirect to login or return 403
        assert response.status_code in [302, 403]


# ============================================================================
# Deploy Policy Tests
# ============================================================================

@pytest.mark.django_db
class TestDeployPolicy:
    """Tests for the deploy_policy endpoint"""

    def test_deploy_policy_success(self, authenticated_client, test_policy):
        """Test successful policy deployment"""
        initial_revision = test_policy.current_revision_number

        response = authenticated_client.post(
            '/ConnectionManager/DeployPolicy/',
            data=json.dumps({
                'policy_id': test_policy.id
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['revision_number'] == initial_revision + 1
        assert data['policy_name'] == test_policy.name

        # Verify policy was updated
        test_policy.refresh_from_db()
        assert test_policy.current_revision_number == initial_revision + 1
        assert test_policy.last_deployed_at is not None

        # Verify revision was created
        assert Revision.objects.filter(
            policy=test_policy,
            revision_number=initial_revision + 1
        ).exists()

    def test_deploy_policy_creates_snapshot(self, authenticated_client, test_policy, test_pipeline, test_keystore_entry):
        """Test that deployment creates proper snapshot"""
        response = authenticated_client.post(
            '/ConnectionManager/DeployPolicy/',
            data=json.dumps({
                'policy_id': test_policy.id
            }),
            content_type='application/json'
        )

        assert response.status_code == 200

        # Get the created revision
        revision = Revision.objects.filter(policy=test_policy).first()
        assert revision is not None

        # Verify snapshot contains all data
        snapshot = revision.snapshot_json
        assert snapshot['logstash_yml'] == test_policy.logstash_yml
        assert snapshot['jvm_options'] == test_policy.jvm_options
        assert snapshot['log4j2_properties'] == test_policy.log4j2_properties
        assert snapshot['settings_path'] == test_policy.settings_path
        assert len(snapshot['pipelines']) == 1
        assert snapshot['pipelines'][0]['name'] == 'test_pipeline'
        assert len(snapshot['keystore']) == 1
        assert snapshot['keystore'][0]['key_name'] == 'test_key'

    def test_deploy_policy_missing_policy_id(self, authenticated_client):
        """Test deployment without policy_id"""
        response = authenticated_client.post(
            '/ConnectionManager/DeployPolicy/',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy ID is required' in data['error']

    def test_deploy_policy_nonexistent_policy(self, authenticated_client):
        """Test deployment with non-existent policy"""
        response = authenticated_client.post(
            '/ConnectionManager/DeployPolicy/',
            data=json.dumps({
                'policy_id': 99999
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']

    def test_deploy_policy_wrong_method(self, authenticated_client, test_policy):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/DeployPolicy/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_deploy_policy_invalid_json(self, authenticated_client):
        """Test deployment with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/DeployPolicy/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# Get Policy Diff Tests
# ============================================================================

@pytest.mark.django_db
class TestGetPolicyDiff:
    """Tests for the get_policy_diff endpoint"""

    def test_get_policy_diff_no_revision(self, authenticated_client, test_policy):
        """Test getting diff when no revision exists"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyDiff/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['policy_name'] == test_policy.name
        assert data['current_revision'] == 0
        assert data['last_deployed_revision'] == 0
        assert 'current' in data
        assert 'previous' in data

    def test_get_policy_diff_with_revision(self, authenticated_client, test_policy_with_revision):
        """Test getting diff when revision exists"""
        # Modify the policy
        test_policy_with_revision.logstash_yml = 'http.host: "127.0.0.1"'
        test_policy_with_revision.save()

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyDiff/?policy_id={test_policy_with_revision.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['current_revision'] == 1
        assert data['last_deployed_revision'] == 1
        assert data['current']['logstash_yml'] == 'http.host: "127.0.0.1"'
        assert data['previous']['logstash_yml'] == 'http.host: "0.0.0.0"'

    def test_get_policy_diff_missing_policy_id(self, authenticated_client):
        """Test getting diff without policy_id"""
        response = authenticated_client.get('/ConnectionManager/GetPolicyDiff/')

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy ID is required' in data['error']

    def test_get_policy_diff_nonexistent_policy(self, authenticated_client):
        """Test getting diff for non-existent policy"""
        response = authenticated_client.get('/ConnectionManager/GetPolicyDiff/?policy_id=99999')

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']

    def test_get_policy_diff_wrong_method(self, authenticated_client, test_policy):
        """Test that POST requests are rejected"""
        response = authenticated_client.post(
            '/ConnectionManager/GetPolicyDiff/',
            data=json.dumps({'policy_id': test_policy.id}),
            content_type='application/json'
        )

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']


# ============================================================================
# Get Policy Agent Count Tests
# ============================================================================

@pytest.mark.django_db
class TestGetPolicyAgentCount:
    """Tests for the get_policy_agent_count endpoint"""

    def test_get_policy_agent_count_zero(self, authenticated_client, test_policy):
        """Test agent count when no agents are assigned"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyAgentCount/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['agent_count'] == 0
        assert data['policy_name'] == test_policy.name

    def test_get_policy_agent_count_with_agents(self, authenticated_client, test_policy, test_agent_connection):
        """Test agent count with assigned agents"""
        # Create another agent
        Connection.objects.create(
            name='Test Agent 2',
            connection_type='AGENT',
            host='agent2.example.com',
            agent_id='test-agent-002',
            is_active=True,
            policy=test_policy
        )

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyAgentCount/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['agent_count'] == 2

    def test_get_policy_agent_count_excludes_inactive(self, authenticated_client, test_policy):
        """Test that inactive agents are not counted"""
        Connection.objects.create(
            name='Inactive Agent',
            connection_type='AGENT',
            host='inactive.example.com',
            agent_id='inactive-001',
            is_active=False,
            policy=test_policy
        )

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyAgentCount/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['agent_count'] == 0

    def test_get_policy_agent_count_excludes_centralized(self, authenticated_client, test_policy):
        """Test that centralized connections are not counted"""
        Connection.objects.create(
            name='Centralized',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme',
            is_active=True
        )

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyAgentCount/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['agent_count'] == 0

    def test_get_policy_agent_count_missing_policy_id(self, authenticated_client):
        """Test agent count without policy_id"""
        response = authenticated_client.get('/ConnectionManager/GetPolicyAgentCount/')

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy ID is required' in data['error']

    def test_get_policy_agent_count_nonexistent_policy(self, authenticated_client):
        """Test agent count for non-existent policy"""
        response = authenticated_client.get('/ConnectionManager/GetPolicyAgentCount/?policy_id=99999')

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']


# ============================================================================
# Get Policy Change Count Tests
# ============================================================================

@pytest.mark.django_db
class TestGetPolicyChangeCount:
    """Tests for the get_policy_change_count endpoint"""

    def test_get_policy_change_count_no_changes(self, authenticated_client, test_policy_with_revision):
        """Test change count when no changes exist"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyChangeCount/?policy_id={test_policy_with_revision.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['pending_changes'] == 0

    def test_get_policy_change_count_config_file_changes(self, authenticated_client, test_policy_with_revision):
        """Test change count with config file changes"""
        test_policy_with_revision.logstash_yml = 'http.host: "127.0.0.1"'
        test_policy_with_revision.jvm_options = '-Xms2g\n-Xmx2g'
        test_policy_with_revision.save()

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyChangeCount/?policy_id={test_policy_with_revision.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['pending_changes'] == 2  # logstash_yml + jvm_options

    def test_get_policy_change_count_pipeline_changes(self, authenticated_client, test_policy_with_revision):
        """Test change count with pipeline changes"""
        Pipeline.objects.create(
            policy=test_policy_with_revision,
            name='new_pipeline',
            lscl='input {} filter {} output {}'
        )

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyChangeCount/?policy_id={test_policy_with_revision.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['pending_changes'] == 1  # pipelines changed

    def test_get_policy_change_count_keystore_changes(self, authenticated_client, test_policy_with_revision):
        """Test change count with keystore changes"""
        Keystore.objects.create(
            policy=test_policy_with_revision,
            key_name='new_key',
            key_value='new_value'
        )

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyChangeCount/?policy_id={test_policy_with_revision.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['pending_changes'] == 1  # keystore changed

    def test_get_policy_change_count_global_settings_changes(self, authenticated_client, test_policy_with_revision):
        """Test change count with global settings changes"""
        test_policy_with_revision.settings_path = '/new/settings'
        test_policy_with_revision.save()

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyChangeCount/?policy_id={test_policy_with_revision.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['pending_changes'] == 1  # global_settings changed

    def test_get_policy_change_count_all_changes(self, authenticated_client, test_policy_with_revision):
        """Test change count with all types of changes"""
        # Config files
        test_policy_with_revision.logstash_yml = 'http.host: "127.0.0.1"'
        test_policy_with_revision.jvm_options = '-Xms2g\n-Xmx2g'
        test_policy_with_revision.log4j2_properties = 'logger.logstash.level = debug'
        # Global settings
        test_policy_with_revision.settings_path = '/new/settings'
        # Keystore password
        test_policy_with_revision.keystore_password = 'new_password'
        test_policy_with_revision.save()

        # Pipeline
        Pipeline.objects.create(
            policy=test_policy_with_revision,
            name='new_pipeline',
            lscl='input {} filter {} output {}'
        )

        # Keystore
        Keystore.objects.create(
            policy=test_policy_with_revision,
            key_name='new_key',
            key_value='new_value'
        )

        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyChangeCount/?policy_id={test_policy_with_revision.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        # 3 config files + 1 pipelines + 1 keystore + 1 keystore_password + 1 global_settings = 7
        assert data['pending_changes'] == 7

    def test_get_policy_change_count_no_revision(self, authenticated_client, test_policy):
        """Test change count when no revision exists (all changes)"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetPolicyChangeCount/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        # Should count all sections as changed when no revision exists
        assert data['pending_changes'] > 0

    def test_get_policy_change_count_missing_policy_id(self, authenticated_client):
        """Test change count without policy_id"""
        response = authenticated_client.get('/ConnectionManager/GetPolicyChangeCount/')

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy ID is required' in data['error']

    def test_get_policy_change_count_nonexistent_policy(self, authenticated_client):
        """Test change count for non-existent policy"""
        response = authenticated_client.get('/ConnectionManager/GetPolicyChangeCount/?policy_id=99999')

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']


# ============================================================================
# Get Keystore Entries Tests
# ============================================================================

@pytest.mark.django_db
class TestGetKeystoreEntries:
    """Tests for the get_keystore_entries endpoint"""

    def test_get_keystore_entries_empty(self, authenticated_client, test_policy):
        """Test getting keystore entries when none exist"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetKeystoreEntries/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['entries']) == 0
        assert data['has_keystore_password'] is True  # test_policy has password

    def test_get_keystore_entries_with_entries(self, authenticated_client, test_policy, test_keystore_entry):
        """Test getting keystore entries"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetKeystoreEntries/?policy_id={test_policy.id}'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['entries']) == 1
        assert data['entries'][0]['key_name'] == 'test_key'
        assert 'id' in data['entries'][0]
        assert 'last_updated' in data['entries'][0]

    def test_get_keystore_entries_missing_policy_id(self, authenticated_client):
        """Test getting entries without policy_id"""
        response = authenticated_client.get('/ConnectionManager/GetKeystoreEntries/')

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy ID is required' in data['error']

    def test_get_keystore_entries_nonexistent_policy(self, authenticated_client):
        """Test getting entries for non-existent policy"""
        response = authenticated_client.get('/ConnectionManager/GetKeystoreEntries/?policy_id=99999')

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']


# ============================================================================
# Set Keystore Password Tests
# ============================================================================

@pytest.mark.django_db
class TestSetKeystorePassword:
    """Tests for the set_keystore_password endpoint"""

    def test_set_keystore_password_success(self, authenticated_client, test_policy):
        """Test setting keystore password"""
        response = authenticated_client.post(
            '/ConnectionManager/SetKeystorePassword/',
            data=json.dumps({
                'policy_id': test_policy.id,
                'password': 'new_secure_password'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'Keystore password updated' in data['message']

        # Verify password was set and encrypted
        test_policy.refresh_from_db()
        assert test_policy.keystore_password is not None
        assert test_policy.keystore_password != 'new_secure_password'  # Should be encrypted
        assert test_policy.has_undeployed_changes is True

    def test_set_keystore_password_missing_policy_id(self, authenticated_client):
        """Test setting password without policy_id"""
        response = authenticated_client.post(
            '/ConnectionManager/SetKeystorePassword/',
            data=json.dumps({
                'password': 'test_password'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Policy ID is required' in data['error']

    def test_set_keystore_password_missing_password(self, authenticated_client, test_policy):
        """Test setting password without password field"""
        response = authenticated_client.post(
            '/ConnectionManager/SetKeystorePassword/',
            data=json.dumps({
                'policy_id': test_policy.id
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Password cannot be empty' in data['error']

    def test_set_keystore_password_nonexistent_policy(self, authenticated_client):
        """Test setting password for non-existent policy"""
        response = authenticated_client.post(
            '/ConnectionManager/SetKeystorePassword/',
            data=json.dumps({
                'policy_id': 99999,
                'password': 'test_password'
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']

    def test_set_keystore_password_wrong_method(self, authenticated_client, test_policy):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/SetKeystorePassword/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_set_keystore_password_invalid_json(self, authenticated_client):
        """Test setting password with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/SetKeystorePassword/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# Create Keystore Entry Tests
# ============================================================================

@pytest.mark.django_db
class TestCreateKeystoreEntry:
    """Tests for the create_keystore_entry endpoint"""

    def test_create_keystore_entry_success(self, authenticated_client, test_policy):
        """Test creating a keystore entry"""
        response = authenticated_client.post(
            '/ConnectionManager/CreateKeystoreEntry/',
            data=json.dumps({
                'policy_id': test_policy.id,
                'key_name': 'new_key',
                'key_value': 'secret_value'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'created successfully' in data['message']
        assert 'entry_id' in data

        # Verify entry was created
        assert Keystore.objects.filter(
            policy=test_policy,
            key_name='new_key'
        ).exists()

    def test_create_keystore_entry_duplicate_key(self, authenticated_client, test_policy, test_keystore_entry):
        """Test creating a duplicate keystore entry"""
        response = authenticated_client.post(
            '/ConnectionManager/CreateKeystoreEntry/',
            data=json.dumps({
                'policy_id': test_policy.id,
                'key_name': 'test_key',  # Already exists
                'key_value': 'another_value'
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'already exists' in data['error']

    def test_create_keystore_entry_missing_fields(self, authenticated_client, test_policy):
        """Test creating entry with missing fields"""
        response = authenticated_client.post(
            '/ConnectionManager/CreateKeystoreEntry/',
            data=json.dumps({
                'policy_id': test_policy.id,
                'key_name': 'test_key'
                # Missing key_value
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'required' in data['error']

    def test_create_keystore_entry_nonexistent_policy(self, authenticated_client):
        """Test creating entry for non-existent policy"""
        response = authenticated_client.post(
            '/ConnectionManager/CreateKeystoreEntry/',
            data=json.dumps({
                'policy_id': 99999,
                'key_name': 'test_key',
                'key_value': 'test_value'
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'Policy not found' in data['error']

    def test_create_keystore_entry_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/CreateKeystoreEntry/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_create_keystore_entry_invalid_json(self, authenticated_client):
        """Test creating entry with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/CreateKeystoreEntry/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# Update Keystore Entry Tests
# ============================================================================

@pytest.mark.django_db
class TestUpdateKeystoreEntry:
    """Tests for the update_keystore_entry endpoint"""

    def test_update_keystore_entry_success(self, authenticated_client, test_keystore_entry):
        """Test updating a keystore entry"""
        response = authenticated_client.post(
            '/ConnectionManager/UpdateKeystoreEntry/',
            data=json.dumps({
                'entry_id': test_keystore_entry.id,
                'key_value': 'updated_value'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'updated successfully' in data['message']

        # Verify entry was updated
        test_keystore_entry.refresh_from_db()
        # Value should be encrypted, so we can't compare directly
        assert test_keystore_entry.key_value != 'test_value'

    def test_update_keystore_entry_missing_fields(self, authenticated_client, test_keystore_entry):
        """Test updating entry with missing fields"""
        response = authenticated_client.post(
            '/ConnectionManager/UpdateKeystoreEntry/',
            data=json.dumps({
                'entry_id': test_keystore_entry.id
                # Missing key_value
            }),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'required' in data['error']

    def test_update_keystore_entry_nonexistent(self, authenticated_client):
        """Test updating non-existent entry"""
        response = authenticated_client.post(
            '/ConnectionManager/UpdateKeystoreEntry/',
            data=json.dumps({
                'entry_id': 99999,
                'key_value': 'test_value'
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['error']

    def test_update_keystore_entry_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/UpdateKeystoreEntry/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_update_keystore_entry_invalid_json(self, authenticated_client):
        """Test updating entry with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/UpdateKeystoreEntry/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']


# ============================================================================
# Delete Keystore Entry Tests
# ============================================================================

@pytest.mark.django_db
class TestDeleteKeystoreEntry:
    """Tests for the delete_keystore_entry endpoint"""

    def test_delete_keystore_entry_success(self, authenticated_client, test_keystore_entry):
        """Test deleting a keystore entry"""
        entry_id = test_keystore_entry.id

        response = authenticated_client.post(
            '/ConnectionManager/DeleteKeystoreEntry/',
            data=json.dumps({
                'entry_id': entry_id
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'deleted successfully' in data['message']

        # Verify entry was deleted
        assert not Keystore.objects.filter(id=entry_id).exists()

    def test_delete_keystore_entry_missing_entry_id(self, authenticated_client):
        """Test deleting entry without entry_id"""
        response = authenticated_client.post(
            '/ConnectionManager/DeleteKeystoreEntry/',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Entry ID is required' in data['error']

    def test_delete_keystore_entry_nonexistent(self, authenticated_client):
        """Test deleting non-existent entry"""
        response = authenticated_client.post(
            '/ConnectionManager/DeleteKeystoreEntry/',
            data=json.dumps({
                'entry_id': 99999
            }),
            content_type='application/json'
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False
        assert 'not found' in data['error']

    def test_delete_keystore_entry_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/DeleteKeystoreEntry/')

        assert response.status_code == 405
        data = response.json()
        assert data['success'] is False
        assert 'Method not allowed' in data['error']

    def test_delete_keystore_entry_invalid_json(self, authenticated_client):
        """Test deleting entry with invalid JSON"""
        response = authenticated_client.post(
            '/ConnectionManager/DeleteKeystoreEntry/',
            data='not valid json',
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'Invalid JSON data' in data['error']
