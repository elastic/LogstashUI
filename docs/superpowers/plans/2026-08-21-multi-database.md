# Multi-database (SQLite | PostgreSQL | MariaDB/MySQL) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let LogstashUI 0.5.2 run on SQLite (default), PostgreSQL, or MariaDB/MySQL via discrete `LOGSTASHUI_DB_*` env vars, with a BETA sqlite→server migrator and a local Docker test matrix.

**Architecture:** Do not add a CRUD/repository layer. Django ORM already abstracts queries. The only switch is `LogstashUI/database.py` → `DATABASES['default']`. Drivers are install extras; the Docker image installs `[databases]`. Gunicorn stays gevent. `psycopg[binary]>=3.2` cooperates with gunicorn’s gevent `patch_select` (psycopg ≥ 3.1.14); PyMySQL is the MySQL driver so the C `mysqlclient` does not block the hub. Migration is `dumpdata` / `migrate` / `loaddata` in **child processes** so Django settings never have to switch engines in-process.

**Tech Stack:** Django 6, Python 3.12–3.14, `psycopg[binary]`, PyMySQL, gunicorn/gevent, Docker Compose for Postgres 16 + MariaDB 11 + MySQL 8.0.

**Spec:** `docs/superpowers/specs/2026-08-21-multi-database-design.md`

**Context:** Work on the current branch (`feat/sqleng` or whatever the operator is on). Do not rotate the product CA. Do not put Postgres/MariaDB/MySQL in the smoke compose. Do not “fix” pre-existing pytest failures (`test_update_policy_default_policy_forbidden`, `test_delete_policy_default_policy_forbidden`, `test_clone_policy_success`) unless they fail **because of** engine differences.

Every new/edited `.py` file must keep the Elastic license header already used in this repo.

---

## File map

| File | Responsibility |
|---|---|
| `pyproject.toml` | Optional extras `[postgres]`, `[mysql]`, `[databases]` |
| `src/logstashui/LogstashUI/database.py` | Engine aliases, `DATABASES` dict, fail-fast, SSL/CONN, driver import, server version check |
| `src/logstashui/LogstashUI/migrate_engine.py` | BETA migrator: pidfile SIGTERM, WAL checkpoint, dump/load subprocesses, `--write-env` |
| `src/logstashui/LogstashUI/cli.py` | `migrate-engine` subcommand, gunicorn `--pid`, SQLite scale warning, systemd DB prompts |
| `src/logstashui/LogstashUI/wsgi.py` | Comment only: gevent+psycopg is automatic at ≥ 3.1.14 |
| `src/logstashui/LogstashUI/packaging/logstashui.default` | Documented `LOGSTASHUI_DB_*` keys |
| `src/logstashui/LogstashUI/tests/test_database.py` | Unit tests for `build_databases` / version check (no live server) |
| `src/logstashui/LogstashUI/tests/test_migrate_engine.py` | Unit tests for migrator (mocked subprocess / pid) |
| `src/logstashui/LogstashUI/tests/test_cli.py` | Parser + serve pid + warning |
| `src/logstashui/LogstashUI/tests/test_migrate_live.py` | Live dump/load; skipped unless `LOGSTASHUI_LIVE_DB=1` |
| `docker/docker-compose.db.yml` | Postgres, MariaDB, MySQL for local/CI |
| `bin/test_databases.sh` / `bin/test_databases.bat` | SQLite pytest + three-engine pytest + live migrator |
| `docker/Dockerfile` | `uv pip install '/app[databases]'` |
| `docs/docs/logstashui/configuration/environment.md` | Env table + extras + scale warning + optional PgBouncer |
| `docs/docs/logstashui/general/deploy.md` | External DB + PVC still required + offline migrate |
| `CHANGELOG.md` | 0.5.2 section |
| `.github/workflows/test-databases.yml` | CI runs `bin/test_databases.sh` |
| `scripts/generate_notice.py` | Map psycopg / PyMySQL licenses |

No new DAO modules. No YAML. No `DATABASE_URL`.

---

### Task 1: Install extras in pyproject.toml

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` (via `uv lock`)
- Modify: `scripts/generate_notice.py` (repository mappings only)

- [ ] **Step 1: Add optional-dependencies after `[project.urls]`**

In `pyproject.toml`, immediately after the `[project.urls]` block, insert:

```toml
[project.optional-dependencies]
postgres = [
    "psycopg[binary]>=3.2.0",
]
mysql = [
    "PyMySQL>=1.1.1",
]
databases = [
    "psycopg[binary]>=3.2.0",
    "PyMySQL>=1.1.1",
]
```

Do **not** add these to the default `[project].dependencies` list. Default `pip install LogstashUI` must stay SQLite-only.

- [ ] **Step 2: Map licenses so NOTICE can mention extras**

In `scripts/generate_notice.py`, add to `REPOSITORY_MAPPINGS`:

```python
    "psycopg": "https://github.com/psycopg/psycopg/blob/master/LICENSE.txt",
    "psycopg-binary": "https://github.com/psycopg/psycopg/blob/master/LICENSE.txt",
    "PyMySQL": "https://github.com/PyMySQL/PyMySQL/blob/main/LICENSE",
```

And to `CUSTOM_DEPENDENCIES` so extras are documented even when not in the default wheel:

```python
    "psycopg": "https://github.com/psycopg/psycopg/blob/master/LICENSE.txt",
    "PyMySQL": "https://github.com/PyMySQL/PyMySQL/blob/main/LICENSE",
```

- [ ] **Step 3: Lock**

Run:

```bash
uv lock
```

Expected: `uv.lock` updates; no change to the default resolved production set beyond optional extra packages.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock scripts/generate_notice.py
git commit -m "build: add postgres/mysql/databases install extras"
```

---

### Task 2: Failing unit tests for `build_databases`

**Files:**
- Modify: `src/logstashui/LogstashUI/tests/test_database.py`

- [ ] **Step 1: Replace `test_database.py` with the suite below**

Overwrite `src/logstashui/LogstashUI/tests/test_database.py` with:

