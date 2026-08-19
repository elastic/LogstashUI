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

### `paths`

Where LogstashUI stores sqlite, TLS material, secrets, and logs. **Outside the application tree.**

```yaml
paths:
  data: /var/lib/logstashui   # or relative to the git/project root, e.g. logstashui_data
  logs: /var/log/logstashui   # optional; default is <data>/logs
```

Environment variables **win** over this file:

| Variable | Purpose |
|----------|---------|
| `LOGSTASHUI_DATA_DIR` | Data root (db, `tls/`, `.secret_key`, `.django_secret_key`) |
| `LOGSTASHUI_LOGS_DIR` | Log directory (default `<data>/logs`) |

From a git checkout, `docker compose` bind-mounts `<project_root>/logstashui_data` → `/var/lib/logstashui`. Native default (no env) is `<project_root>/logstashui_data`.

`SNMP/data/` is shipped product content and is **not** this directory.

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

- **`mode`** - Local agent role for tooling (`embedded` | `simulate` | `default`).  
  Enrolled simulate agents get role/paths from **policy enrollment**. Legacy start scripts rewrite this to `embedded` + supervisor `simulation_mode: host`.

- **`logstash_binary`** - Path to the Logstash executable (SYSTEM package paths for local supervisor only)
  - Linux (default): `/usr/share/logstash/bin/logstash`
  - Windows example: `C:\logstash-9.3.1\logstash-9.3.1\bin\logstash.bat`

- **`logstash_settings`** / **`logstash_log_path`** - Package paths for the legacy local agent only  
  Enrolled simulate instances use `/opt/logstash-agent/simulate-N/` instead.

> **IMPORTANT:** Prefer **enrolled Simulate** agents. The legacy `simulation.mode: host` start path lets the local agent manage package Logstash via supervisor; do not point it at production pipelines.

📖 **Learn more:** [Simulate agents](/docs/docs/logstashui/configuration/host_mode.md)

---

## Complete Example

### Linux (Embedded Mode)

```yaml
# WARNING: Enabling no_auth disables all authentication.
# Only use in sandbox/development environments. Never enable in production.
no_auth:
  enabled: false  # true | false

simulation:
  mode: embedded  # embedded | host (host = legacy local start path)

  logstash_agent:
    mode: embedded

    logstash_binary: /usr/share/logstash/bin/logstash
    logstash_settings: /etc/logstash
    logstash_log_path: /var/log/logstash
```

### Linux (Legacy host start path)

```yaml
no_auth:
  enabled: false

simulation:
  # LEGACY: native agent on :9501 for start_logstashui.sh
  # Prefer enrolling a Simulate policy agent instead.
  mode: host

  logstash_agent:
    mode: embedded  # rewritten by sync_config to embedded + simulation_mode: host

    logstash_binary: /usr/share/logstash/bin/logstash
    logstash_settings: /etc/logstash
    logstash_log_path: /var/log/logstash
```

### Windows (Legacy host start path)

```yaml
no_auth:
  enabled: false

simulation:
  mode: host  # legacy local start path only

  logstash_agent:
    mode: embedded

    logstash_binary: C:\logstash-9.3.1\logstash-9.3.1\bin\logstash.bat
    logstash_settings: C:\logstash-9.3.1\logstash-9.3.1\config
    logstash_log_path: C:\logstash-9.3.1\logstash-9.3.1\logs
```

---

## Related Documentation

- **[Simulation Configuration](/docs/docs/logstashui/configuration/simulation.md)** - Simulation targets and settings
- **[Simulate agents (formerly host mode)](/docs/docs/logstashui/configuration/host_mode.md)** - Enrolled multi-instance sim
- **[Getting Started](/docs/docs/getting_started.md)** - Quick start guide for LogstashUI
