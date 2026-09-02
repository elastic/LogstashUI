#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""LogstashUI console script: serve, manage, systemd."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from importlib.resources import files
from pathlib import Path

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logstashui",
        description="Run LogstashUI, Django management commands, or install systemd units.",
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run gunicorn (migrate + TLS ensure first)")
    serve.add_argument(
        "--bind",
        default=os.environ.get("LOGSTASHUI_BIND", "0.0.0.0:8443"),
        help="Bind address (env LOGSTASHUI_BIND). Default 0.0.0.0:8443",
    )
    serve.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("LOGSTASHUI_WORKERS", "2")),
        help="Gunicorn workers (env LOGSTASHUI_WORKERS). Default 2",
    )
    serve.add_argument(
        "--no-tls",
        action="store_true",
        help="Serve HTTP (env LOGSTASHUI_TLS=false). For TLS-terminating ingress.",
    )
    serve.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Do not run migrate / SNMP sync / collectstatic on startup",
    )

    manage = sub.add_parser("manage", help="Django management command passthrough")
    manage.add_argument("manage_args", nargs=argparse.REMAINDER)

    migrate = sub.add_parser(
        "migrate-engine",
        help="BETA: copy SQLite data to PostgreSQL or MySQL (stops gunicorn)",
    )
    migrate.add_argument(
        "--to",
        required=True,
        choices=("postgresql", "mysql", "mariadb"),
        help="Target engine (mariadb is an alias of mysql)",
    )
    migrate.add_argument(
        "--i-have-a-backup",
        dest="i_have_a_backup",
        action="store_true",
        help="Required. Confirms db.sqlite3 was copied aside.",
    )
    migrate.add_argument("--pid", type=Path, default=None, help="gunicorn pidfile to signal")
    migrate.add_argument(
        "--write-env",
        type=Path,
        default=None,
        help="Append LOGSTASHUI_DB_* to this EnvironmentFile",
    )

    systemd = sub.add_parser(
        "systemd",
        help="Generate /etc/default/logstashui and the systemd unit (manual)",
    )
    systemd.add_argument(
        "--output-dir",
        type=Path,
        help="Write unit + env file here instead of /etc (implies dry-run)",
    )
    systemd.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="Print generated files to stdout and exit",
    )
    systemd.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use defaults / flags; do not prompt",
    )
    systemd.add_argument("--user", default="logstashui")
    systemd.add_argument("--group", default="logstashui")
    systemd.add_argument("--data-dir", default="/var/lib/logstashui")
    systemd.add_argument("--bind", default="0.0.0.0:8443")
    systemd.add_argument("--workers", type=int, default=2)
    systemd.add_argument("--allowed-hosts", default="*")
    systemd.add_argument("--csrf-trusted-origins", default="")
    systemd.add_argument("--host-hostname", default="")
    systemd.add_argument("--host-ips", default="")
    systemd.add_argument("--tls-sans", default="")
    systemd.add_argument("--agent-ui-url", default="")
    systemd.add_argument("--exec-start", default="")
    systemd.add_argument(
        "--tls",
        default="true",
        choices=("true", "false"),
    )
    systemd.add_argument(
        "--no-auth",
        default="false",
        choices=("true", "false"),
    )
    systemd.add_argument("--db-engine", default="")
    systemd.add_argument("--db-host", default="")
    systemd.add_argument("--db-name", default="")
    systemd.add_argument("--db-user", default="")
    systemd.add_argument("--db-port", default="")
    parser.set_defaults(
        command="serve",
        bind=os.environ.get("LOGSTASHUI_BIND", "0.0.0.0:8443"),
        workers=int(os.environ.get("LOGSTASHUI_WORKERS", "2")),
        no_tls=False,
        skip_migrate=False,
    )
    return parser


def _packaging_file(name: str) -> str:
    return files("LogstashUI.packaging").joinpath(name).read_text(encoding="utf-8")


def render_unit(*, exec_start: str, user: str, group: str, working_directory: str) -> str:
    template = _packaging_file("logstashui.service.in")
    return template.format(
        exec_start=exec_start,
        user=user,
        group=group,
        working_directory=working_directory,
    )