```python
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from pathlib import Path

import pytest

from LogstashUI.database import (
    build_databases,
    canonical_engine,
    check_server_version,
)


def _clear_db_env(monkeypatch):
    for name in (
        "LOGSTASHUI_DB_ENGINE",
        "LOGSTASHUI_DB_NAME",
        "LOGSTASHUI_DB_HOST",
        "LOGSTASHUI_DB_PORT",
        "LOGSTASHUI_DB_USER",
        "LOGSTASHUI_DB_PASSWORD",
        "LOGSTASHUI_DB_SSLMODE",
        "LOGSTASHUI_DB_SSL_CA",
        "LOGSTASHUI_DB_CONN_MAX_AGE",
        "LOGSTASHUI_DB_CONN_HEALTH_CHECKS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_build_databases_sqlite_default(tmp_path, monkeypatch):
    _clear_db_env(monkeypatch)
    db = build_databases(tmp_path)
    assert db["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert db["default"]["NAME"] == tmp_path / "db.sqlite3"
    assert db["default"]["OPTIONS"]["timeout"] == 20
    assert "PRAGMA journal_mode=WAL" in db["default"]["OPTIONS"]["init_command"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", "sqlite"),
        ("sqlite", "sqlite"),
        ("sqlite3", "sqlite"),
        ("postgres", "postgresql"),
        ("postgresql", "postgresql"),
        ("mysql", "mysql"),
        ("mariadb", "mysql"),
        ("my", "mysql"),
        ("POSTGRESQL", "postgresql"),
    ],
)
def test_canonical_engine_aliases(raw, expected):
    assert canonical_engine(raw) == expected


def test_unknown_engine_fails(tmp_path, monkeypatch):
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("LOGSTASHUI_DB_ENGINE", "oracle")
    with pytest.raises(RuntimeError, match="Unknown LOGSTASHUI_DB_ENGINE"):
        build_databases(tmp_path)


def test_postgresql_requires_host_user(tmp_path, monkeypatch):
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("LOGSTASHUI_DB_ENGINE", "postgresql")
    monkeypatch.setattr("LogstashUI.database._import_or_raise", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="LOGSTASHUI_DB_HOST"):
        build_databases(tmp_path)
    monkeypatch.setenv("LOGSTASHUI_DB_HOST", "db.example")
    with pytest.raises(RuntimeError, match="LOGSTASHUI_DB_USER"):
        build_databases(tmp_path)


def test_build_databases_postgresql(tmp_path, monkeypatch):
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("LOGSTASHUI_DB_ENGINE", "postgres")
    monkeypatch.setenv("LOGSTASHUI_DB_HOST", "db.example")
    monkeypatch.setenv("LOGSTASHUI_DB_USER", "lsui")
    monkeypatch.setenv("LOGSTASHUI_DB_PASSWORD", "s3cret")
    monkeypatch.setenv("LOGSTASHUI_DB_SSLMODE", "require")
    monkeypatch.setenv("LOGSTASHUI_DB_SSL_CA", "/etc/ssl/db-ca.pem")
    monkeypatch.setattr("LogstashUI.database._import_or_raise", lambda *a, **k: None)
    db = build_databases(tmp_path)["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert db["NAME"] == "logstashui"
    assert db["HOST"] == "db.example"
    assert db["PORT"] == "5432"
    assert db["USER"] == "lsui"
    assert db["PASSWORD"] == "s3cret"
    assert db["CONN_MAX_AGE"] == 60
    assert db["CONN_HEALTH_CHECKS"] is True
    assert db["OPTIONS"]["sslmode"] == "require"
    assert db["OPTIONS"]["sslrootcert"] == "/etc/ssl/db-ca.pem"


def test_build_databases_mysql_mariadb_alias(tmp_path, monkeypatch):
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("LOGSTASHUI_DB_ENGINE", "mariadb")
    monkeypatch.setenv("LOGSTASHUI_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("LOGSTASHUI_DB_USER", "lsui")
    monkeypatch.setenv("LOGSTASHUI_DB_PORT", "3307")
    monkeypatch.setenv("LOGSTASHUI_DB_CONN_MAX_AGE", "0")
    monkeypatch.setenv("LOGSTASHUI_DB_CONN_HEALTH_CHECKS", "false")
    monkeypatch.setattr("LogstashUI.database._import_or_raise", lambda *a, **k: None)
    db = build_databases(tmp_path)["default"]
    assert db["ENGINE"] == "django.db.backends.mysql"
    assert db["PORT"] == "3307"
    assert db["CONN_MAX_AGE"] == 0
    assert db["CONN_HEALTH_CHECKS"] is False
    assert db["OPTIONS"]["charset"] == "utf8mb4"
    assert "utf8mb4_bin" in db["OPTIONS"]["init_command"]
    assert db["TEST"]["CHARSET"] == "utf8mb4"
    assert db["TEST"]["COLLATION"] == "utf8mb4_bin"


def test_postgresql_missing_driver(tmp_path, monkeypatch):
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("LOGSTASHUI_DB_ENGINE", "postgresql")
    monkeypatch.setenv("LOGSTASHUI_DB_HOST", "localhost")
    monkeypatch.setenv("LOGSTASHUI_DB_USER", "lsui")

    def boom(module, extra):
        raise RuntimeError(
            f"{module} is not installed. Install with: uv pip install 'LogstashUI[{extra}]'"
        )

    monkeypatch.setattr("LogstashUI.database._import_or_raise", boom)
    with pytest.raises(RuntimeError, match=r"LogstashUI\[postgres\]"):
        build_databases(tmp_path)


def test_check_server_version_sqlite_noop():
    class Conn:
        vendor = "sqlite"

    check_server_version(Conn())


def test_check_server_version_postgres_too_old():
    class Conn:
        vendor = "postgresql"
        pg_version = 130000

    with pytest.raises(RuntimeError, match="PostgreSQL 14"):
        check_server_version(Conn())


def test_check_server_version_mysql_and_mariadb():
    class Mysql:
        vendor = "mysql"
        mysql_is_mariadb = False
        mysql_server_info = "8.0.36"

        def get_database_version(self):
            return (8, 0, 36)

    check_server_version(Mysql())

    class OldMysql:
        vendor = "mysql"
        mysql_is_mariadb = False
        mysql_server_info = "5.7.44"

        def get_database_version(self):
            return (5, 7, 44)

    with pytest.raises(RuntimeError, match="MySQL 8.0"):
        check_server_version(OldMysql())

    class Maria:
        vendor = "mysql"
        mysql_is_mariadb = True
        mysql_server_info = "10.5.22-MariaDB"

        def get_database_version(self):
            return (10, 5, 22)

    with pytest.raises(RuntimeError, match="MariaDB 10.6"):
        check_server_version(Maria())
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/buh/WORK/LogstashUI
uv run pytest src/logstashui/LogstashUI/tests/test_database.py -v --no-cov
```

Expected: FAIL — `canonical_engine`, `_import_or_raise`, and `check_server_version` are not defined; postgresql/mysql still raise “not implemented”.

- [ ] **Step 3: Commit tests**

```bash
git add src/logstashui/LogstashUI/tests/test_database.py
git commit -m "test: specify multi-engine build_databases behavior"
```

---

### Task 3: Implement `build_databases` and version check

**Files:**
- Modify: `src/logstashui/LogstashUI/database.py`

- [ ] **Step 1: Replace `database.py`**

Overwrite `src/logstashui/LogstashUI/database.py` with:

