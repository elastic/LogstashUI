#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for API/policies_views.py — REST policy endpoints."""

import json
import pytest

from django.contrib.auth.models import User
from Management.models import UserProfile
from PipelineManager.models import EnrollmentToken, Policy, Revision


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def readonly_user(db):
    user = User.objects.create_user(username='rouser', password='R0Pass!Secure')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    return user


@pytest.fixture
def readonly_client(client, readonly_user):
    client.login(username='rouser', password='R0Pass!Secure')
    return client


@pytest.fixture
def packaged_policy(db):
    """A non-system PACKAGED policy for CRUD tests."""
    return Policy.objects.create(
        name='test-packaged',
        policy_type=Policy.PolicyType.PACKAGED,
        is_system=False,
        logstash_yml='# default yml',
        jvm_options='-Xms512m',
        log4j2_properties='# log4j2',
    )


@pytest.fixture
def system_policy(db):
    """A system PACKAGED policy (non-deletable, partially immutable)."""
    return Policy.objects.create(
        name='system-packaged',
        policy_type=Policy.PolicyType.PACKAGED,
        is_system=True,
        logstash_yml='# system yml',
        jvm_options='-Xms256m',
        log4j2_properties='# system log4j2',
    )


@pytest.fixture
def managed_policy(db):
    """A non-system MANAGED policy."""
    return Policy.objects.create(
        name='test-managed',
        policy_type=Policy.PolicyType.MANAGED,
        is_system=False,
        logstash_yml='# managed yml',
        jvm_options='-Xms512m',
        log4j2_properties='# managed log4j2',
    )


@pytest.fixture
def enrolled_policy(db, packaged_policy):
    """Policy with a pre-existing enrollment token."""
    EnrollmentToken.objects.create(
        policy=packaged_policy, name='default', token='tok-abc123'
    )
    return packaged_policy


def _post(client, url, body, **h):
    return client.post(url, data=json.dumps(body), content_type='application/json', **h)

def _put(client, url, body, **h):
    return client.put(url, data=json.dumps(body), content_type='application/json', **h)


# ---------------------------------------------------------------------------
# GET /api/policies/  — list
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyList:

    def test_list_200(self, authenticated_client, packaged_policy):
        r = authenticated_client.get('/api/policies/')
        assert r.status_code == 200
        assert r.json()['success'] is True

    def test_list_envelope(self, authenticated_client):
        r = authenticated_client.get('/api/policies/')
        data = r.json()
        assert 'policies' in data
        assert 'total' in data

    def test_list_includes_policy(self, authenticated_client, packaged_policy):
        ids = [p['id'] for p in authenticated_client.get('/api/policies/').json()['policies']]
        assert packaged_policy.id in ids

    def test_list_excludes_embedded(self, authenticated_client, db):
        embedded = Policy.objects.create(
            name='embedded-test', policy_type=Policy.PolicyType.EMBEDDED, is_system=True
        )
        ids = [p['id'] for p in authenticated_client.get('/api/policies/').json()['policies']]
        assert embedded.id not in ids

    def test_list_fields_present(self, authenticated_client, packaged_policy):
        policies = authenticated_client.get('/api/policies/').json()['policies']
        item = next(p for p in policies if p['id'] == packaged_policy.id)
        for field in ('id', 'name', 'policy_type', 'is_system', 'logstash_yml',
                      'jvm_options', 'log4j2_properties', 'current_revision_number',
                      'has_undeployed_changes', 'active_agent_count', 'created_at'):
            assert field in item, f'Missing field: {field}'

    def test_list_no_auth_401(self, client):
        assert client.get('/api/policies/').status_code == 401

    def test_list_readonly_403(self, readonly_client):
        assert readonly_client.get('/api/policies/').status_code == 403

    def test_list_wrong_method_405(self, authenticated_client):
        assert authenticated_client.patch('/api/policies/').status_code == 405