def render_default_env(
    *,
    data_dir: str,
    bind: str,
    workers: int,
    allowed_hosts: str,
    csrf_trusted_origins: str,
    tls: str,
    host_hostname: str,
    host_ips: str,
    tls_sans: str,
    agent_ui_url: str,
    no_auth: str,
    db_engine: str = "",
    db_host: str = "",
    db_name: str = "",
    db_user: str = "",
    db_port: str = "",
) -> str:
    sample = _packaging_file("logstashui.default")
    replacements = {
        "LOGSTASHUI_DATA_DIR=/var/lib/logstashui": f"LOGSTASHUI_DATA_DIR={data_dir}",
        "LOGSTASHUI_BIND=0.0.0.0:8443": f"LOGSTASHUI_BIND={bind}",
        "LOGSTASHUI_WORKERS=2": f"LOGSTASHUI_WORKERS={workers}",
        "LOGSTASHUI_TLS=true": f"LOGSTASHUI_TLS={tls}",
        "ALLOWED_HOSTS=*": f"ALLOWED_HOSTS={allowed_hosts}",
        "LOGSTASHUI_NO_AUTH=false": f"LOGSTASHUI_NO_AUTH={no_auth}",
        "LOGSTASHUI_INCLUDE_CA_FINGERPRINT=true": "LOGSTASHUI_INCLUDE_CA_FINGERPRINT=true",
    }
    text = sample
    for old, new in replacements.items():
        text = text.replace(old, new, 1)
    extras = []
    if csrf_trusted_origins:
        extras.append(f"CSRF_TRUSTED_ORIGINS={csrf_trusted_origins}")
    if host_hostname:
        extras.append(f"LOGSTASHUI_HOST_HOSTNAME={host_hostname}")
    if host_ips:
        extras.append(f"LOGSTASHUI_HOST_IPS={host_ips}")
    if tls_sans:
        extras.append(f"LOGSTASHUI_TLS_SANS={tls_sans}")
    if agent_ui_url:
        extras.append(f"LOGSTASHUI_AGENT_UI_URL={agent_ui_url}")
    from LogstashUI.database import canonical_engine

    if db_engine and canonical_engine(db_engine) != "sqlite":
        extras.append(f"LOGSTASHUI_DB_ENGINE={canonical_engine(db_engine)}")
        if db_host:
            extras.append(f"LOGSTASHUI_DB_HOST={db_host}")
        if db_port:
            extras.append(f"LOGSTASHUI_DB_PORT={db_port}")
        if db_name:
            extras.append(f"LOGSTASHUI_DB_NAME={db_name}")
        if db_user:
            extras.append(f"LOGSTASHUI_DB_USER={db_user}")
    if extras:
        text = text.rstrip() + "\n\n# Values from logstashui systemd\n" + "\n".join(extras) + "\n"
    return text


