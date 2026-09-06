# Migrating the database

Two paths copy **SQLite** data onto PostgreSQL or MySQL/MariaDB. Both require a **stopped** UI so nothing writes during dump. Keep `$LOGSTASHUI_DATA_DIR` (same Django secret key) or encrypted keystore rows will not decrypt. Sessions are not copied; log in again.

Create the empty target first ([examples](examples/)). MySQL/MariaDB: `utf8mb4` / `utf8mb4_bin`. Native installs need `LogstashUI[postgres]` or `LogstashUI[mysql]`. The container image already has both drivers.

BETA `migrate-engine` is **not atomic** on the target: `dumpdata` → `migrate` → `loaddata` is three steps. If `loaddata` fails, drop or recreate the target and re-run. SQLite is only WAL-checkpointed.

---

## Offline dump / load (supported)

Do this while `LOGSTASHUI_DB_ENGINE` is still sqlite (or unset). If you point env at the empty server first, `dumpdata` dumps the empty server.

1. Stop the UI.
   - systemd: `sudo systemctl stop logstashui` (avoid `Restart=` racing SIGTERM).
   - Docker: stop the container (`docker compose stop logstashui`).
   - Kubernetes: `kubectl -n logstashui scale statefulset/logstashui --replicas=0` and wait for the pod to disappear.
2. Copy `$LOGSTASHUI_DATA_DIR/db.sqlite3` (and `-wal` / `-shm` if present) somewhere safe. Keep the rest of `DATA_DIR`.
3. Dump from SQLite:

   ```bash
   logstashui manage dumpdata --natural-foreign --natural-primary \
     -e contenttypes -e auth.permission -e sessions \
     -o dump.json
   ```

   In a container: `docker exec -it <ui> logstashui manage dumpdata ...` **before** changing env, or exec with `LOGSTASHUI_DB_ENGINE=sqlite` and `LOGSTASHUI_DB_NAME` pointing at the sqlite file.

4. Create the server database (`utf8mb4_bin` on MySQL/MariaDB).
5. Set `LOGSTASHUI_DB_*` for the target (`ENGINE`, `HOST`, `PORT`, `NAME`, `USER`, `PASSWORD`, plus `SSLMODE` / `SSL_CA` as needed).
6. Schema + load:

   ```bash
   logstashui manage migrate --noinput
   logstashui manage loaddata dump.json
   ```

7. Postgres sequences: this path does **not** reset them. Use BETA `migrate-engine` if you need `sequence_reset_sql` without a `psql` client. Django will still insert; sequences can drift until reset.
8. Start LogstashUI. Log in again.

Kubernetes after env change: patch ConfigMap/Secret, then `scale --replicas=1` (or delete the pod). First start runs `migrate` again (no-op if already applied) — **loaddata is not automatic**. Run loaddata from a one-shot `kubectl exec` after migrate, or run steps 6–7 from a job with the same env and a copy of `dump.json`.

---

## BETA CLI

```bash
# Target LOGSTASHUI_DB_* already set; sqlite file still in DATA_DIR
sudo systemctl stop logstashui
logstashui migrate-engine --to postgresql --i-have-a-backup
# --to mysql | --to mariadb   (mariadb is an alias of mysql)
# --write-env /etc/default/logstashui   # upserts engine/host/name/user; never password
sudo systemctl start logstashui
```

`--i-have-a-backup` is required.

The command:

1. SIGTERMs gunicorn if `$LOGSTASHUI_DATA_DIR/gunicorn.pid` is live (does not restart serve).
2. WAL checkpoint on the sqlite file in `DATA_DIR`.
3. `dumpdata` from that sqlite file (ignores target `LOGSTASHUI_DB_*` for the dump).
4. `migrate --noinput` on the target, then `loaddata`.
5. PostgreSQL: `sequence_reset_sql` through the Django connection (no `psql`).

Kubernetes: scale to 0, `kubectl exec` is the wrong place if the pod is gone. Run `migrate-engine` from a debug pod / CI job that mounts the same PVC (`DATA_DIR`) and has target `LOGSTASHUI_DB_*`. Then scale to 1.

If `loaddata` fails: drop or recreate the **target** database and re-run. Do not restore SQLite unless you also lost the backup.

---

## What is not copied

`contenttypes`, `auth.permission`, and `sessions` are excluded from dump/load. Permissions recreate on migrate. Sessions mean everyone logs in again.