# ---------------------------------------------------------------------------
# POST /api/policies/  — create
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyCreate:

    def test_create_packaged_201(self, authenticated_client):
        r = _post(authenticated_client, '/api/policies/', {'name': 'new-p', 'policy_type': 'PACKAGED'})
        assert r.status_code == 201
        assert r.json()['success'] is True
        assert 'id' in r.json()

    def test_create_persists(self, authenticated_client):
        _post(authenticated_client, '/api/policies/', {'name': 'persist-p', 'policy_type': 'PACKAGED'})
        assert Policy.objects.filter(name='persist-p').exists()

    def test_create_mints_enrollment_token(self, authenticated_client):
        r = _post(authenticated_client, '/api/policies/', {'name': 'token-p', 'policy_type': 'PACKAGED'})
        policy_id = r.json()['id']
        assert EnrollmentToken.objects.filter(policy_id=policy_id, name='default').exists()

    def test_create_managed(self, authenticated_client):
        r = _post(authenticated_client, '/api/policies/', {'name': 'managed-p', 'policy_type': 'MANAGED'})
        assert r.status_code == 201
        assert Policy.objects.get(name='managed-p').policy_type == Policy.PolicyType.MANAGED

    def test_create_simulate(self, authenticated_client):
        r = _post(authenticated_client, '/api/policies/', {'name': 'sim-p', 'policy_type': 'SIMULATE'})
        assert r.status_code == 201

    def test_create_uses_default_configs_when_omitted(self, authenticated_client):
        _post(authenticated_client, '/api/policies/', {'name': 'defaults-p', 'policy_type': 'PACKAGED'})
        p = Policy.objects.get(name='defaults-p')
        assert len(p.logstash_yml) > 0
        assert len(p.jvm_options) > 0

    def test_create_accepts_custom_configs(self, authenticated_client):
        _post(authenticated_client, '/api/policies/', {
            'name': 'custom-cfg', 'policy_type': 'PACKAGED',
            'logstash_yml': 'pipeline.workers: 2\n',
            'jvm_options': '-Xms1g\n',
        })
        p = Policy.objects.get(name='custom-cfg')
        assert 'pipeline.workers' in p.logstash_yml
        assert '1g' in p.jvm_options

    def test_create_missing_name_400(self, authenticated_client):
        r = _post(authenticated_client, '/api/policies/', {'policy_type': 'PACKAGED'})
        assert r.status_code == 400

    def test_create_invalid_type_400(self, authenticated_client):
        r = _post(authenticated_client, '/api/policies/', {'name': 'bad-type', 'policy_type': 'EMBEDDED'})
        assert r.status_code == 400

    def test_create_duplicate_name_409(self, authenticated_client, packaged_policy):
        r = _post(authenticated_client, '/api/policies/', {'name': packaged_policy.name, 'policy_type': 'PACKAGED'})
        assert r.status_code == 409

    def test_create_no_auth_401(self, client):
        r = _post(client, '/api/policies/', {'name': 'no-auth', 'policy_type': 'PACKAGED'})
        assert r.status_code == 401

    def test_create_readonly_403(self, readonly_client):
        r = _post(readonly_client, '/api/policies/', {'name': 'ro', 'policy_type': 'PACKAGED'})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/policies/{id}/  — read
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyGet:

    def test_get_200(self, authenticated_client, packaged_policy):
        r = authenticated_client.get(f'/api/policies/{packaged_policy.id}/')
        assert r.status_code == 200
        assert r.json()['policy']['id'] == packaged_policy.id

    def test_get_full_fields(self, authenticated_client, packaged_policy):
        p = authenticated_client.get(f'/api/policies/{packaged_policy.id}/').json()['policy']
        for f in ('logstash_yml', 'jvm_options', 'log4j2_properties', 'settings_path',
                  'policy_type', 'is_system', 'current_revision_number', 'has_undeployed_changes'):
            assert f in p, f'Missing: {f}'

    def test_get_no_sensitive_fields(self, authenticated_client, packaged_policy):
        p = authenticated_client.get(f'/api/policies/{packaged_policy.id}/').json()['policy']
        assert 'keystore_password' not in p
        assert 'keystore_password_hash' not in p

    def test_get_404(self, authenticated_client):
        assert authenticated_client.get('/api/policies/99999/').status_code == 404

    def test_get_no_auth_401(self, client, packaged_policy):
        assert client.get(f'/api/policies/{packaged_policy.id}/').status_code == 401

    def test_get_readonly_403(self, readonly_client, packaged_policy):
        assert readonly_client.get(f'/api/policies/{packaged_policy.id}/').status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/policies/{id}/  — update
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyUpdate:

    def test_update_jvm_options(self, authenticated_client, packaged_policy):
        _put(authenticated_client, f'/api/policies/{packaged_policy.id}/', {'jvm_options': '-Xms2g\n'})
        packaged_policy.refresh_from_db()
        assert '-Xms2g' in packaged_policy.jvm_options

    def test_update_logstash_yml(self, authenticated_client, packaged_policy):
        _put(authenticated_client, f'/api/policies/{packaged_policy.id}/', {'logstash_yml': 'pipeline.workers: 8\n'})
        packaged_policy.refresh_from_db()
        assert 'pipeline.workers' in packaged_policy.logstash_yml

    def test_update_log4j2(self, authenticated_client, packaged_policy):
        _put(authenticated_client, f'/api/policies/{packaged_policy.id}/', {'log4j2_properties': '# custom log4j2\n'})
        packaged_policy.refresh_from_db()
        assert 'custom' in packaged_policy.log4j2_properties

    def test_update_cannot_change_type(self, authenticated_client, packaged_policy):
        # Bug 6 fix: changed from 403 (permission) to 400 (validation error)
        # since this is a bad-request constraint, not an authorisation failure.
        r = _put(authenticated_client, f'/api/policies/{packaged_policy.id}/', {'policy_type': 'MANAGED'})
        assert r.status_code == 400

    def test_update_embedded_403(self, authenticated_client, db):
        embedded = Policy.objects.create(
            name='emb', policy_type=Policy.PolicyType.EMBEDDED, is_system=True
        )
        r = _put(authenticated_client, f'/api/policies/{embedded.id}/', {'jvm_options': '-Xms1g'})
        assert r.status_code == 403

    def test_update_system_simulate_path_locked(self, authenticated_client, db):
        sys_sim = Policy.objects.create(
            name='sys-sim', policy_type=Policy.PolicyType.SIMULATE, is_system=True,
            settings_path='/etc/logstash/',
        )
        _put(authenticated_client, f'/api/policies/{sys_sim.id}/', {
            'settings_path': '/changed/path/', 'jvm_options': '-Xms2g'
        })
        sys_sim.refresh_from_db()
        # path-locked: settings_path should NOT change; jvm_options SHOULD
        assert '/changed/path/' not in sys_sim.settings_path
        assert '-Xms2g' in sys_sim.jvm_options

    def test_update_404(self, authenticated_client):
        r = _put(authenticated_client, '/api/policies/99999/', {'jvm_options': '-Xms1g'})
        assert r.status_code == 404

    def test_update_no_auth_401(self, client, packaged_policy):
        assert _put(client, f'/api/policies/{packaged_policy.id}/', {}).status_code == 401

    def test_update_readonly_403(self, readonly_client, packaged_policy):
        assert _put(readonly_client, f'/api/policies/{packaged_policy.id}/', {}).status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/policies/{id}/  — delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyDelete:

    def test_delete_200(self, authenticated_client, packaged_policy):
        r = authenticated_client.delete(f'/api/policies/{packaged_policy.id}/')
        assert r.status_code == 200
        assert not Policy.objects.filter(id=packaged_policy.id).exists()

    def test_delete_system_403(self, authenticated_client, system_policy):
        r = authenticated_client.delete(f'/api/policies/{system_policy.id}/')
        assert r.status_code == 403
        assert Policy.objects.filter(id=system_policy.id).exists()

    def test_delete_with_connection_400(self, authenticated_client, packaged_policy, db):
        from PipelineManager.models import Connection
        Connection.objects.create(
            name='conn-for-policy', connection_type='AGENT',
            policy=packaged_policy, host='192.168.1.1', port=22,
        )
        r = authenticated_client.delete(f'/api/policies/{packaged_policy.id}/')
        assert r.status_code == 400

    def test_delete_404(self, authenticated_client):
        assert authenticated_client.delete('/api/policies/99999/').status_code == 404

    def test_delete_no_auth_401(self, client, packaged_policy):
        assert client.delete(f'/api/policies/{packaged_policy.id}/').status_code == 401

    def test_delete_readonly_403(self, readonly_client, packaged_policy):
        assert readonly_client.delete(f'/api/policies/{packaged_policy.id}/').status_code == 403

    def test_delete_wrong_method_405(self, authenticated_client, packaged_policy):
        assert authenticated_client.patch(f'/api/policies/{packaged_policy.id}/').status_code == 405


