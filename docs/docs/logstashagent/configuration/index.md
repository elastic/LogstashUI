# Configuration

LogstashAgent configuration for **packaged**, **managed**, **simulate**, and **embedded** roles.

> **Roles, ports, coexistence, VERSION CLI:** see the full guide  
> **[Agent roles, ports, coexistence, and VERSION](/docs/docs/logstashagent/general/roles.md)**

---

## Configuration Files

### Packaged agent — `/etc/logstash-agent/logstash-agent.yml`

When you install with a **Packaged** policy token, configuration is written to:

```
/etc/logstash-agent/logstash-agent.yml
```

State lives under `/var/lib/logstash-agent/`. Unit: `logstash-agent` (Logstash: `logstash`).

### Multi-instance (Managed / Simulate) — under the instance tree

Managed and Simulate do **not** use the packaged `/etc` file for runtime config. Each instance has:

```
/opt/logstash-agent/managed-N/logstash-agent.yml
/opt/logstash-agent/simulate-N/logstash-agent.yml
```

with isolated state under `…/state/` and systemd `EnvironmentFile=…/agent.env` (`LOGSTASH_AGENT_STATE_DIR`, `LOGSTASH_AGENT_CONFIG`).

| Role | Paths | Units |
|------|-------|-------|
| **Managed N** | `/opt/logstash-agent/managed-N/` | `logstash-agent@N`, `logstash-managed@N` |
| **Simulate N** | `/opt/logstash-agent/simulate-N/` | `lsagent-simulate@N`, `ls-simulate@N` |

Packaged and multi-instance roles can **coexist** on one host. See the [roles guide](/docs/docs/logstashagent/general/roles.md#host-coexistence).

Adjust SYSTEM paths if Logstash is nonstandard. For packaged agents, run `sudo logstash-agent configure` after installing Logstash late, then restart `logstash-agent`.

---

### **[logstashagent.yml](/docs/docs/logstashagent/configuration/logstashagent.yml.md)** — Modes and paths

**Key settings:**
- `mode`: `packaged` | `managed` | `simulate` | `embedded` (legacy `default` / `agent` / `host` mapped)
- Paths, API ports, VERSION download settings
- Keystore sync endpoints for simulation

**📖 [View full logstashagent.yml documentation →](/docs/docs/logstashagent/configuration/logstashagent.yml.md)**

---

## Quick Links

- **[Roles, ports, coexistence, VERSION](/docs/docs/logstashagent/general/roles.md)** — operator reference
- **[LogstashAgent Overview](/docs/docs/logstashagent/index.md)** — feature overview
- **[Simulate agents](/docs/docs/logstashui/configuration/host_mode.md)** — sim enroll details
- **[LogstashUI Configuration](/docs/docs/logstashui/configuration/index.md)** — main LogstashUI configuration
