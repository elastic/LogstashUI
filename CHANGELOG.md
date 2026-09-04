## [0.5.2] - Multi-database - 09/01/2026

Package version is **0.5.2** (`pyproject.toml`). Preferred LogstashAgent version is **0.5.2** (lockstep).

SQLite does not scale under gunicorn/gevent. Operators can now run LogstashUI on **SQLite** (default), **PostgreSQL 14+**, or **MariaDB 10.6+ / MySQL 8.0+** without changing the Django ORM data model.

### Database engines

- `LOGSTASHUI_DB_ENGINE=sqlite|postgresql|mysql` (MariaDB uses `mysql`). Aliases: `sqlite3`, `postgres`, `mariadb`, `my`.
- Discrete env only: `LOGSTASHUI_DB_HOST`, `PORT`, `NAME`, `USER`, `PASSWORD`, plus `LOGSTASHUI_DB_SSLMODE` / `LOGSTASHUI_DB_SSL_CA`, `LOGSTASHUI_DB_CONN_MAX_AGE` (default 60), `LOGSTASHUI_DB_CONN_HEALTH_CHECKS` (default true). No YAML. No `DATABASE_URL`.
- Unset engine is still SQLite at `$LOGSTASHUI_DATA_DIR/db.sqlite3` (WAL + `busy_timeout` unchanged).
- `logstashui serve` logs a warning when engine is SQLite and `LOGSTASHUI_WORKERS>1`; it does not refuse to start.
- Fail-fast on unknown engine, missing driver extra, missing HOST/USER, or server below version floors. `logstashui serve` checks the server version **before** `migrate` and still checks when `--skip-migrate` is set.
- `logstashui migrate-engine --to` accepts `postgresql`, `mysql`, and `mariadb` (`mariadb` is an alias of `mysql`).
- MySQL/MariaDB use `utf8mb4` / `utf8mb4_bin` so unique names match SQLite/Postgres case-sensitivity. Create the database with that collation.
- `LOGSTASHUI_DATA_DIR` is still required when the database is remote (TLS, Django secret, logs, staticfiles).
- gunicorn stays `--worker-class gevent`. PostgreSQL uses `psycopg[binary]`; MySQL/MariaDB use PyMySQL (not mysqlclient). Optional PgBouncer is documented, not required.

### Packaging and Docker

- Native extras: `LogstashUI[postgres]`, `LogstashUI[mysql]`, `LogstashUI[databases]`, `LogstashUI[otel]`. Default wheel stays SQLite-only.
- Optional air-gapped freeze: `bin/freeze_logstashui.sh` (`--wheels` / `--docker` / `--standalone`). Default `uv build` unchanged. Linux x86_64, CPython 3.12, `[databases]` and `[otel]` included, no Agent. Wheelhouse prefers manylinux2014 then manylinux_2_28; pure-Python sdists are wheeled on the builder. Standalone PyInstaller is experimental. See [Air-gapped freeze](docs/docs/logstashui/general/offline.md).
- Container image installs `LogstashUI[databases,otel]`. Tracing stays off until `LOGSTASHUI_OTEL=true`. Kubernetes only sets env.
- systemd generator prompts for engine/host/port/name/user; sample `/etc/default/logstashui` documents all `LOGSTASHUI_DB_*` keys. Set the password in the EnvironmentFile or a Secret (`chmod 640`).
- gunicorn writes `$LOGSTASHUI_DATA_DIR/gunicorn.pid`.

### Migration off SQLite

- **Supported offline path:** stop UI → back up `db.sqlite3` → `dumpdata` while still on SQLite → create the server database → set `LOGSTASHUI_DB_*` → `migrate` + `loaddata`. Keep `DATA_DIR` (same secret key) or encrypted keystore rows will not decrypt. Sessions are not copied; log in again.
- **BETA** `logstashui migrate-engine --to postgresql|mysql --i-have-a-backup` dumps the SQLite file, loads the target, and does **not** restart serve. It SIGTERMs gunicorn if a pidfile is live. Prefer `systemctl stop` first so `Restart=` does not race. Optional `--write-env` appends engine/host/name/user (never the password).
- BETA `migrate-engine` is **not atomic** on the target: `dumpdata` → `migrate` → `loaddata` is three steps. If `loaddata` fails, the target may be partially populated. Drop or recreate the target database (SQLite is only WAL-checkpointed) and re-run. A later production migrator could wrap `loaddata` and Postgres `sequence_reset_sql` in `transaction.atomic()` after `migrate`; `migrate` itself applies DDL and cannot be one atomic unit on MySQL/MariaDB.

### Testing

- Default `pytest` stays SQLite (no Docker, no extras).
- `bin/test_databases.sh` / `bin/test_databases.bat` start local Docker Postgres 16, MariaDB 11, and MySQL 8.0 and run the full suite on each engine, then run `tests/Database/` via testcontainers. CI workflow `.github/workflows/test-databases.yml` calls the same script.
- Self-contained database test suite at `tests/Database/integration/` uses `testcontainers` (postgres:16, mysql:8.0, mariadb:11 — no external Docker Compose). Parametrized over PostgreSQL and MySQL; MariaDB covered for `check_server_version` version-detection. Skips gracefully when Docker is unavailable. Covers DB config, migrations (clean, idempotent, no unapplied), ORM CRUD/JSON/uniqueness, and full SQLite → PG/MySQL/MariaDB `migrate-engine` round-trips. Run with `uv run pytest tests/Database/ -v --no-cov` after `uv sync --group dev --extra databases`.
- All tests migrated from `src/logstashui/<App>/tests/` to a dedicated `tests/` tree at the project root. Layout: `tests/<App>/unit/` per Django app, `tests/Database/unit|integration/` for database and migration tests. Shared fixtures moved from `Common/test_resources.py` to `tests/conftest.py` (auto-discovered by pytest). `testpaths` trimmed to `["tests"]`; `pythonpath = ["src/logstashui"]` unchanged so app imports still resolve. Run any app in isolation: `uv run pytest tests/SNMP -v`.
- `test_case_sensitive_unique` now asserts case-sensitive uniqueness at both layers. `Network.save()` calls `full_clean()`, so a duplicate name raises `ValidationError` from `validate_unique()` and the `INSERT` is never issued — the test previously expected an `IntegrityError` that the database could never raise, and failed identically on both engines. The collation check (`utf8mb4_bin` on MySQL, default on PostgreSQL) rides on the `validate_unique()` query; the database unique index is verified separately via `bulk_create()`, which bypasses `save()`, inside `transaction.atomic()` so PostgreSQL can roll back the aborted statement before cleanup.
- Container fixtures moved from the deprecated `testcontainers.postgres` / `testcontainers.mysql` shims to `testcontainers.community.*`. The dev-dependency floor is raised to `testcontainers>=4.15.0`, the first release containing that package.
- API token coverage in `tests/Common/unit/test_api_token_middleware.py` and `tests/Management/unit/test_api_tokens.py`. The load-bearing case is the inverse one: a logged-in session POSTing without a CSRF token must still be rejected, so the exemption cannot regress into a site-wide CSRF bypass. Also covers revoked/expired/inactive-owner tokens, readonly-owner denial, agent keys passing through untouched, and that re-saving a token does not double-hash it.
- Smoke compose is still SQLite (product CA / PUID unchanged).

