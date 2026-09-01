# 2026-08-21 — Multi-database design (SQLite | PostgreSQL | MariaDB/MySQL)

**LogstashUI version:** 0.5.2  
**Python:** 3.12–3.14  
**Django:** 6.x (existing)  
**Chosen approach:** Django backends + keep gevent. No new CRUD/repository layer.

## Goal

Operators can run LogstashUI on **SQLite** (default), **PostgreSQL**, or **MariaDB/MySQL** using discrete environment variables. Default `pytest` on SQLite stays green. Local Docker can exercise each server engine for CRUD **and** SQLite→server migration.

SQLite does not scale under gunicorn/gevent (2 workers × 1000 greenlets). Server engines address that without changing the product data model.

## Non-goals (0.5.2)

- A new DAO/repository over `Model.objects` (Django ORM already abstracts CRUD).
- YAML, `logstashui.yml`, or `DATABASE_URL`.
- Oracle, SQL Server, or other engines.
- Requiring PgBouncer/ProxySQL, or changing gunicorn off gevent.
- Live dual-write, reverse migration (server→SQLite), or pgloader as the supported path.
- An in-app migration wizard (stopping :8443 removes the UI).
- A 503 maintenance page on :8443 during copy.
- Helm charts; shipping Postgres/MariaDB/MySQL in the default smoke compose.
- Product CA rotation; relocating `DATA_DIR` (TLS, secrets, logs, staticfiles stay on disk).

## Decisions (locked)

| Topic | Decision |
|---|---|
| Abstraction | Django ORM only; the switch is `build_databases()` |
| Default engine | SQLite; warn at scale; do not refuse to start |
| Config | Env vars only, discrete `LOGSTASHUI_DB_*` |
| Engine names | Canonical: `sqlite`, `postgresql`, `mysql` |
| MariaDB vs MySQL | One engine `mysql`; both documented |
| Drivers | Optional extras; Docker image installs `[databases]` |
| Postgres driver | `psycopg[binary]` (v3) + gevent wait callback |
| MySQL driver | `PyMySQL` + `pymysql.install_as_MySQLdb()` before Django setup |
| Gunicorn | gevent for all engines |
| Pooler | Not required; `CONN_MAX_AGE` + health checks |
| Existing SQLite deploys | Stay on SQLite until the operator migrates |
| Migration | Documented offline dump/load **and** BETA CLI that stops gunicorn |
| Tests | Default pytest = SQLite; local Docker compose for Postgres + MariaDB + MySQL (functional **and** migrator); CI uses the same compose |

## Architecture

```
LOGSTASHUI_DB_*  →  build_databases(DATA_DIR)  →  Django DATABASES['default']
                                              ├ sqlite3     DATA_DIR/db.sqlite3
                                              ├ postgresql  psycopg 3
                                              └ mysql       PyMySQL (MariaDB or MySQL)
```

All apps keep `Model.objects`, `transaction.atomic`, `select_for_update`, and existing migrations. No `raw()` / `cursor()` / `PRAGMA` outside `LogstashUI/database.py` (SQLite PRAGMAs stay there).

`DATA_DIR` remains mandatory: TLS, `.django_secret_key`, logs, staticfiles. A remote database does not remove the PVC or bind-mount.

`pymysql.install_as_MySQLdb()` runs once at process start, before `django.setup()`, when the MySQL extra is installed (safe no-op if engine is not mysql).

## Configuration

No YAML. No URL DSN.

| Variable | Default | Rules |
|---|---|---|
| `LOGSTASHUI_DB_ENGINE` | `sqlite` | Aliases below |
| `LOGSTASHUI_DB_NAME` | sqlite: `DATA_DIR/db.sqlite3`; else `logstashui` | |
| `LOGSTASHUI_DB_HOST` | empty | **Required** for postgresql/mysql |
| `LOGSTASHUI_DB_PORT` | 5432 / 3306 | Engine default if unset |
| `LOGSTASHUI_DB_USER` | empty | **Required** for postgresql/mysql |
| `LOGSTASHUI_DB_PASSWORD` | empty | Secret / EnvironmentFile |
| `LOGSTASHUI_DB_SSLMODE` | postgres: `prefer`; mysql: unset | postgres: `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full` |
| `LOGSTASHUI_DB_SSL_CA` | empty | Path; mysql TLS and postgres `verify-*` |
| `LOGSTASHUI_DB_CONN_MAX_AGE` | `60` | `0` = close per request |
| `LOGSTASHUI_DB_CONN_HEALTH_CHECKS` | `true` | Django `CONN_HEALTH_CHECKS` |

