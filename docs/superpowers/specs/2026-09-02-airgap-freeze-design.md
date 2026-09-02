# 2026-09-02 — Air-gapped freeze (optional offline zip)

**LogstashUI version:** 0.5.2 (packaging feature; does not bump by itself)  
**Builder:** Linux x86_64, CPython **3.12**, uv, Docker (for the image tarball)  
**Isolated host (wheels):** Linux x86_64, CPython **3.12** (venv module / distro `python3.12-venv`)  
**Isolated host (docker):** Docker Engine  
**Isolated host (standalone):** glibc-compatible Linux x86_64, no Python  
**Chosen approach:** Optional freeze **script** that emits up to three artifacts. Default `uv build` / hatchling / published image **unchanged**.

## Goal

A maintainer with internet builds zip files that an air-gapped operator can copy, unpack, and run **without PyPI or a container registry**. This is not the default packaging path.

## Non-goals (v1)

- Changing hatchling includes, extras, or `uv build` output.
- A `logstashui freeze` CLI subcommand.
- Bundling LogstashAgent (separate product; compose `embedded` profile stays online-registry).
- Bundling CPython into the wheelhouse (host must already have 3.12).
- arm64 or Windows artifacts (names keep platform/ABI so those can be added later).
- Multiple CPython ABIs in one zip (cp312 only).
- Shipping uv, Node, or a compiler to the isolated host.
- Helm, K8s operator, or air-gap registry mirroring as this feature.
- Making freeze a required PR CI gate.
- Auto-update / delta patches of a freeze.

## Decisions (locked)

| Topic | Decision |
|---|---|
| Builder entry | `bin/freeze_logstashui.sh` (bash). Not default packaging. |
| Artifacts | Wheels zip **and** Docker tarball **and** standalone zip. Operator tests all three. |
| Default `uv build` | Unchanged (sdist + py3-none-any wheel only). |
| Python ABI | CPython **3.12** x86_64 only. Documented pin. |
| Platform | Linux x86_64 only. Later: arm64 / Windows as extra tags, not a rename. |
| Extras | Always include `LogstashUI[databases]` (psycopg binary + PyMySQL). |
| Agent | Not in any freeze zip. |
| Isolated run | Each zip has `README.md` + helper (`install.sh` / `load.sh` / `run.sh`). |
| Config | Same env as today. No YAML. `LOGSTASHUI_DATA_DIR` default `$(pwd)/logstashui_data`. |
| Standalone tool | PyInstaller. **Experimental** until smoke covers migrate + SNMP sync + TLS serve. |
| Wheel policy | **Binary wheels only** (`pip download --only-binary :all:`). Sdist-only dep → freeze **fails**. |
| Pins | Resolve from `uv.lock` (`uv export --frozen`). |
| PyInstaller in deps | **No.** Freeze script uses `uvx pyinstaller` (or a throwaway venv). Do not add to `[project]` or default `dev`. |
| CI | Optional `workflow_dispatch` only. Not on every PR. |

## Architecture

```
connected builder (linux x86_64, python3.12, uv, docker)
        |
        +-- bin/freeze_logstashui.sh [--wheels] [--docker] [--standalone] [--all]
                |
                +-- dist/offline/logstashui-{ver}-offline-wheels-linux-x86_64-cp312.zip
                +-- dist/offline/logstashui-{ver}-offline-docker-linux-x86_64.zip
                +-- dist/offline/logstashui-{ver}-offline-standalone-linux-x86_64.zip

isolated host copies zip → unzip → helper → logstashui serve
```

`--all` if no artifact flags. `--output DIR` default `dist/offline`. `--image NAME` for docker-save (skip build). `--version` taken from `pyproject.toml`.

Output stays under gitignored `/dist/`.

## Artifact 1 — Wheelhouse

**Builder steps**

