# Device Discovery

Discovery finds SNMP devices on your network ranges so you don't have to add every device by hand.

## How It Works

1. **Enable discovery on a network** — discovery is on by default for new networks, but it only runs once the network has a **discovery credential** assigned ([Networks configuration](/docs/docs/logstashui/SNMP/configuration.md#networks)).
2. **Deploy** — the [deploy flow](/docs/docs/logstashui/SNMP/deploying_changes.md) generates a discovery pipeline (`snmp-<network>-discovery`) alongside the network's polling pipelines.
3. **The pipeline scans the CIDR range** — every host address in the network range is probed with the discovery credential on a **5-minute interval**. Addresses that already exist as devices in LogstashUI are excluded from the scan.
4. **Responders are recorded** — each device that answers is queried for basic system identity (sysDescr, sysName, and related OIDs from the generic system profile) and written to `logs-snmp.discovery-*` with `event.category: discovery`.
5. **Review in the Discovered Devices modal** — on the Devices page, the **Discovered Devices** button shows devices seen in the **last 10 minutes** (aggregated by IP address), along with a **suggested device template**.

## Template Suggestion

Discovered devices are matched against every [device template's matching rules](/docs/docs/logstashui/SNMP/configuration.md#device-templates) — case-insensitive substrings compared to the device's sysDescr. Templates where **all** rules match rank first, followed by partial matches ranked by match percentage. The best match appears in the Suggested Template column, and clicking **+ Add** pre-fills the device modal with it.

> [!NOTE]
> Discovery never creates devices automatically. It surfaces candidates; you decide which ones become monitored devices.

## What Gets Detected — and What Doesn't

Discovery **will** find a device if all of these are true:

- Its address is inside the network's CIDR range
- It responds to SNMP using the network's **discovery credential** (matching version and community/v3 settings)
- It is reachable from the Logstash node running the discovery pipeline (routing, firewalls, and SNMP ACLs permitting)

Discovery **will not** find:

- Devices using a different community string or v3 user than the discovery credential — one credential per network's discovery scan
- Devices with SNMP disabled, or with agent ACLs that don't allow the Logstash node's address
- Devices blocked by firewalls between the Logstash node and the target (UDP/161)
- Devices outside the CIDR range, or in networks with no discovery credential assigned
- Non-SNMP devices — discovery is purely SNMP-based; there is no ping/ARP/port-scan fallback

Devices you've already added are deliberately skipped, so the discovery list only ever shows *new* candidates.

> [!TIP]
> A device that responds to discovery but has no matching template still yields data — assign it the Default template, or see [Device Support](/docs/docs/logstashui/SNMP/device_support.md) for how to get a proper profile built for it.

---

## Related Documentation

- **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** - Networks, credentials, and templates
- **[Pipeline Generation](/docs/docs/logstashui/SNMP/pipeline_generation.md)** - How the discovery pipeline is built
- **[Device Support](/docs/docs/logstashui/SNMP/device_support.md)** - When your device isn't recognized
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
