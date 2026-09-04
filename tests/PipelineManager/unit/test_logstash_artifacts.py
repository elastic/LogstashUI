#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Logstash tarball proxy: claim mechanics, the agent endpoint, and imports."""

import os
import threading
from datetime import timedelta

from django.test import Client
from django.utils import timezone

import pytest

from PipelineManager import artifacts as artifact_lib
from PipelineManager.models import (
    ApiKey,
    Connection,
    LogstashArtifact,
    Policy,
    parse_artifact_filename,
)


TARBALL = 'logstash-9.4.3-linux-x86_64.tar.gz'
CHECKSUM = f'{TARBALL}.sha512'


@pytest.fixture
def cache_dir(tmp_path, settings):
    settings.LOGSTASH_DIR = tmp_path
    return tmp_path


@pytest.fixture
def agent(db):
    """An enrolled agent connection and the raw key it presents."""
    connection = Connection.objects.create(
        name='agent-1', connection_type='AGENT', host='https://agent-1:9500'
    )
    raw = 'agent-raw-key-for-artifacts'
    ApiKey.objects.create(connection=connection, api_key=raw)
    return connection, raw


@pytest.fixture
def ready_artifact(cache_dir, db):
    """A cached, READY tarball with real bytes on disk."""
    body = b'x' * 4096
    (cache_dir / TARBALL).write_bytes(body)
    (cache_dir / CHECKSUM).write_text('0' * 128 + f'  {TARBALL}\n')
    return LogstashArtifact.objects.create(
        filename=TARBALL,
        version='9.4.3',
        arch='linux-x86_64',
        status=LogstashArtifact.Status.READY,
        size_bytes=len(body),
        bytes_downloaded=len(body),
    ), body


def _get(client, connection, filename, raw, **extra):
    return client.get(
        f'/ConnectionManager/LogstashArtifact/{connection.id}/{filename}',
        HTTP_AUTHORIZATION=f'ApiKey {raw}',
        **extra,
    )


class TestFilenameParsing:
    @pytest.mark.parametrize('name,version,arch', [
        (TARBALL, '9.4.3', 'linux-x86_64'),
        ('logstash-9.4.3-linux-aarch64.tar.gz', '9.4.3', 'linux-aarch64'),
        ('logstash-9.4.3-SNAPSHOT-linux-x86_64.tar.gz', '9.4.3-SNAPSHOT', 'linux-x86_64'),
        ('logstash-10.0.0-darwin-aarch64.tar.gz', '10.0.0', 'darwin-aarch64'),
    ])
    def test_accepts_release_names(self, name, version, arch):
        tarball, parsed_version, parsed_arch, is_checksum = parse_artifact_filename(name)
        assert tarball == name
        assert parsed_version == version
        assert parsed_arch == arch
        assert is_checksum is False

    def test_checksum_resolves_to_its_tarball(self):
        """One row and one fetch cover both files."""
        tarball, _v, _a, is_checksum = parse_artifact_filename(CHECKSUM)
        assert tarball == TARBALL
        assert is_checksum is True

    @pytest.mark.parametrize('name', [
        '', 'logstash.tar.gz', '../../../etc/passwd', '/etc/passwd',
        'logstash-9.4.3-linux-x86_64.tar.gz/../evil',
        '../logstash-9.4.3-linux-x86_64.tar.gz',
        'logstash-9.4.3-linux-riscv.tar.gz', 'logstash-9.4.3-linux-x86_64.zip',
        'kibana-9.4.3-linux-x86_64.tar.gz', 'logstash-9.4.3-linux-x86_64.tar.gz.sig',
    ])
    def test_rejects_everything_else(self, name):
        assert parse_artifact_filename(name) is None


