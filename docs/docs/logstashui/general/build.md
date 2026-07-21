# Building LogstashUI from Source

How to run LogstashUI from the checked-out source tree, and how to build the Docker image locally. If you just want to deploy LogstashUI, see the [Deployment Guide](/docs/docs/logstashui/general/deploy.md) instead.

---

## Running from Source (Development)

### Prerequisites

Install these first (the same on any OS) — the setup blocks below clone the repo for you:

1. Install [Python 3.12+](https://www.python.org/downloads/)
2. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
3. Install [Node.js 20+ & npm](https://nodejs.org/en/download) (for building Tailwind CSS assets)

Also note:

- LogstashAgent runs separately for simulation features (see the [LogstashAgent build guide](/docs/docs/logstashagent/general/build.md))
- Elasticsearch 8.x+ is optional — only needed for Monitoring, Centralized Pipeline Management connections, and saving pipelines to Elasticsearch

### Setup and Run

Each block below is self-contained — you can run it top to bottom like a script.

> [!TIP]
> If the `tailwind install` step errors out, chances are you're running an old version of Node.js. Update to Node.js 20+ and try again.

#### Linux
```bash
git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI
uv sync
cd src/logstashui/

uv run manage.py migrate
uv run manage.py tailwind install
uv run manage.py tailwind build
uv run manage.py collectstatic --noinput
uv run manage.py sync_snmp_official_data --cleanup

LOGSTASHUI_CONFIG=logstashui.example.yml uv run manage.py runserver 0.0.0.0:8080
```

#### Windows (PowerShell)
```powershell
git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI
uv sync
cd src/logstashui/

uv run manage.py migrate
uv run manage.py tailwind install
uv run manage.py tailwind build
uv run manage.py collectstatic --noinput
uv run manage.py sync_snmp_official_data --cleanup

$env:LOGSTASHUI_CONFIG="logstashui.example.yml"
uv run manage.py runserver 0.0.0.0:8080
```

> [!NOTE]
> Relative `LOGSTASHUI_CONFIG` paths resolve from your current working directory — the commands above work because you `cd src/logstashui` first. If `LOGSTASHUI_CONFIG` is not set, LogstashUI falls back to `src/logstashui/logstashui.yml` (and then the data directory) automatically.

---

## Building the Docker Image Locally

The standard deployment pulls the published `codyjackson032/logstashui` image. To build it from source instead, uncomment the `build:` block in `docker/docker-compose.yml`:

```yaml
services:
  logstashui:
    image: codyjackson032/logstashui:latest
    build:
      context: ..
      dockerfile: docker/Dockerfile
```

Then build and start:

```bash
cd docker
docker compose --profile embedded up -d --build
```

Or build the image directly without Compose:

```bash
docker build -t codyjackson032/logstashui:latest -f docker/Dockerfile .
```

(run from the repository root — the build context is the whole source tree).

The **LogstashAgent** image builds from the separate [LogstashAgent repository](https://github.com/elastic/LogstashAgent); see its build guide for instructions.

---

## Related Documentation

- **[Deployment Guide](/docs/docs/logstashui/general/deploy.md)** - All the ways to deploy LogstashUI
- **[Updating LogstashUI](/docs/docs/logstashui/general/updating.md)** - How to update to the latest version
- **[Configuration](/docs/docs/logstashui/configuration/index.md)** - Configure LogstashUI settings
- **[General Overview](/docs/docs/logstashui/general/index.md)** - Return to general guides index
- **[Getting Started](/docs/docs/getting_started.md)** - Quick start guide
