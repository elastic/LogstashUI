# API Access

LogstashUI's JSON endpoints are normally reached from a logged-in browser session. An **API
token** lets a script, CI job, or provisioning tool call the same endpoints with `curl`.

## Creating a token

**Management → API Tokens → Create Token.**

Give the token a name, optionally set an expiry in days, and copy the value. It looks like:

```plain
lsui_bfed5132382f_kmrqP9ETXxF0yKz1s--1SPrHl93yllxhq_kj2Hpz3i8
```

Only a hash is stored, so **the token is shown exactly once**. If you lose it, revoke it and mint
a new one.

A token acts as the user who created it and inherits that account's role. A token created by a
`readonly` user can read but not write. Revoking takes effect on the next request.

## Making requests

Send the token in an `Authorization` header:

```bash
curl -k -X POST \
  -H "Authorization: ApiKey lsui_<prefix>_<secret>" \
  -d "connection_type=CENTRALIZED&name=my-cluster&host=https://es.example.com&port=443&api_key=<es-api-key>" \
  https://localhost:8443/ConnectionManager/AddConnection
```

Token requests are exempt from CSRF, so no cookie jar or `X-CSRFToken` header is needed. CSRF
remains fully enforced for ordinary browser sessions — the exemption applies only after a token
has been verified.

Every existing JSON endpoint accepts a token, not just the one below.

## Adding a remote Elasticsearch cluster for Centralized Pipeline Management

`POST /ConnectionManager/AddConnection` (note: **no trailing slash**), form-encoded.

| Field | Required | Notes |
| --- | --- | --- |
| `connection_type` | yes | `CENTRALIZED` |
| `name` | yes | Display name, must be unique |
| `host` | one of | Full URL, e.g. `https://es.example.com` |
| `cloud_id` | one of | Elastic Cloud ID, as an alternative to `host` |
| `port` | no | Usually `9200`, or `443` for Cloud |
| `api_key` | no | Elasticsearch API key |
| `username` / `password` | no | Basic auth, as an alternative to `api_key` |
| `cloud_url` | no | Full cluster URL |

Either `host` or `cloud_id` must be present. Supply either `api_key` or `username`+`password`;
missing credentials are not rejected by validation but will fail the connectivity test.

On success:

```json
{"success": true, "connection_id": 7, "message": "Connection created and tested successfully!"}
```

LogstashUI pings the cluster before saving. If the ping fails, the connection is rolled back and
the error is returned.

## Two things that will bite you

**Check the body, not the status code.** `AddConnection` returns **HTTP 200** even when the
request fails, with the reason in the body:

```json
{"success": false, "error": "Connection error caused by: ..."}
```

So test `.success`:

```bash
resp=$(curl -sk -X POST -H "Authorization: ApiKey $TOKEN" -d "$BODY" \
  https://localhost:8443/ConnectionManager/AddConnection)
echo "$resp" | grep -q '"success": true' || { echo "failed: $resp" >&2; exit 1; }
```

**`-k` is required against the built-in certificate.** LogstashUI serves TLS from its own product
CA, which curl does not trust by default. Either pass `-k`, or fetch the CA and trust it properly:

```bash
curl -sk https://localhost:8443/.well-known/logstashui/ca.crt -o logstashui-ca.crt
curl --cacert logstashui-ca.crt -X POST -H "Authorization: ApiKey $TOKEN" ...
```

## Error responses

| Status | Meaning |
| --- | --- |
| `401` | Token missing, malformed, unknown, revoked, expired, or owned by a disabled user |
| `403` | Token is valid but its owner lacks the required role |
| `405` | Wrong HTTP method |
| `200` with `"success": false` | Request reached the view and was rejected there |

## Notes

- Agent enrollment keys are a separate credential and are unaffected. They carry no `lsui_`
  marker and continue to authenticate as before.
- Verifying a token costs one PBKDF2 comparison. That is deliberate, and fine at scripting rates,
  but do not put a token request in a tight loop.
- Never commit a token. Treat it as equivalent to the password of the account that created it.
