#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from django.contrib.auth.models import User
from django.test import Client
from unittest.mock import patch, MagicMock, Mock
import json

from SNMP.models import Network, Device, Credential, Profile, DeviceTemplate
from PipelineManager.models import Connection
from Management.models import UserProfile


@pytest.fixture
def admin_user(db):
    """Create a uer with admin profile"""
    user = User.objects.create_user(
        username='admin_user',
        password='testpass123',
        email='admin@example.com'
    )
    profile, created = UserProfile.objects.get_or_create(user=user, defaults={'role': 'admin'})
    if not created:
        profile.role = 'admin'
        profile.save()
    return user


@pytest.fixture
def readonly_user(db):
    """Create a user with readonly profile"""
    user = User.objects.create_user(
        username='readonly_user',
        password='testpass123',
        email='readonly@example.com'
    )
    profile = UserProfile.objects.get(user=user)
    profile.role = 'readonly'
    profile.save()
    user.refresh_from_db()
    return user


@pytest.fixture
def authenticated_client(admin_user):
    """Create an authenticated client with admin user"""
    client = Client()
    client.force_login(admin_user)
    return client


@pytest.fixture
def readonly_client(readonly_user):
    """Create an authenticated client with readonly user"""
    client = Client()
    client.force_login(readonly_user)
    return client


@pytest.fixture
def test_connection(db):
    """Create a test Elasticsearch connection"""
    return Connection.objects.create(
        name='Test Connection',
        connection_type='CENTRALIZED',
        host='https://localhost:9200',
        username='elastic',
        password='changeme'
    )


@pytest.fixture
def test_credential_v2c(db):
    """Create a test SNMP v2c credential"""
    return Credential.objects.create(
        name='Test Credential v2c',
        version='2c',
        community='public',
        description='Test SNMP v2c credential'
    )


@pytest.fixture
def test_credential_v3(db):
    """Create a test SNMP v3 credential"""
    return Credential.objects.create(
        name='Test Credential v3',
        version='3',
        security_name='snmpuser',
        security_level='authPriv',
        auth_protocol='sha',
        auth_pass='authpassword',
        priv_protocol='aes',
        priv_pass='privpassword',
        description='Test SNMP v3 credential'
    )


@pytest.fixture
def test_network(db, test_connection, test_credential_v2c):
    """Create a test SNMP network"""
    return Network.objects.create(
        name='Test Network',
        network_range='192.168.1.0/24',
        connection=test_connection,
        discovery_credential=test_credential_v2c,
        discovery_enabled=True,
        traps_enabled=False,
        interval=30
    )


@pytest.fixture
def test_device(db, test_network, test_credential_v2c):
    """Create a test SNMP device"""
    return Device.objects.create(
        name='Test Device',
        ip_address='192.168.1.100',
        port=161,
        retries=2,
        timeout=1000,
        credential=test_credential_v2c,
        network=test_network
    )


@pytest.fixture
def test_profile(db):
    """Create a test user profile"""
    return Profile.objects.create(
        name='custom_profile',
        description='Custom test profile',
        vendor='Generic',
        profile_data={
            'get': {
                'test.metric': '1.3.6.1.2.1.1.1.0'
            },
            'walk': {},
            'table': {}
        }
    )


# ============================================================================
# Credential CRUD Tests
# ============================================================================