### Kubernetes and database docs

- Kubernetes subsection: StatefulSet + one PVC at `/var/lib/logstashui`, TLS kept on `:8443`, Ingress-nginx skip backend verify, Envoy Gateway `Backend` `insecureSkipVerify` (enable Backend API), CloudNativePG Cluster in the app namespace.
- K8s probes send `Host: logstashui` (kubelet otherwise uses the pod IP and Django returns 400). Downward API `status.podIP` → `LOGSTASHUI_HOST_IPS` for the product leaf; those IPs are appended to `ALLOWED_HOSTS` unless the list is `*`.
- Example manifests under `docs/docs/logstashui/kubernetes/examples/{sqlite,postgresql,mysql}/`.
- Database subsection: engines, every `LOGSTASHUI_DB_*` default, offline dump/load, BETA `migrate-engine`, CREATE DATABASE scripts (`utf8mb4_bin` for MySQL/MariaDB), schema snapshots from 0.5.2 `migrate`.

### Insecure HTTP (escape hatch)

- `LOGSTASHUI_INSECURE_HTTP=true` forces plain HTTP for the UI and every UI→agent URL, skips product CA and certificate generation, and overrides `LOGSTASHUI_TLS`. This is **not** best practice; automatic TLS remains the supported default. It is **not** the same as `LOGSTASHUI_TLS=false` (TLS-terminating ingress). See [Environment](docs/docs/logstashui/configuration/environment.md).
- Settings TLS **Upload** and **Revert** are hidden in this mode and return **409** before any filesystem change. Leftover `$DATA_DIR/tls/` custom leaves are left intact (`save_custom_ui_certificate` / `revert_ui_certificate_to_product_default` raise `ProductCADisabled` first).
- Default Compose and Kubernetes examples remain HTTPS. The hatch is native/`logstashui serve` (or a hand-edited EnvironmentFile). StatefulSet examples comment that probes stay `scheme: HTTPS`.

### Fixes

- `LOGSTASHUI_OTEL=true` without the `[otel]` extra now logs **ERROR** (was INFO) and continues. Docker/K8s and freeze artifacts install `[otel]`; uncomment the OTEL keys in the Kubernetes ConfigMap examples to enable OTLP/HTTP (port 4318, not gRPC 4317).
- `LOGSTASHUI_TLS=false` now suppresses the Django-level HTTP→HTTPS redirect (`SECURE_SSL_REDIRECT`) in addition to disabling the Gunicorn TLS certificate. Previously, running the container with `-e LOGSTASHUI_TLS=false` still returned a `301` because `SECURE_SSL_REDIRECT` was gated on `DEBUG` only. Both knobs are now independent.
- `ApiKey.save()` no longer re-hashes an already-hashed key. `make_password()` ran unconditionally on every save, so any update to an existing row silently rewrote the hash and invalidated the credential. Latent until now — nothing re-saved an `ApiKey` — but renaming or revoking a token does.
- The pipeline editor's simulation **Target** picker no longer hides the embedded agent on first page load. Making the probe non-blocking left `list_simulation_targets()` requiring a successful probe it never performed, so the sticky embedded row lost a race against the background thread and the dropdown rendered empty until a later refresh. The row is now dropped only when a probe has *explicitly* reported the agent offline — never-probed is treated as unknown, not offline. Target rows also carry a `discovered` flag so callers can distinguish a confirmed agent from an unconfirmed one.

### API access

- **Admin API tokens** (`Management → API Tokens`) let scripts, CI, and provisioning tools call LogstashUI's JSON endpoints without a browser session. Send `Authorization: ApiKey lsui_<prefix>_<secret>`. The original motivation was registering a remote Elasticsearch cluster for Centralized Pipeline Management from `curl`, which previously failed CSRF verification; it now works against the existing `/ConnectionManager/AddConnection` URL. Every other JSON endpoint accepts a token too — no per-endpoint opt-in.
- A token acts as the user who created it and inherits that account's role, so audit lines stay attributable and a `readonly` user's token stays readonly. Tokens can carry an optional expiry and be revoked or deleted; revocation takes effect on the next request. Only a hash is stored, so the secret is displayed exactly once at creation.
- Implemented as a pair of middlewares rather than per-view decorators. `ApiTokenCsrfMiddleware` runs immediately before `CsrfViewMiddleware` and sets `_dont_enforce_csrf_checks` **only after a token verifies** — a forged or absent header cannot switch CSRF off, and cookie-authenticated browser requests are unaffected. `ApiTokenUserMiddleware` runs just after `AuthenticationMiddleware`, which would otherwise overwrite `request.user`; the split is forced by that ordering. Because `request.user` becomes a real user, `LoginRequiredMiddleware` and `require_admin_role` pass on their own — no `@csrf_exempt` and no `LOGIN_REQUIRED_IGNORE_PATHS` entries were added.
- `require_admin_role` now answers API-token callers with JSON instead of an `HX-Trigger` toast, which is unreadable to a script.
- Admin tokens reuse the agent `ApiKey` table and its `make_password`/`check_password` machinery. The one addition is an unhashed, indexed `prefix` column: agent keys are found via the `connection_id` in the request body before their hash is checked, but a token presents only a header, and without a lookup key resolving it would mean a PBKDF2 comparison against every row. Existing agent keys get `prefix=NULL` and are never matched by the middleware.
- See [API Access](docs/docs/logstashui/api_access.md).

### Agent version display

