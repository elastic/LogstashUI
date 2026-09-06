# Kubernetes

Run LogstashUI as a one-replica StatefulSet. The container image is `codyjackson032/logstashui:latest` (or a tag you built). Configuration is environment variables only — ConfigMap for non-secrets, Secret for `SECRET_KEY` and `LOGSTASHUI_DB_PASSWORD`.

Copy-paste manifests:

- [SQLite](examples/sqlite/) — database file on the data PVC (fine for a single replica; not for concurrent agents)
- [PostgreSQL](examples/postgresql/) — external Postgres 14+, optional [CloudNativePG](cnpg.md)
- [MySQL / MariaDB](examples/mysql/) — one engine (`mysql`); create the database as `utf8mb4` / `utf8mb4_bin`

Envoy Gateway users: [skip backend TLS verify](envoy-gateway.md) (`Backend` CR). Ingress-nginx users: see the `ingress.yaml` in each examples folder.

---

## Image and command

The image already installs `LogstashUI[databases]` and `LogstashUI[otel]`. Tracing stays off until `LOGSTASHUI_OTEL=true`. `CMD` is `logstashui serve`. Do not override the command unless you are debugging.

```bash
docker build -f docker/Dockerfile -t logstashui:0.5.2-dev .
# Apple Silicon → amd64 cluster:
docker build --platform linux/amd64 -f docker/Dockerfile -t logstashui:0.5.2-dev .
```

Build context is the **repository root**.

---

## Data directory (required)

Set `LOGSTASHUI_DATA_DIR=/var/lib/logstashui` and mount a PVC there. The PVC holds TLS (`tls/`), the Django secret file, logs, `staticfiles/`, and (SQLite only) `db.sqlite3`. Keep the PVC when the database is Postgres or MySQL — it is not optional.

Use **one** `volumeClaimTemplate` named `data`. Splitting logs onto a second claim is not useful: `LOGSTASHUI_LOGS_DIR` still lives under `DATA_DIR` unless you override it, and TLS/secrets cannot move.

**Replicas: 1.** LogstashUI is not horizontally scalable (product CA, gunicorn pidfile, SQLite).

---

## Security context

Image user is **appuser (uid/gid 10001)**. The entrypoint chowns `DATA_DIR` only when it is root. Kubernetes should not run the container as root:

```yaml
spec:
  template:
    spec:
      securityContext:
        fsGroup: 10001
        fsGroupChangePolicy: OnRootMismatch
      containers:
        - name: logstashui
          securityContext:
            runAsUser: 10001
            runAsGroup: 10001
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
```

---

## TLS (keep it on)

Leave `LOGSTASHUI_TLS` unset or `true`. Gunicorn serves HTTPS on **8443** with the product CA under `$LOGSTASHUI_DATA_DIR/tls/`. Do **not** set `LOGSTASHUI_TLS=false` for an ingress or HTTPRoute.

The gateway or Ingress **originates HTTPS** to the pod and **skips backend certificate verification** because the product leaf is self-signed:

- Ingress-nginx: `backend-protocol: HTTPS` and `proxy-ssl-verify: "off"` (see examples)
- Envoy Gateway: [`Backend` with `tls.insecureSkipVerify: true`](envoy-gateway.md)

Set `CSRF_TRUSTED_ORIGINS` and `ALLOWED_HOSTS` to the public hostname (keep `logstashui` in `ALLOWED_HOSTS`). `LOGSTASHUI_TLS_SANS` / `LOGSTASHUI_HOST_HOSTNAME` add that name to the product leaf. `LOGSTASHUI_AGENT_UI_URL` is the URL agents should use.

Inject the pod IP so the product leaf SAN matches Kubernetes (compose does this with `LOGSTASHUI_HOST_IPS` on the host; the UDP-to-8.8.8.8 trick often has no egress in a cluster):

```yaml
env:
  - name: LOGSTASHUI_HOST_IPS
    valueFrom:
      fieldRef:
        fieldPath: status.podIP
```

Django also appends `LOGSTASHUI_HOST_IPS` / `POD_IP` to `ALLOWED_HOSTS` unless that list is `*`.

Probes: `httpGet` `scheme: HTTPS` on port 8443. kubelet does not verify the pod certificate, but it **does** send `Host: <podIP>:8443`. Set the probe Host to a name already in `ALLOWED_HOSTS` (examples use `logstashui`):

```yaml
httpGet:
  path: /
  port: https
  scheme: HTTPS
  httpHeaders:
    - name: Host
      value: logstashui
```

---

## Database

Default engine is SQLite on the PVC. For Postgres or MySQL/MariaDB, set the discrete `LOGSTASHUI_DB_*` keys — see [Database](/docs/docs/logstashui/database/index.md). Put the password in a Secret. CloudNativePG: [CNPG](cnpg.md).

---

## Embedded agent (optional)

This uses the embedded agent image [embedded-agent.yaml](examples/embedded-agent.yaml). Apply a DB tree, set `LOGSTASHUI_AGENT_CSR_SECRET`, then apply the overlay. ClusterIP only (`9500` / `9560` / `9449`). Details: [examples README](examples/README.md#embedded-agent-optional).

---

## Apply (generic)

```bash
kubectl apply -f docs/docs/logstashui/kubernetes/examples/sqlite/
# or postgresql/ or mysql/
# optional embedded sim node:
# kubectl apply -f docs/docs/logstashui/kubernetes/examples/embedded-agent.yaml
```

Replace `logstashui.example.com` in ConfigMap, Secret, and Ingress. Replace `SECRET_KEY`. For Postgres/MySQL, create the empty database first ([SQL examples](/docs/docs/logstashui/database/examples/)), then apply the StatefulSet. First start runs `migrate`.
