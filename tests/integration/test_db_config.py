#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Integration tests for database configuration and server version checking.
All tests that open real connections use subprocesses so Django settings
are configured in an isolated interpreter with the container env vars.
"""

import os
import subprocess
import sys

import pytest

from LogstashUI.database import build_databases


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run_python(code: str, extra_env: dict[str, str]) -> str:
    from LogstashUI import migrate_engine as me

    env = os.environ.copy()
    env.update(extra_env)
    env.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    me._with_package_pythonpath(env)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"python -c exited {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout


# ---------------------------------------------------------------------------
# Inline scripts
# ---------------------------------------------------------------------------

_CHECK_SERVER_VERSION = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.db import connection
from LogstashUI.database import check_server_version
connection.ensure_connection()
check_server_version(connection)
print("OK")
"""

_ENSURE_CONNECTION = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.db import connection
connection.ensure_connection()
assert connection.connection is not None, "connection is None"
print("OK")
"""


# ---------------------------------------------------------------------------
# Tests — build_databases() dict structure (no Docker needed)
# ---------------------------------------------------------------------------

def test_mysql_options_include_utf8mb4(monkeypatch, tmp_path):
    """build_databases() for MySQL must include utf8mb4 charset and utf8mb4_bin collation."""
    for key in (
        "LOGSTASHUI_DB_ENGINE", "LOGSTASHUI_DB_HOST", "LOGSTASHUI_DB_PORT",
        "LOGSTASHUI_DB_USER", "LOGSTASHUI_DB_PASSWORD", "LOGSTASHUI_DB_NAME",
        "LOGSTASHUI_DB_CONN_MAX_AGE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LOGSTASHUI_DB_ENGINE", "mysql")
    monkeypatch.setenv("LOGSTASHUI_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("LOGSTASHUI_DB_USER", "root")
    monkeypatch.setattr("LogstashUI.database._import_or_raise", lambda *a, **k: _fake_pymysql())
    db = build_databases(tmp_path)["default"]
    assert db["OPTIONS"]["charset"] == "utf8mb4"
    assert "utf8mb4_bin" in db["OPTIONS"]["init_command"]
    assert db["TEST"]["CHARSET"] == "utf8mb4"
    assert db["TEST"]["COLLATION"] == "utf8mb4_bin"


def _fake_pymysql():
    from types import SimpleNamespace
    fake = SimpleNamespace(
        version_info=(1, 1, 1, "final", 0),
        install_as_MySQLdb=lambda: None,
    )
    return fake


def test_conn_max_age_applied(monkeypatch, tmp_path):
    """LOGSTASHUI_DB_CONN_MAX_AGE overrides the default 60s for postgres."""
    for key in (
        "LOGSTASHUI_DB_ENGINE", "LOGSTASHUI_DB_HOST", "LOGSTASHUI_DB_PORT",
        "LOGSTASHUI_DB_USER", "LOGSTASHUI_DB_PASSWORD", "LOGSTASHUI_DB_NAME",
        "LOGSTASHUI_DB_CONN_MAX_AGE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LOGSTASHUI_DB_ENGINE", "postgresql")
    monkeypatch.setenv("LOGSTASHUI_DB_HOST", "db.example")
    monkeypatch.setenv("LOGSTASHUI_DB_USER", "lsui")
    monkeypatch.setenv("LOGSTASHUI_DB_CONN_MAX_AGE", "120")
    monkeypatch.setattr("LogstashUI.database._import_or_raise", lambda *a, **k: None)
    db = build_databases(tmp_path)["default"]
    assert db["CONN_MAX_AGE"] == 120


def test_build_databases_returns_valid_dict(engine_env, tmp_path, monkeypatch):
    """build_databases() produces a valid DATABASES dict for each engine."""
    engine, env = engine_env
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", str(tmp_path))
    # For MySQL, stub _import_or_raise so it runs without the spoof side-effect
    if engine == "mysql":
        monkeypatch.setattr(
            "LogstashUI.database._import_or_raise",
            lambda *a, **k: _fake_pymysql(),
        )
    db = build_databases(tmp_path)["default"]
    assert "ENGINE" in db
    assert "HOST" in db
    assert "PORT" in db
    assert "NAME" in db
    assert isinstance(db["PORT"], str)


# ---------------------------------------------------------------------------
# Tests — real container connections (subprocess)
# ---------------------------------------------------------------------------

def test_real_connection_opens(engine_env, tmp_path):
    """Django can open a connection to the container database."""
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _run_python(_ENSURE_CONNECTION, full_env)


def test_check_server_version_passes_on_real_connection(engine_env, tmp_path):
    """check_server_version() passes without error on a real container connection."""
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _run_python(_CHECK_SERVER_VERSION, full_env)


def test_check_server_version_mariadb_branch(mariadb_container, tmp_path):
    """check_server_version() MariaDB detection branch passes on a real MariaDB server."""
    from tests.integration.conftest import mysql_env
    env = mysql_env(mariadb_container)
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _run_python(_CHECK_SERVER_VERSION, full_env)
