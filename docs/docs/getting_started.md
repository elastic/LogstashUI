# Getting Started

## Requirements

### System Requirements
**Minimum:**
- 8 GB RAM
- 4 CPU Cores

**Why these requirements?**

LogstashUI can run on smaller instances for light usage, especially when only using the editor or basic configuration workflows. The minimum requirements above are intended to provide a reliable baseline for common usage and heavier operations like pipeline simulation and multiple instances of Logstash Agent.

If you choose to run LogstashUI with fewer resources, it will likely work fine, but performance can vary depending on the operation. If the UI feels slow, simulations take too long, or agent operations appear delayed, increase CPU and memory before troubleshooting further.

### Software

#### For Embedded mode (See Quick Start)
- [Docker](https://www.docker.com/get-started/)

#### For [Host mode](/docs/docs/logstashui/configuration/host_mode.md) (If you have a simulation-heavy use case)
- [Docker](https://www.docker.com/get-started/)
- [Python 3.12+](https://www.python.org/downloads/)
- [Logstash 9.x](https://www.elastic.co/docs/reference/logstash/installing-logstash)

### For Local Development
**Required:**
- [Python 3.12+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/) — the Python package/dependency manager the dev commands use
- [Node.js 20+ & npm (for building Tailwind CSS assets)](https://nodejs.org/en/download)

**Optional:**
- [Docker](https://www.docker.com/get-started/) — not required for local development, but handy: if you're developing you'll likely want to test container builds and run the simulation agent.
- [Elasticsearch 8.x or later](https://cloud.elastic.co) — only needed for Monitoring, Centralized Pipeline Management connections, and saving pipelines to Elasticsearch. The pipeline editor and simulation work without it.

## Quick Start
> [!TIP]
> If you plan on doing a lot of simulations, consider using [host mode](/docs/docs/logstashui/configuration/host_mode.md). It's more performant.

### Download LogstashUI
```bash
git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI/bin
```

### Run LogstashUI

**Linux:**
```bash
./start_logstashui.sh
```

**Windows:**
```cmd
start_logstashui.bat
```

Once the containers are running, navigate to your host in your browser:

```
https://<your_server_ip_or_hostname>
```

And that's it!

---

## Add Your First Connection

### 1. Create an initial user
![Login](/docs/images/login.png)

### 2. Add a connection
![New Connection](/docs/images/new_connection.gif)

### 3. Start managing pipelines!
![Simulate](/docs/images/simulate.gif)

### Optional: Add monitoring to your connections
Use [this guide](https://www.elastic.co/docs/reference/logstash/monitoring-with-elastic-agent) to set up the Elastic Agent's Logstash integration. Once Logstash monitoring data is indexed into Elasticsearch, metrics and logs will appear in the UI.

![Monitoring](/docs/images/monitoring.png)

---

## Next Steps

- **[LogstashUI Documentation](/docs/docs/logstashui/index.md)** - Learn about features and configuration
- **[LogstashAgent Documentation](/docs/docs/logstashagent/index.md)** - Set up agents on your Logstash nodes
- **[Documentation Home](/docs/docs/index.md)** - Return to documentation overview