- ConnectionManager and Policy editor Agents tab show a cyan **LS X.Y.Z** pill for the Logstash version the agent reported (`logstash_version_resolved`, else Logstash API version). Hidden until known.
- Policy Source **VERSION** live-fills and persists Binary Path as `{download_dir}/logstash-{version}/bin` (default `/opt/logstash-agent/logstash-versions/logstash-X.Y.Z/bin`). Custom paths are kept. Switching back to SYSTEM restores `/usr/share/logstash/bin` when the field still looks derived.
- Agent newer than preferred (`__PREFERRED_LS_AGENT_VERSION__`, currently 0.5.2) shows **unreleased version** instead of a backwards Upgrade button. Older agents still get Upgrade. Unparseable versions still get Upgrade.
- **The LS pill now tracks the Logstash version actually running on the host.** It was frozen at whatever version happened to be recorded first, for two reasons. `resolve_running_logstash_version()` consulted the `Connection.logstash_version_resolved` column *before* the current check-in's `status_blob`, and that column is only ever written on a truthy value and never cleared — so one stored version permanently shadowed every later one. The check-in handler also never read `status_blob.logstash_api.version`, the version the running instance reports through its own API, so on hosts that report it only there the column was never refreshed at all. The blob now leads and the column is the fallback, which keeps the last known version on screen while Logstash is stopped or its API is unreachable.
- The pill also updates without a page reload. The Connections page adds `logstash_version` to the existing agent-status SSE payload — free, since the stream already selects `status_blob` — and the Policies → Agents table, which had no live channel at all, polls every 10s while that tab is visible and pauses when the browser tab is hidden.

### Logstash tarball proxy

- **LogstashUI can now cache Logstash release tarballs and serve them to agents.** A `MANAGED` or `SIMULATE` policy pinned to **VERSION** previously made every agent pull its own ~450 MB tarball from `artifacts.elastic.co`. Tick **Download the tarball from LogstashUI** on the policy and LogstashUI fetches each release once, verifies its SHA-512, and serves it to every agent. Required for air-gapped sites, where the direct download is impossible. See [Logstash Tarball Proxy](docs/docs/logstashui/configuration/logstash_proxy.md).
- **Compatibility — the agent artifact URL gained a `connection_id` segment.** `GET /ConnectionManager/LogstashArtifact/{filename}` is now `GET /ConnectionManager/LogstashArtifact/{connection_id}/{filename}`. A GET has no body, and an agent key is a bare hash with no lookup column, so the header alone cannot identify the caller — the path is what narrows the lookup to one row before `check_password` runs. Agents older than the paired release cannot use the proxy; the boolean simply stays off for them and they continue downloading from Elastic.
- The proxy is exposed to agents in three places: `logstash_via_ui` in the enrollment `policy_config`, `logstash_via_ui` in the check-in response, and `logstash_runtime.via_ui` in the config delta. `via_ui` participates in the `runtime_changed` comparison, so flipping the checkbox alone triggers a re-materialize — no separate Deploy for binary-only changes.
- **Management → Logstash Tarballs** manages the cache: download by version + architecture (or from a full URL for an internal mirror), delete, retry, and **Import from disk** for air-gapped operators who copy a tarball into the cache directory by hand. Import hashes the file, checks a supplied `.sha512` and fails on mismatch, and writes one when none was supplied. There is no browser upload — 450 MB through a form is not viable. Progress polls over htmx only while a row is actively fetching.
- **Single-flight is a conditional database `UPDATE`, not an in-process lock.** `settings.py` defines no `CACHES`, so Django falls back to per-process `LocMemCache`, which does not coordinate across gunicorn workers. The first agent to ask claims the row and gets a `503`; everyone else gets a `503` until the file lands, across all workers. A fetch killed by a restart leaves a stale claim that the next request reclaims after the heartbeat window, and the orphaned `.part` is swept at startup — crash recovery is the normal path, not an edge case, because a 450 MB fetch will always be killed by `graceful_timeout`.
- Nothing partial is ever served: downloads land in a `.part` file and are `os.replace()`d into place only after the SHA-512 verifies. Agents get `200`/`206` when the file is ready, `503` while it is being fetched, `429` at the concurrent-serve cap, `502` on an upstream failure, `404` for an unrecognized filename, and `401` for a bad key or mismatched `connection_id`. `503`/`429`/`502` all carry `Retry-After`; agents honour it, backing off to a 5-minute ceiling, and never fall back to `artifacts.elastic.co` while the proxy is enabled.
- Range requests are supported (single range only) so an interrupted transfer resumes instead of re-pulling the whole tarball. Files under 1 MiB — the `.sha512` companions — are exempt from the serve semaphore, so a burst of checksum fetches cannot consume download slots.
- New env vars: `LOGSTASHUI_LOGSTASH_DIR` (default `<DATA_DIR>/logstashes`), `LOGSTASHUI_ARTIFACT_MAX_UPSTREAM` (default `2`, cluster-wide), and `LOGSTASHUI_ARTIFACT_MAX_SERVE_PER_WORKER` (default `4`; effective total is this × `LOGSTASHUI_WORKERS`). The serve cap is deliberately per-worker — dividing a global limit by the worker count truncates to zero and makes the knob lie. The upstream base URL is **Management → Settings → Logstash tarball source**, blank meaning `https://artifacts.elastic.co/downloads/logstash`.
- Tarballs are stored in `<DATA_DIR>/logstashes`, **not** under `staticfiles/` — `STATIC_ROOT` is served by WhiteNoise at `/static/`, which is in `LOGIN_REQUIRED_IGNORE_PATHS`, so every tarball would have been an unauthenticated public download, and `collectstatic` would churn over them on every `serve`.
- **Optional OpenTelemetry export** (`LOGSTASHUI_OTEL=true` plus the new `LogstashUI[otel]` extra) sends traces and metrics over OTLP/HTTP. The Docker/K8s image and freeze artifacts install `[otel]` (the wheelhouse already downloaded those wheels); tracing stays off until the env flag is set. Native pip/uv still needs the extra. If `LOGSTASHUI_OTEL=true` and the extra is missing, LogstashUI logs ERROR and the worker keeps serving. Four custom instruments answer the capacity question Django spans cannot: `logstashui.gevent.hub.lag`, `logstashui.artifact.downloads.active`, `logstashui.artifact.requests`, and `logstashui.artifact.serve.bytes_per_second`. Only the HTTP/protobuf exporter is supported — the gRPC exporter's native threads are not gevent-patchable.
- Migrations: `PipelineManager/0029_logstash_artifacts` (the `LogstashArtifact` model and `Policy.logstash_via_ui`) and `Management/0004_settings_logstash_artifact_base_url`.
- New tests: `tests/PipelineManager/unit/test_logstash_artifacts.py` and `tests/Management/unit/test_logstash_artifact_page.py`.


## [0.5.1] - Agent control plane, SNMP NMS, dual HTTPS - 08/31/2026

Package version is **0.5.1** (`pyproject.toml`). Preferred LogstashAgent version is **0.5.1**.

This release is the next step after **0.4.x**: full SNMP network management, first-class agent roles (Packaged / Managed / Simulate / Embedded), multi-instance simulation, and mutual TLS between UI and agents.

### Agent roles and multi-instance simulation

