#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Logstash tarball proxy: fetch each release once, serve it to every agent.

A ``MANAGED`` or ``SIMULATE`` policy pinned to ``logstash_source=VERSION`` makes
every agent pull its own ~450 MB tarball from artifacts.elastic.co. This module
caches each tarball under ``settings.LOGSTASH_DIR`` and streams it to agents,
which turns N downloads into one and makes air-gapped operation possible.

Three properties are load-bearing, and each is here for a reason specific to how
LogstashUI is deployed:

**Single-flight lives in the database.** There is no ``CACHES`` backend, so
Django falls back to per-process LocMemCache and gunicorn runs 2+ workers. The
``cache.add()`` lock used elsewhere in this codebase cannot coordinate them. A
conditional UPDATE on the artifact row can — see ``LogstashArtifact.claim_for_fetch``.

**A fetch "thread" is a greenlet.** ``GeventWorker.patch()`` monkey-patches
threading before the app loads, so a download dies with its worker: on SIGTERM
gunicorn waits out ``graceful_timeout`` and then kills it. Every download writes
to ``<name>.part`` and is only ``os.replace``d into place after its SHA-512
verifies, so a ``.tar.gz`` in the cache is always complete. Stale claims are
reclaimed by heartbeat.

**Serving is capped per worker.** A gevent worker is one OS thread; concurrent
streams serialize their TLS writes on one core. The cap is a fairness knob, not a
throughput knob: it decides whether 20 agents each crawl or 8 finish fast and 12
retry. The latter is better for a rollout, and ``Retry-After`` makes it orderly.
"""

import hashlib
import logging
import os
import re
import threading
import time

import django.db
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

import requests

from . import artifact_metrics
from .models import (
    SMALL_FILE_BYTES,
    Connection as ConnectionTable,
    LogstashArtifact,
    parse_artifact_filename,
)

logger = logging.getLogger(__name__)

#: Read/write size for the upstream fetch. Disk writes are not gevent-cooperative,
#: but a 1 MiB write to page cache is microseconds.
FETCH_CHUNK = 1024 * 1024

#: Chunk size when streaming to an agent. Each chunk is one SSL_write, a C call
#: the greenlet cannot yield inside, so this is a latency knob rather than a
#: throughput one. Django's 4096 default would mean ~110k iterations per tarball;
#: 1 MiB would hold the hub for ~1 ms at a time. 256 KiB sits between them.
SERVE_BLOCK_SIZE = 256 * 1024

#: Progress and heartbeat are written on a strict time floor, never per chunk.
#: On SQLite a blocked writer sits in C for up to busy_timeout (20 s), which
#: stalls the entire gevent hub -- every greenlet, including agent check-ins.
HEARTBEAT_INTERVAL = 5.0

RETRY_AFTER_FETCHING = 30
RETRY_AFTER_BUSY = 60
RETRY_AFTER_FAILED = 300

_RANGE_RE = re.compile(r'^bytes=(\d*)-(\d*)$')

#: Per-worker, deliberately. Cross-worker coordination would mean adding Redis;
#: the imperfection (429 while a sibling worker is idle) is harmless given
#: Retry-After. Effective total is this value times LOGSTASHUI_WORKERS.
_serve_semaphore = threading.BoundedSemaphore(
    max(1, getattr(settings, 'LOGSTASH_ARTIFACT_MAX_SERVE_PER_WORKER', 4))
)


# --- storage ---------------------------------------------------------------


def artifact_dir():
    return settings.LOGSTASH_DIR


def artifact_path(filename):
    return os.path.join(artifact_dir(), filename)


def upstream_base_url():
    """Operator-configured mirror, falling back to Elastic's artifact host.

    Read defensively: this runs on the agent-facing hot path and must not break
    on an un-migrated database.
    """
    default = settings.LOGSTASH_ARTIFACT_DEFAULT_BASE_URL
    try:
        from Management.models import Settings as AppSettings

        configured = (AppSettings.get_settings().logstash_artifact_base_url or '').strip()
        return configured or default
    except Exception:
        return default


def sweep_partials():
    """Remove ``.part`` files orphaned by a worker that died mid-download.

    Safe to call at any time: a live download holds its ``.part`` open, and on
    POSIX unlinking an open file only removes the name, so the writer fails at
    its final rename rather than corrupting anything.
    """
    removed = 0
    try:
        entries = os.listdir(artifact_dir())
    except OSError:
        return 0
    for name in entries:
        if not name.endswith('.part'):
            continue
        try:
            os.unlink(os.path.join(artifact_dir(), name))
            removed += 1
        except OSError:
            pass
    if removed:
        logger.info(f"Swept {removed} orphaned Logstash tarball download(s)")
    return removed


# --- fetching --------------------------------------------------------------


def _fetch(pk, otel_context=None):
    """Download and verify one artifact. Runs in its own greenlet.

    Never raises into the caller; every exit path records terminal state on the
    row so a watching UI and a polling agent both see the outcome.
    """
    detach = artifact_metrics.attach_context(otel_context)
    try:
        _fetch_inner(pk)
    except Exception as exc:
        logger.error(f"Logstash tarball fetch failed for artifact {pk}: {exc}")
        try:
            django.db.close_old_connections()
            LogstashArtifact.objects.filter(pk=pk).update(
                status=LogstashArtifact.Status.FAILED,
                error=str(exc)[:2000],
                heartbeat_at=timezone.now(),
            )
        except Exception:
            logger.exception("Could not record tarball fetch failure")
    finally:
        artifact_metrics.detach_context(detach)
        # Mandatory. This greenlet gets its own DB connection and never receives
        # request_started/request_finished, so nothing else will ever close it.
        django.db.connections.close_all()


def _fetch_inner(pk):
    artifact = LogstashArtifact.objects.get(pk=pk)
    base = upstream_base_url()
    tarball_url = artifact.resolve_source_url(base)
    checksum_url = f"{tarball_url}.sha512"

    dest = artifact_path(artifact.filename)
    part = f"{dest}.part"
    checksum_dest = artifact_path(artifact.checksum_filename)

    logger.info(f"Fetching Logstash tarball {artifact.filename} from {tarball_url}")

    expected = _fetch_expected_sha512(checksum_url, artifact.filename)

    digest = hashlib.sha512()
    downloaded = 0
    last_beat = 0.0

    with requests.get(tarball_url, stream=True, timeout=(10, 120)) as response:
        response.raise_for_status()
        total = response.headers.get('Content-Length')
        LogstashArtifact.objects.filter(pk=pk).update(
            size_bytes=int(total) if total and total.isdigit() else None,
        )
        with open(part, 'wb') as handle:
            for chunk in response.iter_content(chunk_size=FETCH_CHUNK):
                if not chunk:
                    continue
                handle.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_beat >= HEARTBEAT_INTERVAL:
                    last_beat = now
                    django.db.close_old_connections()
                    LogstashArtifact.objects.filter(pk=pk).update(
                        bytes_downloaded=downloaded,
                        heartbeat_at=timezone.now(),
                    )
            handle.flush()
            os.fsync(handle.fileno())

    actual = digest.hexdigest()
    if expected and actual != expected:
        os.unlink(part)
        raise ValueError(
            f"SHA-512 mismatch for {artifact.filename}: "
            f"upstream published {expected[:16]}…, downloaded {actual[:16]}…"
        )

    # Atomic on POSIX, so a .tar.gz in the cache directory is never partial.
    os.replace(part, dest)
    if expected:
        with open(checksum_dest, 'w', encoding='utf-8') as handle:
            handle.write(f"{expected}  {artifact.filename}\n")

    django.db.close_old_connections()
    LogstashArtifact.objects.filter(pk=pk).update(
        status=LogstashArtifact.Status.READY,
        sha512=actual,
        size_bytes=downloaded,
        bytes_downloaded=downloaded,
        error='',
        heartbeat_at=timezone.now(),
    )
    logger.info(
        f"Logstash tarball {artifact.filename} ready ({downloaded} bytes, sha512 verified)"
    )


def _fetch_expected_sha512(url, filename):
    """Pull the ``.sha512`` sidecar. Absent is tolerated; malformed is not.

    A mirror may not publish checksums, and refusing to cache in that case would
    make internal mirrors unusable. A checksum that exists but does not parse is
    a different matter and fails the fetch.
    """
    try:
        response = requests.get(url, timeout=(10, 30))
        if response.status_code == 404:
            logger.warning(f"No upstream checksum for {filename}; skipping verification")
            return None
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning(f"Could not fetch checksum for {filename}: {exc}")
        return None

    token = response.text.strip().split()[0] if response.text.strip() else ''
    if not re.fullmatch(r'[0-9a-fA-F]{128}', token):
        raise ValueError(f"Malformed upstream SHA-512 for {filename}")
    return token.lower()


def start_fetch(artifact):
    """Try to become the one process downloading this artifact.

    Returns True when a download was started here, False when someone else owns
    it or we are at the upstream cap. Either way the caller answers 503; the
    distinction only matters for logging.
    """
    if not LogstashArtifact.claim_for_fetch(artifact.pk):
        return False

    # Claim first, then check the cap, then hand the claim back if we are over.
    # Counting before claiming would be a TOCTOU window, and closing it properly
    # needs select_for_update -- which SQLite ignores and which would take gap
    # locks on MySQL in a hot path. Overshoot here is bounded by worker count.
    limit = getattr(settings, 'LOGSTASH_ARTIFACT_MAX_UPSTREAM', 2)
    if LogstashArtifact.active_fetch_count() > limit:
        LogstashArtifact.release_claim(artifact.pk)
        logger.info(
            f"Deferring fetch of {artifact.filename}: at the upstream cap ({limit})"
        )
        return False

    context = artifact_metrics.current_context()
    # A no-op under autocommit (ATOMIC_REQUESTS is unset), but correct if this
    # ever runs inside a transaction -- otherwise the greenlet could start before
    # the claim is visible to anyone else.
    transaction.on_commit(
        lambda: threading.Thread(
            target=_fetch, args=(artifact.pk,), kwargs={'otel_context': context},
            daemon=True,
        ).start()
    )
    return True


def get_or_create_artifact(filename, *, source_url=''):
    """Find or register the row for a tarball. Returns None for a bad filename."""
    parsed = parse_artifact_filename(filename)
    if parsed is None:
        return None
    tarball, version, arch, _is_checksum = parsed
    artifact, _created = LogstashArtifact.objects.get_or_create(
        filename=tarball,
        defaults={'version': version, 'arch': arch, 'source_url': source_url},
    )
    if source_url and artifact.source_url != source_url:
        LogstashArtifact.objects.filter(pk=artifact.pk).update(source_url=source_url)
        artifact.source_url = source_url
    return artifact


# --- importing from disk (air-gapped) --------------------------------------


def scan_for_imports():
    """Register tarballs dropped into the cache directory by hand.

    The air-gapped path: an operator copies the tarball in over sneakernet and
    clicks Import rather than uploading 450 MB through a browser. Hashing is
    deferred to a greenlet because SHA-512 over half a gigabyte takes seconds.

    Returns the list of filenames newly registered.
    """
    try:
        entries = sorted(os.listdir(artifact_dir()))
    except OSError:
        return []

    known = set(LogstashArtifact.objects.values_list('filename', flat=True))
    imported = []
    for name in entries:
        # .part files belong to a download in flight, and .sha512 sidecars are
        # covered by their tarball's row.
        if name.endswith('.part') or name.endswith('.sha512'):
            continue
        if name in known:
            continue
        parsed = parse_artifact_filename(name)
        if parsed is None:
            continue
        tarball, version, arch, _is_checksum = parsed
        path = artifact_path(tarball)
        artifact = LogstashArtifact.objects.create(
            filename=tarball,
            version=version,
            arch=arch,
            status=LogstashArtifact.Status.IMPORTING,
            size_bytes=os.path.getsize(path),
            heartbeat_at=timezone.now(),
        )
        imported.append(tarball)
        transaction.on_commit(
            lambda pk=artifact.pk: threading.Thread(
                target=_verify_import, args=(pk,), daemon=True
            ).start()
        )
    return imported


def _verify_import(pk):
    """Hash an imported tarball and publish it, or fail the row."""
    try:
        artifact = LogstashArtifact.objects.get(pk=pk)
        path = artifact_path(artifact.filename)
        digest = hashlib.sha512()
        total = 0
        last_beat = 0.0
        with open(path, 'rb') as handle:
            while True:
                chunk = handle.read(FETCH_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
                now = time.monotonic()
                if now - last_beat >= HEARTBEAT_INTERVAL:
                    last_beat = now
                    django.db.close_old_connections()
                    LogstashArtifact.objects.filter(pk=pk).update(
                        bytes_downloaded=total, heartbeat_at=timezone.now()
                    )

        actual = digest.hexdigest()
        expected = _read_local_checksum(artifact)
        if expected and actual != expected:
            raise ValueError(
                f"SHA-512 mismatch for imported {artifact.filename}: the "
                f"accompanying .sha512 does not match the file"
            )
        if not expected:
            # No sidecar supplied: record what we computed and write one, so the
            # agent's own verification step still has something to check against.
            with open(artifact_path(artifact.checksum_filename), 'w', encoding='utf-8') as fh:
                fh.write(f"{actual}  {artifact.filename}\n")

        django.db.close_old_connections()
        LogstashArtifact.objects.filter(pk=pk).update(
            status=LogstashArtifact.Status.READY,
            sha512=actual,
            size_bytes=total,
            bytes_downloaded=total,
            error='',
            heartbeat_at=timezone.now(),
        )
        logger.info(f"Imported Logstash tarball {artifact.filename} ({total} bytes)")
    except Exception as exc:
        logger.error(f"Import verification failed for artifact {pk}: {exc}")
        try:
            django.db.close_old_connections()
            LogstashArtifact.objects.filter(pk=pk).update(
                status=LogstashArtifact.Status.FAILED,
                error=str(exc)[:2000],
                heartbeat_at=timezone.now(),
            )
        except Exception:
            logger.exception("Could not record import failure")
    finally:
        django.db.connections.close_all()


def _read_local_checksum(artifact):
    """Read a hand-supplied ``.sha512`` sidecar, if there is one."""
    path = artifact_path(artifact.checksum_filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            token = handle.read().strip().split()[0]
    except (OSError, IndexError):
        return None
    if not re.fullmatch(r'[0-9a-fA-F]{128}', token):
        return None
    return token.lower()


def delete_artifact(artifact):
    """Remove an artifact row along with its tarball and checksum on disk."""
    for name in (artifact.filename, artifact.checksum_filename, f"{artifact.filename}.part"):
        try:
            os.unlink(artifact_path(name))
        except OSError:
            pass
    artifact.delete()


# --- serving ---------------------------------------------------------------


class _SemaphoreGuardedFile:
    """A file object that stops at ``limit`` bytes and frees a semaphore slot.

    Two jobs, both of which ``FileResponse`` cannot do itself.

    *Releasing the slot.* Django registers this object's ``close`` as a resource
    closer and gunicorn calls ``respiter.close()`` in a ``finally``, so it fires
    both on a completed transfer and on a client that hangs up mid-stream —
    exactly the guarantee the cap depends on. Wrapping the file beats appending
    to ``response._resource_closers``, which is private and ordering-sensitive.

    *Enforcing the range.* ``FileResponse`` reads to EOF regardless of the
    ``Content-Length`` header, so a seek alone would send the whole remainder of
    the file for a bounded range and the client would see more bytes than it was
    promised. ``limit`` caps it.
    """

    def __init__(self, handle, semaphore, on_close=None, limit=None):
        self._handle = handle
        self._semaphore = semaphore
        self._on_close = on_close
        self._remaining = limit
        self._released = False

    def read(self, size=-1):
        if self._remaining is None:
            return self._handle.read(size)
        if self._remaining <= 0:
            return b''
        if size is None or size < 0:
            size = self._remaining
        chunk = self._handle.read(min(size, self._remaining))
        self._remaining -= len(chunk)
        return chunk

    def seek(self, *args, **kwargs):
        return self._handle.seek(*args, **kwargs)

    def tell(self):
        return self._handle.tell()

    def fileno(self):
        return self._handle.fileno()

    def close(self):
        try:
            self._handle.close()
        finally:
            # close() can legitimately fire twice; a BoundedSemaphore raises on
            # an over-release, which would surface as a 500 on an otherwise
            # successful download.
            if not self._released:
                self._released = True
                if self._semaphore is not None:
                    self._semaphore.release()
                if self._on_close is not None:
                    self._on_close()

    @property
    def closed(self):
        return self._handle.closed


def _parse_range(header, size):
    """Parse a single byte range. Returns (start, end) inclusive, or a sentinel.

    Returns ``None`` when there is no usable range (absent, malformed, or
    multi-range — all of which are answered with a normal 200), and the string
    ``'unsatisfiable'`` when the range is well-formed but outside the file.
    """
    if not header:
        return None
    # Multi-range gains nothing here and would let a segmented downloader
    # multiply itself against the semaphore. Answer it with the whole file.
    if ',' in header:
        return None
    match = _RANGE_RE.match(header.strip())
    if match is None:
        return None
    start_raw, end_raw = match.group(1), match.group(2)
    if not start_raw and not end_raw:
        return None
    if not start_raw:
        # Suffix form: bytes=-500 means the last 500 bytes.
        length = int(end_raw)
        if length <= 0:
            return 'unsatisfiable'
        start = max(0, size - length)
        end = size - 1
    else:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
        end = min(end, size - 1)
    if start >= size or start > end:
        return 'unsatisfiable'
    return start, end


def _retry(status, payload, retry_after):
    response = JsonResponse(payload, status=status)
    response['Retry-After'] = str(retry_after)
    return response


def _authenticate_agent(request, connection_id):
    """Resolve and verify the calling agent. Returns (connection, error_response).

    Same inline sequence as the other agent endpoints; the only difference is
    that ``connection_id`` arrives in the URL, because a GET has no body to put
    it in. It has to come from somewhere: an agent key is a bare PBKDF2 hash with
    no lookup column, so the header alone cannot identify a row without hashing
    against every key in the table.
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('ApiKey '):
        return None, JsonResponse(
            {'success': False, 'error': 'Invalid authorization header'}, status=401
        )
    raw_api_key = auth_header[len('ApiKey '):].strip()

    try:
        connection = ConnectionTable.objects.get(
            id=connection_id, connection_type='AGENT'
        )
    except ConnectionTable.DoesNotExist:
        # 401, not 404: an unauthenticated caller must not be able to probe which
        # connection ids exist.
        return None, JsonResponse(
            {'success': False, 'error': 'Invalid API key'}, status=401
        )

    try:
        api_key_obj = connection.api_keys.first()
        if not api_key_obj or not api_key_obj.verify_api_key(raw_api_key):
            return None, JsonResponse(
                {'success': False, 'error': 'Invalid API key'}, status=401
            )
    except Exception as exc:
        logger.error(f"API key verification error: {exc}")
        return None, JsonResponse(
            {'success': False, 'error': 'Authentication failed'}, status=401
        )

    return connection, None


