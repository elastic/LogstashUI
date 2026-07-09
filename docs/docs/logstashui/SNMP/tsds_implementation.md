# TSDS Implementation

## Overview

SNMP polling data is stored in a Time Series Data Stream (TSDS) index under `metrics-snmp.polling-*`. LogstashUI ships a custom index template (`snmp_template.json`) that explicitly enables TSDS mode (`index.mode: time_series`) and defines the routing path. The lookback and lookahead time window values are left at their Elasticsearch defaults (2-hour lookback, 30-minute lookahead).

## How TSDS Differs From a Normal Index

TSDS is purpose-built for time series metrics and behaves differently from a regular data stream in a few important ways.

### Rollover and Backing Indices

With a normal data stream, a rollover creates a new backing index and the old one is sealed. You can safely delete it once ILM transitions it out.

**With TSDS, this is not the case.** Each backing index has an explicit accepted time range. Data with timestamps that fall inside that window will always be routed to the correct backing index, even after a rollover has occurred. The default lookback window is **2 hours**, meaning that after a rollover, the previous backing index can still receive writes for up to 2 hours after its nominal end time.

**Do not delete a backing index immediately after a rollover.** The previous index's time window may still be open and Logstash may still be writing to it.

### ILM Transition Timing

Because of the 2-hour write window, ILM phase transitions that move an index out of the hot tier (or that delete it) must be scheduled with this in mind. If you trigger a delete or frozen transition within the 2-hour window, you risk losing in-flight data.

**Rule of thumb:** ILM transitions on TSDS backing indices should be set to greater than 2 hours from rollover time to avoid write conflicts.

---

## Routing Fields

The `snmp_template.json` defines `routing_path` explicitly as two fields:

```json
"routing_path": [
  "host.polled_address",
  "tsds.category"
]
```

Both fields are mapped as `time_series_dimension: true`. Elasticsearch uses these two values together as the composite key that determines which shard a document belongs to and which internal time series it is part of.

| Field | Description |
|---|---|
| `host.polled_address` | The IP address or hostname used to poll the device. Identifies which device the data came from. |
| `tsds.category` | The data category for this event (e.g., `interface`, `metrics`, `system`). Identifies what kind of data the event contains. |

Note that `tsds.index` is also mapped as a dimension (used to disambiguate multiple rows from the same poll, such as one row per interface), but it is **not** part of the routing path.

---

## Query Performance

TSDS indices are stored in a columnar format optimized for time range and dimension queries. Broad queries that touch many series can be expensive.

### Filtering by Device

When you need to scope a query to a specific device, filter on **`host.polled_address`**. This is one of the two routing dimensions and will be the most efficient way to narrow down to a single device.

```esql
FROM metrics-snmp.polling-*
| WHERE host.polled_address == "10.0.1.5"
```

### Filtering by Data Category

Each event has a category exposed in two places:

- **`event.category`** — the Elastic Common Schema field. This is not a TSDS dimension and is not optimized for routing.
- **`tsds.category`** — set by the pipeline to the specific data type (e.g., `interface`, `metrics`, `system`). This is a TSDS dimension and should be preferred for category filtering.

If you are experiencing slow queries when filtering on data type, use **`tsds.category`** instead of `event.category`:

```esql
FROM metrics-snmp.polling-*
| WHERE tsds.category == "interface"
```

Combining both routing dimensions gives the best query performance:

```esql
FROM metrics-snmp.polling-*
| WHERE host.polled_address == "10.0.1.5" AND tsds.category == "interface"
| SORT @timestamp DESC
```
