# Building and Running LogstashAgent

LogstashAgent can be run in multiple ways depending on your use case.

---

## Using Docker Compose (Recommended for Testing)

The easiest way to run LogstashAgent standalone for testing:

```bash
cd LogstashAgent/docker
docker-compose up --build
```

This will:
- Build the LogstashAgent Docker image with Python 3.12
- Start Logstash with the agent supervisor
- Expose ports:
  - `9650`: Logstash API
  - `9449`: Logstash HTTP input (for simulation)
  - `9500`: FastAPI sidecar API

### Configuration

Set the LogstashUI URL via environment variable:

```bash
LOGSTASH_URL=http://your-logstashui:8080 docker-compose up --build
```

Or mount a custom config:

```yaml
# docker-compose.yml
volumes:
  - ./logstashui.yml:/app/logstashui.yml:ro
```

---

## Building Docker Image Manually

Build the image:

```bash
cd LogstashAgent
docker build -t logstashagent:latest -f docker/Dockerfile .
```

Run the container:

```bash
docker run -p 9650:9650 -p 9449:9449 -p 9500:9500 \
  -e LOGSTASH_URL=http://host.docker.internal:8080 \
  --add-host host.docker.internal:host-gateway \
  logstashagent:latest
```

---

## Running Locally (Development)

### Prerequisites

- Python 3.12+
- Logstash 9.x installed locally
- `uv` (recommended) or `pip`
- Node.js 20+ & npm

### Install Dependencies

```bash
cd LogstashAgent
uv sync
```

Or with pip:

```bash
cd LogstashAgent
pip install -e .
```

### Configure

(OPTIONAL) Copy and edit the example config:

```bash
cp src/logstashagent/config/logstashagent.example.yml src/logstashagent/config/logstashagent.yml
```

Edit `logstashagent.yml` to point to your local Logstash installation.

### Start the agent in simulation mode (default)

```bash
python src/logstashagent/main.py
```

The agent will be available at:
- FastAPI API: http://localhost:9500
- Logstash API: http://localhost:9650
- Simulation Input: http://localhost:9449

---

## Enrollment Mode (Controller)

To enroll the agent with LogstashUI:

```bash
python src/logstashagent/main.py --enroll=<BASE64_TOKEN> --logstash-ui-url=http://localhost:8080
```

Then run in controller mode:

```bash
python src/logstashagent/main.py --run
```

---

## Docker Build Notes

The Dockerfile:
- Starts from the official Logstash 9.3.1 image
- Compiles Python 3.12 from source (microdnf only provides Python 3.9)
- Installs dependencies using `uv` for faster resolution
- Copies the entire `src/` directory for proper package structure
- Sets `PYTHONPATH=/app/src` for module imports

Build time is approximately 5-10 minutes due to Python compilation.

---

## Building a Standalone Binary (PyInstaller)

The CI/CD release pipeline uses [PyInstaller](https://pyinstaller.org/) to produce a self-contained `logstash-agent` executable. You can replicate this locally whenever you need to cut a manual build.

### Prerequisites

- Python 3.12+
- `uv` installed

### Steps

**1. Install dev dependencies** (PyInstaller lives in the `dev` dependency group):

```bash
cd LogstashAgent
uv sync --dev
```

**2. Run PyInstaller against the spec file:**

```bash
uv run pyinstaller logstash-agent.spec
```

The spec file (`logstash-agent.spec` at the repo root) points PyInstaller at `src/logstashagent/main.py` as the entry point and produces a **directory bundle** (not a single file) under `dist/logstash-agent/`.

**3. Archive the bundle for distribution:**

```bash
mkdir -p release
tar -czf release/logstash-agent-linux-amd64.tar.gz -C dist logstash-agent
```

The resulting archive matches what is uploaded as a GitHub release asset on every `v*` tag.

### Spec File Notes

The `logstash-agent.spec` uses `COLLECT` mode (i.e. `exclude_binaries=True` on the `EXE`), so the output is a **folder** containing the executable and its bundled libraries, not a single standalone file. UPX compression is enabled for both the executable and collected binaries.

| Setting | Value |
|---|---|
| Entry point | `src/logstashagent/main.py` |
| Output name | `logstash-agent` |
| Output mode | Directory bundle (`dist/logstash-agent/`) |
| UPX compression | Enabled |
| Console | Yes |

---

## Related Documentation

- **[Configuration](/docs/docs/logstashagent/configuration/index.md)** - Configure LogstashAgent settings
- **[General Overview](/docs/docs/logstashagent/general/index.md)** - Return to general guides index
- **[LogstashAgent Overview](/docs/docs/logstashagent/index.md)** - Return to LogstashAgent documentation
- **[LogstashUI Documentation](/docs/docs/logstashui/index.md)** - Main LogstashUI documentation