1. Ensure Tailwind CSS exists (`src/logstashui/theme/static/css/dist/styles.css`); build it the same way `uv build` / Dockerfile does if missing.
2. `uv build` (reuse the normal wheel; do not invent a second hatch target).
3. `uv export --frozen --no-dev --extra databases --no-emit-project -o dist/offline/requirements-offline.txt` (keep hashes).
4. Copy the local LogstashUI wheel into `wheels/`. Download deps with **pip** (uv 0.12 has no `uv pip download`):
   `uv run --python 3.12 --with pip python -m pip download -r requirements-offline.txt -d wheels/ --python-version 3.12 --platform manylinux2014_x86_64 --implementation cp --abi cp312 --only-binary :all:`
5. Copy `LICENSE.txt`, `NOTICE.txt`, generated `install.sh`, `README.md`, `MANIFEST.txt`, `SHA256SUMS.txt`.
6. Zip. Fail if any `.tar.gz` sdist landed in `wheels/`.

**MANIFEST.txt** must list: LogstashUI version, git sha (or `unknown` if not a git checkout), CPython 3.12, platform `linux-x86_64`, extra `databases`, package list with versions.

**Isolated `install.sh`**

- `PYTHON=${PYTHON:-python3.12}`
- Refuse unless `sys.version_info[:2] == (3, 12)` and the interpreter is 64-bit.
- `$PYTHON -m venv .venv` (do **not** `pip install --upgrade pip` — that hits PyPI).
- `.venv/bin/python -m pip install --no-index --no-cache-dir --find-links ./wheels 'LogstashUI[databases]'`
- Print: activate / `.venv/bin/logstashui serve`, data-dir default, env pointer to the configuration docs (copied as a short README section, not a second docs site).

`install.sh` must not reach the network. `pip` `--no-index` is required. Prefer `--disable-pip-version-check`.

Isolated host packages: `python3.12` and the distro venv module (Debian/Ubuntu: `python3.12-venv`). **uv is not required** on the isolated host.

## Artifact 2 — Docker tarball

**Builder**

- If `--image` is set: `docker save` that **local** image. **Never** `docker pull`. Fail if the name is missing.
- Else: `docker build -f docker/Dockerfile -t logstashui:offline-{version} .` from repo root (same file as K8s/compose), then save that tag.
- Write `image.tar.gz` (`docker save | gzip`). Zip it with `load.sh`, UI-only `compose.offline.yml`, `README.md`, `SHA256SUMS.txt`, license files. Same zip story as the other two artifacts.

**`compose.offline.yml`**

- **One** service: LogstashUI. **No** Agent, **no** `embedded` profile.
- Image name matches what `docker load` will register.
- Port **8443**, `LOGSTASHUI_TLS` on, `LOGSTASHUI_DATA_DIR=/var/lib/logstashui`, named or bind volume for data.
- Same env-first model as Option 1. Operator fills `LOGSTASHUI_ALLOWED_HOSTS` / `LOGSTASHUI_DB_*` as needed.

**Isolated `load.sh`:** `docker load -i <tar>`, print the image name, print `docker compose -f compose.offline.yml up -d`.

## Artifact 3 — Standalone (experimental)

PyInstaller **onedir** (not onefile — Django data files + gunicorn + gevent extract less painfully). Entry: `LogstashUI.cli:main`.

Spec + helper templates live in repo `packaging/offline/` (not inside the Django wheel). Freeze script invokes `uvx pyinstaller` with that spec.

Must collect:

- All Django apps that the hatch wheel force-includes (`LogstashUI`, `PipelineManager`, `Management`, `Utilities`, `SNMP`, `Monitoring`, `Site`, `Documentation`, `AI`, `theme`, `Common`).
- Templates, static (including built Tailwind CSS), SNMP official data, packaged docs.
- Hidden imports: Django, gunicorn, gevent, greenlet, cryptography, pysnmp, lark, pygrok, whitenoise, psycopg, pymysql, yaml, htmx/tailwind Django apps.

