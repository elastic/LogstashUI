#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""A3-A5: DEBUG opt-in pins and import-time settings under the flipped default.

Spec logstashui-django-debug-default-false r2 (plan-slice S1).

- A3: ``DEBUG=true|1|yes`` (case-insensitive) pins ``settings.DEBUG`` True.
- A4: all in-scope env vars unset pins the secure import-time settings.
- A5: ``DEBUG=true`` with ``LOGSTASHUI_TLS`` unset pins the dev import-time
  settings.

The reload helper is duplicated here (not imported) so each module is
self-contained and the base-tree worktree run needs no conftest backport.
"""

import importlib
import sys

import pytest

_SETTINGS_MODULE = "LogstashUI.settings"
_EVICTION_PREFIXES = ("LogstashUI", "Common")
_SETTINGS_ENV_VARS = (
    "DEBUG",
    "LOGSTASHUI_TLS",
    "LOGSTASHUI_INSECURE_HTTP",
    "LOGSTASH_AGENT_URL",
    "LOGSTASHUI_LOG_LEVEL",
)


def _import_settings(monkeypatch, tmp_path, **env):
    """Evict and reimport ``LogstashUI.settings`` under a controlled environment.

    Sets every ``_SETTINGS_ENV_VARS`` entry to ``env``'s value or clears it,
    points ``LOGSTASHUI_DATA_DIR`` at ``tmp_path``, evicts ``LogstashUI*``/
    ``Common*`` modules from ``sys.modules``, imports the settings fresh, then
    **restores the prior ``sys.modules`` state** so no other test observes a
    re-created module object (eviction without restore desynchronized
    ``tests/LogstashUI/unit/test_paths.py``).

    Args:
        monkeypatch: pytest ``monkeypatch`` fixture.
        tmp_path: pytest ``tmp_path`` fixture; used for ``LOGSTASHUI_DATA_DIR``.
        **env: Controlled values for ``_SETTINGS_ENV_VARS``; omitted vars unset.

    Returns:
        The freshly imported settings module.
    """
    for name in _SETTINGS_ENV_VARS:
        if name in env:
            monkeypatch.setenv(name, env[name])
        else:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", str(tmp_path / "data"))

    saved = {}
    for name in list(sys.modules):
        if name.startswith(_EVICTION_PREFIXES):
            saved[name] = sys.modules[name]
            del sys.modules[name]
    try:
        settings = importlib.import_module(_SETTINGS_MODULE)
    finally:
        sys.modules.update(saved)

    return settings


# --- A3: DEBUG opt-in accepts true / 1 / yes, case-insensitive ----------------


@pytest.mark.parametrize("raw", ["true", "TRUE", "True", "1", "yes", "YES", "Yes"])
def test_debug_opt_in_values(monkeypatch, tmp_path, raw):
    """``DEBUG=true|1|yes`` in any case pins ``settings.DEBUG`` True (spec A3)."""
    settings = _import_settings(monkeypatch, tmp_path, DEBUG=raw)
    assert settings.DEBUG is True


@pytest.mark.parametrize("raw", ["false", "0", "no", "FALSE", "garbage"])
def test_debug_opt_out_values(monkeypatch, tmp_path, raw):
    """Non-truthy values keep the disabled default (parser semantics unchanged)."""
    settings = _import_settings(monkeypatch, tmp_path, DEBUG=raw)
    assert settings.DEBUG is False


# --- A4: unset-env import-time pins (secure posture) --------------------------


def test_unset_env_secure_posture(monkeypatch, tmp_path):
    """All in-scope env vars unset pins the secure import-time settings (A4)."""
    settings = _import_settings(monkeypatch, tmp_path)  # all five unset
    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True
    assert settings.SECURE_HSTS_SECONDS == 31536000
    assert settings.X_FRAME_OPTIONS == "DENY"
    assert not any("django_browser_reload" in app for app in settings.INSTALLED_APPS)
    assert not any("django_browser_reload" in mw for mw in settings.MIDDLEWARE)
    assert settings.LOGSTASH_AGENT_URL == "https://logstashagent:9500"
    assert settings.LOGSTASHUI_LOG_LEVEL == "INFO"


# --- A5: DEBUG=true opt-in path ----------------------------------------------


def test_debug_true_dev_posture(monkeypatch, tmp_path):
    """``DEBUG=true`` with ``LOGSTASHUI_TLS`` unset pins the dev values (A5)."""
    settings = _import_settings(monkeypatch, tmp_path, DEBUG="true")
    assert any("django_browser_reload" in app for app in settings.INSTALLED_APPS)
    assert any("django_browser_reload" in mw for mw in settings.MIDDLEWARE)
    assert settings.SECURE_SSL_REDIRECT is False
    assert settings.LOGSTASH_AGENT_URL == "http://127.0.0.1:9500"
    assert settings.LOGSTASHUI_LOG_LEVEL == "DEBUG"
