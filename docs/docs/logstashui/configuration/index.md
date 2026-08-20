# Configuration

LogstashUI is configured with **environment variables** (shell, systemd `/etc/default/logstashui`, Docker, or a Kubernetes ConfigMap). There is no required YAML file.

---

## Configuration

### **[Environment variables](/docs/docs/logstashui/configuration/environment.md)**

Data dir, TLS, bind address, `LOGSTASHUI_NO_AUTH`, agent URL, systemd, and Kubernetes.

**📖 [View environment configuration →](/docs/docs/logstashui/configuration/environment.md)**

`logstashui.yml` is [removed](/docs/docs/logstashui/configuration/logstashui.yml.md).

---

## Simulation Configuration

### **[Simulation](/docs/docs/logstashui/configuration/simulation.md)**

Pipeline simulation uses **LogstashAgent** targets:

- **Simulate agents** (enrolled) — isolated instances, multi-version capable (recommended)
- **Embedded** — Docker agent for quick start
- **Default agents** — production only (not sim targets)

**📖 [View simulation guide →](/docs/docs/logstashui/configuration/simulation.md)**

---

### **[Simulate agents (formerly host mode)](/docs/docs/logstashui/configuration/host_mode.md)**

Enroll and run dedicated simulate instances (`lsagent-simulate@N` / `ls-simulate@N`).

**Covers:**
- Prerequisites
- Install + enroll against Simulate Policy
- Ports, paths, multi-version notes
- Upgrade from old host mode

**📖 [View simulate agent setup →](/docs/docs/logstashui/configuration/host_mode.md)**

---

### **[Agent roles, ports, coexistence, VERSION](/docs/docs/logstashagent/general/roles.md)**

Operator reference for all agent roles on a host:

- Packaged / Managed / Simulate / Embedded
- Port map, path layout, install registry
- Host coexistence and day-2 commands
- VERSION download CLI

**📖 [View roles guide →](/docs/docs/logstashagent/general/roles.md)**

---

## Quick Links

- **[Getting Started](/docs/docs/getting_started.md)** - Initial setup and first steps
- **[LogstashUI Overview](/docs/docs/logstashui/index.md)** - Feature overview and introduction
