#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import os
import shutil
import subprocess
import sys
import uuid

import pytest


# ---------------------------------------------------------------------------
# Docker availability — checked once at module import time
# ---------------------------------------------------------------------------

def _check_docker() -> tuple[bool, str]:
    if not shutil.which("docker"):
        return False, "docker binary not found in PATH"
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False, (
                f"docker info returned {r.returncode}: "
                f"{r.stderr.decode()[:200]}"
            )
        return True, ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)


_DOCKER_OK, _DOCKER_REASON = _check_docker()


@pytest.fixture(scope="session", autouse=True)
def skip_if_no_docker():
    """Skip every test in the integration suite when Docker is unavailable."""
    if not _DOCKER_OK:
        pytest.skip(f"Docker not available: {_DOCKER_REASON}")


# ---------------------------------------------------------------------------
# Container fixtures (session scope — start once, reused across all tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def postgres_container():
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(
        image="postgres:16",
        username="logstashui",
        password="logstashui",
        dbname="logstashui_test",
    ) as c:
        yield c


@pytest.fixture(scope="session")
def mysql_container():
    from testcontainers.community.mysql import MySqlContainer

    c = MySqlContainer(
        image="mysql:8.0",
        root_password="logstashui",
        dbname="logstashui_test",
    )
    c.with_command(
        "--character-set-server=utf8mb4 --collation-server=utf8mb4_bin"
    )
    with c:
        yield c


@pytest.fixture(scope="session")
def mariadb_container():
    from testcontainers.community.mysql import MySqlContainer

    c = MySqlContainer(
        image="mariadb:11",
        root_password="logstashui",
        dbname="logstashui_test",
    )
    c.with_command(
        "--character-set-server=utf8mb4 --collation-server=utf8mb4_bin"
    )
    with c:
        yield c


# ---------------------------------------------------------------------------
# Env-dict helpers (module-level, not fixtures — importable by test files)
# ---------------------------------------------------------------------------

def pg_env(container, *, dbname: str = "logstashui_test") -> dict[str, str]:
    """Return LOGSTASHUI_DB_* env dict for a PostgreSQL container."""
    return {
        "LOGSTASHUI_DB_ENGINE": "postgresql",
        "LOGSTASHUI_DB_HOST": container.get_container_host_ip(),
        "LOGSTASHUI_DB_PORT": str(container.get_exposed_port(5432)),
        "LOGSTASHUI_DB_USER": "logstashui",
        "LOGSTASHUI_DB_PASSWORD": "logstashui",
        "LOGSTASHUI_DB_NAME": dbname,
    }


def mysql_env(container, *, dbname: str = "logstashui_test") -> dict[str, str]:
    """Return LOGSTASHUI_DB_* env dict for a MySQL/MariaDB container (root user)."""
    return {
        "LOGSTASHUI_DB_ENGINE": "mysql",
        "LOGSTASHUI_DB_HOST": container.get_container_host_ip(),
        "LOGSTASHUI_DB_PORT": str(container.get_exposed_port(3306)),
        "LOGSTASHUI_DB_USER": "root",
        "LOGSTASHUI_DB_PASSWORD": "logstashui",
        "LOGSTASHUI_DB_NAME": dbname,
    }


def new_dbname() -> str:
    """Generate a unique database name for test isolation."""
    return f"logstashui_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Fresh-database helpers (create/drop via native drivers)
# ---------------------------------------------------------------------------

def create_pg_db(base_env: dict[str, str], dbname: str) -> None:
    """Create *dbname* in the PostgreSQL container reachable via *base_env*."""
    import psycopg

    connstr = (
        f"host={base_env['LOGSTASHUI_DB_HOST']} "
        f"port={base_env['LOGSTASHUI_DB_PORT']} "
        f"user={base_env['LOGSTASHUI_DB_USER']} "
        f"password={base_env['LOGSTASHUI_DB_PASSWORD']} "
        f"dbname={base_env['LOGSTASHUI_DB_NAME']}"
    )
    with psycopg.connect(connstr, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{dbname}"')


def drop_pg_db(base_env: dict[str, str], dbname: str) -> None:
    import psycopg

    connstr = (
        f"host={base_env['LOGSTASHUI_DB_HOST']} "
        f"port={base_env['LOGSTASHUI_DB_PORT']} "
        f"user={base_env['LOGSTASHUI_DB_USER']} "
        f"password={base_env['LOGSTASHUI_DB_PASSWORD']} "
        f"dbname={base_env['LOGSTASHUI_DB_NAME']}"
    )
    with psycopg.connect(connstr, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{dbname}"')


def create_mysql_db(base_env: dict[str, str], dbname: str) -> None:
    """Create *dbname* with utf8mb4/utf8mb4_bin in the MySQL/MariaDB container."""
    import pymysql

    conn = pymysql.connect(
        host=base_env["LOGSTASHUI_DB_HOST"],
        port=int(base_env["LOGSTASHUI_DB_PORT"]),
        user=base_env["LOGSTASHUI_DB_USER"],
        password=base_env["LOGSTASHUI_DB_PASSWORD"],
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE `{dbname}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_bin"
            )
    finally:
        conn.close()


def drop_mysql_db(base_env: dict[str, str], dbname: str) -> None:
    import pymysql

    conn = pymysql.connect(
        host=base_env["LOGSTASHUI_DB_HOST"],
        port=int(base_env["LOGSTASHUI_DB_PORT"]),
        user=base_env["LOGSTASHUI_DB_USER"],
        password=base_env["LOGSTASHUI_DB_PASSWORD"],
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{dbname}`")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Parametrized engine fixture (postgres + mysql)
# ---------------------------------------------------------------------------

@pytest.fixture(params=["postgres", "mysql"])
def engine_env(request, postgres_container, mysql_container):
    """Yield (engine_name, env_dict) for each supported engine."""
    if request.param == "postgres":
        yield "postgresql", pg_env(postgres_container)
    else:
        yield "mysql", mysql_env(mysql_container)


# ---------------------------------------------------------------------------
# Fresh per-test database fixture (for migration / round-trip tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_db_env(engine_env, tmp_path):
    """
    Yield (engine_name, env_dict) with a unique throwaway database and
    LOGSTASHUI_DATA_DIR set. The database is created before the test and
    dropped afterwards.
    """
    engine, base_env = engine_env
    dbname = new_dbname()

    if engine == "postgresql":
        create_pg_db(base_env, dbname)
        full_env = {
            **base_env,
            "LOGSTASHUI_DB_NAME": dbname,
            "LOGSTASHUI_DATA_DIR": str(tmp_path),
        }
        yield engine, full_env
        drop_pg_db(base_env, dbname)
    else:
        create_mysql_db(base_env, dbname)
        full_env = {
            **base_env,
            "LOGSTASHUI_DB_NAME": dbname,
            "LOGSTASHUI_DATA_DIR": str(tmp_path),
        }
        yield engine, full_env
        drop_mysql_db(base_env, dbname)
