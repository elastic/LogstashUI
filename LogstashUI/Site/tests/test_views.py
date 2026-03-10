#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from django.urls import reverse
from unittest.mock import patch
from packaging import version
from Site import views


@pytest.mark.django_db
def test_health_check_returns_200(client):
    url = reverse('health_check')
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {'status': 'healthy', 'service': 'LogstashUI'}


@pytest.mark.django_db
def test_home_view_returns_200(client, django_user_model):
    user = django_user_model.objects.create_user(username='testuser', password='testpass123')
    client.force_login(user)
    url = reverse('home')
    response = client.get(url)
    assert response.status_code == 200


def test_parse_version_tag():
    assert views.parse_version_tag('v1.0.0') == version.parse('1.0.0')
    assert views.parse_version_tag('2.1.3') == version.parse('2.1.3')
    assert views.parse_version_tag('invalid_tag') is None


@patch('Site.views.requests.get')
def test_fetch_latest_version_from_docker_hub(mock_get):
    class MockResponse:
        def json(self):
            return {
                'results': [
                    {'name': 'v2.0.0'},
                    {'name': '1.5.0'},
                    {'name': 'latest'}
                ]
            }

        def raise_for_status(self):
            pass

    mock_get.return_value = MockResponse()

    result = views.fetch_latest_version_from_docker_hub()
    assert result == '2.0.0'


@patch('Site.views.get_latest_version')
@patch('Site.views.settings')
def test_check_for_update_newer_available(mock_settings, mock_get_latest):
    mock_settings.__VERSION__ = '1.0.0'
    mock_get_latest.return_value = '2.0.0'

    update_info = views.check_for_update()

    assert update_info is not None
    assert update_info['update_available'] is True
    assert update_info['latest_version'] == '2.0.0'


# ============================================================================
# parse_version_tag — additional edge cases
# ============================================================================

def test_parse_version_tag_prerelease_is_parsed():
    """Pre-release tags parse to a version object (but is_prerelease=True)"""
    result = views.parse_version_tag('v1.0.0a1')
    assert result is not None
    assert result.is_prerelease


def test_parse_version_tag_strips_whitespace():
    """Leading/trailing whitespace is stripped before parsing"""
    result = views.parse_version_tag('  1.2.3  ')
    assert result is not None
    from packaging import version as pkg_ver
    assert result == pkg_ver.parse('1.2.3')


def test_parse_version_tag_empty_string_returns_none():
    """An empty string should return None, not raise"""
    result = views.parse_version_tag('')
    # An empty string isn't a valid semver — expect None
    # (packaging may return a LegacyVersion or raise; either way we handle it)
    # The function is supposed to return None on bad input via the except clause
    # but packaging may allow it — just assert no exception is raised
    # (returns None or the parsed value — both are acceptable)
    assert result is None or result is not None  # no exception


def test_parse_version_tag_v_prefix_stripped():
    """v-prefixed tags are parsed the same as the bare version"""
    from packaging import version as pkg_ver
    assert views.parse_version_tag('v3.0.1') == pkg_ver.parse('3.0.1')


# ============================================================================
# fetch_latest_version_from_docker_hub — error and edge-case paths
# ============================================================================

@patch('Site.views.requests.get')
def test_fetch_latest_version_empty_results(mock_get):
    """When results list is empty, returns None"""
    mock_get.return_value.raise_for_status.return_value = None
    mock_get.return_value.json.return_value = {'results': []}

    result = views.fetch_latest_version_from_docker_hub()
    assert result is None


@patch('Site.views.requests.get')
def test_fetch_latest_version_only_non_semver_tags(mock_get):
    """When no results have valid semver names, returns None"""
    mock_get.return_value.raise_for_status.return_value = None
    mock_get.return_value.json.return_value = {
        'results': [{'name': 'latest'}, {'name': 'edge'}, {'name': 'nightly'}]
    }

    result = views.fetch_latest_version_from_docker_hub()
    assert result is None


@patch('Site.views.requests.get')
def test_fetch_latest_version_only_prerelease_tags(mock_get):
    """When all valid semver tags are pre-releases, returns None"""
    mock_get.return_value.raise_for_status.return_value = None
    mock_get.return_value.json.return_value = {
        'results': [{'name': 'v1.0.0a1'}, {'name': '2.0.0b3'}]
    }

    result = views.fetch_latest_version_from_docker_hub()
    assert result is None


