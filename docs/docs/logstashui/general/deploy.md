# Deploying LogstashUI

The ways to deploy LogstashUI, from the standard Docker install to running from source.

> [!TIP]
> If you have internet access and can use Docker and GitHub, use **Option 1** — it's the standard install and takes a couple of minutes. See the [Getting Started guide](/docs/docs/getting_started.md) for the step-by-step walkthrough.

- [Option 1: Standard Docker Deployment (Recommended)](#option-1-standard-docker-deployment-recommended)
- [Option 2: Host-backed Simulation](#option-2-host-backed-simulation)
- [Option 3: Source Development Setup](#option-3-source-development-setup)

---

## Option 1: Standard Docker Deployment (Recommended)

Use this when you want the simplest, self-contained deployment.

**Requirements:** [Docker](https://www.docker.com/get-started/)

**Who is this for?** Users who can access GitHub and container registries from the deployment network and can run Docker Compose on the LogstashUI host.

The startup scripts handle everything — they read `simulation.mode` from `src/logstashui/logstashui.yml` (creating it from the example config on first run) and start the right services:

```bash
git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI/bin
./start_logstashui.sh        # Linux
start_logstashui.bat         # Windows
```

Then browse to `https://<your_server_ip_or_hostname>:8443`.

This is **embedded mode** — the default `simulation.mode` — which brings up two containers: **LogstashUI** (gunicorn HTTPS on **8443**) and **LogstashAgent** (uvicorn HTTPS on **9500**). There is **no nginx**. The mode is controlled by `simulation.mode` in [`logstashui.yml`](/docs/docs/logstashui/configuration/logstashui.yml.md); leave it as `embedded` for this option.

**Data directory:** Runtime state (sqlite, TLS, secrets, logs) lives **outside** `src/`. From a git checkout, Docker Compose bind-mounts `<project_root>/logstashui_data` to `/var/lib/logstashui` and sets `LOGSTASHUI_DATA_DIR`. Override with `LOGSTASHUI_DATA_DIR` / `LOGSTASHUI_LOGS_DIR` or `paths.data` / `paths.logs` in `logstashui.yml`. Do not store this under `src/logstashui/data`.

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

**Legacy alternative:** Set `simulation.mode: host` in [`logstashui.yml`](/docs/docs/logstashui/configuration/logstashui.yml.md) and run the same startup script as Option 1. That path starts a **native FastAPI agent on port 9501** (supervisor, not enrolled `mode: simulate`) and only the UI/nginx containers. Prefer enrolled Simulate agents for multi-instance or production-quality sim.

---

## Option 3: Source Development Setup

Use this when you want to run LogstashUI directly from source for development or contribution work.

**Requirements:** [Python 3.12+](https://www.python.org/downloads/), [Node.js 20+ & npm](https://nodejs.org/en/download) (for building Tailwind CSS assets)

**📖 Full instructions: [Building LogstashUI from Source](/docs/docs/logstashui/general/build.md)**

---

## Related Documentation

- **[Getting Started](/docs/docs/getting_started.md)** - Step-by-step standard install
- **[Building LogstashUI from Source](/docs/docs/logstashui/general/build.md)** - Source builds and local development
- **[Host Mode Setup](/docs/docs/logstashui/configuration/host_mode.md)** - High-performance simulation setup
- **[Updating LogstashUI](/docs/docs/logstashui/general/updating.md)** - Keeping your deployment current
- **[General Overview](/docs/docs/logstashui/general/index.md)** - Return to general guides index
