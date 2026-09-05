#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Tests for SNMP.snmp_test — format helpers, auth data creation, and the
RunSNMPTest / RunSNMPWalk view endpoints (SNMP network I/O mocked).
"""

import json
import socket
import pytest
from unittest.mock import patch, MagicMock
from django.test import Client
from django.contrib.auth.models import User

from SNMP.snmp_test import (
    _create_auth_data,
    _device_poll_address,
    _device_response_data,
    _format_snmp_value,
    _load_profile_data,
    _merge_profile_oids,
    _resolve_device_poll_address,
)
from SNMP.models import Device, DeviceTemplate, Profile, Credential, Network
from PipelineManager.models import Connection
from Management.models import UserProfile


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        username='snmp_test_admin',
        password='testpass123',
        email='snmp_test_admin@example.com'
    )
    profile, created = UserProfile.objects.get_or_create(user=user, defaults={'role': 'admin'})
    if not created:
        profile.role = 'admin'
        profile.save()
    return user


@pytest.fixture
def authenticated_client(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client


@pytest.fixture
def test_connection(db):
    return Connection.objects.create(
        name='SNMP Test Connection',
        connection_type='CENTRALIZED',
        host='https://localhost:9200',
        username='elastic',
        password='changeme'
    )


@pytest.fixture
def test_credential_v2c(db):
    return Credential.objects.create(
        name='snmp_test_cred_v2c',
        version='2c',
        community='public',
        description='Test v2c credential for snmp_test tests'
    )


@pytest.fixture
def test_credential_v3_auth_priv(db):
    return Credential.objects.create(
        name='snmp_test_cred_v3',
        version='3',
        security_name='testuser',
        security_level='authPriv',
        auth_protocol='sha',
        auth_pass='authpass123',
        priv_protocol='aes',
        priv_pass='privpass123',
    )


@pytest.fixture
def test_credential_v3_auth_no_priv(db):
    return Credential.objects.create(
        name='snmp_test_cred_v3_anp',
        version='3',
        security_name='testuser2',
        security_level='authNoPriv',
        auth_protocol='md5',
        auth_pass='authpass123',
    )


@pytest.fixture
def test_credential_v3_no_auth(db):
    return Credential.objects.create(
        name='snmp_test_cred_v3_noanp',
        version='3',
        security_name='testuser3',
        security_level='noAuthNoPriv',
    )


@pytest.fixture
def test_network(db, test_connection, test_credential_v2c):
    return Network.objects.create(
        name='SNMP Test Network',
        network_range='10.0.0.0/24',
        connection=test_connection,
        discovery_credential=test_credential_v2c,
        interval=30
    )


@pytest.fixture
def test_custom_profile(db):
    return Profile.objects.create(
        name='snmp_test_custom_profile',
        description='Custom profile for snmp_test tests',
        vendor='Generic',
        profile_data={
            'get': {'sysDescr': '1.3.6.1.2.1.1.1.0'},
            'walk': {},
            'table': {}
        }
    )


@pytest.fixture
def test_device_template(db, test_custom_profile):
    template = DeviceTemplate.objects.create(
        name='snmp_test_template',
        description='Test template',
        vendor='Generic',
    )
    template.profiles.add(test_custom_profile)
    return template


@pytest.fixture
def test_device(db, test_network, test_credential_v2c, test_device_template):
    return Device.objects.create(
        name='snmp_test_device',
        ip_address='10.0.0.1',
        port=161,
        retries=1,
        timeout=500,
        credential=test_credential_v2c,
        network=test_network,
        device_template=test_device_template,
    )


# ===========================================================================
# _format_snmp_value — pure function
# ===========================================================================

class TestFormatSnmpValue:

    def test_printable_string_returned_as_is(self):
        assert _format_snmp_value('Hello World') == 'Hello World'

    def test_empty_string_returned_as_is(self):
        assert _format_snmp_value('') == ''

    def test_numeric_string_returned_as_is(self):
        assert _format_snmp_value('12345') == '12345'

    def test_mostly_printable_string_returned_as_is(self):
        # All printable ASCII
        value = 'Linux router 2.6.32'
        assert _format_snmp_value(value) == value

    def test_six_byte_binary_value_formatted_as_mac(self):
        # Simulate a 6-character string with non-printable bytes → MAC-like hex
        binary = '\x00\x11\x22\x33\x44\x55'
        result = _format_snmp_value(binary)
        # Should be hex-formatted
        assert ':' in result

    def test_four_byte_binary_value_formatted_as_hex(self):
        binary = '\xc0\xa8\x01\x01'  # 192.168.1.1 as binary
        result = _format_snmp_value(binary)
        assert ':' in result


# ===========================================================================
# _load_profile_data
# ===========================================================================

class TestLoadProfileData:

    def test_returns_profile_data_for_custom_profile(self, test_custom_profile):
        data = _load_profile_data(test_custom_profile)
        assert data == test_custom_profile.profile_data

    def test_official_placeholder_loads_from_file(self, settings, tmp_path):
        import os, json as jsonlib
        # Point BASE_DIR at tmp_path and create the official profile file
        settings.BASE_DIR = str(tmp_path)
        profile_dir = tmp_path / 'SNMP' / 'data' / 'official_profiles'
        profile_dir.mkdir(parents=True)

        profile_content = {
            'get': {'sysDescr': '1.3.6.1.2.1.1.1.0'},
            'walk': {},
            'table': {}
        }
        profile_file = profile_dir / 'test_official.json'
        profile_file.write_text(jsonlib.dumps(profile_content))

        official_profile = Profile(
            name='test_official.json',
            profile_data={'is_official_placeholder': True},
            vendor='Generic'
        )
        data = _load_profile_data(official_profile)
        assert data['get']['sysDescr'] == '1.3.6.1.2.1.1.1.0'

    def test_official_placeholder_missing_file_returns_empty(self, settings, tmp_path):
        settings.BASE_DIR = str(tmp_path)
        (tmp_path / 'SNMP' / 'data' / 'official_profiles').mkdir(parents=True)

        official_profile = Profile(
            name='nonexistent.json',
            profile_data={'is_official_placeholder': True},
            vendor='Generic'
        )
        data = _load_profile_data(official_profile)
        assert data == {'get': {}, 'walk': {}, 'table': {}}


# ===========================================================================
# _merge_profile_oids
# ===========================================================================

class TestMergeProfileOids:

    def test_empty_profiles_returns_empty_structure(self):
        result = _merge_profile_oids([])
        assert result == {'get': {}, 'walk': {}, 'table': {}}

    def test_single_profile_merged_correctly(self, test_custom_profile):
        result = _merge_profile_oids([test_custom_profile])
        assert 'sysDescr' in result['get']

    def test_multiple_profiles_oids_merged(self, db):
        p1 = Profile.objects.create(
            name='merge_test_p1',
            vendor='Generic',
            profile_data={'get': {'oid_a': '1.3.6.1.2.1.1.1.0'}, 'walk': {}, 'table': {}}
        )
        p2 = Profile.objects.create(
            name='merge_test_p2',
            vendor='Generic',
            profile_data={'get': {'oid_b': '1.3.6.1.2.1.1.2.0'}, 'walk': {}, 'table': {}}
        )
        result = _merge_profile_oids([p1, p2])
        assert 'oid_a' in result['get']
        assert 'oid_b' in result['get']

    def test_later_profile_overwrites_duplicate_oid_key(self, db):
        p1 = Profile.objects.create(
            name='merge_test_dup1',
            vendor='Generic',
            profile_data={'get': {'oid_x': '1.3.6.1.2.1.1.1.0'}, 'walk': {}, 'table': {}}
        )
        p2 = Profile.objects.create(
            name='merge_test_dup2',
            vendor='Generic',
            profile_data={'get': {'oid_x': '1.3.6.1.2.1.1.2.0'}, 'walk': {}, 'table': {}}
        )
        result = _merge_profile_oids([p1, p2])
        # p2's value wins
        assert result['get']['oid_x'] == '1.3.6.1.2.1.1.2.0'


# ===========================================================================
# Device poll address
# ===========================================================================

class TestDevicePollAddress:

    def test_hostname_is_preferred_over_ip_address(self):
        device = MagicMock(
            id=1,
            name='switch-1',
            hostname='switch-1.example.com',
            ip_address='10.0.0.1',
            port=161,
        )

        assert _device_poll_address(device) == 'switch-1.example.com'
        assert _device_response_data(device)['address'] == 'switch-1.example.com'

    def test_ip_address_is_used_when_hostname_is_empty(self):
        device = MagicMock(hostname=None, ip_address='10.0.0.1')

        assert _device_poll_address(device) == '10.0.0.1'

    @patch('SNMP.snmp_test.socket.getaddrinfo')
    def test_resolvable_hostname_is_used(self, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_DGRAM, 17, '', ('10.0.0.1', 161))]
        device = MagicMock(
            hostname='switch-1.example.com',
            ip_address='10.0.0.1',
            port=161,
        )

        address, warning = _resolve_device_poll_address(device)

        assert address == 'switch-1.example.com'
        assert warning is None

    @patch('SNMP.snmp_test.socket.getaddrinfo', side_effect=socket.gaierror)
    def test_unresolvable_hostname_falls_back_to_ip(self, mock_getaddrinfo):
        device = MagicMock(
            hostname='switch-1.example.com',
            ip_address='10.0.0.1',
            port=161,
        )

        address, warning = _resolve_device_poll_address(device)

        assert address == '10.0.0.1'
        assert 'cannot resolve' in warning
        assert 'Falling back' in warning

    @patch('SNMP.snmp_test.socket.getaddrinfo', side_effect=socket.gaierror)
    def test_unresolvable_hostname_without_ip_raises_clear_error(self, mock_getaddrinfo):
        device = MagicMock(
            hostname='switch-1.example.com',
            ip_address=None,
            port=161,
        )

        with pytest.raises(ValueError, match='No fallback IP address'):
            _resolve_device_poll_address(device)


# ===========================================================================
# _create_auth_data
# ===========================================================================

class TestCreateAuthData:

    def test_v2c_creates_community_data(self, test_credential_v2c):
        from pysnmp.hlapi.v3arch.asyncio import CommunityData
        auth = _create_auth_data(test_credential_v2c)
        assert isinstance(auth, CommunityData)

    def test_v3_no_auth_no_priv_creates_usm(self, test_credential_v3_no_auth):
        from pysnmp.hlapi.v3arch.asyncio import UsmUserData
        auth = _create_auth_data(test_credential_v3_no_auth)
        assert isinstance(auth, UsmUserData)

    def test_v3_auth_no_priv_creates_usm_with_auth(self, test_credential_v3_auth_no_priv):
        from pysnmp.hlapi.v3arch.asyncio import UsmUserData
        auth = _create_auth_data(test_credential_v3_auth_no_priv)
        assert isinstance(auth, UsmUserData)

    def test_v3_auth_priv_creates_usm_with_auth_and_priv(self, test_credential_v3_auth_priv):
        from pysnmp.hlapi.v3arch.asyncio import UsmUserData
        auth = _create_auth_data(test_credential_v3_auth_priv)
        assert isinstance(auth, UsmUserData)

    def test_v2c_missing_community_raises_value_error(self):
        # Use an unsaved model instance to bypass model-level validation
        # and test the _create_auth_data logic directly
        cred = Credential(
            name='snmp_test_cred_nocommunity',
            version='2c',
            community='',  # explicitly empty, overriding default='public'
        )
        with pytest.raises(ValueError, match='no community string'):
            _create_auth_data(cred)

    def test_v3_auth_no_priv_missing_auth_protocol_raises(self):
        # Use unsaved instance: model validates auth_protocol at save() time,
        # but _create_auth_data validates it independently at runtime
        cred = Credential(
            version='3',
            security_name='user',
            security_level='authNoPriv',
            auth_protocol='',  # no protocol
            auth_pass='',
        )
        with pytest.raises(ValueError, match='auth protocol'):
            _create_auth_data(cred)

    def test_v3_auth_priv_missing_priv_protocol_raises(self):
        # Use unsaved instance to bypass model validation
        cred = Credential(
            version='3',
            security_name='user',
            security_level='authPriv',
            auth_protocol='sha',
            auth_pass='authpass123',
            priv_protocol='',  # no priv protocol
            priv_pass='',
        )
        with pytest.raises(ValueError, match='privacy protocol'):
            _create_auth_data(cred)

    def test_unknown_version_raises_value_error(self):
        cred = Credential(
            name='bad_version_cred',
            version='9',
            security_name='user',
        )
        with pytest.raises(ValueError, match='Unknown SNMP version'):
            _create_auth_data(cred)


# ===========================================================================
# RunSNMPTest view
# ===========================================================================

@pytest.mark.django_db
class TestRunSNMPTestView:

    def test_missing_device_id_returns_400(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({}),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'device_id' in data['error']

    def test_device_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': 999999}),
            content_type='application/json'
        )
        assert response.status_code == 404
        data = json.loads(response.content)
        assert data['success'] is False

    def test_device_without_credential_returns_400(self, authenticated_client, test_network, test_device_template, db):
        # Create device with no credential by bypassing model validation
        # We'll use a credential initially then remove it
        cred = Credential.objects.create(
            name='temp_cred_for_removal',
            version='2c',
            community='public'
        )
        device = Device.objects.create(
            name='device_no_cred',
            ip_address='10.0.0.99',
            port=161,
            retries=1,
            timeout=500,
            credential=cred,
            network=test_network,
            device_template=test_device_template,
        )
        # Remove credential by setting it to None directly in DB
        Device.objects.filter(pk=device.pk).update(credential=None)

        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': device.pk}),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'credential' in data['error'].lower()

    def test_template_not_found_returns_404(self, authenticated_client, test_device):
        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': test_device.pk, 'template_id': 999999}),
            content_type='application/json'
        )
        assert response.status_code == 404
        data = json.loads(response.content)
        assert data['success'] is False

    def test_template_with_no_profiles_returns_400(self, authenticated_client, test_network,
                                                    test_credential_v2c, db):
        empty_template = DeviceTemplate.objects.create(
            name='snmp_test_empty_template',
            vendor='Generic',
        )
        device = Device.objects.create(
            name='device_empty_template',
            ip_address='10.0.0.50',
            port=161,
            retries=1,
            timeout=500,
            credential=test_credential_v2c,
            network=test_network,
            device_template=empty_template,
        )

        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': device.pk, 'template_id': empty_template.pk}),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'profiles' in data['error'].lower()

    @patch('SNMP.snmp_test._perform_snmp_get')
    @patch('SNMP.snmp_test._perform_snmp_walk')
    @patch('SNMP.snmp_test._perform_snmp_table')
    def test_successful_snmp_test_returns_200_with_results(
        self, mock_table, mock_walk, mock_get,
        authenticated_client, test_device
    ):
        mock_get.return_value = {'sysDescr': 'Linux router'}
        mock_walk.return_value = {}
        mock_table.return_value = {}

        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': test_device.pk}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert 'results' in data
        assert data['device']['id'] == test_device.pk
        assert data['device']['address'] == test_device.ip_address
        assert data['template']['name'] == test_device.device_template.name

    @patch('SNMP.snmp_test._perform_snmp_get')
    @patch('SNMP.snmp_test._perform_snmp_walk')
    @patch('SNMP.snmp_test._perform_snmp_table')
    def test_hostname_device_response_uses_hostname_as_poll_address(
        self, mock_table, mock_walk, mock_get,
        authenticated_client, test_device
    ):
        test_device.hostname = 'switch-1.example.com'
        test_device.save(update_fields=['hostname'])
        mock_get.return_value = {'sysDescr': 'Network switch'}
        mock_walk.return_value = {}
        mock_table.return_value = {}

        with patch(
            'SNMP.snmp_test._resolve_device_poll_address',
            return_value=('switch-1.example.com', None),
        ):
            response = authenticated_client.post(
                '/SNMP/RunSNMPTest/',
                data=json.dumps({'device_id': test_device.pk}),
                content_type='application/json'
            )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['device']['address'] == 'switch-1.example.com'
        assert data['device']['hostname'] == 'switch-1.example.com'
        assert data['device']['ip_address'] == '10.0.0.1'

    @patch('SNMP.snmp_test._perform_snmp_get')
    @patch('SNMP.snmp_test._perform_snmp_walk')
    @patch('SNMP.snmp_test._perform_snmp_table')
    def test_unresolvable_hostname_falls_back_to_ip_and_returns_warning(
        self, mock_table, mock_walk, mock_get,
        authenticated_client, test_device
    ):
        test_device.hostname = 'switch-1.example.com'
        test_device.save(update_fields=['hostname'])
        mock_get.return_value = {'sysDescr': 'Network switch'}
        mock_walk.return_value = {}
        mock_table.return_value = {}

        warning = (
            "The machine running LogstashUI cannot resolve hostname "
            "'switch-1.example.com'. Falling back to IP address 10.0.0.1."
        )
        with patch(
            'SNMP.snmp_test._resolve_device_poll_address',
            return_value=('10.0.0.1', warning),
        ):
            response = authenticated_client.post(
                '/SNMP/RunSNMPTest/',
                data=json.dumps({'device_id': test_device.pk}),
                content_type='application/json'
            )

        data = json.loads(response.content)
        assert data['success'] is True
        assert data['device']['address'] == '10.0.0.1'
        assert data['address_warning'] == warning
        mock_get.assert_called_once_with(
            test_device, test_device.credential,
            test_device.device_template.profiles.first().profile_data['get'],
            '10.0.0.1'
        )

    @patch('SNMP.snmp_test.socket.getaddrinfo', side_effect=socket.gaierror)
    def test_unresolvable_hostname_only_device_returns_clear_error(
        self, mock_getaddrinfo, authenticated_client, test_device
    ):
        test_device.hostname = 'switch-1.example.com'
        test_device.ip_address = None
        test_device.save(update_fields=['hostname', 'ip_address'])

        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': test_device.pk}),
            content_type='application/json'
        )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['success'] is False
        assert data['error'] == (
            "The machine running LogstashUI cannot resolve hostname "
            "'switch-1.example.com'. No fallback IP address is configured "
            "for this device."
        )

    @patch('SNMP.snmp_test._perform_snmp_get')
    @patch('SNMP.snmp_test._perform_snmp_walk')
    @patch('SNMP.snmp_test._perform_snmp_table')
    def test_auth_failure_returns_success_false_with_auth_error(
        self, mock_table, mock_walk, mock_get,
        authenticated_client, test_device
    ):
        auth_error = {'error': 'Unknown USM user'}
        mock_get.return_value = {'sysDescr': auth_error}
        mock_walk.return_value = {}
        mock_table.return_value = {}

        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': test_device.pk}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'authentication' in data['error'].lower() or 'auth' in data['error'].lower()

    @patch('SNMP.snmp_test._perform_snmp_get')
    @patch('SNMP.snmp_test._perform_snmp_walk')
    @patch('SNMP.snmp_test._perform_snmp_table')
    def test_all_operations_fail_returns_success_false(
        self, mock_table, mock_walk, mock_get,
        authenticated_client, test_device
    ):
        mock_get.return_value = {'sysDescr': {'error': 'No response from device'}}
        mock_walk.return_value = {}
        mock_table.return_value = {}

        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': test_device.pk}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is False

    @patch('SNMP.snmp_test._perform_snmp_get')
    @patch('SNMP.snmp_test._perform_snmp_walk')
    @patch('SNMP.snmp_test._perform_snmp_table')
    def test_partial_success_returns_success_true_with_has_errors(
        self, mock_table, mock_walk, mock_get,
        authenticated_client, test_device, test_custom_profile, db
    ):
        # Profile has two GET OIDs so we can simulate one success and one failure
        test_custom_profile.profile_data = {
            'get': {'sysDescr': '1.3.6.1.2.1.1.1.0', 'sysUpTime': '1.3.6.1.2.1.1.3.0'},
            'walk': {},
            'table': {}
        }
        test_custom_profile.save()

        mock_get.return_value = {
            'sysDescr': 'Linux router',
            'sysUpTime': {'error': 'No such object'}
        }
        mock_walk.return_value = {}
        mock_table.return_value = {}

        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': test_device.pk}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['has_errors'] is True

    def test_get_method_not_allowed(self, authenticated_client):
        response = authenticated_client.get('/SNMP/RunSNMPTest/')
        assert response.status_code == 405

    @patch('SNMP.snmp_test._perform_snmp_get')
    @patch('SNMP.snmp_test._perform_snmp_walk')
    @patch('SNMP.snmp_test._perform_snmp_table')
    def test_explicit_template_id_overrides_device_template(
        self, mock_table, mock_walk, mock_get,
        authenticated_client, test_device, db
    ):
        mock_get.return_value = {'sysDescr': 'Linux router'}
        mock_walk.return_value = {}
        mock_table.return_value = {}

        # Create a second template with a profile
        extra_profile = Profile.objects.create(
            name='snmp_test_extra_profile',
            vendor='Generic',
            profile_data={'get': {'sysContact': '1.3.6.1.2.1.1.4.0'}, 'walk': {}, 'table': {}}
        )
        extra_template = DeviceTemplate.objects.create(
            name='snmp_test_extra_template',
            vendor='Generic',
        )
        extra_template.profiles.add(extra_profile)

        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': test_device.pk, 'template_id': extra_template.pk}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['template']['name'] == extra_template.name

    @patch('SNMP.snmp_test._perform_snmp_get')
    @patch('SNMP.snmp_test._perform_snmp_walk')
    @patch('SNMP.snmp_test._perform_snmp_table')
    def test_response_contains_execution_time(
        self, mock_table, mock_walk, mock_get,
        authenticated_client, test_device
    ):
        mock_get.return_value = {'sysDescr': 'Linux router'}
        mock_walk.return_value = {}
        mock_table.return_value = {}

        response = authenticated_client.post(
            '/SNMP/RunSNMPTest/',
            data=json.dumps({'device_id': test_device.pk}),
            content_type='application/json'
        )
        data = json.loads(response.content)
        assert 'execution_time' in data


# ===========================================================================
# RunSNMPWalk view
# ===========================================================================

@pytest.mark.django_db
class TestRunSNMPWalkView:

    def test_missing_host_returns_400(self, authenticated_client, test_credential_v2c):
        response = authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({'credential_id': test_credential_v2c.pk}),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'host' in data['error']

    def test_missing_credential_id_returns_400(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({'host': '10.0.0.1'}),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'credential_id' in data['error']

    def test_credential_not_found_returns_404(self, authenticated_client):
        response = authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({'host': '10.0.0.1', 'credential_id': 999999}),
            content_type='application/json'
        )
        assert response.status_code == 404
        data = json.loads(response.content)
        assert data['success'] is False

    @patch('SNMP.snmp_test._perform_full_walk')
    def test_successful_walk_returns_results(self, mock_walk, authenticated_client, test_credential_v2c):
        mock_walk.return_value = {
            'results': [
                {'oid': '1.3.6.1.2.1.1.1.0', 'value': 'Linux router'},
                {'oid': '1.3.6.1.2.1.1.2.0', 'value': '1.3.6.1.4.1.8072.3.2.10'},
            ]
        }

        response = authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({'host': '10.0.0.1', 'credential_id': test_credential_v2c.pk}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['oid_count'] == 2
        assert len(data['results']) == 2
        assert data['host'] == '10.0.0.1'

    @patch('SNMP.snmp_test._perform_full_walk')
    def test_walk_error_without_results_returns_success_false(
        self, mock_walk, authenticated_client, test_credential_v2c
    ):
        mock_walk.return_value = {'error': 'No response from device', 'results': []}

        response = authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({'host': '10.0.0.1', 'credential_id': test_credential_v2c.pk}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is False
        assert 'error' in data

    @patch('SNMP.snmp_test._perform_full_walk')
    def test_walk_with_partial_error_and_results_returns_success_true(
        self, mock_walk, authenticated_client, test_credential_v2c
    ):
        mock_walk.return_value = {
            'results': [{'oid': '1.3.6.1.2.1.1.1.0', 'value': 'Linux'}],
            'error': 'End of MIB'
        }

        response = authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({'host': '10.0.0.1', 'credential_id': test_credential_v2c.pk}),
            content_type='application/json'
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['partial_error'] == 'End of MIB'

    @patch('SNMP.snmp_test._perform_full_walk')
    def test_custom_port_and_start_oid_forwarded(
        self, mock_walk, authenticated_client, test_credential_v2c
    ):
        mock_walk.return_value = {'results': []}

        authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({
                'host': '10.0.0.1',
                'port': 1161,
                'credential_id': test_credential_v2c.pk,
                'start_oid': '1.3.6.1.2.1.2'
            }),
            content_type='application/json'
        )
        mock_walk.assert_called_once()
        call_args = mock_walk.call_args
        assert call_args[0][1] == 1161          # port
        assert call_args[0][3] == '1.3.6.1.2.1.2'  # start_oid

    @patch('SNMP.snmp_test._perform_full_walk')
    def test_default_port_is_161(self, mock_walk, authenticated_client, test_credential_v2c):
        mock_walk.return_value = {'results': []}

        authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({'host': '10.0.0.1', 'credential_id': test_credential_v2c.pk}),
            content_type='application/json'
        )
        call_args = mock_walk.call_args
        assert call_args[0][1] == 161

    @patch('SNMP.snmp_test._perform_full_walk')
    def test_default_start_oid_is_1_3_6_1(self, mock_walk, authenticated_client, test_credential_v2c):
        mock_walk.return_value = {'results': []}

        authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({'host': '10.0.0.1', 'credential_id': test_credential_v2c.pk}),
            content_type='application/json'
        )
        call_args = mock_walk.call_args
        assert call_args[0][3] == '1.3.6.1'

    @patch('SNMP.snmp_test._perform_full_walk')
    def test_response_includes_execution_time(
        self, mock_walk, authenticated_client, test_credential_v2c
    ):
        mock_walk.return_value = {'results': []}

        response = authenticated_client.post(
            '/SNMP/RunSNMPWalk/',
            data=json.dumps({'host': '10.0.0.1', 'credential_id': test_credential_v2c.pk}),
            content_type='application/json'
        )
        data = json.loads(response.content)
        assert 'execution_time' in data

    def test_get_method_not_allowed(self, authenticated_client):
        response = authenticated_client.get('/SNMP/RunSNMPWalk/')
        assert response.status_code == 405
