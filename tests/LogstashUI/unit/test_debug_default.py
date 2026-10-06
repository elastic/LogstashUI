#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""A2: the DEBUG default flips to False when the env var is absent.

Spec logstashui-django-debug-default-false r2 (plan-slice S1).

A2's red-on-base gate requires this module to produce **exactly one** failure
against the base tree (``AssertionError: assert True is False`` at
``settings.DEBUG``). The opt-in / import-time pins (A3-A5) live in
``test_settings_import_time.py`` so this module stays A2-only.

The helper is self-contained (no conftest backport) so the base-tree worktree
run needs nothing beyond this file. Evicted modules are **restored** after the
fresh import: sys.modules eviction without restore leaves a second live
``LogstashUI.paths`` module object behind, which desynchronizes pre-existing
tests that bind its names at collection time (measured: it broke
``tests/LogstashUI/unit/test_paths.py::test_migrate_legacy_copies_sqlite``).
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
    re-created module object.

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


def test_debug_default_false_when_env_absent(monkeypatch, tmp_path):
    """``settings.DEBUG`` is False with the DEBUG env var absent (spec A2)."""
    settings = _import_settings(monkeypatch, tmp_path)  # DEBUG not set at all
    assert settings.DEBUG is False