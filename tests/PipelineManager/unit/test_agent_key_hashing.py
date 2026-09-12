from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password

from PipelineManager.models import ApiKey, Connection


@pytest.fixture(params=['agent', 'api'])
def generated_key(db, django_user_model, request):
    if request.param == 'api':
        user = django_user_model.objects.create_user(username='hash-test-admin')
        token, raw = ApiKey.issue_for_user(user)
        return token, ApiKey.parse_token(raw)[1]
    connection = Connection.objects.create(
        name='hash-test', connection_type='AGENT', host='localhost'
    )
    raw = 'test-random-agent-key'
    return ApiKey.objects.create(connection=connection, api_key=raw), raw


def test_verification_avoids_password_hasher_and_database(generated_key, django_assert_num_queries):
    key, raw = generated_key
    key.refresh_from_db()
    assert key.api_key != raw
    with patch('PipelineManager.models.check_password', side_effect=AssertionError('slow hasher')):
        with django_assert_num_queries(0):
            assert key.verify_api_key(raw)
            assert not key.verify_api_key('wrong-key')
            assert not key.verify_api_key(None)
    encoded = key.api_key
    key.name = 'renamed'
    key.save()
    key.refresh_from_db()
    assert key.api_key == encoded


def test_legacy_key_upgrades_only_after_success(generated_key):
    key, _ = generated_key
    legacy = make_password('legacy-key')
    ApiKey.objects.filter(pk=key.pk).update(api_key=legacy)
    key.refresh_from_db()
    assert not key.verify_api_key('wrong-key')
    key.refresh_from_db()
    assert key.api_key == legacy
    assert key.verify_api_key('legacy-key')
    key.refresh_from_db()
    assert key.api_key == key._key_digest('legacy-key')
    assert key.verify_api_key('legacy-key')


def test_legacy_upgrade_does_not_overwrite_rotated_key(generated_key):
    key, _ = generated_key
    legacy = make_password('legacy-key')
    ApiKey.objects.filter(pk=key.pk).update(api_key=legacy)
    key.refresh_from_db()
    replacement = key._key_digest('replacement-key')
    ApiKey.objects.filter(pk=key.pk).update(api_key=replacement)
    assert key.verify_api_key('legacy-key')
    key.refresh_from_db()
    assert key.api_key == replacement
    assert not key.verify_api_key('legacy-key')
    assert key.verify_api_key('replacement-key')


def test_digest_prefix_must_match_owner(generated_key):
    token, raw = generated_key
    expected = 'agent_sha256' if token.connection_id else 'api_sha256'
    other = 'api_sha256' if token.connection_id else 'agent_sha256'
    assert token.api_key.startswith(expected + '$')
    token.api_key = token.api_key.replace(expected, other, 1)
    assert not token.verify_api_key(raw)
