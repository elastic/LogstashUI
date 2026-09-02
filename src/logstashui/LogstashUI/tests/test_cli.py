#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from argparse import Namespace

from django.core.management.base import CommandError

from LogstashUI.cli import build_parser, cmd_serve, install_systemd


def test_parser_defaults_to_serve():
    parser = build_parser()
    ns = parser.parse_args([])
    assert ns.command == "serve"


def test_parser_manage_passthrough():
    parser = build_parser()
    ns = parser.parse_args(["manage", "migrate", "--noinput"])
    assert ns.command == "manage"
    assert ns.manage_args == ["migrate", "--noinput"]


def test_systemd_dry_run_writes_unit_and_default(tmp_path):
    result = install_systemd(
        output_dir=tmp_path,
        exec_start="/usr/bin/logstashui serve",
        user="logstashui",
        group="logstashui",
        data_dir="/var/lib/logstashui",
        bind="0.0.0.0:8443",
        workers=2,
        allowed_hosts="ui.example",
        csrf_trusted_origins="https://ui.example:8443",
        tls="true",
        host_hostname="ui.example",
        host_ips="10.0.0.5",
        tls_sans="ui.example,10.0.0.5",
        agent_ui_url="https://ui.example:8443",
        no_auth="false",
        dry_run=True,
    )
    unit = tmp_path / "logstashui.service"
    envf = tmp_path / "logstashui.default"
    assert unit.is_file()
    assert envf.is_file()
    unit_text = unit.read_text()
    env_text = envf.read_text()
    assert "EnvironmentFile=-/etc/default/logstashui" in unit_text
    assert "ExecStart=/usr/bin/logstashui serve" in unit_text
    assert "User=logstashui" in unit_text
    assert "LOGSTASHUI_DATA_DIR=/var/lib/logstashui" in env_text
    assert "LOGSTASHUI_BIND=0.0.0.0:8443" in env_text
    assert "LOGSTASHUI_NO_AUTH=false" in env_text
    assert result["unit"] == unit
    assert result["default"] == envf
    assert "LOGSTASHUI_DB_ENGINE=postgresql" not in env_text
    assert "# LOGSTASHUI_DB_ENGINE=sqlite" in env_text


def test_systemd_env_includes_postgres_when_passed(tmp_path):
    result = install_systemd(
        output_dir=tmp_path,
        exec_start="/usr/bin/logstashui serve",
        user="logstashui",
        group="logstashui",
        data_dir="/var/lib/logstashui",
        bind="0.0.0.0:8443",
        workers=2,
        allowed_hosts="*",
        csrf_trusted_origins="",
        tls="true",
        host_hostname="",
        host_ips="",
        tls_sans="",
        agent_ui_url="",
        no_auth="false",
        dry_run=True,
        db_engine="postgresql",
        db_host="db.example",
        db_port="5432",
        db_name="logstashui",
        db_user="lsui",
    )
    text = (tmp_path / "logstashui.default").read_text()
    assert "LOGSTASHUI_DB_ENGINE=postgresql" in text
    assert "LOGSTASHUI_DB_HOST=db.example" in text
    assert "LOGSTASHUI_DB_PORT=5432" in text
    assert "LOGSTASHUI_DB_NAME=logstashui" in text
    assert "LOGSTASHUI_DB_USER=lsui" in text
    assert result["default"] == tmp_path / "logstashui.default"


def test_serve_snmp_commanderror_does_not_abort(monkeypatch):
    """execute_from_command_line sys.exits on CommandError; call_command must not."""
    from LogstashUI import cli

    monkeypatch.setattr(cli, "_manage", lambda argv: None)
    monkeypatch.setattr(cli, "_check_db_floor", lambda: None)
    monkeypatch.setenv("LOGSTASHUI_TLS", "false")

    def fake_call(name, *args, **kwargs):
        if name == "sync_snmp_official_data":
            raise CommandError("sync failed")
        return None

    monkeypatch.setattr("django.core.management.call_command", fake_call)

    exec_called = {}

    def fake_execvp(file, args):
        exec_called["file"] = file
        raise SystemExit(0)

    monkeypatch.setattr(cli.os, "execvp", fake_execvp)

    ns = Namespace(skip_migrate=False, no_tls=True, bind="127.0.0.1:8443", workers=1)
    try:
        cmd_serve(ns)
    except SystemExit as exc:
        assert exc.code == 0
    assert exec_called.get("file") == "gunicorn"


def test_parser_migrate_engine_requires_backup_flag():
    parser = build_parser()
    ns = parser.parse_args(["migrate-engine", "--to", "postgresql"])
    assert ns.command == "migrate-engine"
    assert ns.to == "postgresql"
    assert ns.i_have_a_backup is False


def test_parser_migrate_engine_accepts_mariadb_alias():
    parser = build_parser()
    ns = parser.parse_args(["migrate-engine", "--to", "mariadb", "--i-have-a-backup"])
    assert ns.to == "mariadb"
    assert ns.i_have_a_backup is True


def test_serve_checks_version_before_migrate(monkeypatch):
    from LogstashUI import cli

    order = []
    monkeypatch.setattr(cli, "_check_db_floor", lambda: order.append("check"))
    monkeypatch.setattr(cli, "_manage", lambda argv: order.append(argv[0]))
    monkeypatch.setattr(cli, "_best_effort_call", lambda *a, **k: None)
    monkeypatch.setenv("LOGSTASHUI_TLS", "false")

    def fake_execvp(file, args):
        raise SystemExit(0)

    monkeypatch.setattr(cli.os, "execvp", fake_execvp)
    ns = Namespace(skip_migrate=False, no_tls=True, bind="127.0.0.1:8443", workers=1)
    try:
        cmd_serve(ns)
    except SystemExit:
        pass
    assert order[0] == "check"
    assert "migrate" in order


def test_serve_checks_version_when_skip_migrate(monkeypatch, tmp_path):
    from LogstashUI import cli

    called = []
    monkeypatch.setattr(cli, "_check_db_floor", lambda: called.append(True))
    monkeypatch.setattr(cli, "_manage", lambda argv: None)
    monkeypatch.setenv("LOGSTASHUI_TLS", "false")
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", str(tmp_path))

    def fake_execvp(file, args):
        raise SystemExit(0)

    monkeypatch.setattr(cli.os, "execvp", fake_execvp)
    ns = Namespace(skip_migrate=True, no_tls=True, bind="127.0.0.1:8443", workers=1)
    try:
        cmd_serve(ns)
    except SystemExit:
        pass
    assert called == [True]


def test_serve_adds_pidfile_and_warns_sqlite(monkeypatch, tmp_path, capsys):
    from LogstashUI import cli

    monkeypatch.setattr(cli, "_manage", lambda argv: None)
    monkeypatch.setattr(cli, "_check_db_floor", lambda: None)
    monkeypatch.setenv("LOGSTASHUI_TLS", "false")
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LOGSTASHUI_DB_ENGINE", raising=False)

    captured = {}

    def fake_execvp(file, args):
        captured["file"] = file
        captured["args"] = list(args)
        raise SystemExit(0)

    monkeypatch.setattr(cli.os, "execvp", fake_execvp)
    ns = Namespace(skip_migrate=True, no_tls=True, bind="127.0.0.1:8443", workers=2)
    try:
        cmd_serve(ns)
    except SystemExit:
        pass
    assert "--pid" in captured["args"]
    pid_idx = captured["args"].index("--pid")
    assert captured["args"][pid_idx + 1].endswith("gunicorn.pid")
    err = capsys.readouterr().err
    assert "SQLite is the small-install default" in err