# ---------------------------------------------------------------------------
# POST /api/policies/{id}/deploy/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyDeploy:

    def test_deploy_200(self, authenticated_client, packaged_policy):
        r = authenticated_client.post(f'/api/policies/{packaged_policy.id}/deploy/')
        assert r.status_code == 200
        assert r.json()['success'] is True

    def test_deploy_increments_revision(self, authenticated_client, packaged_policy):
        before = packaged_policy.current_revision_number
        authenticated_client.post(f'/api/policies/{packaged_policy.id}/deploy/')
        packaged_policy.refresh_from_db()
        assert packaged_policy.current_revision_number == before + 1

    def test_deploy_creates_revision_row(self, authenticated_client, packaged_policy):
        authenticated_client.post(f'/api/policies/{packaged_policy.id}/deploy/')
        assert Revision.objects.filter(policy=packaged_policy).exists()

    def test_deploy_sets_last_deployed_at(self, authenticated_client, packaged_policy):
        assert packaged_policy.last_deployed_at is None
        authenticated_client.post(f'/api/policies/{packaged_policy.id}/deploy/')
        packaged_policy.refresh_from_db()
        assert packaged_policy.last_deployed_at is not None

    def test_deploy_snapshot_contains_config(self, authenticated_client, packaged_policy):
        authenticated_client.post(f'/api/policies/{packaged_policy.id}/deploy/')
        rev = Revision.objects.get(policy=packaged_policy)
        assert 'logstash_yml' in rev.snapshot_json
        assert 'pipelines' in rev.snapshot_json

    def test_deploy_multiple_increments_sequentially(self, authenticated_client, packaged_policy):
        authenticated_client.post(f'/api/policies/{packaged_policy.id}/deploy/')
        authenticated_client.post(f'/api/policies/{packaged_policy.id}/deploy/')
        packaged_policy.refresh_from_db()
        assert packaged_policy.current_revision_number == 2
        assert Revision.objects.filter(policy=packaged_policy).count() == 2

    def test_deploy_404(self, authenticated_client):
        assert authenticated_client.post('/api/policies/99999/deploy/').status_code == 404

    def test_deploy_no_auth_401(self, client, packaged_policy):
        assert client.post(f'/api/policies/{packaged_policy.id}/deploy/').status_code == 401

    def test_deploy_readonly_403(self, readonly_client, packaged_policy):
        assert readonly_client.post(f'/api/policies/{packaged_policy.id}/deploy/').status_code == 403

    def test_deploy_get_405(self, authenticated_client, packaged_policy):
        assert authenticated_client.get(f'/api/policies/{packaged_policy.id}/deploy/').status_code == 405


