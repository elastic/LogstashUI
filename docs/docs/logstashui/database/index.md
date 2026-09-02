# Database

LogstashUI stores operator data (policies, connections, pipelines, SNMP, users) in a SQL database. The Django ORM is the only CRUD layer. Choose the engine with discrete environment variables. There is no `DATABASE_URL` and no YAML.

| Engine | `LOGSTASHUI_DB_ENGINE` | Server floor | When to use |
|---|---|---|---|
| **SQLite** (default) | `sqlite` (aliases: `sqlite3`, empty) | — | Single replica, lab, default Docker |
| **PostgreSQL** | `postgresql` (alias: `postgres`) | 14+ | Concurrent agents, Kubernetes |
| **MariaDB / MySQL** | `mysql` (aliases: `mariadb`, `my`) | MariaDB 10.6+ / MySQL 8.0+ | Same as Postgres; one engine covers both |

`logstashui serve` logs a **warning** when the engine is SQLite and `LOGSTASHUI_WORKERS` > 1. It still starts. SQLite does not scale under gunicorn/gevent with concurrent agents.

The container image already installs `LogstashUI[databases]` (both drivers). Native pip/uv:

```bash
uv pip install 'LogstashUI[postgres]'
uv pip install 'LogstashUI[mysql]'
uv pip install 'LogstashUI[databases]'   # both
```

Missing driver fails at startup with the extra name. Unknown engine, missing `HOST`/`USER` on server engines, or a server below the floor fails **before** `migrate`.

Create the empty server database yourself ([examples](examples/)). Tables come from `logstashui manage migrate` (also run by `logstashui serve`). Do not apply the schema snapshots instead of migrate.

MySQL/MariaDB **must** be `utf8mb4` / `utf8mb4_bin` so unique names match SQLite/Postgres case-sensitivity. The Django connection also sets `NAMES utf8mb4 COLLATE utf8mb4_bin`.

---

## Environment variables

Unset keys use the default in the **Default** column. Empty string after strip is treated as unset for name/port/sslmode.

### Data directory (still required when the database is remote)

| Variable | Default | Notes |
|---|---|---|
| `LOGSTASHUI_DATA_DIR` | `$(pwd)/logstashui_data` | Docker/K8s/systemd **must** set `/var/lib/logstashui`. TLS, `.django_secret_key`, logs, `staticfiles/`, SQLite file. |
| `LOGSTASHUI_LOGS_DIR` | `$LOGSTASHUI_DATA_DIR/logs` | |

### Engine and connection

| Variable | Default | Notes |
|---|---|---|
| `LOGSTASHUI_DB_ENGINE` | `sqlite` | `sqlite`, `postgresql`, `mysql`. Aliases: `sqlite3`, `postgres`, `mariadb`, `my`. |
| `LOGSTASHUI_DB_NAME` | sqlite: `$LOGSTASHUI_DATA_DIR/db.sqlite3`; else `logstashui` | Database name, or SQLite file path. |
| `LOGSTASHUI_DB_HOST` | empty | **Required** for postgresql/mysql. |
| `LOGSTASHUI_DB_PORT` | postgresql: `5432`; mysql: `3306` | |
| `LOGSTASHUI_DB_USER` | empty | **Required** for postgresql/mysql. |
| `LOGSTASHUI_DB_PASSWORD` | empty | Secret / `chmod 640` EnvironmentFile. Never in a ConfigMap. |
| `LOGSTASHUI_DB_SSLMODE` | postgresql: `prefer` | `disable` `allow` `prefer` `require` `verify-ca` `verify-full`. Ignored for mysql/sqlite. |
| `LOGSTASHUI_DB_SSL_CA` | empty | CA file. Postgres `sslrootcert` when `verify-*`; MySQL `ssl.ca`. |
| `LOGSTASHUI_DB_CONN_MAX_AGE` | `60` | Seconds. `0` closes per request. Non-integer → startup error. |
| `LOGSTASHUI_DB_CONN_HEALTH_CHECKS` | `true` | Django `CONN_HEALTH_CHECKS`. |

SQLite opens WAL (`PRAGMA journal_mode=WAL`) and `busy_timeout=20000`.

gunicorn stays `--worker-class gevent` (`--worker-connections 1000`). Keep `LOGSTASHUI_WORKERS` × in-flight requests under the server `max_connections`. PgBouncer is optional.

Related server knobs (not DB-specific, but they interact):

| Variable | Default | Notes |
|---|---|---|
| `LOGSTASHUI_WORKERS` | `2` | SQLite + workers > 1 logs a warning. |
| `LOGSTASHUI_TLS` | `true` | Keep `true` in Kubernetes. |
| `SECRET_KEY` | auto in `DATA_DIR/.django_secret_key` | Keep `DATA_DIR` across engine switches or encrypted rows will not decrypt. |

---

## Kubernetes

PVC at `/var/lib/logstashui` for every engine. ConfigMap: `LOGSTASHUI_DB_ENGINE` / `HOST` / `PORT` / `NAME` / `USER` (and `SSLMODE` for Postgres). Secret: `LOGSTASHUI_DB_PASSWORD`. CloudNativePG: [CNPG](/docs/docs/logstashui/kubernetes/cnpg.md).

Manifests: [kubernetes/examples](/docs/docs/logstashui/kubernetes/examples/).

---

## Moving data

[Migration](migration.md) — offline `dumpdata`/`loaddata` (supported) and BETA `logstashui migrate-engine`.
