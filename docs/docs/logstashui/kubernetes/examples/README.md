# Example manifests

Apply **one** tree. All of them keep LogstashUI TLS on (`:8443`) and use Ingress-nginx with `backend-protocol: HTTPS` and `proxy-ssl-verify: "off"`. Image: `codyjackson032/logstashui:latest`. Namespace: `logstashui`. Replicas: **1**. One PVC at `/var/lib/logstashui`.

| Directory | Database |
|---|---|
| [sqlite/](sqlite/) | SQLite file on the data PVC. Simplest. Not for concurrent agents. |
| [postgresql/](postgresql/) | External PostgreSQL 14+. Optional [cnpg.yaml](postgresql/cnpg.yaml) if you run CloudNativePG. |
| [mysql/](mysql/) | MariaDB 10.6+ or MySQL 8.0+. Engine is `mysql`. Create the schema as `utf8mb4` / `utf8mb4_bin`. |

Replace `logstashui.example.com` and `SECRET_KEY` before apply. For Postgres/MySQL, create the empty database first — [SQL examples](/docs/docs/logstashui/database/examples/).

Envoy Gateway instead of Ingress: [envoy-gateway.md](../envoy-gateway.md) (enable the Backend API, then `Backend` + `HTTPRoute`).

```bash
kubectl apply -f docs/docs/logstashui/kubernetes/examples/sqlite/
```
