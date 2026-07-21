# SNMP Monitoring

LogstashUI provides comprehensive SNMP monitoring capabilities, allowing you to collect and visualize metrics from network devices, servers, and other SNMP-enabled equipment — without hand-writing a single pipeline.

![SNMP Support](/docs/images/snmp.gif)

## Overview

The SNMP module enables you to:

- **Monitor Network Devices**: Collect metrics from switches, routers, firewalls, and other network equipment
- **Track Server Health**: Monitor servers and infrastructure components via SNMP
- **Auto-Discover Devices**: Scan network ranges to find SNMP devices automatically
- **Receive Traps**: Listen for device-initiated notifications
- **Manage Centrally**: Configure everything from one interface and deploy with a reviewable diff

## Key Concepts

- **Devices** — individual endpoints to monitor. Each has an address, a credential, a network, and a device template.
- **Networks** — monitoring zones with a CIDR range. Every network gets its own generated pipelines, deployment target, polling interval, and namespace.
- **Credentials** — SNMP authentication (v1/v2c community strings or v3 security settings), stored encrypted.
- **Device Templates** — bundles of profiles that define what to collect from a kind of device, with matching rules for auto-suggestion.
- **Profiles** — the actual OID definitions (GET / walk / table) and normalizers. Official profiles ship with LogstashUI; custom profiles are yours.

Read more in **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)**.

## Deployment Modes

Each network deploys its pipelines one of two ways:

- **Centralized Pipeline Management** — pipelines are written to Elasticsearch and picked up by your self-managed Logstash node
- **Logstash Agent** — pipelines are pushed to a Logstash node fully managed by an enrolled [Logstash Agent](/docs/docs/logstashagent/index.md)

See **[Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md)** for the comparison.

## Documentation

### Getting Started
- **[Quickstart Guide](/docs/docs/logstashui/SNMP/Quickstart.md)** - From zero to metrics, in either deployment mode

### Concepts & Configuration
- **[SNMP Architecture](/docs/docs/logstashui/SNMP/architecture.md)** - How the pieces fit together
- **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** - Credentials, networks, devices, templates, and profiles
- **[Device Discovery](/docs/docs/logstashui/SNMP/discovery.md)** - What gets detected, and what doesn't
- **[Trap Support](/docs/docs/logstashui/SNMP/traps.md)** - Receiving device-initiated notifications

### Pipelines & Deployment
- **[Pipeline Generation](/docs/docs/logstashui/SNMP/pipeline_generation.md)** - How configuration becomes Logstash pipelines
- **[Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md)** - The deploy flow and deployment modes

### Data
- **[Data Overview](/docs/docs/logstashui/SNMP/data_overview.md)** - Core Network Vitals and monitoring philosophy
- **[SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md)** - Canonical field names, MIBs, and OIDs
- **[TSDS Implementation](/docs/docs/logstashui/SNMP/tsds_implementation.md)** - Time series storage and query performance

### Tools & Support
- **[Testing & Validation](/docs/docs/logstashui/SNMP/testing.md)** - Test profiles, walk devices, AI-generate templates
- **[Device Support](/docs/docs/logstashui/SNMP/device_support.md)** - When your device isn't in the official catalog
