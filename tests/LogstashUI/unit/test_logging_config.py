#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest

from LogstashUI.logging_config import resolve_django_log_levels, resolve_log_level


def test_log_level_defaults_follow_debug_flag(monkeypatch):
    monkeypatch.delenv("LOGSTASHUI_LOG_LEVEL", raising=False)
    assert resolve_log_level("LOGSTASHUI_LOG_LEVEL", default="INFO") == "INFO"
    assert resolve_log_level("LOGSTASHUI_LOG_LEVEL", default="DEBUG") == "DEBUG"


def test_log_level_env_override(monkeypatch):
    monkeypatch.setenv("LOGSTASHUI_LOG_LEVEL", "warning")
    assert resolve_log_level("LOGSTASHUI_LOG_LEVEL", default="INFO") == "WARNING"
    monkeypatch.setenv("LOGSTASHUI_LOG_LEVEL", "WARN")
    assert resolve_log_level("LOGSTASHUI_LOG_LEVEL", default="INFO") == "WARNING"


def test_log_level_invalid(monkeypatch):
    monkeypatch.setenv("LOGSTASHUI_LOG_LEVEL", "verbose")
    with pytest.raises(RuntimeError, match="LOGSTASHUI_LOG_LEVEL"):
        resolve_log_level("LOGSTASHUI_LOG_LEVEL", default="INFO")


def test_django_levels_default(monkeypatch):
    monkeypatch.delenv("LOGSTASHUI_DJANGO_LOG_LEVEL", raising=False)
    monkeypatch.delenv("DJANGO_LOG_LEVEL", raising=False)
    django_level, request_level = resolve_django_log_levels()
    assert django_level == "INFO"
    assert request_level == "ERROR"


def test_django_levels_prefixed_env(monkeypatch):
    monkeypatch.setenv("LOGSTASHUI_DJANGO_LOG_LEVEL", "debug")
    monkeypatch.setenv("DJANGO_LOG_LEVEL", "error")
    django_level, request_level = resolve_django_log_levels()
    assert django_level == "DEBUG"
    assert request_level == "DEBUG"


def test_django_levels_alias(monkeypatch):
    monkeypatch.delenv("LOGSTASHUI_DJANGO_LOG_LEVEL", raising=False)
    monkeypatch.setenv("DJANGO_LOG_LEVEL", "warning")
    django_level, request_level = resolve_django_log_levels()
    assert django_level == "WARNING"
    assert request_level == "WARNING"
