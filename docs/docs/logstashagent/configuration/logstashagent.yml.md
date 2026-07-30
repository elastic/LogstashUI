# logstashagent.yml

Configuration for LogstashAgent runtime. Installed agents also store enrollment state under the agent state directory (not only this file).

## Modes (roles)

```yaml
mode: default   # default | simulate | embedded
```

| Mode | Meaning |
|------|---------|
| **default** | Enrolled production agent. Controller check-in; `systemctl` manages package `logstash`. No sim FastAPI by default. |
| **simulate** | Enrolled simulation agent instance **N**. FastAPI + controller; manages `ls-simulate@N` with isolated paths. |
| **embedded** | Docker/local sim without enrollment. FastAPI + process supervisor. |

### Legacy values

Still accepted and mapped at startup:

| Legacy | Maps to |
|--------|---------|
| `agent`, `host` | `default` |
| `simulation` + `simulation_mode: embedded` | `embedded` |
| `simulation` + `simulation_mode: host` | `simulate` (prefer re-enroll under Simulate Policy) |

Startup logs include lines like:

```text
mode=default (legacy 'agent' mapped) [config]
```

## Paths (default / SYSTEM)

```yaml
logstash_binary: /usr/share/logstash/bin/logstash
logstash_settings: /etc/logstash
logstash_log_path: /var/log/logstash
logstash_api_port: 9600   # package Logstash monitoring API
```

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

## FastAPI (simulate / embedded)

```yaml
host: 0.0.0.0
port: 9500   # embedded; simulate uses 9500+N from policy
```

Notable endpoints:

- `/_logstash/simulate`, slots, validate, logs
- `GET /_logstash/keystore` — current secrets (for compare)
- `POST /_logstash/keystore/sync` — write only if different; restart only then

## Install vs runtime

| Command | Purpose |
|---------|---------|
| `sudo logstash-agent install --enroll …` | Root: binary, units, enroll, materialize simulate tree / VERSION download |
| `logstash-agent --run` | Controller (default) or controller+FastAPI (simulate) |
| `sudo logstash-agent configure` | Permissions/sudoers after late Logstash install (default agents) |

## Related

- **[Simulation](/docs/docs/logstashui/configuration/simulation.md)**
- **[Simulate agent setup](/docs/docs/logstashui/configuration/host_mode.md)**
