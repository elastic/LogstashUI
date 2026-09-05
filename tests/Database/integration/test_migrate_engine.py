# Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
# or more contributor license agreements. Licensed under the Elastic License;
# you may not use this file except in compliance with the Elastic License.

"""
Integration tests for cmd_migrate_engine (SQLite → PostgreSQL / MySQL / MariaDB).

Each test uses a unique throwaway database in the session-scoped container
to prevent cross-test contamination.
"""

import json
import os
import subprocess
import sys
from argparse import Namespace

import pytest

from LogstashUI import migrate_engine as me
from tests.Database.integration.conftest import (
    create_mysql_db,
    create_pg_db,
    drop_mysql_db,
    drop_pg_db,
    mysql_env,
    new_dbname,
    pg_env,
)

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

_SEED = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.contrib.auth import get_user_model
from PipelineManager.models import Connection, Policy
User = get_user_model()
User.objects.create_user(username="migrate-user", password="migrate-pass")
policy = Policy.objects.create(
    name="Migrate Policy",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms1g",
    log4j2_properties="status = error",
)
Connection.objects.create(
    name="Migrate Conn",
    connection_type=Connection.ConnectionType.AGENT,
    host="127.0.0.1",
    policy=policy,
    status_blob={"health": "green", "n": 1},
)
"""

_COUNT = """
import json
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.contrib.auth import get_user_model
from PipelineManager.models import Connection, Policy
User = get_user_model()
conn = Connection.objects.filter(name="Migrate Conn").first()
print(json.dumps({
    "users": User.objects.count(),
    "policies": Policy.objects.count(),
    "migrate_user": User.objects.filter(username="migrate-user").count(),
    "migrate_policy": Policy.objects.filter(name="Migrate Policy").count(),
    "status_blob": conn.status_blob if conn else None,
}))
"""

_POST_MIGRATE_INSERT = """
import json
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.create_user(username="post-migrate-user", password="x")
assert u.pk is not None
print(json.dumps({"pk": u.pk}))
"""

_TARGET_KEYS = (
    "LOGSTASHUI_DATA_DIR",
    "LOGSTASHUI_DB_ENGINE",
    "LOGSTASHUI_DB_HOST",
    "LOGSTASHUI_DB_PORT",
    "LOGSTASHUI_DB_USER",
    "LOGSTASHUI_DB_PASSWORD",
    "LOGSTASHUI_DB_NAME",
)


# ---------------------------------------------------------------------------
# Core migration helper
# ---------------------------------------------------------------------------


def _run_to(tmp_path, target_env: dict[str, str]) -> dict:
    """
    Seed a fresh SQLite database, run cmd_migrate_engine to the target,
    then assert data counts.  Returns the parsed count dict.
    """
    data_dir = tmp_path
    sqlite_path = data_dir / "db.sqlite3"
    sqlite_env = {
        "LOGSTASHUI_DATA_DIR": str(data_dir),
        "LOGSTASHUI_DB_ENGINE": "sqlite",
        "LOGSTASHUI_DB_NAME": str(sqlite_path),
    }
    me.run_manage(["migrate", "--noinput", "--verbosity", "0"], sqlite_env)
    _run_python(_SEED, sqlite_env)

    full_target = {**target_env, "LOGSTASHUI_DATA_DIR": str(data_dir)}
    previous = {key: os.environ.get(key) for key in _TARGET_KEYS}
    try:
        os.environ.update(full_target)
        ns = Namespace(
            to=full_target["LOGSTASHUI_DB_ENGINE"],
            i_have_a_backup=True,
            pid=None,
            write_env=None,
        )
        try:
            rc = me.cmd_migrate_engine(ns)
        except SystemExit as exc:
            raise AssertionError(f"cmd_migrate_engine SystemExit {exc.code}") from exc
        assert rc == 0
        raw = _run_python(_COUNT, full_target)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    counts = json.loads(raw.strip().splitlines()[-1])
    assert counts["users"] >= 1
    assert counts["policies"] >= 1
    assert counts["migrate_user"] == 1
    assert counts["migrate_policy"] == 1
    assert counts["status_blob"] == {"health": "green", "n": 1}
    return counts


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_migrate_engine_to_postgres(postgres_container, tmp_path):
    dbname = new_dbname()
    base = pg_env(postgres_container)
    create_pg_db(base, dbname)
    try:
        target = pg_env(postgres_container, dbname=dbname)
        _run_to(tmp_path, target)
    finally:
        drop_pg_db(base, dbname)


def test_migrate_engine_to_mysql(mysql_container, tmp_path):
    dbname = new_dbname()
    base = mysql_env(mysql_container)
    create_mysql_db(base, dbname)
    try:
        target = mysql_env(mysql_container, dbname=dbname)
        _run_to(tmp_path, target)
    finally:
        drop_mysql_db(base, dbname)


def test_migrate_engine_to_mariadb(mariadb_container, tmp_path):
    dbname = new_dbname()
    base = mysql_env(mariadb_container)
    create_mysql_db(base, dbname)
    try:
        target = mysql_env(mariadb_container, dbname=dbname)
        _run_to(tmp_path, target)
    finally:
        drop_mysql_db(base, dbname)


def test_sequence_reset_postgres(postgres_container, tmp_path):
    """After SQLite→Postgres migration, inserting a new User does not fail on sequence."""
    dbname = new_dbname()
    base = pg_env(postgres_container)
    create_pg_db(base, dbname)
    try:
        target = pg_env(postgres_container, dbname=dbname)
        _run_to(tmp_path, target)
        full_env = {**target, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
        out = _run_python(_POST_MIGRATE_INSERT, full_env)
        result = json.loads(out.strip())
        assert isinstance(result["pk"], int) and result["pk"] > 0
    finally:
        drop_pg_db(base, dbname)


def test_migrate_engine_write_env(postgres_container, tmp_path):
    """--write-env produces a file with engine/host keys but no PASSWORD."""
    dbname = new_dbname()
    base = pg_env(postgres_container)
    create_pg_db(base, dbname)
    env_file = tmp_path / "logstashui.env"
    try:
        target = pg_env(postgres_container, dbname=dbname)
        full_target = {**target, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
        sqlite_path = tmp_path / "db.sqlite3"
        sqlite_env = {
            "LOGSTASHUI_DATA_DIR": str(tmp_path),
            "LOGSTASHUI_DB_ENGINE": "sqlite",
            "LOGSTASHUI_DB_NAME": str(sqlite_path),
        }
        me.run_manage(["migrate", "--noinput", "--verbosity", "0"], sqlite_env)
        _run_python(_SEED, sqlite_env)
        previous = {key: os.environ.get(key) for key in _TARGET_KEYS}
        try:
            os.environ.update(full_target)
            ns = Namespace(
                to="postgresql",
                i_have_a_backup=True,
                pid=None,
                write_env=str(env_file),
            )
            rc = me.cmd_migrate_engine(ns)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        assert rc == 0
        text = env_file.read_text()
        assert "LOGSTASHUI_DB_ENGINE=postgresql" in text
        assert "LOGSTASHUI_DB_HOST=" in text
        assert "PASSWORD" not in text
    finally:
        drop_pg_db(base, dbname)


def test_migrate_engine_idempotent_env(postgres_container, tmp_path):
    """Running write_env twice produces no duplicate keys in the output file."""
    dbname = new_dbname()
    base = pg_env(postgres_container)
    create_pg_db(base, dbname)
    env_file = tmp_path / "logstashui.env"
    try:
        target = pg_env(postgres_container, dbname=dbname)
        full_target = {**target, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
        # Run migration once
        _run_to(tmp_path, target)
        # write_env twice, pointing at the already-migrated DB
        me.write_env_file(env_file, "postgresql")
        me.write_env_file(env_file, "postgresql")
        text = env_file.read_text()
        assert text.count("LOGSTASHUI_DB_ENGINE=postgresql") == 1
    finally:
        drop_pg_db(base, dbname)
