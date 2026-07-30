# Agent roles, ports, coexistence, and VERSION

LogstashAgent and LogstashUI use **policy types** and matching **agent modes** so one Linux host can run production Logstash and one or more isolated multi-instance agents without sharing state or config.

> **Paired releases:** Prefer matching LogstashUI and LogstashAgent minor versions (see [Compatibility](/docs/docs/logstashui/compatibility.md)).

---

## Roles at a glance

| Policy type (UI) | Agent `mode` | What it manages | Typical unit(s) |
|------------------|--------------|-----------------|-----------------|
| **PACKAGED** | `packaged` (legacy: `default`) | Distro / package Logstash | `logstash-agent` + `logstash` |
| **MANAGED** | `managed` | Agent-owned Logstash tree **N** | `logstash-agent@N` + `logstash-managed@N` |
| **SIMULATE** | `simulate` | Isolated sim tree **N** | `lsagent-simulate@N` + `ls-simulate@N` |
| **EMBEDDED** | `embedded` | Docker/local sim (no enroll) | Compose / process supervisor |
| **DEFAULT** | — | Legacy alias of **PACKAGED** | same as Packaged |

### Policy types (LogstashUI)

| Type | System seed name | Enroll? | Clone behavior |
|------|------------------|---------|----------------|
| **PACKAGED** | Packaged Policy | Yes | Clone → **MANAGED** (managed path scheme) |
| **MANAGED** | Managed Policy | Yes | Clone stays **MANAGED** |
| **SIMULATE** | Simulate Policy | Yes | Clone stays **SIMULATE** |
| **EMBEDDED** | Embedded Policy | **No** (Docker/auto) | Cannot clone |

---

## Ports

| Role | Agent API (HTTPS) | Logstash monitoring API |
|------|-------------------|-------------------------|
| **Packaged** | not used by controller | **9600** (package default) |
| **Managed N** | **9600 + N** | **9700 + N** |
| **Simulate N** | **9500 + N** | **9560 + N** |
| **Embedded** | **9500** | **9560** |

`N` is a **1-based** instance id assigned at enroll (globally free id for that policy type on the UI). Connection names look like `host-managed-1` or `host-simulate-2`.

---

## Paths and state (host layout)

### Packaged

| Item | Path |
|------|------|
| Binary | `/opt/logstash-agent/bin/logstash-agent` |
| Symlink | `/usr/local/bin/logstash-agent` (or `/usr/bin` on some RHEL) |
| Config | `/etc/logstash-agent/logstash-agent.yml` |
| State | `/var/lib/logstash-agent/` (`state.json`, TLS, registry) |
| Logs | `/var/log/logstash-agent/` |
| Cache | `/var/cache/logstash-agent/` |
| Logstash settings (SYSTEM) | `/etc/logstash/`, logs `/var/log/logstash` |

### Managed instance **N**

| Item | Path |
|------|------|
| Tree root | `/opt/logstash-agent/managed-N/` |
| Settings / config / logs / data | `…/settings`, `…/config`, `…/logs`, `…/data` |
| Logstash env (`LOGSTASH_BINARY`, keystore pass) | `…/env` |
| Agent env (systemd) | `…/agent.env` |
| Agent config | `…/logstash-agent.yml` |
| Agent state | `…/state/` (**not** `/var/lib/logstash-agent`) |

### Simulate instance **N**

Same shape under `/opt/logstash-agent/simulate-N/` (includes sim harness confs under settings).

### Shared on the host

| Item | Path |
|------|------|
| Shared agent binary | `/opt/logstash-agent/bin/` |
| `logstash-agent-ctl` | `/opt/logstash-agent/bin/logstash-agent-ctl` |
| VERSION download cache | `/opt/logstash-agent/logstash-versions/` |
| Install registry | `/var/lib/logstash-agent/install-registry.json` |
| Multi-instance unit templates | `/etc/systemd/system/logstash-agent@.service`, `logstash-managed@.service`, `lsagent-simulate@.service`, `ls-simulate@.service` |

---

## Host coexistence

**Packaged + Managed + Simulate can run on the same machine.**

### Isolation rules

1. **State** — Each multi-instance unit sets `LOGSTASH_AGENT_STATE_DIR` in `agent.env`. Packaged uses `/var/lib/logstash-agent`. Agent ids and API keys are **not** shared.
2. **Config** — Multi-instance writes `logstash-agent.yml` under the instance tree. Packaged keeps `/etc/logstash-agent/logstash-agent.yml`. Install does **not** overwrite packaged config when adding Managed/Simulate.
3. **Units** — Distinct systemd units per role. Stopping `logstash-agent` does **not** stop `logstash-agent@N` or `lsagent-simulate@N`.
4. **Distro Logstash** — Packaged install **enables** the `logstash` unit but does **not** start/restart it at install time (live-traffic safety). Multi-instance Logstash units are enable-only until the agent restarts them after apply.
5. **Install order** — Packaged install also ships multi-instance templates so a later Managed/Simulate enroll does not require reinstalling the binary. Multi-instance install leaves an existing packaged service alone.

### Day-2 map

```bash
# What is on this host?
logstash-agent list-instances

# Packaged only
sudo systemctl status logstash-agent
sudo journalctl -u logstash-agent -f

# Managed instance N only
sudo systemctl status logstash-agent@N
sudo systemctl status logstash-managed@N
# or: sudo logstash-agent-ctl status logstash-agent@N

# Simulate instance N only
sudo systemctl status lsagent-simulate@N
sudo systemctl status ls-simulate@N
```

