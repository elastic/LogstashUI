# LogstashUI air-gapped wheelhouse (__VERSION__)

Linux **x86_64**, CPython **3.12** only. No PyPI. `[databases]` (psycopg + PyMySQL) and `[otel]` extras are in `wheels/`. SQLite is still the runtime default. Tracing stays off until `LOGSTASHUI_OTEL=true`.

This zip is **not** the recommended install when the host can reach GitHub or a container registry. Prefer Docker Compose (connected) or `pip install` of the normal wheel.

## Host packages

- CPython 3.12 (64-bit x86_64)
- Distro venv module (Debian/Ubuntu: `python3.12-venv`)

uv is **not** required.

## Install and run

Prefer the bundled `logstashui_local.sh`:

```sh
./logstashui_local.sh --install
./logstashui_local.sh serve --bind 127.0.0.1:8443
```

`--install` creates `.venv` from the bundled `wheels/` and installs `LogstashUI[databases,otel]` with no network. `serve` starts the server and passes trailing arguments through to `logstashui serve`, so use `--bind` for host/port binding. `serve` installs first if `.venv` is missing.

To upgrade in place from a newer archive, stop the server first and run `--upgrade` against the new zip:

```sh
./logstashui_local.sh --upgrade /path/to/logstashui-<version>-offline-wheels-linux-x86_64-cp312.zip
```

`--upgrade` reuses the existing `.venv`, reinstalls from the archive's `wheels/`, and applies database migrations in place.

The legacy `install.sh` and `wheels-install.sh` remain in the archive for backward compatibility:

```sh
./install.sh
.venv/bin/logstashui serve
```

Override the interpreter with `PYTHON=/path/to/python3.12 ./logstashui_local.sh --install` (or before `./install.sh`).

HTTPS UI is **:8443**. Data dir default is `$INSTALL_DIR/logstashui_data` (for a bundle in place, `$(pwd)/logstashui_data`). Keep an existing custom data directory by setting `LOGSTASHUI_DATA_DIR`, which both `serve` and `--upgrade` honour and export. Same env vars as a normal install (`LOGSTASHUI_*`, `LOGSTASHUI_DB_*`).

systemd (does **not** enable the unit):

```sh
sudo .venv/bin/logstashui systemd
```

## Not included

LogstashAgent. Enroll agents separately. arm64 / Windows freezes are not this zip.

Git: `__GIT_SHA__`
