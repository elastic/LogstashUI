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
