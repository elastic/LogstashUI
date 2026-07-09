# Deploying Changes

SNMP configuration in LogstashUI is **staged**: adding a device, editing a network, or changing a template updates LogstashUI's database, but nothing reaches Logstash until you deploy.

## The Undeployed Changes Badge

Any create, update, or delete across SNMP configuration (devices, networks, credentials, templates, profiles) marks the configuration as changed. An orange **"Undeployed changes"** badge with a pulsing dot appears next to the **Deploy Changes** button on every SNMP page and stays there until a deploy succeeds.

## The Deploy Flow

1. Click **Deploy Changes** (available on all SNMP pages).
2. LogstashUI regenerates every network's pipelines and diffs them against what is currently deployed.
3. The diff modal shows the result per pipeline: **created**, **modified** (with a config diff), and **deleted** pipelines (for example, after renaming a network or removing its last device).
4. Confirm to deploy. Each network's pipelines go to that network's configured connection.
5. On success, the badge clears.

Pipelines whose generated content is unchanged are skipped — deploying with no effective changes is a no-op.

## Deployment Modes

Each **network** chooses one of two deployment modes, so different networks can use different modes side by side.

### Centralized Pipeline Management (CPM)

Pipelines are written to **Elasticsearch** via the Logstash management API. Your Logstash node picks them up because its `logstash.yml` enables central management and lists a matching pipeline ID pattern:

```yaml
xpack.management.enabled: true
xpack.management.elasticsearch.hosts: ["https://your-elasticsearch:9200"]
xpack.management.pipeline.id: ["snmp-<your-network>-*"]
```

**CPM cannot manage the Logstash node itself** — LogstashUI has no access to the node's keystore, `logstash.yml`, or `jvm.options` in this mode. That's why the network's **credential mode** exists:

- **Manage Keystore Manually** (default) — credential values are kept out of the deployed pipeline; you add the SNMP credential entries to the [Logstash keystore](https://www.elastic.co/docs/reference/logstash/keystore) on each node yourself. LogstashUI supplies the exact commands to run — if you skip them, the pipelines will fail to start.
- **Plaintext Credentials** — credential values are embedded directly in the pipeline definition. Zero node-side setup, but anyone who can read pipelines in Elasticsearch can read the credentials. Not recommended outside labs.

**You manage the Logstash node**: installation, restarts, `logstash.yml`, `jvm.options`, and keystore entries are all your responsibility.

### Logstash Agent

Pipelines are pushed to an enrolled **[Logstash Agent](/docs/docs/logstashagent/index.md)** over its agent connection, and the agent applies them to the Logstash instance it manages. No `logstash.yml` editing, no Elasticsearch middleman for pipeline delivery.

Unlike CPM, the agent **fully manages the node's host configuration** — `logstash.yml`, `jvm.options`, `log4j2.properties`, and **keystore entries** are applied by the agent, so credentials reach the node without any manual node-side setup and the credential mode setting does not apply.

### Choosing Between Them

| | Centralized Pipeline Management | Logstash Agent |
|---|---|---|
| **Pipeline delivery** | Written to Elasticsearch; Logstash polls for them | Pushed directly to the agent |
| **Logstash node setup** | You configure `xpack.management` and restart Logstash once | Enroll an agent once; it manages the instance |
| **Instance management** | Yours (install, config, restarts) | Agent-managed |
| **Keystore & host config** (`logstash.yml`, `jvm.options`) | Manual — keystore entries yourself, or plaintext credential mode | Managed by the agent |
| **Best for** | Existing self-managed Logstash deployments | Nodes you want LogstashUI to fully control |

Keep LogstashUI and enrolled Logstash Agents on matching versions — see [Compatibility](/docs/docs/logstashui/compatibility.md).

---

## Related Documentation

- **[SNMP Quickstart](/docs/docs/logstashui/SNMP/Quickstart.md)** - Set up either mode end to end
- **[Pipeline Generation](/docs/docs/logstashui/SNMP/pipeline_generation.md)** - What actually gets deployed
- **[LogstashAgent Documentation](/docs/docs/logstashagent/index.md)** - Agent enrollment and management
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
