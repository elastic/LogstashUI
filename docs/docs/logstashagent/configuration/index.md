# Configuration

LogstashAgent configuration for **default** (production), **simulate**, and **embedded** roles.

---

## Configuration Files

### Installed agent — `/etc/logstash-agent/logstash-agent.yml`

When LogstashAgent is installed as a system service (`logstash-agent install`), configuration is written to:

```
/etc/logstash-agent/logstash-agent.yml
```

- **default** role: production paths + `mode: default`
- **simulate** role: `mode: simulate`, `instance_id`, ports, simulate-N paths

Adjust SYSTEM paths if Logstash is nonstandard; for default agents run `sudo logstash-agent configure` after installing Logstash late, then restart the service.

Simulate instances also use `/opt/logstash-agent/simulate-N/` and units `lsagent-simulate@N` / `ls-simulate@N`.

---

### **[logstashagent.yml](/docs/docs/logstashagent/configuration/logstashagent.yml.md)** — Modes and paths

**Key settings:**
- `mode`: `default` | `simulate` | `embedded` (legacy values mapped)
- Paths, API ports, VERSION download settings
- Keystore sync endpoints for simulation

**📖 [View full logstashagent.yml documentation →](/docs/docs/logstashagent/configuration/logstashagent.yml.md)**

---

## Quick Links

- **[LogstashAgent Overview](/docs/docs/logstashagent/index.md)** - Feature overview and introduction
- **[LogstashUI Configuration](/docs/docs/logstashui/configuration/index.md)** - Main LogstashUI configuration
