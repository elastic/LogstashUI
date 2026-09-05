#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""API token authentication middleware.

The endpoint under test is ``/ConnectionManager/AddConnection`` because it
exercises all three gates a scripted caller has to clear: CsrfViewMiddleware,
LoginRequiredMiddleware, and ``require_admin_role``.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

import pytest

from Management.models import UserProfile
from PipelineManager.models import ApiKey


ADD_CONNECTION = '/ConnectionManager/AddConnection'
FORM_CT = 'application/x-www-form-urlencoded'
BODY = (
    'connection_type=CENTRALIZED&name=api-created'
    '&host=https://es.invalid&port=443&api_key=abc'
)


@pytest.fixture
def csrf_client():
    """A client that enforces CSRF, so exemption is actually observable."""
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def admin_token(test_user):
    return ApiKey.issue_for_user(test_user, name='ci')


@pytest.fixture
def readonly_token(db):
    user = User.objects.create_user(username='ro', password='ropass123')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    return ApiKey.issue_for_user(user, name='ro-token')


def _post(client, raw=None):
    kwargs = {}
    if raw is not None:
        kwargs['HTTP_AUTHORIZATION'] = f'ApiKey {raw}'
    return client.post(ADD_CONNECTION, BODY, content_type=FORM_CT, **kwargs)


@pytest.mark.django_db
class TestTokenAccepted:
    def test_valid_token_reaches_the_view(self, csrf_client, admin_token, monkeypatch):
        """No CSRF token, no session — the request still reaches AddConnection."""
        monkeypatch.setattr(
            'PipelineManager.manager_views.test_connectivity',
            lambda cid: (True, 'ok'),
        )
        _token, raw = admin_token

        response = _post(csrf_client, raw)

        assert response.status_code == 200
        payload = response.json()
        assert payload['success'] is True
        assert payload['connection_id']

    def test_token_acts_as_its_owner(self, request_factory, admin_token):
        """Both halves of the middleware pair, driven directly.

        The split exists because AuthenticationMiddleware sits between them and
        would overwrite request.user, so assert the two effects separately.
        """
        from django.contrib.auth.models import AnonymousUser
        from Common.middleware import (
            ApiTokenCsrfMiddleware, ApiTokenUserMiddleware,
        )

        _token, raw = admin_token
        request = request_factory.post(
            ADD_CONNECTION, BODY, content_type=FORM_CT,
            HTTP_AUTHORIZATION=f'ApiKey {raw}',
        )
        request.user = AnonymousUser()

        ApiTokenCsrfMiddleware(lambda r: None)(request)
        assert request._dont_enforce_csrf_checks is True

        ApiTokenUserMiddleware(lambda r: None)(request)
        assert request.user.username == 'testuser'

    def test_absent_token_leaves_csrf_alone(self, request_factory):
        from Common.middleware import ApiTokenCsrfMiddleware

        request = request_factory.post(ADD_CONNECTION, BODY, content_type=FORM_CT)
        ApiTokenCsrfMiddleware(lambda r: None)(request)

        assert not hasattr(request, '_dont_enforce_csrf_checks')
        assert not hasattr(request, '_api_token')

    def test_last_used_at_is_recorded(self, csrf_client, admin_token, monkeypatch):
        monkeypatch.setattr(
            'PipelineManager.manager_views.test_connectivity',
            lambda cid: (True, 'ok'),
        )
        token, raw = admin_token
        assert token.last_used_at is None

        _post(csrf_client, raw)

        token.refresh_from_db()
        assert token.last_used_at is not None


@pytest.mark.django_db
class TestTokenRejected:
    def test_unknown_prefix(self, csrf_client):
        response = _post(csrf_client, 'lsui_deadbeefcafe_bogus')
        assert response.status_code == 401
        assert response.json()['success'] is False

    def test_wrong_secret(self, csrf_client, admin_token):
        token, _raw = admin_token
        response = _post(csrf_client, f'lsui_{token.prefix}_wrongsecret')
        assert response.status_code == 401

    def test_revoked(self, csrf_client, admin_token):
        token, raw = admin_token
        token.revoked_at = timezone.now()
        token.save()
        assert _post(csrf_client, raw).status_code == 401

    def test_expired(self, csrf_client, admin_token):
        token, raw = admin_token
        token.expires_at = timezone.now() - timedelta(seconds=1)
        token.save()
        assert _post(csrf_client, raw).status_code == 401

    def test_inactive_owner(self, csrf_client, admin_token, test_user):
        _token, raw = admin_token
        test_user.is_active = False
        test_user.save()
        assert _post(csrf_client, raw).status_code == 401

    def test_readonly_owner_gets_json_403(self, csrf_client, readonly_token):
        """require_admin_role must answer a script in JSON, not an HX-Trigger toast."""
        _token, raw = readonly_token
        response = _post(csrf_client, raw)
        assert response.status_code == 403
        assert response.json()['success'] is False
        assert 'HX-Trigger' not in response


