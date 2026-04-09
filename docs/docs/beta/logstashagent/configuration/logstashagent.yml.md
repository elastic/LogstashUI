---
layout: default
title: logstashagent.yml
description: Configuration reference for LogstashAgent
---

# logstashagent.yml Configuration

> **Note:** `logstashagent.yml` ONLY applies for simulation mode. It is unused when running this as an agent to control Logstash instances.

The `logstashagent.yml` file configures the LogstashAgent component, which is responsible for managing Logstash processes for pipeline simulation.

---

## File Location

The configuration file should be placed in the LogstashAgent directory:

```
LogstashAgent/
├── logstashagent.yml
├── src/
└── ...
```

---

## Configuration Sections

### `mode`

Determines if the agent is used for simulating in LogstashUI, or for controlling an actual Logstash host.

```yaml
mode: simulation  # simulation | host
```

**Options:**
- `simulation` - Agent manages Logstash for pipeline simulation in LogstashUI
- `host` - Agent controls an actual Logstash host instance

---

### `simulation_mode`

Controls how the simulation Logstash instance runs. Only applies if `mode` is set to `simulation`.

```yaml
simulation_mode: embedded  # embedded | host
```

**Options:**
- `embedded` - Runs Logstash in a local container (slower, easier setup)
- `host` - Runs Logstash natively on the host machine (faster, requires Logstash installation)

**Quick Comparison:**

| Feature | Embedded Mode | Host Mode |
|---------|---------------|-----------|
| **Performance** | Error prone with large pipelines | Highly reliable |
| **Setup** | Simple - no dependencies | Requires Logstash installation |
| **Best For** | Quick start, occasional simulations | Heavy simulation workloads |

---

### Logstash Paths

Configures the paths to the Logstash installation. These settings are used when `simulation_mode: host`.

```yaml
logstash_binary: /usr/share/logstash/bin/logstash
logstash_settings: /etc/logstash
logstash_log_path: /var/log/logstash
```

**Settings:**

- **`logstash_binary`** - Path to the Logstash executable
  - Linux (default): `/usr/share/logstash/bin/logstash`
  - Windows example: `C:\logstash-9.3.1\logstash-9.3.1\bin\logstash.bat`

- **`logstash_settings`** - Path to Logstash configuration directory
  - Linux (default): `/etc/logstash`
  - Windows example: `C:\logstash-9.3.1\logstash-9.3.1\config`

- **`logstash_log_path`** - Path to Logstash log directory
  - Linux (default): `/var/log/logstash`
  - Windows example: `C:\logstash-9.3.1\logstash-9.3.1\logs`

> **IMPORTANT:** When using host mode, Logstash is fully managed by LogstashAgent. Logstash should not be started manually, and your configuration files will be modified.

---

## Complete Examples

### Linux (Embedded Mode)

```yaml
mode: simulation
simulation_mode: embedded

logstash_binary: /usr/share/logstash/bin/logstash
logstash_settings: /etc/logstash
logstash_log_path: /var/log/logstash
```

### Linux (Host Mode)

```yaml
mode: simulation
simulation_mode: host

# Linux paths (adjust if Logstash is installed in a custom location)
logstash_binary: /usr/share/logstash/bin/logstash
logstash_settings: /etc/logstash
logstash_log_path: /var/log/logstash
```

### Windows (Host Mode)

```yaml
mode: simulation
simulation_mode: host

# Windows paths - adjust to match your Logstash installation
logstash_binary: C:\logstash-9.3.1\logstash-9.3.1\bin\logstash.bat
logstash_settings: C:\logstash-9.3.1\logstash-9.3.1\config
logstash_log_path: C:\logstash-9.3.1\logstash-9.3.1\logs
```

---

## Related Documentation

- **[LogstashUI Configuration](../../logstashui/configuration/logstashui.yml)** - Main LogstashUI configuration
- **[Host Mode Setup](../../logstashui/configuration/host_mode)** - Complete guide to setting up host mode
- **[Simulation Configuration](../../logstashui/configuration/simulation)** - Detailed simulation modes
