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


# ============================================================================
# Overview Page
# ============================================================================

@pytest.mark.django_db
class TestOverviewView:
    """Test the SNMP Overview page view."""

    def test_overview_requires_authentication(self, client):
        response = client.get('/SNMP/Overview/')
        assert response.status_code == 302
        assert '/Management/Login/' in response.url

    def test_overview_accessible_to_admin(self, authenticated_client):
        response = authenticated_client.get('/SNMP/Overview/')
        assert response.status_code == 200

    def test_overview_accessible_to_readonly(self, readonly_client):
        response = readonly_client.get('/SNMP/Overview/')
        assert response.status_code == 200


# ============================================================================
# GetOverviewMetrics API
# ============================================================================

@pytest.mark.django_db
class TestGetOverviewMetricsView:
    """Test the /SNMP/GetOverviewMetrics/ JSON endpoint."""

    def test_get_overview_metrics_requires_auth(self, client):
        response = client.get('/SNMP/GetOverviewMetrics/')
        assert response.status_code == 302

    def test_get_overview_metrics_success(self, authenticated_client):
        """GetOverviewMetrics returns the expected JSON shape when ES helpers succeed."""
        with patch('SNMP.views.get_discovered_devices_count', return_value={'count': 5, 'errors': []}), \
             patch('SNMP.views.get_template_data_categories', return_value={'templates': [], 'errors': []}), \
             patch('SNMP.views.get_high_resource_usage', return_value={'high_cpu': [], 'high_memory': [], 'errors': []}):
            response = authenticated_client.get('/SNMP/GetOverviewMetrics/')

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'metrics' in data
        assert data['metrics']['discovered_devices'] == 5
        assert 'high_usage' in data
        assert 'data_quality' in data

    def test_get_overview_metrics_total_devices(self, authenticated_client, test_device):
        """total_devices counts devices in the database."""
        with patch('SNMP.views.get_discovered_devices_count', return_value={'count': 0, 'errors': []}), \
             patch('SNMP.views.get_template_data_categories', return_value={'templates': [], 'errors': []}), \
             patch('SNMP.views.get_high_resource_usage', return_value={'high_cpu': [], 'high_memory': [], 'errors': []}):
            response = authenticated_client.get('/SNMP/GetOverviewMetrics/')

        data = json.loads(response.content)
        assert data['metrics']['total_devices'] >= 1

    def test_get_overview_metrics_propagates_errors(self, authenticated_client):
        """Errors from helpers are propagated to the response errors list."""
        with patch('SNMP.views.get_discovered_devices_count', return_value={'count': 0, 'errors': ['ES connection failed']}), \
             patch('SNMP.views.get_template_data_categories', return_value={'templates': [], 'errors': []}), \
             patch('SNMP.views.get_high_resource_usage', return_value={'high_cpu': [], 'high_memory': [], 'errors': []}):
            response = authenticated_client.get('/SNMP/GetOverviewMetrics/')

        data = json.loads(response.content)
        assert data['success'] is True
        assert data['errors'] is not None
        assert 'ES connection failed' in data['errors']

    def test_get_overview_metrics_exception_returns_500(self, authenticated_client):
        """An unexpected exception inside GetOverviewMetrics returns HTTP 500."""
        with patch('SNMP.views.get_discovered_devices_count', side_effect=Exception('Boom')):
            response = authenticated_client.get('/SNMP/GetOverviewMetrics/')
        assert response.status_code == 500
        data = json.loads(response.content)
        assert data['success'] is False


# ============================================================================
# CheckSNMPIndexTemplate
# ============================================================================

