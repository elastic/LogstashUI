# LogstashUI

> A visual tool for authoring, simulating, and managing Logstash pipelines.
> 
> ⚠️ **Beta Release** - This project is under active development. Features may change.

![LogstashUI Simulation](../images/simulate.png)

## Overview

LogstashUI provides a visual interface for designing, testing, and operating Logstash pipelines.

Instead of editing configuration files manually, pipelines can be authored visually, simulated against sample events, and deployed to multiple Logstash nodes from a single interface.

## Features

### Visual Pipeline Editor
Author pipelines in three modes: an inline graphical interface, raw text editor, and a full visual graph for building pipelines by connecting nodes. Switch between modes seamlessly on any pipeline.

![Visual Pipeline Editor](../images/graph.gif)

### Pipeline Simulation
Execute pipelines against sample events and inspect transformations step-by-step.

![Pipeline Simulation](../images/simulate.gif)

### Multi-Instance Management
Manage pipelines across multiple Logstash nodes using Centralized Pipeline Management.

### Pipeline Monitoring
View metrics and performance for running pipelines.

![Pipeline Monitoring](../images/monitoring.png)

### SNMP Support
Configure polling, traps, and discovery through a web interface.

![SNMP Support](../images/snmp.gif)

---

## Documentation

- **[LogstashUI Documentation](logstashui/index.md)** - Installation, configuration, and usage guides for LogstashUI
- **[LogstashAgent Documentation](logstashagent/index.md)** - Setup and configuration for LogstashAgent

---

## Limitations

Currently, the translation engine cannot process comments inside plugin blocks. For example:

```
input {
    udp { # Translation engine doesn't like this
        port => 5119 # This is a comment that we can't convert
    }
}
```

---

## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/elastic/LogstashUI/issues/new?template=issue.md).

---

## License

Copyright 2024–2026 Elasticsearch and contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE.txt) for details.