- Policy types **PACKAGED**, **MANAGED**, **SIMULATE**, **EMBEDDED** (DEFAULT remains a legacy alias of PACKAGED). System seeds: Packaged, Managed, Simulate, and Embedded policies.
- Clone **Packaged → Managed** auto-applies isolated `managed-N` path schemes. Simulate policies stay cloneable with SYSTEM vs VERSION Logstash source.
- Enroll allocates instance **N** with role-specific ports and units:
  - **Packaged:** `logstash-agent` + distro `logstash` (enable-only at install)
  - **Packaged:** agent FastAPI **9550**, distro Logstash API **9600** (not both 9600)
  - **Managed N:** `logstash-agent@N` / `logstash-managed@N`, paths under `/opt/logstash-agent/managed-N/`, ports **9550+N** / **9700+N**
  - **Simulate N:** `lsagent-simulate@N` / `ls-simulate@N`, paths under `/opt/logstash-agent/simulate-N/`, ports **9500+N** / **9560+N**
- Pipeline editor **Sim target** picker (sticky selection); embedded Docker agent appears without enroll.
- Pre-simulation keystore clone with compare-and-skip; keystore password clear over check-in.
- Policy UI filters/badges for roles; VERSION lifecycle hint (binary pin applies on agent check-in).
- Enroll UI: Embedded excluded from enroll list; Install Logstash hidden for Embedded and VERSION; install snippet is full-deploy (no trailing enable/start noise).
- **Embedded** policy type is now hidden from the operator UI, policy type picker, and external data directory settings to reduce confusion for non-simulate workflows.
- Simulate target slots are now **pre-warmed** before use; multi-doc session slots and allocation reliability are improved.
- Sim slots are **isolated per agent**; slow simulate-forward is tolerated more gracefully rather than causing slot exhaustion.

### Dual HTTPS and product CA

- UI serves HTTPS on **:8443** (gunicorn); embedded agent on **:9500**. Compose no longer uses nginx.
- Auto product CA under `$LOGSTASHUI_DATA_DIR/tls/` (git checkout bind: `<project_root>/logstashui_data`); public `/.well-known/logstashui/ca.crt`; optional enrollment-token CA fingerprint.
- Product-CA-signed **agent server certs** (enroll, check-in re-issue, or compose CSR secret).
- Settings: agent callback URL and custom UI certificate upload / revert to product default.
- Host hostname and LAN IPs injected for product cert SANs so browsers can use `https://<host-ip>:8443`.
- **Container-aware agent callback host:** when LogstashUI runs in a container (or `LOGSTASHUI_IN_CONTAINER=1`), check-in/enroll prefer the agent’s `callback_ip` / IP-literal `host` for `Connection.host` so sim health and editor traffic do not depend on host DNS.
- Check-in / GetConfigChanges expand multi-instance path templates (`{instance_id}`) using `Connection.instance_id` so simulate/managed agents do not get literal `simulate-{instance_id}` paths.
- Materialize nested `api.http.port` (and `{instance_id}` in paths) for simulate/managed enroll and GetConfigChanges so Logstash listens on **9560+N** / **9700+N** instead of leaving the template port **9560**.

### SNMP network management (NMS)

- End-to-end SNMP app: discovery, onboarding, templates/profiles, monitoring cards, and deploy through Logstash.
- Device Wizard onboarding (manual, discovery, and AI-assisted) with MIB-grounded authoring.
- Official device templates/profiles (including Ubiquiti APs, Palo Alto firewalls, and a generic Default catchall), images, and type classification.
- **Palo Alto firewall** official device template added, including a "keep when" Ruby normalizer to extract a specific row type from mixed-type SNMP tables (this normalizer primitive is restricted to official profiles).
- Profile normalizers (rename, multiply/divide, ratios, averages, translate) through onboarding and pipeline generation.
- Time Series Data Streams for SNMP metrics, namespaces, and index-template install on deploy.
- SNMP deploy/check-in coordination with agent multi-source apply (policy + SNMP in one cycle).

### Operations and docs

- Runtime state (sqlite, TLS, secrets, logs) is configurable via `LOGSTASHUI_DATA_DIR` / `paths.data` and lives outside `src/`. Git-checkout Compose bind-mounts `<project_root>/logstashui_data` → `/var/lib/logstashui`.
- Linux Docker bind-mount: entrypoint starts as root, chowns **only** the data dir if needed, drops to `PUID`/`PGID` (`start_logstashui.sh` uses the operator uid) or `appuser` **10001**. Does not rotate the product CA. K8s: PVC + `runAsUser`/`fsGroup` 10001.
- Installable sdist/wheel with `logstashui` console script (`serve` / `manage` / `systemd`). Config is environment-only; `logstashui.yml` is not read. systemd unit generator writes `/etc/default/logstashui` (manual).
- Operator guide: [Agent roles, ports, coexistence, and VERSION](docs/docs/logstashagent/general/roles.md).
- E2E smoke: `bin/smoke_agent_modes.sh` (HTTPS, Django enroll, sibling agent offline tests).
- Migrations through **0027** (Packaged/Managed default ports). Compose entrypoint migrates on start.

### Bug fixes and polish