# ---------------------------------------------------------------------------
# POST /api/policies/{id}/clone/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyClone:

    def test_clone_201(self, authenticated_client, packaged_policy):
        r = _post(authenticated_client, f'/api/policies/{packaged_policy.id}/clone/', {'new_name': 'cloned-p'})
        assert r.status_code == 201
        assert Policy.objects.filter(name='cloned-p').exists()

    def test_clone_sets_cloned_from(self, authenticated_client, packaged_policy):
        _post(authenticated_client, f'/api/policies/{packaged_policy.id}/clone/', {'new_name': 'clone2'})
        clone = Policy.objects.get(name='clone2')
        assert clone.cloned_from_id == packaged_policy.id

    def test_clone_packaged_becomes_managed(self, authenticated_client, packaged_policy):
        _post(authenticated_client, f'/api/policies/{packaged_policy.id}/clone/', {'new_name': 'clone-managed'})
        clone = Policy.objects.get(name='clone-managed')
        assert clone.policy_type == Policy.PolicyType.MANAGED

    def test_clone_mints_enrollment_token(self, authenticated_client, packaged_policy):
        r = _post(authenticated_client, f'/api/policies/{packaged_policy.id}/clone/', {'new_name': 'clone-tok'})
        clone_id = r.json()['id']
        assert EnrollmentToken.objects.filter(policy_id=clone_id).exists()

    def test_clone_not_system(self, authenticated_client, packaged_policy):
        _post(authenticated_client, f'/api/policies/{packaged_policy.id}/clone/', {'new_name': 'clone-notsys'})
        clone = Policy.objects.get(name='clone-notsys')
        assert clone.is_system is False

    def test_clone_embedded_403(self, authenticated_client, db):
        embedded = Policy.objects.create(
            name='emb-src', policy_type=Policy.PolicyType.EMBEDDED, is_system=True
        )
        r = _post(authenticated_client, f'/api/policies/{embedded.id}/clone/', {'new_name': 'emb-clone'})
        assert r.status_code == 403

    def test_clone_missing_new_name_400(self, authenticated_client, packaged_policy):
        r = _post(authenticated_client, f'/api/policies/{packaged_policy.id}/clone/', {})
        assert r.status_code == 400

    def test_clone_duplicate_name_409(self, authenticated_client, packaged_policy, managed_policy):
        r = _post(authenticated_client, f'/api/policies/{packaged_policy.id}/clone/', {'new_name': managed_policy.name})
        assert r.status_code == 409

    def test_clone_404(self, authenticated_client):
        r = _post(authenticated_client, '/api/policies/99999/clone/', {'new_name': 'ghost'})
        assert r.status_code == 404

    def test_clone_no_auth_401(self, client, packaged_policy):
        r = _post(client, f'/api/policies/{packaged_policy.id}/clone/', {'new_name': 'x'})
        assert r.status_code == 401

    def test_clone_readonly_403(self, readonly_client, packaged_policy):
        r = _post(readonly_client, f'/api/policies/{packaged_policy.id}/clone/', {'new_name': 'x'})
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/policies/{id}/diff/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyDiff:

    def test_diff_200(self, authenticated_client, packaged_policy):
        r = authenticated_client.get(f'/api/policies/{packaged_policy.id}/diff/')
        assert r.status_code == 200

    def test_diff_envelope(self, authenticated_client, packaged_policy):
        d = authenticated_client.get(f'/api/policies/{packaged_policy.id}/diff/').json()
        for key in ('current', 'previous', 'current_revision', 'last_deployed_revision',
                    'pending_changes', 'has_undeployed_changes', 'policy_name'):
            assert key in d, f'Missing: {key}'

    def test_diff_no_revisions_previous_empty(self, authenticated_client, packaged_policy):
        d = authenticated_client.get(f'/api/policies/{packaged_policy.id}/diff/').json()
        assert d['last_deployed_revision'] == 0
        assert d['previous']['logstash_yml'] == ''

    def test_diff_after_deploy_previous_matches_snapshot(self, authenticated_client, packaged_policy):
        authenticated_client.post(f'/api/policies/{packaged_policy.id}/deploy/')
        d = authenticated_client.get(f'/api/policies/{packaged_policy.id}/diff/').json()
        assert d['last_deployed_revision'] == 1
        assert d['previous']['logstash_yml'] == packaged_policy.logstash_yml

    def test_diff_404(self, authenticated_client):
        assert authenticated_client.get('/api/policies/99999/diff/').status_code == 404

    def test_diff_no_auth_401(self, client, packaged_policy):
        assert client.get(f'/api/policies/{packaged_policy.id}/diff/').status_code == 401

    def test_diff_post_405(self, authenticated_client, packaged_policy):
        assert authenticated_client.post(f'/api/policies/{packaged_policy.id}/diff/').status_code == 405


