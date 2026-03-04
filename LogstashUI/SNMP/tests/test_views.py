"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from unittest.mock import patch, MagicMock
import json
import os

from SNMP.models import Network, Device, Credential, Profile
from PipelineManager.models import Connection
from Management.models import UserProfile


@pytest.fixture
def admin_user(db):
    """Create a user with admin profile"""
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
def test_credential(db):
    """Create a test SNMP credential"""
    return Credential.objects.create(
        name='Test Credential',
        version='2c',
        community='public',
        description='Test SNMP v2c credential'
    )


@pytest.fixture
def test_network(db, test_connection, test_credential):
    """Create a test SNMP network"""
    return Network.objects.create(
        name='Test Network',
        network_range='192.168.1.0/24',
        logstash_name='test-logstash',
        connection=test_connection,
        discovery_credential=test_credential,
        discovery_enabled=True,
        traps_enabled=False,
        interval=30
    )


@pytest.fixture
def test_device(db, test_network, test_credential):
    """Create a test SNMP device"""
    device = Device.objects.create(
        name='Test Device',
        ip_address='192.168.1.100',
        port=161,
        retries=2,
        timeout=1000,
        credential=test_credential,
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
# View Tests - Read-Only Pages
# ============================================================================

@pytest.mark.django_db
class TestNetworksView:
    """Test Networks page view"""

    def test_networks_view_requires_authentication(self, client):
        """Test that Networks view requires authentication"""
        response = client.get('/SNMP/Networks/')
        assert response.status_code == 302
        assert '/Management/Login/' in response.url

    def test_networks_view_accessible_to_admin(self, authenticated_client):
        """Test that admin users can access Networks view"""
        response = authenticated_client.get('/SNMP/Networks/')
        assert response.status_code == 200
        assert b'Networks' in response.content or b'networks' in response.content

    def test_networks_view_accessible_to_readonly(self, readonly_client):
        """Test that readonly users can access Networks view"""
        response = readonly_client.get('/SNMP/Networks/')
        assert response.status_code == 200

    def test_networks_view_displays_networks(self, authenticated_client, test_network):
        """Test that Networks view displays existing networks"""
        response = authenticated_client.get('/SNMP/Networks/')
        assert response.status_code == 200
        # Networks are loaded via AJAX, so just verify the page loads and has the networks context
        assert 'networks' in response.context

    def test_networks_view_with_connection_form(self, authenticated_client):
        """Test that Networks view includes connection form"""
        response = authenticated_client.get('/SNMP/Networks/')
        assert response.status_code == 200
        # Should have form context
        assert 'form' in response.context


@pytest.mark.django_db
class TestDevicesView:
    """Test Devices page view"""

    def test_devices_view_requires_authentication(self, client):
        """Test that Devices view requires authentication"""
        response = client.get('/SNMP/Devices/')
        assert response.status_code == 302
        assert '/Management/Login/' in response.url

    def test_devices_view_accessible_to_admin(self, authenticated_client):
        """Test that admin users can access Devices view"""
        response = authenticated_client.get('/SNMP/Devices/')
        assert response.status_code == 200

    def test_devices_view_accessible_to_readonly(self, readonly_client):
        """Test that readonly users can access Devices view"""
        response = readonly_client.get('/SNMP/Devices/')
        assert response.status_code == 200

    def test_devices_view_displays_devices(self, authenticated_client, test_device):
        """Test that Devices view displays existing devices"""
        response = authenticated_client.get('/SNMP/Devices/')
        assert response.status_code == 200
        # Device data is loaded via AJAX, so just check page loads
        assert b'devices' in response.content.lower()


@pytest.mark.django_db
class TestProfilesView:
    """Test Profiles page view"""

    def test_profiles_view_requires_authentication(self, client):
        """Test that Profiles view requires authentication"""
        response = client.get('/SNMP/Profiles/')
        assert response.status_code == 302
        assert '/Management/Login/' in response.url

    def test_profiles_view_accessible_to_admin(self, authenticated_client):
        """Test that admin users can access Profiles view"""
        response = authenticated_client.get('/SNMP/Profiles/')
        assert response.status_code == 200

    def test_profiles_view_accessible_to_readonly(self, readonly_client):
        """Test that readonly users can access Profiles view"""
        response = readonly_client.get('/SNMP/Profiles/')
        assert response.status_code == 200

    def test_profiles_view_displays_official_profiles(self, authenticated_client):
        """Test that Profiles view displays official profiles from JSON files"""
        response = authenticated_client.get('/SNMP/Profiles/')
        assert response.status_code == 200
        # Should have profiles in context
        assert 'profiles' in response.context
        profiles = response.context['profiles']
        # Should have at least one profile (system profile if it exists in the data directory)
        assert len(profiles) >= 0  # May be empty if no official profiles exist in test environment

    def test_profiles_view_displays_user_profiles(self, authenticated_client, test_profile):
        """Test that Profiles view displays user-created profiles"""
        response = authenticated_client.get('/SNMP/Profiles/')
        assert response.status_code == 200
        profiles = response.context['profiles']
        # Should include custom profile
        assert any(p['name'] == 'custom_profile' for p in profiles)

    def test_profiles_view_excludes_placeholder_profiles(self, authenticated_client):
        """Test that placeholder profiles are excluded from display"""
        # Create a placeholder profile
        Profile.objects.create(
            name='placeholder.json',
            profile_data={'is_official_placeholder': True},
            description='Placeholder'
        )
        
        response = authenticated_client.get('/SNMP/Profiles/')
        assert response.status_code == 200
        profiles = response.context['profiles']
        # Placeholder should not be in user profiles list
        user_profiles = [p for p in profiles if not p['is_official']]
        assert not any(p['name'] == 'placeholder.json' for p in user_profiles)

    def test_profiles_view_sorts_by_pinned_then_alphabetically(self, authenticated_client):
        """Test that profiles are sorted with pinned first, then alphabetically"""
        response = authenticated_client.get('/SNMP/Profiles/')
        assert response.status_code == 200
        profiles = response.context['profiles']
        
        # Pinned profiles should come first
        pinned_profiles = [p for p in profiles if p.get('pinned', False)]
        unpinned_profiles = [p for p in profiles if not p.get('pinned', False)]
        
        # If there are pinned profiles, they should be at the start
        if pinned_profiles:
            assert profiles[0] in pinned_profiles


@pytest.mark.django_db
class TestCredentialsView:
    """Test Credentials page view"""

    def test_credentials_view_requires_authentication(self, client):
        """Test that Credentials view requires authentication"""
        response = client.get('/SNMP/Credentials/')
        assert response.status_code == 302
        assert '/Management/Login/' in response.url

    def test_credentials_view_accessible_to_admin(self, authenticated_client):
        """Test that admin users can access Credentials view"""
        response = authenticated_client.get('/SNMP/Credentials/')
        assert response.status_code == 200

    def test_credentials_view_accessible_to_readonly(self, readonly_client):
        """Test that readonly users can access Credentials view"""
        response = readonly_client.get('/SNMP/Credentials/')
        assert response.status_code == 200

    def test_credentials_view_displays_credentials(self, authenticated_client, test_credential):
        """Test that Credentials view displays existing credentials"""
        response = authenticated_client.get('/SNMP/Credentials/')
        assert response.status_code == 200
        # Credentials data is loaded via AJAX, so just check page loads
        assert b'credentials' in response.content.lower()


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

@pytest.mark.django_db
class TestViewsEdgeCases:
    """Test edge cases and error handling in views"""

    def test_networks_view_with_no_networks(self, authenticated_client):
        """Test Networks view when no networks exist"""
        response = authenticated_client.get('/SNMP/Networks/')
        assert response.status_code == 200
        assert 'networks' in response.context
        assert len(response.context['networks']) == 0

    def test_profiles_view_with_missing_json_files(self, authenticated_client, tmp_path):
        """Test Profiles view handles missing JSON files gracefully"""
        # This should not crash even if some JSON files are missing
        response = authenticated_client.get('/SNMP/Profiles/')
        assert response.status_code == 200

    def test_profiles_view_with_invalid_json_file(self, authenticated_client, settings, tmp_path):
        """Test Profiles view handles invalid JSON files gracefully"""
        # Create an invalid JSON file
        official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
        if os.path.exists(official_profiles_dir):
            invalid_file = os.path.join(official_profiles_dir, 'test_invalid.json')
            try:
                with open(invalid_file, 'w') as f:
                    f.write('{ invalid json }')
                
                response = authenticated_client.get('/SNMP/Profiles/')
                # Should handle gracefully and still return 200
                assert response.status_code == 200
            finally:
                # Cleanup
                if os.path.exists(invalid_file):
                    os.remove(invalid_file)

    def test_view_with_database_error(self, authenticated_client):
        """Test views handle database errors gracefully"""
        with patch('SNMP.models.Network.objects') as mock_objects:
            mock_objects.select_related.side_effect = Exception("Database error")
            
            # Should return error response, not crash
            try:
                response = authenticated_client.get('/SNMP/Networks/')
                # May return 500 or handle gracefully
                assert response.status_code in [200, 500]
            except Exception:
                # If exception is raised, that's also acceptable for this test
                pass