@pytest.mark.django_db
class TestClaim:
    def test_exactly_one_caller_wins(self, cache_dir):
        """The whole cross-worker single-flight guarantee, in one assertion."""
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64'
        )
        results = []
        for _ in range(5):
            results.append(LogstashArtifact.claim_for_fetch(artifact.pk))
        assert results.count(True) == 1

    def test_fresh_claim_is_not_stealable(self, cache_dir):
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.FETCHING,
            heartbeat_at=timezone.now(),
        )
        assert LogstashArtifact.claim_for_fetch(artifact.pk) is False

    def test_stale_claim_is_reclaimed(self, cache_dir):
        """A download orphaned by a worker restart must be recoverable."""
        stale = timezone.now() - timedelta(
            seconds=LogstashArtifact.STALE_CLAIM_SECONDS + 10
        )
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.FETCHING,
            heartbeat_at=stale,
        )
        assert LogstashArtifact.claim_for_fetch(artifact.pk) is True

    def test_ready_is_never_reclaimed(self, cache_dir):
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY,
        )
        assert LogstashArtifact.claim_for_fetch(artifact.pk) is False

    def test_failed_is_retryable(self, cache_dir):
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.FAILED, error='boom',
        )
        assert LogstashArtifact.claim_for_fetch(artifact.pk) is True
        artifact.refresh_from_db()
        assert artifact.error == ''

    def test_release_returns_it_to_the_queue(self, cache_dir):
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64'
        )
        LogstashArtifact.claim_for_fetch(artifact.pk)
        LogstashArtifact.release_claim(artifact.pk)
        artifact.refresh_from_db()
        assert artifact.status == LogstashArtifact.Status.PENDING
        assert LogstashArtifact.claim_for_fetch(artifact.pk) is True

    def test_stale_fetches_do_not_count_toward_the_cap(self, cache_dir):
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.FETCHING,
            heartbeat_at=timezone.now() - timedelta(seconds=999),
        )
        assert LogstashArtifact.active_fetch_count() == 0

    def test_upstream_cap_releases_the_claim(self, cache_dir, settings, monkeypatch):
        """Over the cap, the claim must go back so another worker can take it."""
        settings.LOGSTASH_ARTIFACT_MAX_UPSTREAM = 0
        monkeypatch.setattr(threading, 'Thread', _never_started_thread)
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64'
        )

        assert artifact_lib.start_fetch(artifact) is False

        artifact.refresh_from_db()
        assert artifact.status == LogstashArtifact.Status.PENDING


def _never_started_thread(*_args, **_kwargs):
    class _Stub:
        def start(self):
            raise AssertionError("no fetch thread should have been started")
    return _Stub()


@pytest.mark.django_db
class TestServeAuth:
    def test_valid_key_gets_the_file(self, client, agent, ready_artifact):
        connection, raw = agent
        _artifact, body = ready_artifact

        response = _get(client, connection, TARBALL, raw)

        assert response.status_code == 200
        assert b''.join(response.streaming_content) == body
        assert response['Accept-Ranges'] == 'bytes'
        assert response['Content-Length'] == str(len(body))

    def test_wrong_key_is_rejected(self, client, agent, ready_artifact):
        connection, _raw = agent
        assert _get(client, connection, TARBALL, 'nope').status_code == 401

    def test_missing_header_is_rejected(self, client, agent, ready_artifact):
        connection, _raw = agent
        response = client.get(
            f'/ConnectionManager/LogstashArtifact/{connection.id}/{TARBALL}'
        )
        assert response.status_code == 401

    def test_unknown_connection_id_is_401_not_404(self, client, agent, ready_artifact):
        """404 here would let an unauthenticated caller enumerate connection ids."""
        _connection, raw = agent
        response = client.get(
            f'/ConnectionManager/LogstashArtifact/99999/{TARBALL}',
            HTTP_AUTHORIZATION=f'ApiKey {raw}',
        )
        assert response.status_code == 401

    def test_another_agents_key_is_rejected(self, client, agent, ready_artifact, db):
        connection, _raw = agent
        other = Connection.objects.create(
            name='agent-2', connection_type='AGENT', host='https://agent-2:9500'
        )
        ApiKey.objects.create(connection=other, api_key='other-raw-key')

        assert _get(client, connection, TARBALL, 'other-raw-key').status_code == 401

    def test_endpoint_is_exempt_from_the_login_wall(self, client, agent, ready_artifact):
        """No session, no CSRF token -- an agent has neither."""
        anon = Client(enforce_csrf_checks=True)
        connection, raw = agent
        assert _get(anon, connection, TARBALL, raw).status_code == 200

    def test_post_is_rejected(self, client, agent, ready_artifact):
        connection, raw = agent
        response = client.post(
            f'/ConnectionManager/LogstashArtifact/{connection.id}/{TARBALL}',
            HTTP_AUTHORIZATION=f'ApiKey {raw}',
        )
        assert response.status_code == 405


