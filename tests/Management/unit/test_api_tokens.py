#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Management -> API Tokens page."""

from django.contrib.auth.models import User

import pytest

from Management.models import UserProfile
from PipelineManager.models import ApiKey


URL = '/Management/ApiTokens/'


@pytest.fixture
def readonly_client(client, db):
    user = User.objects.create_user(username='ro', password='ropass123')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    client.login(username='ro', password='ropass123')
    return client


@pytest.mark.django_db
class TestCreate:
    def test_create_shows_raw_token_once(self, authenticated_client):
        response = authenticated_client.post(
            URL, {'action': 'create', 'name': 'ci'}
        )

        assert response.status_code == 200
        token = ApiKey.objects.get(name='ci')
        body = response.content.decode()
        assert f'lsui_{token.prefix}_' in body
        # The stored value is a hash, so the page is the only source of the raw
        # secret — and the list view must never render it.
        assert token.api_key not in body

    def test_created_token_is_usable(self, authenticated_client):
        import re

        response = authenticated_client.post(
            URL, {'action': 'create', 'name': 'ci'}
        )
        raw = re.search(r'lsui_[0-9a-f]{12}_[A-Za-z0-9_\-]+',
                        response.content.decode()).group(0)

        prefix, secret = ApiKey.parse_token(raw)
        assert ApiKey.objects.get(prefix=prefix).verify_api_key(secret)

    def test_owner_is_the_creator(self, authenticated_client, test_user):
        authenticated_client.post(URL, {'action': 'create', 'name': 'ci'})
        assert ApiKey.objects.get(name='ci').user == test_user

    def test_expiry_in_days(self, authenticated_client):
        authenticated_client.post(
            URL, {'action': 'create', 'name': 'ci', 'expires_days': '30'}
        )
        assert ApiKey.objects.get(name='ci').expires_at is not None

    @pytest.mark.parametrize('payload,fragment', [
        ({'action': 'create', 'name': ''}, 'name is required'),
        ({'action': 'create', 'name': 'ci', 'expires_days': 'soon'}, 'whole number'),
        ({'action': 'create', 'name': 'ci', 'expires_days': '0'}, 'at least 1 day'),
    ])
    def test_validation(self, authenticated_client, payload, fragment):
        response = authenticated_client.post(URL, payload)
        assert fragment in response.content.decode()
        assert not ApiKey.objects.exists()

    def test_no_expiry_by_default(self, authenticated_client):
        authenticated_client.post(URL, {'action': 'create', 'name': 'ci'})
        assert ApiKey.objects.get(name='ci').expires_at is None


@pytest.mark.django_db
class TestRevokeAndDelete:
    def test_revoke_sets_timestamp(self, authenticated_client, test_user):
        token, _raw = ApiKey.issue_for_user(test_user, name='ci')

        response = authenticated_client.post(
            URL, {'action': 'revoke', 'token_id': token.id}
        )

        assert response.status_code == 200
        token.refresh_from_db()
        assert token.revoked_at is not None

    def test_revoke_preserves_the_hash(self, authenticated_client, test_user):
        """Revoke re-saves the row; without the double-hash guard the stored
        secret would be silently rewritten."""
        token, raw = ApiKey.issue_for_user(test_user, name='ci')
        stored = token.api_key

        authenticated_client.post(URL, {'action': 'revoke', 'token_id': token.id})

        token.refresh_from_db()
        assert token.api_key == stored
        assert token.verify_api_key(ApiKey.parse_token(raw)[1])

    def test_delete_removes_row(self, authenticated_client, test_user):
        token, _raw = ApiKey.issue_for_user(test_user, name='ci')

        authenticated_client.post(URL, {'action': 'delete', 'token_id': token.id})

        assert not ApiKey.objects.filter(pk=token.pk).exists()

    def test_cannot_touch_agent_keys(self, authenticated_client, test_connection):
        """The page manages admin tokens only; agent keys are not addressable."""
        key = ApiKey.objects.create(connection=test_connection, api_key='raw')

        response = authenticated_client.post(
            URL, {'action': 'delete', 'token_id': key.id}
        )

        assert 'not found' in response.content.decode()
        assert ApiKey.objects.filter(pk=key.pk).exists()

    def test_unknown_action(self, authenticated_client):
        response = authenticated_client.post(URL, {'action': 'nope'})
        assert 'Unknown action' in response.content.decode()


@pytest.mark.django_db
class TestListing:
    def test_lists_only_admin_tokens(self, authenticated_client, test_user,
                                     test_connection):
        ApiKey.issue_for_user(test_user, name='mine')
        ApiKey.objects.create(connection=test_connection, api_key='agent-raw')

        response = authenticated_client.get(URL)

        body = response.content.decode()
        assert response.status_code == 200
        assert 'mine' in body
        assert 'agent-raw' not in body

    def test_empty_state(self, authenticated_client):
        response = authenticated_client.get(URL)
        assert 'No API tokens yet' in response.content.decode()

    def test_secret_never_rendered_in_list(self, authenticated_client, test_user):
        token, raw = ApiKey.issue_for_user(test_user, name='mine')
        _prefix, secret = ApiKey.parse_token(raw)

        body = authenticated_client.get(URL).content.decode()

        assert secret not in body
        assert token.api_key not in body


@pytest.mark.django_db
class TestReadonlyUserBlocked:
    def test_get_denied(self, readonly_client):
        assert readonly_client.get(URL).status_code == 403

    def test_create_denied(self, readonly_client):
        response = readonly_client.post(URL, {'action': 'create', 'name': 'x'})
        assert response.status_code == 403
        assert not ApiKey.objects.exists()

    def test_anonymous_redirected(self, client):
        response = client.get(URL)
        assert response.status_code in (302, 403)
