#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for API/snmp_views.py — REST SNMP device endpoints."""

import json
import pytest

from django.contrib.auth.models import User
from Management.models import UserProfile
from PipelineManager.models import Connection
from SNMP.models import Credential, Device, DeviceTemplate, Network, SNMPDeploymentState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def snmp_connection(db):
    return Connection.objects.create(
        name='SNMP ES Connection',
        connection_type='CENTRALIZED',
        host='https://es.example.com',
        port=9200,
        username='elastic',
        password='changeme',
    )


@pytest.fixture
def credential(db):
    return Credential.objects.create(
        name='v2c-cred',
        version='2c',
        community='public',
    )


@pytest.fixture
def network(db, snmp_connection, credential):
    return Network.objects.create(
        name='Test Network',
        network_range='10.0.0.0/24',
        connection=snmp_connection,
        discovery_credential=credential,
        discovery_enabled=True,
        interval=30,
    )


@pytest.fixture
def device(db, network, credential):
    return Device.objects.create(
        name='test-router',
        ip_address='10.0.0.1',
        port=161,
        retries=2,
        timeout=1000,
        credential=credential,
        network=network,
    )


@pytest.fixture
def readonly_user(db):
    user = User.objects.create_user(username='rouser', password='Sup3rS3cur3!Pass')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    return user


@pytest.fixture
def readonly_client(client, readonly_user):
    client.login(username='rouser', password='Sup3rS3cur3!Pass')
    return client


def _post(client, url, body, **headers):
    return client.post(url, data=json.dumps(body), content_type='application/json', **headers)


def _put(client, url, body, **headers):
    return client.put(url, data=json.dumps(body), content_type='application/json', **headers)