```python
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Build Django DATABASES from discrete LOGSTASHUI_DB_* environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from .config import env_bool

_ENGINE_ALIASES = {
    "": "sqlite",
    "sqlite": "sqlite",
    "sqlite3": "sqlite",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "mysql": "mysql",
    "mariadb": "mysql",
    "my": "mysql",
}

_CANONICAL = ("sqlite", "postgresql", "mysql")


def canonical_engine(raw: str | None) -> str:
    key = (raw or "").strip().lower()
    if key not in _ENGINE_ALIASES:
        supported = "sqlite, postgresql, mysql (aliases: sqlite3, postgres, mariadb, my)"
        raise RuntimeError(
            f"Unknown LOGSTASHUI_DB_ENGINE={raw!r}. Supported: {supported}."
        )
    return _ENGINE_ALIASES[key]


def _import_or_raise(module: str, extra: str) -> None:
    try:
        __import__(module)
    except ImportError as exc:
        raise RuntimeError(
            f"{module} is not installed. Install with: uv pip install 'LogstashUI[{extra}]' "
            f"(Docker/K8s image already includes LogstashUI[databases])."
        ) from exc


def _env(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name, "")
    if raw == "":
        return default
    return int(raw)


def _require(names: list[str]) -> None:
    missing = [n for n in names if not _env(n)]
    if missing:
        raise RuntimeError(
            "Missing required database settings: " + ", ".join(missing)
        )


def build_databases(data_dir: Path) -> dict:
    engine = canonical_engine(os.environ.get("LOGSTASHUI_DB_ENGINE"))
    conn_max_age = _env_int("LOGSTASHUI_DB_CONN_MAX_AGE", 60)
    health = env_bool("LOGSTASHUI_DB_CONN_HEALTH_CHECKS", True)

    if engine == "sqlite":
        name = _env("LOGSTASHUI_DB_NAME")
        db_name = Path(name) if name else Path(data_dir) / "db.sqlite3"
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": db_name,
                "CONN_MAX_AGE": conn_max_age,
                "CONN_HEALTH_CHECKS": health,
                "OPTIONS": {
                    "init_command": (
                        "PRAGMA busy_timeout=20000;"
                        "PRAGMA journal_mode=WAL;"
                    ),
                    "timeout": 20,
                },
            }
        }

    if engine == "postgresql":
        _import_or_raise("psycopg", "postgres")
        _require(["LOGSTASHUI_DB_HOST", "LOGSTASHUI_DB_USER"])
        sslmode = _env("LOGSTASHUI_DB_SSLMODE", "prefer") or "prefer"
        options: dict = {"sslmode": sslmode}
        ca = _env("LOGSTASHUI_DB_SSL_CA")
        if ca:
            options["sslrootcert"] = ca
        return {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": _env("LOGSTASHUI_DB_NAME", "logstashui") or "logstashui",
                "USER": _env("LOGSTASHUI_DB_USER"),
                "PASSWORD": os.environ.get("LOGSTASHUI_DB_PASSWORD") or "",
                "HOST": _env("LOGSTASHUI_DB_HOST"),
                "PORT": _env("LOGSTASHUI_DB_PORT", "5432") or "5432",
                "CONN_MAX_AGE": conn_max_age,
                "CONN_HEALTH_CHECKS": health,
                "OPTIONS": options,
            }
        }

    _import_or_raise("pymysql", "mysql")
    import pymysql

    pymysql.install_as_MySQLdb()
    _require(["LOGSTASHUI_DB_HOST", "LOGSTASHUI_DB_USER"])
    options = {
        "charset": "utf8mb4",
        "init_command": (
            "SET sql_mode='STRICT_TRANS_TABLES', "
            "NAMES utf8mb4 COLLATE utf8mb4_bin"
        ),
    }
    ca = _env("LOGSTASHUI_DB_SSL_CA")
    if ca:
        options["ssl"] = {"ca": ca}
    return {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": _env("LOGSTASHUI_DB_NAME", "logstashui") or "logstashui",
            "USER": _env("LOGSTASHUI_DB_USER"),
            "PASSWORD": os.environ.get("LOGSTASHUI_DB_PASSWORD") or "",
            "HOST": _env("LOGSTASHUI_DB_HOST"),
            "PORT": _env("LOGSTASHUI_DB_PORT", "3306") or "3306",
            "CONN_MAX_AGE": conn_max_age,
            "CONN_HEALTH_CHECKS": health,
            "OPTIONS": options,
            "TEST": {
                "CHARSET": "utf8mb4",
                "COLLATION": "utf8mb4_bin",
            },
        }
    }


def check_server_version(connection) -> None:
    """Fail-fast if the server is below documented floors. No-op for SQLite."""
    vendor = getattr(connection, "vendor", "")
    if vendor == "postgresql":
        pg_version = int(getattr(connection, "pg_version", 0) or 0)
        if pg_version and pg_version < 140000:
            raise RuntimeError(
                f"PostgreSQL 14+ is required (server_version_num={pg_version})."
            )
        return
    if vendor != "mysql":
        return
    is_mariadb = bool(getattr(connection, "mysql_is_mariadb", False))
    info = (getattr(connection, "mysql_server_info", "") or "").lower()
    if "mariadb" in info:
        is_mariadb = True
    if hasattr(connection, "get_database_version"):
        tup = connection.get_database_version()
    else:
        tup = (0, 0, 0)
    major_minor = (int(tup[0]), int(tup[1]))
    if is_mariadb and major_minor < (10, 6):
        raise RuntimeError(
            f"MariaDB 10.6+ is required (server={getattr(connection, 'mysql_server_info', tup)})."
        )
    if not is_mariadb and major_minor < (8, 0):
        raise RuntimeError(
            f"MySQL 8.0+ is required (server={getattr(connection, 'mysql_server_info', tup)})."
        )
```

- [ ] **Step 2: Run unit tests**

```bash
uv run pytest src/logstashui/LogstashUI/tests/test_database.py -v --no-cov
```

Expected: all PASS.

- [ ] **Step 3: Confirm default pytest still uses sqlite**

```bash
uv run pytest src/logstashui/LogstashUI/tests/test_database.py src/logstashui/LogstashUI/tests/test_paths.py -v --no-cov
```

Expected: PASS (paths tests still copy `db.sqlite3`).

- [ ] **Step 4: Commit**

```bash
git add src/logstashui/LogstashUI/database.py
git commit -m "feat: wire PostgreSQL and MySQL Django backends from env"
```

---

### Task 4: SQLite scale warning, gunicorn pidfile, version check on serve

**Files:**
- Modify: `src/logstashui/LogstashUI/cli.py`
- Modify: `src/logstashui/LogstashUI/tests/test_cli.py`
- Modify: `src/logstashui/LogstashUI/wsgi.py` (comment only)

- [ ] **Step 1: Add failing CLI tests**

Append to `src/logstashui/LogstashUI/tests/test_cli.py`:

```python
def test_parser_migrate_engine_requires_backup_flag():
    parser = build_parser()
    ns = parser.parse_args(["migrate-engine", "--to", "postgresql"])
    assert ns.command == "migrate-engine"
    assert ns.to == "postgresql"
    assert ns.i_have_a_backup is False


def test_serve_adds_pidfile_and_warns_sqlite(monkeypatch, tmp_path, capsys):
    from LogstashUI import cli

    monkeypatch.setattr(cli, "_manage", lambda argv: None)
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
```

- [ ] **Step 2: Run the new tests — expect FAIL**

```bash
uv run pytest src/logstashui/LogstashUI/tests/test_cli.py -v --no-cov
```

Expected: FAIL on unknown `migrate-engine` subparser and missing `--pid`.

- [ ] **Step 3: Implement CLI pieces**

In `build_parser()`, after the `manage` subparser, add:

```python
    migrate = sub.add_parser(
        "migrate-engine",
        help="BETA: copy SQLite data to PostgreSQL or MySQL (stops gunicorn)",
    )
    migrate.add_argument("--to", required=True, choices=("postgresql", "mysql"))
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
```

In `cmd_serve`, **before** building `gunicorn_cmd`:

```python
    import logging
    from .database import canonical_engine, check_server_version
    from .paths import resolve_data_dir

    engine = canonical_engine(os.environ.get("LOGSTASHUI_DB_ENGINE"))
    if engine == "sqlite" and int(args.workers) > 1:
        msg = (
            "SQLite is the small-install default; use PostgreSQL or MySQL/MariaDB "
            "for concurrent agents (LOGSTASHUI_WORKERS>1)."
        )
        logging.getLogger("LogstashUI").warning(msg)
        print(f"WARNING: {msg}", file=sys.stderr)
```

