#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from django.contrib.auth.models import User
from django.test import Client
from unittest.mock import patch, MagicMock, Mock
import json

from SNMP.models import Network, Device, Credential, Profile
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
        logstash_name='test-logstash',
        connection=test_connection,
        discovery_credential=test_credential_v2c,
        discovery_enabled=True,
        traps_enabled=False,
        interval=30
    )


@pytest.fixture
def test_device(db, test_network, test_credential_v2c):
    """Create a test SNMP device"""
    device = Device.objects.create(
        name='Test Device',
        ip_address='192.168.1.100',
        port=161,
        retries=2,
        timeout=1000,
        credential=test_credential_v2c,
        network=test_network
    )
    # Add system profile
    system_profile, _ = Profile.objects.get_or_create(
        name='system.json',
        defaults={
            'profile_data': {'is_official_placeholder': True},
            'description': 'Official profile'
        }
    )
    device.profiles.add(system_profile)
    return device


@pytest.fixture
def test_profile(db):
    """Create a test user profile"""
    return Profile.objects.create(
        name='custom_profile',
        description='Custom test profile',
        type='Network',
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
            'logstash_name': 'test',
            'connection': test_connection.id,
            'discovery_credential': test_credential_v2c.id
        })
        assert response.status_code == 403

    def test_add_network_success(self, authenticated_client, test_connection, test_credential_v2c):
        """Test successfully adding a network"""
        response = authenticated_client.post('/SNMP/AddNetwork/', {
            'name': 'New Network',
            'network_range': '10.0.0.0/24',
            'logstash_name': 'new-logstash',
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
            'logstash_name': 'test'
        })
        assert response.status_code == 400
        assert b'Invalid CIDR notation' in response.content

    def test_update_network_requires_admin(self, readonly_client, test_network):
        """Test that updating a network requires admin role"""
        response = readonly_client.post(f'/SNMP/UpdateNetwork/{test_network.id}/', {
            'name': 'Updated Network',
            'network_range': '192.168.1.0/24',
            'logstash_name': 'test'
        })
        assert response.status_code == 403

    def test_update_network_success(self, authenticated_client, test_network):
        """Test successfully updating a network"""
        response = authenticated_client.post(f'/SNMP/UpdateNetwork/{test_network.id}/', {
            'name': 'Updated Network',
            'network_range': '192.168.2.0/24',
            'logstash_name': 'updated-logstash',
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
        assert 'system' in data['profiles']

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
        assert device.profiles.filter(name='system.json').exists()

    def test_add_device_auto_adds_system_profile(self, authenticated_client, test_network, test_credential_v2c):
        """Test that system profile is automatically added to devices"""
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'Device Without Profiles',
            'ip_address': '192.168.1.102',
            'network': test_network.id,
            'credential': test_credential_v2c.id
        })
        assert response.status_code == 200
        
        # Verify system profile was added
        device = Device.objects.get(name='Device Without Profiles')
        assert device.profiles.filter(name='system.json').exists()

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
        # Should have both official and custom profiles
        assert any(p['name'] == 'system' for p in data['profiles'])
        assert any(p['name'] == 'custom_profile' for p in data['profiles'])

    def test_get_official_profile(self, authenticated_client):
        """Test getting an official profile"""
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
# Commit Configuration Tests
# ============================================================================

