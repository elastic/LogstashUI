#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from argparse import Namespace
from pathlib import Path

import pytest

from LogstashUI import migrate_engine as me


def test_refuses_without_backup_flag(capsys):
    ns = Namespace(to="postgresql", i_have_a_backup=False, pid=None, write_env=None)
    with pytest.raises(SystemExit) as exc:
        me.cmd_migrate_engine(ns)
    assert exc.value.code == 2
    assert "back up" in capsys.readouterr().err.lower()


def test_refuses_sqlite_target(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", str(tmp_path))
    ns = Namespace(to="sqlite", i_have_a_backup=True, pid=None, write_env=None)
    with pytest.raises(SystemExit):
        me.cmd_migrate_engine(ns)


def test_refuses_missing_sqlite_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", str(tmp_path))
    ns = Namespace(to="postgresql", i_have_a_backup=True, pid=None, write_env=None)
    with pytest.raises(SystemExit) as exc:
        me.cmd_migrate_engine(ns)
    assert exc.value.code == 1
    assert "db.sqlite3" in capsys.readouterr().err


def test_stop_pid_sends_sigterm(tmp_path, monkeypatch):
    pidfile = tmp_path / "gunicorn.pid"
    pidfile.write_text("4242\n")
    sent = {}
    calls = {"n": 0}

    def kill_then_gone(pid, sig):
        calls["n"] += 1
        if calls["n"] == 1:
            sent["pid"] = pid
            sent["sig"] = sig
            return
        raise ProcessLookupError()

    monkeypatch.setattr(me.os, "kill", kill_then_gone)
    monkeypatch.setattr(me.time, "sleep", lambda s: None)
    me.stop_gunicorn(pidfile)
    assert sent["pid"] == 4242
    assert sent["sig"] == me.signal.SIGTERM
    assert not pidfile.exists()


def test_write_env_appends(tmp_path, monkeypatch):
    envf = tmp_path / "logstashui.default"
    envf.write_text("LOGSTASHUI_DATA_DIR=/var/lib/logstashui\n")
    monkeypatch.setenv("LOGSTASHUI_DB_HOST", "db.example")
    monkeypatch.setenv("LOGSTASHUI_DB_USER", "lsui")
    monkeypatch.setenv("LOGSTASHUI_DB_NAME", "logstashui")
    me.write_env_file(envf, "postgresql")
    text = envf.read_text()
    assert "LOGSTASHUI_DB_ENGINE=postgresql" in text
    assert "LOGSTASHUI_DB_HOST=db.example" in text
    assert "PASSWORD" not in text


def test_run_manage_sets_package_pythonpath(monkeypatch):
    captured = {}

    def fake_run(cmd, env=None, check=False):
        captured["env"] = env
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(me.subprocess, "run", fake_run)
    me.run_manage(["migrate", "--noinput"], {"LOGSTASHUI_DB_ENGINE": "sqlite"})
    pythonpath = captured["env"]["PYTHONPATH"]
    pkg_root = str(Path(me.__file__).resolve().parent.parent)
    assert pythonpath.split(me.os.pathsep)[0] == pkg_root


def test_reset_postgres_sequences_does_not_require_psql(monkeypatch):
    captured = {}

    def fake_run(cmd, env=None, check=False, capture_output=False, text=False):
        captured["cmd"] = cmd
        captured["env"] = env
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return Result()

    monkeypatch.setattr(me.subprocess, "run", fake_run)
    me._reset_postgres_sequences({"LOGSTASHUI_DB_ENGINE": "postgresql"})
    assert captured["cmd"][0] == me.sys.executable
    assert captured["cmd"][1] == "-c"
    code = captured["cmd"][2]
    assert "dbshell" not in code
    assert "psql" not in code
    assert "sequence_reset_sql" in code
    assert "cursor.execute" in code
    pkg_root = str(Path(me.__file__).resolve().parent.parent)
    assert captured["env"]["PYTHONPATH"].split(me.os.pathsep)[0] == pkg_root