**Aliases** (normalize to canonical):

- `sqlite3` → `sqlite`
- `postgres`, `postgresql` → `postgresql`
- `mysql`, `mariadb`, `my` → `mysql`

**SQLite OPTIONS (unchanged):** `timeout=20`; `init_command` `PRAGMA busy_timeout=20000; PRAGMA journal_mode=WAL;`

**MySQL OPTIONS:** `charset=utf8mb4`; `init_command=SET sql_mode='STRICT_TRANS_TABLES'`; collation `utf8mb4_bin` so unique `Policy.name` (and similar) match SQLite/Postgres case-sensitivity. MySQL’s default `_ci` collation would treat `Foo` and `foo` as a clash.

**Postgres OPTIONS:** `sslmode` from env; `sslrootcert` when `LOGSTASHUI_DB_SSL_CA` is set.

**Version floors** (docs; fail-fast if the server version is below): PostgreSQL **14+**, MariaDB **10.6+**, MySQL **8.0+**.

Update `LogstashUI/packaging/logstashui.default`, `docs/docs/logstashui/configuration/environment.md`, the systemd generator (interactive prompt for engine + host/name/user; password from env or prompt), and CHANGELOG.

## Packaging and Docker

Default wheel: SQLite only (stdlib).

```
LogstashUI[postgres]     → psycopg[binary]
LogstashUI[mysql]        → PyMySQL
LogstashUI[databases]    → both
```

Missing extra at runtime → `RuntimeError` naming the extra (`uv pip install 'LogstashUI[postgres]'`).

**Docker/K8s image:** install `LogstashUI[databases]` (e.g. `uv pip install '/app[databases]'`). Operators set env; no extra pip in the cluster.

Native pip/uv: extras are the supported advanced path.

Python 3.12–3.14: `psycopg[binary]` wheels; PyMySQL is pure Python (no mysqlclient compile). Pin `psycopg[binary]` to a release that ships 3.14 wheels, or document build deps.

## Gevent and connections

Keep `--worker-class gevent` and `--worker-connections 1000`.

- Register a psycopg3 **gevent wait callback** at process start so libpq does not block the hub.
- PyMySQL uses monkey-patched sockets; do not add mysqlclient.
- `CONN_MAX_AGE=60` and `CONN_HEALTH_CHECKS=true` by default.
- Do not require an external pooler. Document that `LOGSTASHUI_WORKERS` × in-flight greenlets must stay under the server’s `max_connections` (leave room for `migrate` and the test matrix). Optional PgBouncer is documented, not required.
- In-process `psycopg_pool` only if it is gevent-safe; otherwise skip for 0.5.2.

**SQLite scale warning:** one WARNING at `logstashui serve` when the engine is sqlite and `LOGSTASHUI_WORKERS` > 1 (gunicorn default is 2). Message: SQLite is the small-install default; use PostgreSQL or MySQL/MariaDB for concurrent agents. Do not refuse to start. No UI modal.

## Fail-fast (before gunicorn bind)

| Condition | Result |
|---|---|
| Unknown engine | `RuntimeError`, list canonical names + aliases |
| postgresql/mysql, driver not installed | `RuntimeError` + extra name |
| postgresql/mysql, HOST/NAME/USER empty | `RuntimeError` naming the empty vars |
| Cannot connect during `migrate` | Django error; serve exits non-zero |
| SSL verify fail | Driver error; do not swallow |

Never log passwords. INFO may log engine, host, and name.

## Migration off SQLite

One mechanism: Django `dumpdata` → target `migrate` → `loaddata` → `sqlsequencereset`.

