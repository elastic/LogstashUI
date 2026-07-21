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

### Getting Started
- **[Getting Started Guide](/docs/docs/getting_started.md)** - Installation and first steps

### LogstashUI
- **[LogstashUI Overview](/docs/docs/logstashui/index.md)** - Features and introduction
- **[Architecture](/docs/docs/logstashui/architecture.md)** - System architecture
- **[Compatibility](/docs/docs/logstashui/compatibility.md)** - Logstash version compatibility

#### Configuration
- **[Configuration Overview](/docs/docs/logstashui/configuration/index.md)**
  - **[logstashui.yml](/docs/docs/logstashui/configuration/logstashui.yml.md)** - Main configuration file reference
  - **[Simulation Modes](/docs/docs/logstashui/configuration/simulation.md)** - Embedded vs Host mode
  - **[Host Mode Setup](/docs/docs/logstashui/configuration/host_mode.md)** - High-performance simulation setup

#### SNMP Monitoring
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Network monitoring introduction
  - **[Quickstart Guide](/docs/docs/logstashui/SNMP/Quickstart.md)** - From zero to metrics
  - **[SNMP Architecture](/docs/docs/logstashui/SNMP/architecture.md)** - How the pieces fit together
  - **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** - Credentials, networks, devices, templates, profiles
  - **[Device Discovery](/docs/docs/logstashui/SNMP/discovery.md)** - Automatic device discovery
  - **[Trap Support](/docs/docs/logstashui/SNMP/traps.md)** - Device-initiated notifications
  - **[Pipeline Generation](/docs/docs/logstashui/SNMP/pipeline_generation.md)** - How pipelines are built
  - **[Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md)** - Deploy flow and deployment modes
  - **[Data Overview](/docs/docs/logstashui/SNMP/data_overview.md)** - Core Network Vitals
  - **[SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md)** - Field names, MIBs, and OIDs
  - **[TSDS Implementation](/docs/docs/logstashui/SNMP/tsds_implementation.md)** - Time series storage
  - **[Testing & Validation](/docs/docs/logstashui/SNMP/testing.md)** - Test profiles and walk devices
  - **[Device Support](/docs/docs/logstashui/SNMP/device_support.md)** - Unsupported device workflow

#### General
- **[General Overview](/docs/docs/logstashui/general/index.md)**
  - **[Deploying LogstashUI](/docs/docs/logstashui/general/deploy.md)** - All deployment options
  - **[Building from Source](/docs/docs/logstashui/general/build.md)** - Source builds and local development
  - **[Updating LogstashUI](/docs/docs/logstashui/general/updating.md)** - How to update to latest version

### LogstashAgent
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

Licensed under the Elastic License 2.0 (ELv2). See [LICENSE](https://github.com/elastic/LogstashUI/blob/main/LICENSE.txt) for details.
