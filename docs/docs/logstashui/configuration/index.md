# Configuration

LogstashUI is configured through the `logstashui.yml` file in the project root. This section covers the main configuration options and setup guides.

---

## Configuration Files

### **[logstashui.yml](/docs/docs/logstashui/configuration/logstashui.yml.md)**

The main configuration file for LogstashUI. Controls authentication, simulation helpers, and legacy local agent settings.

**Key settings:**
- Authentication (`no_auth`)
- Simulation helpers (`simulation.mode` for compose/legacy URL defaults)
- Optional local `logstash_agent` block (secondary to enrolled simulate agents)

**📖 [View full logstashui.yml documentation →](/docs/docs/logstashui/configuration/logstashui.yml.md)**

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
