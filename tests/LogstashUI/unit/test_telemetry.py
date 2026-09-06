#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import logging
import sys
import types
from unittest.mock import MagicMock

import pytest

import LogstashUI.telemetry as telemetry


@pytest.fixture(autouse=True)
def _reset_telemetry():
    telemetry._initialized = False
    yield
    telemetry._initialized = False


def test_init_telemetry_noop_when_disabled(monkeypatch, caplog):
    monkeypatch.delenv("LOGSTASHUI_OTEL", raising=False)
    with caplog.at_level(logging.ERROR, logger="LogstashUI.telemetry"):
        assert telemetry.init_telemetry() is False
    assert not any("OpenTelemetry is not installed" in r.message for r in caplog.records)


def test_init_telemetry_errors_when_extra_missing(monkeypatch, caplog):
    monkeypatch.setenv("LOGSTASHUI_OTEL", "true")
    real_import = __import__

    def _block_otel(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("simulated missing otel extra")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _block_otel)
    with caplog.at_level(logging.ERROR, logger="LogstashUI.telemetry"):
        assert telemetry.init_telemetry() is False
    assert any(
        r.levelno >= logging.ERROR
        and "otel" in r.message.lower()
        and "not installed" in r.message.lower()
        for r in caplog.records
    )


def _install_fake_otel(monkeypatch):
    """Minimal opentelemetry tree so init_telemetry() can import and run."""
    instrument = MagicMock()

    def _mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        monkeypatch.setitem(sys.modules, name, m)
        return m

    metrics = MagicMock()
    trace = MagicMock()
    _mod("opentelemetry", metrics=metrics, trace=trace)
    _mod("opentelemetry.metrics")
    _mod("opentelemetry.trace")

    class _Resource:
        @staticmethod
        def create(_attrs):
            return object()

    class _TracerProvider:
        def __init__(self, resource=None):
            pass

        def add_span_processor(self, _proc):
            pass

    class _MeterProvider:
        def __init__(self, resource=None, metric_readers=None):
            pass

        def get_meter(self, _name):
            meter = MagicMock()
            meter.create_observable_gauge = MagicMock()
            return meter

    class _Exporter:
        def __init__(self, *args, **kwargs):
            pass

    class _Processor:
        def __init__(self, *args, **kwargs):
            pass

    class _Instrumentor:
        def instrument(self, *args, **kwargs):
            instrument(*args, **kwargs)

    _mod("opentelemetry.sdk")
    _mod("opentelemetry.sdk.resources", Resource=_Resource)
    _mod("opentelemetry.sdk.trace", TracerProvider=_TracerProvider)
    _mod("opentelemetry.sdk.trace.export", BatchSpanProcessor=_Processor)
    _mod("opentelemetry.sdk.metrics", MeterProvider=_MeterProvider)
    _mod(
        "opentelemetry.sdk.metrics.export",
        PeriodicExportingMetricReader=_Processor,
    )
    _mod("opentelemetry.exporter")
    _mod("opentelemetry.exporter.otlp")
    _mod("opentelemetry.exporter.otlp.proto")
    _mod("opentelemetry.exporter.otlp.proto.http")
    _mod(
        "opentelemetry.exporter.otlp.proto.http.metric_exporter",
        OTLPMetricExporter=_Exporter,
    )
    _mod(
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        OTLPSpanExporter=_Exporter,
    )
    _mod("opentelemetry.instrumentation")
    _mod(
        "opentelemetry.instrumentation.django",
        DjangoInstrumentor=_Instrumentor,
    )
    _mod(
        "opentelemetry.instrumentation.requests",
        RequestsInstrumentor=_Instrumentor,
    )
    return instrument


def test_init_telemetry_success_instruments_django(monkeypatch):
    monkeypatch.setenv("LOGSTASHUI_OTEL", "true")
    instrument = _install_fake_otel(monkeypatch)
    monkeypatch.setattr(telemetry, "_start_hub_lag_probe", lambda _mp: None)
    monkeypatch.setattr(
        "PipelineManager.artifact_metrics.init", lambda _mp=None: True
    )
    assert telemetry.init_telemetry() is True
    assert telemetry._initialized is True
    instrument.assert_called()

