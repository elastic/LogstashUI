#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for REST SNMP device template endpoints — /api/snmp/templates/."""

import json
import pytest

from django.contrib.auth.models import User
from Management.models import UserProfile
from SNMP.models import DeviceTemplate, Profile


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

SAMPLE_PROFILE_DATA = {'get': {'system.name': '1.3.6.1.2.1.1.5.0'}, 'walk': [], 'table': {}}


@pytest.fixture
def profile(db):
    return Profile.objects.create(
        name='tmpl_test_profile', vendor='Acme',
        profile_data=SAMPLE_PROFILE_DATA, normalizers=[],
    )


@pytest.fixture
def template(db, profile):
    t = DeviceTemplate.objects.create(
        name='test_template', vendor='Acme', model='Switch-X',
        description='Test template', matching_rules=['Acme Switch'], official=False,
    )
    t.profiles.add(profile)
    return t


@pytest.fixture
def official_template(db):
    return DeviceTemplate.objects.create(
        name='official_template', vendor='OfficialCo',
        official=True, official_key='official_template',
    )


@pytest.fixture
def readonly_user(db):
    user = User.objects.create_user(username='rotmpl', password='Readonly1!')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    return user


@pytest.fixture
def readonly_client(client, readonly_user):
    client.login(username='rotmpl', password='Readonly1!')
    return client


# ---------------------------------------------------------------------------
# GET /api/snmp/templates/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTemplateList:

    def test_list_200(self, authenticated_client, template):
        assert authenticated_client.get('/api/snmp/templates/').status_code == 200

    def test_list_envelope(self, authenticated_client, template):
        data = authenticated_client.get('/api/snmp/templates/').json()
        assert 'templates' in data and 'total' in data

    def test_list_includes_template(self, authenticated_client, template):
        ids = [t['id'] for t in authenticated_client.get('/api/snmp/templates/').json()['templates']]
        assert template.id in ids

    def test_list_expected_fields(self, authenticated_client, template):
        tmpl_list = authenticated_client.get('/api/snmp/templates/').json()['templates']
        t = next(x for x in tmpl_list if x['id'] == template.id)
        for f in ('id', 'name', 'vendor', 'model', 'product', 'type', 'official', 'description'):
            assert f in t, f'Missing: {f}'

    def test_list_no_profiles_in_list(self, authenticated_client, template):
        tmpl_list = authenticated_client.get('/api/snmp/templates/').json()['templates']
        t = next(x for x in tmpl_list if x['id'] == template.id)
        assert 'profiles' not in t  # profiles only in detail

    def test_list_no_auth_401(self, client):
        assert client.get('/api/snmp/templates/').status_code == 401

    def test_list_search_filter(self, authenticated_client, template):
        data = authenticated_client.get(f'/api/snmp/templates/?search={template.name}').json()
        assert any(t['id'] == template.id for t in data['templates'])

    def test_list_official_true_filter(self, authenticated_client, template, official_template):
        data = authenticated_client.get('/api/snmp/templates/?official=true').json()
        assert all(t['official'] for t in data['templates'])

    def test_list_official_false_filter(self, authenticated_client, template, official_template):
        data = authenticated_client.get('/api/snmp/templates/?official=false').json()
        assert all(not t['official'] for t in data['templates'])

    def test_list_wrong_method_405(self, authenticated_client):
        assert authenticated_client.patch('/api/snmp/templates/').status_code == 405


# ---------------------------------------------------------------------------
# GET /api/snmp/templates/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTemplateGet:

    def test_get_200(self, authenticated_client, template):
        r = authenticated_client.get(f'/api/snmp/templates/{template.id}/')
        assert r.status_code == 200
        assert r.json()['template']['id'] == template.id

    def test_get_includes_profiles(self, authenticated_client, template, profile):
        d = authenticated_client.get(f'/api/snmp/templates/{template.id}/').json()['template']
        assert 'profiles' in d
        assert any(p['id'] == profile.id for p in d['profiles'])

    def test_get_full_fields(self, authenticated_client, template):
        d = authenticated_client.get(f'/api/snmp/templates/{template.id}/').json()['template']
        for f in ('matching_rules', 'description', 'updated_at', 'created_at'):
            assert f in d, f'Missing: {f}'

    def test_get_404(self, authenticated_client):
        assert authenticated_client.get('/api/snmp/templates/99999/').status_code == 404

    def test_get_no_auth_401(self, client, template):
        assert client.get(f'/api/snmp/templates/{template.id}/').status_code == 401

    def test_get_readonly_allowed(self, readonly_client, template):
        assert readonly_client.get(f'/api/snmp/templates/{template.id}/').status_code == 200