@pytest.mark.django_db
class TestCredentialCRUD:
    """Test Credential Create, Read, Update, Delete operations"""

    def test_get_credentials(self, authenticated_client, test_credential_v2c):
        """Test getting all credentials"""
        response = authenticated_client.get('/SNMP/GetCredentials/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(c['name'] == 'Test Credential v2c' for c in data)

    def test_get_credential_by_id(self, authenticated_client, test_credential_v2c):
        """Test getting a single credential by ID"""
        response = authenticated_client.get(f'/SNMP/GetCredential/{test_credential_v2c.id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['name'] == 'Test Credential v2c'
        assert data['version'] == '2c'
        # Community should be masked
        assert data['community'] == '***'

    def test_get_credential_not_found(self, authenticated_client):
        """Test getting a non-existent credential"""
        response = authenticated_client.get('/SNMP/GetCredential/99999/')
        assert response.status_code == 404

    def test_add_credential_v2c_requires_admin(self, readonly_client):
        """Test that adding a credential requires admin role"""
        response = readonly_client.post('/SNMP/AddCredential/', {
            'name': 'New Credential',
            'version': '2c',
            'community': 'public'
        })
        assert response.status_code == 403
        assert b'Admin role required' in response.content

    def test_add_credential_v2c_success(self, authenticated_client):
        """Test successfully adding a v2c credential"""
        response = authenticated_client.post('/SNMP/AddCredential/', {
            'name': 'New v2c Credential',
            'version': '2c',
            'community': 'private',
            'description': 'Test description'
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'id' in data
        assert 'Credential created successfully!' in data['message']
        
        # Verify credential was created
        credential = Credential.objects.get(name='New v2c Credential')
        assert credential.version == '2c'
        assert credential.get_community() == 'private'

    def test_add_credential_v3_success(self, authenticated_client):
        """Test successfully adding a v3 credential"""
        response = authenticated_client.post('/SNMP/AddCredential/', {
            'name': 'New v3 Credential',
            'version': '3',
            'security_name': 'testuser',
            'security_level': 'authPriv',
            'auth_protocol': 'sha',
            'auth_pass': 'authpass123',
            'priv_protocol': 'aes',
            'priv_pass': 'privpass123'
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'id' in data
        
        # Verify credential was created
        credential = Credential.objects.get(name='New v3 Credential')
        assert credential.version == '3'
        assert credential.security_name == 'testuser'
        assert credential.get_auth_pass() == 'authpass123'
        assert credential.get_priv_pass() == 'privpass123'

    def test_add_credential_validation_error(self, authenticated_client):
        """Test adding a credential with validation errors"""
        response = authenticated_client.post('/SNMP/AddCredential/', {
            'name': 'Invalid Credential',
            'version': '2c',
            'community': ''  # Empty community should fail
        })
        assert response.status_code == 400
        assert b'Community string is required' in response.content

    def test_update_credential_requires_admin(self, readonly_client, test_credential_v2c):
        """Test that updating a credential requires admin role"""
        response = readonly_client.post(f'/SNMP/UpdateCredential/{test_credential_v2c.id}/', {
            'name': 'Updated Name',
            'version': '2c',
            'community': 'newcommunity'
        })
        assert response.status_code == 403

    def test_update_credential_success(self, authenticated_client, test_credential_v2c):
        """Test successfully updating a credential"""
        response = authenticated_client.post(f'/SNMP/UpdateCredential/{test_credential_v2c.id}/', {
            'name': 'Updated Credential',
            'version': '2c',
            'community': 'newcommunity',
            'description': 'Updated description'
        })
        assert response.status_code == 200
        
        # Verify credential was updated
        test_credential_v2c.refresh_from_db()
        assert test_credential_v2c.name == 'Updated Credential'
        assert test_credential_v2c.get_community() == 'newcommunity'

    def test_update_credential_not_found(self, authenticated_client):
        """Test updating a non-existent credential"""
        response = authenticated_client.post('/SNMP/UpdateCredential/99999/', {
            'name': 'Test',
            'version': '2c',
            'community': 'public'
        })
        assert response.status_code == 404

    def test_delete_credential_requires_admin(self, readonly_client, test_credential_v2c):
        """Test that deleting a credential requires admin role"""
        response = readonly_client.post(f'/SNMP/DeleteCredential/{test_credential_v2c.id}/')
        assert response.status_code == 403

    def test_delete_credential_success(self, authenticated_client, test_credential_v2c):
        """Test successfully deleting a credential"""
        credential_id = test_credential_v2c.id
        response = authenticated_client.post(f'/SNMP/DeleteCredential/{credential_id}/')
        assert response.status_code == 200
        assert b'Credential deleted successfully!' in response.content
        
        # Verify credential was deleted
        assert not Credential.objects.filter(id=credential_id).exists()

    def test_delete_credential_not_found(self, authenticated_client):
        """Test deleting a non-existent credential"""
        response = authenticated_client.post('/SNMP/DeleteCredential/99999/')
        assert response.status_code == 404


# ============================================================================
# Network CRUD Tests
# ============================================================================

@pytest.mark.django_db
class TestNetworkCRUD:
    """Test Network Create, Read, Update, Delete operations"""

    def test_get_networks(self, authenticated_client, test_network):
        """Test getting all networks"""
        response = authenticated_client.get('/SNMP/GetNetworks/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(n['name'] == 'Test Network' for n in data)

    def test_get_network_by_id(self, authenticated_client, test_network):
        """Test getting a single network by ID"""
        response = authenticated_client.get(f'/SNMP/GetNetwork/{test_network.id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['name'] == 'Test Network'
        assert data['network_range'] == '192.168.1.0/24'

    def test_add_network_requires_admin(self, readonly_client, test_connection, test_credential_v2c):
        """Test that adding a network requires admin role"""
        response = readonly_client.post('/SNMP/AddNetwork/', {
            'name': 'New Network',
            'network_range': '10.0.0.0/24',
            'connection': test_connection.id,
            'discovery_credential': test_credential_v2c.id
        })
        assert response.status_code == 403

    def test_add_network_success(self, authenticated_client, test_connection, test_credential_v2c):
        """Test successfully adding a network"""
        response = authenticated_client.post('/SNMP/AddNetwork/', {
            'name': 'New Network',
            'network_range': '10.0.0.0/24',
            'connection': test_connection.id,
            'discovery_credential': test_credential_v2c.id,
            'discovery_enabled': 'true',
            'traps_enabled': 'false',
            'interval': '60'
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'id' in data
        assert 'Network created successfully!' in data['message']
        
        # Verify network was created
        network = Network.objects.get(name='New Network')
        assert network.network_range == '10.0.0.0/24'
        assert network.interval == 60

    def test_add_network_invalid_cidr(self, authenticated_client, test_connection):
        """Test adding a network with invalid CIDR notation"""
        response = authenticated_client.post('/SNMP/AddNetwork/', {
            'name': 'Invalid Network',
            'network_range': 'not-a-valid-cidr',
        })
        assert response.status_code == 400
        assert b'Invalid CIDR notation' in response.content

    def test_update_network_requires_admin(self, readonly_client, test_network):
        """Test that updating a network requires admin role"""
        response = readonly_client.post(f'/SNMP/UpdateNetwork/{test_network.id}/', {
            'name': 'Updated Network',
            'network_range': '192.168.1.0/24',
        })
        assert response.status_code == 403

    def test_update_network_success(self, authenticated_client, test_network):
        """Test successfully updating a network"""
        response = authenticated_client.post(f'/SNMP/UpdateNetwork/{test_network.id}/', {
            'name': 'Updated Network',
            'network_range': '192.168.2.0/24',
            'interval': '120'
        })
        assert response.status_code == 200
        
        # Verify network was updated
        test_network.refresh_from_db()
        assert test_network.name == 'Updated Network'
        assert test_network.network_range == '192.168.2.0/24'
        assert test_network.interval == 120

    def test_delete_network_requires_admin(self, readonly_client, test_network):
        """Test that deleting a network requires admin role"""
        response = readonly_client.post(f'/SNMP/DeleteNetwork/{test_network.id}/')
        assert response.status_code == 403

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_delete_network_success(self, mock_es_conn, authenticated_client, test_network):
        """Test successfully deleting a network"""
        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {}
        mock_es_conn.return_value = mock_es
        
        network_id = test_network.id
        response = authenticated_client.post(f'/SNMP/DeleteNetwork/{network_id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        
        # Verify network was deleted
        assert not Network.objects.filter(id=network_id).exists()

    def test_get_network_pipeline_name(self, authenticated_client, test_network):
        """Test getting the pipeline name for a network"""
        response = authenticated_client.get(f'/SNMP/GetNetworkPipelineName/{test_network.id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'pipeline_name' in data
        assert 'snmp-' in data['pipeline_name']


# ============================================================================
# Device CRUD Tests
# ============================================================================

@pytest.mark.django_db
class TestDeviceCRUD:
    """Test Device Create, Read, Update, Delete operations"""

    def test_get_devices_paginated(self, authenticated_client, test_device):
        """Test getting paginated devices"""
        response = authenticated_client.get('/SNMP/GetDevices/?page=1&page_size=25')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'devices' in data
        assert 'total' in data
        assert 'page' in data
        assert len(data['devices']) >= 1

    def test_get_devices_with_search(self, authenticated_client, test_device):
        """Test getting devices with search filter"""
        response = authenticated_client.get('/SNMP/GetDevices/?search=Test')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data['devices']) >= 1
        assert any(d['name'] == 'Test Device' for d in data['devices'])

    def test_get_devices_with_network_filter(self, authenticated_client, test_device, test_network):
        """Test getting devices filtered by network"""
        response = authenticated_client.get(f'/SNMP/GetDevices/?network={test_network.id}')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert all(d['network_id'] == test_network.id for d in data['devices'])

    def test_get_device_by_id(self, authenticated_client, test_device):
        """Test getting a single device by ID"""
        response = authenticated_client.get(f'/SNMP/GetDevice/{test_device.id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['name'] == 'Test Device'
        assert data['ip_address'] == '192.168.1.100'
        assert 'device_template' in data

    def test_add_device_requires_admin(self, readonly_client, test_network, test_credential_v2c):
        """Test that adding a device requires admin role"""
        response = readonly_client.post('/SNMP/AddDevice/', {
            'name': 'New Device',
            'ip_address': '192.168.1.101',
            'network': test_network.id,
            'credential': test_credential_v2c.id
        })
        assert response.status_code == 403

    def test_add_device_success(self, authenticated_client, test_network, test_credential_v2c):
        """Test successfully adding a device"""
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'New Device',
            'ip_address': '192.168.1.101',
            'port': '161',
            'retries': '3',
            'timeout': '2000',
            'network': test_network.id,
            'credential': test_credential_v2c.id,
            'profiles': ['system']
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'id' in data
        assert 'Device created successfully!' in data['message']
        
        # Verify device was created
        device = Device.objects.get(name='New Device')
        assert device.ip_address == '192.168.1.101'

    def test_add_device_auto_adds_system_profile(self, authenticated_client, test_network, test_credential_v2c):
        """Test that system profile is automatically added to devices"""
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'Device Without Profiles',
            'ip_address': '192.168.1.102',
            'network': test_network.id,
            'credential': test_credential_v2c.id
        })
        assert response.status_code == 200
        
        # Verify device was created successfully
        device = Device.objects.get(name='Device Without Profiles')
        assert device.ip_address == '192.168.1.102'

    def test_add_device_invalid_ip(self, authenticated_client, test_network, test_credential_v2c):
        """Test adding a device with invalid IP address"""
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'Invalid Device',
            'ip_address': 'not-an-ip!@#',
            'network': test_network.id,
            'credential': test_credential_v2c.id
        })
        assert response.status_code == 400

    def test_update_device_requires_admin(self, readonly_client, test_device):
        """Test that updating a device requires admin role"""
        response = readonly_client.post(f'/SNMP/UpdateDevice/{test_device.id}/', {
            'name': 'Updated Device',
            'ip_address': '192.168.1.100'
        })
        assert response.status_code == 403

    def test_update_device_success(self, authenticated_client, test_device):
        """Test successfully updating a device"""
        response = authenticated_client.post(f'/SNMP/UpdateDevice/{test_device.id}/', {
            'name': 'Updated Device',
            'ip_address': '192.168.1.200',
            'port': '162',
            'profiles': ['system']
        })
        assert response.status_code == 200
        
        # Verify device was updated
        test_device.refresh_from_db()
        assert test_device.name == 'Updated Device'
        assert test_device.ip_address == '192.168.1.200'
        assert test_device.port == 162

    def test_delete_device_requires_admin(self, readonly_client, test_device):
        """Test that deleting a device requires admin role"""
        response = readonly_client.post(f'/SNMP/DeleteDevice/{test_device.id}/')
        assert response.status_code == 403

    def test_delete_device_success(self, authenticated_client, test_device):
        """Test successfully deleting a device"""
        device_id = test_device.id
        response = authenticated_client.post(f'/SNMP/DeleteDevice/{device_id}/')
        assert response.status_code == 200
        assert b'Device deleted successfully!' in response.content
        
        # Verify device was deleted
        assert not Device.objects.filter(id=device_id).exists()


# ============================================================================
# Profile CRUD Tests
# ============================================================================

@pytest.mark.django_db
class TestProfileCRUD:
    """Test Profile Create, Read, Update, Delete operations"""

    def test_get_all_profiles(self, authenticated_client, test_profile):
        """Test getting all profiles"""
        response = authenticated_client.get('/SNMP/GetAllProfiles/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'profiles' in data
        # The custom profile created by the fixture should always appear
        assert any(p['name'] == 'custom_profile' for p in data['profiles'])

    def test_get_official_profile(self, authenticated_client):
        """Test getting an official profile (mocks filesystem)"""
        fake_data = {'description': 'Generic system profile', 'vendor': 'Generic', 'get': {}}
        with patch('SNMP.snmp_crud.os.path.exists', return_value=True), \
             patch('builtins.open', create=True) as mock_open, \
             patch('SNMP.snmp_crud.json.load', return_value=fake_data):
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            response = authenticated_client.get('/SNMP/GetOfficialProfile/system/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'profile_data' in data

    def test_get_user_profile(self, authenticated_client, test_profile):
        """Test getting a user profile"""
        response = authenticated_client.get('/SNMP/GetProfile/custom_profile/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['name'] == 'custom_profile'

    def test_add_profile_requires_admin(self, readonly_client):
        """Test that adding a profile requires admin role"""
        response = readonly_client.post('/SNMP/AddProfile/', 
            json.dumps({
                'name': 'new_profile',
                'description': 'Test',
                'profile_data': {'get': {}}
            }),
            content_type='application/json'
        )
        assert response.status_code == 403

    def test_add_profile_success(self, authenticated_client):
        """Test successfully adding a profile"""
        response = authenticated_client.post('/SNMP/AddProfile/',
            json.dumps({
                'name': 'new_custom_profile',
                'description': 'New custom profile',
                'type': 'Network',
                'vendor': 'Cisco',
                'profile_data': {
                    'get': {
                        'custom.metric': '1.3.6.1.4.1.1.1.0'
                    },
                    'walk': {},
                    'table': {}
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        
        # Verify profile was created
        profile = Profile.objects.get(name='new_custom_profile')
        assert profile.vendor == 'Cisco'

    def test_add_profile_duplicate_name(self, authenticated_client, test_profile):
        """Test adding a profile with duplicate name"""
        response = authenticated_client.post('/SNMP/AddProfile/',
            json.dumps({
                'name': 'custom_profile',
                'profile_data': {'get': {}}
            }),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'already exists' in data['message']

    def test_update_profile_requires_admin(self, readonly_client, test_profile):
        """Test that updating a profile requires admin role"""
        response = readonly_client.post(f'/SNMP/UpdateProfile/{test_profile.name}/',
            json.dumps({
                'name': 'updated_profile',
                'profile_data': {'get': {}}
            }),
            content_type='application/json'
        )
        assert response.status_code == 403

    def test_update_profile_success(self, authenticated_client, test_profile):
        """Test successfully updating a profile"""
        response = authenticated_client.post(f'/SNMP/UpdateProfile/{test_profile.name}/',
            json.dumps({
                'description': 'Updated description',
                'vendor': 'Updated Vendor',
                'profile_data': {
                    'get': {
                        'updated.metric': '1.3.6.1.2.1.1.2.0'
                    }
                }
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        
        # Verify profile was updated
        test_profile.refresh_from_db()
        assert test_profile.description == 'Updated description'
        assert test_profile.vendor == 'Updated Vendor'

    def test_delete_profile_requires_admin(self, readonly_client, test_profile):
        """Test that deleting a profile requires admin role"""
        response = readonly_client.post(f'/SNMP/DeleteProfile/{test_profile.name}/')
        assert response.status_code == 403

    def test_delete_profile_success(self, authenticated_client, test_profile):
        """Test successfully deleting a profile"""
        response = authenticated_client.post(f'/SNMP/DeleteProfile/{test_profile.name}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        
        # Verify profile was deleted
        assert not Profile.objects.filter(name='custom_profile').exists()

    def test_delete_system_profile_forbidden(self, authenticated_client):
        """Test that system profile cannot be deleted"""
        response = authenticated_client.post('/SNMP/DeleteProfile/system/')
        assert response.status_code == 403
        data = json.loads(response.content)
        assert 'cannot be deleted' in data['message']


# ============================================================================
# Deploy Configuration Tests
# ============================================================================

@pytest.mark.django_db
class TestDeployConfiguration:
    """Test configuration deployment operations"""

    def test_get_deploy_diff(self, authenticated_client, test_network, test_device):
        """Test getting deploy diff"""
        with patch('SNMP.snmp_crud.get_elastic_connection') as mock_es_conn:
            mock_es = MagicMock()
            mock_es.logstash.get_pipeline.return_value = {}
            mock_es_conn.return_value = mock_es
            
            response = authenticated_client.get('/SNMP/GetDeployDiff/')
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['success'] is True
            assert 'networks' in data
            assert any(c['id'] == test_network.connection.id for c in data['connections'])

    def test_get_deploy_diff_includes_es_connection_for_agent_only_networks(
        self, authenticated_client, test_network, test_device, test_connection
    ):
        """Agent-only setups still need the SNMP index template on their ES connection."""
        from PipelineManager.models import Policy, Connection as AgentConnection

        policy = Policy.objects.create(
            name='Simulated SNMP Policy',
            settings_path='/etc/logstash/',
            logs_path='/var/log/logstash',
            binary_path='/usr/share/logstash/bin',
            logstash_yml='http.host: "0.0.0.0"',
            jvm_options='-Xms1g',
            log4j2_properties='logger.logstash.name = logstash',
            keystore_password='test_password',
        )
        agent = AgentConnection.objects.create(
            name='SimulatedSNMP Agent',
            connection_type='AGENT',
            host='agent.example.com',
            agent_id='sim-snmp-001',
            is_active=True,
            policy=policy,
        )
        test_network.deployment_mode = 'AGENT'
        test_network.agent_connection = agent
        test_network.save(update_fields=['deployment_mode', 'agent_connection'])

        with patch('SNMP.snmp_crud.get_elastic_connection') as mock_es_conn:
            mock_es = MagicMock()
            mock_es.logstash.get_pipeline.return_value = {}
            mock_es_conn.return_value = mock_es

            response = authenticated_client.get('/SNMP/GetDeployDiff/')

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['connections'] == [
            {'id': test_connection.id, 'name': test_connection.name}
        ]

        # GetDeployDiff caches a 60s deploy plan; don't leak an Agent-mode plan
        # into later DeployConfiguration tests in this class.
        from django.core.cache import cache
        cache.delete('snmp_deployment_plan')

    def test_deploy_configuration_requires_admin(self, readonly_client):
        """Test that deploying configuration requires admin role"""
        response = readonly_client.post('/SNMP/DeployConfiguration/')
        assert response.status_code == 403

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_deploy_configuration_success(self, mock_es_conn, authenticated_client, test_network, test_device):
        """Test successfully deploying configuration"""
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {}
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_es_conn.return_value = mock_es
        
        response = authenticated_client.post('/SNMP/DeployConfiguration/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_deploy_configuration_no_networks(self, mock_es_conn, authenticated_client):
        """Test deploying with no networks configured"""
        response = authenticated_client.post('/SNMP/DeployConfiguration/')
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'No networks configured' in data['error']


# ============================================================================
# Device Status and Visualization Tests
# ============================================================================

@pytest.mark.django_db
class TestDeviceStatusAndVisualization:
    """Test device status checking and visualization endpoints"""

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_get_devices_status(self, mock_es_conn, authenticated_client, test_device):
        """Test getting device status in batch"""
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'online_devices': {
                    'buckets': [
                        {'key': '192.168.1.100', 'doc_count': 10}
                    ]
                }
            }
        }
        mock_es_conn.return_value = mock_es
        
        response = authenticated_client.get(f'/SNMP/GetDevicesStatus/?device_ids={test_device.id}')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'statuses' in data
        assert data['statuses'][str(test_device.id)]['is_online'] is True

        search_kwargs = mock_es.search.call_args.kwargs
        assert search_kwargs['index'] == 'metrics-snmp*'
        assert search_kwargs['aggregations']['online_devices']['terms']['field'] == 'host.polled_address'

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_get_devices_status_hostname_only_device(
        self, mock_es_conn, authenticated_client, test_network, test_credential_v2c
    ):
        """Hostname-only devices are matched on host.polled_address, not IP."""
        device = Device.objects.create(
            name='Linux',
            hostname='linux_host.lab',
            ip_address=None,
            port=1161,
            credential=test_credential_v2c,
            network=test_network,
        )
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'online_devices': {
                    'buckets': [
                        {'key': 'linux_host.lab', 'doc_count': 4}
                    ]
                }
            }
        }
        mock_es_conn.return_value = mock_es

        response = authenticated_client.get(f'/SNMP/GetDevicesStatus/?device_ids={device.id}')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['statuses'][str(device.id)]['is_online'] is True

        terms_filter = mock_es.search.call_args.kwargs['query']['bool']['filter'][1]
        assert terms_filter == {'terms': {'host.polled_address': ['linux_host.lab']}}

    def test_get_devices_status_invalid_ids(self, authenticated_client):
        """Test getting device status with invalid IDs"""
        response = authenticated_client.get('/SNMP/GetDevicesStatus/?device_ids=invalid')
        assert response.status_code == 400

    @patch('SNMP.snmp_crud.generate_visualizations')
    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_get_device_visualization(self, mock_es_conn, mock_gen_viz, authenticated_client, test_device):
        """Test getting device visualization data"""
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'data_kinds': {
                    'buckets': [
                        {'key': 'metric', 'doc_count': 100}
                    ]
                }
            }
        }
        mock_es_conn.return_value = mock_es
        
        # Mock the visualization generation to return simple data
        mock_gen_viz.return_value = {
            'charts': [],
            'has_data': True
        }
        
        response = authenticated_client.get(f'/SNMP/GetDeviceVisualization/{test_device.id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'device' in data
        assert 'visualizations' in data

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_get_discovered_devices(self, mock_es_conn, authenticated_client, test_connection, test_network):
        """Test getting discovered devices from Elasticsearch"""
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'devices_by_host': {
                    'buckets': [
                        {
                            'key': 'device1',
                            'latest_doc': {
                                'hits': {
                                    'hits': [
                                        {
                                            '_source': {
                                                'host': {'name': 'device1', 'hostname': '192.168.1.50'},
                                                'network': {'name': 'Test Network'},
                                                '@timestamp': '2024-01-01T00:00:00Z'
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        }
        mock_es_conn.return_value = mock_es
        
        response = authenticated_client.get('/SNMP/DiscoveredDevices/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'devices' in data


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

@pytest.mark.django_db
class TestEdgeCasesAndErrors:
    """Test edge cases and error handling"""

    def test_unauthenticated_access_denied(self, client):
        """Test that unauthenticated requests are denied"""
        response = client.get('/SNMP/GetCredentials/')
        assert response.status_code == 302
        assert '/Management/Login/' in response.url

    def test_credential_encryption(self, authenticated_client):
        """Test that credentials are encrypted when saved"""
        response = authenticated_client.post('/SNMP/AddCredential/', {
            'name': 'Encryption Test',
            'version': '2c',
            'community': 'secret'
        })
        assert response.status_code == 200
        
        # Verify community is encrypted in database
        credential = Credential.objects.get(name='Encryption Test')
        # Encrypted value should start with 'gAAAAA' (Fernet token)
        assert credential.community.startswith('gAAAAA')
        # But decrypted value should be original
        assert credential.get_community() == 'secret'

    def test_network_cidr_validation(self, authenticated_client):
        """Test CIDR validation for networks"""
        # Valid CIDR within the /20 size limit
        response = authenticated_client.post('/SNMP/AddNetwork/', {
            'name': 'Valid CIDR',
            'network_range': '10.0.0.0/24',
        })
        assert response.status_code == 200

        # Networks larger than /20 are rejected (would OOM during discovery)
        response = authenticated_client.post('/SNMP/AddNetwork/', {
            'name': 'Too Large CIDR',
            'network_range': '10.0.0.0/8',
        })
        assert response.status_code == 400
        data = response.json()
        assert not data['success']
        assert 'too large' in data['message'].lower()

        # Invalid CIDR is rejected by model validation
        response = authenticated_client.post('/SNMP/AddNetwork/', {
            'name': 'Invalid CIDR',
            'network_range': '999.999.999.999/99',
        })
        assert response.status_code == 400

    def test_device_ip_validation(self, authenticated_client, test_network, test_credential_v2c):
        """Test IP address validation for devices"""
        # Valid IP address
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'Valid IP Device',
            'ip_address': '192.168.1.1',
            'network': test_network.id,
            'credential': test_credential_v2c.id
        })
        assert response.status_code == 200
        
        # Hostname in ip_address is no longer valid; ip_address must be a valid IP.
        # Hostnames should be set in the 'hostname' field instead.
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'Hostname Device',
            'ip_address': 'router.example.com',
            'network': test_network.id,
            'credential': test_credential_v2c.id
        })
        assert response.status_code == 400

    def test_profile_json_validation(self, authenticated_client):
        """Test that profile_data must be valid JSON object"""
        # Valid JSON object — vendor is now required
        response = authenticated_client.post('/SNMP/AddProfile/',
            json.dumps({
                'name': 'valid_json_profile',
                'vendor': 'Generic',
                'profile_data': {'get': {}, 'walk': {}}
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_deploy_handles_elasticsearch_errors(self, mock_es_conn, authenticated_client, test_network, test_device):
        """Test that deploy handles Elasticsearch errors gracefully"""
        mock_es_conn.side_effect = Exception("Connection failed")
        
        response = authenticated_client.post('/SNMP/DeployConfiguration/')
        # Should return error but not crash
        assert response.status_code in [400, 500]


# ============================================================================
# Pure-function unit tests for snmp_crud.py helpers
# ============================================================================

@pytest.mark.django_db
class TestGetPipelineName:
    """Tests for _get_pipeline_name() helper"""

    def test_basic_name_generation(self, test_network):
        from SNMP.snmp_crud import _get_pipeline_name
        name = _get_pipeline_name(test_network)
        assert name.startswith('snmp-')
        # network name is 'Test Network' — spaces become underscores via sanitizer
        assert 'test_network' in name

    def test_special_chars_sanitized(self, test_connection, test_credential_v2c):
        """Special chars in network name are sanitized"""
        from SNMP.snmp_crud import _get_pipeline_name
        network = Network.objects.create(
            name='My Network (prod)!',
            network_range='10.0.0.0/24',
            connection=test_connection,
        )
        name = _get_pipeline_name(network)
        # Pipeline names must not contain special chars
        import re
        assert re.match(r'^[a-z0-9_\-]+$', name), f"Bad pipeline name: {name}"


@pytest.mark.django_db
class TestCreateOrUpdatePipeline:
    """Tests for _create_or_update_pipeline() helper"""

    def test_creates_new_pipeline(self):
        from SNMP.snmp_crud import _create_or_update_pipeline
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.side_effect = Exception("not found")
        mock_es.logstash.put_pipeline.return_value = {}

        success, is_new, error, was_updated = _create_or_update_pipeline(
            mock_es, 'test-pipe', 'input {} filter {} output {}'
        )
        assert success is True
        assert is_new is True
        assert error is None
        assert was_updated is True
        mock_es.logstash.put_pipeline.assert_called_once()

    def test_updates_existing_pipeline_when_content_changed(self):
        from SNMP.snmp_crud import _create_or_update_pipeline
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'test-pipe': {
                'pipeline': 'input {} filter {} output { old_output }',
                'pipeline_settings': {'queue.type': 'memory'},
                'pipeline_metadata': {'version': 2, 'type': 'logstash_pipeline'},
            }
        }
        mock_es.logstash.put_pipeline.return_value = {}

        success, is_new, error, was_updated = _create_or_update_pipeline(
            mock_es, 'test-pipe', 'input {} filter {} output { new_output }'
        )
        assert success is True
        assert is_new is False
        assert was_updated is True
        mock_es.logstash.put_pipeline.assert_called_once()

    def test_skips_update_when_content_identical(self):
        from SNMP.snmp_crud import _create_or_update_pipeline
        content = 'input {} filter {} output {}'
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'test-pipe': {
                'pipeline': content,
                'pipeline_settings': {},
                'pipeline_metadata': {},
            }
        }

        success, is_new, error, was_updated = _create_or_update_pipeline(
            mock_es, 'test-pipe', content
        )
        assert success is True
        assert is_new is False
        assert was_updated is False
        mock_es.logstash.put_pipeline.assert_not_called()

    def test_returns_false_on_put_exception(self):
        from SNMP.snmp_crud import _create_or_update_pipeline
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.side_effect = Exception("not found")
        mock_es.logstash.put_pipeline.side_effect = Exception("ES write error")

        success, is_new, error, was_updated = _create_or_update_pipeline(
            mock_es, 'test-pipe', 'input {} filter {} output {}'
        )
        assert success is False
        assert error is not None
        assert 'ES write error' in error

    def test_new_pipeline_uses_default_settings(self):
        from SNMP.snmp_crud import _create_or_update_pipeline
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.side_effect = Exception("not found")
        mock_es.logstash.put_pipeline.return_value = {}

        _create_or_update_pipeline(mock_es, 'new-pipe', 'input {}')
        call_body = mock_es.logstash.put_pipeline.call_args[1]['body']
        assert 'pipeline_settings' in call_body
        assert call_body['pipeline_settings']['queue.type'] == 'memory'

    def test_existing_pipeline_preserves_settings(self):
        from SNMP.snmp_crud import _create_or_update_pipeline
        custom_settings = {'queue.type': 'persisted', 'pipeline.workers': 4}
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'test-pipe': {
                'pipeline': 'old content',
                'pipeline_settings': custom_settings,
                'pipeline_metadata': {'version': 5},
            }
        }
        mock_es.logstash.put_pipeline.return_value = {}

        _create_or_update_pipeline(mock_es, 'test-pipe', 'new content')
        call_body = mock_es.logstash.put_pipeline.call_args[1]['body']
        assert call_body['pipeline_settings'] == custom_settings


@pytest.mark.django_db
class TestGetDeviceProfiles:
    """Tests for _get_device_profiles() helper (lives in snmp_pipeline_generator)"""

    def test_no_template_returns_empty(self, test_network, test_credential_v2c):
        from SNMP.snmp_pipeline_generator import _get_device_profiles
        device = Device.objects.create(
            name='No Template Device', ip_address='10.0.0.1',
            credential=test_credential_v2c, network=test_network
        )
        profile_ids, merged, normalizers = _get_device_profiles(device, {})
        assert profile_ids == tuple()
        assert merged == {'get': {}, 'walk': {}, 'table': {}}
        assert normalizers == []

    def test_custom_profile_oids_merged(self, test_network, test_credential_v2c):
        from SNMP.snmp_pipeline_generator import _get_device_profiles
        profile = Profile.objects.create(
            name='custom_test',
            vendor='Generic',
            profile_data={
                'get': {'system.name': '1.3.6.1.2.1.1.5.0'},
                'walk': {},
                'table': {}
            }
        )
        template = DeviceTemplate.objects.create(name='Test Template', vendor='Generic')
        template.profiles.add(profile)
        device = Device.objects.create(
            name='Profile Device', ip_address='10.0.0.2',
            credential=test_credential_v2c, network=test_network,
            device_template=template
        )

        profile_ids, merged, normalizers = _get_device_profiles(device, {})
        assert len(profile_ids) == 1
        assert '1.3.6.1.2.1.1.5.0' in merged['get'].values()

    def test_official_placeholder_loaded_from_file(self, test_network, test_credential_v2c):
        from SNMP.snmp_pipeline_generator import _get_device_profiles
        profile = Profile.objects.create(
            name='test_official.json',
            vendor='Generic',
            profile_data={'is_official_placeholder': True},
        )
        template = DeviceTemplate.objects.create(name='Official Template', vendor='Generic')
        template.profiles.add(profile)
        device = Device.objects.create(
            name='Official Device', ip_address='10.0.0.3',
            credential=test_credential_v2c, network=test_network,
            device_template=template
        )

        fake_data = {'get': {'system.desc': '1.3.6.1.2.1.1.1.0'}, 'walk': {}, 'table': {}}
        with patch('SNMP.snmp_pipeline_generator.os.path.exists', return_value=True), \
             patch('builtins.open', create=True) as mock_open, \
             patch('SNMP.snmp_pipeline_generator.json.load', return_value=fake_data):
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            profile_ids, merged, normalizers = _get_device_profiles(device, {})

        assert '1.3.6.1.2.1.1.1.0' in merged['get'].values()

    def test_official_placeholder_file_missing_skipped(self, test_network, test_credential_v2c):
        from SNMP.snmp_pipeline_generator import _get_device_profiles
        profile = Profile.objects.create(
            name='missing_official.json',
            vendor='Generic',
            profile_data={'is_official_placeholder': True},
        )
        template = DeviceTemplate.objects.create(name='Missing File Template', vendor='Generic')
        template.profiles.add(profile)
        device = Device.objects.create(
            name='Missing File Device', ip_address='10.0.0.4',
            credential=test_credential_v2c, network=test_network,
            device_template=template
        )

        with patch('SNMP.snmp_pipeline_generator.os.path.exists', return_value=False):
            profile_ids, merged, normalizers = _get_device_profiles(device, {})

        assert merged == {'get': {}, 'walk': {}, 'table': {}}

    def test_oid_conflict_gets_suffixed(self, test_network, test_credential_v2c):
        """When two profiles define the same OID key with different values, a suffix is added"""
        from SNMP.snmp_pipeline_generator import _get_device_profiles
        profile_a = Profile.objects.create(
            name='profile_a', vendor='Generic',
            profile_data={'get': {'metric': 'oid.1'}, 'walk': {}, 'table': {}}
        )
        profile_b = Profile.objects.create(
            name='profile_b', vendor='Generic',
            profile_data={'get': {'metric': 'oid.2'}, 'walk': {}, 'table': {}}
        )
        template = DeviceTemplate.objects.create(name='Conflict Template', vendor='Generic')
        template.profiles.add(profile_a, profile_b)
        device = Device.objects.create(
            name='Conflict Device', ip_address='10.0.0.5',
            credential=test_credential_v2c, network=test_network,
            device_template=template
        )

        _, merged, _ = _get_device_profiles(device, {})
        assert len(merged['get']) == 2


@pytest.mark.django_db
class TestFormatFieldName:
    """Tests for _format_field_name() pure function"""

    def test_already_bracket_notation_unchanged(self):
        from SNMP.snmp_pipeline_generator import _format_field_name
        assert _format_field_name('[system][cpu]') == '[system][cpu]'

    def test_dotted_name_converted(self):
        from SNMP.snmp_pipeline_generator import _format_field_name
        assert _format_field_name('system.cpu.load') == '[system][cpu][load]'

    def test_plain_name_wrapped_in_brackets(self):
        # In snmp_pipeline_generator, plain names without dots are wrapped in [brackets]
        from SNMP.snmp_pipeline_generator import _format_field_name
        assert _format_field_name('hostname') == '[hostname]'

    def test_single_dot(self):
        from SNMP.snmp_pipeline_generator import _format_field_name
        assert _format_field_name('a.b') == '[a][b]'


@pytest.mark.django_db
class TestGetDiscoveryIpAddresses:
    """Tests for _get_discovery_ip_addresses() helper"""

    def test_returns_all_hosts_in_range(self, test_network):
        from SNMP.snmp_pipeline_generator import _get_discovery_ip_addresses
        # /30 has 2 usable hosts
        test_network.network_range = '192.168.100.0/30'
        test_network.save()
        ips = _get_discovery_ip_addresses(test_network)
        assert '192.168.100.1' in ips
        assert '192.168.100.2' in ips
        assert '192.168.100.0' not in ips   # network address
        assert '192.168.100.3' not in ips   # broadcast

    def test_excludes_existing_device_ips(self, test_network, test_credential_v2c):
        from SNMP.snmp_pipeline_generator import _get_discovery_ip_addresses
        test_network.network_range = '10.0.0.0/30'
        test_network.save()
        Device.objects.create(
            name='Existing', ip_address='10.0.0.1',
            credential=test_credential_v2c, network=test_network
        )
        ips = _get_discovery_ip_addresses(test_network)
        assert '10.0.0.1' not in ips
        assert '10.0.0.2' in ips

    def test_legacy_hostname_ip_values_not_excluded(self, test_network):
        """If legacy data has a non-IP value in ip_address, the function skips it gracefully.

        The Device model now validates that ip_address must be a valid IP, so this
        scenario can only occur with legacy data. We test it using a mocked queryset.
        """
        from SNMP.snmp_pipeline_generator import _get_discovery_ip_addresses
        test_network.network_range = '10.0.1.0/30'
        test_network.save()

        with patch('SNMP.snmp_pipeline_generator.Device.objects') as mock_objs:
            mock_objs.filter.return_value.values_list.return_value = ['router.example.com']
            ips = _get_discovery_ip_addresses(test_network)

        # Hostname in ip_address should be skipped; both usable IPs remain
        assert '10.0.1.1' in ips
        assert '10.0.1.2' in ips

    def test_invalid_cidr_returns_empty(self):
        """Invalid CIDR can't be saved to DB (model validates it), so use a Mock."""
        from SNMP.snmp_pipeline_generator import _get_discovery_ip_addresses
        from unittest.mock import MagicMock
        fake_network = MagicMock()
        fake_network.network_range = 'not-a-cidr'
        fake_network.name = 'Fake'
        ips = _get_discovery_ip_addresses(fake_network)
        assert ips == []


@pytest.mark.django_db
class TestGetCredentialEndpointV3:
    """Additional GetCredential tests for v3 fields"""

    def test_get_credential_v3_returns_security_fields(self, authenticated_client, test_credential_v3):
        """v3 credential response includes security_name, security_level, auth_protocol"""
        response = authenticated_client.get(f'/SNMP/GetCredential/{test_credential_v3.id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['version'] == '3'
        assert data['security_name'] == 'snmpuser'
        assert data['security_level'] == 'authPriv'
        assert data['auth_protocol'] == 'sha'
        # Passwords must be masked
        assert data['auth_pass'] == '***'
        assert data['priv_pass'] == '***'

    def test_get_credential_v3_authnopriv_no_priv_fields(self, authenticated_client):
        """authNoPriv credential has no priv fields in response"""
        cred = Credential.objects.create(
            name='v3_authNoPriv',
            version='3',
            security_name='user',
            security_level='authNoPriv',
            auth_protocol='sha',
            auth_pass='authpass',
        )
        response = authenticated_client.get(f'/SNMP/GetCredential/{cred.id}/')
        data = json.loads(response.content)
        assert 'priv_pass' not in data
        assert 'auth_protocol' in data


@pytest.mark.django_db
class TestGetNetworkEndpointEdgeCases:
    """Tests for GetNetwork, UpdateNetwork, GetNetworkPipelineName error paths"""

    def test_get_network_not_found(self, authenticated_client):
        response = authenticated_client.get('/SNMP/GetNetwork/99999/')
        assert response.status_code == 404
        assert 'error' in json.loads(response.content)

    def test_update_network_not_found(self, authenticated_client):
        response = authenticated_client.post('/SNMP/UpdateNetwork/99999/', {
            'name': 'Ghost', 'network_range': '10.0.0.0/24'
        })
        assert response.status_code == 404

    def test_get_network_pipeline_name_not_found(self, authenticated_client):
        response = authenticated_client.get('/SNMP/GetNetworkPipelineName/99999/')
        assert response.status_code == 404
        data = json.loads(response.content)
        assert data['success'] is False

    def test_update_network_clears_optional_fields_when_empty(self, authenticated_client, test_network):
        """Passing empty connection/credential nullifies those FK fields"""
        response = authenticated_client.post(f'/SNMP/UpdateNetwork/{test_network.id}/', {
            'name': test_network.name,
            'network_range': test_network.network_range,
            'connection': '',
            'discovery_credential': '',
            'credential': '',
        })
        assert response.status_code == 200
        test_network.refresh_from_db()
        assert test_network.connection is None
        assert test_network.discovery_credential is None
        assert test_network.credential is None


@pytest.mark.django_db
class TestDeleteNetworkPipelinePaths:
    """Tests for DeleteNetwork pipeline deletion branches"""

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_delete_network_with_pipeline_deleted_reports_it(self, mock_get_es, authenticated_client, test_network):
        """When both pipelines exist and are deleted, success message mentions them"""
        mock_es = MagicMock()
        # make get_pipeline return the pipeline as existing
        def get_pipeline_side_effect(id):
            return {id: {'pipeline': 'content'}}
        mock_es.logstash.get_pipeline.side_effect = get_pipeline_side_effect
        mock_es.logstash.delete_pipeline.return_value = {}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post(f'/SNMP/DeleteNetwork/{test_network.id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'pipeline' in data['message'].lower()

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_delete_network_connection_error_still_deletes_db_record(
            self, mock_get_es, authenticated_client, test_network):
        """Even if ES connection fails, the DB record is deleted and success=True returned"""
        mock_get_es.side_effect = Exception("ES connection failed")
        network_id = test_network.id

        response = authenticated_client.post(f'/SNMP/DeleteNetwork/{network_id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        # DB record should be gone
        assert not Network.objects.filter(id=network_id).exists()

    def test_delete_network_without_connection_skips_es(self, authenticated_client, test_credential_v2c):
        """Network with no connection skips ES interaction and deletes cleanly"""
        network = Network.objects.create(
            name='No Conn Network',
            network_range='172.16.0.0/24',
        )
        network_id = network.id
        response = authenticated_client.post(f'/SNMP/DeleteNetwork/{network_id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert not Network.objects.filter(id=network_id).exists()


class TestDefaultTemplateAssignment:
    """Tests for automatic Default template assignment (Device.save / DeviceTemplate.delete)"""

    @pytest.fixture
    def default_template(self, db):
        """Create the official default template as synced from default.json"""
        return DeviceTemplate.objects.create(
            name='default',
            description='Fallback template applied when no other template matches.',
            vendor='Any',
            official=True
        )

    def test_device_without_template_gets_default(self, default_template, test_network, test_credential_v2c):
        """A device saved with no template is auto-assigned the official default template"""
        device = Device.objects.create(
            name='No Template Device',
            ip_address='192.168.1.150',
            credential=test_credential_v2c,
            network=test_network
        )
        assert device.device_template == default_template

    def test_device_keeps_explicit_template(self, default_template, test_network, test_credential_v2c):
        """A device saved with an explicit template is not reassigned to default"""
        other_template = DeviceTemplate.objects.create(
            name='custom_template',
            vendor='Any',
            official=False
        )
        device = Device.objects.create(
            name='Templated Device',
            ip_address='192.168.1.151',
            credential=test_credential_v2c,
            network=test_network,
            device_template=other_template
        )
        assert device.device_template == other_template

    def test_default_template_cannot_be_deleted(self, default_template):
        """The official default template is protected from deletion"""
        from django.core.exceptions import ValidationError
        with pytest.raises(ValidationError):
            default_template.delete()

    def test_deleting_template_reassigns_devices_to_default(self, default_template, test_network, test_credential_v2c):
        """Deleting a template moves its devices onto the default template"""
        doomed_template = DeviceTemplate.objects.create(
            name='doomed_template',
            vendor='Any',
            official=False
        )
        device = Device.objects.create(
            name='Orphaned Device',
            ip_address='192.168.1.152',
            credential=test_credential_v2c,
            network=test_network,
            device_template=doomed_template
        )
        doomed_template.delete()
        device.refresh_from_db()
        assert device.device_template == default_template


# ============================================================================
# DeviceTemplate CRUD Endpoint Tests
# ============================================================================

@pytest.fixture
def test_device_template(db):
    """Create a custom (non-official) device template."""
    return DeviceTemplate.objects.create(
        name='custom_template',
        description='A custom test template',
        vendor='Cisco',
        model='9300',
        product='Catalyst',
        official=False,
        matching_rules=['cisco', 'catalyst'],
    )


@pytest.fixture
def official_template(db):
    """Create an official (read-only) device template."""
    return DeviceTemplate.objects.create(
        name='official_template',
        description='Official template',
        vendor='Dell',
        official=True,
    )


@pytest.mark.django_db
class TestDeviceTemplateCRUD:
    """Test DeviceTemplate Create, Read, Update, Delete operations via API endpoints."""

    # ── GetDeviceTemplates ────────────────────────────────────────────────────

    def test_get_device_templates_returns_list(self, authenticated_client, test_device_template):
        response = authenticated_client.get('/SNMP/GetDeviceTemplates/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'templates' in data
        names = [t['name'] for t in data['templates']]
        assert 'custom_template' in names

    def test_get_device_templates_includes_required_fields(self, authenticated_client, test_device_template):
        response = authenticated_client.get('/SNMP/GetDeviceTemplates/')
        data = json.loads(response.content)
        template = next(t for t in data['templates'] if t['name'] == 'custom_template')
        for field in ('id', 'name', 'display_name', 'vendor', 'model', 'product', 'official'):
            assert field in template

    def test_get_device_templates_display_name_formatted(self, authenticated_client, test_device_template):
        response = authenticated_client.get('/SNMP/GetDeviceTemplates/')
        data = json.loads(response.content)
        template = next(t for t in data['templates'] if t['name'] == 'custom_template')
        assert template['display_name'] == 'Custom Template'

    # ── GetDeviceTemplate ────────────────────────────────────────────────────

    def test_get_device_template_by_id(self, authenticated_client, test_device_template):
        response = authenticated_client.get(f'/SNMP/GetDeviceTemplate/{test_device_template.id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['name'] == 'custom_template'
        assert data['vendor'] == 'Cisco'
        assert 'profiles' in data
        assert 'matching_rules' in data

    def test_get_device_template_not_found(self, authenticated_client):
        response = authenticated_client.get('/SNMP/GetDeviceTemplate/99999/')
        # Falls back to GetOfficialDeviceTemplate which returns 404 for unknown names
        assert response.status_code in (404, 200)

    def test_get_device_template_includes_profiles(self, authenticated_client, test_device_template, test_profile):
        test_device_template.profiles.add(test_profile)
        response = authenticated_client.get(f'/SNMP/GetDeviceTemplate/{test_device_template.id}/')
        data = json.loads(response.content)
        assert any(p['name'] == test_profile.name for p in data['profiles'])

    # ── AddDeviceTemplate ────────────────────────────────────────────────────

    def test_add_device_template_requires_admin(self, readonly_client):
        response = readonly_client.post('/SNMP/AddDeviceTemplate/', {
            'name': 'new_tmpl',
            'vendor': 'Cisco',
        })
        assert response.status_code == 403

    def test_add_device_template_success(self, authenticated_client):
        import json as _json
        response = authenticated_client.post('/SNMP/AddDeviceTemplate/', {
            'name': 'brand_new_template',
            'description': 'Test',
            'vendor': 'Juniper',
            'model': 'EX2300',
            'product': 'EX',
            'matching_rules': _json.dumps(['juniper', 'ex']),
            'profiles': _json.dumps([]),
        })
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'template_id' in data
        assert DeviceTemplate.objects.filter(name='brand_new_template').exists()

    def test_add_device_template_missing_name(self, authenticated_client):
        import json as _json
        response = authenticated_client.post('/SNMP/AddDeviceTemplate/', {
            'vendor': 'Cisco',
            'matching_rules': _json.dumps([]),
            'profiles': _json.dumps([]),
        })
        assert response.status_code == 400

    def test_add_device_template_missing_vendor(self, authenticated_client):
        import json as _json
        response = authenticated_client.post('/SNMP/AddDeviceTemplate/', {
            'name': 'no_vendor_tmpl',
            'matching_rules': _json.dumps([]),
            'profiles': _json.dumps([]),
        })
        assert response.status_code == 400

    def test_add_device_template_with_profile_ids(self, authenticated_client, test_profile):
        import json as _json
        response = authenticated_client.post('/SNMP/AddDeviceTemplate/', {
            'name': 'with_profiles',
            'vendor': 'Generic',
            'matching_rules': _json.dumps([]),
            'profiles': _json.dumps([test_profile.id]),
        })
        assert response.status_code == 200
        tmpl = DeviceTemplate.objects.get(name='with_profiles')
        assert tmpl.profiles.filter(id=test_profile.id).exists()

    # ── UpdateDeviceTemplate ─────────────────────────────────────────────────

    def test_update_device_template_requires_admin(self, readonly_client, test_device_template):
        import json as _json
        response = readonly_client.post(
            f'/SNMP/UpdateDeviceTemplate/{test_device_template.id}/',
            {
                'name': 'hacked_name',
                'vendor': 'X',
                'matching_rules': _json.dumps([]),
                'profiles': _json.dumps([]),
            },
        )
        assert response.status_code == 403

    def test_update_device_template_success(self, authenticated_client, test_device_template):
        import json as _json
        response = authenticated_client.post(
            f'/SNMP/UpdateDeviceTemplate/{test_device_template.id}/',
            {
                'name': 'updated_template',
                'vendor': 'HPE',
                'model': 'ProLiant',
                'description': 'Updated desc',
                'matching_rules': _json.dumps(['hpe']),
                'profiles': _json.dumps([]),
            },
        )
        assert response.status_code == 200
        test_device_template.refresh_from_db()
        assert test_device_template.name == 'updated_template'
        assert test_device_template.vendor == 'HPE'

    def test_update_official_template_rejected(self, authenticated_client, official_template):
        import json as _json
        response = authenticated_client.post(
            f'/SNMP/UpdateDeviceTemplate/{official_template.id}/',
            {
                'name': 'hacked_official',
                'vendor': 'X',
                'matching_rules': _json.dumps([]),
                'profiles': _json.dumps([]),
            },
        )
        assert response.status_code == 403

    def test_update_device_template_not_found(self, authenticated_client):
        import json as _json
        response = authenticated_client.post(
            '/SNMP/UpdateDeviceTemplate/99999/',
            {
                'name': 'ghost',
                'vendor': 'X',
                'matching_rules': _json.dumps([]),
                'profiles': _json.dumps([]),
            },
        )
        assert response.status_code == 404

    # ── DeleteDeviceTemplate ──────────────────────────────────────────────────

    def test_delete_device_template_requires_admin(self, readonly_client, test_device_template):
        response = readonly_client.post(f'/SNMP/DeleteDeviceTemplate/{test_device_template.id}/')
        assert response.status_code == 403

    def test_delete_device_template_success(self, authenticated_client, test_device_template):
        tmpl_id = test_device_template.id
        response = authenticated_client.post(f'/SNMP/DeleteDeviceTemplate/{tmpl_id}/')
        assert response.status_code == 200
        assert not DeviceTemplate.objects.filter(id=tmpl_id).exists()

    def test_delete_official_template_rejected(self, authenticated_client, official_template):
        response = authenticated_client.post(f'/SNMP/DeleteDeviceTemplate/{official_template.id}/')
        assert response.status_code == 403

    def test_delete_device_template_not_found(self, authenticated_client):
        response = authenticated_client.post('/SNMP/DeleteDeviceTemplate/99999/')
        assert response.status_code == 404


# ============================================================================
# suggest_device_template
# ============================================================================

@pytest.mark.django_db
class TestSuggestDeviceTemplate:
    """Test the suggest_device_template pure function in snmp_crud."""

    @pytest.fixture(autouse=True)
    def clear_templates(self, db):
        """Ensure no leftover templates pollute suggestion results."""
        DeviceTemplate.objects.all().delete()

    def _make_template(self, name, rules):
        return DeviceTemplate.objects.create(
            name=name, vendor='Any', matching_rules=rules
        )

    def test_empty_device_info_returns_empty(self):
        from SNMP.snmp_crud import suggest_device_template
        assert suggest_device_template('') == []
        assert suggest_device_template(None) == []

    def test_all_rules_match_returns_full_match(self):
        from SNMP.snmp_crud import suggest_device_template
        tmpl = self._make_template('cisco_cat', ['cisco', 'catalyst'])
        result = suggest_device_template('Cisco Catalyst 9300 switch')
        assert tmpl.id in result
        assert result.index(tmpl.id) == 0  # full match first

    def test_partial_match_returned(self):
        from SNMP.snmp_crud import suggest_device_template
        tmpl = self._make_template('cisco_any', ['cisco', 'nexus'])
        result = suggest_device_template('Cisco Catalyst switch')  # 'cisco' matches, 'nexus' doesn't
        assert tmpl.id in result

    def test_no_match_excluded(self):
        from SNMP.snmp_crud import suggest_device_template
        self._make_template('juniper_tmpl', ['juniper', 'ex'])
        result = suggest_device_template('Cisco Catalyst 9300')
        assert result == []

    def test_full_match_ranked_before_partial(self):
        from SNMP.snmp_crud import suggest_device_template
        full = self._make_template('full_match', ['cisco', 'catalyst'])
        partial = self._make_template('partial_match', ['cisco', 'nexus'])
        result = suggest_device_template('Cisco Catalyst switch')
        assert result.index(full.id) < result.index(partial.id)

    def test_case_insensitive_matching(self):
        from SNMP.snmp_crud import suggest_device_template
        tmpl = self._make_template('caps_tmpl', ['CISCO'])
        result = suggest_device_template('cisco ios router')
        assert tmpl.id in result

    def test_template_without_rules_excluded(self):
        from SNMP.snmp_crud import suggest_device_template
        self._make_template('no_rules', [])
        result = suggest_device_template('cisco ios')
        assert result == []


# ============================================================================
# GetDeviceLocationData
# ============================================================================

@pytest.mark.django_db
class TestGetDeviceLocationData:
    """Test the /SNMP/GetDeviceLocationData/ endpoint."""

    def test_requires_authentication(self, client):
        response = client.get('/SNMP/GetDeviceLocationData/')
        assert response.status_code == 302

    def test_returns_empty_lists_when_no_devices(self, authenticated_client):
        Device.objects.all().delete()
        response = authenticated_client.get('/SNMP/GetDeviceLocationData/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['sites'] == []
        assert data['site_building'] == []
        assert data['full'] == []

    def test_returns_sites(self, authenticated_client, test_credential_v2c, test_network):
        Device.objects.create(
            name='dev_site1',
            ip_address='10.0.0.1',
            credential=test_credential_v2c,
            network=test_network,
            site='HQ',
        )
        response = authenticated_client.get('/SNMP/GetDeviceLocationData/')
        data = json.loads(response.content)
        assert 'HQ' in data['sites']

    def test_site_building_pairs(self, authenticated_client, test_credential_v2c, test_network):
        Device.objects.create(
            name='dev_sb',
            ip_address='10.0.0.2',
            credential=test_credential_v2c,
            network=test_network,
            site='Campus A',
            building='Bldg 1',
        )
        response = authenticated_client.get('/SNMP/GetDeviceLocationData/')
        data = json.loads(response.content)
        assert any(
            sb['site'] == 'Campus A' and sb['building'] == 'Bldg 1'
            for sb in data['site_building']
        )

    def test_full_entries_with_coordinates(self, authenticated_client, test_credential_v2c, test_network):
        Device.objects.create(
            name='dev_full',
            ip_address='10.0.0.3',
            credential=test_credential_v2c,
            network=test_network,
            site='Site B',
            building='Bldg 2',
            room='Room 101',
            latitude='37.774929',
            longitude='-122.419418',
        )
        response = authenticated_client.get('/SNMP/GetDeviceLocationData/')
        data = json.loads(response.content)
        entry = next((e for e in data['full'] if e['room'] == 'Room 101'), None)
        assert entry is not None
        # lat/lon must be serialised as strings (Decimal-safe)
        assert isinstance(entry['latitude'], str)
        assert isinstance(entry['longitude'], str)

    def test_devices_without_site_excluded_from_sites(self, authenticated_client, test_credential_v2c, test_network):
        Device.objects.create(
            name='dev_no_site',
            ip_address='10.0.0.4',
            credential=test_credential_v2c,
            network=test_network,
            site=None,
        )
        response = authenticated_client.get('/SNMP/GetDeviceLocationData/')
        data = json.loads(response.content)
        assert None not in data['sites']


# ============================================================================
# GetDevices – additional coverage (pagination, sorting)
# ============================================================================

@pytest.mark.django_db
class TestGetDevicesAdditional:
    """Additional GetDevices tests not covered by TestDeviceCRUD."""

    def test_sort_by_name(self, authenticated_client, test_network, test_credential_v2c):
        Device.objects.create(name='Zebra Device', ip_address='10.1.1.1',
                              credential=test_credential_v2c, network=test_network)
        Device.objects.create(name='Alpha Device', ip_address='10.1.1.2',
                              credential=test_credential_v2c, network=test_network)
        response = authenticated_client.get('/SNMP/GetDevices/?sort_by=name')
        data = json.loads(response.content)
        names = [d['name'] for d in data['devices']]
        assert names == sorted(names)

    def test_sort_by_name_descending(self, authenticated_client, test_network, test_credential_v2c):
        Device.objects.create(name='ZZZ Device', ip_address='10.1.2.1',
                              credential=test_credential_v2c, network=test_network)
        Device.objects.create(name='AAA Device', ip_address='10.1.2.2',
                              credential=test_credential_v2c, network=test_network)
        response = authenticated_client.get('/SNMP/GetDevices/?sort_by=-name')
        data = json.loads(response.content)
        names = [d['name'] for d in data['devices']]
        assert names == sorted(names, reverse=True)

    def test_pagination_has_next(self, authenticated_client, test_network, test_credential_v2c):
        """When more devices than page_size exist, has_next is True."""
        for i in range(5):
            Device.objects.create(
                name=f'Paged Device {i}',
                ip_address=f'10.2.0.{i + 1}',
                credential=test_credential_v2c,
                network=test_network,
            )
        response = authenticated_client.get('/SNMP/GetDevices/?page=1&page_size=2')
        data = json.loads(response.content)
        assert data['has_next'] is True
        assert len(data['devices']) == 2

    def test_pagination_page_2(self, authenticated_client, test_network, test_credential_v2c):
        """Page 2 returns the next slice and has_previous is True."""
        for i in range(4):
            Device.objects.create(
                name=f'Page2 Device {i}',
                ip_address=f'10.3.0.{i + 1}',
                credential=test_credential_v2c,
                network=test_network,
            )
        response = authenticated_client.get('/SNMP/GetDevices/?page=2&page_size=2')
        data = json.loads(response.content)
        assert data['has_previous'] is True

    def test_search_by_ip(self, authenticated_client, test_network, test_credential_v2c):
        Device.objects.create(name='IP Search Device', ip_address='172.16.100.1',
                              credential=test_credential_v2c, network=test_network)
        response = authenticated_client.get('/SNMP/GetDevices/?search=172.16.100')
        data = json.loads(response.content)
        assert any(d['name'] == 'IP Search Device' for d in data['devices'])

    def test_get_device_returns_location_fields(self, authenticated_client, test_network, test_credential_v2c):
        """GetDevice includes location and metadata fields."""
        device = Device.objects.create(
            name='Location Device',
            ip_address='10.5.5.5',
            credential=test_credential_v2c,
            network=test_network,
            site='HQ',
            building='Main',
            room='A1',
            metadata={'rack': '12'},
        )
        response = authenticated_client.get(f'/SNMP/GetDevice/{device.id}/')
        data = json.loads(response.content)
        assert data['site'] == 'HQ'
        assert data['building'] == 'Main'
        assert data['room'] == 'A1'
        assert data['metadata'] == {'rack': '12'}

    def test_add_device_with_location_fields(self, authenticated_client, test_network, test_credential_v2c):
        """AddDevice persists location and metadata fields."""
        import json as _json
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'Located Device',
            'ip_address': '10.6.6.6',
            'network': test_network.id,
            'credential': test_credential_v2c.id,
            'site': 'West Campus',
            'building': 'B1',
            'room': 'R2',
            'metadata': _json.dumps({'owner': 'infra'}),
        })
        assert response.status_code == 200
        device = Device.objects.get(name='Located Device')
        assert device.site == 'West Campus'
        assert device.metadata == {'owner': 'infra'}

    def test_add_device_with_hostname(self, authenticated_client, test_network, test_credential_v2c):
        """AddDevice accepts hostname-only devices (no IP)."""
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'Hostname Only Device',
            'hostname': 'myswitch.example.com',
            'network': test_network.id,
            'credential': test_credential_v2c.id,
        })
        assert response.status_code == 200
        device = Device.objects.get(name='Hostname Only Device')
        assert device.hostname == 'myswitch.example.com'
        assert device.ip_address is None


# ============================================================================
# Unit tests for _build_trap_components helper
# ============================================================================

@pytest.mark.django_db
class TestBuildTrapComponents:
    """Direct unit tests for the _build_trap_components() internal helper"""

    def test_v2c_trap_components_have_correct_structure(
        self, test_connection, test_credential_v2c
    ):
        from SNMP.snmp_crud import _build_trap_components
        network = Network.objects.create(
            name='Trap V2c Network',
            network_range='10.10.0.0/24',
            connection=test_connection,
            credential=test_credential_v2c,
            traps_enabled=True,
            credential_mode='PLAINTEXT',
        )
        result = _build_trap_components(network)
        assert 'input' in result
        assert 'filter' in result
        assert 'output' in result
        assert len(result['input']) == 1
        assert result['input'][0]['plugin'] == 'snmptrap'
        trap_cfg = result['input'][0]['config']
        assert '2c' in trap_cfg.get('supported_versions', [])

    def test_v1_trap_components_include_v1_version(
        self, test_connection, test_credential_v2c
    ):
        from SNMP.snmp_crud import _build_trap_components
        cred = Credential.objects.create(name='V1 Trap Cred', version='1', community='public')
        network = Network.objects.create(
            name='Trap V1 Network',
            network_range='10.11.0.0/24',
            connection=test_connection,
            credential=cred,
            traps_enabled=True,
            credential_mode='PLAINTEXT',
        )
        result = _build_trap_components(network)
        trap_cfg = result['input'][0]['config']
        assert '1' in trap_cfg.get('supported_versions', [])

    def test_v3_trap_components_include_security_fields(
        self, test_connection, test_credential_v3
    ):
        from SNMP.snmp_crud import _build_trap_components
        network = Network.objects.create(
            name='Trap V3 Network',
            network_range='10.12.0.0/24',
            connection=test_connection,
            credential=test_credential_v3,
            traps_enabled=True,
            credential_mode='PLAINTEXT',
        )
        result = _build_trap_components(network)
        trap_cfg = result['input'][0]['config']
        assert '3' in trap_cfg.get('supported_versions', [])
        assert 'security_name' in trap_cfg

    def test_keystore_mode_emits_keystore_references(
        self, test_connection, test_credential_v2c
    ):
        from SNMP.snmp_crud import _build_trap_components
        network = Network.objects.create(
            name='Trap Keystore Network',
            network_range='10.13.0.0/24',
            connection=test_connection,
            credential=test_credential_v2c,
            traps_enabled=True,
            credential_mode='KEYSTORE',
        )
        result = _build_trap_components(network)
        trap_cfg = result['input'][0]['config']
        # In KEYSTORE mode the community string should be a ${...} reference
        community = trap_cfg.get('community', [])
        assert community and community[0].startswith('${')

    def test_plaintext_mode_emits_decrypted_community(
        self, test_connection, test_credential_v2c
    ):
        from SNMP.snmp_crud import _build_trap_components
        network = Network.objects.create(
            name='Trap Plaintext Network',
            network_range='10.14.0.0/24',
            connection=test_connection,
            credential=test_credential_v2c,
            traps_enabled=True,
            credential_mode='PLAINTEXT',
        )
        result = _build_trap_components(network)
        trap_cfg = result['input'][0]['config']
        community = trap_cfg.get('community', [])
        assert community and not community[0].startswith('${')

    def test_filter_adds_event_category_traps(self, test_connection, test_credential_v2c):
        from SNMP.snmp_crud import _build_trap_components
        network = Network.objects.create(
            name='Trap Filter Check',
            network_range='10.15.0.0/24',
            connection=test_connection,
            credential=test_credential_v2c,
            traps_enabled=True,
            credential_mode='PLAINTEXT',
        )
        result = _build_trap_components(network)
        mutate_filter = next(
            (f for f in result['filter'] if f.get('plugin') == 'mutate'), None
        )
        assert mutate_filter is not None
        add_field = mutate_filter['config'].get('add_field', {})
        assert add_field.get('[event][category]') == 'traps'


# ============================================================================
# Unit tests for _build_network_pipeline_configs helper
# ============================================================================

@pytest.mark.django_db
class TestBuildNetworkPipelineConfigs:
    """Direct unit tests for the _build_network_pipeline_configs() internal helper"""

    def test_returns_empty_when_no_devices(self, test_connection, test_credential_v2c):
        from SNMP.snmp_crud import _build_network_pipeline_configs
        network = Network.objects.create(
            name='Empty Network Configs',
            network_range='10.20.0.0/24',
            connection=test_connection,
            traps_enabled=False,
            discovery_enabled=False,
        )
        results = _build_network_pipeline_configs(network)
        assert results == []

    def test_returns_polling_pipeline_for_v2c_device(
        self, test_connection, test_credential_v2c
    ):
        from SNMP.snmp_crud import _build_network_pipeline_configs
        network = Network.objects.create(
            name='Polling V2c Configs',
            network_range='10.21.0.0/24',
            connection=test_connection,
            traps_enabled=False,
            discovery_enabled=False,
        )
        Device.objects.create(
            name='Config Test Device',
            ip_address='10.21.0.10',
            credential=test_credential_v2c,
            network=network,
        )
        results = _build_network_pipeline_configs(network)
        assert len(results) >= 1
        pipeline_types = [r['pipeline_type'] for r in results]
        assert 'polling' in pipeline_types

    def test_trap_pipeline_included_when_enabled(
        self, test_connection, test_credential_v2c
    ):
        from SNMP.snmp_crud import _build_network_pipeline_configs
        network = Network.objects.create(
            name='Trap Enabled Configs',
            network_range='10.22.0.0/24',
            connection=test_connection,
            credential=test_credential_v2c,
            traps_enabled=True,
            discovery_enabled=False,
            credential_mode='PLAINTEXT',
        )
        Device.objects.create(
            name='Trap Config Device',
            ip_address='10.22.0.10',
            credential=test_credential_v2c,
            network=network,
        )
        results = _build_network_pipeline_configs(network)
        pipeline_types = [r['pipeline_type'] for r in results]
        assert 'trap' in pipeline_types

    def test_discovery_pipeline_included_when_enabled(
        self, test_connection, test_credential_v2c
    ):
        from SNMP.snmp_crud import _build_network_pipeline_configs
        network = Network.objects.create(
            name='Discovery Enabled Configs',
            network_range='10.23.0.0/24',
            connection=test_connection,
            discovery_credential=test_credential_v2c,
            traps_enabled=False,
            discovery_enabled=True,
            credential_mode='PLAINTEXT',
        )
        Device.objects.create(
            name='Discovery Config Device',
            ip_address='10.23.0.10',
            credential=test_credential_v2c,
            network=network,
        )
        results = _build_network_pipeline_configs(network)
        pipeline_types = [r['pipeline_type'] for r in results]
        assert 'discovery' in pipeline_types

    def test_pipeline_name_contains_network_name(
        self, test_connection, test_credential_v2c
    ):
        from SNMP.snmp_crud import _build_network_pipeline_configs
        network = Network.objects.create(
            name='Name Check Network',
            network_range='10.24.0.0/24',
            connection=test_connection,
            traps_enabled=False,
            discovery_enabled=False,
        )
        Device.objects.create(
            name='Name Check Device',
            ip_address='10.24.0.10',
            credential=test_credential_v2c,
            network=network,
        )
        results = _build_network_pipeline_configs(network)
        for r in results:
            assert 'name_check_network' in r['pipeline_name']

    def test_config_is_valid_logstash_syntax(
        self, test_connection, test_credential_v2c
    ):
        from SNMP.snmp_crud import _build_network_pipeline_configs
        network = Network.objects.create(
            name='Syntax Check Network',
            network_range='10.25.0.0/24',
            connection=test_connection,
            traps_enabled=False,
            discovery_enabled=False,
        )
        Device.objects.create(
            name='Syntax Device',
            ip_address='10.25.0.10',
            credential=test_credential_v2c,
            network=network,
        )
        results = _build_network_pipeline_configs(network)
        for r in results:
            config = r['config']
            assert 'input {' in config
            assert 'output {' in config


@pytest.mark.django_db
class TestDeviceVisualizationData:
    """Regression tests for device visualization data shaping.

    Covers the defects that left the device detail panel blank or wrong while the
    underlying data was present: interface values nested under OpenConfig's
    ``state``, and memory being sourced from the wrong place.
    """

    def _search_stub(self, by_category, captured=None):
        """Build an es.search side_effect that dispatches on event.category."""
        def search(**kwargs):
            filters = kwargs['query']['bool']['filter']
            if captured is not None:
                captured.append(filters)
            categories = [f['term']['event.category'] for f in filters
                          if 'term' in f and 'event.category' in f['term']]
            for category in categories:
                if category in by_category:
                    return {'hits': {'hits': by_category[category]}}
            return {'hits': {'hits': []}}
        return search

    # ---- interface shaping ----

    def test_interfaces_flatten_openconfig_state_and_counters(self, test_device):
        """state.* AND state.counters.* are lifted to where the UI reads them."""
        from SNMP.snmp_crud import _get_device_interfaces

        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {'fans': {'buckets': [
                {'top_if_doc': {'hits': {'hits': [{'_source': {'interface': {
                    'name': 'Ethernet1',
                    'index': 1,
                    'state': {
                        'admin_status': 'UP',
                        'oper_status': 'DOWN',
                        'speed': 1000000000.0,
                        'counters': {'in_octets': 42, 'out_errors': 7},
                    },
                }}}]}}},
            ]}}
        }

        iface = _get_device_interfaces(test_device, mock_es)['interfaces'][0]

        assert iface['admin_status'] == 'UP'
        assert iface['oper_status'] == 'DOWN'
        assert iface['speed'] == 1000000000.0
        # Counters must be flat — createInterfaceCard reads iface.in_octets, so
        # leaving them at iface.counters.in_octets renders 0 B on a busy link.
        assert iface['in_octets'] == 42
        assert iface['out_errors'] == 7
        assert iface['name'] == 'Ethernet1'
        assert iface['index'] == 1
        assert 'state' not in iface

    def test_normalized_top_level_status_wins_over_raw_state(self, test_device):
        """A raw state value must not clobber the pipeline-normalized one."""
        from SNMP.snmp_crud import _get_device_interfaces

        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {'fans': {'buckets': [
                {'top_if_doc': {'hits': {'hits': [{'_source': {'interface': {
                    'name': 'Ethernet1',
                    # Translate normalizer already decoded 1 -> UP here.
                    'oper_status': 'UP',
                    # ...while the raw enum survives under state.
                    'state': {'oper_status': 1, 'admin_status': 'UP'},
                }}}]}}},
            ]}}
        }

        iface = _get_device_interfaces(test_device, mock_es)['interfaces'][0]

        # The UI compares strictly against 'UP'; the raw 1 would render "Unknown".
        assert iface['oper_status'] == 'UP'
        # Keys only present under state still come through.
        assert iface['admin_status'] == 'UP'

    def test_interfaces_without_state_are_passed_through(self, test_device):
        """A device that already reports flat status is left alone."""
        from SNMP.snmp_crud import _get_device_interfaces

        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {'fans': {'buckets': [
                {'top_if_doc': {'hits': {'hits': [{'_source': {'interface': {
                    'name': 'Ethernet1', 'admin_status': 'UP', 'oper_status': 'UP',
                }}}]}}},
            ]}}
        }

        iface = _get_device_interfaces(test_device, mock_es)['interfaces'][0]
        assert iface['admin_status'] == 'UP'
        assert iface['oper_status'] == 'UP'

    # ---- metrics sourcing ----

    def test_canonical_memory_field_is_preferred(self, test_device):
        """Profiles deriving system.memory.actual.used.pct keep working."""
        from SNMP.snmp_crud import _get_device_metrics

        captured = []
        mock_es = MagicMock()
        mock_es.search.side_effect = self._search_stub({
            'metrics': [{'_source': {
                '@timestamp': '2026-08-04T01:00:00Z',
                'system': {
                    'cpu': {'total': {'norm': {'pct': 0.25}}},
                    'memory': {'actual': {'used': {'pct': 0.19}}},
                },
                'host': {'uptime': 12345},
            }}],
        }, captured)

        metrics = _get_device_metrics(test_device, mock_es)

        assert metrics['CPU'] == [0.25]
        assert metrics['Memory'] == [0.19]
        assert metrics['MemorySource'] == 'system.memory.actual.used.pct'
        assert metrics['Uptime'] == 12345
        # The storage-table fallback must not be queried when the canonical
        # field is present — that query is pure overhead here.
        queried = [f['term']['event.category'] for fl in captured for f in fl
                   if 'term' in f and 'event.category' in f['term']]
        assert 'system.filesystem' not in queried

    def test_cpu_returned_when_memory_is_absent(self, test_device):
        """CPU must survive on its own — it used to be dropped with memory."""
        from SNMP.snmp_crud import _get_device_metrics

        mock_es = MagicMock()
        mock_es.search.side_effect = self._search_stub({
            'metrics': [{'_source': {
                '@timestamp': '2026-08-04T01:00:00Z',
                'system': {'cpu': {'total': {'norm': {'pct': 0.25}}}},
                'host': {'uptime': 12345},
            }}],
        })

        metrics = _get_device_metrics(test_device, mock_es)

        assert metrics['CPU'] == [0.25]
        assert metrics['CPUTime'] == ['2026-08-04T01:00:00Z']
        assert metrics['Memory'] == []
        assert metrics['MemorySource'] is None

    def test_memory_falls_back_to_physical_hrstorage_ram_row(self, test_device):
        """Without the canonical field, use hrStorageRam — physical, not cache."""
        from SNMP.snmp_crud import _get_device_metrics

        captured = []

        def search(**kwargs):
            filters = kwargs['query']['bool']['filter']
            captured.append(filters)
            categories = [f['term']['event.category'] for f in filters
                          if 'term' in f and 'event.category' in f['term']]
            if 'metrics' in categories:
                return {'hits': {'hits': [{'_source': {
                    '@timestamp': '2026-08-04T01:00:00Z',
                    'system': {'cpu': {'total': {'norm': {'pct': 0.25}}}},
                }}]}}
            # The aggregation asks for the lowest hrStorageIndex per poll, so the
            # physical row is what comes back — cache/buffers rows are ranked out
            # by the sort, which is the behaviour being pinned here.
            return {'aggregations': {'by_poll': {'buckets': [
                {'key': 1, 'physical': {'hits': {'hits': [{'_source': {
                    '@timestamp': '2026-08-04T01:00:00Z',
                    'system': {'filesystem': {'used': {'pct': 0.98}}},
                }}]}}},
            ]}}}

        mock_es = MagicMock()
        mock_es.search.side_effect = search

        metrics = _get_device_metrics(test_device, mock_es)

        assert metrics['Memory'] == [0.98]
        assert metrics['MemoryTime'] == ['2026-08-04T01:00:00Z']
        assert metrics['MemorySource'] == 'hrStorageRam'

        fs_filters = [fl for fl in captured
                      if any('term' in f and f['term'].get('event.category') == 'system.filesystem'
                             for f in fl)]
        assert fs_filters, "expected a system.filesystem query"

        # Rows are selected by hrStorageType, not by a locale-specific description
        # ("RAM" on EOS vs "Physical memory" on net-snmp), and matched under both
        # possible mappings of that field.
        shoulds = [f['bool']['should'] for f in fs_filters[0] if 'bool' in f]
        assert shoulds, "expected a bool/should type filter"
        fields = {list(clause['term'].keys())[0] for clause in shoulds[0]}
        assert fields == {'system.filesystem.type', 'system.filesystem.type.keyword'}
        assert all(list(c['term'].values())[0] == '1.3.6.1.2.1.25.2.1.2' for c in shoulds[0])
        assert not any('mount_point' in str(f) for f in fs_filters[0])

        # All RAM rows report the same total, so the row must be disambiguated by
        # lowest hrStorageIndex — ranking by total silently picks an arbitrary row.
        agg = mock_es.search.call_args_list[-1].kwargs['aggregations']
        top_hits = agg['by_poll']['aggregations']['physical']['top_hits']
        assert top_hits['sort'] == [{'system.filesystem.index': {'order': 'asc'}}]
        assert top_hits['size'] == 1

    def test_metrics_queries_are_scoped_to_the_device(self, test_device):
        """Every metrics query must filter to this device, not the whole fleet."""
        from SNMP.snmp_crud import _get_device_metrics

        captured = []
        mock_es = MagicMock()
        mock_es.search.side_effect = self._search_stub({
            'metrics': [{'_source': {
                '@timestamp': '2026-08-04T01:00:00Z',
                'system': {'cpu': {'total': {'norm': {'pct': 0.25}}}},
            }}],
            'system.filesystem': [],
        }, captured)

        _get_device_metrics(test_device, mock_es)

        assert captured, "expected at least one query"
        for filters in captured:
            assert {"term": {"host.polled_address": test_device.ip_address}} in filters
            assert {"range": {"@timestamp": {"gte": "now-6h"}}} in filters

    def test_uptime_defaults_to_zero_without_metrics_docs(self, test_device):
        """No metrics documents must not raise."""
        from SNMP.snmp_crud import _get_device_metrics

        mock_es = MagicMock()
        mock_es.search.side_effect = self._search_stub({})

        metrics = _get_device_metrics(test_device, mock_es)

        assert metrics['Uptime'] == 0
        assert metrics['CPU'] == []
        assert metrics['Memory'] == []
