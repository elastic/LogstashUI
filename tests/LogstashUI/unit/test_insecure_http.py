#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from LogstashUI.insecure_http import (
    INSECURE_HTTP_WARNING,
    force_http_origins,
    force_http_url,
    insecure_http,
    secure_cookies,
    tls_enabled,
    warn_if_enabled,
)


def test_insecure_http_default_off(monkeypatch):
    monkeypatch.delenv("LOGSTASHUI_INSECURE_HTTP", raising=False)
    assert insecure_http() is False


def test_insecure_http_parses_truthy(monkeypatch):
    for raw in ("true", "TRUE", "1", "yes", "on"):
        monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", raw)
        assert insecure_http() is True, raw


def test_insecure_http_parses_falsey(monkeypatch):
    for raw in ("false", "0", "no", "off"):
        monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", raw)
        assert insecure_http() is False, raw


def test_force_http_url_noop_when_disabled():
    url = "https://agent.example:9500/path?q=1"
    assert force_http_url(url, enabled=False) == url


def test_force_http_url_rewrites_https_when_enabled():
    assert (
        force_http_url("https://agent.example:9500/path?q=1", enabled=True)
        == "http://agent.example:9500/path?q=1"
    )
    assert (
        force_http_url("HTTPS://Agent.Example:9500", enabled=True)
        == "http://Agent.Example:9500"
    )


def test_force_http_url_leaves_http_and_empty():
    assert force_http_url("http://already", enabled=True) == "http://already"
    assert force_http_url("", enabled=True) == ""
    assert force_http_url(None, enabled=True) is None


def test_force_http_url_defaults_to_env(monkeypatch):
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    assert force_http_url("https://x:1") == "http://x:1"
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "false")
    assert force_http_url("https://x:1") == "https://x:1"


def test_tls_enabled_overridden_by_insecure():
    assert tls_enabled(tls_env="true", insecure=True) is False
    assert tls_enabled(tls_env="false", insecure=True) is False
    assert tls_enabled(tls_env="true", insecure=False) is True
    assert tls_enabled(tls_env="false", insecure=False) is False
    assert tls_enabled(tls_env="0", insecure=False) is False


def test_force_http_origins():
    origins = [
        "https://localhost",
        "http://127.0.0.1:8080",
        "https://ui.example:8443",
    ]
    assert force_http_origins(origins, enabled=True) == [
        "http://localhost",
        "http://127.0.0.1:8080",
        "http://ui.example:8443",
    ]
    assert force_http_origins(origins, enabled=False) == origins


def test_secure_cookies():
    assert secure_cookies(debug=False, insecure=False) is True
    assert secure_cookies(debug=False, insecure=True) is False
    assert secure_cookies(debug=True, insecure=False) is False
    assert secure_cookies(debug=True, insecure=True) is False


def test_warn_if_enabled(monkeypatch, caplog):
    import logging

    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    caplog.set_level(logging.WARNING)
    warn_if_enabled()
    assert INSECURE_HTTP_WARNING in caplog.text
