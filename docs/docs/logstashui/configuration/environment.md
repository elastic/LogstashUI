# Environment configuration

LogstashUI is configured with **environment variables**. There is no required `logstashui.yml`.

Use:

- a shell export / dotenv for `uv run logstashui`
- `/etc/default/logstashui` for systemd (`logstashui systemd` writes this file)
- a Kubernetes ConfigMap (non-secrets) plus a Secret (`SECRET_KEY`, `LOGSTASHUI_AGENT_CSR_SECRET`)

A commented sample ships in the wheel at `LogstashUI/packaging/logstashui.default`.

---

## Data directory

| Variable | Default | Purpose |
|---|---|---|
| `LOGSTASHUI_DATA_DIR` | `$(pwd)/logstashui_data` | sqlite, `tls/`, secrets |
| `LOGSTASHUI_LOGS_DIR` | `$LOGSTASHUI_DATA_DIR/logs` | application logs |

Docker, systemd, and Kubernetes **must** set `LOGSTASHUI_DATA_DIR=/var/lib/logstashui` (bind-mount or PVC). Do not rely on cwd in those environments.

Relative values resolve from the process working directory.

---

## Server

| Variable | Default | Purpose |
|---|---|---|
| `DEBUG` | `true` (native) / `false` (Docker) | Django debug |
| `LOGSTASHUI_LOG_LEVEL` | `DEBUG` if `DEBUG` else `INFO` | App / root / file / console Python logs |
| `LOGSTASHUI_DJANGO_LOG_LEVEL` | django=`INFO`, `django.request`=`ERROR` | Django framework loggers. Alias: `DJANGO_LOG_LEVEL` |
| `LOGSTASHUI_BIND` | `0.0.0.0:8443` | gunicorn bind |
| `LOGSTASHUI_WORKERS` | `2` | gunicorn workers |
| `LOGSTASHUI_TLS` | `true` | HTTPS with product CA under `$LOGSTASHUI_DATA_DIR/tls/` |
| `ALLOWED_HOSTS` | `*` | Django allowed hosts |
| `CSRF_TRUSTED_ORIGINS` | (dev localhost defaults) | comma-separated origins |
| `SECRET_KEY` | auto in data dir | Django secret |

Keep `LOGSTASHUI_TLS=true` (the default) in Kubernetes. Ingress/HTTPRoute should originate HTTPS to `:8443` and skip backend cert verify. See [Kubernetes](/docs/docs/logstashui/kubernetes/index.md).

---

## Auth and agent URL

| Variable | Default | Purpose |
|---|---|---|
| `LOGSTASHUI_NO_AUTH` | `false` | Bypass login (**sandbox only**) |
| `LOGSTASHUI_AGENT_UI_URL` | empty | Prefill `--logstash-ui-url` (DB Settings wins if set) |
| `LOGSTASHUI_INCLUDE_CA_FINGERPRINT` | `true` | Embed product CA fingerprint in enrollment tokens |
| `LOGSTASH_AGENT_URL` | debug: `http://127.0.0.1:9500`; else `https://logstashagent:9500` | Embedded/compose agent API |
| `LOGSTASHUI_HOST_HOSTNAME` / `LOGSTASHUI_HOST_IPS` / `LOGSTASHUI_TLS_SANS` | empty | Extra SANs on the product UI cert. Kubernetes: set `LOGSTASHUI_HOST_IPS` from `status.podIP` (Downward API). IPs are also appended to `ALLOWED_HOSTS` unless that list is `*`. |
| `LOGSTASHUI_AGENT_CSR_SECRET` | empty | Compose/embedded agent CSR without enroll |
| `LOGSTASHUI_DOCS_DIR` | checkout `docs/` or packaged copy | In-app documentation root |

Booleans accept `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off`.

---

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

Floors: PostgreSQL 14+, MariaDB 10.6+, MySQL 8.0+. Create MySQL/MariaDB as `utf8mb4` / `utf8mb4_bin` so unique names match SQLite/Postgres case-sensitivity. Full engine docs, env defaults, and SQL examples: [Database](/docs/docs/logstashui/database/index.md). Migration (offline + BETA CLI): [Migration](/docs/docs/logstashui/database/migration.md).

