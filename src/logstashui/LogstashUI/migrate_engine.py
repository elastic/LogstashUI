#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""BETA: copy SQLite data to PostgreSQL or MySQL. Stops gunicorn; does not restart serve."""

from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from argparse import Namespace
from pathlib import Path

from LogstashUI.database import canonical_engine
from LogstashUI.paths import resolve_data_dir

_TARGET_ENGINES = frozenset({"postgresql", "mysql"})
_DUMPDATA_EXCLUDES = ("contenttypes", "auth.permission", "sessions")


def run_manage(argv: list[str], extra_env: dict[str, str]) -> None:
    env = os.environ.copy()
    env.update(extra_env)
    env.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    code = (
        "import sys; from django.core.management import execute_from_command_line; "
        "execute_from_command_line(['logstashui'] + sys.argv[1:])"
    )
    cmd = [sys.executable, "-c", code, *argv]
    proc = subprocess.run(cmd, env=env, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def wal_checkpoint(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def stop_gunicorn(pidfile: Path) -> None:
    pid = int(pidfile.read_text(encoding="utf-8").strip())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 30
    while True:
        time.sleep(0.2)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        if time.monotonic() >= deadline:
            print(
                f"gunicorn pid {pid} did not exit within 30s after SIGTERM",
                file=sys.stderr,
            )
            raise SystemExit(1)


def write_env_file(path: Path, engine: str) -> None:
    pairs = [
        ("LOGSTASHUI_DB_ENGINE", engine),
        ("LOGSTASHUI_DB_NAME", os.environ.get("LOGSTASHUI_DB_NAME")),
        ("LOGSTASHUI_DB_HOST", os.environ.get("LOGSTASHUI_DB_HOST")),
        ("LOGSTASHUI_DB_PORT", os.environ.get("LOGSTASHUI_DB_PORT")),
        ("LOGSTASHUI_DB_USER", os.environ.get("LOGSTASHUI_DB_USER")),
    ]
    lines = [f"{key}={value}" for key, value in pairs if value]
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(prefix + "\n".join(lines) + "\n")


def _sqlsequencereset_to_dbshell(extra_env: dict[str, str]) -> None:
    env = os.environ.copy()
    env.update(extra_env)
    env.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    reset_code = (
        "import os, django\n"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LogstashUI.settings')\n"
        "django.setup()\n"
        "from django.apps import apps\n"
        "from django.core.management import call_command\n"
        "labels = [c.label for c in apps.get_app_configs() if c.models_module]\n"
        "call_command('sqlsequencereset', *labels)\n"
    )
    reset = subprocess.run(
        [sys.executable, "-c", reset_code],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if reset.returncode != 0:
        sys.stderr.write(reset.stderr or "")
        raise SystemExit(reset.returncode)
    dbshell_code = (
        "import sys; from django.core.management import execute_from_command_line; "
        "execute_from_command_line(['logstashui'] + sys.argv[1:])"
    )
    proc = subprocess.run(
        [sys.executable, "-c", dbshell_code, "dbshell"],
        env=env,
        input=reset.stdout,
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "")
        raise SystemExit(proc.returncode)


def cmd_migrate_engine(args: Namespace) -> int:
    if not args.i_have_a_backup:
        print(
            "Refusing to run migrate-engine without --i-have-a-backup. "
            "Back up db.sqlite3 (and the WAL) before copying data to another engine.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    try:
        engine = canonical_engine(getattr(args, "to", None))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    if engine not in _TARGET_ENGINES:
        print(
            f"migrate-engine --to must be postgresql or mysql, not {engine}.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    data_dir = resolve_data_dir(migrate_legacy=False)
    sqlite_path = data_dir / "db.sqlite3"
    if not sqlite_path.is_file():
        print(
            f"SQLite database not found: {sqlite_path} (expected db.sqlite3).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(
        "BETA: migrate-engine stops gunicorn and does not restart serve. "
        "Start `logstashui serve` yourself after verifying the target database.",
        file=sys.stderr,
    )

    pidfile = Path(args.pid) if args.pid is not None else data_dir / "gunicorn.pid"
    if pidfile.is_file():
        stop_gunicorn(pidfile)

    wal_checkpoint(sqlite_path)

    dump_fd, dump_name = tempfile.mkstemp(prefix="logstashui-migrate-", suffix=".json")
    os.close(dump_fd)
    dump_path = Path(dump_name)
    sqlite_env = {
        "LOGSTASHUI_DB_ENGINE": "sqlite",
        "LOGSTASHUI_DB_NAME": str(sqlite_path),
    }
    target_env = {"LOGSTASHUI_DB_ENGINE": engine}
    dump_argv = [
        "dumpdata",
        "--natural-foreign",
        "--natural-primary",
        "--output",
        str(dump_path),
    ]
    for label in _DUMPDATA_EXCLUDES:
        dump_argv.extend(["--exclude", label])
    try:
        run_manage(dump_argv, sqlite_env)
        run_manage(["migrate", "--noinput"], target_env)
        run_manage(["loaddata", str(dump_path)], target_env)
        if engine == "postgresql":
            _sqlsequencereset_to_dbshell(target_env)
    finally:
        dump_path.unlink(missing_ok=True)

    if args.write_env is not None:
        write_env_file(Path(args.write_env), engine)

    return 0
