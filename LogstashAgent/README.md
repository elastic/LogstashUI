# LogstashAgent

> A control-plane agent for LogstashUI that fully manages the Logstash instance it runs alongside.
>
> Warning: **Beta Release** - This project is under active development. Features may change.

## Overview

LogstashAgent is the host-side runtime for LogstashUI-managed instances.

It enrolls with LogstashUI, persists local agent state, checks in for policy and configuration changes, and applies those changes directly to the local Logstash installation.

## Features

<details>
<summary><b>Enrollment + Reconciliation Loop</b> - Enroll with LogstashUI and continuously reconcile desired state to the local Logstash instance.</summary>

- Enrollment mode: `python src/logstashagent/main.py --enroll=<TOKEN> --logstash-ui-url=<URL>`
- Controller mode: `python src/logstashagent/main.py --run`
- Agent state includes enrollment identity, policy assignment, and revision tracking.

</details>

<details>
<summary><b>Pipeline Management API</b> - Create, update, delete, validate, and inspect Logstash pipelines.</summary>

- Endpoints include `/_logstash/pipeline`, `/_logstash/pipeline/{pipeline_id}`, `/_logstash/pipeline/{pipeline_id}/logs`, and `/_logstash/pipelines/status`.
- Config persistence is backed by `pipelines.yml`, `conf.d`, and metadata files.

</details>

<details>
<summary><b>Host Configuration Management</b> - Apply managed configuration to local Logstash runtime files and secure settings.</summary>

- Controller updates `logstash.yml`, `jvm.options`, `log4j2.properties`, and keystore entries.
- Supports reconciliation and service restart flows for managed updates.

</details>

<details>
<summary><b>Local State + Credential Protection</b> - Persist agent identity and encrypted sensitive fields under package-local data storage.</summary>

- State file: `src/logstashagent/data/state.json`
- Encryption key file: `src/logstashagent/data/.secret_key`
- Log file: `src/logstashagent/data/logs/logstashagent.log`

</details>

## Requirements

### Software

#### For Managed Agent mode
- [Python 3.12+](https://www.python.org/downloads/)
- [Logstash 8.x, 9.x](https://www.elastic.co/docs/reference/logstash/installing-logstash)

#### For Enrolled Controller mode (`--run`)
- [Python 3.12+](https://www.python.org/downloads/)
- Access to managed Logstash settings/log paths
- Network reachability to your LogstashUI instance

### For Local Development
- [Python 3.12+](https://www.python.org/downloads/)
- `uv` (recommended) or `pip`

## Quick Start - Agent Mode
> [!TIP]
> Use `--run` only after successful enrollment, because controller mode requires persisted enrollment state.

### Install
```bash
cd LogstashAgent
uv sync
```

### Configure
Copy and adjust the example config:
```bash
cp src/logstashagent/config/logstashagent.example.yml src/logstashagent/config/logstashagent.yml
```

### Run agent process
```bash
python src/logstashagent/main.py
```

By default this starts the agent service (including management API) on `0.0.0.0:9600` unless overridden in config.

---
## Enroll And Run Controller

### 1. Enroll the agent
```bash
python src/logstashagent/main.py --enroll=<BASE64_TOKEN> --logstash-ui-url=http://localhost:8080
```

### 2. Start controller mode
```bash
python src/logstashagent/main.py --run
```

### 3. Verify state files
- `src/logstashagent/data/state.json`
- `src/logstashagent/data/.secret_key`

## Updating

Pull latest source and resync dependencies:

```bash
git pull
uv sync
```

Then restart the running agent process.

## Limitations
- Controller behavior depends on available host service managers (`systemctl` or `service`) for restart operations.
- Host filesystem permissions must allow managed writes to Logstash settings and metadata paths.

## Roadmap
- Hardened host-mode lifecycle and service integration
- Expanded policy diff/apply visibility and diagnostics
- Additional keystore and secret-management workflows
- Broader automated test coverage around simulation and controller reconciliation paths

## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/elastic/LogstashUI/issues/new?template=issue.md).

## Contributing

Contributions are welcome.

Please open an issue to discuss large changes before submitting a pull request.

## License

Copyright 2024-2026 Elasticsearch and contributors.

Licensed under the Apache License, Version 2.0. See [LICENSE](../LICENSE.txt) for details.
