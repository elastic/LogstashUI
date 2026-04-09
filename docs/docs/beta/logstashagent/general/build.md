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
  - `9600`: Logstash API
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
docker run -p 9600:9600 -p 9449:9449 -p 9500:9500 \
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

Copy and edit the example config:

```bash
cp src/logstashagent/config/logstashagent.example.yml src/logstashagent/config/logstashagent.yml
```

Edit `logstashagent.yml` to point to your local Logstash installation.

### Run

Start the agent in simulation mode (default):

```bash
python src/logstashagent/main.py
```

The agent will be available at:
- FastAPI API: http://localhost:9500
- Logstash API: http://localhost:9600
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