**Why experimental:** Django loads apps/commands by name; gunicorn+gevent fork and monkey-patch; native wheels (`cryptography`, `psycopg`, `gevent`) need the same glibc. A missed hidden import or data file often boots then dies on `migrate`, SNMP, or the first TLS handshake. The freeze **must** document that.

**Pass criteria to drop “experimental”:** isolated-like run (no network) of `./logstashui serve` completes migrate + SNMP sync + collectstatic, binds **8443** HTTPS, `GET /` is not 500. Until then README says experimental; `run.sh` is `./logstashui serve`.

If gevent+PyInstaller cannot pass that smoke, do **not** silently switch the product default worker. Document the failure and stop; a sync/gthread workaround is a spec amendment, not a surprise.

## Isolated runtime (all three)

Unchanged product behavior after install:

- `logstashui serve` (migrate, SNMP official sync, collectstatic, product CA, gunicorn HTTPS :8443).
- Env: `LOGSTASHUI_*` / `LOGSTASHUI_DB_*` as today. SQLite default; Postgres/MySQL if they have a server.
- Do not rotate the product CA. Do not relocate `DATA_DIR` into the zip.
- systemd: after wheelhouse install, `logstashui systemd` still works if they have root (helper does **not** enable the unit). Standalone: document `ExecStart=` path to the unpacked binary; do not auto-write units in v1.

## Error handling

| Condition | Result |
|---|---|
| Builder not CPython 3.12 | Exit non-zero, print required ABI |
| Missing uv | Exit, how to install uv |
| `--docker` and Docker missing / image missing | Exit |
| `--standalone` and `uvx pyinstaller` fails | Exit |
| Dep has no manylinux cp312 binary wheel | Exit, name the package (no sdist fallback) |
| Tailwind CSS missing and npm build fails | Exit |
| Isolated `install.sh` wrong Python | Exit, “need CPython 3.12 x86_64” |
| Isolated pip would use PyPI | `--no-index` makes it fail; do not catch and retry online |

Never log DB passwords. MANIFEST may list package names/versions.

## Testing

Not a default pytest matrix job.

1. **Wheels (required for merge of the script):** run freeze `--wheels`; assert zip contains only `.whl` + scripts/docs; `docker run --network=none -v $PWD/zipdir:/offline python:3.12-slim` runs `install.sh` and `logstashui --help` plus `logstashui manage check`.
2. **Docker:** freeze `--docker`; `docker load`; `docker image inspect` the tag. Full compose up is manual.
3. **Standalone:** freeze `--standalone`; binary `--help`. Full `serve` smoke is the experiment gate (can be `--network=none` on a throwaway dir).

Optional GitHub Action: `workflow_dispatch`, linux runner, `--wheels` only (fastest, no PyInstaller cache pain). `--docker` / `--standalone` stay maintainer commands.

## Docs

New page: `docs/docs/logstashui/general/offline.md` (air-gap freeze). Link from `deploy.md` as an extra option **after** Docker / pip / systemd / K8s. State clearly: not the recommended connected-network install.

Page covers: builder prerequisites, the three zips, CPython 3.12 pin, `[databases]` included, no Agent, how to set env, DATA_DIR, and “later: arm64 / Windows”.

CHANGELOG under 0.5.2: optional freeze script; default wheel unchanged.

## Layout (repo)

```
bin/freeze_logstashui.sh          # builder
packaging/offline/                # PyInstaller spec, README/install/load/run templates
docs/docs/logstashui/general/offline.md
```

Do not put freeze helpers inside `src/logstashui/LogstashUI/packaging/` (that tree is systemd templates shipped in the wheel).

## Later (not v1)

- `linux/arm64` and `win_amd64` as additional freeze invocations (`--python-platform` / Windows builder).
- LogstashAgent sibling freeze script.
- Promoting standalone from experimental after the serve smoke exists.
- Bundling a CPython embed for hosts with no 3.12 (different product).
