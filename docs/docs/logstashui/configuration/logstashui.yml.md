# logstashui.yml Configuration

The `logstashui.yml` file is the main configuration file for LogstashUI. It controls authentication, simulation behavior, and Logstash agent settings.

---

## File Location

The configuration file lives at `src/logstashui/logstashui.yml`:

```
LogstashUI/
├── bin/
├── src/
│   └── logstashui/
│       ├── logstashui.yml
│       └── logstashui.example.yml
└── ...
```

If the file does not exist, the startup script creates it from `logstashui.example.yml` in the same directory — as a **symlink** on Linux, and as a **copy** on Windows (symlinks require elevated privileges there). To customize settings on Linux, replace the symlink with a real copy of the example file and edit it; on Windows, just edit the copied file.

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

Helpers for pipeline simulation URL defaults and legacy local agents.  
**Preferred model:** enroll **Simulate** agents and pick them in the editor (**Sim target**).  
See [Simulation](/docs/docs/logstashui/configuration/simulation.md).

```yaml
simulation:
  mode: embedded  # embedded | host (legacy URL defaults)
```

**Options:**
- `embedded` - Docker-oriented agent URL defaults (agent **9500**, Logstash API **9560**)
- `host` - Legacy host-agent URL defaults; prefer an enrolled **simulate** agent instead

| Approach | Reliability | Notes |
|----------|-------------|--------|
| **Simulate agent (enrolled)** | High | Isolated `simulate-N` paths; multi-version |
| **Embedded (Docker)** | Lower for large pipelines | No enroll; pseudo-connection in picker |
| **`simulation.mode: host` (legacy)** | Variable | Superseded by simulate enrollment |

📖 **Learn more:** [Simulation](/docs/docs/logstashui/configuration/simulation.md) · [Simulate agents](/docs/docs/logstashui/configuration/host_mode.md)

---

### `logstash_agent`

Optional block for a **local** agent process started with LogstashUI tooling.  
Enrolled simulate agents receive paths and ports from **policy enrollment**, not only this file.

```yaml
logstash_agent:
  mode: embedded  # embedded | simulate | default (agent maps legacy simulation/*)

  # SYSTEM paths when not using isolated simulate-N layout
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

📖 **Learn more:** [Host Mode Setup Guide](/docs/docs/logstashui/configuration/host_mode.md)

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

- **[Simulation Configuration](/docs/docs/logstashui/configuration/simulation.md)** - Detailed simulation modes and settings
- **[Host Mode Setup](/docs/docs/logstashui/configuration/host_mode.md)** - Complete guide to setting up host mode for high-performance simulations
- **[Getting Started](/docs/docs/getting_started.md)** - Quick start guide for LogstashUI