After migrate (still inside `if not args.skip_migrate`), after `_manage(["migrate", "--noinput"])`:

```python
        _django_setup()
        from django.db import connection

        check_server_version(connection)
```

When skip_migrate is true, still run version check only if Django can connect — skip if skip_migrate to keep tests simple. Version check stays tied to migrate path.

Add pidfile to `gunicorn_cmd` after `--error-logfile`:

```python
    data_dir = resolve_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    gunicorn_cmd += ["--pid", str(data_dir / "gunicorn.pid")]
```

`resolve_data_dir` lives in `LogstashUI.paths` and does not import Django. Import it at the top of `cli.py`:

```python
from .paths import resolve_data_dir
```

`cli.py` currently has no relative imports; it uses `from LogstashUI...` nowhere. Keep consistency with the rest of the file: use

```python
from LogstashUI.paths import resolve_data_dir
from LogstashUI.database import canonical_engine, check_server_version
```

Wire `main()`:

```python
    if command == "migrate-engine":
        from LogstashUI.migrate_engine import cmd_migrate_engine

        return cmd_migrate_engine(args)
```

For this task, `migrate_engine.py` does not exist yet. **Do not add the main() branch until Task 6.** Only add the argparse subparser so `test_parser_migrate_engine_requires_backup_flag` passes. Leave `main()` unchanged except serve.

In `wsgi.py`, above `application = get_wsgi_application()`, add this comment (no code):

```python
# gunicorn --worker-class gevent monkey-patches select before this module loads.
# psycopg 3.1.14+ detects that and waits cooperatively; do not use psycogreen.
```

- [ ] **Step 4: Re-run CLI tests**

```bash
uv run pytest src/logstashui/LogstashUI/tests/test_cli.py -v --no-cov
```

Expected: PASS (migrate-engine parser exists; serve pid + warning). `main()` still errors if someone runs migrate-engine — that is Task 6.

- [ ] **Step 5: Commit**

```bash
git add src/logstashui/LogstashUI/cli.py src/logstashui/LogstashUI/tests/test_cli.py src/logstashui/LogstashUI/wsgi.py
git commit -m "feat: gunicorn pidfile and SQLite scale warning"
```

---

### Task 5: Docker Compose DB matrix and `bin/test_databases.sh`

**Files:**
- Create: `docker/docker-compose.db.yml`
- Create: `bin/test_databases.sh`
- Create: `bin/test_databases.bat`
- Create: `src/logstashui/LogstashUI/tests/test_migrate_live.py` (skip unless env set — empty skip is enough this task)

- [ ] **Step 1: Write compose file**

Create `docker/docker-compose.db.yml`:

```yaml
# Local/CI database matrix for LogstashUI. Not used by smoke compose.
# Host ports avoid clashing with a developer’s own 5432/3306.
name: logstashui-db-test

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: logstashui
      POSTGRES_PASSWORD: logstashui
      POSTGRES_DB: logstashui
    ports:
      - "55432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U logstashui -d logstashui"]
      interval: 2s
      timeout: 5s
      retries: 30

  mariadb:
    image: mariadb:11
    environment:
      MARIADB_ROOT_PASSWORD: logstashui
      MARIADB_DATABASE: logstashui
      MARIADB_USER: logstashui
      MARIADB_PASSWORD: logstashui
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_bin
    ports:
      - "53306:3306"
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 3s
      timeout: 5s
      retries: 40

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: logstashui
      MYSQL_DATABASE: logstashui
      MYSQL_USER: logstashui
      MYSQL_PASSWORD: logstashui
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_bin
    ports:
      - "53307:3306"
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-ulogstashui", "-plogstashui"]
      interval: 3s
      timeout: 5s
      retries: 40
```

pytest-django must CREATE DATABASE. Postgres `POSTGRES_USER` is superuser. MariaDB/MySQL app users are not. **For the mysql/mariadb pytest runs, use root / logstashui** so Django can create `test_logstashui`.

- [ ] **Step 2: Write `bin/test_databases.sh`**

```bash
#!/usr/bin/env bash
# Run SQLite pytest, then the same suite against Postgres, MariaDB, and MySQL,
# then live dump/load tests. Requires Docker. Default `pytest` does not.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f docker/docker-compose.db.yml)
KEEP=0
if [[ "${1:-}" == "--keep" ]]; then
  KEEP=1
fi

if ! command -v docker >/dev/null; then
  echo "ERROR: Docker is required for bin/test_databases.sh" >&2
  echo "Default pytest (SQLite) still works: uv run pytest" >&2
  exit 1
fi

uv sync --extra databases --group dev

echo "==> SQLite pytest (no compose)"
uv run pytest src/logstashui --no-cov

echo "==> Starting Postgres / MariaDB / MySQL"
"${COMPOSE[@]}" up -d --wait

run_engine () {
  local name="$1"
  shift
  echo "==> pytest on ${name}"
  env "$@" uv run pytest src/logstashui --no-cov
}

run_engine postgresql \
  LOGSTASHUI_DB_ENGINE=postgresql \
  LOGSTASHUI_DB_HOST=127.0.0.1 \
  LOGSTASHUI_DB_PORT=55432 \
  LOGSTASHUI_DB_NAME=logstashui \
  LOGSTASHUI_DB_USER=logstashui \
  LOGSTASHUI_DB_PASSWORD=logstashui

run_engine mariadb \
  LOGSTASHUI_DB_ENGINE=mysql \
  LOGSTASHUI_DB_HOST=127.0.0.1 \
  LOGSTASHUI_DB_PORT=53306 \
  LOGSTASHUI_DB_NAME=logstashui \
  LOGSTASHUI_DB_USER=root \
  LOGSTASHUI_DB_PASSWORD=logstashui

run_engine mysql \
  LOGSTASHUI_DB_ENGINE=mysql \
  LOGSTASHUI_DB_HOST=127.0.0.1 \
  LOGSTASHUI_DB_PORT=53307 \
  LOGSTASHUI_DB_NAME=logstashui \
  LOGSTASHUI_DB_USER=root \
  LOGSTASHUI_DB_PASSWORD=logstashui

echo "==> Live migrator tests"
env LOGSTASHUI_LIVE_DB=1 \
  LOGSTASHUI_LIVE_PG_PORT=55432 \
  LOGSTASHUI_LIVE_MARIA_PORT=53306 \
  LOGSTASHUI_LIVE_MYSQL_PORT=53307 \
  LOGSTASHUI_LIVE_DB_USER=root \
  LOGSTASHUI_LIVE_DB_PASSWORD=logstashui \
  LOGSTASHUI_LIVE_PG_USER=logstashui \
  uv run pytest src/logstashui/LogstashUI/tests/test_migrate_live.py -v --no-cov

if [[ "$KEEP" -eq 0 ]]; then
  "${COMPOSE[@]}" down -v
fi
```

`chmod +x bin/test_databases.sh`

Until Task 7, `test_migrate_live.py` should skip (no `LOGSTASHUI_LIVE_DB` assertions yet — see Step 3). Running the live file with the env set will collect 0 tests or skip. Create a placeholder that skips:

