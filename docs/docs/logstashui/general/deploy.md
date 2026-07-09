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

Then browse to `https://<your_server_ip_or_hostname>`.

This is **embedded mode** — the default `simulation.mode` — which brings up three containers: **LogstashUI** (the web app), **LogstashAgent** (pipeline simulation), and **Nginx** (HTTPS reverse proxy on port 443). The mode is controlled by `simulation.mode` in [`logstashui.yml`](/docs/docs/logstashui/configuration/logstashui.yml.md); leave it as `embedded` for this option.

> [!NOTE]
> If you run Docker Compose directly instead of using the scripts, the simulation agent is gated behind the `embedded` Compose profile: `cd docker && docker compose --profile embedded up -d`. A plain `docker compose up` starts only LogstashUI and Nginx.

---

## Option 2: Host-backed Simulation

Use this when you want LogstashUI to run normally, but pipeline simulation should execute against a host-installed Logstash instance. Recommended for frequent or heavy simulation workloads — it's more reliable than the embedded container.

**Requirements:** [Docker](https://www.docker.com/get-started/), [Python 3.12+](https://www.python.org/downloads/), [Logstash 9.x](https://www.elastic.co/docs/reference/logstash/installing-logstash) (a dedicated instance that is not running production pipelines)

This uses the **same startup script as Option 1** — the difference is one setting. Set `simulation.mode: host` in [`logstashui.yml`](/docs/docs/logstashui/configuration/logstashui.yml.md) (see [Simulation Configuration](/docs/docs/logstashui/configuration/simulation.md)) before running it. The script then runs the simulation agent natively on the host (port 9501) and starts only the LogstashUI and Nginx containers; Nginx proxies simulation traffic to the native agent.

**📖 Full setup guide: [Host Mode Setup](/docs/docs/logstashui/configuration/host_mode.md)**

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