# ---------------------------------------------------------------------------
# Enrollment token endpoints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyTokens:

    def test_list_tokens_200(self, authenticated_client, enrolled_policy):
        r = authenticated_client.get(f'/api/policies/{enrolled_policy.id}/tokens/')
        assert r.status_code == 200
        assert len(r.json()['tokens']) == 1

    def test_list_tokens_includes_enroll_command(self, authenticated_client, enrolled_policy):
        tokens = authenticated_client.get(f'/api/policies/{enrolled_policy.id}/tokens/').json()['tokens']
        assert 'enroll_command' in tokens[0]
        assert 'encoded_token' in tokens[0]

    def test_create_token_201(self, authenticated_client, packaged_policy):
        r = _post(authenticated_client, f'/api/policies/{packaged_policy.id}/tokens/', {'name': 'prod'})
        assert r.status_code == 201
        assert EnrollmentToken.objects.filter(policy=packaged_policy, name='prod').exists()

    def test_create_token_default_name(self, authenticated_client, packaged_policy):
        _post(authenticated_client, f'/api/policies/{packaged_policy.id}/tokens/', {})
        assert EnrollmentToken.objects.filter(policy=packaged_policy, name='default').exists()

    def test_delete_token_200(self, authenticated_client, enrolled_policy):
        token = EnrollmentToken.objects.get(policy=enrolled_policy)
        r = authenticated_client.delete(f'/api/policies/{enrolled_policy.id}/tokens/{token.id}/')
        assert r.status_code == 200
        assert not EnrollmentToken.objects.filter(id=token.id).exists()

    def test_delete_token_404(self, authenticated_client, packaged_policy):
        r = authenticated_client.delete(f'/api/policies/{packaged_policy.id}/tokens/99999/')
        assert r.status_code == 404

    def test_tokens_policy_404(self, authenticated_client):
        assert authenticated_client.get('/api/policies/99999/tokens/').status_code == 404

    def test_tokens_no_auth_401(self, client, packaged_policy):
        assert client.get(f'/api/policies/{packaged_policy.id}/tokens/').status_code == 401

    def test_tokens_readonly_403(self, readonly_client, packaged_policy):
        assert readonly_client.get(f'/api/policies/{packaged_policy.id}/tokens/').status_code == 403