### Uninstall (registry-aware)

```bash
# One multi-instance role only (package binary stays)
sudo logstash-agent uninstall --instance managed-1
sudo logstash-agent uninstall --instance simulate-2 --purge   # also delete tree

# Full package uninstall (stops multi units; --purge removes trees + state)
sudo logstash-agent uninstall
sudo logstash-agent uninstall --purge
```

---

## VERSION binary lifecycle

Policies can set **Logstash binary source**:

| Source | Meaning |
|--------|---------|
| **SYSTEM** | Use host binary path (package or custom `binary_path`) |
| **VERSION** | Download Elastic distribution `logstash_version` into `logstash_download_dir` |

### Apply flow (Managed / Simulate)

1. Save the policy in LogstashUI (Source = VERSION, pin e.g. `9.4.3`).
2. **No separate Deploy is required for binary-only changes** — the next agent check-in detects runtime drift.
3. Agent downloads (if needed) into `/opt/logstash-agent/logstash-versions/<version>/`.
4. Writes `LOGSTASH_BINARY=` into the instance `env` file.
5. Restarts the Logstash unit when the binary path or pin changes.
6. Reports resolved version on check-in (`status_blob.logstash_version_resolved`).

Enroll / install with VERSION also pre-downloads during materialize when possible.

### Host CLI

```bash
# Cache inventory
logstash-agent list-versions
logstash-agent list-versions --json
logstash-agent list-versions --download-dir /opt/logstash-agent/logstash-versions

# Pre-download or refresh a pin
logstash-agent ensure-version 9.4.3
logstash-agent ensure-version 9.4.3 --force

# Remove unused trees (always keeps pins in use by state/registry/env)
logstash-agent prune-versions --dry-run
logstash-agent prune-versions --yes
logstash-agent prune-versions --keep 9.4.3 --yes
```

### Notes

- VERSION is intended for **Simulate** and **Managed** multi-instance roles. Packaged production still typically uses distro SYSTEM Logstash.
- Enroll “Install Logstash” package checkbox is hidden for VERSION (agent download, not OS package).
- Download root defaults to `/opt/logstash-agent/logstash-versions` (legacy `/opt/LogstashAgent/...` is rewritten).

---

## Install and enroll by role

### Packaged (production)

1. LogstashUI → Agent Policies → **Packaged Policy** (or a user Packaged policy) → enrollment token.
2. On the host:

```bash
sudo logstash-agent install \
  --enroll '<TOKEN>' \
  --logstash-ui-url 'https://logstashui.example' \
  --yes
```

3. Day-2: `sudo systemctl status logstash-agent`  
   Install already enables and starts the agent; distro `logstash` is enable-only.

### Managed (multi-instance production tree)

1. Use **Managed Policy**, or **clone Packaged → Managed**.
2. Install with a Managed token (same `install --enroll` command).
3. Instance **N**, units `logstash-agent@N` / `logstash-managed@N`, paths under `managed-N/`.
4. Optional: pin Logstash with **VERSION** on the policy.

### Simulate

1. **Simulate Policy** (or clone).
2. Enroll as above (or non-root enroll + `sudo logstash-agent setup-simulate`).
3. Units `lsagent-simulate@N` / `ls-simulate@N`.
4. Pick the instance in the pipeline editor **Sim target** list.

See also [Simulate agents](/docs/docs/logstashui/configuration/host_mode.md).

### Embedded

- Docker Compose / local UI stack only; **do not enroll** the Embedded policy.
- Ports **9500 / 9560**. Listed automatically as a sim target when the agent is reachable.

---

## systemd and `logstash-agent-ctl`

Multi-instance and packaged units are controlled without sudoers wildcards (sudo-rs safe):

```bash
sudo logstash-agent-ctl start|stop|restart|status|enable|disable <unit>
```

Allowed units include:

- `logstash`, `logstash-agent`
- `logstash-agent@N`, `logstash-managed@N`
- `lsagent-simulate@N`, `ls-simulate@N`

(Numeric instance ids only.)

---

## E2E smoke

From the LogstashUI repo (sibling `LogstashAgent` checkout expected):

```bash
# Agent offline suite (no docker)
./bin/smoke_agent_modes.sh --offline

# HTTPS health + Django enroll smoke + agent offline
./bin/smoke_agent_modes.sh

# Rebuild UI/agent smoke images (applies migrations including PACKAGED/MANAGED), then smoke
./bin/smoke_agent_modes.sh --rebuild
```

What it checks:

| Phase | Coverage |
|-------|----------|
| Offline pytest | Coexistence configs, registry, materialize managed/simulate, VERSION prune, unit templates |
| HTTPS | UI product CA `:8443`, embedded agent `:9500` |
| Django | System policies, `build_policy_config`, enroll PACKAGED/MANAGED/SIMULATE, reject EMBEDDED, VERSION fields |

## Related docs

- [logstashagent.yml](/docs/docs/logstashagent/configuration/logstashagent.yml.md) — file schema
- [Agent configuration index](/docs/docs/logstashagent/configuration/index.md)
- [Simulate agents](/docs/docs/logstashui/configuration/host_mode.md)
- [LogstashAgent overview](/docs/docs/logstashagent/index.md)
- [Build guide](/docs/docs/logstashagent/general/build.md)