```python
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LOGSTASHUI_LIVE_DB") != "1",
    reason="set LOGSTASHUI_LIVE_DB=1 (bin/test_databases.sh)",
)


def test_live_placeholder():
    pytest.skip("migrator live tests land in Task 7")
```

- [ ] **Step 3: Write `bin/test_databases.bat`**

```bat
@echo off
setlocal
cd /d "%~dp0\.."
where docker >nul 2>&1
if errorlevel 1 (
  echo ERROR: Docker is required for bin\test_databases.bat
  exit /b 1
)
uv sync --extra databases --group dev
uv run pytest src\logstashui --no-cov
if errorlevel 1 exit /b 1
docker compose -f docker\docker-compose.db.yml up -d --wait
if errorlevel 1 exit /b 1

set LOGSTASHUI_DB_ENGINE=postgresql
set LOGSTASHUI_DB_HOST=127.0.0.1
set LOGSTASHUI_DB_PORT=55432
set LOGSTASHUI_DB_NAME=logstashui
set LOGSTASHUI_DB_USER=logstashui
set LOGSTASHUI_DB_PASSWORD=logstashui
uv run pytest src\logstashui --no-cov
if errorlevel 1 goto :down

set LOGSTASHUI_DB_ENGINE=mysql
set LOGSTASHUI_DB_PORT=53306
set LOGSTASHUI_DB_USER=root
uv run pytest src\logstashui --no-cov
if errorlevel 1 goto :down

set LOGSTASHUI_DB_PORT=53307
uv run pytest src\logstashui --no-cov
if errorlevel 1 goto :down

set LOGSTASHUI_LIVE_DB=1
set LOGSTASHUI_LIVE_PG_PORT=55432
set LOGSTASHUI_LIVE_MARIA_PORT=53306
set LOGSTASHUI_LIVE_MYSQL_PORT=53307
uv run pytest src\logstashui\LogstashUI\tests\test_migrate_live.py -v --no-cov

:down
if /I not "%1"=="--keep" docker compose -f docker\docker-compose.db.yml down -v
```

- [ ] **Step 4: Smoke the compose file (not the full suite if too long — at least `up --wait`)**

```bash
docker compose -f docker/docker-compose.db.yml up -d --wait
docker compose -f docker/docker-compose.db.yml ps
docker compose -f docker/docker-compose.db.yml down -v
```

Expected: three services healthy, then removed.

Then run **one** engine pytest if time allows:

```bash
uv sync --extra databases --group dev
LOGSTASHUI_DB_ENGINE=postgresql LOGSTASHUI_DB_HOST=127.0.0.1 LOGSTASHUI_DB_PORT=55432 \
  LOGSTASHUI_DB_NAME=logstashui LOGSTASHUI_DB_USER=logstashui LOGSTASHUI_DB_PASSWORD=logstashui \
  uv run pytest src/logstashui/LogstashUI/tests/test_database.py src/logstashui/Site/tests/test_views.py::test_health_check_returns_200 --no-cov
```

(Bring compose back up first.) Expected: PASS. If `test_health_check` fails on migrate, fix charset/user and re-run. Known CRUD failures on sqlite may also appear on postgres — do not xfail them in this task.

- [ ] **Step 5: Commit**

```bash
git add docker/docker-compose.db.yml bin/test_databases.sh bin/test_databases.bat \
  src/logstashui/LogstashUI/tests/test_migrate_live.py
git commit -m "test: Docker Postgres/MariaDB/MySQL matrix script"
```

---

### Task 6: BETA `migrate-engine` (unit-tested, no live servers)

**Files:**
- Create: `src/logstashui/LogstashUI/migrate_engine.py`
- Create: `src/logstashui/LogstashUI/tests/test_migrate_engine.py`
- Modify: `src/logstashui/LogstashUI/cli.py` (`main()` branch)

- [ ] **Step 1: Write failing unit tests**

Create `src/logstashui/LogstashUI/tests/test_migrate_engine.py`:

```python
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
```

- [ ] **Step 2: Run — expect FAIL (module missing)**

```bash
uv run pytest src/logstashui/LogstashUI/tests/test_migrate_engine.py -v --no-cov
```

- [ ] **Step 3: Implement `migrate_engine.py`**

```python
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""BETA sqlite → PostgreSQL/MySQL copy via dumpdata/loaddata in child processes."""

from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from LogstashUI.database import canonical_engine
from LogstashUI.paths import resolve_data_dir

_DUMP_EXCLUDE = ["contenttypes", "auth.permission", "sessions"]
_SEQUENCE_APPS = [
    "admin",
    "auth",
    "PipelineManager",
    "Management",
    "SNMP",
    "AI",
    "Monitoring",
    "Site",
]


def cmd_migrate_engine(args) -> int:
    if not getattr(args, "i_have_a_backup", False):
        print(
            "BETA migrate-engine: copy DATA_DIR/db.sqlite3 to a backup first, "
            "then re-run with --i-have-a-backup.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    target = canonical_engine(getattr(args, "to", ""))
    if target not in ("postgresql", "mysql"):
        print(" --to must be postgresql or mysql", file=sys.stderr)
        raise SystemExit(2)

    data_dir = resolve_data_dir(migrate_legacy=False)
    sqlite_path = data_dir / "db.sqlite3"
    if not sqlite_path.is_file():
        print(f"No SQLite database at {sqlite_path}", file=sys.stderr)
        raise SystemExit(1)

    print(
        "BETA: migrate-engine stops gunicorn (UI port down), dumps SQLite, "
        "loads the target, and does not restart serve.",
        file=sys.stderr,
    )

    pidfile = args.pid or (data_dir / "gunicorn.pid")
    if Path(pidfile).is_file():
        stop_gunicorn(Path(pidfile))

    wal_checkpoint(sqlite_path)
    dump_path = data_dir / "migrate-engine-dump.json"
    run_manage(
        [
            "dumpdata",
            "--natural-foreign",
            "--natural-primary",
            "--output",
            str(dump_path),
            *[f"-e={item}" for item in _DUMP_EXCLUDE],
        ],
        extra_env={"LOGSTASHUI_DB_ENGINE": "sqlite"},
    )
    run_manage(["migrate", "--noinput"], extra_env={"LOGSTASHUI_DB_ENGINE": target})
    run_manage(["loaddata", str(dump_path)], extra_env={"LOGSTASHUI_DB_ENGINE": target})
    if target == "postgresql":
        reset_postgres_sequences(extra_env={"LOGSTASHUI_DB_ENGINE": target})

    if args.write_env:
        write_env_file(Path(args.write_env), target)

    print(
        "Done. Keep LOGSTASHUI_DB_ENGINE="
        f"{target} and start LogstashUI (systemctl start logstashui). "
        "Do not auto-restart: systemd Restart= would race."
    )
    return 0


def wal_checkpoint(sqlite_path: Path) -> None:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def stop_gunicorn(pidfile: Path) -> None:
    raw = pidfile.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        print(f"Invalid pidfile {pidfile}", file=sys.stderr)
        raise SystemExit(1)
    pid = int(raw)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pidfile.unlink(missing_ok=True)
        return
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pidfile.unlink(missing_ok=True)
            return
        time.sleep(0.2)
    print(f"gunicorn pid {pid} did not exit after SIGTERM", file=sys.stderr)
    raise SystemExit(1)


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


def reset_postgres_sequences(extra_env: dict[str, str]) -> None:
    env = os.environ.copy()
    env.update(extra_env)
    env.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    code = (
        "import sys; from django.core.management import execute_from_command_line; "
        "execute_from_command_line(['logstashui', 'sqlsequencereset'] + sys.argv[1:])"
    )
    sql = subprocess.run(
        [sys.executable, "-c", code, *_SEQUENCE_APPS],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if sql.returncode != 0:
        print(sql.stderr, file=sys.stderr)
        raise SystemExit(sql.returncode)
    if not sql.stdout.strip():
        return
    dbshell = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from django.core.management import execute_from_command_line; "
            "execute_from_command_line(['logstashui', 'dbshell'])",
        ],
        env=env,
        input=sql.stdout,
        text=True,
        check=False,
    )
    if dbshell.returncode != 0:
        raise SystemExit(dbshell.returncode)


def write_env_file(path: Path, engine: str) -> None:
    lines = [
        f"LOGSTASHUI_DB_ENGINE={engine}",
        f"LOGSTASHUI_DB_NAME={os.environ.get('LOGSTASHUI_DB_NAME', 'logstashui')}",
        f"LOGSTASHUI_DB_HOST={os.environ.get('LOGSTASHUI_DB_HOST', '')}",
        f"LOGSTASHUI_DB_PORT={os.environ.get('LOGSTASHUI_DB_PORT', '')}",
        f"LOGSTASHUI_DB_USER={os.environ.get('LOGSTASHUI_DB_USER', '')}",
    ]
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.write_text(existing.rstrip() + "\n\n# migrate-engine\n" + "\n".join(lines) + "\n")
```

