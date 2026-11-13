# LogstashUI air-gapped wheelhouse (__VERSION__)

Linux **x86_64**, CPython **3.12** only. No PyPI. `[databases]` (psycopg + PyMySQL) and `[otel]` extras are in `wheels/`. SQLite is still the runtime default. Tracing stays off until `LOGSTASHUI_OTEL=true`.

This zip is **not** the recommended install when the host can reach GitHub or a container registry. Prefer Docker Compose (connected) or `pip install` of the normal wheel.

## Host packages

- CPython 3.12 (64-bit x86_64)
- Distro venv module (Debian/Ubuntu: `python3.12-venv`)

uv is **not** required.

## Install and run

```sh
./logstashui_local.sh --install
./logstashui_local.sh serve
```

`logstashui_local.sh --install` creates `.venv` and installs the bundled wheels. `serve` starts the server from that `.venv` and installs first if `.venv` is missing. Pass-through arguments go to the server: `./logstashui_local.sh serve --host 127.0.0.1`.

Upgrade from a newer archive or directory, in place:

```sh
./logstashui_local.sh --upgrade <archive>
```

`--upgrade` reuses the existing `.venv`, refuses to run while the server is running (stop it first; pid file `gunicorn.pid` in the data directory), and applies database migrations in place.

`--install-path <DIR>` installs into `<DIR>/.venv` instead of this directory. The default data directory resolves to `$INSTALL_DIR/logstashui_data`; set `LOGSTASHUI_DATA_DIR` to keep a custom data directory. Upgrades never delete, move, or replace files under it.

`install.sh` remains in this archive for backward compatibility:

```sh
./install.sh
.venv/bin/logstashui serve
```

Override the interpreter with `PYTHON=/path/to/python3.12 ./logstashui_local.sh --install` (or `PYTHON=/path/to/python3.12 ./install.sh`).

HTTPS UI is **:8443**. Data dir default is `$(pwd)/logstashui_data` (`LOGSTASHUI_DATA_DIR`). Same env vars as a normal install (`LOGSTASHUI_*`, `LOGSTASHUI_DB_*`).

systemd (does **not** enable the unit):

```sh
sudo .venv/bin/logstashui systemd
```

## Not included

LogstashAgent. Enroll agents separately. arm64 / Windows freezes are not this zip.

Git: `__GIT_SHA__`
