# LogstashUI air-gapped Docker image (__VERSION__)

Linux **x86_64** image tarball. No registry. The image already includes `LogstashUI[databases]` and `LogstashUI[otel]`. Tracing stays off until `LOGSTASHUI_OTEL=true`. There is **no** LogstashAgent in this zip.

## Load and run

```sh
./load.sh
docker compose -f compose.offline.yml up -d
```

`load.sh` never pulls. HTTPS UI is **:8443**. Named volume `logstashui_data` is `LOGSTASHUI_DATA_DIR=/var/lib/logstashui`. Keep `LOGSTASHUI_TLS` on.

Set `ALLOWED_HOSTS`, `LOGSTASHUI_HOST_*`, and `LOGSTASHUI_DB_*` in the environment or a `.env` next to `compose.offline.yml` as needed.

Git: `__GIT_SHA__`