**Install extras (native pip/uv):** `uv pip install 'LogstashUI[postgres]'`, `'LogstashUI[mysql]'`, or `'LogstashUI[databases]'`. The Docker/K8s image already installs `[databases]`. Missing driver fails at startup with that extra name.

`LOGSTASHUI_DATA_DIR` is still required when the database is remote (TLS, `.django_secret_key`, logs, staticfiles).

**SQLite scale:** `logstashui serve` logs a warning when engine is sqlite and `LOGSTASHUI_WORKERS` > 1. Use PostgreSQL or MySQL/MariaDB for concurrent agents. Startup still succeeds.

**Connections:** gunicorn remains gevent (`--worker-connections 1000`). Keep `LOGSTASHUI_WORKERS` × in-flight requests under the server `max_connections`. PgBouncer (or equivalent) is optional, not required.

No `DATABASE_URL`. No YAML.

### Offline migration (supported)

1. `systemctl stop logstashui` (or stop the container).
2. Copy `$LOGSTASHUI_DATA_DIR/db.sqlite3` somewhere safe. Keep the rest of `DATA_DIR` (same Django secret key).
3. Dump **from sqlite** while `LOGSTASHUI_DB_ENGINE` is still sqlite (or unset): `logstashui manage dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e sessions -o dump.json`. Do not set target `LOGSTASHUI_DB_*` yet, or dumpdata will dump the empty server database.
4. Create the server database (`utf8mb4_bin` on MySQL/MariaDB).
5. **Then** set `LOGSTASHUI_DB_*` for the target. Native installs need the matching extra.
6. `logstashui manage migrate --noinput && logstashui manage loaddata dump.json`
7. Postgres sequences: the BETA CLI (`logstashui migrate-engine`) resets them through Django (no `psql`). The dump/load path above does not; use `migrate-engine` when you need sequence reset without a Postgres client.
8. Start LogstashUI. Log in again (sessions were not copied).

### BETA CLI

```bash
# env already points at the empty target server; sqlite file still in DATA_DIR
sudo systemctl stop logstashui    # avoid Restart= racing SIGTERM
logstashui migrate-engine --to postgresql --i-have-a-backup
# optional: --write-env /etc/default/logstashui
sudo systemctl start logstashui
```

`--to mysql` covers MariaDB and MySQL. The command SIGTERMs gunicorn if `$LOGSTASHUI_DATA_DIR/gunicorn.pid` is live, checkpoints WAL, dump/load from the sqlite file in `DATA_DIR` (regardless of target `LOGSTASHUI_DB_*`), and **does not** restart serve.

---

## Kubernetes

Minimum:

1. StatefulSet `replicas: 1`, env from a ConfigMap (`LOGSTASHUI_DB_ENGINE` / `HOST` / `NAME` / `USER`) + Secret (`SECRET_KEY`, `LOGSTASHUI_DB_PASSWORD`)
2. PVC mounted at `/var/lib/logstashui` (still required when the database is external)
3. Container image `CMD` is `logstashui serve` (already the Docker default)
4. Ingress or HTTPRoute: keep `LOGSTASHUI_TLS=true`, originate HTTPS to `:8443`, skip backend cert verify, set `CSRF_TRUSTED_ORIGINS=https://<host>`

No ConfigMap file mount is required. Manifests and CloudNativePG: [Kubernetes](/docs/docs/logstashui/kubernetes/index.md).

---

## systemd

```bash
sudo logstashui systemd          # prompts, writes /etc/default/logstashui + unit
sudo logstashui systemd --print  # preview
sudo logstashui systemd --output-dir /tmp/logstashui-unit
sudo systemctl enable --now logstashui
```

The generator is **manual**. `pip install` does not enable the unit.

---

## CLI

```bash
uv run logstashui                 # serve (HTTPS :8443, data in ./logstashui_data)
uv run logstashui serve --no-tls --bind 0.0.0.0:8080
uv run logstashui manage migrate
uv run logstashui manage runserver 0.0.0.0:8080
python -m LogstashUI
```
