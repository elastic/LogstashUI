# Configuration

LogstashAgent configuration for simulation mode and host management.

---

## Configuration Files

### Controller / Host Mode — `/etc/logstash-agent/logstash-agent.yml`

When LogstashAgent is installed as a system service (via `logstash-agent install`), its configuration is written to:

```
/etc/logstash-agent/logstash-agent.yml
```

This file is managed by the installer. The key settings you may need to adjust are `logstash_binary`, `logstash_settings`, and `logstash_log_path` if Logstash is installed in a non-standard location. After editing, run `sudo logstash-agent configure` to re-apply permissions, then restart the service.

---

### **[logstashagent.yml](/docs/docs/logstashagent/configuration/logstashagent.yml.md)** — Simulation Mode Only

> **Note:** This file only applies when LogstashAgent is running in simulation mode. It is unused when running as an installed agent to control Logstash instances.

The configuration file for LogstashAgent when used for pipeline simulation.

**Key settings:**
- Agent mode (`simulation` vs `host`)
- Simulation mode (`embedded` vs `host`)
- Logstash installation paths

**📖 [View full logstashagent.yml documentation →](/docs/docs/logstashagent/configuration/logstashagent.yml.md)**

---

## Quick Links

- **[LogstashAgent Overview](/docs/docs/logstashagent/index.md)** - Feature overview and introduction
- **[LogstashUI Configuration](/docs/docs/logstashui/configuration/index.md)** - Main LogstashUI configuration
