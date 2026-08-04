# Simulation

LogstashUI runs pipeline simulation against a real Logstash process managed by **LogstashAgent**.

## Agent roles (recommended model)

LogstashAgent (and LogstashUI policies) use three roles:

| Role | Enrollment | Purpose |
|------|------------|---------|
| **default** | Yes | Production control plane for a real Logstash node |
| **simulate** | Yes | Dedicated simulation instance(s), isolated paths and ports |
| **embedded** | No (Docker pseudo-connection) | Local container agent for quick-start sim |

### Simulate agents (preferred for serious work)

1. In LogstashUI, open the system **Simulate Policy** (or a **clone** with a pinned Logstash version).
2. Create an enrollment token and install the agent as root:

```bash
sudo logstash-agent install \
  --enroll <TOKEN> \
  --logstash-ui-url https://logstashui.example.com
```

3. Enrollment allocates instance **N** and returns:
   - Paths: `/opt/logstash-agent/simulate-N/{settings,config,logs,data}`
   - Agent API port: **9500 + N**
   - Logstash API port: **9560 + N**
   - Units: `lsagent-simulate@N`, `ls-simulate@N`

4. Start:

```bash
sudo systemctl start lsagent-simulate@N
```

5. In the pipeline editor, use the **Sim target** dropdown (shows `simulate-N · Logstash <version>`).

You can run **default** and **simulate** agents on the same host; simulate never uses package `/etc/logstash` as its data root.

#### Multi-version testing

Clone the Simulate Policy, set `logstash_source=VERSION` and a version (e.g. `9.4.3`). The agent downloads that release into `/opt/logstash-agent/logstash-versions/` when materializing. Pick the instance in the editor to compare pipeline behavior across releases.

#### Keystore variables

If the pipeline contains `${…}` references **and** is associated with a policy (`ls_id`):

1. UI loads that policy’s user keystore entries.
2. Compares them to the simulate agent’s current keystore.
3. Syncs and restarts Logstash **only if they differ**.

Without a policy association, secrets are not uploaded.

### Embedded (Docker quick start)

Embedded mode keeps a local containerized agent (compose profile). LogstashUI ensures an **Embedded Policy** pseudo-connection so the Sim target list includes `embedded · docker` without enrollment.

- Agent API: **9500**
- Logstash API: **9560**

Good for demos; less reliable for large pipelines than enrolled simulate agents.

### Default agents

Default agents manage production Logstash. They are not selected as Sim targets. Upgrade existing production agents without re-enrolling (see CHANGELOG upgrade notes).

---

# Runtime Settings (`logstashui.yml`)

```yaml
simulation:
  # Legacy / compose helper — secondary to enrolled simulate agents
  # embedded: prefer Docker agent URL defaults
  # host: legacy local-agent URL defaults (prefer enrolled simulate instead)
  mode: embedded  # embedded | host

  # Optional: config passed to a co-started local agent (legacy host tooling)
  logstash_agent:
    mode: embedded  # or simulate / default when using a local agent process
    logstash_binary: /usr/share/logstash/bin/logstash
    logstash_settings: /etc/logstash
    logstash_log_path: /var/log/logstash
```

> **Note:** Prefer **enrolled simulate agents** over `simulation.mode: host`. Host mode remains for compatibility with older start scripts.

---

## Related Documentation

- **[Simulate agents (formerly host mode)](/docs/docs/logstashui/configuration/host_mode.md)** - Setup notes for dedicated sim Logstash
- **[logstashui.yml](/docs/docs/logstashui/configuration/logstashui.yml.md)** - Full configuration reference
- **[LogstashAgent configuration](/docs/docs/logstashagent/configuration/logstashagent.yml.md)** - Agent roles and paths
- **[Configuration Overview](/docs/docs/logstashui/configuration/index.md)** - Return to configuration index
