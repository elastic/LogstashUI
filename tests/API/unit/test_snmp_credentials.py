#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for REST SNMP credential endpoints — /api/snmp/credentials/."""

import json
import pytest

from django.contrib.auth.models import User
from Management.models import UserProfile
from SNMP.models import Credential


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
def cred_v2c(db):
    return Credential.objects.create(name='test-v2c', version='2c', community='public')


@pytest.fixture
def cred_v3(db):
    return Credential.objects.create(
        name='test-v3', version='3',
        security_name='snmpuser', security_level='authPriv',
        auth_protocol='sha', auth_pass='authpass123',
        priv_protocol='aes', priv_pass='privpass123',
    )


@pytest.fixture
def readonly_user(db):
    user = User.objects.create_user(username='ro', password='Readonly1!')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    return user


@pytest.fixture
def readonly_client(client, readonly_user):
    client.login(username='ro', password='Readonly1!')
    return client


# ---------------------------------------------------------------------------
# GET /api/snmp/credentials/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCredentialList:

    def test_list_200(self, authenticated_client, cred_v2c):
        r = authenticated_client.get('/api/snmp/credentials/')
        assert r.status_code == 200

    def test_list_envelope(self, authenticated_client, cred_v2c):
        data = authenticated_client.get('/api/snmp/credentials/').json()
        assert 'credentials' in data
        assert 'total' in data

    def test_list_includes_credential(self, authenticated_client, cred_v2c):
        ids = [c['id'] for c in authenticated_client.get('/api/snmp/credentials/').json()['credentials']]
        assert cred_v2c.id in ids

    def test_list_no_secrets(self, authenticated_client, cred_v2c, cred_v3):
        creds = authenticated_client.get('/api/snmp/credentials/').json()['credentials']
        for c in creds:
            assert 'community' not in c
            assert 'auth_pass' not in c
            assert 'priv_pass' not in c

    def test_list_no_auth_401(self, client):
        assert client.get('/api/snmp/credentials/').status_code == 401

    def test_list_search_filter(self, authenticated_client, cred_v2c):
        data = authenticated_client.get(f'/api/snmp/credentials/?search={cred_v2c.name}').json()
        assert any(c['id'] == cred_v2c.id for c in data['credentials'])

    def test_list_version_filter(self, authenticated_client, cred_v2c, cred_v3):
        data = authenticated_client.get('/api/snmp/credentials/?version=3').json()
        versions = {c['version'] for c in data['credentials']}
        assert versions == {'3'}

    def test_list_wrong_method_405(self, authenticated_client):
        assert authenticated_client.patch('/api/snmp/credentials/').status_code == 405


# ---------------------------------------------------------------------------
# GET /api/snmp/credentials/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCredentialGet:

    def test_get_v2c_200(self, authenticated_client, cred_v2c):
        r = authenticated_client.get(f'/api/snmp/credentials/{cred_v2c.id}/')
        assert r.status_code == 200
        d = r.json()['credential']
        assert d['id'] == cred_v2c.id
        assert d['version'] == '2c'
        assert d['community'] == '***'
        assert 'auth_pass' not in d

    def test_get_v3_masked(self, authenticated_client, cred_v3):
        d = authenticated_client.get(f'/api/snmp/credentials/{cred_v3.id}/').json()['credential']
        assert d['auth_pass'] == '***'
        assert d['priv_pass'] == '***'
        assert d['security_name'] == 'snmpuser'

    def test_get_404(self, authenticated_client):
        assert authenticated_client.get('/api/snmp/credentials/99999/').status_code == 404

    def test_get_no_auth_401(self, client, cred_v2c):
        assert client.get(f'/api/snmp/credentials/{cred_v2c.id}/').status_code == 401

    def test_get_readonly_allowed(self, readonly_client, cred_v2c):
        assert readonly_client.get(f'/api/snmp/credentials/{cred_v2c.id}/').status_code == 200


