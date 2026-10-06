#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for REST SNMP network endpoints — /api/snmp/networks/."""

import json
import pytest

from django.contrib.auth.models import User
from Management.models import UserProfile
from PipelineManager.models import Connection
from SNMP.models import Credential, Network


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(client, url, body, **kw):
    return client.post(url, data=json.dumps(body), content_type='application/json', **kw)


def _put(client, url, body, **kw):
    return client.put(url, data=json.dumps(body), content_type='application/json', **kw)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def es_connection(db):
    return Connection.objects.create(
        name='Test ES', connection_type='CENTRALIZED',
        host='https://es.example.com', port=9200,
        username='elastic', password='changeme',
    )


@pytest.fixture
def cred(db):
    return Credential.objects.create(name='net-test-cred', version='2c', community='public')


@pytest.fixture
def network(db, es_connection, cred):
    return Network.objects.create(
        name='TestNet', network_range='10.0.0.0/24',
        connection=es_connection, discovery_credential=cred,
        discovery_enabled=True, interval=30,
    )


@pytest.fixture
def readonly_user(db):
    user = User.objects.create_user(username='ronet', password='Readonly1!')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    return user


@pytest.fixture
def readonly_client(client, readonly_user):
    client.login(username='ronet', password='Readonly1!')
    return client


# ---------------------------------------------------------------------------
# GET /api/snmp/networks/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNetworkList:

    def test_list_200(self, authenticated_client, network):
        assert authenticated_client.get('/api/snmp/networks/').status_code == 200

    def test_list_envelope(self, authenticated_client, network):
        data = authenticated_client.get('/api/snmp/networks/').json()
        assert 'networks' in data and 'total' in data

    def test_list_includes_network(self, authenticated_client, network):
        ids = [n['id'] for n in authenticated_client.get('/api/snmp/networks/').json()['networks']]
        assert network.id in ids

    def test_list_expected_fields(self, authenticated_client, network):
        nets = authenticated_client.get('/api/snmp/networks/').json()['networks']
        n = next(x for x in nets if x['id'] == network.id)
        for f in ('id', 'name', 'network_range', 'deployment_mode', 'credential_mode',
                  'connection_id', 'discovery_credential_id', 'discovery_enabled',
                  'traps_enabled', 'interval', 'namespace', 'device_count'):
            assert f in n, f'Missing field: {f}'

    def test_list_no_auth_401(self, client):
        assert client.get('/api/snmp/networks/').status_code == 401

    def test_list_search_filter(self, authenticated_client, network):
        data = authenticated_client.get(f'/api/snmp/networks/?search={network.name}').json()
        assert any(n['id'] == network.id for n in data['networks'])

    def test_list_wrong_method_405(self, authenticated_client):
        assert authenticated_client.patch('/api/snmp/networks/').status_code == 405


# ---------------------------------------------------------------------------
# GET /api/snmp/networks/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNetworkGet:

    def test_get_200(self, authenticated_client, network):
        r = authenticated_client.get(f'/api/snmp/networks/{network.id}/')
        assert r.status_code == 200
        assert r.json()['network']['id'] == network.id

    def test_get_full_fields(self, authenticated_client, network):
        d = authenticated_client.get(f'/api/snmp/networks/{network.id}/').json()['network']
        assert 'namespace_from_device_template' in d
        assert 'updated_at' in d

    def test_get_404(self, authenticated_client):
        assert authenticated_client.get('/api/snmp/networks/99999/').status_code == 404

    def test_get_no_auth_401(self, client, network):
        assert client.get(f'/api/snmp/networks/{network.id}/').status_code == 401

    def test_get_readonly_allowed(self, readonly_client, network):
        assert readonly_client.get(f'/api/snmp/networks/{network.id}/').status_code == 200


