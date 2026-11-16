"""Management -> Settings: Docker Hub update-check toggle."""

import pytest

from Management.models import Settings


URL = '/Management/Settings/'


@pytest.mark.django_db
class TestCheckForUpdatesSetting:
    def test_defaults_to_enabled(self):
        assert Settings.get_settings().check_for_updates is True

    def test_unchecked_toggle_disables(self, authenticated_client):
        response = authenticated_client.post(URL, {'agent_ui_url': ''})

        assert response.json()['success'] is True
        assert Settings.get_settings().check_for_updates is False

    def test_checked_toggle_enables(self, authenticated_client):
        Settings.objects.filter(pk=Settings.get_settings().pk).update(check_for_updates=False)

        response = authenticated_client.post(URL, {
            'agent_ui_url': '',
            'check_for_updates': 'on',
        })

        assert response.json()['success'] is True
        assert Settings.get_settings().check_for_updates is True

    def test_page_renders_the_toggle_checked_by_default(self, authenticated_client):
        response = authenticated_client.get(URL)

        assert response.status_code == 200
        content = response.content.decode()
        assert 'Check Docker Hub for updates' in content
        assert 'name="check_for_updates"' in content
