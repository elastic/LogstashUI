#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Optional OpenTelemetry bootstrap.

Enabled by ``LOGSTASHUI_OTEL=true`` and the ``LogstashUI[otel]`` extra. Absent
either, every entry point here is a no-op — LogstashUI ships as an air-gapped
wheel bundle and an offline Docker image, so tracing cannot be a hard dependency.

Two constraints come from running under gunicorn's gevent worker, and both are
easy to get wrong:

* **The gRPC exporter is unusable.** ``grpcio`` runs its own C-core native
  threads, which gevent cannot monkey-patch; it deadlocks or silently drops
  spans. This module only ever configures the HTTP/protobuf exporter, which goes
  through ``requests`` and is fully cooperative.
* **``BatchSpanProcessor`` is required, not optional.** Its worker is a
  ``threading.Thread``, which under gevent is a greenlet, and it blocks on a
  patched ``Condition.wait`` — so it is safe. ``SimpleSpanProcessor`` would put a
  synchronous OTLP round-trip inside every request, including agent check-ins.

Initialization belongs in ``wsgi.build_application()``: once per worker, after
the fork and after monkey-patching, and **before** ``get_wsgi_application()``
so ``DjangoInstrumentor`` can mutate ``MIDDLEWARE`` before the handler
snapshots it. ``settings.py`` is imported by ``manage.py``, every migration,
and every ``cli.py`` management command, so initializing there would spin up a
tracer provider for ``collectstatic``.
"""

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_initialized = False

#: How often the hub-lag probe samples. Cheap: one greenlet, one sleep.
_LAG_INTERVAL = 1.0


def _enabled():
    return os.environ.get('LOGSTASHUI_OTEL', 'false').lower() in ('true', '1', 'yes')


def init_telemetry():
    """Set up tracing and metrics. Returns True when instrumentation is live."""
    global _initialized
    if _initialized or not _enabled():
        return False

    try:
        from opentelemetry import metrics, trace  # type: ignore[import-not-found]
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # type: ignore[import-not-found]
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.django import DjangoInstrumentor  # type: ignore[import-not-found]
        from opentelemetry.instrumentation.requests import RequestsInstrumentor  # type: ignore[import-not-found]
        from opentelemetry.sdk.metrics import MeterProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader  # type: ignore[import-not-found]
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-not-found]
    except ImportError:
        logger.error(
            "LOGSTASHUI_OTEL is set but OpenTelemetry is not installed; "
            "tracing disabled. Install the 'otel' extra to enable it."
        )
        return False

    try:
        import django

        if not django.apps.apps.ready:
            django.setup()

        resource = Resource.create({
            'service.name': os.environ.get('OTEL_SERVICE_NAME', 'logstashui'),
        })

        tracer_provider = TracerProvider(resource=resource)
        # Batch, never Simple -- see the module docstring.
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
        metrics.set_meter_provider(meter_provider)

        # Mutates settings.MIDDLEWARE, so it has to run before the handler is built.
        DjangoInstrumentor().instrument()
        RequestsInstrumentor().instrument()

        from PipelineManager import artifact_metrics

        artifact_metrics.init(meter_provider)
        _start_hub_lag_probe(meter_provider)

        _initialized = True
        logger.info("OpenTelemetry instrumentation enabled (OTLP over HTTP)")
        return True
    except Exception:
        # Telemetry must never be the reason a worker fails to boot.
        logger.exception("OpenTelemetry initialization failed; continuing without it")
        return False


def _start_hub_lag_probe(meter_provider):
    """Measure how late a greenlet wakes up from a 1-second sleep.

    This is the single most useful signal for capacity decisions and the only one
    that sees the problems a span cannot. A greenlet that asks to sleep 1.0 s and
    wakes at 1.4 s spent 0.4 s waiting behind something that would not yield --
    a TLS write, a SQLite writer blocked on ``busy_timeout``, a large disk read.

    Reading it: lag stays flat as load rises => the NIC is the ceiling and adding
    workers will not help. Lag climbs => greenlets are starving, so more workers
    or cores will.
    """
    meter = meter_provider.get_meter('logstashui.runtime')
    state = {'lag': 0.0}

    def _observe(_options):
        from opentelemetry.metrics import Observation  # type: ignore[import-not-found]

        return [Observation(state['lag'])]

    meter.create_observable_gauge(
        'logstashui.gevent.hub.lag',
        callbacks=[_observe],
        unit='s',
        description='How far past its deadline a sleeping greenlet actually woke',
    )

    def _probe():
        while True:
            start = time.monotonic()
            time.sleep(_LAG_INTERVAL)
            state['lag'] = max(0.0, time.monotonic() - start - _LAG_INTERVAL)

    threading.Thread(target=_probe, daemon=True).start()