`test_refuses_sqlite_target`: `canonical_engine("sqlite")` returns sqlite, then `target not in (...)` exits 2. argparse `choices` already blocks sqlite in CLI; the function still guards.

`test_stop_pid_sends_sigterm` uses `ProcessLookupError` on the wait loop — `os.kill(pid, 0)` raises, success.

Fix the test’s double-setattr: keep only `kill_then_gone`.

- [ ] **Step 4: Wire `main()` in `cli.py`**

```python
    if command == "migrate-engine":
        from LogstashUI.migrate_engine import cmd_migrate_engine

        return cmd_migrate_engine(args)
```

- [ ] **Step 5: Run unit tests**

```bash
uv run pytest src/logstashui/LogstashUI/tests/test_migrate_engine.py src/logstashui/LogstashUI/tests/test_cli.py -v --no-cov
```

Expected: PASS. If `test_refuses_sqlite_target` never hits `cmd_migrate_engine` because argparse isn’t used (Namespace to=sqlite), the guard in `cmd_migrate_engine` handles it.

- [ ] **Step 6: Commit**

```bash
git add src/logstashui/LogstashUI/migrate_engine.py \
  src/logstashui/LogstashUI/tests/test_migrate_engine.py \
  src/logstashui/LogstashUI/cli.py
git commit -m "feat: BETA migrate-engine sqlite to postgres/mysql"
```

---

### Task 7: Live migration tests

**Files:**
- Modify: `src/logstashui/LogstashUI/tests/test_migrate_live.py`

- [ ] **Step 1: Replace the placeholder with subprocess live tests**

Live tests must not use `@pytest.mark.django_db` and then switch `LOGSTASHUI_DB_ENGINE` in-process (Django settings are frozen). Use isolated `DATA_DIR` + child processes only.

Overwrite `src/logstashui/LogstashUI/tests/test_migrate_live.py` with:

```python
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from __future__ import annotations

import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from LogstashUI.migrate_engine import cmd_migrate_engine, run_manage

pytestmark = pytest.mark.skipif(
    os.environ.get("LOGSTASHUI_LIVE_DB") != "1",
    reason="set LOGSTASHUI_LIVE_DB=1 (bin/test_databases.sh)",
)


def _python_manage(args: list[str], env: dict[str, str]) -> None:
    run_manage(args, extra_env=env)


def _seed(data_dir: Path) -> None:
    env = {
        "LOGSTASHUI_DATA_DIR": str(data_dir),
        "LOGSTASHUI_DB_ENGINE": "sqlite",
        "DJANGO_SETTINGS_MODULE": "LogstashUI.settings",
    }
    _python_manage(["migrate", "--noinput"], env)
    code = (
        "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','LogstashUI.settings'); "
        "django.setup(); "
        "from django.contrib.auth.models import User; "
        "from PipelineManager.models import Policy; "
        "User.objects.create_user('migrate-user', password='x'); "
        "Policy.objects.create(name='Migrate Policy', logstash_yml='node.name: t', "
        "jvm_options='#', log4j2_properties='#')"
    )
    env_full = os.environ.copy()
    env_full.update(env)
    subprocess.run([sys.executable, "-c", code], env=env_full, check=True)


def _count(env: dict[str, str]) -> tuple[int, int]:
    env_full = os.environ.copy()
    env_full.update(env)
    env_full.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    code = (
        "import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','LogstashUI.settings'); "
        "django.setup(); "
        "from django.contrib.auth.models import User; "
        "from PipelineManager.models import Policy; "
        "print(User.objects.filter(username='migrate-user').count()); "
        "print(Policy.objects.filter(name='Migrate Policy').count())"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], env=env_full, check=True, capture_output=True, text=True
    )
    lines = [ln for ln in out.stdout.splitlines() if ln.strip().isdigit()]
    return int(lines[-2]), int(lines[-1])


def _run_to(tmp_path: Path, engine: str, port: str, user: str) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    os.environ["LOGSTASHUI_DATA_DIR"] = str(data_dir)
    _seed(data_dir)
    target = {
        "LOGSTASHUI_DB_ENGINE": engine,
        "LOGSTASHUI_DB_HOST": "127.0.0.1",
        "LOGSTASHUI_DB_PORT": port,
        "LOGSTASHUI_DB_NAME": "logstashui_migrate",
        "LOGSTASHUI_DB_USER": user,
        "LOGSTASHUI_DB_PASSWORD": os.environ.get("LOGSTASHUI_LIVE_DB_PASSWORD", "logstashui"),
    }
    for k, v in target.items():
        os.environ[k] = v
    ns = Namespace(to="postgresql" if engine == "postgresql" else "mysql", i_have_a_backup=True, pid=None, write_env=None)
    cmd_migrate_engine(ns)
    users, policies = _count(target | {"LOGSTASHUI_DATA_DIR": str(data_dir)})
    assert users == 1
    assert policies == 1


def test_live_postgres(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", str(tmp_path / "data"))
    _run_to(
        tmp_path,
        "postgresql",
        os.environ.get("LOGSTASHUI_LIVE_PG_PORT", "55432"),
        os.environ.get("LOGSTASHUI_LIVE_PG_USER", "logstashui"),
    )


def test_live_mariadb(tmp_path, monkeypatch):
    _run_to(
        tmp_path,
        "mysql",
        os.environ.get("LOGSTASHUI_LIVE_MARIA_PORT", "53306"),
        os.environ.get("LOGSTASHUI_LIVE_DB_USER", "root"),
    )


def test_live_mysql(tmp_path, monkeypatch):
    _run_to(
        tmp_path,
        "mysql",
        os.environ.get("LOGSTASHUI_LIVE_MYSQL_PORT", "53307"),
        os.environ.get("LOGSTASHUI_LIVE_DB_USER", "root"),
    )
```

