#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import logging

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
