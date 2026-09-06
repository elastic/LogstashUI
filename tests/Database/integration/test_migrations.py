#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Integration tests for Django migrations against real database containers.
Each parametrized test gets a fresh isolated database (created and dropped
per-test via the fresh_db_env fixture).
"""

import os
import subprocess
import sys

import pytest

from LogstashUI import migrate_engine as me


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run_python(code: str, extra_env: dict[str, str]) -> str:
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

_NO_UNAPPLIED = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
loader = MigrationLoader(connection)
executor = MigrationExecutor(connection)
plan = executor.migration_plan(loader.graph.leaf_nodes())
assert plan == [], f"Unapplied migrations: {[str(m) for m, _ in plan]}"
print("OK")
"""


# ---------------------------------------------------------------------------
# Tests — container migrations
# ---------------------------------------------------------------------------

def test_migrate_runs_clean(fresh_db_env):
    """migrate --noinput completes without error on a fresh container database."""
    engine, env = fresh_db_env
    me.run_manage(["migrate", "--noinput", "--verbosity", "0"], env)


def test_migrate_is_idempotent(fresh_db_env):
    """Running migrate twice is safe (no errors, no unexpected state)."""
    engine, env = fresh_db_env
    me.run_manage(["migrate", "--noinput", "--verbosity", "0"], env)
    me.run_manage(["migrate", "--noinput", "--verbosity", "0"], env)


def test_no_unapplied_migrations(fresh_db_env):
    """After migrate, MigrationExecutor reports an empty plan."""
    engine, env = fresh_db_env
    me.run_manage(["migrate", "--noinput", "--verbosity", "0"], env)
    _run_python(_NO_UNAPPLIED, env)


# ---------------------------------------------------------------------------
# SQLite baseline (no Docker needed — fast sanity check)
# ---------------------------------------------------------------------------

def test_sqlite_migrate_baseline(tmp_path):
    """migrate --noinput works against SQLite; ensures the test runner itself is healthy."""
    sqlite_path = tmp_path / "db.sqlite3"
    env = {
        "LOGSTASHUI_DATA_DIR": str(tmp_path),
        "LOGSTASHUI_DB_ENGINE": "sqlite",
        "LOGSTASHUI_DB_NAME": str(sqlite_path),
    }
    me.run_manage(["migrate", "--noinput", "--verbosity", "0"], env)
    assert sqlite_path.exists()