Create the target database `logstashui_migrate` in each engine before load. Add a helper at the top of `_run_to` that uses `run_manage(["migrate", "--noinput"], target)` which `cmd_migrate_engine` already does. Postgres cannot connect if the DB name does not exist.

**Create `logstashui_migrate` in compose** by adding a second database via init SQL.

Add `docker/db-init/postgres-extra.sql`:

```sql
CREATE DATABASE logstashui_migrate OWNER logstashui;
```

Mount it in compose under postgres:

```yaml
    volumes:
      - ./db-init/postgres-extra.sql:/docker-entrypoint-initdb.d/02-migrate.sql:ro
```

For MariaDB/MySQL, `docker/db-init/mysql-extra.sql`:

```sql
CREATE DATABASE IF NOT EXISTS logstashui_migrate CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
GRANT ALL ON logstashui_migrate.* TO 'logstashui'@'%';
GRANT ALL ON logstashui_migrate.* TO 'root'@'%';
```

Mount on **both** mariadb and mysql services as `/docker-entrypoint-initdb.d/02-migrate.sql`.

If compose was already created without the volume, `down -v` so init runs again.

- [ ] **Step 2: Run live tests**

```bash
./bin/test_databases.sh
```

Expected: SQLite pytest completes; three engine pytest runs; three live migrator tests PASS. Pre-existing CRUD failures may still fail the **full** suite — if they fail on sqlite they fail on all engines. Do not change those tests. If the script must be CI-green despite them, do **not** hide them with xfail; report in the PR. Optionally restrict engine runs to `LogstashUI/tests` + `Site/tests/test_views.py::test_health_check_returns_200` **only if** the full suite is blocked by those known failures **and** they fail the same way on sqlite. Prefer full suite.

- [ ] **Step 3: Commit**

```bash
git add src/logstashui/LogstashUI/tests/test_migrate_live.py docker/docker-compose.db.yml docker/db-init
git commit -m "test: live sqlite dump/load onto Postgres MariaDB MySQL"
```

---

### Task 8: systemd prompts, sample env, operator docs, CHANGELOG, Docker image, CI

**Files:**
- Modify: `src/logstashui/LogstashUI/packaging/logstashui.default`
- Modify: `src/logstashui/LogstashUI/cli.py` (`install_systemd`, `render_default_env`)
- Modify: `src/logstashui/LogstashUI/tests/test_cli.py` (`test_systemd_dry_run_writes_unit_and_default`)
- Modify: `docs/docs/logstashui/configuration/environment.md`
- Modify: `docs/docs/logstashui/general/deploy.md`
- Modify: `CHANGELOG.md`
- Modify: `docker/Dockerfile`
- Create: `.github/workflows/test-databases.yml`

- [ ] **Step 1: Sample env**

Replace the “Future database backends” block in `logstashui.default` with:

```
# Database. Unset engine = sqlite at $LOGSTASHUI_DATA_DIR/db.sqlite3.
# DATA_DIR is still required for TLS, secrets, logs, staticfiles.
# LOGSTASHUI_DB_ENGINE=sqlite
# LOGSTASHUI_DB_NAME=logstashui
# LOGSTASHUI_DB_HOST=
# LOGSTASHUI_DB_PORT=
# LOGSTASHUI_DB_USER=
# LOGSTASHUI_DB_PASSWORD=
# LOGSTASHUI_DB_SSLMODE=prefer
# LOGSTASHUI_DB_SSL_CA=
# LOGSTASHUI_DB_CONN_MAX_AGE=60
# LOGSTASHUI_DB_CONN_HEALTH_CHECKS=true
#
# Native extras: uv pip install 'LogstashUI[postgres]' or 'LogstashUI[mysql]'
# or 'LogstashUI[databases]'. The container image already includes both drivers.
#
# Create MySQL/MariaDB with utf8mb4_bin:
#   CREATE DATABASE logstashui CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
```

- [ ] **Step 2: systemd generator**

Add optional kwargs to `install_systemd` and `render_default_env`: `db_engine=""`, `db_host=""`, `db_name=""`, `db_user=""`, `db_port=""`.

In the interactive block, after `no_auth` prompt:

```python
        db_engine = _prompt("LOGSTASHUI_DB_ENGINE (sqlite/postgresql/mysql)", db_engine or "sqlite")
        if canonical_engine(db_engine) != "sqlite":
            db_host = _prompt("LOGSTASHUI_DB_HOST", db_host)
            db_port = _prompt("LOGSTASHUI_DB_PORT", db_port)
            db_name = _prompt("LOGSTASHUI_DB_NAME", db_name or "logstashui")
            db_user = _prompt("LOGSTASHUI_DB_USER", db_user)
```

Do not prompt for password (operator edits the EnvironmentFile / Secret).

In `render_default_env`, if `canonical_engine(db_engine) != "sqlite"` append extras like the other optional keys:

```python
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
```

Pass the new kwargs from `cmd_systemd` / `install_systemd` into `render_default_env`. Keep `test_systemd_dry_run_writes_unit_and_default` working (defaults empty → sqlite comments only).

- [ ] **Step 3: Docs**

In `docs/docs/logstashui/configuration/environment.md`, replace the “Database (sqlite only)” section with:

