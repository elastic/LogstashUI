# LogstashUI

> A visual tool for authoring, simulating, and managing Logstash pipelines.
> 
> ⚠️ **Beta Release** - This project is under active development. Features may change.

📖 **[View Documentation](https://elastic.github.io/LogstashUI/)**

<img src="docs/images/simulate.png" width="100%">

## Overview

LogstashUI provides a visual interface for designing, testing, and operating Logstash pipelines.

Instead of editing configuration files manually, pipelines can be authored visually, simulated against sample events, and deployed to multiple Logstash nodes from a single interface.

## Features

<details>
<summary><b>Visual Pipeline Editor</b> — Author pipelines in three modes: an inline graphical interface, raw text editor, and a full visual graph for building pipelines by connecting nodes. Switch between modes seamlessly on any pipeline.</summary>

![Visual Pipeline Editor](docs/images/graph.gif)

</details>

<details>
<summary><b>Pipeline Simulation</b> — Execute pipelines against sample events and inspect transformations step-by-step</summary>

![Pipeline Simulation](docs/images/simulate.gif)

</details>

<details>
<summary><b>Multi-Instance Management</b> — Manage pipelines across multiple Logstash nodes using Centralized Pipeline Management</summary>

</details>

<details>
<summary><b>Pipeline Monitoring</b> — View metrics and performance for running pipelines</summary>

![Pipeline Monitoring](docs/images/monitoring.png)

</details>

<details>
<summary><b>SNMP Support</b> — Configure polling, traps, and discovery through a web interface</summary>

![SNMP Support](docs/images/snmp.gif)

</details>


## Requirements

### System Requirements
**Minimum:**
- 8 GB RAM
- 4 CPU Cores

### Software

#### For Embedded mode (See Quick Start)
- [Docker](https://www.docker.com/get-started/)

#### For [Host mode](docs/docs/beta/PipelineEditor/host_mode.md) (If you have a simulation-heavy use case)
- [Docker](https://www.docker.com/get-started/)
- [Python 3.12+](https://www.python.org/downloads/)
- [Logstash 8.x, 9.x](https://www.elastic.co/docs/reference/logstash/installing-logstash)


### For Local Development
- [Python 3.12+](https://www.python.org/downloads/)
- [Node.js & npm (for building Tailwind CSS assets)](https://nodejs.org/en/download)
- [Elasticsearch 8.x or later](https://cloud.elastic.co)
- [Docker](https://www.docker.com/get-started/)


## Quick Start - Embedded Mode
> [!TIP]
> If you plan on doing a lot of simulations, consider using [host mode](docs/docs/beta/PipelineEditor/host_mode.md). It's more performant.
### Download LogstashUI
```bash
git clone https://github.com/elastic/LogstashUI.git
cd logstashui/bin
````

### Run LogstashUI
#### Linux
```cmd
./start_logstashui.sh
```

#### Windows
```cmd
start_logstashui.bat
```

Once the containers are running, navigate to your host in your browser:

https://<your_server_ip_or_hostname>

And that's it!

---
## Add Your First Connection

### 1. Create an initial user
<img src="docs/images/login.png" width="400px">

### 2. Add a connection
<img src="docs/images/new_connection.gif" width="800px">

### 3. Start managing pipelines!
<img src="docs/images/simulate.gif" width="800px">


### Optional: Add monitoring to your connections:
Use [this guide](https://www.elastic.co/docs/reference/logstash/monitoring-with-elastic-agent) to set up the Elastic Agent's Logstash integration. Once Logstash monitoring data is indexed into Elasticsearch, metrics and logs will appear in the UI.

<img src="docs/images/monitoring.png" width="800px">

## Updating

LogstashUI will notify you when a new version is available via a banner in the navigation sidebar:

To update LogstashUI to the latest version:

#### Linux
```bash
cd logstashui/bin
./start_logstashui.sh --update
```

#### Windows
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