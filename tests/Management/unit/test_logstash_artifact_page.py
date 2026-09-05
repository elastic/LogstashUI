#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Management -> Logstash Tarballs."""

from django.contrib.auth.models import User

import pytest

from Management.models import UserProfile
from PipelineManager.models import LogstashArtifact, Policy


URL = '/Management/LogstashArtifacts/'
TARBALL = 'logstash-9.4.3-linux-x86_64.tar.gz'


@pytest.fixture
def cache_dir(tmp_path, settings):
    settings.LOGSTASH_DIR = tmp_path
    return tmp_path


@pytest.fixture
def no_fetch(monkeypatch):
    """Never touch the network; record what would have been fetched."""
    from PipelineManager import artifacts as artifact_lib

    started = []
    monkeypatch.setattr(
        artifact_lib, 'start_fetch', lambda a: started.append(a.filename) or True
    )
    return started


@pytest.fixture
def readonly_client(client, db):
    user = User.objects.create_user(username='ro', password='ropass123')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    client.login(username='ro', password='ropass123')
    return client


@pytest.mark.django_db
class TestDownload:
    def test_version_and_arch_derive_the_filename(
        self, authenticated_client, cache_dir, no_fetch
    ):
        response = authenticated_client.post(URL, {
            'action': 'download', 'version': '9.4.3', 'arch': 'linux-x86_64',
        })

        assert response.status_code == 204
        assert no_fetch == [TARBALL]
        artifact = LogstashArtifact.objects.get(filename=TARBALL)
        assert artifact.version == '9.4.3'
        assert artifact.arch == 'linux-x86_64'

    def test_full_url_overrides_version_and_arch(
        self, authenticated_client, cache_dir, no_fetch
    ):
        url = f'https://mirror.invalid/ls/{TARBALL}'

        response = authenticated_client.post(URL, {
            'action': 'download', 'source_url': url, 'version': 'ignored',
        })

        assert response.status_code == 204
        assert LogstashArtifact.objects.get(filename=TARBALL).source_url == url

    @pytest.mark.parametrize('payload,fragment', [
        ({'action': 'download', 'version': ''}, 'version is required'),
        ({'action': 'download', 'source_url': 'ftp://x/logstash.tar.gz'},
         'must start with http'),
        ({'action': 'download', 'version': '9.4.3', 'arch': 'linux-riscv'},
         'not a recognized Logstash tarball name'),
        ({'action': 'download', 'source_url': 'https://x/evil.sh'},
         'not a recognized Logstash tarball name'),
    ])
    def test_validation(self, authenticated_client, cache_dir, payload, fragment):
        response = authenticated_client.post(URL, payload)
        assert fragment in response.content.decode()
        assert not LogstashArtifact.objects.exists()

    def test_already_cached_is_refused(self, authenticated_client, cache_dir):
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY,
        )

        response = authenticated_client.post(URL, {
            'action': 'download', 'version': '9.4.3', 'arch': 'linux-x86_64',
        })

        assert 'already cached' in response.content.decode()


@pytest.mark.django_db
class TestImport:
    def test_import_registers_new_files(
        self, authenticated_client, cache_dir, django_capture_on_commit_callbacks
    ):
        (cache_dir / TARBALL).write_bytes(b'bytes')

        with django_capture_on_commit_callbacks():
            response = authenticated_client.post(URL, {'action': 'import'})

        assert response.status_code == 204
        assert LogstashArtifact.objects.filter(filename=TARBALL).exists()

    def test_nothing_to_import_explains_where_to_put_files(
        self, authenticated_client, cache_dir
    ):
        response = authenticated_client.post(URL, {'action': 'import'})
        body = response.content.decode()
        assert 'No new tarballs found' in body
        assert str(cache_dir) in body


@pytest.mark.django_db
class TestDelete:
    def test_delete_removes_row_and_file(self, authenticated_client, cache_dir):
        (cache_dir / TARBALL).write_bytes(b'bytes')
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY,
        )

        response = authenticated_client.post(URL, {
            'action': 'delete', 'artifact_id': artifact.id,
        })

        assert response.status_code == 200
        assert not LogstashArtifact.objects.exists()
        assert not (cache_dir / TARBALL).exists()

    def test_delete_unknown_id(self, authenticated_client, cache_dir):
        response = authenticated_client.post(URL, {
            'action': 'delete', 'artifact_id': 9999,
        })
        assert 'not found' in response.content.decode()

    def test_unknown_action(self, authenticated_client, cache_dir):
        response = authenticated_client.post(URL, {'action': 'nope'})
        assert 'Unknown action' in response.content.decode()


