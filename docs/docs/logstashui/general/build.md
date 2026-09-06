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
# Tailwind (first clone only)
cd src/logstashui
uv run manage.py tailwind install
uv run manage.py tailwind build
cd ../..

uv run logstashui manage migrate
uv run logstashui manage collectstatic --noinput
uv run logstashui manage sync_snmp_official_data --cleanup

# Product-like HTTPS on :8443 (data in ./logstashui_data)
uv run logstashui

# Or Django runserver (HTTP):
uv run logstashui manage runserver 0.0.0.0:8080
```

#### Windows (PowerShell)
```powershell
git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI
uv sync
cd src/logstashui
uv run manage.py tailwind install
uv run manage.py tailwind build
cd ../..

uv run logstashui manage migrate
uv run logstashui manage collectstatic --noinput
uv run logstashui manage sync_snmp_official_data --cleanup
uv run logstashui
```

> [!NOTE]
> Configuration is environment variables only. Native default data dir is `$(pwd)/logstashui_data`. See [environment configuration](/docs/docs/logstashui/configuration/environment.md).

---

## Contributing Setup (Pre-commit Hooks)

After your first `uv sync`, install the git pre-commit hooks once:

```bash
uv run pre-commit install
```

The hooks run automatically on every `git commit` and handle two things:

- **License headers** — adds the Elastic license notice to any source file that doesn't have one yet
- **Dependency notices** — regenerates `NOTICE.txt` to reflect any new third-party packages

### Windows developers

Set git's line-ending mode to `input` **before your first commit**. This prevents git from converting LF to CRLF on checkout, which fights the repo's `.gitattributes` settings and produces phantom "modified" files:

```powershell
git config --global core.autocrlf input
```

You only need to run this once — it applies to all your repos globally.

---

## Building an sdist and wheel

Compile Tailwind first (the `dist/` CSS path is not `node_modules`; repo-root `/dist/` is the packaging output):

```bash
cd src/logstashui/theme/static_src
npm install && npm run build
cd ../../../..
uv build
# dist/logstashui-0.5.2.tar.gz
# dist/logstashui-0.5.2-py3-none-any.whl
```

The wheel includes systemd templates (`LogstashUI/packaging/`) and the `logstashui` console script.

Air-gapped hosts that cannot reach PyPI or a registry: optional `bin/freeze_logstashui.sh` (not default packaging). See [Air-gapped freeze](/docs/docs/logstashui/general/offline.md).

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