@pytest.mark.django_db
class TestServeStatus:
    def test_uncached_returns_503_and_starts_a_fetch(
        self, client, agent, cache_dir, monkeypatch
    ):
        started = []
        monkeypatch.setattr(
            artifact_lib, 'start_fetch', lambda a: started.append(a.filename) or True
        )
        connection, raw = agent

        response = _get(client, connection, TARBALL, raw)

        assert response.status_code == 503
        assert response['Retry-After'] == str(artifact_lib.RETRY_AFTER_FETCHING)
        assert response.json()['status'] == 'fetching'
        assert started == [TARBALL]

    def test_in_progress_reports_percent(self, client, agent, cache_dir, monkeypatch):
        monkeypatch.setattr(artifact_lib, 'start_fetch', lambda a: False)
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.FETCHING,
            size_bytes=1000, bytes_downloaded=410,
            heartbeat_at=timezone.now(),
        )
        connection, raw = agent

        response = _get(client, connection, TARBALL, raw)

        assert response.status_code == 503
        assert response.json()['percent'] == 41

    def test_failed_returns_502_with_the_reason(
        self, client, agent, cache_dir, monkeypatch
    ):
        monkeypatch.setattr(artifact_lib, 'start_fetch', lambda a: True)
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.FAILED, error='upstream 404',
        )
        connection, raw = agent

        response = _get(client, connection, TARBALL, raw)

        assert response.status_code == 502
        assert response['Retry-After'] == str(artifact_lib.RETRY_AFTER_FAILED)
        assert 'upstream 404' in response.json()['error']

    def test_ready_row_with_a_missing_file_refetches(
        self, client, agent, cache_dir, monkeypatch
    ):
        """Someone deleted the tarball out from under us; don't serve a 500."""
        monkeypatch.setattr(artifact_lib, 'start_fetch', lambda a: True)
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY,
        )
        connection, raw = agent

        assert _get(client, connection, TARBALL, raw).status_code == 503

    @pytest.mark.parametrize('bad', [
        'logstash-9.4.3-linux-riscv.tar.gz', 'evil.sh', 'logstash-9.4.3.tar.gz',
    ])
    def test_bad_filename_is_404(self, client, agent, cache_dir, bad):
        connection, raw = agent
        response = _get(client, connection, bad, raw)
        assert response.status_code == 404
        assert not LogstashArtifact.objects.exists()


@pytest.mark.django_db
class TestRangeRequests:
    def test_suffix_range_returns_206(self, client, agent, ready_artifact):
        connection, raw = agent
        _artifact, body = ready_artifact

        response = _get(client, connection, TARBALL, raw, HTTP_RANGE='bytes=4000-')

        assert response.status_code == 206
        assert response['Content-Range'] == f'bytes 4000-4095/{len(body)}'
        assert b''.join(response.streaming_content) == body[4000:]

    def test_bounded_range(self, client, agent, ready_artifact):
        connection, raw = agent
        _artifact, body = ready_artifact

        response = _get(client, connection, TARBALL, raw, HTTP_RANGE='bytes=10-19')

        assert response.status_code == 206
        assert response['Content-Length'] == '10'
        assert b''.join(response.streaming_content) == body[10:20]

    def test_last_n_bytes(self, client, agent, ready_artifact):
        connection, raw = agent
        _artifact, body = ready_artifact

        response = _get(client, connection, TARBALL, raw, HTTP_RANGE='bytes=-100')

        assert response.status_code == 206
        assert b''.join(response.streaming_content) == body[-100:]

    def test_past_the_end_is_416(self, client, agent, ready_artifact):
        connection, raw = agent
        _artifact, body = ready_artifact

        response = _get(client, connection, TARBALL, raw, HTTP_RANGE='bytes=99999-')

        assert response.status_code == 416
        assert response['Content-Range'] == f'bytes */{len(body)}'

    def test_multi_range_falls_back_to_the_whole_file(
        self, client, agent, ready_artifact
    ):
        """Segmented downloaders would otherwise multiply against the semaphore."""
        connection, raw = agent
        _artifact, body = ready_artifact

        response = _get(client, connection, TARBALL, raw, HTTP_RANGE='bytes=0-9,20-29')

        assert response.status_code == 200
        assert b''.join(response.streaming_content) == body

    def test_malformed_range_falls_back_to_the_whole_file(
        self, client, agent, ready_artifact
    ):
        connection, raw = agent
        _artifact, body = ready_artifact

        response = _get(client, connection, TARBALL, raw, HTTP_RANGE='rows=1-2')

        assert response.status_code == 200
        assert b''.join(response.streaming_content) == body