# ---------------------------------------------------------------------------
# POST /api/snmp/networks/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNetworkCreate:

    def test_create_201(self, authenticated_client, es_connection, cred):
        r = _post(authenticated_client, '/api/snmp/networks/', {
            'name': 'NewNet', 'network_range': '192.168.10.0/24',
            'connection': es_connection.id, 'discovery_credential': cred.id,
        })
        assert r.status_code == 201
        assert r.json()['success'] is True

    def test_create_persists(self, authenticated_client):
        _post(authenticated_client, '/api/snmp/networks/', {
            'name': 'PersistNet', 'network_range': '10.1.0.0/24',
        })
        assert Network.objects.filter(name='PersistNet').exists()

    def test_create_missing_name_400(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/networks/', {'network_range': '10.0.0.0/24'})
        assert r.status_code == 400

    def test_create_cidr_too_large_400(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/networks/', {
            'name': 'BigNet', 'network_range': '10.0.0.0/8',
        })
        assert r.status_code == 400
        assert 'too large' in r.json()['error'].lower()

    def test_create_cidr_exactly_20_ok(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/networks/', {
            'name': 'Slash20Net', 'network_range': '10.2.0.0/20',
        })
        assert r.status_code == 201

    def test_create_invalid_cidr_400(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/networks/', {
            'name': 'BadCIDR', 'network_range': 'not-a-cidr',
        })
        assert r.status_code == 400

    def test_create_invalid_namespace_400(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/networks/', {
            'name': 'BadNS', 'network_range': '10.3.0.0/24',
            'namespace': 'INVALID NAMESPACE!',
        })
        assert r.status_code == 400

    def test_create_no_auth_401(self, client):
        assert _post(client, '/api/snmp/networks/', {'name': 'x'}).status_code == 401

    def test_create_readonly_403(self, readonly_client):
        assert _post(readonly_client, '/api/snmp/networks/', {
            'name': 'ro-net', 'network_range': '10.4.0.0/24',
        }).status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/snmp/networks/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNetworkUpdate:

    def test_update_name(self, authenticated_client, network):
        _put(authenticated_client, f'/api/snmp/networks/{network.id}/', {'name': 'Renamed'})
        network.refresh_from_db()
        assert network.name == 'Renamed'

    def test_update_interval(self, authenticated_client, network):
        _put(authenticated_client, f'/api/snmp/networks/{network.id}/', {'interval': 120})
        network.refresh_from_db()
        assert network.interval == 120

    def test_update_clear_connection_null(self, authenticated_client, network, es_connection):
        assert network.connection == es_connection
        _put(authenticated_client, f'/api/snmp/networks/{network.id}/', {'connection': None})
        network.refresh_from_db()
        assert network.connection is None

    def test_update_cidr_too_large_400(self, authenticated_client, network):
        r = _put(authenticated_client, f'/api/snmp/networks/{network.id}/', {
            'network_range': '10.0.0.0/16',
        })
        assert r.status_code == 400

    def test_update_404(self, authenticated_client):
        assert _put(authenticated_client, '/api/snmp/networks/99999/', {}).status_code == 404

    def test_update_no_auth_401(self, client, network):
        assert _put(client, f'/api/snmp/networks/{network.id}/', {}).status_code == 401

    def test_update_readonly_403(self, readonly_client, network):
        assert _put(readonly_client, f'/api/snmp/networks/{network.id}/', {}).status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/snmp/networks/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNetworkDelete:

    def test_delete_removes_row(self, authenticated_client, network):
        nid = network.id
        r = authenticated_client.delete(f'/api/snmp/networks/{nid}/')
        assert r.status_code == 200
        assert not Network.objects.filter(id=nid).exists()

    def test_delete_returns_success(self, authenticated_client, network):
        assert authenticated_client.delete(f'/api/snmp/networks/{network.id}/').json()['success'] is True

    def test_delete_404(self, authenticated_client):
        assert authenticated_client.delete('/api/snmp/networks/99999/').status_code == 404

    def test_delete_no_auth_401(self, client, network):
        assert client.delete(f'/api/snmp/networks/{network.id}/').status_code == 401

    def test_delete_readonly_403(self, readonly_client, network):
        assert readonly_client.delete(f'/api/snmp/networks/{network.id}/').status_code == 403

    def test_delete_wrong_method_405(self, authenticated_client, network):
        assert authenticated_client.patch(f'/api/snmp/networks/{network.id}/').status_code == 405
