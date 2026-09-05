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

## Embedded agent (optional)

Same role as compose `--profile embedded`: an in-cluster LogstashAgent for the pipeline editor Sim target (`embedded · docker`). No enroll. Lab only — prefer an enrolled Simulate agent for serious work.

1. Apply **one** DB tree above.
2. Set `LOGSTASHUI_AGENT_CSR_SECRET` in its Secret. DO NOT use the secret default.
3. Apply the overlay:

```bash
kubectl apply -f docs/docs/logstashui/kubernetes/examples/embedded-agent.yaml
```

`Service/logstashagent` is ClusterIP **9500** (agent API), **9560** (Logstash API), **9449** (HTTP input). Nothing is published outside the cluster. Image: `codyjackson032/logstash-agent:latest`.

If the CSR secret key is still commented, the agent pod is `CreateContainerConfigError` until you uncomment it.

Agent ConfigMap `logstashagent` already sets `LOGSTASH_UI_URL` / `LOGSTASH_URL` to `https://logstashui:8443`. Two extra keys are **commented** (LogstashAgent env, not UI):

| Env | Default | Do not enable without cause |
|---|---|---|
| `LOGSTASH_AGENT_TLS` | `true` | Uncomment `"false"` only with `LOGSTASHUI_INSECURE_HTTP` and `http://` URLs. Serves the agent API over HTTP. |
| `LOGSTASH_UI_TLS_INSECURE` | `false` | Uncomment `"true"` to skip verifying the UI HTTPS cert. Not the same as plain HTTP. Product CA pinning works out of the box. |

See the LogstashAgent README TLS table. Standard examples stay HTTPS.
