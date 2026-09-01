# Updating

LogstashUI will notify you when a new version is available via a banner in the navigation sidebar.

To update LogstashUI to the latest version:

> [!WARNING]
> `--update` switches the repository to the `main` branch (`git checkout main`) before pulling. If you are running from a feature branch or have local modifications, note that you will be moved off your branch.

## Linux

```bash
cd LogstashUI/bin
./start_logstashui.sh --update
```

## Windows

```cmd
cd LogstashUI\bin
start_logstashui.bat --update
```

## LogstashAgent pairing

When LogstashUI is updated, upgrade enrolled agents to the **preferred agent version** shown in the UI (banner / Settings). For **0.5.1**:

1. Install the matching LogstashAgent package on each host.
2. Restart the agent unit for that role (`logstash-agent`, `logstash-agent@N`, or `lsagent-simulate@N`).
3. **Production Packaged/Default agents do not need to re-enroll.**
4. Apply DB migrations (compose entrypoint runs them; bare metal: `python manage.py migrate`).

See [CHANGELOG 0.5.1](https://github.com/elastic/LogstashUI/blob/main/CHANGELOG.md) and [agent roles](/docs/docs/logstashagent/general/roles.md) for Packaged/Managed coexistence and VERSION notes.

### Smoke after upgrade (optional)

```bash
# From LogstashUI repo with sibling LogstashAgent
./bin/smoke_agent_modes.sh --offline
# or with compose: ./bin/smoke_agent_modes.sh --rebuild
```

---

## Related Documentation

- **[Building and Running](/docs/docs/logstashui/general/build.md)** - Build and deployment guides
- **[Configuration](/docs/docs/logstashui/configuration/index.md)** - Configure LogstashUI settings
- **[Agent roles, ports, coexistence, VERSION](/docs/docs/logstashagent/general/roles.md)** - Agent operator reference
- **[General Overview](/docs/docs/logstashui/general/index.md)** - Return to general guides index