@pytest.mark.django_db
class TestServeCap:
    @pytest.fixture
    def big_artifact(self, cache_dir):
        """Over SMALL_FILE_BYTES, so it actually consumes a semaphore slot."""
        body = b'y' * (artifact_lib.SMALL_FILE_BYTES + 1)
        (cache_dir / TARBALL).write_bytes(body)
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY, size_bytes=len(body),
        )
        return body

    @pytest.fixture
    def one_slot(self, monkeypatch):
        monkeypatch.setattr(
            artifact_lib, '_serve_semaphore', threading.BoundedSemaphore(1)
        )

    def test_over_the_cap_returns_429(self, client, agent, big_artifact, one_slot):
        connection, raw = agent
        first = _get(client, connection, TARBALL, raw)
        assert first.status_code == 200

        second = _get(client, connection, TARBALL, raw)

        assert second.status_code == 429
        assert second['Retry-After'] == str(artifact_lib.RETRY_AFTER_BUSY)
        assert second.json()['status'] == 'busy'

    def test_slot_is_released_when_the_response_closes(
        self, client, agent, big_artifact, one_slot
    ):
        """The guarantee the whole cap depends on."""
        connection, raw = agent
        first = _get(client, connection, TARBALL, raw)
        b''.join(first.streaming_content)
        first.close()

        assert _get(client, connection, TARBALL, raw).status_code == 200

    def test_slot_is_released_on_a_client_disconnect(
        self, client, agent, big_artifact, one_slot
    ):
        """An agent that hangs up mid-transfer must not leak a slot forever."""
        connection, raw = agent
        first = _get(client, connection, TARBALL, raw)
        next(iter(first.streaming_content))  # read one chunk, then abandon it
        first.close()

        assert _get(client, connection, TARBALL, raw).status_code == 200

    def test_double_close_does_not_over_release(
        self, client, agent, big_artifact, one_slot
    ):
        """BoundedSemaphore raises on over-release, which would be a 500."""
        connection, raw = agent
        response = _get(client, connection, TARBALL, raw)
        b''.join(response.streaming_content)
        response.close()
        response.close()

        assert _get(client, connection, TARBALL, raw).status_code == 200

    def test_checksum_does_not_consume_a_slot(
        self, client, agent, big_artifact, one_slot, cache_dir
    ):
        """A burst of tiny sidecar fetches must not starve real transfers."""
        (cache_dir / CHECKSUM).write_text('0' * 128 + f'  {TARBALL}\n')
        connection, raw = agent

        for _ in range(3):
            assert _get(client, connection, CHECKSUM, raw).status_code == 200

        assert _get(client, connection, TARBALL, raw).status_code == 200


@pytest.mark.django_db
class TestServeAccounting:
    def test_serve_count_increments(self, client, agent, ready_artifact):
        connection, raw = agent
        artifact, _body = ready_artifact

        _get(client, connection, TARBALL, raw)
        _get(client, connection, TARBALL, raw)

        artifact.refresh_from_db()
        assert artifact.serve_count == 2
        assert artifact.last_served_at is not None

    def test_checksum_does_not_count_as_a_serve(self, client, agent, ready_artifact):
        """The sidecar shares the tarball's row; counting it doubled every serve."""
        connection, raw = agent
        artifact, _body = ready_artifact

        assert _get(client, connection, CHECKSUM, raw).status_code == 200

        artifact.refresh_from_db()
        assert artifact.serve_count == 0
        assert artifact.last_served_at is None

    def test_one_download_counts_once(self, client, agent, ready_artifact):
        """What an agent actually does: fetch the tarball and its checksum."""
        connection, raw = agent
        artifact, _body = ready_artifact

        _get(client, connection, TARBALL, raw)
        _get(client, connection, CHECKSUM, raw)

        artifact.refresh_from_db()
        assert artifact.serve_count == 1

    def test_head_does_not_count_as_a_serve(self, client, agent, ready_artifact):
        connection, raw = agent
        artifact, _body = ready_artifact

        response = client.head(
            f'/ConnectionManager/LogstashArtifact/{connection.id}/{TARBALL}',
            HTTP_AUTHORIZATION=f'ApiKey {raw}',
        )

        assert response.status_code == 200
        artifact.refresh_from_db()
        assert artifact.serve_count == 0

    def test_resume_does_not_count_as_a_serve(self, client, agent, ready_artifact):
        """A resume continues a download that was already counted."""
        connection, raw = agent
        artifact, _body = ready_artifact

        response = _get(client, connection, TARBALL, raw, HTTP_RANGE='bytes=2000-')

        assert response.status_code == 206
        artifact.refresh_from_db()
        assert artifact.serve_count == 0

    def test_range_from_zero_counts_as_a_serve(self, client, agent, ready_artifact):
        connection, raw = agent
        artifact, _body = ready_artifact

        response = _get(client, connection, TARBALL, raw, HTTP_RANGE='bytes=0-999')

        assert response.status_code == 206
        artifact.refresh_from_db()
        assert artifact.serve_count == 1

    def test_checksum_is_served_as_text(self, client, agent, ready_artifact):
        connection, raw = agent
        response = _get(client, connection, CHECKSUM, raw)
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/plain'


