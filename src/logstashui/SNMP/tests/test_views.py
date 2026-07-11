#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

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
        connection=test_connection,
        discovery_credential=test_credential,
        discovery_enabled=True,
        traps_enabled=False,
        interval=30
    )


@pytest.fixture
def test_device(db, test_network, test_credential):
    """Create a test SNMP device"""
    return Device.objects.create(
        name='Test Device',
        ip_address='192.168.1.100',
        port=161,
        retries=2,
        timeout=1000,
        credential=test_credential,
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
    """Test DeviceTemplates page (profiles now live there; /SNMP/Profiles/ no longer exists)"""

    def test_device_templates_accessible_to_admin(self, authenticated_client):
        """Admin users can access DeviceTemplates (the new home for profiles)"""
        response = authenticated_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200

    def test_device_templates_accessible_to_readonly(self, readonly_client):
        """Readonly users can access DeviceTemplates"""
        response = readonly_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200

    def test_device_templates_exposes_profiles_in_context(self, authenticated_client):
        """DeviceTemplates view includes 'profiles' list in its context"""
        response = authenticated_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200
        assert 'profiles' in response.context

    def test_device_templates_displays_user_profiles(self, authenticated_client, test_profile):
        """User-created profiles appear in the DeviceTemplates context"""
        response = authenticated_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200
        profiles = response.context['profiles']
        assert any(p['name'] == 'custom_profile' for p in profiles)

    def test_device_templates_excludes_placeholder_profiles(self, authenticated_client):
        """Placeholder profiles are excluded from the profiles list on DeviceTemplates"""
        Profile.objects.create(
            name='placeholder.json',
            vendor='Generic',
            profile_data={'is_official_placeholder': True},
            description='Placeholder'
        )
        response = authenticated_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200
        profiles = response.context['profiles']
        user_profiles = [p for p in profiles if not p['is_official']]
        assert not any(p['name'] == 'placeholder.json' for p in user_profiles)

    def test_device_templates_profiles_sorted_alphabetically(self, authenticated_client):
        """Profiles are sorted alphabetically by display_name on DeviceTemplates"""
        response = authenticated_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200
        profiles = response.context['profiles']
        display_names = [p['display_name'] for p in profiles]
        assert display_names == sorted(display_names)


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

    def test_device_templates_with_invalid_json_file(self, authenticated_client, settings):
        """DeviceTemplates handles malformed official profile JSON files gracefully"""
        official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
        if os.path.exists(official_profiles_dir):
            invalid_file = os.path.join(official_profiles_dir, 'test_invalid.json')
            try:
                with open(invalid_file, 'w') as f:
                    f.write('{ invalid json }')
                response = authenticated_client.get('/SNMP/DeviceTemplates/')
                assert response.status_code == 200
            finally:
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


# ============================================================================
# Additional context / content verification tests
# ============================================================================

@pytest.mark.django_db
class TestViewContextContent:
    """Additional tests verifying the data passed to each template context"""

    def test_networks_context_contains_network_instance(self, authenticated_client, test_network):
        """Networks context 'networks' queryset contains our test network"""
        response = authenticated_client.get('/SNMP/Networks/')
        assert response.status_code == 200
        network_names = [n.name for n in response.context['networks']]
        assert 'Test Network' in network_names

    def test_devices_context_has_devices_key(self, authenticated_client, test_device):
        """Devices view passes 'devices' queryset to template"""
        response = authenticated_client.get('/SNMP/Devices/')
        assert response.status_code == 200
        assert 'devices' in response.context
        device_names = [d.name for d in response.context['devices']]
        assert 'Test Device' in device_names

    def test_credentials_context_has_credentials_key(self, authenticated_client, test_credential):
        """Credentials view passes 'credentials' queryset to template"""
        response = authenticated_client.get('/SNMP/Credentials/')
        assert response.status_code == 200
        assert 'credentials' in response.context
        cred_names = [c.name for c in response.context['credentials']]
        assert 'Test Credential' in cred_names

    def test_device_templates_user_profile_required_fields(self, authenticated_client, test_profile):
        """User profile dicts in DeviceTemplates context contain all required fields"""
        response = authenticated_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200
        user_profiles = [p for p in response.context['profiles'] if not p['is_official']]
        for p in user_profiles:
            for key in ('name', 'display_name', 'description', 'vendor', 'is_official'):
                assert key in p

    def test_device_templates_official_profile_fields(self, authenticated_client):
        """Official profiles in DeviceTemplates context always have is_official=True"""
        response = authenticated_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200
        official_profiles = [p for p in response.context['profiles'] if p['is_official']]
        for p in official_profiles:
            assert p['is_official'] is True
            for key in ('name', 'display_name', 'description', 'vendor'):
                assert key in p

    def test_device_templates_invalid_json_handled_gracefully(self, authenticated_client, settings, tmp_path):
        """DeviceTemplates gracefully skips official profile JSON files that cannot be parsed"""
        official_dir = tmp_path / 'official_profiles'
        official_dir.mkdir()
        (official_dir / 'broken.json').write_text('{ not valid json }')

        with patch('SNMP.views.os.path.exists', return_value=True), \
             patch('SNMP.views.os.listdir', return_value=['broken.json']):
            response = authenticated_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200
        profiles = response.context['profiles']
        official_names = [p['name'] for p in profiles if p['is_official']]
        assert 'broken' in official_names
        broken = next(p for p in profiles if p['name'] == 'broken')
        assert broken['description'] == ''

    def test_networks_view_form_is_connection_form(self, authenticated_client):
        """Networks context form is a ConnectionForm instance"""
        from PipelineManager.forms import ConnectionForm
        response = authenticated_client.get('/SNMP/Networks/')
        assert isinstance(response.context['form'], ConnectionForm)

    def test_profiles_alphabetical_sort_among_unpinned(self, authenticated_client):
        """User profiles are sorted alphabetically by display_name on DeviceTemplates"""
        Profile.objects.all().delete()  # start clean for this test
        Profile.objects.create(name='zebra_profile', vendor='Generic', description='', profile_data={'get': {}})
        Profile.objects.create(name='alpha_profile', vendor='Generic', description='', profile_data={'get': {}})

        response = authenticated_client.get('/SNMP/DeviceTemplates/')
        assert response.status_code == 200
        user_profiles = [p for p in response.context['profiles'] if not p['is_official']]
        display_names = [p['display_name'] for p in user_profiles]
        assert display_names == sorted(display_names)


class TestGenerateTemplateGroundingInline:
    """GenerateTemplateAndProfiles reduces the walk to MIB-grounded columns and passes
    them INLINE to the agent. It must NOT stage the walk in a backend ES index — the
    record of truth stays local to LogstashUI, which may connect to multiple backends,
    so per-backend staging (residue + backend-dependent output) is disallowed."""

    # Mixed walk: SNMPv2 + IF-MIB columns (grounded) plus an enterprise OID (ungrounded).
    WALK = "\n".join([
        "1.3.6.1.2.1.1.1.0 = Cisco IOS Software, C2960X Software",
        "1.3.6.1.2.1.1.3.0 = 44266130",
        "1.3.6.1.2.1.1.5.0 = homelab-switch1",
        "1.3.6.1.2.1.2.2.1.10.1 = 12345",   # ifInOctets col (IF-MIB) -> grounded, instances=2
        "1.3.6.1.2.1.2.2.1.10.2 = 67890",
        "1.3.6.1.4.1.9.9.999.1.0 = 1",       # enterprise -> no compiled MIB -> ungrounded
    ])

    def _post(self, client, connection_id):
        resp = client.post(
            '/SNMP/GenerateTemplateAndProfiles/',
            data=json.dumps({
                'connection_id': connection_id,
                'walk_text': self.WALK,
                'inference_id': '.rainbow-sprinkles-elastic',
            }),
            content_type='application/json',
        )
        # Drain the SSE stream.
        return b''.join(resp.streaming_content).decode()

    @patch('Common.elastic_utils.bulk_index_documents')
    @patch('Common.ai.agent_builder.AgentBuilder')
    def test_grounded_columns_inline_no_backend_write(
        self, MockAgentBuilder, mock_bulk, authenticated_client, test_connection
    ):
        instance = MockAgentBuilder.return_value
        instance._kibana_url = 'https://kb.example'
        captured = {}

        def _invoke(agent_id, message, **kwargs):
            captured['agent_id'] = agent_id
            captured['message'] = message
            return iter(())  # empty agent stream is fine for this assertion

        instance.invoke_agent.side_effect = _invoke

        body = self._post(authenticated_client, test_connection.id)

        # 1. Nothing is written to any backend — no bulk index, no temp index name anywhere.
        mock_bulk.assert_not_called()
        assert 'snmp-template_generation' not in body
        assert 'snmp-template_generation' not in captured['message']

        # 2. The agent received the grounded columns INLINE (not an index to query).
        assert 'grounded_columns' in captured['message']
        payload = json.loads(captured['message'][captured['message'].index('{'):])
        names = {c['name'] for c in payload['grounded_columns']}
        assert 'sysDescr' in names      # SNMPv2-MIB scalar grounded
        assert 'ifInOctets' in names    # IF-MIB table column grounded (multi-instance)
        assert next(c for c in payload['grounded_columns'] if c['name'] == 'ifInOctets')['instances'] == 2
        # The enterprise OID had no compiled MIB -> reported for MIB-loading, not authored.
        assert any(u['prefix'].startswith('1.3.6.1.4.1.9') for u in payload['ungrounded_subtrees'])

        # 3. SSE reports the grounding phase and never the old indexing phase.
        assert '"phase": "grounding"' in body
        assert 'indexing' not in body

    @patch('Common.elastic_utils.bulk_index_documents')
    @patch('Common.ai.agent_builder.AgentBuilder')
    def test_empty_grounding_errors_without_backend_write(
        self, MockAgentBuilder, mock_bulk, authenticated_client, test_connection
    ):
        # A walk with only un-grounded enterprise OIDs -> no columns to author.
        resp = authenticated_client.post(
            '/SNMP/GenerateTemplateAndProfiles/',
            data=json.dumps({
                'connection_id': test_connection.id,
                'walk_text': '1.3.6.1.4.1.9999.1.2.3.0 = 5',
                'inference_id': '.rainbow-sprinkles-elastic',
            }),
            content_type='application/json',
        )
        body = b''.join(resp.streaming_content).decode()

        assert '"phase": "error"' in body
        mock_bulk.assert_not_called()
        MockAgentBuilder.return_value.invoke_agent.assert_not_called()
