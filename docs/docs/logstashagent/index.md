# LogstashAgent

> A control-plane agent for LogstashUI that fully manages the Logstash instance it runs alongside.
>
> ⚠️ **Beta Release** - This project is under active development. Features may change.

## Overview

LogstashAgent is the host-side runtime for LogstashUI-managed instances.

It enrolls with LogstashUI, persists local agent state, checks in for policy and configuration changes, and applies those changes directly to the local Logstash installation.

---

### Enrollment + Reconciliation Loop
Enroll with LogstashUI and continuously reconcile desired state to the local Logstash instance.

- **Install and enroll**: `sudo ./logstash-agent/logstash-agent install --enroll <TOKEN> --logstash-ui-url <URL>`
- **Controller mode**: managed automatically by the `logstash-agent` systemd service after installation
- Agent state includes enrollment identity, policy assignment, and revision tracking

### Pipeline Management API
Create, update, delete, validate, and inspect Logstash pipelines.

- Endpoints: `/_logstash/pipeline`, `/_logstash/pipeline/{pipeline_id}`, `/_logstash/pipeline/{pipeline_id}/logs`, `/_logstash/pipelines/status`
- Config persistence backed by `pipelines.yml`, `conf.d`, and metadata files

### Host Configuration Management
Apply managed configuration to local Logstash runtime files and secure settings.

- Controller updates `logstash.yml`, `jvm.options`, `log4j2.properties`, and keystore entries
- Supports reconciliation and service restart flows for managed updates

### Local State + Credential Protection
Persist agent identity and encrypted sensitive fields under package-local data storage.

- State file: `src/logstashagent/data/state.json`
- Encryption key: `src/logstashagent/data/.secret_key`
- Log file: `src/logstashagent/data/logs/logstashagent.log`

---

## Requirements

### Software

