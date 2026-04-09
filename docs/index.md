---
layout: default
title: Home
description: A visual tool for authoring, simulating, and managing Logstash pipelines
---

# LogstashUI

> A visual tool for authoring, simulating, and managing Logstash pipelines.
> 
> ⚠️ **Beta Release** - This project is under active development. Features may change.

![LogstashUI Simulation](images/simulate.png)

## Overview

LogstashUI provides a visual interface for designing, testing, and operating Logstash pipelines.

Instead of editing configuration files manually, pipelines can be authored visually, simulated against sample events, and deployed to multiple Logstash nodes from a single interface.

## Features

### Visual Pipeline Editor
Author pipelines in three modes: an inline graphical interface, raw text editor, and a full visual graph for building pipelines by connecting nodes. Switch between modes seamlessly on any pipeline.

![Visual Pipeline Editor](images/graph.gif)

### Pipeline Simulation
Execute pipelines against sample events and inspect transformations step-by-step.

![Pipeline Simulation](images/simulate.gif)

### Multi-Instance Management
Manage pipelines across multiple Logstash nodes using Centralized Pipeline Management.

### Pipeline Monitoring
View metrics and performance for running pipelines.

![Pipeline Monitoring](images/monitoring.png)

### SNMP Support
Configure polling, traps, and discovery through a web interface.

![SNMP Support](images/snmp.gif)

## Requirements

### System Requirements
**Minimum:**
- 8 GB RAM
- 4 CPU Cores

### Software

#### For Embedded mode (See Quick Start)
- [Docker](https://www.docker.com/get-started/)

#### For [Host mode](docs/beta/configuration/host_mode) (If you have a simulation-heavy use case)
- [Docker](https://www.docker.com/get-started/)
- [Python 3.12+](https://www.python.org/downloads/)
- [Logstash 8.x, 9.x](https://www.elastic.co/docs/reference/logstash/installing-logstash)

## Quick Start - Embedded Mode

> **Tip:** If you plan on doing a lot of simulations, consider using [host mode](docs/beta/configuration/host_mode). It's more performant.

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
![Login](images/login.png)

### 2. Add a connection
![New Connection](images/new_connection.gif)

### 3. Start managing pipelines!
![Simulate](images/simulate.gif)

### Optional: Add monitoring to your connections
Use [this guide](https://www.elastic.co/docs/reference/logstash/monitoring-with-elastic-agent) to set up the Elastic Agent's Logstash integration. Once Logstash monitoring data is indexed into Elasticsearch, metrics and logs will appear in the UI.

![Monitoring](images/monitoring.png)

## Updating

LogstashUI will notify you when a new version is available via a banner in the navigation sidebar.

To update LogstashUI to the latest version:

**Linux:**
```bash
cd logstashui/bin
./start_logstashui.sh --update
```

**Windows:**
```cmd
cd LogstashUI\bin
start_logstashui.bat --update
```

## Limitations
- Currently, the translation engine cannot process comments inside plugin blocks. For example:

```
input {
    udp { # Translation engine doesn't like this
        port => 5119 # This is a comment that we can't convert
    }
}
```

## Roadmap
- Reusable grok and regex patterns
- Git backups for configuration
- Loggy AI Assistant for pipeline failure analysis
- Management of Logstash Nodes via external agent
- Logstash Keystore management
- Expression editor for conditions

## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/elastic/LogstashUI/issues/new?template=issue.md).

## Contributing

Contributions are welcome!

Please open an issue to discuss large changes before submitting a pull request.

## License

Copyright 2024–2026 Elasticsearch and contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE.txt) for details.