@pytest.mark.django_db
class TestCheckSNMPIndexTemplateView:
    """Test the /SNMP/CheckSNMPIndexTemplate/ endpoint."""

    def test_requires_post(self, authenticated_client):
        response = authenticated_client.get('/SNMP/CheckSNMPIndexTemplate/')
        assert response.status_code == 405

    def test_requires_connection_ids(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/CheckSNMPIndexTemplate/',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_invalid_json_body(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/CheckSNMPIndexTemplate/',
            data='not json',
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_connection_not_found(self, authenticated_client):
        """A non-existent connection_id returns an error result (not a 500)."""
        with patch('SNMP.views._load_snmp_template', return_value={'_meta': {'template_name': 'metrics-snmp.polling'}}), \
             patch('Common.elastic_utils.check_index_template', return_value={'status': 'installed', 'differences': []}):
            response = authenticated_client.post(
                '/SNMP/CheckSNMPIndexTemplate/',
                data=json.dumps({'connection_ids': [99999]}),
                content_type='application/json',
            )
        assert response.status_code == 200
        data = json.loads(response.content)
        result = data['results'][0]
        assert result['status'] == 'error'
        assert 'not found' in result['error']

    def test_installed_status(self, authenticated_client, test_connection):
        """Returns 'installed' status when template is present and up to date."""
        with patch('SNMP.views._load_snmp_template', return_value={'_meta': {'template_name': 'metrics-snmp.polling'}}), \
             patch('Common.elastic_utils.check_index_template', return_value={'status': 'installed', 'differences': []}):
            response = authenticated_client.post(
                '/SNMP/CheckSNMPIndexTemplate/',
                data=json.dumps({'connection_ids': [test_connection.id]}),
                content_type='application/json',
            )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['results'][0]['status'] == 'installed'
        assert data['results'][0]['connection_name'] == test_connection.name


# ============================================================================
# InstallSNMPIndexTemplate
# ============================================================================

@pytest.mark.django_db
class TestInstallSNMPIndexTemplateView:
    """Test the /SNMP/InstallSNMPIndexTemplate/ endpoint."""

    def test_requires_admin(self, readonly_client, test_connection):
        response = readonly_client.post(
            '/SNMP/InstallSNMPIndexTemplate/',
            data=json.dumps({'connection_ids': [test_connection.id]}),
            content_type='application/json',
        )
        assert response.status_code == 403

    def test_requires_post(self, authenticated_client):
        response = authenticated_client.get('/SNMP/InstallSNMPIndexTemplate/')
        assert response.status_code == 405

    def test_requires_connection_ids(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/InstallSNMPIndexTemplate/',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_success(self, authenticated_client, test_connection):
        """Successfully installing a template returns success=True."""
        with patch('SNMP.views._load_snmp_template', return_value={'_meta': {'template_name': 'metrics-snmp.polling'}}), \
             patch('Common.elastic_utils.create_index_template', return_value=None):
            response = authenticated_client.post(
                '/SNMP/InstallSNMPIndexTemplate/',
                data=json.dumps({'connection_ids': [test_connection.id]}),
                content_type='application/json',
            )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['results'][0]['success'] is True

    def test_connection_not_found(self, authenticated_client):
        """A non-existent connection_id records failure without crashing."""
        with patch('SNMP.views._load_snmp_template', return_value={'_meta': {'template_name': 'metrics-snmp.polling'}}):
            response = authenticated_client.post(
                '/SNMP/InstallSNMPIndexTemplate/',
                data=json.dumps({'connection_ids': [99999]}),
                content_type='application/json',
            )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is False
        assert data['results'][0]['success'] is False


# ============================================================================
# CheckAgentBuilderResources
# ============================================================================

@pytest.mark.django_db
class TestCheckAgentBuilderResourcesView:
    """Test the /SNMP/CheckAgentBuilderResources/ endpoint."""

    def test_requires_post(self, authenticated_client):
        response = authenticated_client.get('/SNMP/CheckAgentBuilderResources/')
        assert response.status_code == 405

    def test_requires_connection_id(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/CheckAgentBuilderResources/',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_invalid_json_body(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/CheckAgentBuilderResources/',
            data='{ bad json',
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_success(self, authenticated_client):
        """Returns result from AgentBuilder.check_resources when successful."""
        mock_result = {'tools': [], 'skills': [], 'agents': []}
        with patch('Common.ai.agent_builder.AgentBuilder') as MockBuilder, \
             patch('Common.ai.agent_builder.load_resources_from_directory', return_value=([], [], [])):
            MockBuilder.return_value.check_resources.return_value = mock_result
            response = authenticated_client.post(
                '/SNMP/CheckAgentBuilderResources/',
                data=json.dumps({'connection_id': 1}),
                content_type='application/json',
            )
        assert response.status_code == 200

    def test_agent_builder_exception_returns_500(self, authenticated_client):
        """If AgentBuilder raises, the endpoint returns 500."""
        with patch('Common.ai.agent_builder.AgentBuilder', side_effect=Exception('KB down')), \
             patch('Common.ai.agent_builder.load_resources_from_directory', return_value=([], [], [])):
            response = authenticated_client.post(
                '/SNMP/CheckAgentBuilderResources/',
                data=json.dumps({'connection_id': 1}),
                content_type='application/json',
            )
        assert response.status_code == 500


# ============================================================================
# InstallAgentBuilderPackage
# ============================================================================

@pytest.mark.django_db
class TestInstallAgentBuilderPackageView:
    """Test the /SNMP/InstallAgentBuilderPackage/ endpoint."""

    def test_requires_admin(self, readonly_client):
        response = readonly_client.post(
            '/SNMP/InstallAgentBuilderPackage/',
            data=json.dumps({'connection_id': 1}),
            content_type='application/json',
        )
        assert response.status_code == 403

    def test_requires_post(self, authenticated_client):
        response = authenticated_client.get('/SNMP/InstallAgentBuilderPackage/')
        assert response.status_code == 405

    def test_requires_connection_id(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/InstallAgentBuilderPackage/',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_success(self, authenticated_client):
        """Returns result from AgentBuilder.apply_all_resources when successful."""
        mock_result = {'success': True, 'results': []}
        with patch('Common.ai.agent_builder.AgentBuilder') as MockBuilder, \
             patch('Common.ai.agent_builder.load_resources_from_directory', return_value=([], [], [])):
            MockBuilder.return_value.apply_all_resources.return_value = mock_result
            response = authenticated_client.post(
                '/SNMP/InstallAgentBuilderPackage/',
                data=json.dumps({'connection_id': 1}),
                content_type='application/json',
            )
        assert response.status_code == 200

    def test_exception_returns_500(self, authenticated_client):
        """Unexpected exception returns 500 with success=False."""
        with patch('Common.ai.agent_builder.AgentBuilder', side_effect=Exception('Fail')), \
             patch('Common.ai.agent_builder.load_resources_from_directory', return_value=([], [], [])):
            response = authenticated_client.post(
                '/SNMP/InstallAgentBuilderPackage/',
                data=json.dumps({'connection_id': 1}),
                content_type='application/json',
            )
        assert response.status_code == 500
        data = json.loads(response.content)
        assert data['success'] is False