@csrf_exempt
def serve_artifact(request, connection_id, filename):
    """Serve a cached Logstash tarball to an enrolled agent.

    ``GET /ConnectionManager/LogstashArtifact/<connection_id>/<filename>`` with
    ``Authorization: ApiKey <raw enrollment key>``.

    Answers a cache miss with 503 + ``Retry-After`` and kicks off the download,
    and a full serve queue with 429 + ``Retry-After``. Both are retryable; the
    agent must not fall back to artifacts.elastic.co, which would defeat the
    point in an air-gapped site.
    """
    if request.method not in ('GET', 'HEAD'):
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    _connection, error = _authenticate_agent(request, connection_id)
    if error is not None:
        artifact_metrics.record_request('401')
        return error

    parsed = parse_artifact_filename(filename)
    if parsed is None:
        logger.warning(f"Rejected Logstash tarball request for {filename!r}")
        artifact_metrics.record_request('404')
        return JsonResponse({'status': 'not_found'}, status=404)
    tarball, version, arch, is_checksum = parsed

    artifact = LogstashArtifact.objects.filter(filename=tarball).first()
    if artifact is None:
        artifact = LogstashArtifact.objects.create(
            filename=tarball, version=version, arch=arch
        )

    if artifact.status == LogstashArtifact.Status.FAILED:
        # Retry the fetch, but tell this caller to come back later either way:
        # a 502 body is more useful to an operator reading agent logs than a
        # silent stall.
        start_fetch(artifact)
        artifact_metrics.record_request('502')
        return _retry(
            502,
            {'status': 'failed', 'error': artifact.error or 'Upstream fetch failed'},
            RETRY_AFTER_FAILED,
        )

    path = artifact_path(filename)
    if artifact.status != LogstashArtifact.Status.READY or not os.path.exists(path):
        started = start_fetch(artifact)
        artifact_metrics.record_request('503')
        return _retry(
            503,
            {
                'status': 'fetching',
                'filename': filename,
                'percent': 0 if started else (artifact.percent or 0),
            },
            RETRY_AFTER_FETCHING,
        )

    return _stream_file(request, artifact, path, is_checksum)


