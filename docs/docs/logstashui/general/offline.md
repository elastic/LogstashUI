# Air-gapped freeze (optional)

Build zip files on a **connected** Linux x86_64 machine, copy them to a host with **no PyPI and no container registry**, and run LogstashUI.

This is **not** the default packaging path and **not** the recommended install when the network can reach GitHub or a registry. Prefer [Option 1: Docker](deploy.md#option-1-standard-docker-deployment-recommended) or [Option 3: pip / uv](deploy.md#option-3-pip--uv--systemd). Default `uv build` (sdist + `py3-none-any` wheel) is unchanged.

## What you get

`bin/freeze_logstashui.sh` emits up to three zips under `dist/offline/` (gitignored):

| Zip | Isolated host needs | Run |
|---|---|---|
| `logstashui-*-offline-wheels-linux-x86_64-cp312.zip` | CPython **3.12** x86_64 + venv | `./install.sh` then `.venv/bin/logstashui serve` |
| `logstashui-*-offline-docker-linux-x86_64.zip` | Docker Engine | `./load.sh` then `docker compose -f compose.offline.yml up -d` |
| `logstashui-*-offline-standalone-linux-x86_64.zip` | glibc Linux x86_64 | `./run.sh` (**experimental**) |

All three include `LogstashUI[databases]` (psycopg + PyMySQL) and `LogstashUI[otel]` (inert until `LOGSTASHUI_OTEL=true`). SQLite remains the runtime default. **LogstashAgent is not bundled.** arm64 and Windows are later freeze invocations, not this zip.

## Builder (connected)

Requirements: Linux x86_64 (wheels can also be downloaded from another OS via pip's `--platform`), CPython 3.12 (`uv python install 3.12`), [uv](https://docs.astral.sh/uv/), Docker for `--docker`, and (on Linux x86_64 only) a throwaway venv for PyInstaller.

```bash
./bin/freeze_logstashui.sh --wheels
./bin/freeze_logstashui.sh --docker
./bin/freeze_logstashui.sh --standalone   # Linux x86_64 only
./bin/freeze_logstashui.sh --all          # default if you pass no artifact flags
./bin/freeze_logstashui.sh --docker --image logstashui:offline-0.5.1
```

`--image` saves a **local** tag. The script never `docker pull`. `--standalone` on macOS/Windows/ARM **fails** if you passed that flag; `--all` **skips** it with a warning.

Wheel policy: **zip contains only `.whl` files**. The builder prefers `manylinux2014` then `manylinux_2_28` cp312 wheels (isolated host needs glibc **2.28+**, e.g. RHEL 8 / Ubuntu 20.04). Pure-Python sdists (no manylinux wheel) are converted to `py3-none-any` on the **connected** builder. A native package with no manylinux wheel fails the freeze — the isolated host has no compiler. Pins come from `uv.lock`.

Smoke the wheelhouse (pulls `python:3.12-slim` first, then installs with `--network=none`):

```bash
./bin/test_freeze_wheels.sh
```

Optional CI: `.github/workflows/offline-freeze.yml` is `workflow_dispatch` only (not a required PR check).

## Isolated host

Same env as a normal install: `LOGSTASHUI_DATA_DIR` (default `$(pwd)/logstashui_data`), `LOGSTASHUI_*`, `LOGSTASHUI_DB_*`. HTTPS on **:8443**. Product CA is created on first start under the data dir — do not expect CA files inside the zip.

**Wheels:** Debian/Ubuntu need `python3.12` and `python3.12-venv`. `install.sh` uses `pip install --no-index --find-links ./wheels 'LogstashUI[databases,otel]'`. It does **not** upgrade pip (that would hit PyPI). uv is not required.

**Docker:** UI-only compose (no Agent, no `embedded` profile). Set `ALLOWED_HOSTS` / `LOGSTASHUI_HOST_*` / `LOGSTASHUI_DB_*` as needed.

**Standalone:** experimental PyInstaller onedir. Treat as a trial until `serve` completes migrate, SNMP official sync, collectstatic, and HTTPS :8443 with no network. Gunicorn stays gevent; do not switch workers as a workaround.

After a wheelhouse install, `logstashui systemd` still writes the unit and `/etc/default/logstashui` and does **not** enable it.

## Later

linux/arm64 and Windows x86_64 as extra freeze tags; a sibling LogstashAgent freeze; promoting standalone off experimental after the serve smoke exists.