`DATA_DIR` does not move. `.django_secret_key` must stay or Fernet keystore rows will not decrypt.

### Offline (supported)

Documented in deploy/environment:

1. Stop LogstashUI.
2. Copy `DATA_DIR/db.sqlite3` to a backup.
3. Dump from SQLite.
4. Set `LOGSTASHUI_DB_*` for the server.
5. `logstashui manage migrate --noinput`.
6. `loaddata`.
7. `sqlsequencereset` (Postgres sequences; document as skippable/no-op guidance for MySQL).
8. Start LogstashUI. Verify login, a policy, and an agent.

### BETA CLI

`logstashui migrate-engine --to postgresql|mysql --i-have-a-backup`

1. Print BETA + backup warning; refuse without `--i-have-a-backup`.
2. Source must be sqlite; target must be postgresql or mysql; extras must be installed.
3. If gunicorn is running (pidfile written by `serve` in 0.5.2, or `--pid`), **SIGTERM it**. That is maintenance: the UI port closes. No in-app wizard.
4. `PRAGMA wal_checkpoint(TRUNCATE)` on SQLite.
5. `dumpdata --natural-foreign --natural-primary`, exclude `contenttypes`, `auth.permission`, `sessions`.
6. Target `DATABASES` from env. `migrate --noinput`, `loaddata`, `sqlsequencereset`.
7. Print remaining env. Do not edit `/etc/default/logstashui` unless `--write-env PATH`. Do not auto-restart serve (systemd `Restart=` would race). Document `systemctl stop` → migrate → `systemctl start`.

No reverse migrator. No sqlite→sqlite. If a pidfile points at a live process and SIGTERM fails, refuse.

## Testing

### Default inner loop (unchanged)

`pytest` uses SQLite via settings. **All existing tests must pass** with no Docker and no extras.

Update `test_database.py`: postgresql/mysql no longer raise “not implemented”; they return a valid `DATABASES` dict (connect may be skipped in unit tests). New unit tests: aliases, missing driver, missing HOST, sqlite default path, SSL/CONN keys.

### Local Docker matrix (required)

Ship `docker/docker-compose.db.yml` with **three** databases for local use and CI:

- PostgreSQL 16 (or 14+)
- MariaDB 10.11+ (or 10.6+)
- MySQL 8.0+

Fixed test credentials in the compose file (not production). Healthchecks so tests wait for ready.

Ship `bin/test_databases.sh` (and `bin/test_databases.bat` to match the existing Windows start scripts):

1. `docker compose -f docker/docker-compose.db.yml up -d --wait`
2. Run the **existing pytest suite** against each server engine (`LOGSTASHUI_DB_ENGINE` plus host/port/user/password/name pointing at the container). A SQLite run remains the first step (no compose required for that step).
3. Run **migration tests**: a fixture SQLite database → dump/load (the same helpers as `migrate-engine`) into Postgres, MariaDB, and MySQL; assert a `Policy`, `User`, and JSONField row survive.
4. Tear down compose unless `--keep`.

This is how a developer proves basic functionality and migration without waiting on CI. CI calls the same script.

If Docker is unavailable, `bin/test_databases.sh` fails clearly; default `pytest` still works.

Do **not** put Postgres/MariaDB/MySQL in `docker-compose.yml` or the smoke stack by default. Smoke stays SQLite so product CA and PUID behavior stay unchanged.

### Pre-existing pytest failures

`test_update_policy_default_policy_forbidden`, `test_delete_policy_default_policy_forbidden`, and `test_clone_policy_success` were already failing before this work. 0.5.2 database work must not add new failures. Do not silently “fix” those unless they fail **because of** engine differences.

## Dialect traps (must handle)