@pytest.mark.django_db
class TestListing:
    def test_empty_state(self, authenticated_client, cache_dir):
        assert 'No tarballs cached yet' in authenticated_client.get(URL).content.decode()

    def test_shows_the_cache_dir_and_source(self, authenticated_client, cache_dir):
        body = authenticated_client.get(URL).content.decode()
        assert str(cache_dir) in body
        assert 'artifacts.elastic.co/downloads/logstash' in body

    def test_configured_mirror_is_shown(self, authenticated_client, cache_dir):
        from Management.models import Settings

        settings_row = Settings.get_settings()
        settings_row.logstash_artifact_base_url = 'https://mirror.invalid/ls'
        settings_row.save()

        assert 'https://mirror.invalid/ls' in \
            authenticated_client.get(URL).content.decode()

    def test_in_use_badge_when_a_policy_pins_the_version(
        self, authenticated_client, cache_dir
    ):
        """Deleting an in-use tarball is allowed, but must not be a surprise."""
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY,
        )
        Policy.objects.create(
            name='managed-via-ui', policy_type=Policy.PolicyType.MANAGED,
            logstash_source=Policy.LogstashSource.VERSION,
            logstash_version='9.4.3', logstash_via_ui=True,
            logstash_yml='', jvm_options='', log4j2_properties='',
        )

        body = authenticated_client.get(URL).content.decode()

        assert 'in use' in body
        assert 'A policy still pins 9.4.3' in body

    def test_no_badge_when_no_policy_uses_the_proxy(
        self, authenticated_client, cache_dir
    ):
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY,
        )
        Policy.objects.create(
            name='managed-direct', policy_type=Policy.PolicyType.MANAGED,
            logstash_source=Policy.LogstashSource.VERSION,
            logstash_version='9.4.3', logstash_via_ui=False,
            logstash_yml='', jvm_options='', log4j2_properties='',
        )

        assert 'in use' not in authenticated_client.get(URL).content.decode()


@pytest.mark.django_db
class TestPolling:
    def test_polls_only_while_something_is_in_flight(
        self, authenticated_client, cache_dir
    ):
        """The trigger rides on the tbody and is swapped out with it, so an idle
        page must not carry one at all."""
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY,
        )
        assert 'hx-trigger="every 3s"' not in \
            authenticated_client.get(URL).content.decode()

        LogstashArtifact.objects.update(status=LogstashArtifact.Status.FETCHING)
        assert 'hx-trigger="every 3s"' in \
            authenticated_client.get(URL).content.decode()

    def test_rows_endpoint_returns_the_whole_tbody(
        self, authenticated_client, cache_dir
    ):
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.FETCHING,
            size_bytes=1000, bytes_downloaded=410,
        )

        body = authenticated_client.get(f'{URL}?rows=1').content.decode()

        assert 'id="artifactTableBody"' in body
        assert '41%' in body

    def test_progress_bar_width_tracks_bytes(self, authenticated_client, cache_dir):
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.FETCHING,
            size_bytes=200, bytes_downloaded=50,
        )
        assert 'width: 25%' in authenticated_client.get(URL).content.decode()


@pytest.mark.django_db
class TestReadonlyUserBlocked:
    def test_get_denied(self, readonly_client, cache_dir):
        assert readonly_client.get(URL).status_code == 403

    def test_download_denied(self, readonly_client, cache_dir):
        response = readonly_client.post(URL, {'action': 'download', 'version': '9.4.3'})
        assert response.status_code == 403
        assert not LogstashArtifact.objects.exists()

    def test_delete_denied(self, readonly_client, cache_dir):
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
        )
        response = readonly_client.post(URL, {
            'action': 'delete', 'artifact_id': artifact.id,
        })
        assert response.status_code == 403
        assert LogstashArtifact.objects.filter(pk=artifact.pk).exists()

    def test_anonymous_redirected(self, client, cache_dir):
        assert client.get(URL).status_code in (302, 403)


@pytest.mark.django_db
class TestSettingsField:
    URL = '/Management/Settings/'

    def test_saves_a_mirror_url(self, authenticated_client):
        from Management.models import Settings

        response = authenticated_client.post(self.URL, {
            'agent_ui_url': '',
            'logstash_artifact_base_url': 'https://mirror.invalid/ls',
        })

        assert response.json()['success'] is True
        assert Settings.get_settings().logstash_artifact_base_url == \
            'https://mirror.invalid/ls'

    def test_rejects_a_non_http_url(self, authenticated_client):
        response = authenticated_client.post(self.URL, {
            'agent_ui_url': '',
            'logstash_artifact_base_url': 'ftp://mirror.invalid/ls',
        })
        assert response.json()['success'] is False

    def test_blank_falls_back_to_elastic(self, authenticated_client, cache_dir):
        from PipelineManager.artifacts import upstream_base_url

        assert upstream_base_url() == 'https://artifacts.elastic.co/downloads/logstash'
