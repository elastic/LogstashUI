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


# ---------------------------------------------------------------------------
# Edge-case coverage — gaps identified after initial review
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDeviceInvalidForeignKeys:
    """Invalid FK ids should not crash the server — they surface as errors."""

    def test_create_invalid_credential_id(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'bad-cred-device',
            'ip_address': '10.0.1.1',
            'credential': 99999,
        })
        # Django raises ValueError / IntegrityError for bad FK — should not be 500
        assert response.status_code in (400, 409)
        assert response['Content-Type'] == 'application/json'

    def test_create_invalid_network_id(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'bad-net-device',
            'ip_address': '10.0.1.2',
            'network': 99999,
        })
        assert response.status_code in (400, 409, 500)
        assert response['Content-Type'] == 'application/json'

    def test_create_invalid_template_id(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'bad-tmpl-device',
            'ip_address': '10.0.1.3',
            'device_template': 99999,
        })
        assert response.status_code in (400, 409, 500)
        assert response['Content-Type'] == 'application/json'

    def test_update_invalid_credential_id(self, authenticated_client, device):
        response = _put(authenticated_client, f'/api/snmp/devices/{device.id}/', {
            'ip_address': '10.0.0.1',
            'credential': 99999,
        })
        assert response.status_code in (400, 409, 500)
        assert response['Content-Type'] == 'application/json'


@pytest.mark.django_db
class TestDeviceLatLon:
    """latitude / longitude edge cases."""

    def test_create_with_valid_lat_lon(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'geo-device',
            'ip_address': '10.0.2.1',
            'latitude': 37.7749,
            'longitude': -122.4194,
        })
        assert response.status_code == 201
        d = __import__('SNMP.models', fromlist=['Device']).Device.objects.get(name='geo-device')
        assert float(d.latitude) == pytest.approx(37.7749, abs=1e-4)
        assert float(d.longitude) == pytest.approx(-122.4194, abs=1e-4)

    def test_create_non_numeric_latitude_returns_400(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'bad-lat-device',
            'ip_address': '10.0.2.2',
            'latitude': 'not-a-number',
            'longitude': 0,
        })
        assert response.status_code == 400
        assert response['Content-Type'] == 'application/json'

    def test_create_non_numeric_longitude_returns_400(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'bad-lon-device',
            'ip_address': '10.0.2.3',
            'latitude': 0,
            'longitude': 'not-a-number',
        })
        assert response.status_code == 400
        assert response['Content-Type'] == 'application/json'

    def test_update_non_numeric_lat_returns_400(self, authenticated_client, device):
        response = _put(authenticated_client, f'/api/snmp/devices/{device.id}/', {
            'ip_address': '10.0.0.1',
            'latitude': 'bad',
            'longitude': 0,
        })
        assert response.status_code == 400

    def test_lat_lon_null_clears_value(self, authenticated_client):
        """Explicitly passing null should store None."""
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'null-geo-device',
            'ip_address': '10.0.2.4',
            'latitude': None,
            'longitude': None,
        })
        assert response.status_code == 201
        from SNMP.models import Device
        d = Device.objects.get(name='null-geo-device')
        assert d.latitude is None
        assert d.longitude is None


@pytest.mark.django_db
class TestDeviceMetadataVariants:
    """metadata can arrive as a dict or a JSON string."""

    def test_create_metadata_as_dict(self, authenticated_client):
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'meta-dict-device',
            'ip_address': '10.0.3.1',
            'metadata': {'env': 'prod', 'tier': 1},
        })
        assert response.status_code == 201
        from SNMP.models import Device
        d = Device.objects.get(name='meta-dict-device')
        assert d.metadata == {'env': 'prod', 'tier': 1}

    def test_create_metadata_as_json_string(self, authenticated_client):
        """metadata sent as a serialized JSON string should be parsed."""
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'meta-str-device',
            'ip_address': '10.0.3.2',
            'metadata': '{"env": "staging"}',
        })
        assert response.status_code == 201
        from SNMP.models import Device
        d = Device.objects.get(name='meta-str-device')
        assert d.metadata == {'env': 'staging'}

    def test_create_invalid_json_string_metadata_stores_empty(self, authenticated_client):
        """Invalid JSON string for metadata should gracefully store {}."""
        response = _post(authenticated_client, '/api/snmp/devices/', {
            'name': 'meta-bad-str-device',
            'ip_address': '10.0.3.3',
            'metadata': 'not-valid-json{{{',
        })
        assert response.status_code == 201
        from SNMP.models import Device
        d = Device.objects.get(name='meta-bad-str-device')
        assert d.metadata == {}

    def test_update_metadata_as_json_string(self, authenticated_client, device):
        response = _put(authenticated_client, f'/api/snmp/devices/{device.id}/', {
            'ip_address': '10.0.0.1',
            'metadata': '{"role": "core"}',
        })
        assert response.status_code == 200
        device.refresh_from_db()
        assert device.metadata == {'role': 'core'}