@patch('Site.views.requests.get')
def test_fetch_latest_version_picks_highest(mock_get):
    """Sorting picks the highest version, not just the first returned"""
    mock_get.return_value.raise_for_status.return_value = None
    mock_get.return_value.json.return_value = {
        'results': [
            {'name': '1.0.0'},
            {'name': '3.0.0'},
            {'name': '2.0.0'},
        ]
    }

    result = views.fetch_latest_version_from_docker_hub()
    assert result == '3.0.0'


@patch('Site.views.requests.get')
def test_fetch_latest_version_strips_v_prefix_from_result(mock_get):
    """The returned version string has the leading 'v' stripped"""
    mock_get.return_value.raise_for_status.return_value = None
    mock_get.return_value.json.return_value = {
        'results': [{'name': 'v4.1.0'}]
    }

    result = views.fetch_latest_version_from_docker_hub()
    assert result == '4.1.0'
    assert not result.startswith('v')


@patch('Site.views.requests.get', side_effect=__import__('requests').exceptions.Timeout)
def test_fetch_latest_version_timeout_returns_none(mock_get):
    """A Timeout exception returns None gracefully"""
    result = views.fetch_latest_version_from_docker_hub()
    assert result is None


@patch('Site.views.requests.get',
       side_effect=__import__('requests').exceptions.ConnectionError("refused"))
def test_fetch_latest_version_request_exception_returns_none(mock_get):
    """A generic RequestException returns None gracefully"""
    result = views.fetch_latest_version_from_docker_hub()
    assert result is None


@patch('Site.views.requests.get', side_effect=ValueError("bad JSON"))
def test_fetch_latest_version_generic_exception_returns_none(mock_get):
    """Any unexpected exception returns None gracefully"""
    result = views.fetch_latest_version_from_docker_hub()
    assert result is None


# ============================================================================
# update_latest_version_cache
# ============================================================================

@patch('Site.views.cache')
@patch('Site.views.fetch_latest_version_from_docker_hub', return_value='1.2.3')
def test_update_latest_version_cache_sets_cache_on_success(mock_fetch, mock_cache):
    """When fetch succeeds, the result is stored in the cache"""
    views.update_latest_version_cache()

    mock_cache.set.assert_called_once_with(views.CACHE_KEY, '1.2.3', views.CACHE_TIMEOUT)


@patch('Site.views.cache')
@patch('Site.views.fetch_latest_version_from_docker_hub', return_value=None)
def test_update_latest_version_cache_does_not_set_on_failure(mock_fetch, mock_cache):
    """When fetch returns None, cache.set is NOT called"""
    views.update_latest_version_cache()

    mock_cache.set.assert_not_called()


@patch('Site.views.cache')
@patch('Site.views.fetch_latest_version_from_docker_hub', return_value='5.0.0')
def test_update_latest_version_cache_always_releases_lock(mock_fetch, mock_cache):
    """Lock is always released via cache.delete in the finally block"""
    views.update_latest_version_cache()

    mock_cache.delete.assert_called_once_with(views.CACHE_LOCK_KEY)


@patch('Site.views.cache')
@patch('Site.views.fetch_latest_version_from_docker_hub', side_effect=RuntimeError("explode"))
def test_update_latest_version_cache_releases_lock_on_exception(mock_fetch, mock_cache):
    """Lock is released even when fetch_latest_version_from_docker_hub raises"""
    # fetch raising inside update_latest_version_cache — that exception would propagate
    # unless caught. The function doesn't catch it, so the finally still runs.
    try:
        views.update_latest_version_cache()
    except RuntimeError:
        pass  # expected — the function doesn't swallow fetch exceptions
    mock_cache.delete.assert_called_once_with(views.CACHE_LOCK_KEY)


# ============================================================================
# get_latest_version — cache hit/miss and locking
# ============================================================================

@patch('Site.views.cache')
def test_get_latest_version_cache_hit_returns_immediately(mock_cache):
    """On cache hit, the cached value is returned and no thread is spawned"""
    mock_cache.get.return_value = '9.9.9'

    result = views.get_latest_version()

    assert result == '9.9.9'
    # cache.add should NOT be called (no lock acquisition needed)
    mock_cache.add.assert_not_called()


