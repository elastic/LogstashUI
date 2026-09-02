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
