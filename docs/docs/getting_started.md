# Getting Started

## Requirements

### System Requirements
**Minimum:**
- 8 GB RAM
- 4 CPU Cores

### Software

#### For Embedded mode (See Quick Start)
- [Docker](https://www.docker.com/get-started/)

#### For [Host mode](logstashui/configuration/host_mode.md) (If you have a simulation-heavy use case)
- [Docker](https://www.docker.com/get-started/)
- [Python 3.12+](https://www.python.org/downloads/)
- [Logstash 8.x, 9.x](https://www.elastic.co/docs/reference/logstash/installing-logstash)

### For Local Development
- [Python 3.12+](https://www.python.org/downloads/)
- [Node.js & npm (for building Tailwind CSS assets)](https://nodejs.org/en/download)
- [Elasticsearch 8.x or later](https://cloud.elastic.co)
- [Docker](https://www.docker.com/get-started/)

## Quick Start - Embedded Mode

> **Tip:** If you plan on doing a lot of simulations, consider using [host mode](logstashui/configuration/host_mode.md). It's more performant.

### Download LogstashUI
```bash
git clone https://github.com/elastic/LogstashUI.git
cd logstashui/bin
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
![Login](docs/images/login.png)

### 2. Add a connection
![New Connection](docs/images/new_connection.gif)

### 3. Start managing pipelines!
![Simulate](docs/images/simulate.gif)

### Optional: Add monitoring to your connections
Use [this guide](https://www.elastic.co/docs/reference/logstash/monitoring-with-elastic-agent) to set up the Elastic Agent's Logstash integration. Once Logstash monitoring data is indexed into Elasticsearch, metrics and logs will appear in the UI.

![Monitoring](docs/images/monitoring.png)