def _prompt(question: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def install_systemd(
    *,
    output_dir: Path | None = None,
    exec_start: str = "",
    user: str = "logstashui",
    group: str = "logstashui",
    data_dir: str = "/var/lib/logstashui",
    bind: str = "0.0.0.0:8443",
    workers: int = 2,
    allowed_hosts: str = "*",
    csrf_trusted_origins: str = "",
    tls: str = "true",
    host_hostname: str = "",
    host_ips: str = "",
    tls_sans: str = "",
    agent_ui_url: str = "",
    no_auth: str = "false",
    db_engine: str = "",
    db_host: str = "",
    db_name: str = "",
    db_user: str = "",
    db_port: str = "",
    dry_run: bool = False,
    print_only: bool = False,
    interactive: bool = False,
) -> dict:
    if interactive and not dry_run and output_dir is None:
        from LogstashUI.database import canonical_engine

        exec_start = _prompt(
            "Path to logstashui executable",
            exec_start or _default_exec_start(),
        )
        user = _prompt("System user", user)
        group = _prompt("System group", group)
        data_dir = _prompt("LOGSTASHUI_DATA_DIR", data_dir)
        bind = _prompt("Bind address", bind)
        workers = int(_prompt("Workers", str(workers)))
        allowed_hosts = _prompt("ALLOWED_HOSTS", allowed_hosts)
        csrf_trusted_origins = _prompt("CSRF_TRUSTED_ORIGINS", csrf_trusted_origins)
        tls = _prompt("LOGSTASHUI_TLS (true/false)", tls)
        host_hostname = _prompt("LOGSTASHUI_HOST_HOSTNAME", host_hostname)
        host_ips = _prompt("LOGSTASHUI_HOST_IPS", host_ips)
        tls_sans = _prompt("LOGSTASHUI_TLS_SANS", tls_sans)
        agent_ui_url = _prompt("LOGSTASHUI_AGENT_UI_URL", agent_ui_url)
        no_auth = _prompt("LOGSTASHUI_NO_AUTH (true/false)", no_auth)
        db_engine = _prompt(
            "LOGSTASHUI_DB_ENGINE (sqlite/postgresql/mysql)",
            db_engine or "sqlite",
        )
        if canonical_engine(db_engine) != "sqlite":
            db_host = _prompt("LOGSTASHUI_DB_HOST", db_host)
            db_port = _prompt("LOGSTASHUI_DB_PORT", db_port)
            db_name = _prompt("LOGSTASHUI_DB_NAME", db_name or "logstashui")
            db_user = _prompt("LOGSTASHUI_DB_USER", db_user)

    if not exec_start:
        exec_start = _default_exec_start()

    unit_text = render_unit(
        exec_start=exec_start,
        user=user,
        group=group,
        working_directory=data_dir,
    )
    env_text = render_default_env(
        data_dir=data_dir,
        bind=bind,
        workers=workers,
        allowed_hosts=allowed_hosts,
        csrf_trusted_origins=csrf_trusted_origins,
        tls=tls,
        host_hostname=host_hostname,
        host_ips=host_ips,
        tls_sans=tls_sans,
        agent_ui_url=agent_ui_url,
        no_auth=no_auth,
        db_engine=db_engine,
        db_host=db_host,
        db_name=db_name,
        db_user=db_user,
        db_port=db_port,
    )

    if print_only:
        print("----- /etc/systemd/system/logstashui.service -----")
        print(unit_text)
        print("----- /etc/default/logstashui -----")
        print(env_text)
        return {"unit": None, "default": None}

    if output_dir is not None or dry_run:
        dest = Path(output_dir) if output_dir is not None else Path.cwd()
        dest.mkdir(parents=True, exist_ok=True)
        unit_path = dest / "logstashui.service"
        default_path = dest / "logstashui.default"
        unit_path.write_text(unit_text, encoding="utf-8")
        default_path.write_text(env_text, encoding="utf-8")
        return {"unit": unit_path, "default": default_path}

    if os.geteuid() != 0:
        print(
            "logstashui systemd must run as root to write /etc/default/logstashui "
            "and /etc/systemd/system/logstashui.service.\n"
            "Re-run with sudo, or pass --output-dir / --print.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    unit_path = Path("/etc/systemd/system/logstashui.service")
    default_path = Path("/etc/default/logstashui")
    default_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(unit_text, encoding="utf-8")
    default_path.write_text(env_text, encoding="utf-8")
    os.chmod(default_path, 0o640)
    daemon = shutil.which("systemctl")
    if daemon:
        os.system(f"{daemon} daemon-reload")
    print(f"Wrote {unit_path}")
    print(f"Wrote {default_path}")
    print("Not enabled. When ready:")
    print(f"  systemctl enable --now {unit_path.name}")
    return {"unit": unit_path, "default": default_path}


def _default_exec_start() -> str:
    exe = shutil.which("logstashui") or sys.argv[0] or "logstashui"
    return f"{exe} serve"


def _django_setup() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    import django

    django.setup()


def _manage(argv: list[str]) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(["logstashui", *argv])


def _best_effort_call(name: str, **kwargs) -> None:
    """Run a Django command without sys.exit on CommandError (unlike _manage)."""
    from django.core.management import call_command
    from django.core.management.base import CommandError

    try:
        call_command(name, **kwargs)
    except (CommandError, Exception) as exc:
        print(f"Warning: {name} failed: {exc}", file=sys.stderr)


def _check_db_floor() -> None:
    """Connect and enforce engine version floors before migrate or gunicorn bind."""
    _django_setup()
    from django.db import connection

    from LogstashUI.database import check_server_version

    connection.ensure_connection()
    check_server_version(connection)


def _exec_gunicorn(gunicorn_cmd: list[str]) -> int:
    """Replace this process with gunicorn, or run it in-process when frozen.

    PyInstaller onedir has no ``gunicorn`` console script on PATH. Calling
    gunicorn's WSGI app in-process keeps ``--worker-class gevent``.
    """
    if getattr(sys, "frozen", False):
        from gunicorn.app.wsgiapp import run as gunicorn_run

        sys.argv = list(gunicorn_cmd)
        result = gunicorn_run()
        return int(result or 0)
    os.execvp("gunicorn", gunicorn_cmd)
    return 1


def cmd_serve(args: argparse.Namespace) -> int:
    from LogstashUI.database import canonical_engine
    from LogstashUI.paths import resolve_data_dir

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    tls_env = os.environ.get("LOGSTASHUI_TLS", "true")
    tls_on = not args.no_tls and tls_env.strip().lower() not in ("0", "false", "no", "off")

    engine = canonical_engine(os.environ.get("LOGSTASHUI_DB_ENGINE"))
    if engine == "sqlite" and args.workers > 1:
        msg = (
            "SQLite is the small-install default; use PostgreSQL or MySQL/MariaDB "
            "for concurrent agents (LOGSTASHUI_WORKERS>1)."
        )
        logger.warning(msg)
        print(msg, file=sys.stderr)

    _check_db_floor()
    if not args.skip_migrate:
        _manage(["migrate", "--noinput"])
        _best_effort_call("sync_snmp_official_data", cleanup=True)
        _best_effort_call("collectstatic", interactive=False)

    data_dir = resolve_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    gunicorn_cmd = [
        "gunicorn",
        "LogstashUI.wsgi:application",
        "--bind",
        args.bind,
        "--workers",
        str(args.workers),
        "--worker-class",
        "gevent",
        "--worker-connections",
        "1000",
        "--timeout",
        "60",
        "--access-logfile",
        "-",
        "--error-logfile",
        "-",
        "--pid",
        str(data_dir / "gunicorn.pid"),
    ]
    if tls_on:
        _django_setup()
        from django.conf import settings
        from Common.product_ca import (
            ensure_default_ui_server_cert,
            ui_server_cert_path,
            ui_server_key_path,
        )

        ensure_default_ui_server_cert()
        tls_dir = Path(settings.DATA_DIR) / "tls"
        cert = ui_server_cert_path()
        key = ui_server_key_path()
        chain = tls_dir / "ui-server.chain.crt"
        fullchain = tls_dir / "gunicorn-fullchain.pem"
        if chain.is_file():
            fullchain.write_bytes(cert.read_bytes() + chain.read_bytes())
        else:
            fullchain.write_bytes(cert.read_bytes())
        gunicorn_cmd += ["--certfile", str(fullchain), "--keyfile", str(key)]

    return _exec_gunicorn(gunicorn_cmd)


def cmd_systemd(args: argparse.Namespace) -> int:
    interactive = not args.non_interactive and sys.stdin.isatty() and args.output_dir is None
    dry_run = args.output_dir is not None
    install_systemd(
        output_dir=args.output_dir,
        exec_start=args.exec_start,
        user=args.user,
        group=args.group,
        data_dir=args.data_dir,
        bind=args.bind,
        workers=args.workers,
        allowed_hosts=args.allowed_hosts,
        csrf_trusted_origins=args.csrf_trusted_origins,
        tls=args.tls,
        host_hostname=args.host_hostname,
        host_ips=args.host_ips,
        tls_sans=args.tls_sans,
        agent_ui_url=args.agent_ui_url,
        no_auth=args.no_auth,
        db_engine=args.db_engine,
        db_host=args.db_host,
        db_name=args.db_name,
        db_user=args.db_user,
        db_port=args.db_port,
        dry_run=dry_run,
        print_only=args.print_only,
        interactive=interactive,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "serve"
    if command == "manage":
        _manage(list(args.manage_args or []))
        return 0
    if command == "systemd":
        return cmd_systemd(args)
    if command == "migrate-engine":
        from LogstashUI.migrate_engine import cmd_migrate_engine
        return cmd_migrate_engine(args)
    if command == "serve":
        if not hasattr(args, "bind"):
            args = parser.parse_args(["serve"])
        return cmd_serve(args)
    parser.error(f"unknown command {command}")
    return 2
