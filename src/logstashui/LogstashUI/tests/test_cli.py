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


def test_serve_snmp_commanderror_does_not_abort(monkeypatch):
    """execute_from_command_line sys.exits on CommandError; call_command must not."""
    from LogstashUI import cli

    monkeypatch.setattr(cli, "_manage", lambda argv: None)
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
