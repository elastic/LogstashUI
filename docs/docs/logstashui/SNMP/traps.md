# Trap Support

Polling asks devices for data on a schedule; **traps** are the reverse — devices push notifications (link down, PSU failure, config change...) the moment they happen. LogstashUI can generate a trap listener pipeline per network.

## Enabling Traps

1. Edit the network and enable **Traps** ([Networks configuration](/docs/docs/logstashui/SNMP/configuration.md#networks)).
2. Assign the network's **trap credential** — the credential devices use when sending traps (community string for v1/v2c, or the v3 user/security settings).
3. [Deploy Changes](/docs/docs/logstashui/SNMP/deploying_changes.md). A `snmp-<network>-traps` pipeline is generated alongside the network's polling pipelines.

## How the Trap Pipeline Works

The generated pipeline runs Logstash's `snmptrap` input:

- Listens on **all interfaces, UDP port 1662** on the Logstash node running the pipeline
- Accepts the SNMP version of the trap credential (v1, v2c, or v3 with the credential's auth/priv settings)
- Tags every event with `event.category: traps`
- Writes to the `logs-snmp.traps-<namespace>` data stream, using the network's namespace

> [!IMPORTANT]
> The listener uses port **1662**, not the standard trap port 162 (which requires root privileges to bind). Point your devices' trap destination at the Logstash node on port 1662, or redirect 162 → 1662 on the node, e.g.:
>
> ```bash
> sudo iptables -t nat -A PREROUTING -p udp --dport 162 -j REDIRECT --to-port 1662
> ```

Trap OIDs are kept in dotted-string form on the event, so specific trap types can be identified and dashboarded by OID.

## Current Limitations

> [!NOTE]
> Trap support is newer than polling and intentionally minimal today:
>
> - One trap credential per network — devices sending with other credentials are not accepted
> - Traps are ingested with basic normalization only; there is no per-trap-OID enrichment or translation layer yet
> - If multiple Logstash nodes run the same network's pipelines, each runs its own listener — point each device at one of them

---

## Related Documentation

- **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** - Network settings including the traps toggle
- **[Pipeline Generation](/docs/docs/logstashui/SNMP/pipeline_generation.md)** - How trap pipelines fit the bigger picture
- **[Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md)** - Getting the trap pipeline onto a node
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
