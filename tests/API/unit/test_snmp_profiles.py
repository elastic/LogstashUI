#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for REST SNMP profile endpoints — /api/snmp/profiles/."""

import json
import pytest

from django.contrib.auth.models import User
from Management.models import UserProfile
from SNMP.models import Profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_PROFILE_DATA = {
    'get': {'system.name': '1.3.6.1.2.1.1.5.0'},
    'walk': [],
    'table': {},
}


def _post(client, url, body, **kw):
    return client.post(url, data=json.dumps(body), content_type='application/json', **kw)


def _put(client, url, body, **kw):
    return client.put(url, data=json.dumps(body), content_type='application/json', **kw)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def profile(db):
    return Profile.objects.create(
        name='test_profile', vendor='Acme', product='Switch X',
        description='Test profile', profile_data=SAMPLE_PROFILE_DATA, normalizers=[],
    )


@pytest.fixture
def official_profile(db):
    """Simulate an official profile (name ends with .json)."""
    return Profile.objects.create(
        name='official_thing.json', vendor='Official',
        profile_data=SAMPLE_PROFILE_DATA, normalizers=[],
    )


@pytest.fixture
def readonly_user(db):
    user = User.objects.create_user(username='roprofile', password='Readonly1!')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    return user


@pytest.fixture
def readonly_client(client, readonly_user):
    client.login(username='roprofile', password='Readonly1!')
    return client


# ---------------------------------------------------------------------------
# GET /api/snmp/profiles/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProfileList:

    def test_list_200(self, authenticated_client, profile):
        assert authenticated_client.get('/api/snmp/profiles/').status_code == 200

    def test_list_envelope(self, authenticated_client, profile):
        data = authenticated_client.get('/api/snmp/profiles/').json()
        assert 'profiles' in data and 'total' in data

    def test_list_includes_profile(self, authenticated_client, profile):
        ids = [p['id'] for p in authenticated_client.get('/api/snmp/profiles/').json()['profiles']]
        assert profile.id in ids

    def test_list_expected_fields(self, authenticated_client, profile):
        profiles = authenticated_client.get('/api/snmp/profiles/').json()['profiles']
        p = next(x for x in profiles if x['id'] == profile.id)
        for f in ('id', 'name', 'vendor', 'product', 'description', 'is_official', 'created_at'):
            assert f in p, f'Missing field: {f}'

    def test_list_no_profile_data_in_list(self, authenticated_client, profile):
        profiles = authenticated_client.get('/api/snmp/profiles/').json()['profiles']
        p = next(x for x in profiles if x['id'] == profile.id)
        assert 'profile_data' not in p  # heavy field only in detail

    def test_list_no_auth_401(self, client):
        assert client.get('/api/snmp/profiles/').status_code == 401

    def test_list_search_filter(self, authenticated_client, profile):
        data = authenticated_client.get(f'/api/snmp/profiles/?search={profile.name}').json()
        assert any(p['id'] == profile.id for p in data['profiles'])

    def test_list_official_filter_true(self, authenticated_client, profile, official_profile):
        data = authenticated_client.get('/api/snmp/profiles/?official=true').json()
        assert all(p['is_official'] for p in data['profiles'])

    def test_list_official_filter_false(self, authenticated_client, profile, official_profile):
        data = authenticated_client.get('/api/snmp/profiles/?official=false').json()
        assert all(not p['is_official'] for p in data['profiles'])

    def test_list_wrong_method_405(self, authenticated_client):
        assert authenticated_client.patch('/api/snmp/profiles/').status_code == 405


# ---------------------------------------------------------------------------
# GET /api/snmp/profiles/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProfileGet:

    def test_get_200(self, authenticated_client, profile):
        r = authenticated_client.get(f'/api/snmp/profiles/{profile.id}/')
        assert r.status_code == 200
        assert r.json()['profile']['id'] == profile.id

    def test_get_includes_profile_data(self, authenticated_client, profile):
        d = authenticated_client.get(f'/api/snmp/profiles/{profile.id}/').json()['profile']
        assert 'profile_data' in d
        assert 'normalizers' in d
        assert 'updated_at' in d

    def test_get_is_official_false(self, authenticated_client, profile):
        assert authenticated_client.get(f'/api/snmp/profiles/{profile.id}/').json()['profile']['is_official'] is False

    def test_get_is_official_true(self, authenticated_client, official_profile):
        assert authenticated_client.get(f'/api/snmp/profiles/{official_profile.id}/').json()['profile']['is_official'] is True

    def test_get_404(self, authenticated_client):
        assert authenticated_client.get('/api/snmp/profiles/99999/').status_code == 404

    def test_get_no_auth_401(self, client, profile):
        assert client.get(f'/api/snmp/profiles/{profile.id}/').status_code == 401

    def test_get_readonly_allowed(self, readonly_client, profile):
        assert readonly_client.get(f'/api/snmp/profiles/{profile.id}/').status_code == 200


