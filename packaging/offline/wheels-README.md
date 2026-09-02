# LogstashUI air-gapped wheelhouse (__VERSION__)

Linux **x86_64**, CPython **3.12** only. No PyPI. `[databases]` extras (psycopg + PyMySQL) are in `wheels/`. SQLite is still the runtime default.

This zip is **not** the recommended install when the host can reach GitHub or a container registry. Prefer Docker Compose (connected) or `pip install` of the normal wheel.

## Host packages

- CPython 3.12 (64-bit x86_64)
- Distro venv module (Debian/Ubuntu: `python3.12-venv`)

uv is **not** required.

## Install and run

```sh
./install.sh
.venv/bin/logstashui serve
```

Override the interpreter with `PYTHON=/path/to/python3.12 ./install.sh`.

HTTPS UI is **:8443**. Data dir default is `$(pwd)/logstashui_data` (`LOGSTASHUI_DATA_DIR`). Same env vars as a normal install (`LOGSTASHUI_*`, `LOGSTASHUI_DB_*`).

systemd (does **not** enable the unit):

```sh
sudo .venv/bin/logstashui systemd
```

## Not included

LogstashAgent. Enroll agents separately. arm64 / Windows freezes are not this zip.

Git: `__GIT_SHA__`
