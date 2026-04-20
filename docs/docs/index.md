# Welcome to the LogstashUI Documentation!

> ⚠️ **Beta Release** - This project is under active development. Features may change.

This documentation covers two complementary projects for managing and simulating Logstash pipelines:

---

## LogstashUI

**A visual interface for designing, testing, and operating Logstash pipelines.**

LogstashUI provides a web-based platform for authoring pipelines visually, simulating them against sample events, and deploying them to multiple Logstash nodes from a single interface.

- **Control Plane for Logstash** - Centrally manage Logstash nodes with Centralized Pipeline Management and Logstash Agent
- **Visual Pipeline Editor** - Author pipelines in three modes: graphical interface, text editor, and visual graph
- **Pipeline Simulation** - Execute pipelines against sample events and inspect transformations step-by-step
- **Monitoring** - View metrics and performance for running pipelines and Logstash nodes
- **SNMP Pipeline Management** - Configure polling, traps, discovery, credentials, devices, networks, and profiles through the UI

![LogstashUI Simulation](/docs/images/simulate.png)

**📖 [View LogstashUI Documentation →](/docs/docs/logstashui/index.md)**

---

## LogstashAgent

**A native agent for managing and controlling Logstash instances.**

LogstashAgent is installed on your Logstash nodes and provides complete control over the instance through policy-based management. It handles pipeline deployment, configuration management, and high-performance simulation capabilities.

- **Policy-Based Management** - Control Logstash instances through centralized policies
- **Pipeline Deployment** - Automatically deploy and update pipeline configurations
- **High-Performance Simulation** - Native execution for fast, reliable pipeline testing
- **Complete Instance Control** - Manages Logstash process, configuration, and monitoring

**📖 [View LogstashAgent Documentation →](/docs/docs/logstashagent/index.md)**

---

## Quick Start

New to LogstashUI? Start here:

**[Getting Started Guide →](/docs/docs/getting_started.md)**

---

## Documentation Tree

### 📚 Getting Started
- **[Getting Started Guide](/docs/docs/getting_started.md)** - Installation and first steps

### 🎨 LogstashUI
- **[LogstashUI Overview](/docs/docs/logstashui/index.md)** - Features and introduction

#### Configuration
- **[Configuration Overview](/docs/docs/logstashui/configuration/index.md)**
  - **[logstashui.yml](/docs/docs/logstashui/configuration/logstashui.yml.md)** - Main configuration file reference
  - **[Simulation Modes](/docs/docs/logstashui/configuration/simulation.md)** - Embedded vs Host mode
  - **[Host Mode Setup](/docs/docs/logstashui/configuration/host_mode.md)** - High-performance simulation setup

#### General
- **[General Overview](/docs/docs/logstashui/general/index.md)**
  - **[Building and Running](/docs/docs/logstashui/general/build.md)** - Docker Compose and local development
  - **[Updating LogstashUI](/docs/docs/logstashui/general/updating.md)** - How to update to latest version

### 🤖 LogstashAgent
- **[LogstashAgent Overview](/docs/docs/logstashagent/index.md)** - Features and introduction

#### Configuration
- **[Configuration Overview](/docs/docs/logstashagent/configuration/index.md)**
  - **[logstashagent.yml](/docs/docs/logstashagent/configuration/logstashagent.yml.md)** - Agent configuration file reference

#### General
- **[General Overview](/docs/docs/logstashagent/general/index.md)**
  - **[Building and Running](/docs/docs/logstashagent/general/build.md)** - Docker, enrollment, and controller modes

---

## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/elastic/LogstashUI/issues/new?template=issue.md).

---

## License

Copyright 2024–2026 Elasticsearch and contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE.txt) for details.
