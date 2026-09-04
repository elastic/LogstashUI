# Logstash Tarball Proxy

A `MANAGED` or `SIMULATE` policy pinned to **VERSION** makes every agent download its own copy of
the Logstash release tarball — roughly 450 MB each. At two agents that is wasteful; at fifty it is a
bandwidth event, and in an air-gapped site it is impossible.

With the proxy enabled, LogstashUI fetches each release **once**, verifies its SHA-512, and serves it
to every agent that needs it.

## Enabling it

1. **Cache the tarball.** Management → **Logstash Tarballs** → *Download Tarball*. Pick a version and
   architecture, or paste a full URL for an internal mirror.
2. **Point the policy at LogstashUI.** In the policy editor, set the Logstash source to **VERSION**,
   enter the version, and tick **Download the tarball from LogstashUI**.

The checkbox only appears for **Managed** and **Simulate** policies using **VERSION**. Packaged
policies use the OS package and Embedded runs Logstash in-process, so neither ever downloads a
tarball.

Agents pick up the change on their next check-in. No separate Deploy is needed for binary-only
changes.

## Managing the cache

**Management → Logstash Tarballs** lists everything cached, with live progress while a download is
running.

| Action | What it does |
| --- | --- |
| Download Tarball | Fetch by version + architecture, or from a full URL |
| Import from disk | Register tarballs copied into the cache directory by hand |
| Delete | Remove the tarball, its checksum, and the row |
| Retry download | Re-attempt a failed fetch |

Tarballs live in `LOGSTASHUI_LOGSTASH_DIR`, default `<DATA_DIR>/logstashes`. There is no upload
action — 450 MB through a browser is not viable.

**Served** counts full tarball downloads. An agent fetches the `.sha512` sidecar as well, and may
resume an interrupted transfer with a range request; neither adds to the count, so the number tracks
how many agents actually pulled the release.

### Air-gapped sites

Copy the tarball (and its `.sha512`, if you have it) into the cache directory, then click **Import
from disk**. LogstashUI hashes the file and publishes it. If you supply a `.sha512` it is checked and
a mismatch fails the import; if you do not, LogstashUI writes one from what it computed so the
agent's own verification step still has something to check.

## Configuration

The upstream source is **Management → Settings → Logstash tarball source**. Blank means
`https://artifacts.elastic.co/downloads/logstash`. Point it at an internal mirror to keep fetches
inside your network.

Everything else is environment, because the concurrency limits interact with `LOGSTASHUI_WORKERS`
and take effect at startup:

| Variable | Default | Notes |
| --- | --- | --- |
| `LOGSTASHUI_LOGSTASH_DIR` | `<DATA_DIR>/logstashes` | Cache root |
| `LOGSTASHUI_ARTIFACT_MAX_UPSTREAM` | `2` | Concurrent fetches from upstream, across all workers |
| `LOGSTASHUI_ARTIFACT_MAX_SERVE_PER_WORKER` | `4` | Concurrent agent downloads **per worker**; effective total is this × `LOGSTASHUI_WORKERS` |

The serve limit is a fairness knob, not a throughput knob. Capping does not reduce the total bytes
moved — it decides whether twenty agents each crawl at a twentieth of your bandwidth, or eight finish
quickly and twelve retry shortly after. For a rollout, the second is better.

## What agents see

`GET /ConnectionManager/LogstashArtifact/<connection_id>/<filename>` with
`Authorization: ApiKey <enrollment key>`, over the product CA.

The `connection_id` is in the path because a GET has no body to carry it, and an agent key is a bare
hash with no lookup column — the header alone cannot identify which agent is calling.

| Status | Meaning | Agent behaviour |
| --- | --- | --- |
| `200` | The file, with `Content-Length` and `Accept-Ranges: bytes` | Verify the SHA-512 as usual |
| `206` | Partial content, if the agent sent a `Range` header | Append and continue |
| `503` | Not cached yet; a fetch has started | Sleep for `Retry-After`, retry |
| `429` | At the concurrent-serve cap | Sleep for `Retry-After`, retry |
| `502` | The upstream fetch failed | Retry, and check the Logstash Tarballs page |
| `404` | Filename not recognized | Fail the deployment |
| `401` | Bad key or wrong `connection_id` | Re-enroll |

Agents honour `Retry-After`, backing off exponentially to a 5-minute ceiling. When the proxy is
enabled they **never** fall back to `artifacts.elastic.co` — silently reaching the internet would
defeat both the bandwidth saving and air-gapped operation.

Range requests let an agent resume an interrupted transfer instead of re-pulling 450 MB, which is
exactly the load the cache exists to prevent.

## How it behaves under load

- **One download per release, ever.** The first agent to ask triggers the fetch and gets a 503;
  everyone else gets a 503 until it lands. This holds across gunicorn workers — the claim is a
  conditional database update, not an in-process lock.
- **Nothing partial is ever served.** Downloads land in a `.part` file and are moved into place only
  after the SHA-512 verifies.
- **Restarts are safe.** A download killed by a restart leaves a stale claim, which the next request
  reclaims; the orphaned `.part` is swept at startup.
- **Check-ins do not starve.** Transfers are chunked so they yield frequently. With the default caps
  the practical ceiling is your network, not the server.

## Measuring it

Set `LOGSTASHUI_OTEL=true` to export traces and metrics over OTLP/HTTP to
`OTEL_EXPORTER_OTLP_ENDPOINT`. The Docker/K8s image and freeze artifacts already
install `LogstashUI[otel]`. Native pip/uv: `pip install 'LogstashUI[otel]'`.
If the extra is missing, LogstashUI logs ERROR and continues without tracing.

Four instruments answer the capacity question that request traces cannot:

| Instrument | What it tells you |
| --- | --- |
| `logstashui.gevent.hub.lag` | The important one. Flat under load means you are network-bound and more workers will not help; rising means requests are starving and more workers or cores will |
| `logstashui.artifact.downloads.active` | If this never reaches the cap, the cap is not your constraint |
| `logstashui.artifact.requests` | The 429/503 rate — the direct "raise the cap" signal |
| `logstashui.artifact.serve.bytes_per_second` | Per-stream throughput. Falling while the aggregate stays flat means you are at the network ceiling |

Only the HTTP/protobuf OTLP exporter is supported. The gRPC exporter is incompatible with the gevent
worker LogstashUI runs under.

## Troubleshooting

**Agents keep getting 503.** Check the Logstash Tarballs page. A row stuck on *Downloading* with no
progress usually means the upstream is unreachable; a *Failed* row shows the reason.

**"SHA-512 mismatch".** The upstream published a checksum that does not match what was downloaded.
Nothing is published, so agents are unaffected. Retry — this is usually a truncated transfer.

**Agents still hit artifacts.elastic.co.** The checkbox only takes effect for **Managed**/**Simulate**
policies with source **VERSION**. Confirm the policy saved, then confirm the agent has checked in
since.

**A version disappeared.** Deleting a tarball a policy still pins sends those agents into a retry
loop until it is cached again. The table marks those rows **in use**.