@pytest.mark.django_db
class TestFetch:
    def test_verifies_sha512_and_publishes(self, cache_dir, monkeypatch):
        import hashlib

        body = b'tarball-bytes' * 100
        digest = hashlib.sha512(body).hexdigest()
        _install_fake_upstream(monkeypatch, body, digest)
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64'
        )

        artifact_lib._fetch(artifact.pk)

        artifact.refresh_from_db()
        assert artifact.status == LogstashArtifact.Status.READY
        assert artifact.sha512 == digest
        assert (cache_dir / TARBALL).read_bytes() == body
        assert (cache_dir / CHECKSUM).exists()

    def test_mismatch_fails_and_publishes_nothing(self, cache_dir, monkeypatch):
        """A corrupt 450 MB download must never reach an agent."""
        _install_fake_upstream(monkeypatch, b'actual-bytes', 'a' * 128)
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64'
        )

        artifact_lib._fetch(artifact.pk)

        artifact.refresh_from_db()
        assert artifact.status == LogstashArtifact.Status.FAILED
        assert 'SHA-512 mismatch' in artifact.error
        assert not (cache_dir / TARBALL).exists()
        assert not (cache_dir / f'{TARBALL}.part').exists()

    def test_upstream_error_is_recorded(self, cache_dir, monkeypatch):
        def _boom(*_a, **_kw):
            raise RuntimeError('connection refused')

        monkeypatch.setattr(artifact_lib.requests, 'get', _boom)
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64'
        )

        artifact_lib._fetch(artifact.pk)

        artifact.refresh_from_db()
        assert artifact.status == LogstashArtifact.Status.FAILED
        assert 'connection refused' in artifact.error

    def test_missing_upstream_checksum_is_tolerated(self, cache_dir, monkeypatch):
        """A private mirror may not publish sidecars; refusing would break it."""
        _install_fake_upstream(monkeypatch, b'bytes-without-a-checksum', None)
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64'
        )

        artifact_lib._fetch(artifact.pk)

        artifact.refresh_from_db()
        assert artifact.status == LogstashArtifact.Status.READY

    def test_source_url_overrides_the_base(self, cache_dir, db):
        artifact = LogstashArtifact(
            filename=TARBALL, source_url='https://mirror.invalid/custom.tar.gz'
        )
        assert artifact.resolve_source_url('https://ignored') == \
            'https://mirror.invalid/custom.tar.gz'

    def test_base_url_derives_the_url(self, cache_dir, db):
        artifact = LogstashArtifact(filename=TARBALL)
        assert artifact.resolve_source_url('https://mirror.invalid/ls/') == \
            f'https://mirror.invalid/ls/{TARBALL}'


def _install_fake_upstream(monkeypatch, body, checksum_hex):
    """Stand in for artifacts.elastic.co: one streamed tarball, one sidecar."""
    class _StreamResponse:
        status_code = 200
        headers = {'Content-Length': str(len(body))}

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=None):
            yield body

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    class _TextResponse:
        def __init__(self):
            self.status_code = 200 if checksum_hex else 404
            self.text = f'{checksum_hex}  {TARBALL}\n' if checksum_hex else ''

        def raise_for_status(self):
            pass

    def _get(url, **kwargs):
        return _StreamResponse() if kwargs.get('stream') else _TextResponse()

    monkeypatch.setattr(artifact_lib.requests, 'get', _get)