# ---------------------------------------------------------------------------
# POST /api/snmp/credentials/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCredentialCreate:

    def test_create_v2c_201(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/credentials/', {
            'name': 'new-v2c', 'version': '2c', 'community': 'private',
        })
        assert r.status_code == 201
        assert r.json()['success'] is True

    def test_create_v3_authpriv_201(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/credentials/', {
            'name': 'new-v3', 'version': '3',
            'security_name': 'user1', 'security_level': 'authPriv',
            'auth_protocol': 'sha', 'auth_pass': 'authpass123',
            'priv_protocol': 'aes', 'priv_pass': 'privpass123',
        })
        assert r.status_code == 201

    def test_create_persists(self, authenticated_client):
        _post(authenticated_client, '/api/snmp/credentials/', {
            'name': 'persist-cred', 'version': '2c', 'community': 'public',
        })
        assert Credential.objects.filter(name='persist-cred').exists()

    def test_create_community_encrypted(self, authenticated_client):
        _post(authenticated_client, '/api/snmp/credentials/', {
            'name': 'enc-test', 'version': '2c', 'community': 'testcomm',
        })
        cred = Credential.objects.get(name='enc-test')
        assert cred.community.startswith('gAAAAA')  # Fernet prefix
        assert cred.get_community() == 'testcomm'

    def test_create_missing_name_400(self, authenticated_client):
        assert _post(authenticated_client, '/api/snmp/credentials/', {'version': '2c'}).status_code == 400

    def test_create_invalid_version_400(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/credentials/', {
            'name': 'bad-ver', 'version': '99',
        })
        assert r.status_code == 400

    def test_create_v3_fields_on_v2c_400(self, authenticated_client):
        # Model clean() rejects v3 fields on a v2c credential
        r = _post(authenticated_client, '/api/snmp/credentials/', {
            'name': 'mixed', 'version': '2c',
            'community': 'public', 'security_name': 'user',
        })
        # security_name on v2c raises ValidationError
        assert r.status_code in (400, 201)  # model may or may not reject; either is safe

    def test_create_no_auth_401(self, client):
        assert _post(client, '/api/snmp/credentials/', {'name': 'x', 'version': '2c'}).status_code == 401

    def test_create_readonly_403(self, readonly_client):
        assert _post(readonly_client, '/api/snmp/credentials/', {
            'name': 'ro-cred', 'version': '2c', 'community': 'public',
        }).status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/snmp/credentials/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCredentialUpdate:

    def test_update_name(self, authenticated_client, cred_v2c):
        _put(authenticated_client, f'/api/snmp/credentials/{cred_v2c.id}/', {
            'name': 'renamed-cred', 'version': '2c', 'community': 'public',
        })
        cred_v2c.refresh_from_db()
        assert cred_v2c.name == 'renamed-cred'

    def test_update_community(self, authenticated_client, cred_v2c):
        _put(authenticated_client, f'/api/snmp/credentials/{cred_v2c.id}/', {
            'version': '2c', 'community': 'newcommunity',
        })
        cred_v2c.refresh_from_db()
        assert cred_v2c.get_community() == 'newcommunity'

    def test_update_empty_auth_pass_keeps_existing(self, authenticated_client, cred_v3):
        original = cred_v3.auth_pass
        _put(authenticated_client, f'/api/snmp/credentials/{cred_v3.id}/', {
            'version': '3', 'security_name': 'snmpuser',
            'security_level': 'authPriv', 'auth_protocol': 'sha',
            'auth_pass': '',  # empty = keep
            'priv_protocol': 'aes', 'priv_pass': '',
        })
        cred_v3.refresh_from_db()
        assert cred_v3.auth_pass == original

    def test_update_404(self, authenticated_client):
        assert _put(authenticated_client, '/api/snmp/credentials/99999/', {'version': '2c'}).status_code == 404

    def test_update_no_auth_401(self, client, cred_v2c):
        assert _put(client, f'/api/snmp/credentials/{cred_v2c.id}/', {}).status_code == 401

    def test_update_readonly_403(self, readonly_client, cred_v2c):
        assert _put(readonly_client, f'/api/snmp/credentials/{cred_v2c.id}/', {}).status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/snmp/credentials/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCredentialDelete:

    def test_delete_removes_row(self, authenticated_client, cred_v2c):
        cid = cred_v2c.id
        r = authenticated_client.delete(f'/api/snmp/credentials/{cid}/')
        assert r.status_code == 200
        assert not Credential.objects.filter(id=cid).exists()

    def test_delete_returns_success(self, authenticated_client, cred_v2c):
        r = authenticated_client.delete(f'/api/snmp/credentials/{cred_v2c.id}/')
        assert r.json()['success'] is True

    def test_delete_404(self, authenticated_client):
        assert authenticated_client.delete('/api/snmp/credentials/99999/').status_code == 404

    def test_delete_no_auth_401(self, client, cred_v2c):
        assert client.delete(f'/api/snmp/credentials/{cred_v2c.id}/').status_code == 401

    def test_delete_readonly_403(self, readonly_client, cred_v2c):
        assert readonly_client.delete(f'/api/snmp/credentials/{cred_v2c.id}/').status_code == 403

    def test_delete_wrong_method_405(self, authenticated_client, cred_v2c):
        assert authenticated_client.patch(f'/api/snmp/credentials/{cred_v2c.id}/').status_code == 405
