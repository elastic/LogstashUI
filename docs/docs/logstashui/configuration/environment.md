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

Set `LOGSTASHUI_TLS=false` when an ingress terminates TLS and the pod should speak HTTP.

---

## Auth and agent URL

| Variable | Default | Purpose |
|---|---|---|
| `LOGSTASHUI_NO_AUTH` | `false` | Bypass login (**sandbox only**) |
| `LOGSTASHUI_AGENT_UI_URL` | empty | Prefill `--logstash-ui-url` (DB Settings wins if set) |
| `LOGSTASHUI_INCLUDE_CA_FINGERPRINT` | `true` | Embed product CA fingerprint in enrollment tokens |
| `LOGSTASH_AGENT_URL` | debug: `http://127.0.0.1:9500`; else `https://logstashagent:9500` | Embedded/compose agent API |
| `LOGSTASHUI_HOST_HOSTNAME` / `LOGSTASHUI_HOST_IPS` / `LOGSTASHUI_TLS_SANS` | empty | Extra SANs on the product UI cert |
| `LOGSTASHUI_AGENT_CSR_SECRET` | empty | Compose/embedded agent CSR without enroll |
| `LOGSTASHUI_DOCS_DIR` | checkout `docs/` or packaged copy | In-app documentation root |

Booleans accept `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off`.

---

## Database (sqlite only)

| Variable | Default | Purpose |
|---|---|---|
| `LOGSTASHUI_DB_ENGINE` | `sqlite` | **Only `sqlite` is implemented** |

`postgresql` and `mysql` are reserved names: setting them **fails at startup** until those backends land. Keep a PVC on `LOGSTASHUI_DATA_DIR` even after that work (TLS material and secrets still live there).

---

## Kubernetes

Minimum:

1. Deployment env from a ConfigMap + Secret
2. PVC mounted at `/var/lib/logstashui`
3. Container image `CMD` is `logstashui serve` (already the Docker default)
4. Optional ingress: `LOGSTASHUI_TLS=false` and `CSRF_TRUSTED_ORIGINS=https://<host>`

No ConfigMap file mount is required.

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
