# SNMP Architecture

How LogstashUI turns your monitoring configuration into running Logstash pipelines and indexed data.

## The Big Picture

LogstashUI is the **control plane**: you describe *what* to monitor (devices, networks, credentials, templates), and it generates and delivers the Logstash pipelines that do the actual polling. Logstash nodes are the **data plane**: they run the generated pipelines and ship results to Elasticsearch.

![SNMP Architecture](/docs/images/snmp_architecture.png)

## Components

### Configuration (staged in LogstashUI's database)

| Concept | What it is |
|---|---|
| **Credential** | SNMP authentication (v1/v2c community string, or v3 security settings). Stored encrypted. |
| **Network** | A monitoring zone with a CIDR range, deployment mode, polling interval, and toggles for discovery and traps. Every network gets its own pipelines. |
| **Device** | A single SNMP endpoint (IP/hostname + credential + network + device template). |
| **Device Template** | A named bundle of profiles plus matching rules used to auto-suggest the right template for discovered devices. |
| **Profile** | The actual OID definitions — scalar GETs, walks, and tables — plus normalizers that clean up the raw values. |

See **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** for each of these in depth.

### Deploy flow

Configuration changes are **staged, not live**. Editing devices or networks only updates LogstashUI's database; an "Undeployed changes" badge appears until you click **Deploy Changes**, review the per-pipeline diff, and confirm. Only then are pipelines generated and delivered. See **[Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md)**.

### Pipeline generator

For each network, LogstashUI generates:

- **Polling pipelines** — one per network + device template combination (`snmp-<network>-<template>-polling`), grouping devices that share a template and credential into SNMP input blocks
- **Trap pipeline** — `snmp-<network>-traps`, if traps are enabled
- **Discovery pipeline** — `snmp-<network>-discovery`, if discovery is enabled

See **[Pipeline Generation](/docs/docs/logstashui/SNMP/pipeline_generation.md)** for the full input → filter → output flow.

### Delivery: two deployment modes

- **Centralized Pipeline Management** — pipelines are written to Elasticsearch; any Logstash node with `xpack.management` configured and a matching `pipeline.id` pattern picks them up.
- **Logstash Agent** — pipelines are pushed to an enrolled [Logstash Agent](/docs/docs/logstashagent/index.md), which manages the Logstash instance directly.

Each network chooses its own mode, so you can mix both in one deployment.

### Data destinations

| Data stream | Contents |
|---|---|
| `metrics-snmp.polling-*` | Polled metrics, stored as a Time Series Data Stream (TSDS). See [TSDS Implementation](/docs/docs/logstashui/SNMP/tsds_implementation.md). |
| `logs-snmp.discovery-*` | Devices seen by the discovery pipeline. Feeds the Discovered Devices modal and the Overview dashboard. |
| `logs-snmp.traps-*` | Inbound SNMP traps. |

The data stream **namespace** is configurable per network — either a fixed value (e.g., `prod`) or derived from the device template name.

---

## Related Documentation

- **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** - Credentials, networks, devices, templates, and profiles
- **[Pipeline Generation](/docs/docs/logstashui/SNMP/pipeline_generation.md)** - How pipelines are built
- **[Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md)** - Deploy flow and deployment modes
- **[LogstashUI Architecture](/docs/docs/logstashui/architecture.md)** - Overall system architecture
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