# ---------------------------------------------------------------------------
# GET /api/snmp/devices/  — list
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDeviceList:

    def test_list_returns_200(self, authenticated_client, device):
        response = authenticated_client.get('/api/snmp/devices/')
        assert response.status_code == 200

    def test_list_returns_pagination_envelope(self, authenticated_client, device):
        data = authenticated_client.get('/api/snmp/devices/').json()
        for key in ('devices', 'total', 'page', 'page_size', 'total_pages', 'has_next', 'has_previous'):
            assert key in data, f'Missing key: {key}'

    def test_list_includes_device(self, authenticated_client, device):
        data = authenticated_client.get('/api/snmp/devices/').json()
        ids = [d['id'] for d in data['devices']]
        assert device.id in ids

    def test_list_expected_fields(self, authenticated_client, device):
        data = authenticated_client.get('/api/snmp/devices/').json()
        item = next(d for d in data['devices'] if d['id'] == device.id)
        for field in ('id', 'name', 'ip_address', 'hostname', 'port', 'retries', 'timeout',
                      'credential_id', 'network_id', 'site', 'building', 'room', 'created_at'):
            assert field in item, f'Missing field: {field}'

    def test_list_no_auth_returns_401(self, client):
        response = client.get('/api/snmp/devices/')
        assert response.status_code == 401

    def test_list_search_by_name(self, authenticated_client, device):
        response = authenticated_client.get(f'/api/snmp/devices/?search={device.name}')
        ids = [d['id'] for d in response.json()['devices']]
        assert device.id in ids

    def test_list_search_by_ip(self, authenticated_client, device):
        response = authenticated_client.get('/api/snmp/devices/?search=10.0.0.1')
        ids = [d['id'] for d in response.json()['devices']]
        assert device.id in ids

    def test_list_search_no_match_returns_empty(self, authenticated_client, device):
        response = authenticated_client.get('/api/snmp/devices/?search=zzz-no-match-zzz')
        assert response.json()['total'] == 0
        assert response.json()['devices'] == []

    def test_list_filter_by_network(self, authenticated_client, device, network):
        response = authenticated_client.get(f'/api/snmp/devices/?network={network.id}')
        ids = [d['id'] for d in response.json()['devices']]
        assert device.id in ids

    def test_list_filter_excludes_other_networks(self, authenticated_client, device, snmp_connection, credential):
        other_net = Network.objects.create(
            name='Other Network', network_range='172.16.0.0/24',
            connection=snmp_connection, discovery_credential=credential,
        )
        response = authenticated_client.get(f'/api/snmp/devices/?network={other_net.id}')
        ids = [d['id'] for d in response.json()['devices']]
        assert device.id not in ids

    def test_list_pagination(self, authenticated_client, network, credential):
        for i in range(5):
            Device.objects.create(name=f'pag-device-{i}', ip_address=f'10.1.0.{i}',
                                  network=network, credential=credential)
        response = authenticated_client.get('/api/snmp/devices/?page=1&page_size=3')
        data = response.json()
        assert len(data['devices']) == 3
        assert data['total'] >= 5
        assert data['has_next'] is True

    def test_list_invalid_sort_defaults_gracefully(self, authenticated_client, device):
        response = authenticated_client.get('/api/snmp/devices/?sort_by=INVALID')
        assert response.status_code == 200

    def test_list_empty_when_no_devices(self, authenticated_client):
        Device.objects.all().delete()
        response = authenticated_client.get('/api/snmp/devices/')
        assert response.status_code == 200
        assert response.json()['total'] == 0

    def test_list_wrong_method_returns_405(self, authenticated_client):
        response = authenticated_client.patch('/api/snmp/devices/')
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# POST /api/snmp/devices/  — create
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDeviceCreate:

    def test_create_success_returns_201(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'new-device', 'ip_address': '10.0.0.2',
        })
        assert response.status_code == 201
        assert response.json()['success'] is True
        assert 'id' in response.json()

    def test_create_persists_to_db(self, authenticated_client):
        _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'persist-device', 'ip_address': '10.0.0.3',
        })
        assert Device.objects.filter(name='persist-device').exists()

    def test_create_with_all_fields(self, authenticated_client, network, credential):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'full-device',
            'ip_address': '10.0.0.4',
            'hostname': 'router.example.com',
            'port': 162,
            'retries': 3,
            'timeout': 2000,
            'credential': credential.id,
            'network': network.id,
            'site': 'HQ',
            'building': 'A',
            'room': '101',
            'metadata': {'role': 'core'},
        })
        assert response.status_code == 201
        d = Device.objects.get(name='full-device')
        assert d.port == 162
        assert d.network == network
        assert d.credential == credential
        assert d.site == 'HQ'
        assert d.metadata == {'role': 'core'}

    def test_create_hostname_only(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'hostname-only', 'hostname': 'switch.example.com',
        })
        assert response.status_code == 201

    def test_create_missing_name_returns_400(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'ip_address': '10.0.0.5',
        })
        assert response.status_code == 400

    def test_create_no_ip_or_hostname_returns_400(self, authenticated_client):
        """Device.clean() requires at least one of ip_address / hostname."""
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'no-host-device',
        })
        assert response.status_code == 400

    def test_create_duplicate_name_returns_400(self, authenticated_client, device):
        # Device.save() calls full_clean(), so uniqueness violation is a ValidationError → 400
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': device.name, 'ip_address': '10.0.0.99',
        })
        assert response.status_code == 400
        assert response.json()['success'] is False

    def test_create_marks_config_changed(self, authenticated_client):
        SNMPDeploymentState.objects.filter(pk=1).update(last_config_change=None)
        _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'deploy-test', 'ip_address': '10.0.0.6',
        })
        assert SNMPDeploymentState.has_undeployed_changes()

    def test_create_no_auth_returns_401(self, client):
        response = _post(client, '/api/snmp/devices/', {
            'name': 'unauth', 'ip_address': '10.0.0.7',
        })
        assert response.status_code == 401

    def test_create_readonly_returns_403(self, readonly_client):
        response = _post(readonly_client, '/api/snmp/devices/', {
            'name': 'ro-device', 'ip_address': '10.0.0.8',
        })
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/snmp/devices/{id}/  — read
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDeviceGet:

    def test_get_returns_200(self, authenticated_client, device):
        response = authenticated_client.get(f'/api/snmp/devices/{device.id}/')
        assert response.status_code == 200
        assert response.json()['success'] is True
        assert response.json()['device']['id'] == device.id

    def test_get_returns_full_fields(self, authenticated_client, device):
        d = authenticated_client.get(f'/api/snmp/devices/{device.id}/').json()['device']
        for field in ('id', 'name', 'ip_address', 'hostname', 'port', 'retries', 'timeout',
                      'credential_id', 'network_id', 'device_template_id',
                      'site', 'building', 'room', 'latitude', 'longitude',
                      'metadata', 'created_at', 'updated_at'):
            assert field in d, f'Missing field: {field}'

    def test_get_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.get('/api/snmp/devices/99999/')
        assert response.status_code == 404

    def test_get_no_auth_returns_401(self, client, device):
        response = client.get(f'/api/snmp/devices/{device.id}/')
        assert response.status_code == 401

    def test_get_readonly_user_allowed(self, readonly_client, device):
        response = readonly_client.get(f'/api/snmp/devices/{device.id}/')
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# PUT /api/snmp/devices/{id}/  — update
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDeviceUpdate:

    def test_update_name(self, authenticated_client, device):
        response = _put(authenticated_client, f'/api/snmp/devices/{device.id}/', {
            'name': 'renamed-device', 'ip_address': '10.0.0.1',
        })
        assert response.status_code == 200
        device.refresh_from_db()
        assert device.name == 'renamed-device'

    def test_update_numeric_fields(self, authenticated_client, device):
        _put(authenticated_client, f'/api/snmp/devices/{device.id}/', {
            'ip_address': '10.0.0.1',
            'port': 162, 'retries': 5, 'timeout': 3000,
        })
        device.refresh_from_db()
        assert device.port == 162
        assert device.retries == 5
        assert device.timeout == 3000

    def test_update_clears_network_when_null(self, authenticated_client, device, network):
        assert device.network == network
        _put(authenticated_client, f'/api/snmp/devices/{device.id}/', {
            'ip_address': '10.0.0.1', 'network': None,
        })
        device.refresh_from_db()
        assert device.network is None

    def test_update_sets_metadata(self, authenticated_client, device):
        _put(authenticated_client, f'/api/snmp/devices/{device.id}/', {
            'ip_address': '10.0.0.1', 'metadata': {'env': 'prod'},
        })
        device.refresh_from_db()
        assert device.metadata == {'env': 'prod'}

    def test_update_marks_config_changed(self, authenticated_client, device):
        SNMPDeploymentState.objects.filter(pk=1).update(last_config_change=None)
        _put(authenticated_client, f'/api/snmp/devices/{device.id}/', {
            'ip_address': '10.0.0.1',
        })
        assert SNMPDeploymentState.has_undeployed_changes()

    def test_update_nonexistent_returns_404(self, authenticated_client):
        response = _put(authenticated_client, '/api/snmp/devices/99999/', {'ip_address': '1.2.3.4'})
        assert response.status_code == 404

    def test_update_no_ip_or_hostname_returns_400(self, authenticated_client, device):
        response = _put(authenticated_client, f'/api/snmp/devices/{device.id}/', {
            'ip_address': None, 'hostname': None,
        })
        assert response.status_code == 400

    def test_update_no_auth_returns_401(self, client, device):
        response = _put(client, f'/api/snmp/devices/{device.id}/', {'ip_address': '10.0.0.1'})
        assert response.status_code == 401

    def test_update_readonly_returns_403(self, readonly_client, device):
        response = _put(readonly_client, f'/api/snmp/devices/{device.id}/', {'ip_address': '10.0.0.1'})
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/snmp/devices/{id}/  — delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDeviceDelete:

    def test_delete_removes_row(self, authenticated_client, device):
        device_id = device.id
        response = authenticated_client.delete(f'/api/snmp/devices/{device_id}/')
        assert response.status_code == 200
        assert response.json()['success'] is True
        assert not Device.objects.filter(id=device_id).exists()

    def test_delete_returns_json(self, authenticated_client, device):
        response = authenticated_client.delete(f'/api/snmp/devices/{device.id}/')
        assert response['Content-Type'] == 'application/json'

    def test_delete_marks_config_changed(self, authenticated_client, device):
        SNMPDeploymentState.objects.filter(pk=1).update(last_config_change=None)
        authenticated_client.delete(f'/api/snmp/devices/{device.id}/')
        assert SNMPDeploymentState.has_undeployed_changes()

    def test_delete_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.delete('/api/snmp/devices/99999/')
        assert response.status_code == 404

    def test_delete_no_auth_returns_401(self, client, device):
        response = client.delete(f'/api/snmp/devices/{device.id}/')
        assert response.status_code == 401

    def test_delete_readonly_returns_403(self, readonly_client, device):
        response = readonly_client.delete(f'/api/snmp/devices/{device.id}/')
        assert response.status_code == 403

    def test_delete_wrong_method_returns_405(self, authenticated_client, device):
        response = authenticated_client.patch(f'/api/snmp/devices/{device.id}/')
        assert response.status_code == 405