@pytest.mark.django_db
class TestCsrfStillEnforced:
    def test_session_post_without_csrf_token_is_rejected(self, test_user):
        """The regression guard: a logged-in browser POST still needs CSRF.

        A token must not be the thing that switches CSRF off for everyone.
        """
        client = Client(enforce_csrf_checks=True)
        client.login(username='testuser', password='testpass123')

        response = client.post(ADD_CONNECTION, BODY, content_type=FORM_CT)

        assert response.status_code == 403

    def test_forged_header_does_not_disable_csrf(self, test_user):
        """An invalid token is refused outright, never silently CSRF-exempted."""
        client = Client(enforce_csrf_checks=True)
        client.login(username='testuser', password='testpass123')

        response = client.post(
            ADD_CONNECTION, BODY, content_type=FORM_CT,
            HTTP_AUTHORIZATION='ApiKey lsui_deadbeefcafe_bogus',
        )

        assert response.status_code == 401

    def test_anonymous_post_is_rejected(self, csrf_client):
        """Redirected to login by LoginRequiredMiddleware, which runs before the
        CSRF check in process_view."""
        response = _post(csrf_client)
        assert response.status_code in (302, 403)


@pytest.mark.django_db
class TestAgentKeysUnaffected:
    def test_agent_key_header_passes_through(self, csrf_client):
        """Agent keys carry no lsui_ marker; the middleware must ignore them and
        leave authentication to the agent views."""
        response = csrf_client.post(
            '/ConnectionManager/CheckIn/', '{}',
            content_type='application/json',
            HTTP_AUTHORIZATION='ApiKey some-agent-key-without-prefix',
        )
        # 400 from check_in's own missing-connection_id path, not 401 from us.
        assert response.status_code == 400

    def test_non_apikey_scheme_ignored(self, csrf_client, test_user):
        client = Client(enforce_csrf_checks=True)
        client.login(username='testuser', password='testpass123')
        response = client.post(
            ADD_CONNECTION, BODY, content_type=FORM_CT,
            HTTP_AUTHORIZATION='Bearer lsui_deadbeefcafe_bogus',
        )
        # Falls through to normal session handling -> CSRF rejection.
        assert response.status_code == 403


@pytest.mark.django_db
class TestApiKeyModel:
    def test_issue_returns_parseable_token(self, test_user):
        token, raw = ApiKey.issue_for_user(test_user, name='x')
        prefix, secret = ApiKey.parse_token(raw)
        assert prefix == token.prefix
        assert token.verify_api_key(secret)

    def test_prefix_has_no_underscore(self, test_user):
        """split('_', 2) on the wire format depends on this."""
        token, _raw = ApiKey.issue_for_user(test_user, name='x')
        assert '_' not in token.prefix

    def test_resaving_does_not_double_hash(self, test_user):
        """Rename and revoke both re-save the row; the secret must survive."""
        token, raw = ApiKey.issue_for_user(test_user, name='x')
        _prefix, secret = ApiKey.parse_token(raw)

        token.name = 'renamed'
        token.save()
        token.revoked_at = timezone.now()
        token.save()

        token.refresh_from_db()
        assert token.verify_api_key(secret)

    def test_agent_key_still_hashes_on_create(self, test_connection):
        raw = 'agent-raw-key'
        key = ApiKey.objects.create(connection=test_connection, api_key=raw)
        assert key.api_key != raw
        assert key.verify_api_key(raw)

    @pytest.mark.parametrize('raw', [
        '', 'nope', 'lsui_only', 'other_prefix_secret', 'lsui__secret', 'lsui_prefix_',
    ])
    def test_parse_rejects_non_tokens(self, raw):
        assert ApiKey.parse_token(raw) == (None, None)

    def test_clean_requires_exactly_one_owner(self, test_user, test_connection):
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            ApiKey(api_key='x').clean()
        with pytest.raises(ValidationError):
            ApiKey(
                api_key='x', user=test_user, connection=test_connection
            ).clean()
