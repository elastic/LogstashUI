# LogstashUI

> A visual tool for authoring, simulating, and managing Logstash pipelines.
> 
> ⚠️ **Beta Release** - This project is under active development. Features may change.

![LogstashUI Simulation](/docs/images/simulate.png)

## Overview

LogstashUI provides a visual interface for designing, testing, and operating Logstash pipelines.

Instead of editing configuration files manually, pipelines can be authored visually, simulated against sample events, and deployed to multiple Logstash nodes from a single interface.

### Visual Pipeline Editor
Author pipelines in three modes: an inline graphical interface, raw text editor, and a full visual graph for building pipelines by connecting nodes. Switch between modes seamlessly on any pipeline.

![Visual Pipeline Editor](/docs/images/graph.gif)

### Pipeline Simulation
Execute pipelines against sample events and inspect transformations step-by-step.

![Pipeline Simulation](/docs/images/simulate.gif)

### Multi-Instance Management
Manage pipelines across multiple Logstash nodes using Centralized Pipeline Management.

### Pipeline Monitoring
View metrics and performance for running pipelines.

![Pipeline Monitoring](/docs/images/monitoring.png)

### SNMP Support
Configure polling, traps, and discovery through a web interface.

![SNMP Support](/docs/images/snmp.gif)

---

## Documentation

- **[Architecture](/docs/docs/logstashui/architecture.md)** - System architecture
- **[Compatibility](/docs/docs/logstashui/compatibility.md)** - Logstash version compatibility and requirements
- **[Configuration](/docs/docs/logstashui/configuration/index.md)** - Configuration options and settings for LogstashUI
- **[SNMP Monitoring](/docs/docs/logstashui/SNMP/index.md)** - Network monitoring with SNMP polling, traps, and discovery
- **[General](/docs/docs/logstashui/general/index.md)** - Build, update, and deployment guides

---

## Limitations

Comments inside plugin blocks (inline and standalone) are preserved through parsing and serialization, but their exact position relative to config keys is not guaranteed. All comments are grouped at the top of the plugin block in the output:

```
input {
    udp { # inline comments are moved
        port => 5119 # inline comments are moved
    }
}
```

Becomes:

```
input {
    udp {
        # inline comments are moved
        # inline comments are moved
        port => 5119
    }
}
```

---

## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/elastic/LogstashUI/issues/new?template=issue.md).

---

## License

Copyright 2024–2026 Elasticsearch and contributors.

Licensed under the Elastic License 2.0 (ELv2). See [LICENSE](https://github.com/elastic/LogstashUI/blob/main/LICENSE.txt) for details.