@pytest.mark.django_db
class TestCommitConfiguration:
    """Test configuration commit operations"""

    def test_get_commit_diff(self, authenticated_client, test_network, test_device):
        """Test getting commit diff"""
        with patch('SNMP.snmp_crud.get_elastic_connection') as mock_es_conn:
            mock_es = MagicMock()
            mock_es.logstash.get_pipeline.return_value = {}
            mock_es_conn.return_value = mock_es
            
            response = authenticated_client.get('/SNMP/GetCommitDiff/')
            assert response.status_code == 200
            data = json.loads(response.content)
            assert data['success'] is True
            assert 'networks' in data

    def test_commit_configuration_requires_admin(self, readonly_client):
        """Test that committing configuration requires admin role"""
        response = readonly_client.post('/SNMP/CommitConfiguration/')
        assert response.status_code == 403

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_commit_configuration_success(self, mock_es_conn, authenticated_client, test_network, test_device):
        """Test successfully committing configuration"""
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {}
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_es_conn.return_value = mock_es
        
        response = authenticated_client.post('/SNMP/CommitConfiguration/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_commit_configuration_no_networks(self, mock_es_conn, authenticated_client):
        """Test committing with no networks configured"""
        response = authenticated_client.post('/SNMP/CommitConfiguration/')
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
    def test_get_discovered_devices(self, mock_es_conn, authenticated_client, test_connection):
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
        # Valid CIDR
        response = authenticated_client.post('/SNMP/AddNetwork/', {
            'name': 'Valid CIDR',
            'network_range': '10.0.0.0/8',
            'logstash_name': 'test'
        })
        assert response.status_code == 200
        
        # Invalid CIDR
        response = authenticated_client.post('/SNMP/AddNetwork/', {
            'name': 'Invalid CIDR',
            'network_range': '999.999.999.999/99',
            'logstash_name': 'test'
        })
        assert response.status_code == 400

    def test_device_ip_validation(self, authenticated_client, test_network, test_credential_v2c):
        """Test IP address validation for devices"""
        # Valid IP
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'Valid IP Device',
            'ip_address': '192.168.1.1',
            'network': test_network.id,
            'credential': test_credential_v2c.id
        })
        assert response.status_code == 200
        
        # Valid hostname
        response = authenticated_client.post('/SNMP/AddDevice/', {
            'name': 'Hostname Device',
            'ip_address': 'router.example.com',
            'network': test_network.id,
            'credential': test_credential_v2c.id
        })
        assert response.status_code == 200

    def test_profile_json_validation(self, authenticated_client):
        """Test that profile_data must be valid JSON object"""
        # Valid JSON object
        response = authenticated_client.post('/SNMP/AddProfile/',
            json.dumps({
                'name': 'valid_json_profile',
                'profile_data': {'get': {}, 'walk': {}}
            }),
            content_type='application/json'
        )
        assert response.status_code == 200

    @patch('SNMP.snmp_crud.get_elastic_connection')
    def test_commit_handles_elasticsearch_errors(self, mock_es_conn, authenticated_client, test_network, test_device):
        """Test that commit handles Elasticsearch errors gracefully"""
        mock_es_conn.side_effect = Exception("Connection failed")
        
        response = authenticated_client.post('/SNMP/CommitConfiguration/')
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
        # logstash_name is 'test-logstash' — hyphens preserved by sanitizer
        assert 'test-logstash' in name
        # network name is 'Test Network' — spaces become underscores via sanitizer
        assert 'test_network' in name

    def test_special_chars_sanitized(self, test_connection, test_credential_v2c):
        """Special chars in network/logstash names are sanitized"""
        from SNMP.snmp_crud import _get_pipeline_name
        network = Network.objects.create(
            name='My Network (prod)!',
            network_range='10.0.0.0/24',
            logstash_name='my logstash/cluster',
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
    """Tests for _get_device_profiles() helper"""

    def test_no_profiles_returns_empty(self, test_network, test_credential_v2c):
        from SNMP.snmp_crud import _get_device_profiles
        device = Device.objects.create(
            name='No Profiles Device', ip_address='10.0.0.1',
            credential=test_credential_v2c, network=test_network
        )
        profile_ids, merged = _get_device_profiles(device, {})
        assert profile_ids == tuple()
        assert merged == {'get': {}, 'walk': {}, 'table': {}}

    def test_custom_profile_oids_merged(self, test_network, test_credential_v2c):
        from SNMP.snmp_crud import _get_device_profiles
        profile = Profile.objects.create(
            name='custom_test',
            profile_data={
                'get': {'system.name': '1.3.6.1.2.1.1.5.0'},
                'walk': {},
                'table': {}
            }
        )
        device = Device.objects.create(
            name='Profile Device', ip_address='10.0.0.2',
            credential=test_credential_v2c, network=test_network
        )
        device.profiles.add(profile)

        profile_ids, merged = _get_device_profiles(device, {})
        assert len(profile_ids) == 1
        assert '1.3.6.1.2.1.1.5.0' in merged['get'].values()

    def test_official_placeholder_loaded_from_file(self, test_network, test_credential_v2c, tmp_path):
        from SNMP.snmp_crud import _get_device_profiles
        # Create a placeholder profile
        profile = Profile.objects.create(
            name='test_official.json',
            profile_data={'is_official_placeholder': True},
        )
        device = Device.objects.create(
            name='Official Device', ip_address='10.0.0.3',
            credential=test_credential_v2c, network=test_network
        )
        device.profiles.add(profile)

        # mock out the file loading — file exists with real data
        fake_data = {'get': {'system.desc': '1.3.6.1.2.1.1.1.0'}, 'walk': {}, 'table': {}}
        with patch('SNMP.snmp_crud.os.path.exists', return_value=True), \
             patch('builtins.open', create=True) as mock_open, \
             patch('SNMP.snmp_crud.json.load', return_value=fake_data):
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            profile_ids, merged = _get_device_profiles(device, {})

        assert '1.3.6.1.2.1.1.1.0' in merged['get'].values()

    def test_official_placeholder_file_missing_skipped(self, test_network, test_credential_v2c):
        from SNMP.snmp_crud import _get_device_profiles
        profile = Profile.objects.create(
            name='missing_official.json',
            profile_data={'is_official_placeholder': True},
        )
        device = Device.objects.create(
            name='Missing File Device', ip_address='10.0.0.4',
            credential=test_credential_v2c, network=test_network
        )
        device.profiles.add(profile)

        with patch('SNMP.snmp_crud.os.path.exists', return_value=False):
            profile_ids, merged = _get_device_profiles(device, {})

        # Nothing should be merged since file doesn't exist
        assert merged == {'get': {}, 'walk': {}, 'table': {}}

    def test_oid_conflict_gets_suffixed(self, test_network, test_credential_v2c):
        """When two profiles define the same OID key with different values, suffix is added"""
        from SNMP.snmp_crud import _get_device_profiles
        profile_a = Profile.objects.create(
            name='profile_a', profile_data={'get': {'metric': 'oid.1'}, 'walk': {}, 'table': {}}
        )
        profile_b = Profile.objects.create(
            name='profile_b', profile_data={'get': {'metric': 'oid.2'}, 'walk': {}, 'table': {}}
        )
        device = Device.objects.create(
            name='Conflict Device', ip_address='10.0.0.5',
            credential=test_credential_v2c, network=test_network
        )
        device.profiles.add(profile_a, profile_b)

        _, merged = _get_device_profiles(device, {})
        # Both OIDs should be present under different keys
        assert len(merged['get']) == 2


@pytest.mark.django_db
class TestFormatFieldName:
    """Tests for _format_field_name() pure function"""

    def test_already_bracket_notation_unchanged(self):
        from SNMP.snmp_crud import _format_field_name
        assert _format_field_name('[system][cpu]') == '[system][cpu]'

    def test_dotted_name_converted(self):
        from SNMP.snmp_crud import _format_field_name
        assert _format_field_name('system.cpu.load') == '[system][cpu][load]'

    def test_plain_name_unchanged(self):
        from SNMP.snmp_crud import _format_field_name
        assert _format_field_name('hostname') == 'hostname'

    def test_single_dot(self):
        from SNMP.snmp_crud import _format_field_name
        assert _format_field_name('a.b') == '[a][b]'


@pytest.mark.django_db
class TestGetDiscoveryIpAddresses:
    """Tests for _get_discovery_ip_addresses() helper"""

    def test_returns_all_hosts_in_range(self, test_network):
        from SNMP.snmp_crud import _get_discovery_ip_addresses
        # /30 has 2 usable hosts
        test_network.network_range = '192.168.100.0/30'
        test_network.save()
        ips = _get_discovery_ip_addresses(test_network)
        assert '192.168.100.1' in ips
        assert '192.168.100.2' in ips
        assert '192.168.100.0' not in ips   # network address
        assert '192.168.100.3' not in ips   # broadcast

    def test_excludes_existing_device_ips(self, test_network, test_credential_v2c):
        from SNMP.snmp_crud import _get_discovery_ip_addresses
        test_network.network_range = '10.0.0.0/30'
        test_network.save()
        Device.objects.create(
            name='Existing', ip_address='10.0.0.1',
            credential=test_credential_v2c, network=test_network
        )
        ips = _get_discovery_ip_addresses(test_network)
        assert '10.0.0.1' not in ips
        assert '10.0.0.2' in ips

    def test_device_with_hostname_not_excluded(self, test_network, test_credential_v2c):
        """Devices with hostnames (not IPs) don't cause IP to be excluded"""
        from SNMP.snmp_crud import _get_discovery_ip_addresses
        test_network.network_range = '10.0.1.0/30'
        test_network.save()
        Device.objects.create(
            name='Hostname Device', ip_address='router.example.com',
            credential=test_credential_v2c, network=test_network
        )
        ips = _get_discovery_ip_addresses(test_network)
        # All IPs in range should still be present
        assert '10.0.1.1' in ips

    def test_invalid_cidr_returns_empty(self):
        """Invalid CIDR can't be saved to DB (model validates it), so use a Mock."""
        from SNMP.snmp_crud import _get_discovery_ip_addresses
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
            'name': 'Ghost', 'network_range': '10.0.0.0/24', 'logstash_name': 'test'
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
            'logstash_name': test_network.logstash_name,
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
            logstash_name='no-conn',
        )
        network_id = network.id
        response = authenticated_client.post(f'/SNMP/DeleteNetwork/{network_id}/')
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert not Network.objects.filter(id=network_id).exists()
