# logstashagent.yml

Configuration for LogstashAgent runtime. Installed agents also store enrollment state under the agent **state directory** (not only this file).

> Full operator reference: **[Agent roles, ports, coexistence, and VERSION](/docs/docs/logstashagent/general/roles.md)**

## Modes (roles)

```yaml
mode: packaged   # packaged | managed | simulate | embedded
# legacy alias still accepted:
# mode: default  → packaged
```

| Mode | Meaning |
|------|---------|
| **packaged** | Enrolled production agent (Packaged policy). Controller check-in; `systemctl` manages package `logstash`. Config: `/etc/logstash-agent/logstash-agent.yml`. |
| **managed** | Enrolled multi-instance agent **N** (Managed policy). Controller + FastAPI; manages `logstash-managed@N` under `/opt/logstash-agent/managed-N/`. |
| **simulate** | Enrolled simulation agent **N**. FastAPI + controller; manages `ls-simulate@N` with isolated paths. |
| **embedded** | Docker/local sim without enrollment. FastAPI + process supervisor. |
| **default** | Legacy alias of **packaged** (still accepted). |

### Legacy values

Still accepted and mapped at startup:

| Legacy | Maps to |
|--------|---------|
| `agent`, `host` | `packaged` |
| `default` | kept as `default` (treated like packaged controller) |
| `simulation` + `simulation_mode: embedded` | `embedded` |
| `simulation` + `simulation_mode: host` | `simulate` (prefer re-enroll under Simulate Policy) |

Startup logs include lines like:

```text
mode=packaged (legacy 'agent' mapped) [config]
```

## Paths (packaged / SYSTEM)

```yaml
mode: packaged
logstash_binary: /usr/share/logstash/bin/logstash
logstash_settings: /etc/logstash
logstash_log_path: /var/log/logstash
logstash_api_port: 9600   # package Logstash monitoring API
```

State: `/var/lib/logstash-agent/`. Unit: `logstash-agent`.

## Managed-specific (usually from enrollment)

```yaml
mode: managed
instance_id: 1
port: 9551                 # agent FastAPI = 9550 + N
logstash_api_port: 9701    # 9700 + N
logstash_settings: /opt/logstash-agent/managed-1/settings
logstash_log_path: /opt/logstash-agent/managed-1/logs
logstash_source: SYSTEM    # or VERSION
logstash_version: "9.4.3"  # when VERSION
logstash_download_dir: /opt/logstash-agent/logstash-versions
```

File location on disk (host coexistence):  
`/opt/logstash-agent/managed-1/logstash-agent.yml`  
(not under `/etc/logstash-agent/`).

Units: `logstash-agent@1`, `logstash-managed@1`.

## Simulate-specific (usually from enrollment)

```yaml
mode: simulate
instance_id: 1
port: 9501                 # agent FastAPI = 9500 + N
logstash_api_port: 9561    # 9560 + N
logstash_settings: /opt/logstash-agent/simulate-1/settings
logstash_log_path: /opt/logstash-agent/simulate-1/logs
logstash_source: SYSTEM    # or VERSION
logstash_version: "9.4.3"  # when VERSION
logstash_download_dir: /opt/logstash-agent/logstash-versions
```

File location: `/opt/logstash-agent/simulate-1/logstash-agent.yml`.  
Units: `lsagent-simulate@1`, `ls-simulate@1`.

## VERSION settings

```yaml
logstash_source: VERSION
logstash_version: "9.4.3"
logstash_download_dir: /opt/logstash-agent/logstash-versions
```

| Setting | Purpose |
|---------|---------|
| `logstash_source` | `SYSTEM` (host binary) or `VERSION` (download pin) |
| `logstash_version` | Elastic version string when source is VERSION |
| `logstash_download_dir` | Extract root (default `/opt/logstash-agent/logstash-versions`) |

Applied on agent check-in when the policy pin drifts (download → update instance `env` `LOGSTASH_BINARY` → restart Logstash unit). Host helpers:

```bash
logstash-agent list-versions
logstash-agent ensure-version 9.4.3
logstash-agent prune-versions --dry-run
```

See [VERSION binary lifecycle](/docs/docs/logstashagent/general/roles.md#version-binary-lifecycle).

## FastAPI (managed / simulate / embedded)

```yaml
host: 0.0.0.0
port: 9500   # embedded; simulate uses 9500+N; managed uses 9550+N; packaged uses 9550
```

Notable endpoints:

- `/_logstash/simulate`, slots, validate, logs (sim)
- `GET /_logstash/keystore` — current secrets (for compare)
- `POST /_logstash/keystore/sync` — write only if different; restart only then

## Install vs runtime

| Command | Purpose |
|---------|---------|
| `sudo logstash-agent install --enroll …` | Root: binary, units, enroll; materialize multi-instance tree / VERSION download |
| `logstash-agent --run` | Controller (packaged) or controller+FastAPI (managed/simulate) |
| `sudo logstash-agent configure` | Permissions/sudoers after late Logstash install (packaged agents) |
| `sudo logstash-agent setup-simulate` | Finish multi-instance materialize after non-root enroll |
| `logstash-agent list-instances` | Host install registry (all roles) |
| `logstash-agent list-versions` / `ensure-version` / `prune-versions` | VERSION cache lifecycle |

## Related

- **[Roles, ports, coexistence, VERSION](/docs/docs/logstashagent/general/roles.md)**
- **[Simulation](/docs/docs/logstashui/configuration/simulation.md)**
- **[Simulate agent setup](/docs/docs/logstashui/configuration/host_mode.md)**