def _stream_file(request, artifact, path, is_checksum):
    size = os.path.getsize(path)

    # A checksum sidecar is a few dozen bytes. Making it queue behind four
    # 450 MB transfers would be absurd, and letting a burst of them occupy the
    # slots would starve the transfers themselves.
    needs_slot = size > SMALL_FILE_BYTES
    if needs_slot and not _serve_semaphore.acquire(blocking=False):
        artifact_metrics.record_request('429')
        return _retry(429, {'status': 'busy'}, RETRY_AFTER_BUSY)

    semaphore = _serve_semaphore if needs_slot else None
    started = time.monotonic()

    def _finished():
        if needs_slot:
            artifact_metrics.downloads_active_add(-1)
        elapsed = max(time.monotonic() - started, 1e-6)
        artifact_metrics.record_throughput(size / elapsed)

    if needs_slot:
        artifact_metrics.downloads_active_add(1)

    try:
        handle = open(path, 'rb')
    except OSError:
        if semaphore is not None:
            semaphore.release()
            artifact_metrics.downloads_active_add(-1)
        artifact_metrics.record_request('404')
        return JsonResponse({'status': 'not_found'}, status=404)

    content_type = 'text/plain' if is_checksum else 'application/gzip'
    byte_range = _parse_range(request.headers.get('Range'), size)

    if byte_range == 'unsatisfiable':
        handle.close()
        if semaphore is not None:
            semaphore.release()
            artifact_metrics.downloads_active_add(-1)
        response = HttpResponse(status=416)
        response['Content-Range'] = f'bytes */{size}'
        artifact_metrics.record_request('416')
        return response

    if byte_range is not None:
        start, end = byte_range
        handle.seek(start)
        length = end - start + 1
        response = FileResponse(
            _SemaphoreGuardedFile(
                handle, semaphore, on_close=_finished, limit=length
            ),
            content_type=content_type,
            status=206,
        )
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
        response['Content-Length'] = str(length)
        artifact_metrics.record_request('206')
    else:
        response = FileResponse(
            _SemaphoreGuardedFile(handle, semaphore, on_close=_finished),
            content_type=content_type,
        )
        response['Content-Length'] = str(size)
        artifact_metrics.record_request('served')

    response.block_size = SERVE_BLOCK_SIZE
    response['Accept-Ranges'] = 'bytes'
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(path)}"'

    # One serve == one fresh tarball download, which is not the same as one
    # request. A row covers both the .tar.gz and its .sha512, so counting every
    # request made a single agent download read as 2x; a HEAD is a probe with no
    # body, and a resume continues a download already counted.
    counts_as_serve = (
        not is_checksum
        and request.method == 'GET'
        and (byte_range is None or byte_range[0] == 0)
    )
    if counts_as_serve:
        LogstashArtifact.objects.filter(pk=artifact.pk).update(
            serve_count=F('serve_count') + 1,
            last_served_at=timezone.now(),
        )
    return response