# ---------------------------------------------------------------------------
# POST /api/snmp/templates/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTemplateCreate:

    def test_create_201(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/templates/', {
            'name': 'new_template', 'vendor': 'Acme',
        })
        assert r.status_code == 201
        assert r.json()['success'] is True

    def test_create_with_profiles(self, authenticated_client, profile):
        r = _post(authenticated_client, '/api/snmp/templates/', {
            'name': 'with_profiles', 'vendor': 'Acme', 'profiles': [profile.id],
        })
        assert r.status_code == 201
        t = DeviceTemplate.objects.get(name='with_profiles')
        assert profile in t.profiles.all()

    def test_create_with_matching_rules(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/templates/', {
            'name': 'with_rules', 'vendor': 'Acme',
            'matching_rules': ['Acme Switch', 'ACME-SW'],
        })
        assert r.status_code == 201
        t = DeviceTemplate.objects.get(name='with_rules')
        assert 'Acme Switch' in t.matching_rules

    def test_create_persists(self, authenticated_client):
        _post(authenticated_client, '/api/snmp/templates/', {'name': 'persist_tmpl', 'vendor': 'X'})
        assert DeviceTemplate.objects.filter(name='persist_tmpl').exists()

    def test_create_always_non_official(self, authenticated_client):
        _post(authenticated_client, '/api/snmp/templates/', {'name': 'user_tmpl', 'vendor': 'X'})
        assert DeviceTemplate.objects.get(name='user_tmpl').official is False

    def test_create_missing_name_400(self, authenticated_client):
        assert _post(authenticated_client, '/api/snmp/templates/', {'vendor': 'X'}).status_code == 400

    def test_create_missing_vendor_400(self, authenticated_client):
        assert _post(authenticated_client, '/api/snmp/templates/', {'name': 'no_vendor'}).status_code == 400

    def test_create_missing_profile_skipped(self, authenticated_client):
        r = _post(authenticated_client, '/api/snmp/templates/', {
            'name': 'skip_tmpl', 'vendor': 'X', 'profiles': [99999],
        })
        assert r.status_code == 201
        assert 'skipped_profiles' in r.json()

    def test_create_no_auth_401(self, client):
        assert _post(client, '/api/snmp/templates/', {'name': 'x', 'vendor': 'y'}).status_code == 401

    def test_create_readonly_403(self, readonly_client):
        assert _post(readonly_client, '/api/snmp/templates/', {
            'name': 'ro_tmpl', 'vendor': 'X',
        }).status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/snmp/templates/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTemplateUpdate:

    def test_update_description(self, authenticated_client, template):
        _put(authenticated_client, f'/api/snmp/templates/{template.id}/', {'description': 'new desc'})
        template.refresh_from_db()
        assert template.description == 'new desc'

    def test_update_matching_rules(self, authenticated_client, template):
        _put(authenticated_client, f'/api/snmp/templates/{template.id}/', {
            'matching_rules': ['Rule A', 'Rule B'],
        })
        template.refresh_from_db()
        assert template.matching_rules == ['Rule A', 'Rule B']

    def test_update_profiles_replaced(self, authenticated_client, template, profile):
        new_profile = Profile.objects.create(
            name='new_profile_for_update', vendor='Beta',
            profile_data=SAMPLE_PROFILE_DATA, normalizers=[],
        )
        _put(authenticated_client, f'/api/snmp/templates/{template.id}/', {
            'profiles': [new_profile.id],
        })
        assert list(template.profiles.values_list('id', flat=True)) == [new_profile.id]

    def test_update_official_template_403(self, authenticated_client, official_template):
        r = _put(authenticated_client, f'/api/snmp/templates/{official_template.id}/', {
            'description': 'trying to edit official',
        })
        assert r.status_code == 403

    def test_update_404(self, authenticated_client):
        assert _put(authenticated_client, '/api/snmp/templates/99999/', {}).status_code == 404

    def test_update_no_auth_401(self, client, template):
        assert _put(client, f'/api/snmp/templates/{template.id}/', {}).status_code == 401

    def test_update_readonly_403(self, readonly_client, template):
        assert _put(readonly_client, f'/api/snmp/templates/{template.id}/', {}).status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/snmp/templates/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTemplateDelete:

    def test_delete_removes_row(self, authenticated_client, template):
        tid = template.id
        r = authenticated_client.delete(f'/api/snmp/templates/{tid}/')
        assert r.status_code == 200
        assert not DeviceTemplate.objects.filter(id=tid).exists()

    def test_delete_official_403(self, authenticated_client, official_template):
        r = authenticated_client.delete(f'/api/snmp/templates/{official_template.id}/')
        assert r.status_code == 403
        assert DeviceTemplate.objects.filter(id=official_template.id).exists()

    def test_delete_returns_success(self, authenticated_client, template):
        assert authenticated_client.delete(f'/api/snmp/templates/{template.id}/').json()['success'] is True

    def test_delete_404(self, authenticated_client):
        assert authenticated_client.delete('/api/snmp/templates/99999/').status_code == 404

    def test_delete_no_auth_401(self, client, template):
        assert client.delete(f'/api/snmp/templates/{template.id}/').status_code == 401

    def test_delete_readonly_403(self, readonly_client, template):
        assert readonly_client.delete(f'/api/snmp/templates/{template.id}/').status_code == 403

    def test_delete_wrong_method_405(self, authenticated_client, template):
        assert authenticated_client.patch(f'/api/snmp/templates/{template.id}/').status_code == 405
