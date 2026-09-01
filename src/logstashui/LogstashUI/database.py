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


def _import_or_raise(module: str, extra: str):
    try:
        return __import__(module)
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

    pymysql = _import_or_raise("pymysql", "mysql")
    if pymysql is not None:
        # Django 6 MySQL backend requires Database.version_info >= (2, 2, 1)
        # (mysqlclient). PyMySQL reports ~1.1.1, so spoof before the shim.
        pymysql.version_info = (2, 2, 1, "final", 0)
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
