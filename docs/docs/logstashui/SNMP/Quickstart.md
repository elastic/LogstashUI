# SNMP Quickstart Guide

The fastest path from an empty setup to SNMP metrics in Elasticsearch.

LogstashUI can deliver SNMP pipelines to Logstash in two ways. Pick one before you start:

- **Centralized Pipeline Management (CPM)** — LogstashUI writes pipelines to Elasticsearch, and your Logstash node picks them up via [centralized pipeline management](https://www.elastic.co/docs/reference/logstash/logstash-centralized-pipeline-management). Best when you already run Logstash and manage it yourself.
- **Logstash Agent** — LogstashUI pushes pipelines directly to a Logstash node managed by an enrolled [Logstash Agent](/docs/docs/logstashagent/index.md). Best when you want LogstashUI to fully manage the Logstash instance.

See [Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md) for a detailed comparison of the two modes.

---

## Option A: Centralized Pipeline Management

### Step 1: Add a Device

Click the **"Add Device"** button on the SNMP Devices page and fill out the form with your device information. You will be prompted to set up a credential, network, or connection if you haven't set those up yet. Make sure the network's deployment mode is **Centralized Pipeline Management**.

Required information:

- **Device Name**: A descriptive name for your device (e.g., "Core Switch 1")
- **IP Address/Hostname**: The IP address or hostname of the SNMP device
- **Credential**: SNMP credentials (v1, v2c, or v3) for authentication
- **Network**: The network this device belongs to
- **Device Template** (optional): A template that defines what metrics to collect. If you don't pick one, the Default template is applied.

### Step 2: Get Your Pipeline Name Pattern

Navigate back to the Devices page and click the text in the **Network** column to copy the network's pipeline name pattern (e.g., `snmp-production-*`).

> [!NOTE]
> LogstashUI generates one polling pipeline per network + device template combination, plus optional trap and discovery pipelines — all named `snmp-<network>-...`. The wildcard pattern covers all of them. See [Pipeline Generation](/docs/docs/logstashui/SNMP/pipeline_generation.md) for details.

### Step 3: Configure Logstash

In your `logstash.yml` file, add the pattern you copied in Step 2 to the **xpack.management.pipeline.id** list:

```yaml
xpack.management.enabled: true
xpack.management.elasticsearch.hosts: ["https://your-elasticsearch:9200"]
xpack.management.elasticsearch.username: "elastic"
xpack.management.elasticsearch.password: "your-password"
xpack.management.pipeline.id: ["snmp-production-*", "snmp-staging-*"]
```

Then restart Logstash:

```bash
sudo systemctl restart logstash
```

> [!TIP]
> You can add patterns for one or many networks to a single Logstash instance. A pipeline must be listed (or matched by a wildcard) in your config for its devices to be monitored.

### Step 4: Deploy Changes

Click the **"Deploy Changes"** button, review the diff, and confirm. LogstashUI writes the generated pipelines to Elasticsearch, and your Logstash node picks them up automatically.

---

## Option B: Logstash Agent

### Step 1: Enroll a Logstash Agent

Install and enroll a [Logstash Agent](/docs/docs/logstashagent/index.md) on the Logstash node that should run your SNMP pipelines. Once enrolled, the agent appears as a connection in LogstashUI.

### Step 2: Add a Device

Click **"Add Device"** on the SNMP Devices page, same as Option A — but when creating the network, choose **Logstash Agent** as the deployment mode and select your agent connection.

> [!NOTE]
> In agent mode the agent manages the node's host configuration for you — `logstash.yml`, `jvm.options`, and keystore entries included — so there is no manual node-side setup.

### Step 3: Deploy Changes

Click **"Deploy Changes"**, review the diff, and confirm. LogstashUI pushes the pipelines to the agent, which applies them to its Logstash instance — no `logstash.yml` editing required.

---

## Next Steps

1. **Monitor Data**: Open Kibana (or the SNMP Overview page) to view your metrics — polling data lands in `metrics-snmp.polling-*`
2. **Add More Devices**: Repeat the process, or let [Discovery](/docs/docs/logstashui/SNMP/discovery.md) find devices for you
3. **Explore Templates**: Assign [device templates and profiles](/docs/docs/logstashui/SNMP/configuration.md) to control what gets collected

---

## Related Documentation

- **[SNMP Configuration](/docs/docs/logstashui/SNMP/configuration.md)** - Credentials, networks, devices, templates, and profiles in depth
- **[Deploying Changes](/docs/docs/logstashui/SNMP/deploying_changes.md)** - The deploy flow and deployment mode differences
- **[Discovery](/docs/docs/logstashui/SNMP/discovery.md)** - Automatic device discovery
- **[SNMP Overview](/docs/docs/logstashui/SNMP/index.md)** - Return to SNMP documentation
