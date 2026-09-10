#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for API/security_views.py — bootstrap, me, users, and API keys."""

import json
import pytest
import re

from django.contrib.auth.models import User
from Management.models import UserProfile
from PipelineManager.models import ApiKey


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post(client, url, body, **headers):
    return client.post(url, data=json.dumps(body), content_type='application/json', **headers)


def _put(client, url, body, **headers):
    return client.put(url, data=json.dumps(body), content_type='application/json', **headers)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_key_header(test_user):
    """Authorization header dict for the shared admin test_user."""
    _token, raw = ApiKey.issue_for_user(test_user, name='test-key')
    return {'HTTP_AUTHORIZATION': f'ApiKey {raw}'}


@pytest.fixture
def readonly_user(db):
    user = User.objects.create_user(username='rouser', password='Sup3rS3cur3!Pass')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    return user


@pytest.fixture
def readonly_client(client, readonly_user):
    client.login(username='rouser', password='Sup3rS3cur3!Pass')
    return client


# ---------------------------------------------------------------------------
# GET /api/security/bootstrap/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBootstrapGet:

    def test_returns_bootstrapped_true_when_users_exist(self, client, test_user):
        response = client.get('/api/security/bootstrap/')
        assert response.status_code == 200
        assert response.json()['bootstrapped'] is True

    def test_returns_bootstrapped_false_when_no_users(self, client, db):
        User.objects.all().delete()
        response = client.get('/api/security/bootstrap/')
        assert response.status_code == 200
        assert response.json()['bootstrapped'] is False

    def test_no_auth_required(self, client):
        """Bootstrap status must be readable without any credentials."""
        response = client.get('/api/security/bootstrap/')
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/security/bootstrap/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBootstrapPost:

    def test_already_bootstrapped_returns_409(self, client, test_user):
        response = _post(client, '/api/security/bootstrap/', {
            'username': 'newadmin', 'password': 'Sup3rS3cur3!Pass',
        })
        assert response.status_code == 409
        assert response.json()['success'] is False

    def test_creates_first_user(self, client, db):
        User.objects.all().delete()
        response = _post(client, '/api/security/bootstrap/', {
            'username': 'firstadmin',
            'password': 'Sup3rS3cur3!Pass',
        })
        assert response.status_code == 201
        assert User.objects.filter(username='firstadmin').exists()

    def test_created_user_has_admin_role(self, client, db):
        User.objects.all().delete()
        _post(client, '/api/security/bootstrap/', {
            'username': 'firstadmin', 'password': 'Sup3rS3cur3!Pass',
        })
        user = User.objects.get(username='firstadmin')
        assert user.profile.role == 'admin'
        assert user.is_superuser is True
        assert user.is_staff is True

    def test_create_key_true_returns_plaintext_token(self, client, db):
        User.objects.all().delete()
        response = _post(client, '/api/security/bootstrap/', {
            'username': 'firstadmin',
            'password': 'Sup3rS3cur3!Pass',
            'create_key': True,
            'key_name': 'CI Key',
        })
        assert response.status_code == 201
        data = response.json()
        assert 'api_key' in data
        assert data['api_key']['token'].startswith('lsui_')

    def test_create_key_token_is_usable(self, client, db):
        User.objects.all().delete()
        response = _post(client, '/api/security/bootstrap/', {
            'username': 'firstadmin',
            'password': 'Sup3rS3cur3!Pass',
            'create_key': True,
        })
        raw = response.json()['api_key']['token']
        prefix, secret = ApiKey.parse_token(raw)
        assert ApiKey.objects.get(prefix=prefix).verify_api_key(secret)

    def test_create_key_false_no_token_in_response(self, client, db):
        User.objects.all().delete()
        response = _post(client, '/api/security/bootstrap/', {
            'username': 'firstadmin', 'password': 'Sup3rS3cur3!Pass', 'create_key': False,
        })
        assert 'api_key' not in response.json()

    def test_missing_username_returns_400(self, client, db):
        User.objects.all().delete()
        response = _post(client, '/api/security/bootstrap/', {'password': 'Sup3rS3cur3!Pass'})
        assert response.status_code == 400

    def test_missing_password_returns_400(self, client, db):
        User.objects.all().delete()
        response = _post(client, '/api/security/bootstrap/', {'username': 'firstadmin'})
        assert response.status_code == 400

    def test_weak_password_returns_400(self, client, db):
        User.objects.all().delete()
        response = _post(client, '/api/security/bootstrap/', {
            'username': 'firstadmin', 'password': '123',
        })
        assert response.status_code == 400
        assert response.json()['success'] is False

    def test_wrong_method_returns_405(self, client, db):
        User.objects.all().delete()
        response = client.patch('/api/security/bootstrap/')
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# GET /api/security/me/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMe:

    def test_returns_user_info(self, authenticated_client, test_user):
        response = authenticated_client.get('/api/security/me/')
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        me = data['me']
        assert me['username'] == test_user.username
        assert me['role'] == 'admin'

    def test_no_auth_returns_401(self, client):
        response = client.get('/api/security/me/')
        assert response.status_code == 401

    def test_api_key_auth_includes_key_metadata(self, client, api_key_header):
        response = client.get('/api/security/me/', **api_key_header)
        assert response.status_code == 200
        me = response.json()['me']
        assert 'api_key' in me
        assert me['api_key']['name'] == 'test-key'

    def test_session_auth_has_no_api_key_metadata(self, authenticated_client):
        response = authenticated_client.get('/api/security/me/')
        me = response.json()['me']
        assert 'api_key' not in me

    def test_wrong_method_returns_405(self, authenticated_client):
        response = authenticated_client.post('/api/security/me/')
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# GET + POST /api/security/users/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserList:

    def test_list_returns_all_users(self, authenticated_client, test_user, readonly_user):
        response = authenticated_client.get('/api/security/users/')
        assert response.status_code == 200
        usernames = [u['username'] for u in response.json()['users']]
        assert test_user.username in usernames
        assert readonly_user.username in usernames

    def test_list_no_password_in_response(self, authenticated_client, test_user):
        response = authenticated_client.get('/api/security/users/')
        assert 'password' not in response.content.decode()

    def test_list_no_auth_returns_401(self, client):
        response = client.get('/api/security/users/')
        assert response.status_code == 401

    def test_list_readonly_user_returns_403(self, readonly_client):
        response = readonly_client.get('/api/security/users/')
        assert response.status_code == 403

    def test_create_user_success(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/users/', {
            'username': 'newuser',
            'password': 'Sup3rS3cur3!Pass',
            'role': 'readonly',
        })
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['user']['username'] == 'newuser'
        assert data['user']['role'] == 'readonly'

    def test_create_user_persists(self, authenticated_client):
        _post(authenticated_client, '/api/security/users/', {
            'username': 'persistuser',
            'password': 'Sup3rS3cur3!Pass',
            'role': 'admin',
        })
        assert User.objects.filter(username='persistuser').exists()

    def test_create_user_default_role_is_readonly(self, authenticated_client):
        # H7 fix: default role changed from 'admin' to 'readonly' so that omitting
        # the role field does not silently grant admin privileges.
        _post(authenticated_client, '/api/security/users/', {
            'username': 'defaultrole',
            'password': 'Sup3rS3cur3!Pass',
        })
        user = User.objects.get(username='defaultrole')
        assert user.profile.role == 'readonly'

    def test_create_user_sets_django_permissions(self, authenticated_client):
        _post(authenticated_client, '/api/security/users/', {
            'username': 'adminuser',
            'password': 'Sup3rS3cur3!Pass',
            'role': 'admin',
        })
        user = User.objects.get(username='adminuser')
        assert user.is_superuser is True
        assert user.is_staff is True

    def test_create_readonly_user_no_superuser(self, authenticated_client):
        _post(authenticated_client, '/api/security/users/', {
            'username': 'rouser2',
            'password': 'Sup3rS3cur3!Pass',
            'role': 'readonly',
        })
        user = User.objects.get(username='rouser2')
        assert user.is_superuser is False
        assert user.is_staff is False

    def test_create_duplicate_username_returns_409(self, authenticated_client, test_user):
        response = _post(authenticated_client, '/api/security/users/', {
            'username': test_user.username,
            'password': 'Sup3rS3cur3!Pass',
        })
        assert response.status_code == 409

    def test_create_weak_password_returns_400(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/users/', {
            'username': 'weakpw', 'password': '123',
        })
        assert response.status_code == 400
        errors = response.json()['error']
        assert isinstance(errors, list)
        assert len(errors) > 0

    def test_create_invalid_role_returns_400(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/users/', {
            'username': 'badrole', 'password': 'Sup3rS3cur3!Pass', 'role': 'superuser',
        })
        assert response.status_code == 400

    def test_create_missing_username_returns_400(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/users/', {
            'password': 'Sup3rS3cur3!Pass',
        })
        assert response.status_code == 400

    def test_create_no_auth_returns_401(self, client):
        response = _post(client, '/api/security/users/', {
            'username': 'x', 'password': 'Sup3rS3cur3!Pass',
        })
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET + PUT + DELETE /api/security/users/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserDetail:

    def test_get_user(self, authenticated_client, test_user):
        response = authenticated_client.get(f'/api/security/users/{test_user.id}/')
        assert response.status_code == 200
        assert response.json()['user']['username'] == test_user.username

    def test_get_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.get('/api/security/users/99999/')
        assert response.status_code == 404

    def test_update_role(self, authenticated_client, readonly_user):
        response = _put(authenticated_client, f'/api/security/users/{readonly_user.id}/', {
            'role': 'admin',
        })
        assert response.status_code == 200
        data = response.json()
        assert 'role' in data['updated']
        readonly_user.refresh_from_db()
        assert readonly_user.profile.role == 'admin'
        assert readonly_user.is_superuser is True

    def test_update_password(self, authenticated_client, readonly_user):
        response = _put(authenticated_client, f'/api/security/users/{readonly_user.id}/', {
            'password': 'N3wSup3rP@ss!',
        })
        assert response.status_code == 200
        assert 'password' in response.json()['updated']
        readonly_user.refresh_from_db()
        assert readonly_user.check_password('N3wSup3rP@ss!')

    def test_update_reports_changed_fields(self, authenticated_client, readonly_user):
        response = _put(authenticated_client, f'/api/security/users/{readonly_user.id}/', {
            'role': 'admin', 'password': 'N3wSup3rP@ss!',
        })
        updated = response.json()['updated']
        assert 'role' in updated
        assert 'password' in updated

    def test_update_no_changes_returns_400(self, authenticated_client, readonly_user):
        response = _put(authenticated_client, f'/api/security/users/{readonly_user.id}/', {})
        assert response.status_code == 400

    def test_update_weak_password_returns_400(self, authenticated_client, readonly_user):
        response = _put(authenticated_client, f'/api/security/users/{readonly_user.id}/', {
            'password': '123',
        })
        assert response.status_code == 400

    def test_update_invalid_role_returns_400(self, authenticated_client, readonly_user):
        response = _put(authenticated_client, f'/api/security/users/{readonly_user.id}/', {
            'role': 'superadmin',
        })
        assert response.status_code == 400

    def test_delete_user(self, authenticated_client, readonly_user):
        uid = readonly_user.id
        response = authenticated_client.delete(f'/api/security/users/{uid}/')
        assert response.status_code == 200
        assert not User.objects.filter(id=uid).exists()

    def test_delete_self_returns_400(self, authenticated_client, test_user):
        response = authenticated_client.delete(f'/api/security/users/{test_user.id}/')
        assert response.status_code == 400
        assert 'own account' in response.json()['error']

    def test_delete_last_user_returns_400(self, authenticated_client, test_user):
        """With only one user, deleting self hits the self-check first."""
        response = authenticated_client.delete(f'/api/security/users/{test_user.id}/')
        assert response.status_code == 400

    def test_delete_last_non_self_user_blocked(self, db):
        """Two users; delete each other's account until only one remains."""
        admin = User.objects.create_user(username='admin2', password='Sup3rS3cur3!Pass')
        UserProfile.objects.update_or_create(user=admin, defaults={'role': 'admin'})
        admin.is_superuser = True
        admin.is_staff = True
        admin.save()

        victim = User.objects.create_user(username='victim', password='Sup3rS3cur3!Pass')
        UserProfile.objects.update_or_create(user=victim, defaults={'role': 'admin'})

        from django.test import Client
        c = Client()
        c.login(username='admin2', password='Sup3rS3cur3!Pass')

        # Delete victim — now admin2 is the last user
        c.delete(f'/api/security/users/{victim.id}/')
        assert User.objects.count() == 1

        # Try to delete admin2's own account (last user + self) → 400
        response = c.delete(f'/api/security/users/{admin.id}/')
        assert response.status_code == 400

    def test_detail_no_auth_returns_401(self, client, readonly_user):
        response = client.get(f'/api/security/users/{readonly_user.id}/')
        assert response.status_code == 401

    def test_detail_readonly_user_returns_403(self, readonly_client, test_user):
        response = readonly_client.get(f'/api/security/users/{test_user.id}/')
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET + POST /api/security/keys/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestKeyList:

    def test_list_returns_keys(self, authenticated_client, test_user):
        ApiKey.issue_for_user(test_user, name='mykey')
        response = authenticated_client.get('/api/security/keys/')
        assert response.status_code == 200
        names = [k['name'] for k in response.json()['keys']]
        assert 'mykey' in names

    def test_list_excludes_agent_keys(self, authenticated_client, test_user):
        from PipelineManager.models import Connection
        conn = Connection.objects.create(
            name='agent-conn', connection_type='AGENT',
            host='192.168.1.1', agent_id='agt-001',
        )
        ApiKey.objects.create(connection=conn, api_key='agent-raw')
        ApiKey.issue_for_user(test_user, name='admin-key')

        response = authenticated_client.get('/api/security/keys/')
        names = [k['name'] for k in response.json()['keys']]
        assert 'admin-key' in names
        # agent key has no name; check by created_by being null
        for k in response.json()['keys']:
            assert k['created_by'] is not None

    def test_list_no_secrets_in_response(self, authenticated_client, test_user):
        _token, raw = ApiKey.issue_for_user(test_user, name='secretkey')
        _prefix, secret = ApiKey.parse_token(raw)
        body = authenticated_client.get('/api/security/keys/').content.decode()
        assert secret not in body

    def test_list_no_auth_returns_401(self, client):
        response = client.get('/api/security/keys/')
        assert response.status_code == 401

    def test_list_readonly_returns_403(self, readonly_client):
        response = readonly_client.get('/api/security/keys/')
        assert response.status_code == 403

    def test_create_key_returns_201_and_plaintext_token(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/keys/', {'name': 'new-key'})
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['token'].startswith('lsui_')

    def test_create_key_token_is_usable(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/keys/', {'name': 'usable-key'})
        raw = response.json()['token']
        prefix, secret = ApiKey.parse_token(raw)
        assert ApiKey.objects.get(prefix=prefix).verify_api_key(secret)

    def test_create_key_with_expiry(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/keys/', {
            'name': 'expiring-key', 'expires_days': 30,
        })
        assert response.status_code == 201
        assert response.json()['key']['expires_at'] is not None

    def test_create_key_no_expiry_by_default(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/keys/', {'name': 'no-expiry'})
        assert response.json()['key']['expires_at'] is None

    def test_create_key_missing_name_returns_400(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/keys/', {'expires_days': 10})
        assert response.status_code == 400

    def test_create_key_invalid_expires_days_returns_400(self, authenticated_client):
        response = _post(authenticated_client, '/api/security/keys/', {
            'name': 'bad-expiry', 'expires_days': 'soon',
        })
        assert response.status_code == 400

    def test_create_key_no_auth_returns_401(self, client):
        response = _post(client, '/api/security/keys/', {'name': 'x'})
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/security/keys/{id}/revoke/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestKeyRevoke:

    def test_revoke_sets_revoked_at(self, authenticated_client, test_user):
        token, _ = ApiKey.issue_for_user(test_user, name='to-revoke')
        response = authenticated_client.post(f'/api/security/keys/{token.id}/revoke/')
        assert response.status_code == 200
        token.refresh_from_db()
        assert token.revoked_at is not None

    def test_revoke_key_becomes_inactive(self, authenticated_client, test_user):
        token, _ = ApiKey.issue_for_user(test_user, name='to-revoke')
        authenticated_client.post(f'/api/security/keys/{token.id}/revoke/')
        token.refresh_from_db()
        assert token.is_active is False

    def test_revoke_preserves_hash(self, authenticated_client, test_user):
        """Revoke must not re-hash the stored secret."""
        token, raw = ApiKey.issue_for_user(test_user, name='to-revoke')
        stored_hash = token.api_key
        authenticated_client.post(f'/api/security/keys/{token.id}/revoke/')
        token.refresh_from_db()
        assert token.api_key == stored_hash
        _, secret = ApiKey.parse_token(raw)
        assert token.verify_api_key(secret)

    def test_revoke_already_revoked_returns_400(self, authenticated_client, test_user):
        token, _ = ApiKey.issue_for_user(test_user, name='to-revoke')
        authenticated_client.post(f'/api/security/keys/{token.id}/revoke/')
        response = authenticated_client.post(f'/api/security/keys/{token.id}/revoke/')
        assert response.status_code == 400

    def test_revoke_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.post('/api/security/keys/99999/revoke/')
        assert response.status_code == 404

    def test_revoke_wrong_method_returns_405(self, authenticated_client, test_user):
        token, _ = ApiKey.issue_for_user(test_user, name='to-revoke')
        response = authenticated_client.get(f'/api/security/keys/{token.id}/revoke/')
        assert response.status_code == 405

    def test_revoke_no_auth_returns_401(self, client, test_user):
        token, _ = ApiKey.issue_for_user(test_user, name='to-revoke')
        response = client.post(f'/api/security/keys/{token.id}/revoke/')
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/security/keys/{id}/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestKeyDelete:

    def test_delete_removes_row(self, authenticated_client, test_user):
        token, _ = ApiKey.issue_for_user(test_user, name='to-delete')
        response = authenticated_client.delete(f'/api/security/keys/{token.id}/')
        assert response.status_code == 200
        assert not ApiKey.objects.filter(id=token.id).exists()

    def test_delete_nonexistent_returns_404(self, authenticated_client):
        response = authenticated_client.delete('/api/security/keys/99999/')
        assert response.status_code == 404

    def test_delete_wrong_method_returns_405(self, authenticated_client, test_user):
        token, _ = ApiKey.issue_for_user(test_user, name='to-delete')
        response = authenticated_client.get(f'/api/security/keys/{token.id}/')
        assert response.status_code == 405

    def test_delete_no_auth_returns_401(self, client, test_user):
        token, _ = ApiKey.issue_for_user(test_user, name='to-delete')
        response = client.delete(f'/api/security/keys/{token.id}/')
        assert response.status_code == 401

    def test_cannot_delete_agent_key_via_api(self, authenticated_client):
        """Agent keys (user=None) must not be reachable via the security API."""
        from PipelineManager.models import Connection
        conn = Connection.objects.create(
            name='agent-conn', connection_type='AGENT',
            host='192.168.1.1', agent_id='agt-002',
        )
        agent_key = ApiKey.objects.create(connection=conn, api_key='agent-raw')
        response = authenticated_client.delete(f'/api/security/keys/{agent_key.id}/')
        assert response.status_code == 404
        assert ApiKey.objects.filter(id=agent_key.id).exists()
