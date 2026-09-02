#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from argparse import Namespace
import json
import os
import subprocess
import sys

import pytest

from LogstashUI import migrate_engine as me

pytestmark = pytest.mark.skipif(
    os.environ.get("LOGSTASHUI_LIVE_DB") != "1",
    reason="set LOGSTASHUI_LIVE_DB=1 (bin/test_databases.sh)",
)

_SEED = """
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.contrib.auth import get_user_model
from PipelineManager.models import Policy
User = get_user_model()
User.objects.create_user(username="migrate-user", password="migrate-pass")
Policy.objects.create(
    name="Migrate Policy",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms1g",
    log4j2_properties="status = error",
)
"""

_COUNT = """
import json
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.contrib.auth import get_user_model
from PipelineManager.models import Policy
User = get_user_model()
print(json.dumps({
    "users": User.objects.count(),
    "policies": Policy.objects.count(),
    "migrate_user": User.objects.filter(username="migrate-user").count(),
    "migrate_policy": Policy.objects.filter(name="Migrate Policy").count(),
}))
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


def _run_to(tmp_path, engine: str, *, port: str, user: str) -> None:
    data_dir = tmp_path
    sqlite_path = data_dir / "db.sqlite3"
    sqlite_env = {
        "LOGSTASHUI_DATA_DIR": str(data_dir),
        "LOGSTASHUI_DB_ENGINE": "sqlite",
        "LOGSTASHUI_DB_NAME": str(sqlite_path),
    }
    me.run_manage(["migrate", "--noinput"], sqlite_env)
    _run_python(_SEED, sqlite_env)

    target = {
        "LOGSTASHUI_DATA_DIR": str(data_dir),
        "LOGSTASHUI_DB_ENGINE": engine,
        "LOGSTASHUI_DB_HOST": "127.0.0.1",
        "LOGSTASHUI_DB_PORT": str(port),
        "LOGSTASHUI_DB_USER": user,
        "LOGSTASHUI_DB_PASSWORD": os.environ.get(
            "LOGSTASHUI_LIVE_DB_PASSWORD", "logstashui"
        ),
        "LOGSTASHUI_DB_NAME": "logstashui_migrate",
    }
    previous = {key: os.environ.get(key) for key in _TARGET_KEYS}
    try:
        os.environ.update(target)
        ns = Namespace(to=engine, i_have_a_backup=True, pid=None, write_env=None)
        try:
            rc = me.cmd_migrate_engine(ns)
        except SystemExit as exc:
            raise AssertionError(f"cmd_migrate_engine SystemExit {exc.code}") from exc
        assert rc == 0
        raw = _run_python(_COUNT, target)
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


def test_live_postgres(tmp_path):
    _run_to(
        tmp_path,
        "postgresql",
        port=os.environ.get("LOGSTASHUI_LIVE_PG_PORT", "55432"),
        user=os.environ.get("LOGSTASHUI_LIVE_PG_USER", "logstashui"),
    )


def test_live_mariadb(tmp_path):
    _run_to(
        tmp_path,
        "mysql",
        port=os.environ.get("LOGSTASHUI_LIVE_MARIA_PORT", "53306"),
        user=os.environ.get("LOGSTASHUI_LIVE_DB_USER", "root"),
    )


def test_live_mysql(tmp_path):
    _run_to(
        tmp_path,
        "mysql",
        port=os.environ.get("LOGSTASHUI_LIVE_MYSQL_PORT", "53307"),
        user=os.environ.get("LOGSTASHUI_LIVE_DB_USER", "root"),
    )
