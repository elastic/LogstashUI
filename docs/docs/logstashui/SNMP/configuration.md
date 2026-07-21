# SNMP Configuration

Everything you configure in the SNMP module, in the order you'll set it up: **credentials → networks → devices → device templates & profiles**.

All of these are staged changes — nothing reaches Logstash until you [deploy](/docs/docs/logstashui/SNMP/deploying_changes.md).

- [Credentials](#credentials)
- [Networks](#networks)
- [Devices](#devices)
- [Device Templates](#device-templates)
- [Profiles](#profiles)

---

## Credentials

*SNMP → Credentials → Add Credential*

Credentials define how LogstashUI (and the generated pipelines) authenticate to your devices. Each credential has a **name** and optional **description**, and is stored **encrypted** in the LogstashUI database.

### SNMP v1 / v2c

- **Community string** — the shared community string (commonly `public` for read-only access)

### SNMP v3

- **Security name** — the v3 username
- **Security level**:
  - `noAuthNoPriv` — no authentication, no encryption
  - `authNoPriv` — authentication only
  - `authPriv` — authentication and encryption
- **Auth protocol** (for `authNoPriv` / `authPriv`): MD5, SHA, SHA2, HMAC128-SHA224, HMAC192-SHA256, HMAC256-SHA384, HMAC384-SHA512
- **Privacy protocol** (for `authPriv`): DES, 3DES, AES, AES128, AES192, AES256, AES256with3DESKey
- **Auth / privacy passphrases** — stored encrypted

The Credentials table shows a **Devices** count so you can see which credentials are in use before editing or deleting them.

> [!TIP]
> You can create credentials inline from the device and network modals via the **+ Add...** entry at the top of each credential dropdown.

---

## Networks

*SNMP → Networks → Add Network*

A network is a monitoring zone. **Every network gets its own generated pipelines**, which is what lets you split monitoring across multiple Logstash instances.

| Setting | Description |
|---|---|
| **Name** | Unique friendly name. Used (sanitized) in pipeline names: `snmp-<network>-...` |
| **Network range** | CIDR notation, e.g. `192.168.1.0/24`. Used by [discovery](/docs/docs/logstashui/SNMP/discovery.md) to know what to scan. |
| **Deployment mode** | **Centralized Pipeline Management** (pipelines written to Elasticsearch) or **Logstash Agent** (pipelines pushed to an enrolled agent). See [Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md). |
| **Connection** | The Elasticsearch connection (CPM mode) or Logstash Agent connection (agent mode) this network deploys to. |
| **Credential mode** (CPM only) | **Manage Keystore Manually** (you add the credential entries to the Logstash keystore on the node yourself) or **Plaintext Credentials** (credentials embedded in the pipeline definition — convenient, but visible to anyone who can read pipelines in Elasticsearch). Not applicable in agent mode, where the agent manages the node's keystore and host configuration for you. |
| **Polling interval** | How often devices are polled, in seconds (default 30). |
| **Namespace** | Data stream namespace for this network's data (default `default`). Alternatively, enable **namespace from device template** to use the normalized template name as the namespace. |
| **Discovery credential** | The credential used to scan the network range for new devices. Required for discovery. |
| **Traps enabled** | Generates a trap pipeline for this network. A standard SNMP credential is assigned here as the trap credential. See [Trap Support](/docs/docs/logstashui/SNMP/traps.md). |

The Networks table shows a per-network device count, and clicking the network name in the Devices table copies the network's pipeline name pattern (`snmp-<network>-*`).

---

## Devices

*SNMP → Devices → Add Device*

A device is a single SNMP endpoint to poll.

| Setting | Description |
|---|---|
| **Name** | Unique friendly name. Appears on every polled event as `host.name`. |
| **IP address / Hostname** | At least one is required. The polled address appears on events as `host.polled_address`. |
| **Port** | SNMP port (default 161). |
| **Timeout / Retries** | Per-request timeout in milliseconds (default 1000) and retry count (default 2). |
| **Credential** | Which credential to authenticate with. |
| **Network** | Which network (and therefore which pipeline and deployment target) the device belongs to. |
| **Device Template** | What to collect from the device. If you leave it empty, the **Default** template is assigned automatically. |

Devices can be added two ways:

1. **Manually** — the Add Device button.
2. **From discovery** — the Discovered Devices modal lists devices found on your network ranges, with a suggested template pre-matched from the device's sysDescr. See [Discovery](/docs/docs/logstashui/SNMP/discovery.md).

---

## Device Templates

*SNMP → Device Templates*

A device template answers "what should we collect from this kind of device?" by bundling one or more profiles. Devices reference a single template rather than picking profiles individually, so similar devices stay consistent.

Each template has:

- **Name / description**
- **Vendor / Product / Model** — hierarchical categorization (e.g., Dell / iDRAC / Any)
- **Profiles** — the profiles applied to devices using this template
- **Matching rules** — a list of substrings matched (case-insensitively) against a device's sysDescr. Used to suggest templates for [discovered devices](/docs/docs/logstashui/SNMP/discovery.md).

### Official vs custom templates

**Official templates** ship with LogstashUI as JSON files and are synced into the database automatically. They display a star badge and **cannot be edited or deleted**. Official templates exist for popular platforms (Cisco IOS, Dell iDRAC, Brocade FC switches, HPE Nimble, Ubiquiti UniFi, and more).

**Custom templates** are yours — create them from scratch, or start by combining official profiles with your own.

> [!TIP]
> Can't find a template for your hardware? See [Device Support](/docs/docs/logstashui/SNMP/device_support.md) — you can generate one from an snmpwalk, or send us the walk and we'll consider adding official support.

---

## Profiles

*SNMP → Device Templates → Profiles tab*

A profile defines the actual SNMP data collection — which OIDs to query and what fields they become.

A profile contains:

- **GET** — scalar OIDs, mapped directly to field names (e.g., `observer.sys_descr` ← `1.3.6.1.2.1.1.1.0`)
- **WALK** — OID subtrees to walk
- **TABLE** — SNMP tables with per-column field mappings. Each table row becomes its own event (e.g., one event per interface), with fields prefixed by the table name (`interface.in_octets`, `interface.oper_status`, ...)
- **Normalizers** — post-processing applied to the collected values:
  - `multiply` — scale a numeric field by a constant (e.g., convert a 0–100 vendor CPU percentage to a 0–1 fraction)
  - `ratio` — derive totals and percentages from two fields (e.g., used + free → used percentage)
  - `translate` — map raw SNMP integers to readable strings (e.g., interface status `1` → `UP`)

Like templates, profiles come in **official** (JSON-synced, read-only) and **custom** flavors. Field names in official profiles follow the conventions in the [SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md) — reuse those field names in custom profiles so your data stays queryable alongside official data.

### Creating custom profiles

Three ways, from most to least manual:

1. **By hand** — Add Profile, then define GET/table OIDs and normalizers in the modal.
2. **From a walk** — run an SNMP Walk from the [Test SNMP modal](/docs/docs/logstashui/SNMP/testing.md) and use **Generate Template and Profiles** to have AI draft profiles from the walk output.
3. **Copy an official profile's approach** — official profile JSON makes a good reference for structure and naming.

---

## Related Documentation

- **[SNMP Quickstart](/docs/docs/logstashui/SNMP/Quickstart.md)** - End-to-end setup walkthrough
- **[Discovery](/docs/docs/logstashui/SNMP/discovery.md)** - Automatic device discovery
- **[Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md)** - Getting your configuration to Logstash
- **[Testing & Validation](/docs/docs/logstashui/SNMP/testing.md)** - Test profiles and walk devices
- **[SNMP Field Reference](/docs/docs/logstashui/SNMP/schema.md)** - Canonical field names and OIDs
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