@pytest.mark.django_db
class TestImportAndSweep:
    def test_import_registers_a_hand_placed_tarball(
        self, cache_dir, monkeypatch, django_capture_on_commit_callbacks
    ):
        """The air-gapped path: copy it in, click Import."""
        monkeypatch.setattr(threading, 'Thread', _immediate_thread)
        body = b'imported-bytes' * 10
        (cache_dir / TARBALL).write_bytes(body)

        with django_capture_on_commit_callbacks(execute=True):
            assert artifact_lib.scan_for_imports() == [TARBALL]

        artifact = LogstashArtifact.objects.get(filename=TARBALL)
        assert artifact.status == LogstashArtifact.Status.READY
        assert artifact.size_bytes == len(body)
        # No sidecar was supplied, so one is written from what we computed.
        assert (cache_dir / CHECKSUM).exists()

    def test_import_honours_a_supplied_checksum(
        self, cache_dir, monkeypatch, django_capture_on_commit_callbacks
    ):
        import hashlib

        monkeypatch.setattr(threading, 'Thread', _immediate_thread)
        body = b'imported-bytes' * 10
        (cache_dir / TARBALL).write_bytes(body)
        (cache_dir / CHECKSUM).write_text(
            f'{hashlib.sha512(body).hexdigest()}  {TARBALL}\n'
        )

        with django_capture_on_commit_callbacks(execute=True):
            artifact_lib.scan_for_imports()

        assert LogstashArtifact.objects.get(filename=TARBALL).status == \
            LogstashArtifact.Status.READY

    def test_import_rejects_a_bad_checksum(
        self, cache_dir, monkeypatch, django_capture_on_commit_callbacks
    ):
        monkeypatch.setattr(threading, 'Thread', _immediate_thread)
        (cache_dir / TARBALL).write_bytes(b'imported-bytes')
        (cache_dir / CHECKSUM).write_text('b' * 128 + f'  {TARBALL}\n')

        with django_capture_on_commit_callbacks(execute=True):
            artifact_lib.scan_for_imports()

        artifact = LogstashArtifact.objects.get(filename=TARBALL)
        assert artifact.status == LogstashArtifact.Status.FAILED
        assert 'SHA-512 mismatch' in artifact.error

    def test_import_ignores_partials_and_junk(self, cache_dir):
        (cache_dir / f'{TARBALL}.part').write_bytes(b'half a download')
        (cache_dir / 'notes.txt').write_text('hello')
        (cache_dir / CHECKSUM).write_text('0' * 128)

        assert artifact_lib.scan_for_imports() == []
        assert not LogstashArtifact.objects.exists()

    def test_import_skips_already_known_tarballs(self, cache_dir):
        (cache_dir / TARBALL).write_bytes(b'bytes')
        LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY,
        )
        assert artifact_lib.scan_for_imports() == []

    def test_sweep_removes_orphaned_partials(self, cache_dir):
        (cache_dir / f'{TARBALL}.part').write_bytes(b'orphan')
        (cache_dir / TARBALL).write_bytes(b'keep me')

        assert artifact_lib.sweep_partials() == 1

        assert not (cache_dir / f'{TARBALL}.part').exists()
        assert (cache_dir / TARBALL).exists()

    def test_delete_removes_row_and_files(self, cache_dir):
        (cache_dir / TARBALL).write_bytes(b'bytes')
        (cache_dir / CHECKSUM).write_text('0' * 128)
        artifact = LogstashArtifact.objects.create(
            filename=TARBALL, version='9.4.3', arch='linux-x86_64',
            status=LogstashArtifact.Status.READY,
        )

        artifact_lib.delete_artifact(artifact)

        assert not LogstashArtifact.objects.exists()
        assert not (cache_dir / TARBALL).exists()
        assert not (cache_dir / CHECKSUM).exists()


def _immediate_thread(target=None, args=(), kwargs=None, daemon=None):
    """Run the "greenlet" inline so the test can assert on the outcome."""
    class _Inline:
        def start(self):
            target(*args, **(kwargs or {}))
    return _Inline()


