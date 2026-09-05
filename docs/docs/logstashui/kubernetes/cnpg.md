# CloudNativePG

Use this when a [CloudNativePG](https://cloudnative-pg.io/) operator is already installed (commonly in namespace `cnpg-system`). Create the Postgres **Cluster in the LogstashUI namespace**. LogstashUI talks to the Cluster's read-write Service; it does not talk to the operator.

PostgreSQL **14+** is required (16 is a good default). The container image already has `psycopg`.

A sample Cluster is in [examples/postgresql/cnpg.yaml](examples/postgresql/cnpg.yaml).

---

## Cluster

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: logstashui-pg
  namespace: logstashui
spec:
  instances: 1          # 3 for HA
  imageName: ghcr.io/cloudnative-pg/postgresql:16
  bootstrap:
    initdb:
      database: logstashui
      owner: logstashui
      encoding: UTF8
  storage:
    size: 10Gi
```

Do **not** put Django `CREATE TABLE` in `postInitApplicationSQL`. `logstashui serve` runs `migrate` on first start.

Wait until Ready:

```bash
kubectl -n logstashui wait --for=condition=Ready cluster/logstashui-pg --timeout=300s
```

---

## Connection (what CNPG creates)

| Object | Purpose |
|---|---|
| Service `logstashui-pg-rw` | Primary, port 5432 |
| Secret `logstashui-pg-app` | `host`, `port`, `dbname`, `username`, `password`, `uri` |
| Secret `logstashui-pg-ca` | Cluster CA (`ca.crt`) if you want `verify-full` |

Wire LogstashUI from that Secret (do not copy the password into your own Secret):

```yaml
env:
  - name: LOGSTASHUI_DB_ENGINE
    value: postgresql
  - name: LOGSTASHUI_DB_SSLMODE
    value: require
  - name: LOGSTASHUI_DB_HOST
    valueFrom:
      secretKeyRef:
        name: logstashui-pg-app
        key: host
  - name: LOGSTASHUI_DB_PORT
    valueFrom:
      secretKeyRef:
        name: logstashui-pg-app
        key: port
  - name: LOGSTASHUI_DB_NAME
    valueFrom:
      secretKeyRef:
        name: logstashui-pg-app
        key: dbname
  - name: LOGSTASHUI_DB_USER
    valueFrom:
      secretKeyRef:
        name: logstashui-pg-app
        key: username
  - name: LOGSTASHUI_DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: logstashui-pg-app
        key: password
```

`require` is enough for CNPG's server TLS. For `verify-full`, mount `logstashui-pg-ca` `ca.crt` and set `LOGSTASHUI_DB_SSL_CA` to that path.

Keep `LOGSTASHUI_DATA_DIR` on a PVC (TLS and secrets). An init container can `pg_isready -h logstashui-pg-rw` before the UI starts.

---

## Existing Cluster in another namespace

Point `LOGSTASHUI_DB_HOST` at that Cluster's `-rw` Service FQDN (`<name>-rw.<ns>.svc.cluster.local`). Copy or ExternalSecret the app password into `logstashui`. NetworkPolicy must allow 5432 from the UI pods.

---

## SQLite → CNPG

Create the Cluster and empty database, set `LOGSTASHUI_DB_*`, then follow [migration](/docs/docs/logstashui/database/migration.md). Do not `loaddata` until `migrate` has created tables.
