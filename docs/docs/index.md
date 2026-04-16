# Welcome to the LogstashUI Documentation!

> ⚠️ **Beta Release** - This project is under active development. Features may change.

This documentation covers two complementary projects for managing and simulating Logstash pipelines:

---

## LogstashUI

**A visual interface for designing, testing, and operating Logstash pipelines.**

LogstashUI provides a web-based platform for authoring pipelines visually, simulating them against sample events, and deploying them to multiple Logstash nodes from a single interface.

### Key Features
- **Visual Pipeline Editor** - Author pipelines in three modes: graphical interface, text editor, and visual graph
- **Pipeline Simulation** - Test pipelines against sample events and inspect transformations step-by-step
- **Multi-Instance Management** - Deploy and manage pipelines across multiple Logstash nodes
- **Pipeline Monitoring** - View metrics and performance for running pipelines
- **SNMP Support** - Configure SNMP polling, traps, and discovery

![LogstashUI Simulation](../images/simulate.png)

**📖 [View LogstashUI Documentation →](logstashui/index.md)**

---

## LogstashAgent

**A native agent for managing and controlling Logstash instances.**

LogstashAgent is installed on your Logstash nodes and provides complete control over the instance through policy-based management. It handles pipeline deployment, configuration management, and high-performance simulation capabilities.

### Key Features
- **Policy-Based Management** - Control Logstash instances through centralized policies
- **Pipeline Deployment** - Automatically deploy and update pipeline configurations
- **High-Performance Simulation** - Native execution for fast, reliable pipeline testing
- **Complete Instance Control** - Manages Logstash process, configuration, and monitoring

**📖 [View LogstashAgent Documentation →](logstashagent/index.md)**

---

## Quick Start

New to LogstashUI? Start here:

**[Getting Started Guide →](getting_started.md)**

---

## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/elastic/LogstashUI/issues/new?template=issue.md).

---

## License

Copyright 2024–2026 Elasticsearch and contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE.txt) for details.
