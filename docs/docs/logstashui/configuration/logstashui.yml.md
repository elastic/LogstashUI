# logstashui.yml (removed)

`logstashui.yml` is **no longer read**. Configure LogstashUI with environment variables.

See **[Environment configuration](/docs/docs/logstashui/configuration/environment.md)**.

| Old YAML | Replacement |
|---|---|
| `no_auth.enabled` | `LOGSTASHUI_NO_AUTH` |
| `paths.data` / `paths.logs` | `LOGSTASHUI_DATA_DIR` / `LOGSTASHUI_LOGS_DIR` |
| `agent.ui_url` | `LOGSTASHUI_AGENT_UI_URL` (DB Settings still wins) |
| `agent.include_ca_fingerprint` | `LOGSTASHUI_INCLUDE_CA_FINGERPRINT` |
| `simulation.mode` | Enrolled **Simulate** agents + `LOGSTASH_AGENT_URL` for the compose embedded agent |
| `simulation.logstash_agent.*` | `bin/start_logstashui.sh --legacy-host-agent` only |

The sample env file is `LogstashUI/packaging/logstashui.default` in the wheel (source: `src/logstashui/LogstashUI/packaging/logstashui.default`).