- Fixed an agent modes regression that caused page loading to block when resuming certain async agent workflows.
- Fixed template generation when the connection uses an Elasticsearch + Kibana URL pair instead of a Cloud ID; multiple edge cases related to URL-based connections are now handled correctly.
- Fixed a bug where simulation pipelines would not warm up after a pipeline change, requiring a manual refresh before re-simulating.
- Fixed a bug where the connection probe toward the embedded simulation node was blocking, causing every pipeline in the list to take ~3 seconds to load; the probe is now async and non-blocking.
- Fixed a bug in SNMP device testing where hostname-only devices were never tested (only IPs were attempted). Hostname resolution is now tried first, with a fallback to IP, and a clear notification is shown when DNS resolution fails.
- Fixed a bug where the SNMP data stream template install prompt was only triggered for CPM-based connections; it now correctly triggers for agent-managed connections as well.
- Fixed a bug where the SNMP device panel showed no CPU/memory metrics and displayed all interfaces as grey.
- Fixed a bug where temperature sensor and fan metrics were not appearing in the device panel.
- Fixed a bug where the SNMP CRUD modals displayed an incorrect page header on the Devices page when "Add Credential" or "Add Network" was opened.
- Added front-end and back-end validation for the namespace input field to prevent namespaces that Elastic would reject at ingest.
- Improved SNMP deploy messaging when an agent is not assigned to the network being deployed.
- SQLite WAL (Write-Ahead Logging) mode is now enabled, improving concurrency under simultaneous requests.
- Document-waiting popups now use `popup.html` (the app's themed popup) instead of the native browser dialog.
- Updated `start_logstashui.bat` (Windows startup script) to mirror the behavior of `start_logstashui.sh`.

### Upgrade notes

- Pair with **LogstashAgent 0.5.1**.
- Run migrations (compose does this automatically).
- Existing production agents on Default/Packaged **do not need to re-enroll**; restart after agent package upgrade.
- Prefer enrolled **Simulate** agents for pipeline simulation; leave Packaged for production. Use **Managed** for multi-instance production trees on the same host.
- See the roles guide for coexistence (isolated state/config per instance) and VERSION pins.


## [0.5.0] - NMS release - 07/21/2026

### Added

- Added a complete SNMP network management application for discovering, onboarding, configuring, monitoring, and deploying network devices through Logstash.
- Added a consolidated onboarding experience for device discovery, manual device setup, and AI-assisted device generation.
- Added a modal-based Device Wizard workflow so users remain on the Device Wizard page throughout onboarding.
- Added AI-assisted SNMP device onboarding that can:
  - Walk a device.
  - Identify device capabilities.
  - Generate device templates and profiles.
  - Allow iterative review and refinement.
  - Approve and deploy generated configurations.
- Added inline MIB-grounded AI authoring without requiring a separate runtime knowledge base.
- Added full-column SNMP discovery walks to improve grounding coverage during AI generation.
- Added support for re-onboarding devices without failing when an existing template or profile has the same name.
- Added official SNMP device templates and profiles for a wider range of network devices.
- Added initial Ubiquiti access point profiles and templates.
- Added a generic `Default` device template that acts as a catchall for devices without an explicitly assigned template.
- Added device type classification to device templates.
- Added official-template tracking to distinguish built-in templates from user-created templates.
- Added images to device, network, template, and profile interfaces to make objects easier to identify.
- Added card-based metric visuals for:
  - CPU cores.
  - Wireless radios.
  - CDP and LLDP neighbors.
  - Filesystems.
  - Printer ink and consumables.
- Added configurable profile normalizers, replacing the previous hard-coded field-normalization implementation.
- Added normalizers for:
  - Field renaming.
  - Multiplication.
  - Division.
  - Ratios.
  - Ratios calculated from table rows.
  - Column averages.
  - Translate mappings.
- Added support for carrying user-authored and AI-authored normalizers through onboarding, approval, synchronization, and pipeline generation.
- Added Time Series Data Stream support for generated SNMP metrics.
- Added time-series dimensions and index-template installation during deployment.
- Added configurable namespaces for SNMP data streams.
- Added support for separating SNMP data streams by:
  - A shared namespace.
  - Network namespace.
  - Device-template namespace.
- Added a network-level option to create namespaces per device template.
- Added editable Elasticsearch connections.
- Added automatic invalidation of stale credentials when an Elasticsearch connection is edited.
- Added Logstash Agent support for SNMP pipeline deployment and management.
- Added Logstash Agent information to the agent inspection Process tab.
- Added support for identifying agents managed through Centralized Pipeline Management when a sibling connection is used for management.
- Added keystore discovery for Centralized Pipeline Management connections.
- Added support for plaintext SNMP credentials in generated pipelines when keystores are not being used.
- Added SNMP credential and connectivity testing throughout the SNMP application.
- Added clearer SNMP test results for:
  - Invalid credentials.
  - Connection timeouts.
  - Devices that do not respond.
- Added SNMP walk testing for troubleshooting and future AI template generation.
- Added discovery-pipeline generation for empty networks that have discovery enabled.
- Added safeguards preventing discovery configuration for networks larger than `/20`.
- Added device-level location and arbitrary metadata fields.
- Added configurable metadata enrichment for generated SNMP events.
- Added device counts to the credentials page.
- Added credential-table pagination with page sizes of 25, 50, 100, and 200.
- Added asynchronous search and loading for credential selectors.
- Added searchable device-template selectors.
- Added custom image-based device-template selection controls.
- Added expandable editors for large text fields such as Grok patterns and Dissect mappings.
- Added support for preserving comments inside plugin configurations.
- Added support for regular expressions in pipeline conditions.
- Added a Logstash and LogstashUI compatibility matrix.
- Added comprehensive SNMP architecture, onboarding, deployment, and operations documentation.
- Added documentation for:
  - Creating credentials.
  - Creating networks.
  - Discovering devices.
  - Assigning templates and profiles.
  - Committing and deploying changes.
  - SNMP pipeline generation.
  - Discovery behavior and limitations.
  - Undeployed-change workflows.
  - SNMP trap support.
  - Simulation and test data.
  - Logstash Agent compatibility.
  - Deployment-mode differences.
  - Embedded Docker Compose deployments.
  - Building and running LogstashUI from source.
  - AI Device Onboarding.
  - Inline AI grounding.
  - Contributing device walks and official profiles.
- Added automated tests for SNMP CRUD operations, views, synchronization commands, AI onboarding, normalizers, and discovery walks.
- Added regression tests for scope-qualified normalizer filter IDs.
- Added the required license attribution for Marked.js.

### Changed

- Changed SNMP pipeline generation to generate and reconcile pipelines by device template rather than by every profile combination.
- Overhauled SNMP pipeline generation and reconciliation for significantly larger deployments.
- Changed generated enrichment to operate at the device-template level.
- Changed the default SNMP polling interval from 30 seconds to 60 seconds.
- Changed `event.kind` usage to `event.category`.
- Changed `host.description` to `observer.sys_descr` to align with the Kibana network map schema.
- Added `host.type` enrichment from the assigned device template.
- Added `observer.vendor` enrichment from device profiles.
- Updated the SNMP schema to better align with gNMI field conventions.
- Normalized field names across official SNMP profiles and templates.
- Normalized the generic host-system metrics profile.
- Updated generic host-system metrics to detect and normalize available memory metrics.
- Updated table unpacking to use dot-separated table names.
- Changed generated table names so they use the actual table name rather than always being prefixed with `table`.
- Removed the former special-case filter generator after replacing its behavior with configurable normalization.
- Restricted the remaining Ruby filter generation helper to table-splitting behavior.
- Updated ratio normalization to support ordinary division and table rows.
- Scope-qualified multiply and ratio normalizer filter IDs to prevent collisions.
- Updated template and profile synchronization to clean up obsolete official files.
- Moved official SNMP synchronization helpers into a dedicated location.
- Updated discovery to query only SNMP connections currently used by relevant networks.
- Changed discovery behavior to better support devices configured with hostnames rather than IP addresses.
- Updated device identity handling to distinguish:
  - User-assigned names.
  - Discovered system names.
  - DNS names.
  - IP addresses.
- Added IP detection so valid addresses are populated into `host.ip`.
- Updated the network map architecture and made network-map nodes interactive.
- Updated the network-map index used by SNMP views.
- Replaced the device-quality table with a device-template coverage matrix.
- Updated interface health colors:
  - Green for healthy.
  - Yellow for warning.
  - Red for critical.
  - Gray for unknown or administratively down.
- Updated SNMP metric visuals after schema and normalization changes.
- Updated template and profile image sizing.
- Removed the arbitrary Logstash node name from network configuration.
- Removed the Created column from device and credential tables.
- Changed credential loading from server-side rendering to asynchronous JavaScript loading.
- Changed related-object dropdowns to refresh automatically after objects are created in nested modals.
- Removed manual refresh buttons from supported CRUD selectors.
- Changed the plugin configuration search bar so it is visually distinct from configuration fields.
- Standardized SNMP device and network modal inputs.
- Changed the device-template selector to display formatted names and images instead of raw object values.
- Changed the SNMP Devices navigation indicator so it stops pulsing after the user visits the page.
- Updated context processors so the SNMP Devices page only pulses when attention is actually required.
- Updated the Device Wizard template-generation path to remain within the onboarding workflow.
- Changed the AI generation button to clearly indicate unavailable or upcoming functionality where appropriate.
- Replaced the former instruction modal with direct links to documentation.
- Updated deployment progress messaging so smaller deployments no longer warn that they may take several minutes.
- Updated the SNMP walk warning to be more direct.
- Added `system.location` and `system.contact` to the generic system profile.
- Updated Ubiquiti access point uptime polling.
- Removed deprecated profile interfaces and duplicated onboarding functionality.
- Consolidated duplicate `escapeHtml` implementations into the shared base JavaScript module.
- Removed orphaned functions, deprecated helpers, and duplicated code.
- Replaced remaining `print` statements with structured logger calls.
- Added missing administrator authorization checks to SNMP CRUD operations.
- Updated feature gating for SNMP, Centralized Pipeline Management, and traditional Logstash deployment modes.
- Updated the Logstash Agent installation validation to support Logstash installations built or run from source.
- Added jitter to Logstash Agent polling timers.
- Updated Logstash Agent documentation and deployment guidance.
- Updated source-build documentation and minimum system requirements.
- Updated compatibility assets for Logstash 9.4.
- Updated the LogstashUI introductory workshop for the NMS release.
- Improved general UI text, spacing, formatting, and consistency throughout the SNMP application.

### Fixed

- Fixed undeployed-change indicators not clearing after a successful deployment.
- Fixed undeployed-change indicators not appearing or updating correctly after CRUD operations.
- Fixed some network, profile, and template operations failing to trigger the deploy-changes animation.
- Fixed orphaned discovery-pipeline detection overlapping with pipeline deletion.
- Fixed empty discovery-enabled networks not generating discovery pipelines.
- Fixed stale and orphaned generated pipelines not being reconciled correctly.
- Fixed collisions between generated normalizer IDs.
- Fixed multiply and ratio normalizer filter IDs colliding across scopes.
- Fixed AI-authored and user-authored normalizers being dropped during onboarding and pipeline generation.
- Fixed generated profiles losing normalizer configuration.
- Fixed device templates being left empty after a template was deleted.
- Fixed devices without an assigned template by automatically assigning the `Default` template.
- Fixed device-template profile selectors displaying database IDs instead of readable profile names.
- Fixed device-template names being formatted incorrectly in device configuration workflows.
- Fixed official profile and template synchronization issues on Windows.
- Fixed data consistency problems in SNMP profile and template synchronization commands.
- Fixed the renamed `sysDescr` field breaking generated output.
- Fixed missing SNMP metadata in generated `add_field` configuration.
- Fixed Cisco IOS profile metrics that were using an incorrect index.
- Fixed Ubiquiti access point normalizers conflicting with unrelated fields.
- Fixed access point uptime polling using the wrong metric.
- Fixed an orphaned component table in the entity-sensor profile.
- Fixed table normalizers failing to calculate averages correctly.
- Fixed commented fields containing hash values being parsed as active configuration.
- Fixed inline comments containing `{` or `}` causing pipeline-parser errors.
- Fixed plugin comments being discarded instead of preserved.
- Fixed regular expressions in conditions being rejected by the pipeline AST.
- Fixed large text inputs being difficult to inspect and edit.
- Fixed modal input and select controls closing immediately after being clicked.
- Fixed a credentials-table JavaScript error caused by a missing closing brace.
- Fixed credential selectors and CRUD dropdowns failing to update after new objects were created.
- Fixed SNMP tests presenting ambiguous failures for credential errors and timeouts.
- Fixed discovery querying every configured connection instead of only relevant SNMP connections.
- Fixed hostname-based devices being handled incorrectly during discovery.
- Fixed the SNMP Devices page continuing to pulse after it had been visited.
- Fixed the network map using the wrong backing index.
- Fixed network-map rendering after schema changes.
- Fixed fresh installations failing when the last-seen timestamp was null.
- Fixed device and network views exposing inconsistent or incomplete names.
- Fixed missing migrations associated with new SNMP templates, profiles, namespaces, and Logstash Agent functionality.
- Fixed generated device onboarding failing when an approved object reused an existing name.
- Fixed AI discovery walks skipping columns and producing incomplete grounding data.
- Fixed incorrect interactions and state synchronization between LogstashUI and Logstash Agent.
- Fixed Logstash Agent process information being presented as though it were the Logstash process.
- Fixed missing RBAC protection across SNMP administrative operations.
- Fixed installation-asset actions, loading indicators, and cleanup behavior in AI template and profile generation.
- Fixed various SNMP CRUD, rendering, deployment, and code-quality issues discovered during final release testing.



## [0.4.3] - AI Foundation, Simulation Improvements, and SNMP Fixes - 06/07/2026

### Added

- Added an Elastic Serverless indicator after successfully testing a connection.
- Added foundational support for AI agents.
- Added Integration Factory as an experimental feature.
- Added system architecture documentation and linked it from the README.

### Changed

- Updated simulation mode to use port `9650` instead of `9600` to avoid conflicts with Logstash monitoring APIs.
- Normalized language around simulation nodes in the pipeline editor.
- Updated condition editing controls so they appear as clear edit buttons instead of inline pencil icons in both graph and inline modes.
- Updated Integration Factory so it only uses connections configured with Cloud IDs.

### Fixed

- Fixed an issue where simulated document batches could incorrectly show the “no plugins executed” banner for all documents when only a single document returned no results.
- Fixed an issue where simulation continued searching for results after the final document response had already been received.
- Fixed the walk profile caution message so it appears again when rows are added to a walk profile.
- Fixed generated SNMP pipelines so they include the port when connections do not use a Cloud ID, preventing incorrect default port behavior.
- Added additional simulation-mode agent logging to help diagnose agent issues.

## [0.4.2] - SNMP Expansion, Settings, and AI Foundation - 05/14/2026

### Added

- Added global settings support with an initial Experimental Mode setting.
- Added the initial AI / chat app foundation.
- Added the ability to test an SNMP connection and device template directly from the SNMP UI.
- Added an SNMP overview page with initial KPI cards, visualizations, queries, and network summary data.
- Added a CDP-based network map for SNMP adjacency visualization.
- Added CDP adjacency data to the SNMP data quality table.
- Added an agent view to the policy page in preparation for feature flags.
- Added Logstash node visibility to agent policies.
- Added a deploy button glow when there are undeployed changes.
- Added support for cloning SNMP-related objects.
- Added interfaces as a core field in the device data quality check.
- Added `sysObjectID` to the generic system profile.
- Added an Epson device template.
- Added automatic SNMP profile / template detection.
- Added device template assignment suggestions based on detected device metadata such as `sysDescr`.
- Added template suggestion context, including name, description, vendor, family/type, model, matching field, official status, and associated profiles.
- Added handling for cases where no strong device template match is available.
- Added hover descriptions and explanatory text across SNMP CRUD pages.
- Added dedicated SNMP setup documentation and linked to it from the SNMP UI.

### Changed

- Incremented the version number to `0.4.2`.
- Renamed SNMP “Commit Changes” language to “Deploy Changes” for clearer deployment semantics.
- Reduced the discovery modal to show devices seen in the last 10 minutes instead of the last 2 hours.
- Normalized SNMP “Add” button sizing across pages.
- Overhauled the SNMP profile page and removed/changed older pinning behavior.
- Updated SNMP CRUD pages so creating, updating, and deleting values no longer requires a full page reload.
- Replaced the offline symbol with a loading spinner while device information is being fetched from Elasticsearch.
- Added last successful poll / last seen visibility for SNMP devices.
- Added a startup / management sync process for official SNMP profiles instead of re-syncing profiles on page load.
- Updated official SNMP profile sync behavior to remove unused official profiles that are no longer present in the official profile set.
- Replaced the old profile-to-device relationship model with the newer profile-to-template relationship model.
- Removed deprecated profile-to-device junction table usage.
- Moved inline HTML CSS into dedicated CSS files where Tailwind could not be used.
- Moved “Click here for setup instructions” content into a dedicated documentation page and updated the UI to reference that page.
- Added top-of-page explanatory text to SNMP pages describing what each component does and linking to relevant documentation.

### Fixed

- Fixed SNMP connection modal styling on SNMP pages.
- Fixed broken documentation app link rewriting.
- Updated documentation compatibility details for Elastic / Logstash `8.x` and `9.x`.
- Improved SNMP template matching behavior, including tie-breaker handling for competing matches.

### Documentation

- Updated in-app SNMP setup instructions.
- Added SNMP setup documentation.
- Added compatibility documentation for `8.x` and `9.x`.
- Added contextual descriptions for SNMP CRUD pages and linked related docs from the UI.

## [0.4.1] - Post 0.4.0 Polish - 04/20/2026

### Added

- Added an undeployed-changes indicator across SNMP-related pages to make pending SNMP changes more visible.
- Added goto input and goto output navigation buttons in the graph editor.
- Added a global scroll-to-top control that appears after scrolling far enough down a page.
- Added support for closing modals globally by pressing `Esc`.
- Added a `CONTRIBUTING.md` guide for project contributors.

### Changed

- Replaced browser-native confirmation and dialog boxes with the application's native popup experience.
- Centralized toast handling in `base.js` and removed older SNMP-specific `showToast` usage.
- Improved documentation structure and organization to make it easier to navigate.
- Updated automation for generating NOTICE content and license headers.
- Removed concurrent rotating file handlers to avoid ongoing complexity from an inconvenient transitive dependency.

### Fixed

- Fixed Docker packaging so the `/docs/` directory is copied into the image and the in-app documentation feature works as expected.

## [0.4.0] - Logstash Agent - 04/18/2026

### Added

- Added centralized Logstash Agent management, including policy creation, enrollment, and agent-aware connection workflows.
- Added support for managing pipelines through Logstash Agent, including pipeline settings and policy-level pipeline organization.
- Added keystore management improvements, including password management, clearer visibility into sensitive fields, and support for deploying keystore-related changes independently.
- Added agent operational controls such as restart support, upgrade support, health reporting, and richer status details.
- Added live status and log streaming improvements to make troubleshooting and monitoring easier.
- Added validation to help catch missing Logstash installations, invalid paths, and other configuration issues earlier.
- Added clearer deployment feedback, including indicators for undeployed changes and warnings for situations that require special handling.
- Added an in-app documentation experience.
- Added expanded automated testing and coverage reporting.

### Changed

- Improved the overall Logstash Agent experience across enrollment, policy management, deployment workflows, and health visibility.
- Improved the safety of deployments so failed changes are handled more cleanly and unnecessary restarts are reduced.
- Improved the UI across connection management, policy views, agent health/status displays, and navigation.
- Improved security for communication between LogstashUI and Logstash Agent.
- Reworked packaging and project structure to support the ongoing evolution of Logstash Agent.
- Moved documentation into the application for a more integrated user experience.
- Updated SNMP-related UI flows and made minor usability improvements.

### Fixed

- Fixed navigation state so collapsed navigation sections now persist more reliably.
- Fixed several deployment and keystore edge cases that could cause failed or blocked changes.
- Fixed pipeline change detection issues so edits are recognized more reliably.
- Fixed agent status and health display issues.
- Fixed several policy, pipeline, and configuration UI bugs.
- Fixed monitoring behavior to better align with centralized connection workflows.
- Fixed documentation image/link issues.
- Fixed a number of packaging, path, logging, and platform-specific issues introduced during refactoring.


## [0.3.5] - 03/23/2026
### Changed
- Disabled light mode entirely


## [0.3.4] - 03/17/2026
### Changed
- Quick fix to make simulation of dropped messages work universally

## [0.3.3] - 03/17/2026

### Added
- Converted delete alerts/confirmation boxes to use stylized popup components  
- Saving a pipeline now shows a toast notification instead of shifting UI elements  

### Changed
- Pipeline manager table now displays hostname when a node is added via URL instead of Cloud ID  
- Defaulted `logstashagent.yml` to Linux configuration  

### Fixed
- Improved handling of messages sent to pipelines that never loaded  
- Fixed pipeline eviction issue caused by runtime config not being properly detected  

## [0.3.2] - 03/16/2026
### Changed
Fixed elastic host connection string

## [0.3.1] - 03/16/2026

### Added
Added a search bar to the top of the plugin config modal

### Changed
Allow unverified elastic connections
Swapped a javascript alert for our popup box (styled it)

### Fixed
Fixed minor visual line bugs in the graph

## [0.3.0] - 03/16/2026

### Added
- Host mode for Windows and Linux with environment variable preservation
- Log files for LogstashAgent
- Scripts for Linux host mode
- Runtime configuration (replaces build-time config)
- Startup scripts that force shutdown first and manage a `.venv` file
- Graph view in the Pipeline Editor with recursive nested condition support
- Custom popup/modal to replace native browser alerts, matching app theme
- Ability to validate pipelines on click
- Stats strip in the Pipeline Editor
- User preference persistence for last-used editor mode (text vs. graph)
- Toggle in text mode to suppress mode-switch confirmation popup
- Regression tests for Common, Management, Monitoring, PipelineManager, Site, SNMP, and Utilities
- `popup.html` for themed in-app alerts
- GitAttributes file to prevent line ending changes on commit

### Changed
- Default simulation mode is now `embedded`
- ElasticAgent simulation node now listens on localhost only instead of all interfaces
- Logstash supervisor tuned to be more aggressive on restarts and better handle large pipeline simulations
- Startup scripts now activate and manage a `.venv` instead of installing dependencies directly
- Reworked Pipeline Editor top bar UI — more responsive and reactive
- Updated Dockerfile and Docker Compose to support server, development, and Docker Compose modes
- Renamed and reorganized docs
- Text editor behavior now consistent when switching between text and graph modes
- Default YML config example reset to clean state

### Fixed
- Linux host mode permissions and file permission quirks
- Database not persisting due to path mismatch
- Stop script now more reliably terminates the agent
- Testing config now works with the supplied binary instead of hardcoded Linux path
- Windows Server limitations documented for host mode
- Drop return path for pipelines

## [0.2.1] - 03/05/2026

### Added
- Documentation links inside the plugin configuration modal
- Initial implementation of a visual expression editor (foundation for future condition builder)
- Ability to load Logstash plugin documentation directly within LogstashUI
- Label showing the slowest plugin during pipeline simulation
- Icons for filter plugins in the pipeline editor
- Search bar and pagination for Connection Manager
- `pipeline_list.js` for improved pipeline UI behavior

### Changed
- Tuned Logstash performance and stability
- Reduced the number of generated Ruby scripts created during pipeline editing
- Updated Logstash API polling behavior to be less aggressive
- Updated eviction algorithm to reduce unnecessary cache churn
- Simulation overlay now dims the interface while results are loading to prevent interaction

### Fixed
- Eliminated or significantly mitigated a Logstash memory leak caused by cached Ruby plugins
- Added a shared connection pool to prevent opening a new Logstash API connection for every request
- Removed temporary pipeline file writes during simulation
- Fixed missing return statement that caused unexpected behavior
- Simulation timeline now ignores comments
- Updated tests to reflect LogstashAgent pipeline status behavior changes

## [0.2.0] - 03/02/2026

### Added
- Toggle button for simulation that turns on/off simulation metadata
- Simulate now shows time in ms of plugin and entire execution
- Visual indicator of parsing failure / tag on failure in simulate
- Popular plugins float to the top of the plugin selector page
- Added `fs_path` type
- Added file upload for simulate when a pipeline requires it
- Comments are now supported
- Pipelines are now tested every time plugins are added/changed/removed
- Warning badge (!) appears on plugins with missing required fields
- Copy button in simulation result tooltips to copy JSON data to clipboard
- SNMP discovery workflows (tested end-to-end: discovery → device → scheduled monitoring)
- Initial implementation of the pipeline text editor
- Autocomplete, improved bracket matching, and syntax highlighting in the text editor
- Visual indicators when conditions are empty
- Save button is blocked when required fields or conditions are invalid
- SNMP test coverage improvements
- SDK-like script for interacting with the Logstash API (replaces older log analyzer)
- “Memory intensive” plugin flag with visual indicator
- `key_list_hash` type to ensure consistent grok match ordering
- Additional SNMP profiles (new + tuned existing)
- Added traps file (and related `.gitignore` updates)
- Favicon

### Changed
- Colorized the "after" JSON output for clearer visibility into changes
- Overhauled plugin configuration modal for improved usability
- View Full Event and Original Event in simulate are now more clearly clickable
- Default condition is now `if [message]`
- Migrated to Gunicorn (removed runserver + eliminated unnecessary logstashagent port)
- Updated Docker Compose configuration for 0.2.0
- Updated Nginx configuration to resolve Docker Compose issues
- Refreshed `collectstatic` workflow and removed tracking of staticfiles
- Moved pipeline renaming functionality to common module for reuse
- Adjusted Logstash configuration to optimize performance
- Simulation API endpoints now route through ConnectionManager
- Hardened and cleaned up ConnectionManager (including model updates and removal of SSH references)
- Monitoring overhaul with additional tests and refreshed static assets
- Error page overhaul and removal of public CDN calls
- Standardized on a single visualization engine
- Removed legacy Core/API layer and distributed functionality into appropriate apps
- Refactored Ruby code injection to standardize quoting and reduce escaping issues
- Cleaned up legacy JavaScript and consolidated shared utilities into `base.js`

### Fixed
- Drops no longer time out in the simulation feature
- Chevron icon when expanding advanced options in pipeline settings
- Null list values no longer insert the string `"null"` into configs
- Simulation no longer hangs when events don't match conditions (proper message shown)
- Logs no longer appear in the wrong pipeline slot
- Fixed bug when adding Elastic connections via URL after moving away from HTML-returning views
- Fixed regression with hovering over edges in the UI
- Fixed JavaScript bug using `json.dumps` instead of `JSON.stringify`
- Inline comments inside plugins no longer break parsing (inline comments are stripped to preserve round-trip stability)
- Fixed pipeline hashing issues affecting configuration load progress
- Fixed SNMP timeout/retry settings not being applied to generated configs
- Fixed profile caching confusion when pipelines were updated
- Fixed interface hover UI positioning
- Fixed incorrect pipeline count in commit toast
- Fixed bug caused by renaming SNMP data streams
- Simulation now detects success faster and gives pipelines sufficient time to complete
- Fixed race condition when simulating file-dependent plugins
- Fixed simulation file-path handling (user file paths are no longer modified)
- Updated bug report links to correct targets

## [0.1.11-12] - 02/12/2026
### Added
- Instrumented pipeline simulation
- LogstashAgent
- Containerized Logstash

## [0.1.10] - 02/12/2026
### Added
- Tests for all APIs
- User tracking for all CRUD operations
- Logging for all APIs
- CHANGELOG.md!
- Log viewer / exporter
- Clone pipeline functionality
- Added a readonly user and verification for all create/read/delete operations
- Added a cookie session age so that users aren't permanently logged in

### Changed
- Removed commented out function for simulating pipelines, will implement later
- Updated license dates
- Made the showToast function in javascript global and removed duplicated references to it in templates
- Removed CSRF_EXEMPT library because we're not using it anymore

### Fixed
- Missing grok-patterns file, preventing autocomplete in grok debugger from working
- Fixed user CRUD tests to work with new changes