# ---------------------------------------------------------------------------
# POST /api/snmp/profiles/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProfileCreate:

    def test_create_201(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/profiles/', {
            'name': 'new_profile', 'vendor': 'Acme',
            'profile_data': SAMPLE_PROFILE_DATA,
        })
        assert r.status_code == 201
        assert r.json()['success'] is True

    def test_create_persists(self, authenticated_client):
        _post(authenticated_client, '/api/snmp/profiles/', {
            'name': 'persist_profile', 'vendor': 'Acme',
            'profile_data': SAMPLE_PROFILE_DATA,
        })
        assert Profile.objects.filter(name='persist_profile').exists()

    def test_create_missing_name_400(self, authenticated_client):
        assert _post(authenticated_client, '/api/snmp/profiles/', {'vendor': 'Acme'}).status_code == 400

    def test_create_missing_vendor_400(self, authenticated_client):
        assert _post(authenticated_client, '/api/snmp/profiles/', {'name': 'no-vendor'}).status_code == 400

    def test_create_duplicate_name_409(self, authenticated_client, profile):
        # H7/M7 fix: duplicate profile now returns 409 Conflict, not 400.
        r = _post(authenticated_client, '/api/snmp/profiles/', {
            'name': profile.name, 'vendor': 'Acme', 'profile_data': {},
        })
        assert r.status_code == 409

    def test_create_no_auth_401(self, client):
        assert _post(client, '/api/snmp/profiles/', {'name': 'x', 'vendor': 'y'}).status_code == 401

    def test_create_readonly_403(self, readonly_client):
        assert _post(readonly_client, '/api/snmp/profiles/', {
            'name': 'ro_profile', 'vendor': 'Acme',
        }).status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/snmp/profiles/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProfileUpdate:

    def test_update_description(self, authenticated_client, profile):
        _put(authenticated_client, f'/api/snmp/profiles/{profile.id}/', {'description': 'updated'})
        profile.refresh_from_db()
        assert profile.description == 'updated'

    def test_update_profile_data(self, authenticated_client, profile):
        new_data = {'get': {'sys.uptime': '1.3.6.1.2.1.1.3.0'}, 'walk': [], 'table': {}}
        _put(authenticated_client, f'/api/snmp/profiles/{profile.id}/', {'profile_data': new_data})
        profile.refresh_from_db()
        assert profile.profile_data == new_data

    def test_update_rename(self, authenticated_client, profile):
        _put(authenticated_client, f'/api/snmp/profiles/{profile.id}/', {'name': 'renamed_profile'})
        profile.refresh_from_db()
        assert profile.name == 'renamed_profile'

    def test_update_rename_conflict_400(self, authenticated_client, profile, official_profile):
        r = _put(authenticated_client, f'/api/snmp/profiles/{profile.id}/', {
            'name': official_profile.name,
        })
        assert r.status_code == 400

    def test_update_404(self, authenticated_client):
        assert _put(authenticated_client, '/api/snmp/profiles/99999/', {}).status_code == 404

    def test_update_no_auth_401(self, client, profile):
        assert _put(client, f'/api/snmp/profiles/{profile.id}/', {}).status_code == 401

    def test_update_readonly_403(self, readonly_client, profile):
        assert _put(readonly_client, f'/api/snmp/profiles/{profile.id}/', {}).status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/snmp/profiles/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProfileDelete:

    def test_delete_removes_row(self, authenticated_client, profile):
        pid = profile.id
        assert authenticated_client.delete(f'/api/snmp/profiles/{pid}/').status_code == 200
        assert not Profile.objects.filter(id=pid).exists()

    def test_delete_non_json_profile_200(self, authenticated_client, db):
        # Bug 3 fix: only profiles whose name ends in '.json' are protected as
        # "official".  A profile named 'system' (no .json suffix) is a user
        # profile and must be deletable.  The companion test
        # test_delete_generic_system_json_403 covers the .json protection path.
        sys_profile = Profile.objects.create(
            name='system', vendor='System', profile_data=SAMPLE_PROFILE_DATA, normalizers=[],
        )
        assert authenticated_client.delete(f'/api/snmp/profiles/{sys_profile.id}/').status_code == 200

    def test_delete_generic_system_json_403(self, authenticated_client, db):
        p = Profile.objects.create(
            name='generic_system.json', vendor='System',
            profile_data=SAMPLE_PROFILE_DATA, normalizers=[],
        )
        assert authenticated_client.delete(f'/api/snmp/profiles/{p.id}/').status_code == 403

    def test_delete_404(self, authenticated_client):
        assert authenticated_client.delete('/api/snmp/profiles/99999/').status_code == 404

    def test_delete_no_auth_401(self, client, profile):
        assert client.delete(f'/api/snmp/profiles/{profile.id}/').status_code == 401

    def test_delete_readonly_403(self, readonly_client, profile):
        assert readonly_client.delete(f'/api/snmp/profiles/{profile.id}/').status_code == 403

    def test_delete_wrong_method_405(self, authenticated_client, profile):
        assert authenticated_client.patch(f'/api/snmp/profiles/{profile.id}/').status_code == 405