- **Unique case-sensitivity:** MySQL `utf8mb4_bin` (or equivalent) so `Policy.name` unique matches SQLite/Postgres.
- **JSONField:** Connection `status_blob`, Revision `snapshot_json`, SNMP metadata/templates. Native JSON on all three version floors.
- **`select_for_update`:** real row locks on Postgres/MySQL; first-user creation in `Management/views.py`. Tests that mock it stay. Add one real concurrency test on a server engine if cheap.
- **`db_table = 'settings'`:** must migrate cleanly on MySQL (quoted identifier).
- **Index/constraint name length:** MySQL 64 characters; existing `UniqueConstraint` names are short enough — verify `migrate` on MySQL.
- **Timezones:** `USE_TZ=True`; Django maps Postgres timestamptz vs MySQL datetime if USE_TZ stays.
- **BooleanField / BigAutoField:** ORM.
- **RunPython migrations:** ORM-based; portable. No new SQLite-only `RunSQL`.
- **loaddata PKs:** `sqlsequencereset` after load on Postgres.
- **Encrypted CharFields:** copied as Fernet strings; secret key stays in `DATA_DIR`.

## Docs and operator surfaces

- `docs/docs/logstashui/configuration/environment.md` — replace “sqlite only”.
- `docs/docs/logstashui/general/deploy.md` — PVC still required; the database may be external.
- Offline migration procedure + BETA CLI warnings.
- SQLite scale warning explained.
- Extras vs Docker `[databases]`.
- Optional PgBouncer note.
- `CHANGELOG.md` for 0.5.2.
- systemd sample env keys (already stubbed in `logstashui.default`).
- Kubernetes: ConfigMap for engine/host/name/user + Secret for password; PVC still for `DATA_DIR`.

## Obstacles

1. **Gevent × `max_connections`:** default 2 workers is acceptable for small Postgres; document; do not open thousands of sessions.
2. **psycopg3 + gevent:** the wait callback is mandatory; missing it looks like random hangs.
3. **mysqlclient vs PyMySQL:** the C client blocks the hub; PyMySQL is the gevent choice; Django sees it via `install_as_MySQLdb`.
4. **MySQL unique collation** silently changes uniqueness vs SQLite if left at `_ci`.
5. **dumpdata/loaddata** is not a perfect replica (sessions dropped, contenttypes excluded); operators re-login.
6. **Stopping gunicorn** for BETA migrate races with systemd `Restart=`; do not auto-restart; document stop → migrate → start.
7. **Driver wheels on 3.14:** PyMySQL is safe; pin `psycopg[binary]` to a release with 3.14 wheels, or document build deps.
8. **Hatch extras** must not pull mysqlclient into the default wheel.
9. **Tests that assume sqlite paths** (`db.sqlite3` in `paths.py` legacy migrate) stay sqlite-only.
10. **Smoke stack** stays sqlite so CA/PUID work is unchanged.

## Success criteria

- Unset engine → SQLite, same as 0.5.1.
- `LOGSTASHUI_DB_ENGINE=postgresql` or `mysql` with valid env → migrate + serve.
- Default `pytest` green on SQLite (no new failures).
- `bin/test_databases.sh` against local Docker Postgres, MariaDB, and MySQL: existing suite + dump/load migration assertions.
- BETA `migrate-engine` refuses without `--i-have-a-backup` and stops gunicorn when a pidfile is live.
- Docker image can use all three engines via env only.
- Docs match env keys.
- Product CA and `DATA_DIR` behavior unchanged.

## Implementation order

1. Extras + `build_databases()` + fail-fast + unit tests (SQLite pytest).
2. PyMySQL shim + psycopg gevent wait + `CONN_*`.
3. `docker-compose.db.yml` + `bin/test_databases.sh`; existing suite passing on three servers.
4. SQLite scale warning; systemd/docs/sample env.
5. `serve` pidfile; `migrate-engine` BETA; migration tests in the same script.
6. Docker image `[databases]`.
7. CHANGELOG 0.5.2.

## Spec self-review

- **Placeholders:** none. Version floors, env keys, extras, compose services, and CLI flags are explicit.
- **Consistency:** architecture (ORM switch only) matches packaging, gevent, migrator, and tests. Default remains SQLite everywhere except when env selects a server engine.
- **Scope:** one release-sized feature (engine wiring + migrator + test matrix). No Helm, no worker-class split, no repository layer.
- **Ambiguity resolved:** `mysql` covers MariaDB and MySQL; migrator stops the UI port rather than serving a maintenance page; local Docker is required for the three-engine script, not for default pytest.
