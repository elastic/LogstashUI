# SNMP Data Overview

In LogstashUI we aim to provide a stable and robust core experience.

We refer to the following elements as Core Network Vitals:

- CPU
- Memory
- Interfaces
- LLDP / CDP
- Interface errors / discards
- Interface throughput / utilization
- Uptime

These are the items that we prioritize above all others. Things like hardware components, routing protocols, and other values for the time being will be best effort.

You can add your own profiles to collect details like this.

Secondary vitals:

- Temperature
- Fans
- Power supply
- Link aggregation and port channel

## Interface Monitoring

We do not encourage alerting on a giant manually maintained list of "important interfaces", because in most environments that becomes very fragile and high maintenance.

Instead, we focus on the signals that actually reflect meaningful network impact:

1. Is the interface connected to another discoverable device?
2. Is the interface usually up?
3. Did the interface activity change in a meaningful way? (ML)

## Where the Data Lands

- **Polling data** is written to `metrics-snmp.polling-*` as a Time Series Data Stream (TSDS). See **[TSDS Implementation](/docs/docs/logstashui/SNMP/tsds_implementation.md)** for routing dimensions and query guidance.
- **Discovery data** is written to `logs-snmp.discovery-*`.
- **Trap data** is written to `logs-snmp.traps-*`.

Common identifying fields on every polled event:

- `event.category` — the data type. Table rows get the lowercased table name (`interface`, `arp`, ...), scalar polling events get `metrics`, discovery events get `discovery`, and trap events get `traps`.
- `observer.sys_descr` — the device's sysDescr value
- `host.name` — the friendly name you assigned to the device in LogstashUI
- `host.polled_address` — the exact address used to reach the device during polling

## Field Reference

For the complete list of field names, source MIBs, and OIDs (interfaces, system metrics, LLDP/CDP, hardware sensors, and more), see the **[SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md)**.

---

## Related Documentation

- **[SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md)** - Canonical field names, MIBs, and OIDs
- **[TSDS Implementation](/docs/docs/logstashui/SNMP/tsds_implementation.md)** - Time series storage and query performance
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
