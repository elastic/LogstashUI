# Pipeline Generation

LogstashUI provides a network monitoring interface so you can configure your environment like you would in a traditional monitoring solution. It takes that configuration, generates the Logstash pipelines that make the monitoring happen, and either pushes them to Elasticsearch centralized pipeline management for your Logstash node to pick up, or makes them available for your Logstash Agent to run. You never hand-write SNMP pipeline config.

## Pipeline Types

For each network, up to three kinds of pipelines are generated:

| Pipeline | Name | When it's generated |
|---|---|---|
| **Polling** | `snmp-<network>-<template>-polling` | One per network + device template combination that has devices. Devices with no template use the Default template. |
| **Traps** | `snmp-<network>-traps` | When the network has traps enabled and a trap credential. See [Trap Support](/docs/docs/logstashui/SNMP/traps.md). |
| **Discovery** | `snmp-<network>-discovery` | When the network has discovery enabled and a discovery credential. See [Discovery](/docs/docs/logstashui/SNMP/discovery.md). |

Network and template names are sanitized for use in pipeline IDs. Because all of a network's pipelines share the `snmp-<network>-` prefix, a single wildcard (`snmp-<network>-*`) covers them in `xpack.management.pipeline.id`.

> [!NOTE]
> Profile `walk` sections do not produce a separate pipeline — walks run inside the polling pipeline alongside GET and TABLE operations.

## Polling Pipelines: Input → Filter → Output

### Input

Devices in the network are grouped by **(device template, credential)**. Each group becomes an SNMP input block containing the group's device addresses, ports, timeouts/retries, the credential settings, and the merged OID list (GET, walk, and table OIDs) from every profile in the template. The network's **polling interval** controls how often each block polls.

How credentials reach the node depends on the network's deployment mode: in CPM mode, per the network's credential mode (manually maintained keystore entries, or plaintext values embedded in the pipeline); in agent mode, the Logstash Agent manages the node's keystore itself. See [Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md).

### Filters

Generated filters transform the raw SNMP responses:

1. **OID → field renames** — raw OID results are renamed to the field names defined in the profiles (see the [Field Reference](/docs/docs/logstashui/SNMP/schema.md))
2. **Table splits** — table results are split into one event per row (e.g., one event per interface), with fields prefixed by the table name
3. **Normalizers** — profile-defined post-processing: `multiply` (scaling), `ratio` (derived totals/percentages), and `translate` (integer enums → readable strings). GET-scope normalizers run before table splits; table-scope normalizers run on the per-row events after the split
4. **Device enrichment** — device metadata from LogstashUI (like the friendly `host.name`) is stamped onto every event
5. **Error cleanup** — SNMP error placeholders are stripped so failed OIDs don't pollute documents
6. **TSDS fields** — `tsds.category` (the data category, e.g. `interface`, `metrics`) and `tsds.index` (row disambiguator) are added for time series routing

### Output

Each pipeline writes to an Elasticsearch data stream:

| Pipeline | Data stream |
|---|---|
| Polling | `metrics-snmp.polling-<namespace>` (TSDS — see [TSDS Implementation](/docs/docs/logstashui/SNMP/tsds_implementation.md)) |
| Traps | `logs-snmp.traps-<namespace>` |
| Discovery | `logs-snmp.discovery-<namespace>` |

The **namespace** comes from the network configuration: a fixed value (default `default`), or — when *namespace from device template* is enabled — the normalized device template name, which keeps each hardware platform's data in its own backing streams.

## When Pipelines Are (Re)generated

Pipelines are only generated during the [deploy flow](/docs/docs/logstashui/SNMP/deploying_changes.md). The deploy diff compares freshly generated pipeline config against what is currently deployed, and only pipelines whose content actually changed are created, updated, or deleted. Renaming a network or template produces new pipeline names; the old pipelines are detected and marked for deletion in the same diff.

---

## Related Documentation

- **[Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md)** - Review and deploy generated pipelines
- **[TSDS Implementation](/docs/docs/logstashui/SNMP/tsds_implementation.md)** - Time series storage details
- **[SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md)** - Field names produced by the filters
- **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** - The configuration that drives generation
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