@pytest.mark.django_db
class TestPolicyFlag:
    def _policy(self, **kwargs):
        defaults = {
            'name': 'p', 'policy_type': Policy.PolicyType.MANAGED,
            'logstash_source': Policy.LogstashSource.VERSION,
            'logstash_version': '9.4.3', 'logstash_via_ui': True,
            'logstash_yml': '', 'jvm_options': '', 'log4j2_properties': '',
        }
        defaults.update(kwargs)
        return Policy.objects.create(**defaults)

    def test_managed_version_passes_through(self):
        from PipelineManager.agent_modes import logstash_via_ui

        assert logstash_via_ui(self._policy()) is True

    def test_simulate_version_passes_through(self):
        from PipelineManager.agent_modes import logstash_via_ui

        assert logstash_via_ui(
            self._policy(policy_type=Policy.PolicyType.SIMULATE)
        ) is True

    @pytest.mark.parametrize('overrides', [
        {'logstash_source': Policy.LogstashSource.SYSTEM},
        {'policy_type': Policy.PolicyType.PACKAGED},
        {'policy_type': Policy.PolicyType.EMBEDDED},
        {'logstash_via_ui': False},
    ])
    def test_forced_false_where_it_is_meaningless(self, overrides):
        """A stale True left by a policy-type change must not reach an agent."""
        from PipelineManager.agent_modes import logstash_via_ui

        assert logstash_via_ui(self._policy(**overrides)) is False

    def test_appears_in_the_enrollment_payload(self):
        from PipelineManager.agent_modes import build_policy_config

        config = build_policy_config(self._policy(), instance_id=1)
        assert config['logstash_via_ui'] is True

    def test_packaged_payload_carries_a_hard_false(self):
        from PipelineManager.agent_modes import build_policy_config

        config = build_policy_config(
            self._policy(policy_type=Policy.PolicyType.PACKAGED)
        )
        assert config['logstash_via_ui'] is False


@pytest.mark.django_db
class TestAgentContract:
    """The three channels that carry logstash_via_ui out to an agent."""

    @pytest.fixture
    def enrolled(self, db):
        policy = Policy.objects.create(
            name='managed-via-ui',
            policy_type=Policy.PolicyType.MANAGED,
            logstash_source=Policy.LogstashSource.VERSION,
            logstash_version='9.4.3',
            logstash_via_ui=True,
            settings_path='/etc/logstash/',
            logs_path='/var/log/logstash',
            binary_path='/usr/share/logstash/bin',
            logstash_yml='http.host: "0.0.0.0"',
            jvm_options='-Xms1g',
            log4j2_properties='logger.logstash.name = logstash',
        )
        connection = Connection.objects.create(
            name='agent-x', connection_type='AGENT', host='agent.example.com',
            agent_id='agent-x-001', is_active=True, policy=policy,
        )
        raw = 'contract-raw-key'
        ApiKey.objects.create(connection=connection, api_key=raw)
        return policy, connection, raw

    def test_check_in_carries_the_flag(self, client, enrolled):
        import json

        _policy, connection, raw = enrolled

        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({'connection_id': connection.id}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {raw}',
        )

        assert response.status_code == 200
        assert response.json()['logstash_via_ui'] is True

    def test_check_in_reports_false_for_system_source(self, client, enrolled):
        import json

        policy, connection, raw = enrolled
        policy.logstash_source = Policy.LogstashSource.SYSTEM
        policy.save()

        response = client.post(
            '/ConnectionManager/CheckIn/',
            data=json.dumps({'connection_id': connection.id}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {raw}',
        )

        assert response.json()['logstash_via_ui'] is False

    def test_toggling_the_flag_alone_marks_the_runtime_changed(self, client, enrolled):
        """Otherwise the agent keeps pulling from whichever source it used last."""
        import json

        _policy, connection, raw = enrolled

        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': connection.id,
                # Agent state matches the policy in every respect except the flag.
                'logstash_source': 'VERSION',
                'logstash_version': '9.4.3',
                'logstash_download_dir': '/opt/logstash-agent/logstash-versions',
                'logstash_via_ui': False,
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {raw}',
        )

        runtime = response.json()['changes']['logstash_runtime']
        assert runtime['via_ui'] is True

    def test_agreeing_agent_sees_no_runtime_change(self, client, enrolled):
        import json

        _policy, connection, raw = enrolled

        response = client.post(
            '/ConnectionManager/GetConfigChanges/',
            data=json.dumps({
                'connection_id': connection.id,
                'logstash_source': 'VERSION',
                'logstash_version': '9.4.3',
                'logstash_download_dir': '/opt/logstash-agent/logstash-versions',
                'logstash_via_ui': True,
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'ApiKey {raw}',
        )

        assert response.json()['changes']['logstash_runtime'] is False
