#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""OpenTelemetry instruments for the tarball proxy, and no-ops without it.

OpenTelemetry is an optional extra (``LogstashUI[otel]``) because LogstashUI ships
as an air-gapped wheel bundle and an offline Docker image, where every added
dependency has a real cost. Every function here is safe to call unconditionally:
when the packages are absent, or ``LOGSTASHUI_OTEL`` is off, they do nothing.

Django auto-instrumentation alone cannot answer the question these exist for —
"should I add workers, cores, or concurrency?". A span shows that a request was
slow, never that the gevent hub was blocked. These four do:

``logstashui.gevent.hub.lag``
    The most useful of the set. Flat under load means the NIC is the ceiling and
    more workers will not help; spiking means greenlet starvation, so more
    workers or cores will. It is also the only thing that catches a SQLite
    ``busy_timeout`` stall, which blocks every greenlet in the process at once.
``logstashui.artifact.downloads.active``
    If this never reaches the cap, the cap is not the constraint and tuning it
    is wasted effort.
``logstashui.artifact.requests``
    The 429/503 rate is the direct "raise the cap or add capacity" signal.
``logstashui.artifact.serve.bytes_per_second``
    Cross-plotted against ``downloads.active``: per-stream throughput falling
    while aggregate stays flat means you are at the NIC.
"""

import logging

logger = logging.getLogger(__name__)

_enabled = False
_meter = None
_downloads_active = None
_requests_counter = None
_throughput = None
_otel_context = None

_active_downloads = 0


def _noop(*_args, **_kwargs):
    return None


def init(meter_provider=None):
    """Create the instruments. Called from the OTel bootstrap; safe to skip."""
    global _enabled, _meter, _downloads_active, _requests_counter, _throughput
    global _otel_context

    try:
        from opentelemetry import context as otel_context
        from opentelemetry import metrics
    except ImportError:
        return False

    _otel_context = otel_context
    _meter = (meter_provider or metrics).get_meter('logstashui.artifacts')

    _downloads_active = _meter.create_up_down_counter(
        'logstashui.artifact.downloads.active',
        unit='{download}',
        description='Agent tarball downloads currently streaming from this worker',
    )
    _requests_counter = _meter.create_counter(
        'logstashui.artifact.requests',
        unit='{request}',
        description='Tarball requests by outcome',
    )
    _throughput = _meter.create_histogram(
        'logstashui.artifact.serve.bytes_per_second',
        unit='By/s',
        description='Effective throughput of a completed tarball transfer',
    )
    _enabled = True
    return True


def downloads_active_add(delta):
    global _active_downloads
    _active_downloads += delta
    if _enabled and _downloads_active is not None:
        _downloads_active.add(delta)


def active_downloads():
    """In-flight streams on this worker. Useful without OTel too."""
    return _active_downloads


def record_request(result):
    if _enabled and _requests_counter is not None:
        _requests_counter.add(1, {'result': result})


def record_throughput(bytes_per_second):
    if _enabled and _throughput is not None:
        _throughput.record(bytes_per_second)


def current_context():
    """Capture the calling greenlet's trace context, if any.

    A spawned fetch greenlet does not inherit the request's context, so without
    this its spans orphan and the download cannot be tied to the request that
    triggered it.
    """
    if _otel_context is None:
        return None
    try:
        return _otel_context.get_current()
    except Exception:
        return None


def attach_context(context):
    if context is None or _otel_context is None:
        return None
    try:
        return _otel_context.attach(context)
    except Exception:
        return None


def detach_context(token):
    if token is None or _otel_context is None:
        return
    try:
        _otel_context.detach(token)
    except Exception:
        pass