```markdown
## Database

| Variable | Default | Purpose |
|---|---|---|
| `LOGSTASHUI_DB_ENGINE` | `sqlite` | `sqlite`, `postgresql`, or `mysql` (MariaDB uses `mysql`). Aliases: `sqlite3`, `postgres`, `mariadb`, `my` |
| `LOGSTASHUI_DB_NAME` | sqlite: `$LOGSTASHUI_DATA_DIR/db.sqlite3`; else `logstashui` | Database name / sqlite path |
| `LOGSTASHUI_DB_HOST` | empty | **Required** for postgresql/mysql |
| `LOGSTASHUI_DB_PORT` | `5432` / `3306` | |
| `LOGSTASHUI_DB_USER` | empty | **Required** for postgresql/mysql |
| `LOGSTASHUI_DB_PASSWORD` | empty | Put in a Secret / `chmod 640` EnvironmentFile |
| `LOGSTASHUI_DB_SSLMODE` | postgres: `prefer` | `disable` `allow` `prefer` `require` `verify-ca` `verify-full` |
| `LOGSTASHUI_DB_SSL_CA` | empty | CA file for mysql TLS and postgres `verify-*` |
| `LOGSTASHUI_DB_CONN_MAX_AGE` | `60` | Persistent connections (seconds); `0` closes per request |
| `LOGSTASHUI_DB_CONN_HEALTH_CHECKS` | `true` | Django `CONN_HEALTH_CHECKS` |

Floors: PostgreSQL 14+, MariaDB 10.6+, MySQL 8.0+. Create MySQL/MariaDB as `utf8mb4` / `utf8mb4_bin` so unique names match SQLite/Postgres case-sensitivity.

**Install extras (native pip/uv):** `uv pip install 'LogstashUI[postgres]'`, `'LogstashUI[mysql]'`, or `'LogstashUI[databases]'`. The Docker/K8s image already installs `[databases]`. Missing driver fails at startup with that extra name.

`LOGSTASHUI_DATA_DIR` is still required when the database is remote (TLS, `.django_secret_key`, logs, staticfiles).

**SQLite scale:** `logstashui serve` logs a warning when engine is sqlite and `LOGSTASHUI_WORKERS` > 1. Use PostgreSQL or MySQL/MariaDB for concurrent agents. Startup still succeeds.

**Connections:** gunicorn remains gevent (`--worker-connections 1000`). Keep `LOGSTASHUI_WORKERS` × in-flight requests under the server `max_connections`. PgBouncer (or equivalent) is optional, not required.

No `DATABASE_URL`. No YAML.

### Offline migration (supported)

1. `systemctl stop logstashui` (or stop the container).
2. Copy `$LOGSTASHUI_DATA_DIR/db.sqlite3` somewhere safe. Keep the rest of `DATA_DIR` (same Django secret key).
3. Create the server database (`utf8mb4_bin` on MySQL/MariaDB).
4. Set `LOGSTASHUI_DB_*` for the target. Native installs need the matching extra.
5. `logstashui manage dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions -o dump.json` while still on sqlite, **or** use the BETA CLI below.
6. `logstashui manage migrate --noinput && logstashui manage loaddata dump.json`
7. Postgres: `logstashui manage sqlsequencereset PipelineManager Management SNMP AI auth admin | logstashui manage dbshell`
8. Start LogstashUI. Log in again (sessions were not copied).

### BETA CLI

```bash
# env already points at the empty target server; sqlite file still in DATA_DIR
sudo systemctl stop logstashui    # avoid Restart= racing SIGTERM
logstashui migrate-engine --to postgresql --i-have-a-backup
# optional: --write-env /etc/default/logstashui
sudo systemctl start logstashui
```

`--to mysql` covers MariaDB and MySQL. The command SIGTERMs gunicorn if `$LOGSTASHUI_DATA_DIR/gunicorn.pid` is live, checkpoints WAL, dump/load, and **does not** restart serve.
```

In `deploy.md` Data directory paragraph, after the sqlite sentence, add: the database may be external Postgres/MySQL; the PVC/bind-mount is still required for TLS and secrets. In Kubernetes minimum list, add ConfigMap `LOGSTASHUI_DB_ENGINE/HOST/NAME/USER` + Secret `LOGSTASHUI_DB_PASSWORD`.

- [ ] **Step 4: Dockerfile**

Change:

```
RUN uv pip install --system --no-cache /app
```

to:

```
RUN uv pip install --system --no-cache "/app[databases]"
```

Leave `sqlite3` apt package (debug/sqlite CLI in the image is fine).

- [ ] **Step 5: CHANGELOG**

Insert at the top of `CHANGELOG.md`:

```markdown
## [0.5.2] - Multi-database

Package version remains **0.5.1** until release tagging; this documents the 0.5.2 database work.

- `LOGSTASHUI_DB_ENGINE=sqlite|postgresql|mysql` (MariaDB uses `mysql`). Discrete `LOGSTASHUI_DB_HOST/PORT/NAME/USER/PASSWORD` plus SSL and `CONN_MAX_AGE`. No YAML, no `DATABASE_URL`.
- Default is still SQLite. `logstashui serve` warns when `LOGSTASHUI_WORKERS>1` on SQLite.
- Native extras: `LogstashUI[postgres]`, `[mysql]`, `[databases]`. Container image installs `[databases]`.
- BETA `logstashui migrate-engine --to postgresql|mysql --i-have-a-backup` copies SQLite → server (stops gunicorn; does not restart).
- `bin/test_databases.sh` runs the suite and dump/load against local Docker Postgres, MariaDB, and MySQL.
```

Do not bump `pyproject.toml` version in this plan unless the operator asks; the spec is “0.5.2 work”.

- [ ] **Step 6: CI workflow**

Create `.github/workflows/test-databases.yml`:

```yaml
name: Database matrix

on:
  pull_request:
  push:
    branches: [main, master]

jobs:
  db:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          python-version: "3.12"
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Run database matrix
        run: bash bin/test_databases.sh
```

- [ ] **Step 7: Tests for systemd extras**

Extend `test_systemd_dry_run_writes_unit_and_default` **or** add:

```python
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
```

Update `install_systemd` signature with those kwargs defaulting to `""`.

- [ ] **Step 8: Run focused tests + default sqlite pytest slice**

```bash
uv run pytest src/logstashui/LogstashUI/tests/test_cli.py src/logstashui/LogstashUI/tests/test_database.py src/logstashui/LogstashUI/tests/test_migrate_engine.py -v --no-cov
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/logstashui/LogstashUI/packaging/logstashui.default \
  src/logstashui/LogstashUI/cli.py \
  src/logstashui/LogstashUI/tests/test_cli.py \
  docs/docs/logstashui/configuration/environment.md \
  docs/docs/logstashui/general/deploy.md \
  CHANGELOG.md docker/Dockerfile .github/workflows/test-databases.yml
git commit -m "docs: multi-engine env, systemd, Docker extras, CI matrix"
```

---

### Task 9: Verification gate

- [ ] **Step 1: Default inner loop (no Docker extras required)**

```bash
uv run pytest src/logstashui --no-cov
```

Expected: no **new** failures vs sqlite baseline. Pre-existing three CRUD tests may still fail.

- [ ] **Step 2: Full matrix**

```bash
./bin/test_databases.sh
```

Expected: sqlite + postgresql + mariadb + mysql pytest runs; live migrator PASS.

- [ ] **Step 3: Image install extras**

```bash
grep -n '\[databases\]' docker/Dockerfile
```

Expected: `uv pip install --system --no-cache "/app[databases]"`.

- [ ] **Step 4: Do not start smoke compose unless the operator asks.** Product CA must remain untouched.

---

## Spec coverage (self-review)

| Spec item | Task |
|---|---|
| ORM only / `build_databases` | 2–3 |
| Discrete env, aliases, SSL, CONN_* | 2–3, 8 |
| Extras + Docker `[databases]` | 1, 8 |
| psycopg gevent (version pin, no psycogreen) | 1, 4 (wsgi comment) |
| PyMySQL `install_as_MySQLdb` | 3 |
| Fail-fast unknown/missing driver/host | 2–3 |
| Server version floors | 2–3, 4 (serve after migrate) |
| SQLite default + scale warning | 3–4 |
| gunicorn pidfile + SIGTERM | 4, 6 |
| Offline dump/load docs | 8 |
| BETA CLI `--i-have-a-backup` | 6–7 |
| `--write-env`, no auto-restart | 6, 8 |
| Local Docker three engines + migrator | 5, 7, 9 |
| CI uses the same script | 8 |
| systemd prompts / sample env | 8 |
| MySQL `utf8mb4_bin` | 3, 5 (compose command + CREATE DATABASE) |
| DATA_DIR still required | 8 docs |
| No YAML / DATABASE_URL / DAO / smoke-stack DB | throughout |
| Pre-existing pytest failures left alone | 5, 9 |

**Placeholders:** none remaining. Live tests use subprocesses so Django settings never switch in-process (matches architecture).

**Type names:** `canonical_engine`, `_import_or_raise`, `check_server_version`, `cmd_migrate_engine`, `stop_gunicorn`, `write_env_file`, `run_manage` — used consistently across tasks.