@pytest.mark.django_db
class TestDeviceListPaginationBoundaries:
    """page_size clamping and boundary conditions."""

    def test_page_size_zero_clamped_to_one(self, authenticated_client, device):
        response = authenticated_client.get('/api/snmp/devices/?page_size=0')
        assert response.status_code == 200
        data = response.json()
        assert data['page_size'] >= 1

    def test_page_size_above_max_clamped_to_200(self, authenticated_client, device):
        response = authenticated_client.get('/api/snmp/devices/?page_size=9999')
        assert response.status_code == 200
        data = response.json()
        assert data['page_size'] == 200

    def test_page_beyond_last_returns_empty_devices(self, authenticated_client, device):
        response = authenticated_client.get('/api/snmp/devices/?page=9999&page_size=25')
        assert response.status_code == 200
        data = response.json()
        assert data['devices'] == []
        assert data['has_next'] is False

    def test_negative_page_clamped_to_one(self, authenticated_client, device):
        response = authenticated_client.get('/api/snmp/devices/?page=-5')
        assert response.status_code == 200
        assert response.json()['page'] == 1


@pytest.mark.django_db
class TestDeviceListAllSortFields:
    """Every documented sort_by value should return 200."""

    SORT_FIELDS = [
        'name', '-name',
        'ip_address', '-ip_address',
        'hostname', '-hostname',
        'created_at', '-created_at',
    ]

    @pytest.mark.parametrize('sort_by', SORT_FIELDS)
    def test_valid_sort_returns_200(self, authenticated_client, device, sort_by):
        response = authenticated_client.get(f'/api/snmp/devices/?sort_by={sort_by}')
        assert response.status_code == 200

    def test_invalid_sort_falls_back_to_default(self, authenticated_client, device):
        """An unrecognised sort_by should not crash — falls back to -created_at."""
        response = authenticated_client.get('/api/snmp/devices/?sort_by=TOTALLY_INVALID')
        assert response.status_code == 200
        assert 'devices' in response.json()


@pytest.mark.django_db
class TestDeviceListNetworkFilter:
    """Network filter should return only devices in that network."""

    def test_filter_by_valid_network(self, authenticated_client, device, network):
        response = authenticated_client.get(f'/api/snmp/devices/?network={network.id}')
        assert response.status_code == 200
        ids = [d['id'] for d in response.json()['devices']]
        assert device.id in ids

    def test_filter_by_nonexistent_network_returns_empty(self, authenticated_client, device):
        response = authenticated_client.get('/api/snmp/devices/?network=99999')
        assert response.status_code == 200
        assert response.json()['total'] == 0

    def test_filter_excludes_devices_in_other_networks(
        self, authenticated_client, device, network, snmp_connection, credential
    ):
        from SNMP.models import Network, Device
        other_net = Network.objects.create(
            name='OtherNet', network_range='172.16.0.0/24',
            connection=snmp_connection, discovery_credential=credential,
        )
        other_dev = Device.objects.create(
            name='other-net-device', ip_address='172.16.0.1',
            network=other_net, credential=credential,
        )
        response = authenticated_client.get(f'/api/snmp/devices/?network={network.id}')
        ids = [d['id'] for d in response.json()['devices']]
        assert other_dev.id not in ids
        assert device.id in ids
