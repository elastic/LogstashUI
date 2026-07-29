# Simulate agents (formerly “Host Mode”)

> **Renamed concept:** What older docs called **host mode** is now an enrolled **simulate** LogstashAgent with isolated paths. You should not point simulation at your production Logstash under `/etc/logstash`.

## Why simulate agents?

| Feature | Embedded (Docker) | Simulate agent (enrolled) |
|---------|-------------------|---------------------------|
| **Reliability** | Weaker for large pipelines | Strong — native JVM/Logstash |
| **Setup** | Compose only | Install LogstashAgent + enroll |
| **Isolation** | Container | `/opt/LogstashAgent/simulate-N/` |
| **Multi-version** | Single image | Pin VERSION per policy / instance |
| **Coexist with prod agent** | N/A | Yes, on the same host |

## Prerequisites

- Linux host (systemd) for install templates
- Root for `logstash-agent install --enroll …`
- Logstash binary available either:
  - **SYSTEM** — package or tarball already on the host, or
  - **VERSION** — agent downloads from Elastic artifacts into `/opt/LogstashAgent/logstash-versions/`
- Reachable LogstashUI URL from the agent host

## Install a simulate agent

1. In LogstashUI **Agent Policies**, open **Simulate Policy** (or a clone).
2. Copy an enrollment token.
3. On the agent host:

```bash
sudo logstash-agent install \
  --enroll '<TOKEN>' \
  --logstash-ui-url 'https://your-logstashui.example'
```

4. Start the instance (N is assigned at enroll; see install output):

```bash
sudo systemctl enable --now lsagent-simulate@N
# Logstash unit is managed by the agent: ls-simulate@N
```

5. In the pipeline editor, select the target under **Sim target**.

## Paths and ports

For instance **N**:

| Item | Location / value |
|------|------------------|
| Settings | `/opt/LogstashAgent/simulate-N/settings` |
| Config | `/opt/LogstashAgent/simulate-N/config` |
| Logs | `/opt/LogstashAgent/simulate-N/logs` |
| Data | `/opt/LogstashAgent/simulate-N/data` |
| Env (incl. keystore pass) | `/opt/LogstashAgent/simulate-N/env` |
| Agent FastAPI | **9500 + N** |
| Logstash HTTP API | **9560 + N** |
| Agent unit | `lsagent-simulate@N` |
| Logstash unit | `ls-simulate@N` |

Embedded Docker remains **9500 / 9560** and does not use these paths.

## Upgrade from old “host mode”

1. Stop any local agent that was managing production `/etc/logstash` for UI sim only.
2. Enroll a **Simulate** policy agent as above.
3. Leave production agents on **Default** policies (no re-enroll required for those).
4. Prefer the editor Sim target list over `simulation.mode: host` in `logstashui.yml`.

## Legacy start script (`simulation.mode: host`)

`bin/start_logstashui.sh` / `.bat` still accept **`simulation.mode: host`** for a **local** agent:

- Starts native FastAPI agent on port **9501** (supervisor `Popen` of package Logstash)
- `bin/sync_config.py` writes `mode: embedded` + `simulation_mode: host` (not enrolled `mode: simulate`)
- Compose runs UI + nginx only; nginx proxies to `host.docker.internal:9501`

This path is **legacy**. It is not the same as `lsagent-simulate@N` / isolated `/opt/LogstashAgent/simulate-N/`. Use it only for quick local experiments; use enrolled Simulate agents for multi-instance or production-quality simulation.

## Related

- **[Simulation overview](/docs/docs/logstashui/configuration/simulation.md)**
- **[logstashui.yml](/docs/docs/logstashui/configuration/logstashui.yml.md)**
- **[LogstashAgent modes](/docs/docs/logstashagent/configuration/logstashagent.yml.md)**