**For production agent deployment:**
- Linux (x86-64) — the installer is Linux-only
- [Logstash 9.x](https://www.elastic.co/docs/reference/logstash/installing-logstash) — not required at install time, but the agent will not manage pipelines until Logstash is present and configured
- Root / sudo access for installation
- Network reachability to your LogstashUI instance

**For local development (from source):**
- [Python 3.12+](https://www.python.org/downloads/)
- `uv` (recommended) or `pip`
- See the **[Build Guide](/docs/docs/logstashagent/general/build.md)** for full details

---

## Quick Start - Install and Enroll

> [!TIP]
> Download the latest `logstash-agent-linux-amd64.tar.gz` from the [GitHub releases page](https://github.com/elastic/LogstashAgent/releases) and extract it before running the steps below.

### 1. Extract the bundle

```bash
tar -xzf logstash-agent-linux-amd64.tar.gz
```

This produces a `logstash-agent/` directory containing the `logstash-agent` executable and its bundled dependencies.

### 2. Install and enroll

Run the installer as root, passing the enrollment token generated from LogstashUI:

```bash
sudo ./logstash-agent/logstash-agent install \
  --enroll <BASE64_TOKEN> \
  --logstash-ui-url http://<logstashui-host>:8080 \
  --yes
```

The installer will:
- Copy the bundle to `/opt/logstash-agent/bin/`
- Create a symlink at `/usr/local/bin/logstash-agent` (or `/usr/bin/` on RHEL)
- Write a config file to `/etc/logstash-agent/logstash-agent.yml`
- Register and start the `logstash-agent` systemd service
- Enroll with LogstashUI

> [!NOTE]
> If Logstash is not yet installed on the host, the installer will warn you but continue. The agent will be set up and enrolled, but will not manage pipelines until Logstash is installed and the paths in `/etc/logstash-agent/logstash-agent.yml` are correct.

### 3. Enable and start the service

```bash
sudo systemctl enable logstash-agent
sudo systemctl start logstash-agent
```

### 4. Verify

```bash
sudo systemctl status logstash-agent
sudo journalctl -u logstash-agent -f
```

---

## Installing Logstash After the Agent

If you installed the agent on a host where Logstash was not yet present, the agent cannot complete its Logstash-specific setup at install time. You will see this message at the end of installation:

```
ACTION REQUIRED: Logstash was NOT installed at install time.

You MUST run the following after you install Logstash to
complete the setup, otherwise you may see issues:

  sudo logstash-agent configure
```

Once Logstash is installed, follow these steps to complete setup:

**1. Install Logstash** on the host.

**2. Update the agent config** if Logstash is in a non-standard location:

```bash
sudo nano /etc/logstash-agent/logstash-agent.yml
```

Update `logstash_binary`, `logstash_settings`, and `logstash_log_path` to match your installation.

**3. Run configure** (requires root):

```bash
sudo logstash-agent configure --yes
```

This applies:
- Ownership of `/etc/logstash`, `/var/log/logstash`, and `/usr/share/logstash/data` set to `logstash:logstash` so the agent can manage Logstash configuration
- `/etc/sudoers.d/logstash-agent` with the required passwordless sudo grants for service management
- The `logstash-agent` systemd service unit updated to run as the `logstash` user

`configure` is safe to re-run at any time — for example, if you change the Logstash installation path in `/etc/logstash-agent/logstash-agent.yml`, run `configure` again to re-apply the correct permissions before restarting the service.

> [!NOTE]
> Omit `--yes` to be prompted for confirmation before configure proceeds.

**4. Restart the service:**

```bash
sudo systemctl restart logstash-agent
```

> [!WARNING]
> Skipping `logstash-agent configure` after installing Logstash will cause the agent to fail to manage pipelines, restart Logstash, or apply policies correctly.

---

## Enrolled Agent State Files

After installation, agent identity and credentials are stored at:

- `/var/lib/logstash-agent/state.json`
- `/var/lib/logstash-agent/.secret_key`

---

## Documentation

- **[Configuration](/docs/docs/logstashagent/configuration/index.md)** - Configuration options and settings for LogstashAgent
- **[General](/docs/docs/logstashagent/general/index.md)** - Build and deployment guides

---

## Updating

Use the built-in upgrade command to download and apply a new release:

```bash
sudo logstash-agent upgrade --version <NEW_VERSION> --yes
```

The upgrade command will:
1. Download the new release from GitHub (cached to `/var/cache/logstash-agent/`)
2. Atomically replace the running binary
3. Restart the `logstash-agent` service
4. Automatically roll back to the previous version if the new binary fails to start

> [!NOTE]
> Omit `--yes` to be prompted for confirmation before the upgrade proceeds.

---

## Uninstalling

To remove LogstashAgent from a host:

```bash
sudo logstash-agent uninstall --yes
```

This removes:
- Binary: `/opt/logstash-agent/`
- Symlink: `/usr/local/bin/logstash-agent` (or `/usr/bin/logstash-agent` on RHEL)
- Config: `/etc/logstash-agent/`
- Systemd service: `/etc/systemd/system/logstash-agent.service`

Agent state, logs, and the upgrade download cache are **preserved by default** at `/var/lib/logstash-agent/`, `/var/log/logstash-agent/`, and `/var/cache/logstash-agent/`. To remove those as well, add the `--purge` flag:

```bash
sudo logstash-agent uninstall --purge --yes
```

> [!NOTE]
> Omit `--yes` to be prompted for confirmation before uninstallation proceeds.

---

## Limitations

- Controller behavior depends on available host service managers (`systemctl` or `service`) for restart operations
- Host filesystem permissions must allow managed writes to Logstash settings and metadata paths

---

## Roadmap

- Hardened host-mode lifecycle and service integration
- Expanded policy diff/apply visibility and diagnostics
- Additional keystore and secret-management workflows
- Broader automated test coverage around simulation and controller reconciliation paths

---

## Reporting Issues

Found a bug or have a feature request? [Open an issue](https://github.com/elastic/LogstashUI/issues/new?template=issue.md).

---

## Contributing

Contributions are welcome.

Please open an issue to discuss large changes before submitting a pull request.

---

## License

Copyright 2024–2026 Elasticsearch and contributors.

Licensed under the Elastic License 2.0 (ELv2). See [LICENSE](https://github.com/elastic/LogstashUI/blob/main/LICENSE.txt) for details.
