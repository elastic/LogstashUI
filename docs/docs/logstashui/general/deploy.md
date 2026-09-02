# Deploying LogstashUI

The ways to deploy LogstashUI, from the standard Docker install to running from source.

> [!TIP]
> If you have internet access and can use Docker and GitHub, use **Option 1** — it's the standard install and takes a couple of minutes. See the [Getting Started guide](/docs/docs/getting_started.md) for the step-by-step walkthrough.

- [Option 1: Standard Docker Deployment (Recommended)](#option-1-standard-docker-deployment-recommended)
- [Option 2: Host-backed Simulation](#option-2-host-backed-simulation)
- [Option 3: pip / uv + systemd](#option-3-pip--uv--systemd)
- [Option 4: Source Development Setup](#option-4-source-development-setup)
- [Option 5: Kubernetes](#option-5-kubernetes)

---

## Option 1: Standard Docker Deployment (Recommended)

Use this when you want the simplest, self-contained deployment.

**Requirements:** [Docker](https://www.docker.com/get-started/)

**Who is this for?** Users who can access GitHub and container registries from the deployment network and can run Docker Compose on the LogstashUI host.

The startup scripts start Docker Compose (`--profile embedded` by default):

```bash
git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI/bin
./start_logstashui.sh        # Linux
start_logstashui.bat         # Windows
```

Then browse to `https://<your_server_ip_or_hostname>:8443`.

This is **embedded mode** — two containers: **LogstashUI** (gunicorn HTTPS on **8443**) and **LogstashAgent** (uvicorn HTTPS on **9500**). There is **no nginx**. Configuration is [environment variables](/docs/docs/logstashui/configuration/environment.md).

**Data directory:** Runtime state (sqlite, TLS, secrets, logs) lives **outside** `src/`. From a git checkout, Docker Compose bind-mounts `<project_root>/logstashui_data` to `/var/lib/logstashui` and sets `LOGSTASHUI_DATA_DIR`. Native CLI default (no env) is `$(pwd)/logstashui_data`. Do not store this under `src/logstashui/data`. The database may be external Postgres/MySQL; the PVC/bind-mount is still required for TLS and secrets.

On **Linux Docker**, that bind-mount keeps host file ownership. The image entrypoint starts as root, chowns **only** the data directory if it is not writable, then drops to `PUID`/`PGID` (from `start_logstashui.sh`: your uid/gid) or image user **appuser (10001)**. Gunicorn never stays root. Docker Desktop (macOS/Windows) usually maps UIDs already; the same path is a no-op chown. If the directory is still unwritable, startup exits before migrate so sqlite/TLS are not created as the wrong user.

**Kubernetes:** see [Option 5](#option-5-kubernetes) and the [Kubernetes subsection](/docs/docs/logstashui/kubernetes/index.md). PVC at `/var/lib/logstashui`, `runAsUser: 10001`, `runAsNonRoot: true`, `fsGroup: 10001`. Keep `LOGSTASHUI_TLS` on; the Ingress/HTTPRoute originates HTTPS to `:8443` and skips backend cert verify.

**HTTPS / product CA:** On first start, LogstashUI writes a product CA and a UI server certificate under `$LOGSTASHUI_DATA_DIR/tls/` (`ui-server.crt` / `ui-server.key`). Gunicorn presents that cert on port **8443** (ports under 1000 would need root). The product leaf SANs include `localhost`, `logstashui`, **all non-loopback host IPs**, and **PTR reverse-DNS FQDNs** for those IPs when available (injected by `start_logstashui.sh` as `LOGSTASHUI_HOST_*` / `LOGSTASHUI_TLS_SANS`, because the container cannot see the host LAN addresses by itself). Bare short hostnames (common on macOS) are replaced by reverse-lookup FQDNs when PTR records exist. Changing the Agent callback URL or those env SANs **re-issues** the product leaf on next startup (or Settings save); restart the UI container so gunicorn reloads the file. Agents:

1. Bootstrap-fetch `https://…:8443/.well-known/logstashui/ca.crt` with **verify=False only for that GET**, then pin the CA (TOFU or enrollment-token fingerprint).
2. Obtain a **product-CA-signed server cert** (CSR at enroll, re-issue on check-in, or compose `LOGSTASHUI_AGENT_CSR_SECRET`) and serve FastAPI over HTTPS on **9500**.

Browsers warn on the product default leaf until you trust the product CA or upload a public/custom cert under **Management → Settings**. After changing the UI certificate, restart the UI container (`docker compose restart logstashui`).

> [!NOTE]
> If you run Docker Compose directly instead of using the scripts, the simulation agent is gated behind the `embedded` Compose profile: `cd docker && docker compose --profile embedded up -d`. A plain `docker compose up` starts only LogstashUI.

---

## Option 2: Host-backed Simulation (prefer enrolled Simulate agents)

For frequent or heavy simulation, enroll one or more **Simulate** policy agents (`lsagent-simulate@N` / isolated `simulate-N` paths). Select them in the pipeline editor **Sim target** control.

**Preferred:** [Simulate agents setup](/docs/docs/logstashui/configuration/host_mode.md)

**Legacy alternative:** `./start_logstashui.sh --legacy-host-agent` starts a **native FastAPI agent on port 9501** (supervisor, not enrolled `mode: simulate`) and only the UI container. Prefer enrolled Simulate agents for multi-instance or production-quality sim.

---

## Option 3: pip / uv + systemd

```bash
pip install logstashui-0.5.1-py3-none-any.whl   # or: uv pip install …
logstashui                                       # HTTPS :8443, data in $(pwd)/logstashui_data
sudo logstashui systemd                          # writes /etc/default/logstashui + unit; does not enable
sudo systemctl enable --now logstashui
```

Set `LOGSTASHUI_DATA_DIR=/var/lib/logstashui` in `/etc/default/logstashui` (the generator does this). See [environment configuration](/docs/docs/logstashui/configuration/environment.md).

Kubernetes: [Option 5](#option-5-kubernetes). Same image as Option 1; env/ConfigMap plus Secret; PVC at `/var/lib/logstashui`. Keep TLS on. No YAML mount.

---

## Option 4: Source Development Setup

Use this when you want to run LogstashUI directly from source for development or contribution work.

**Requirements:** [Python 3.12+](https://www.python.org/downloads/), [Node.js 20+ & npm](https://nodejs.org/en/download) (for building Tailwind CSS assets)

**📖 Full instructions: [Building LogstashUI from Source](/docs/docs/logstashui/general/build.md)**

---

## Option 5: Kubernetes

One-replica StatefulSet, PVC at `/var/lib/logstashui`, image `codyjackson032/logstashui:latest` (or a tag you built). Gunicorn keeps HTTPS on **8443** (`LOGSTASHUI_TLS` stays true). Ingress-nginx or Envoy Gateway originates HTTPS to the pod and skips verification of the product self-signed leaf.

- Guide: [Kubernetes](/docs/docs/logstashui/kubernetes/index.md)
- Manifests: [examples](/docs/docs/logstashui/kubernetes/examples/README.md) (SQLite, PostgreSQL, MySQL/MariaDB)
- CloudNativePG: [cnpg.md](/docs/docs/logstashui/kubernetes/cnpg.md)
- Envoy Gateway Backend API: [envoy-gateway.md](/docs/docs/logstashui/kubernetes/envoy-gateway.md)
- Database env and migration: [Database](/docs/docs/logstashui/database/index.md)

---

## Related Documentation

- **[Getting Started](/docs/docs/getting_started.md)** - Step-by-step standard install
- **[Kubernetes](/docs/docs/logstashui/kubernetes/index.md)** - StatefulSet, PVC, Ingress, Envoy Gateway, CNPG
- **[Database](/docs/docs/logstashui/database/index.md)** - SQLite, PostgreSQL, MySQL/MariaDB
- **[Building LogstashUI from Source](/docs/docs/logstashui/general/build.md)** - Source builds and local development
- **[Host Mode Setup](/docs/docs/logstashui/configuration/host_mode.md)** - High-performance simulation setup
- **[Updating LogstashUI](/docs/docs/logstashui/general/updating.md)** - Keeping your deployment current
- **[General Overview](/docs/docs/logstashui/general/index.md)** - Return to general guides index
