# logstashui.yml Configuration

The `logstashui.yml` file is the main configuration file for LogstashUI. It controls authentication, simulation behavior, and Logstash agent settings.

---

## File Location

The configuration file should be placed in the project root:

```
LogstashUI/
├── logstashui.yml
├── bin/
├── src/
└── ...
```

---

## Configuration Sections

### `no_auth`

Controls authentication for the LogstashUI application.

```yaml
no_auth:
  enabled: false  # true | false
```

**Options:**
- `enabled: false` (default) - Authentication is required. Users must log in.
- `enabled: true` - **Disables all authentication**. Anyone can access the application.

> **WARNING:** Enabling `no_auth` disables all authentication. Only use in sandbox/development environments. **Never enable in production.**

---

### `simulation`

Controls pipeline simulation behavior. See the [full simulation documentation](simulation.md) for detailed information.

```yaml
simulation:
  mode: embedded  # embedded | host
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

📖 **Learn more:** [Simulation Configuration](simulation.md)

---

### `logstash_agent`

Configures the Logstash agent used for pipeline simulation. This section is only relevant when using `simulation.mode: host`.

```yaml
logstash_agent:
  mode: simulation
  
  # Logstash installation paths
  logstash_binary: /usr/share/logstash/bin/logstash
  logstash_settings: /etc/logstash
  logstash_log_path: /var/log/logstash
```

**Settings:**

- **`mode`** - Agent operation mode
  - `simulation` - Agent manages Logstash for pipeline simulation

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

📖 **Learn more:** [Host Mode Setup Guide](host_mode.md)

---

## Complete Example

### Linux (Embedded Mode)

```yaml
# WARNING: Enabling no_auth disables all authentication.
# Only use in sandbox/development environments. Never enable in production.
no_auth:
  enabled: false  # true | false

simulation:
  mode: embedded  # embedded | host

  logstash_agent:
    mode: simulation
    
    logstash_binary: /usr/share/logstash/bin/logstash
    logstash_settings: /etc/logstash
    logstash_log_path: /var/log/logstash
```

### Linux (Host Mode)

```yaml
no_auth:
  enabled: false

simulation:
  mode: host  # Change to 'host' for better performance

  logstash_agent:
    mode: simulation
    
    # Linux paths (adjust if Logstash is installed in a custom location)
    logstash_binary: /usr/share/logstash/bin/logstash
    logstash_settings: /etc/logstash
    logstash_log_path: /var/log/logstash
```

### Windows (Host Mode)

```yaml
no_auth:
  enabled: false

simulation:
  mode: host

  logstash_agent:
    mode: simulation
    
    # Windows paths - adjust to match your Logstash installation
    logstash_binary: C:\logstash-9.3.1\logstash-9.3.1\bin\logstash.bat
    logstash_settings: C:\logstash-9.3.1\logstash-9.3.1\config
    logstash_log_path: C:\logstash-9.3.1\logstash-9.3.1\logs
```

---

## Related Documentation

- **[Simulation Configuration](simulation.md)** - Detailed simulation modes and settings
- **[Host Mode Setup](host_mode.md)** - Complete guide to setting up host mode for high-performance simulations
- **[Getting Started](../getting_started)** - Quick start guide for LogstashUI