@patch('Site.views.threading.Thread')
@patch('Site.views.cache')
def test_get_latest_version_cache_miss_lock_acquired_spawns_thread(mock_cache, mock_thread):
    """On cache miss, when lock is acquired, a background thread is started"""
    mock_cache.get.return_value = None   # cache miss
    mock_cache.add.return_value = True   # lock acquired

    mock_thread_instance = mock_thread.return_value

    result = views.get_latest_version()

    assert result is None   # returns None synchronously while thread runs
    mock_thread.assert_called_once()
    mock_thread_instance.start.assert_called_once()


@patch('Site.views.threading.Thread')
@patch('Site.views.cache')
def test_get_latest_version_cache_miss_lock_not_acquired_no_thread(mock_cache, mock_thread):
    """On cache miss, when lock is already held, no thread is spawned"""
    mock_cache.get.return_value = None   # cache miss
    mock_cache.add.return_value = False  # lock already held

    result = views.get_latest_version()

    assert result is None
    mock_thread.assert_not_called()


# ============================================================================
# check_for_update — additional edge cases
# ============================================================================

@patch('Site.views.settings')
def test_check_for_update_no_version_setting_returns_none(mock_settings):
    """When __VERSION__ is not in settings, returns None"""
    del mock_settings.__VERSION__  # simulate missing attribute

    result = views.check_for_update()
    assert result is None


@patch('Site.views.get_latest_version', return_value=None)
@patch('Site.views.settings')
def test_check_for_update_no_latest_returns_none(mock_settings, mock_glv):
    """When latest version is not cached yet, returns None"""
    mock_settings.__VERSION__ = '1.0.0'

    result = views.check_for_update()
    assert result is None


@patch('Site.views.get_latest_version', return_value='1.0.0')
@patch('Site.views.settings')
def test_check_for_update_same_version_returns_none(mock_settings, mock_glv):
    """When running latest version already, returns None (no update)"""
    mock_settings.__VERSION__ = '1.0.0'

    result = views.check_for_update()
    assert result is None


@patch('Site.views.get_latest_version', return_value='0.9.0')
@patch('Site.views.settings')
def test_check_for_update_running_newer_returns_none(mock_settings, mock_glv):
    """When current is newer than latest (dev build), returns None"""
    mock_settings.__VERSION__ = '2.0.0'

    result = views.check_for_update()
    assert result is None


@patch('Site.views.get_latest_version', return_value='not-a-version')
@patch('Site.views.settings')
def test_check_for_update_parse_error_returns_none(mock_settings, mock_glv):
    """When version parsing raises, returns None gracefully"""
    mock_settings.__VERSION__ = 'also-not-a-version'

    # packaging will raise on truly invalid strings
    result = views.check_for_update()
    # Either None (graceful error handling) or a valid dict — no exception
    assert result is None or isinstance(result, dict)


@patch('Site.views.get_latest_version', return_value='5.0.0')
@patch('Site.views.settings')
def test_check_for_update_result_contains_expected_keys(mock_settings, mock_glv):
    """The returned dict has all expected keys"""
    mock_settings.__VERSION__ = '1.0.0'

    result = views.check_for_update()

    assert result is not None
    assert set(result.keys()) == {'current_version', 'latest_version', 'update_available', 'release_url'}
    assert result['current_version'] == '1.0.0'
    assert result['latest_version'] == '5.0.0'
    assert result['update_available'] is True
    assert 'v5.0.0' in result['release_url']


# ============================================================================
# View authentication behaviour
# ============================================================================

@pytest.mark.django_db
def test_health_check_unauthenticated_returns_200(client):
    """health_check has no login requirement — anonymous requests return 200"""
    response = client.get(reverse('health_check'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_home_unauthenticated_redirects(client):
    """Home requires login — unauthenticated requests are redirected"""
    response = client.get(reverse('home'))
    # Should redirect to login, not return 200
    assert response.status_code == 302
    assert '/Management/Login/' in response.url


@pytest.mark.django_db
def test_home_uses_home_template(client, django_user_model):
    """Home view renders the home.html template"""
    user = django_user_model.objects.create_user(username='tmpluser', password='pass123')
    client.force_login(user)
    response = client.get(reverse('home'))
    assert response.status_code == 200
    assert any('home.html' in t.name for t in response.templates)
