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
