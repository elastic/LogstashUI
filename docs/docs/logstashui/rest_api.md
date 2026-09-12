# REST API Reference

LogstashUI exposes a JSON REST API under `/api/`. All endpoints require an API key
unless noted otherwise.

---

## Contents

- [Authentication](#authentication)
- [Connections](#connections)
- [Security](#security)
- [SNMP](#snmp-devices)
- [Policies](#policies)
- [Pipelines](#pipelines)

---

## Authentication

### Creating an API key

Go to **[Management](/Management) → [API Keys](/Management/ApiTokens) → Create Key.**

Give the key a name, optionally set an expiry in days, and copy the value shown:

```
lsui_<prefix>_<secret>
```

The secret portion is shown **exactly once** — only a hash is stored server-side. If you lose it,
revoke it and create a new one.

Generated API secrets contain 256 bits of randomness and are stored as SHA-256
digests, verified with a constant-time comparison. Existing PBKDF2 token hashes
upgrade after successful authentication; the token value does not change.
Human login passwords continue to use Django's password hashing.

When upgrading from a release that only understands PBKDF2 tokens, replace all UI
workers together: older workers cannot verify upgraded token hashes. Rolling back
to such a release requires reissuing affected tokens or restoring compatible
stored hashes from a backup.

A key acts as the user who created it and inherits that account's role. A key created by a
`readonly` user can read but not write. Revocation takes effect on the next request.

### Sending the key

Pass the key in an `Authorization` header on every request:

```bash
export KEY="lsui_<prefix>_<secret>"
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/...
```

Key requests are exempt from CSRF. No cookie jar or `X-CSRFToken` header is needed.

> [!NOTE]
> LogstashUI serves TLS from its own product CA. Pass `-k` to skip verification, or fetch
> the CA and trust it properly:
>
> ```bash
> curl -sk https://logstashui.example.com/.well-known/logstashui/ca.crt -o logstashui-ca.crt
> curl --cacert logstashui-ca.crt -H "Authorization: ApiKey $KEY" ...
> ```

### Response conventions

All endpoints return `application/json`. HTTP status codes are meaningful:

| Status | Meaning |
|--------|---------|
| `200` | Success (GET, PUT, DELETE) |
| `201` | Created (POST) |
| `400` | Validation error — body contains `error` with details |
| `401` | Missing or invalid API key |
| `403` | Key is valid but the owning user lacks the required role |
| `404` | Resource not found |
| `405` | Wrong HTTP method |
| `408` | Simulation timeout — agent did not return results within the requested window |
| `409` | Conflict (e.g. duplicate name at the database level) |
| `502` | Upstream error — Elasticsearch or simulate agent returned an unexpected response |

---

## Connections

Manage Elasticsearch connections used by Centralized Pipeline Management and SNMP.

### List connections

```
GET /api/connections/
```

Returns an array of all connections. No query parameters.

```bash
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/connections/
```

```json
[
  {
    "id": 1,
    "name": "my-cluster",
    "connection_type": "CENTRALIZED",
    "host": null,
    "port": 443,
    "cloud_id": "<redacted>",
    "cloud_url": "https://my-cluster.es.us-east-2.aws.elastic-cloud.com",
    "username": null,
    "is_active": true,
    "created_at": "2026-01-01T12:00:00Z"
  }
]
```

---

### Get a connection

```
GET /api/connections/{id}/
```

```bash
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/connections/1/
```

Returns the same fields as the list. `404` if not found.

---

### Create a connection

```
POST /api/connections/
```

**Required role:** admin

The connection is tested before being saved. If the connectivity test fails the record is
rolled back and an error is returned.

**URL + basic auth:**

```bash
curl -X POST https://logstashui.example.com/api/connections/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-cluster",
    "connection_type": "CENTRALIZED",
    "connection_mode": "url",
    "auth_type": "basic",
    "host": "https://es.example.com",
    "port": 9200,
    "username": "elastic",
    "password": "<password>"
  }'
```

**Elastic Cloud + API key:**

```bash
curl -X POST https://logstashui.example.com/api/connections/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-cloud",
    "connection_type": "CENTRALIZED",
    "connection_mode": "cloud",
    "auth_type": "api_key",
    "cloud_id": "<elastic-cloud-id>",
    "cloud_url": "https://my-cluster.es.us-east-2.aws.elastic-cloud.com",
    "port": 443,
    "api_key": "<elasticsearch-api-key>"
  }'
```

```json
{"success": true, "connection_id": 1, "message": "Connection created and tested successfully."}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Must be unique |
| `connection_type` | yes | `CENTRALIZED` or `AGENT` |
| `connection_mode` | no | `url` or `cloud` |
| `auth_type` | no | `basic` or `api_key` |
| `host` | one of | Full URL e.g. `https://es.example.com` |
| `cloud_id` | one of | Elastic Cloud ID |
| `cloud_url` | no | Full cluster URL |
| `port` | no | `9200` for URL, `443` for Cloud |
| `username` / `password` | no | Basic auth |
| `api_key` | no | Elasticsearch API key |

---

### Update a connection

```
PUT /api/connections/{id}/
```

**Required role:** admin

Accepts the same fields as POST. The connectivity test is re-run; on failure the update is
rolled back.

```bash
curl -X PUT https://logstashui.example.com/api/connections/1/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-cluster-renamed", "port": 443}'
```

```json
{"success": true, "connection_id": 1, "message": "Connection updated and tested successfully."}
```

---

### Delete a connection

```
DELETE /api/connections/{id}/
```

**Required role:** admin

```bash
curl -X DELETE https://logstashui.example.com/api/connections/1/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Connection 'my-cluster' deleted."}
```

---

### Test a connection

```
POST /api/connections/{id}/test/
```

Runs a live connectivity check against the saved connection without modifying it.

```bash
curl -X POST https://logstashui.example.com/api/connections/1/test/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Connection test successful."}
```

---

## Security

Manage users, roles, and API keys. All write operations require admin role, except
`/api/security/bootstrap/` (unauthenticated when no users exist) and
`/api/security/me/` (any authenticated user).

### Bootstrap

```
GET  /api/security/bootstrap/
POST /api/security/bootstrap/
```

Checks whether the initial admin account has been created. Unauthenticated; returns
`{"bootstrapped": false}` when no users exist yet.

**Check status:**

```bash
curl https://logstashui.example.com/api/security/bootstrap/
```

```json
{"bootstrapped": false, "message": "No users exist. POST to this endpoint to create the first admin."}
```

**Create the first admin (optionally also create an API key):**

```bash
curl -X POST https://logstashui.example.com/api/security/bootstrap/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "<strong-password>",
    "email": "admin@example.com",
    "create_key": true,
    "key_name": "bootstrap-key"
  }'
```

```json
{
  "success": true,
  "message": "Admin user created successfully.",
  "user_id": 1,
  "key": "lsui_<prefix>_<secret>"
}
```

---

### Current user (me)

```
GET /api/security/me/
```

Returns the identity of the caller. Any authenticated user.

```bash
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/security/me/
```

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "role": "admin",
  "is_active": true
}
```

---

### List users

```
GET /api/security/users/
```

**Required role:** admin

```bash
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/security/users/
```

```json
{
  "users": [
    {"id": 1, "username": "admin", "email": "admin@example.com", "role": "admin", "is_active": true}
  ]
}
```

---

### Create a user

```
POST /api/security/users/
```

**Required role:** admin

```bash
curl -X POST https://logstashui.example.com/api/security/users/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "reader",
    "password": "<strong-password>",
    "email": "reader@example.com",
    "role": "readonly"
  }'
```

```json
{"success": true, "user_id": 2, "message": "User created."}
```

| Field | Required | Notes |
|-------|----------|-------|
| `username` | yes | Must be unique |
| `password` | yes | Minimum 8 characters |
| `email` | no | |
| `role` | no | `admin` or `readonly` (default: `readonly`) |

---

### Get a user

```
GET /api/security/users/{id}/
```

**Required role:** admin

```bash
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/security/users/2/
```

---

### Update a user

```
PUT /api/security/users/{id}/
```

**Required role:** admin

```bash
curl -X PUT https://logstashui.example.com/api/security/users/2/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{"role": "admin", "email": "reader-promoted@example.com"}'
```

```json
{"success": true, "message": "User updated."}
```

---

### Delete a user

```
DELETE /api/security/users/{id}/
```

**Required role:** admin. Cannot delete your own account or the last remaining user.

```bash
curl -X DELETE https://logstashui.example.com/api/security/users/2/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "User 'reader' deleted."}
```

---

### List API keys

```
GET /api/security/keys/
```

**Required role:** admin. Secret values are never returned.

```bash
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/security/keys/
```

```json
{
  "keys": [
    {
      "id": 1,
      "name": "ci-key",
      "prefix": "lsui_abc123",
      "created_at": "2026-01-01T12:00:00Z",
      "expires_at": null,
      "revoked": false,
      "username": "admin"
    }
  ]
}
```

---

### Create an API key

```
POST /api/security/keys/
```

**Required role:** admin. The full key value is returned **once** — store it immediately.

```bash
curl -X POST https://logstashui.example.com/api/security/keys/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "ci-key", "expires_in_days": 90, "user_id": 1}'
```

```json
{
  "success": true,
  "key": "lsui_<prefix>_<secret>",
  "id": 1,
  "message": "API key created. Store it now — it will not be shown again."
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Descriptive label |
| `user_id` | no | Defaults to the calling user |
| `expires_in_days` | no | Omit for no expiry |

---

### Revoke an API key

```
POST /api/security/keys/{id}/revoke/
```

**Required role:** admin. The key stops working immediately; the row is kept for audit.

```bash
curl -X POST https://logstashui.example.com/api/security/keys/1/revoke/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Key revoked."}
```

---

### Delete an API key

```
DELETE /api/security/keys/{id}/
```

**Required role:** admin. Hard delete — removes the audit record as well.

```bash
curl -X DELETE https://logstashui.example.com/api/security/keys/1/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Key deleted."}
```

---

## SNMP Devices

Create and manage the devices that LogstashUI polls via SNMP.

### List devices

```
GET /api/snmp/devices/
```

Paginated, filterable. Any authenticated user.

| Parameter | Default | Notes |
|-----------|---------|-------|
| `page` | `1` | |
| `page_size` | `25` | Max 200 |
| `search` | — | Case-insensitive match on name, IP, or hostname |
| `network` | — | Filter by network ID |
| `sort_by` | `-created_at` | `name`, `-name`, `ip_address`, `-ip_address`, `hostname`, `-hostname`, `created_at`, `-created_at` |

```bash
curl "https://logstashui.example.com/api/snmp/devices/?search=router&sort_by=name&page_size=50" \
  -H "Authorization: ApiKey $KEY"
```

```json
{
  "devices": [
    {
      "id": 1,
      "name": "core-router",
      "ip_address": "10.0.0.1",
      "hostname": "router.example.com",
      "port": 161,
      "retries": 2,
      "timeout": 1000,
      "credential_id": 1,
      "credential_name": "Public",
      "network_id": 1,
      "network_name": "Homelab",
      "network_deployment_mode": "AGENT",
      "device_template_id": 12,
      "device_template_name": "cisco_ios",
      "site": null,
      "building": null,
      "room": null,
      "created_at": "2026-01-01T12:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 25,
  "total_pages": 1,
  "has_next": false,
  "has_previous": false
}
```

---

### Get a device

```
GET /api/snmp/devices/{id}/
```

Returns the full device record including `latitude`, `longitude`, `metadata`, and `updated_at`.
Any authenticated user.

```bash
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/snmp/devices/1/
```

```json
{
  "success": true,
  "device": {
    "id": 1,
    "name": "core-router",
    "ip_address": "10.0.0.1",
    "hostname": "router.example.com",
    "port": 161,
    "retries": 2,
    "timeout": 1000,
    "credential_id": 1,
    "network_id": 1,
    "device_template_id": 12,
    "site": null,
    "building": null,
    "room": null,
    "latitude": null,
    "longitude": null,
    "metadata": {},
    "created_at": "2026-01-01T12:00:00Z",
    "updated_at": "2026-01-01T12:00:00Z"
  }
}
```

---

### Create a device

```
POST /api/snmp/devices/
```

**Required role:** admin. At least one of `ip_address` or `hostname` is required.
On success, `SNMPDeploymentState` is flagged so the next deploy picks up the change.

```bash
curl -X POST https://logstashui.example.com/api/snmp/devices/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "core-router",
    "ip_address": "10.0.0.1",
    "hostname": "router.example.com",
    "port": 161,
    "retries": 2,
    "timeout": 1000,
    "credential": 1,
    "network": 1,
    "device_template": 12,
    "site": "HQ",
    "building": "Data Centre",
    "room": "Rack 3",
    "latitude": 37.7749,
    "longitude": -122.4194,
    "metadata": {"role": "core"}
  }'
```

```json
{"success": true, "id": 1, "message": "Device created successfully."}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Must be unique |
| `ip_address` | one of | |
| `hostname` | one of | |
| `port` | no | Default `161` |
| `retries` | no | Default `2` |
| `timeout` | no | Milliseconds, default `1000` |
| `credential` | no | Credential ID |
| `network` | no | Network ID |
| `device_template` | no | Template ID |
| `site` / `building` / `room` | no | Location labels |
| `latitude` / `longitude` | no | Decimal degrees |
| `metadata` | no | Arbitrary JSON object |

---

### Update a device

```
PUT /api/snmp/devices/{id}/
```

**Required role:** admin. Pass `null` for any FK field to clear the association.

```bash
curl -X PUT https://logstashui.example.com/api/snmp/devices/1/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "core-router-updated",
    "ip_address": "10.0.0.2",
    "port": 1161,
    "retries": 3,
    "network": null
  }'
```

```json
{"success": true, "id": 1, "message": "Device updated successfully."}
```

---

### Delete a device

```
DELETE /api/snmp/devices/{id}/
```

**Required role:** admin.

```bash
curl -X DELETE https://logstashui.example.com/api/snmp/devices/1/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Device 'core-router-updated' deleted."}
```

---

---

## SNMP Credentials

Manage SNMP community strings (v1/v2c) and SNMPv3 user security profiles.
Secret values (community string, auth/priv passwords) are **stored encrypted** and
**never returned** by the API — the response indicates only whether a secret is set.

All write operations require **admin** role. Reads require any authenticated user.

> [!NOTE]
> Every create, update, or delete on a credential flags `SNMPDeploymentState` as changed.
> This lights up the "deploy needed" indicator so keystore changes are pushed on the next
> agent deploy.

### List credentials

```
GET /api/snmp/credentials/
```

| Parameter | Notes |
|-----------|-------|
| `search` | Case-insensitive match on name or description |
| `version` | Filter by SNMP version: `1`, `2c`, or `3` |

```bash
curl -H "Authorization: ApiKey $KEY" \
  "https://logstashui.example.com/api/snmp/credentials/?version=2c"
```

```json
{
  "credentials": [
    {
      "id": 1,
      "name": "Public",
      "description": "",
      "version": "2c",
      "security_level": null,
      "device_count": 5,
      "created_at": "2026-01-01T12:00:00Z"
    }
  ],
  "total": 1
}
```

---

### Get a credential

```
GET /api/snmp/credentials/{id}/
```

Returns all non-secret fields. Secret fields show `***` when set or `""` when empty.

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/snmp/credentials/1/
```

**v2c response:**
```json
{
  "success": true,
  "credential": {
    "id": 1,
    "name": "Public",
    "description": "",
    "version": "2c",
    "has_community": true,
    "community": "***",
    "created_at": "2026-01-01T12:00:00Z",
    "updated_at": "2026-01-01T12:00:00Z"
  }
}
```

**v3 response:**
```json
{
  "success": true,
  "credential": {
    "id": 2,
    "name": "snmpv3-user",
    "version": "3",
    "security_name": "snmpuser",
    "security_level": "authPriv",
    "auth_protocol": "sha",
    "auth_pass": "***",
    "priv_protocol": "aes",
    "priv_pass": "***",
    "has_auth_pass": true,
    "has_priv_pass": true,
    "created_at": "2026-01-01T12:00:00Z",
    "updated_at": "2026-01-01T12:00:00Z"
  }
}
```

---

### Create a credential

```
POST /api/snmp/credentials/
```

**Required role:** admin

**SNMPv2c:**
```bash
curl -X POST https://logstashui.example.com/api/snmp/credentials/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "datacenter-v2c",
    "description": "v2c community for datacenter switches",
    "version": "2c",
    "community": "s3cr3t-community"
  }'
```

**SNMPv3 (authPriv):**
```bash
curl -X POST https://logstashui.example.com/api/snmp/credentials/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "datacenter-v3",
    "version": "3",
    "security_name": "snmpuser",
    "security_level": "authPriv",
    "auth_protocol": "sha",
    "auth_pass": "authpassword123",
    "priv_protocol": "aes",
    "priv_pass": "privpassword123"
  }'
```

```json
{"success": true, "id": 3, "message": "Credential created successfully."}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Must be unique |
| `version` | yes | `1`, `2c`, or `3` |
| `description` | no | |
| `community` | v1/v2c | Community string (stored encrypted) |
| `security_name` | v3 | SNMPv3 username |
| `security_level` | v3 | `noAuthNoPriv`, `authNoPriv`, or `authPriv` |
| `auth_protocol` | v3 authNoPriv/authPriv | `md5`, `sha`, `sha2`, `hmac128sha224`, `hmac192sha256`, `hmac256sha384`, `hmac384sha512` |
| `auth_pass` | v3 authNoPriv/authPriv | Stored encrypted |
| `priv_protocol` | v3 authPriv | `des`, `3des`, `aes`, `aes128`, `aes192`, `aes256` |
| `priv_pass` | v3 authPriv | Stored encrypted |

---

### Update a credential

```
PUT /api/snmp/credentials/{id}/
```

**Required role:** admin

Pass the same fields as POST. To **keep an existing secret** (community, auth_pass, priv_pass),
omit the field or send an **empty string** — the stored value is preserved. Send a non-empty
string to rotate the secret.

```bash
curl -X PUT https://logstashui.example.com/api/snmp/credentials/3/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "datacenter-v3",
    "version": "3",
    "security_name": "snmpuser",
    "security_level": "authPriv",
    "auth_protocol": "sha",
    "auth_pass": "",
    "priv_protocol": "aes",
    "priv_pass": "new-priv-password"
  }'
```

```json
{"success": true, "id": 3, "message": "Credential updated successfully."}
```

---

### Delete a credential

```
DELETE /api/snmp/credentials/{id}/
```

**Required role:** admin. Devices and networks that reference this credential will have their FK set to `null`.

```bash
curl -X DELETE https://logstashui.example.com/api/snmp/credentials/3/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Credential 'datacenter-v3' deleted."}
```

---

## SNMP Networks

Manage the network ranges that LogstashUI discovers and polls. Each network is associated
with an Elasticsearch connection and optional SNMP credentials.

> [!WARNING]
> Networks larger than `/20` are rejected. Discovery expands the full IP range in memory;
> a `/16` (65,536 addresses) would exhaust available RAM. Break large ranges into `/20` or
> smaller subnets.

All write operations require **admin** role. Reads require any authenticated user.

> [!NOTE]
> Deleting a network also attempts to remove the associated Logstash polling and trap
> pipelines from Elasticsearch. This is best-effort — the network row is removed regardless
> of whether pipeline cleanup succeeds.

### List networks

```
GET /api/snmp/networks/
```

| Parameter | Notes |
|-----------|-------|
| `search` | Case-insensitive match on name or network range |

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/snmp/networks/
```

```json
{
  "networks": [
    {
      "id": 1,
      "name": "Homelab",
      "network_range": "192.168.4.0/22",
      "deployment_mode": "AGENT",
      "credential_mode": "KEYSTORE",
      "connection_id": 17,
      "connection_name": "Homelab",
      "agent_connection_id": 8,
      "agent_connection_name": "LogstashAgent-Packaged",
      "discovery_credential_id": 1,
      "credential_id": null,
      "discovery_enabled": true,
      "traps_enabled": false,
      "interval": 60,
      "namespace": "default",
      "namespace_from_device_template": false,
      "device_count": 12,
      "created_at": "2026-01-01T12:00:00Z",
      "updated_at": "2026-01-01T12:00:00Z"
    }
  ],
  "total": 1
}
```

---

### Get a network

```
GET /api/snmp/networks/{id}/
```

Returns the same fields as the list. `404` if not found.

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/snmp/networks/1/
```

---

### Create a network

```
POST /api/snmp/networks/
```

**Required role:** admin

```bash
curl -X POST https://logstashui.example.com/api/snmp/networks/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Office",
    "network_range": "10.10.10.0/24",
    "deployment_mode": "CENTRALIZED",
    "credential_mode": "KEYSTORE",
    "connection": 1,
    "discovery_credential": 1,
    "discovery_enabled": true,
    "traps_enabled": false,
    "interval": 30,
    "namespace": "default"
  }'
```

```json
{"success": true, "id": 2, "message": "Network created successfully."}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Must be unique |
| `network_range` | yes | CIDR notation, prefix must be `/20` or longer |
| `deployment_mode` | no | `CENTRALIZED` (default) or `AGENT` |
| `credential_mode` | no | `KEYSTORE` (default) or `PLAINTEXT` (centralized only) |
| `connection` | no | Elasticsearch connection ID (for centralized polling) |
| `agent_connection` | no | Agent connection ID (for agent-mode polling) |
| `discovery_credential` | no | Credential ID used for discovery |
| `credential` | no | Credential ID used for trap ingestion |
| `discovery_enabled` | no | Default `true` |
| `traps_enabled` | no | Default `false` |
| `interval` | no | Poll interval in seconds, default `30` |
| `namespace` | no | Data-stream namespace, default `"default"` |
| `namespace_from_device_template` | no | Derive namespace from device template name |

---

### Update a network

```
PUT /api/snmp/networks/{id}/
```

**Required role:** admin. Pass `null` for any FK field to clear it. CIDR validation applies on update too.

```bash
curl -X PUT https://logstashui.example.com/api/snmp/networks/2/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Office-updated",
    "interval": 60,
    "traps_enabled": true,
    "connection": null
  }'
```

```json
{"success": true, "id": 2, "message": "Network updated successfully."}
```

---

### Delete a network

```
DELETE /api/snmp/networks/{id}/
```

**Required role:** admin.

```bash
curl -X DELETE https://logstashui.example.com/api/snmp/networks/2/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Network 'Office-updated' deleted."}
```

If associated Logstash pipelines were also removed from Elasticsearch, the message will include the pipeline names.

---

## SNMP Profiles

OID profiles define which metrics to collect from a device (`get`, `walk`, `table` mappings).
They are attached to [Device Templates](#snmp-device-templates) in a many-to-many relationship.

**Official profiles** ship with LogstashUI and have names ending in `.json` (e.g. `cisco_ios.json`).
They cannot be deleted.

All write operations require **admin** role. Reads require any authenticated user.

### List profiles

```
GET /api/snmp/profiles/
```

| Parameter | Notes |
|-----------|-------|
| `search` | Case-insensitive match on name or vendor |
| `official` | `true` or `false` to filter by official status |

```bash
curl -H "Authorization: ApiKey $KEY" \
  "https://logstashui.example.com/api/snmp/profiles/?official=false"
```

```json
{
  "profiles": [
    {
      "id": 36,
      "name": "my_custom_switch",
      "vendor": "Acme",
      "product": "Switch X",
      "description": "Custom profile for in-house switch",
      "is_official": false,
      "created_at": "2026-01-01T12:00:00Z"
    }
  ],
  "total": 1
}
```

> [!NOTE]
> The list response omits `profile_data` and `normalizers` (these can be large). Fetch the
> individual profile to get the full OID map.

---

### Get a profile

```
GET /api/snmp/profiles/{id}/
```

Returns the full profile including `profile_data` and `normalizers`.

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/snmp/profiles/36/
```

```json
{
  "success": true,
  "profile": {
    "id": 36,
    "name": "my_custom_switch",
    "vendor": "Acme",
    "product": "Switch X",
    "description": "Custom profile for in-house switch",
    "is_official": false,
    "profile_data": {
      "get": {
        "system.name": "1.3.6.1.2.1.1.5.0",
        "system.uptime": "1.3.6.1.2.1.1.3.0"
      },
      "walk": [],
      "table": {}
    },
    "normalizers": [],
    "created_at": "2026-01-01T12:00:00Z",
    "updated_at": "2026-01-01T12:00:00Z"
  }
}
```

---

### Create a profile

```
POST /api/snmp/profiles/
```

**Required role:** admin

```bash
curl -X POST https://logstashui.example.com/api/snmp/profiles/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_custom_switch",
    "description": "Custom profile for in-house switch",
    "vendor": "Acme",
    "product": "Switch X",
    "profile_data": {
      "get": {
        "system.name": "1.3.6.1.2.1.1.5.0",
        "system.uptime": "1.3.6.1.2.1.1.3.0"
      },
      "walk": [],
      "table": {}
    },
    "normalizers": []
  }'
```

```json
{"success": true, "id": 36, "message": "Profile created successfully."}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Must be unique. Names ending in `.json` are treated as official |
| `vendor` | yes | |
| `product` | no | |
| `description` | no | |
| `profile_data` | yes | Non-empty dict with `get`, `walk`, and/or `table` keys |
| `normalizers` | no | List of normalizer configs |

---

### Update a profile

```
PUT /api/snmp/profiles/{id}/
```

**Required role:** admin. Renaming is supported via the `name` field; the endpoint checks for conflicts.

```bash
curl -X PUT https://logstashui.example.com/api/snmp/profiles/36/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_custom_switch_v2",
    "description": "Updated OID map",
    "profile_data": {
      "get": {"system.uptime": "1.3.6.1.2.1.1.3.0"},
      "walk": [],
      "table": {}
    }
  }'
```

```json
{"success": true, "id": 36, "message": "Profile updated successfully."}
```

---

### Delete a profile

```
DELETE /api/snmp/profiles/{id}/
```

**Required role:** admin. The built-in `system` and `generic_system.json` profiles cannot be deleted (`403`).

```bash
curl -X DELETE https://logstashui.example.com/api/snmp/profiles/36/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Profile 'my_custom_switch_v2' deleted."}
```

---

## SNMP Device Templates

Device templates bundle one or more OID profiles and matching rules that LogstashUI uses
to automatically classify newly discovered devices. They also control which metrics are
collected from a device.

**Official templates** ship with LogstashUI (`official: true`). They cannot be modified
or deleted — `PUT` and `DELETE` both return `403`.

All write operations require **admin** role. Reads require any authenticated user.

> [!NOTE]
> Deleting a user-created template reassigns any devices currently using it to the built-in
> `default` template. No devices are left without a template.

### List templates

```
GET /api/snmp/templates/
```

| Parameter | Notes |
|-----------|-------|
| `search` | Case-insensitive match on name or vendor |
| `official` | `true` or `false` to filter by official status |

```bash
curl -H "Authorization: ApiKey $KEY" \
  "https://logstashui.example.com/api/snmp/templates/?official=false"
```

```json
{
  "templates": [
    {
      "id": 17,
      "name": "my_custom_switch",
      "vendor": "Acme",
      "model": "Switch-X",
      "product": "",
      "type": "switch",
      "official": false,
      "description": "Template for in-house switches",
      "created_at": "2026-01-01T12:00:00Z"
    }
  ],
  "total": 1
}
```

> [!NOTE]
> The list response omits `profiles` and `matching_rules`. Fetch the individual template to
> get those fields.

---

### Get a template

```
GET /api/snmp/templates/{id}/
```

Returns the full template including associated profiles and matching rules.

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/snmp/templates/1/
```

```json
{
  "success": true,
  "template": {
    "id": 1,
    "name": "generic_linux",
    "vendor": "Generic",
    "model": "",
    "product": "",
    "type": "",
    "official": true,
    "description": "",
    "matching_rules": ["Linux"],
    "profiles": [
      {"id": 10, "name": "generic_host_system_metrics.json"},
      {"id": 11, "name": "generic_interfaces.json"},
      {"id": 12, "name": "generic_system.json"},
      {"id": 13, "name": "generic_ucd_system_metrics.json"}
    ],
    "created_at": "2026-01-01T12:00:00Z",
    "updated_at": "2026-01-01T12:00:00Z"
  }
}
```

---

### Create a template

```
POST /api/snmp/templates/
```

**Required role:** admin. New templates are always created as non-official (`official: false`).

```bash
curl -X POST https://logstashui.example.com/api/snmp/templates/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_custom_switch",
    "description": "Template for in-house switches",
    "vendor": "Acme",
    "model": "Switch-X",
    "product": "Switch X Series",
    "type": "switch",
    "matching_rules": ["Acme Switch", "ACME-SW"],
    "profiles": [36, 37]
  }'
```

```json
{"success": true, "id": 17, "message": "Device template created successfully."}
```

If any profile ID in `profiles` does not exist, it is silently skipped and the response includes a `skipped_profiles` list.

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Must be unique |
| `vendor` | yes | |
| `model` / `product` / `type` | no | Metadata labels |
| `description` | no | |
| `matching_rules` | no | List of sysDescr substrings for auto-classification |
| `profiles` | no | List of profile IDs to attach |

---

### Update a template

```
PUT /api/snmp/templates/{id}/
```

**Required role:** admin. Returns `403` for official templates.
If `profiles` is provided, the existing profile list is **replaced** (not merged).

```bash
curl -X PUT https://logstashui.example.com/api/snmp/templates/17/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Updated description",
    "matching_rules": ["Acme Switch", "ACME-SW", "AcmeSW"],
    "profiles": [36]
  }'
```

```json
{"success": true, "id": 17, "message": "Device template updated successfully."}
```

---

### Delete a template

```
DELETE /api/snmp/templates/{id}/
```

**Required role:** admin. Returns `403` for official templates.

```bash
curl -X DELETE https://logstashui.example.com/api/snmp/templates/17/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Device template 'my_custom_switch' deleted."}
```

---

## SNMP Deploy

Three endpoints control the SNMP deployment lifecycle. The recommended flow is:

1. **Check status** — fast timestamp comparison, no ES round-trip.
2. **Compute diff** — reconciles desired pipelines against ES CPM / agent records and caches the plan for 60 seconds.
3. **Apply** — executes the cached plan (or falls back to a fresh reconciliation if the cache expired).

All three endpoints require **admin** role, except `GET /api/snmp/deploy/status/` which allows any authenticated user.

### Check deploy status

```
GET /api/snmp/deploy/status/
```

Returns `has_changes: true` when configuration has been modified since the last successful deploy.

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/snmp/deploy/status/
```

```json
{"success": true, "has_changes": true}
```

---

### Compute deploy diff

```
POST /api/snmp/deploy/diff/
```

**Required role:** admin. Compares the desired pipeline set against what is currently deployed.
Results are cached for 60 seconds so the subsequent `apply` call can reuse them.

```bash
curl -X POST https://logstashui.example.com/api/snmp/deploy/diff/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{
  "success": true,
  "has_changes": true,
  "blocking_errors": [],
  "networks": [
    {
      "action": "create",
      "pipeline_name": "snmp-office-cisco_ios-polling",
      "deployment_mode": "AGENT"
    },
    {
      "action": "create",
      "pipeline_name": "snmp-office-discovery",
      "deployment_mode": "AGENT"
    },
    {
      "action": "update",
      "pipeline_name": "Keystore: Packaged Policy",
      "deployment_mode": "AGENT"
    }
  ],
  "connections": [{"id": 17, "name": "Homelab"}]
}
```

If `blocking_errors` is non-empty the deploy cannot proceed — fix the listed issues first.

---

### Apply deploy

```
POST /api/snmp/deploy/apply/
```

**Required role:** admin. Executes the deployment plan. Call `diff/` first to preview changes
and cache the plan; `apply/` will reuse it. If the cache has expired (> 60 s), a fresh
reconciliation is performed automatically.

```bash
curl -X POST https://logstashui.example.com/api/snmp/deploy/apply/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{
  "success": true,
  "message": "Successfully deployed: 2 pipeline(s) created, 1 keystore value(s) updated",
  "pipelines_created": 2,
  "pipelines_updated": 0,
  "pipelines_deleted": 0,
  "errors": null
}
```

After a successful apply, `GET /api/snmp/deploy/status/` returns `has_changes: false`.

**Cleanup deploy example** (after removing a network):

```json
{
  "success": true,
  "message": "Successfully deployed: 2 pipeline(s) deleted, 1 keystore value(s) updated",
  "pipelines_created": 0,
  "pipelines_updated": 0,
  "pipelines_deleted": 2,
  "errors": null
}
```

---

## Policies

Agent policies define the Logstash runtime configuration (paths, JVM options, config files, pipelines) that
is pushed to enrolled agents. Each policy has an independent revision history — edits accumulate until
a **deploy** snapshots them as a new revision. Agents pull the latest snapshot on check-in.

**All policy endpoints require admin role.**

> [!NOTE]
> The three large text fields — `logstash_yml`, `jvm_options`, and `log4j2_properties` — contain
> complete config file contents and can each be several kilobytes. They are included in full in
> single-policy responses. The list response also includes them, so pagination is recommended if
> you are scripting over many policies.

> [!NOTE]
> `policy_type` is immutable after creation. `EMBEDDED` policies are internal system policies
> that cannot be read, created, cloned, or modified via the API.

### List policies

```
GET /api/policies/
```

Returns all non-EMBEDDED policies with an active agent count.

```bash
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/policies/
```

```json
{
  "success": true,
  "policies": [
    {
      "id": 1,
      "name": "Packaged Policy",
      "policy_type": "PACKAGED",
      "is_system": true,
      "cloned_from_id": null,
      "settings_path": "/etc/logstash/",
      "logs_path": "/var/log/logstash",
      "binary_path": "/usr/share/logstash/bin",
      "data_path": "",
      "agent_api_port": 9500,
      "logstash_api_port": 9560,
      "logstash_source": "SYSTEM",
      "logstash_version": "",
      "logstash_via_ui": false,
      "logstash_yml": "# ... full logstash.yml contents ...",
      "jvm_options": "# ... full jvm.options contents ...",
      "log4j2_properties": "# ... full log4j2.properties contents ...",
      "has_undeployed_changes": false,
      "current_revision_number": 3,
      "last_deployed_at": "2026-01-01T12:00:00Z",
      "active_agent_count": 2,
      "created_at": "2026-01-01T12:00:00Z",
      "updated_at": "2026-01-01T12:00:00Z"
    }
  ],
  "total": 1
}
```

---

### Get a policy

```
GET /api/policies/{id}/
```

```bash
curl -H "Authorization: ApiKey $KEY" https://logstashui.example.com/api/policies/1/
```

Returns the same fields as the list. `404` if not found.

---

### Create a policy

```
POST /api/policies/
```

**Required role:** admin

A default enrollment token is minted automatically. If `logstash_yml`, `jvm_options`, or
`log4j2_properties` are omitted, the system defaults are used.

```bash
curl -X POST https://logstashui.example.com/api/policies/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-policy",
    "policy_type": "PACKAGED"
  }'
```

```json
{
  "success": true,
  "id": 5,
  "name": "my-policy",
  "policy_type": "PACKAGED",
  "message": "Policy 'my-policy' created successfully."
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Must be unique |
| `policy_type` | yes | `PACKAGED`, `MANAGED`, or `SIMULATE` |
| `settings_path` | no | Default `/etc/logstash/` |
| `logs_path` | no | Default `/var/log/logstash` |
| `binary_path` | no | Default `/usr/share/logstash/bin` |
| `data_path` | no | |
| `keystore_env_file` | no | Default `/etc/default/logstash` |
| `agent_api_port` | no | Port-type default applied per policy type |
| `logstash_api_port` | no | Port-type default applied per policy type |
| `logstash_source` | no | `SYSTEM` (default) or `VERSION` |
| `logstash_version` | no | Required when `logstash_source` is `VERSION` |
| `logstash_via_ui` | no | `false` default |
| `logstash_yml` | no | Full file contents; system default used if omitted |
| `jvm_options` | no | Full file contents; system default used if omitted |
| `log4j2_properties` | no | Full file contents; system default used if omitted |

---

### Update a policy

```
PUT /api/policies/{id}/
```

**Required role:** admin

Pass only the fields you want to change. Two immutability rules apply:

- `policy_type` cannot be changed — send it matching the current value or omit it entirely.
- System `SIMULATE` and `MANAGED` policies are **path-locked**: `settings_path`, `logs_path`,
  `data_path`, and `keystore_env_file` are ignored. `jvm_options`, `logstash_yml`,
  `log4j2_properties`, `logstash_source`, `logstash_version`, and `binary_path` remain editable.

```bash
curl -X PUT https://logstashui.example.com/api/policies/5/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "jvm_options": "-Xms1g\n-Xmx1g\n",
    "logstash_yml": "pipeline.workers: 4\n"
  }'
```

```json
{"success": true, "message": "Policy 'my-policy' updated successfully."}
```

---

### Delete a policy

```
DELETE /api/policies/{id}/
```

**Required role:** admin. System policies (`is_system: true`) cannot be deleted. A policy
with one or more assigned agent connections also cannot be deleted.

```bash
curl -X DELETE https://logstashui.example.com/api/policies/5/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Policy 'my-policy' deleted."}
```

---

### Deploy a policy

```
POST /api/policies/{id}/deploy/
```

**Required role:** admin

Snapshots the current user-authored state (pipelines, keystore, config files) as a new
revision. `current_revision_number` is incremented and `last_deployed_at` is set. Agents
pick up the new revision on their next check-in.

> [!NOTE]
> SNMP-managed pipelines and keystore entries are excluded from the snapshot — they are
> deployed on a separate channel and are never part of policy revision history.

```bash
curl -X POST https://logstashui.example.com/api/policies/5/deploy/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{
  "success": true,
  "revision_number": 4,
  "policy_name": "my-policy",
  "message": "Policy deployed as revision 4."
}
```

---

### Clone a policy

```
POST /api/policies/{id}/clone/
```

**Required role:** admin

Creates a new policy that is an exact copy of the source, including all user-authored pipelines
and keystore entries. A default enrollment token is minted for the clone.

Type promotion rules:
- `PACKAGED` or `DEFAULT` source → clone becomes `MANAGED` (paths rewritten to managed scheme)
- `MANAGED` source → clone is `MANAGED`
- `SIMULATE` source → clone is `SIMULATE`
- `EMBEDDED` source → `403` (cannot clone)

```bash
curl -X POST https://logstashui.example.com/api/policies/1/clone/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{"new_name": "my-cloned-policy"}'
```

```json
{
  "success": true,
  "id": 6,
  "name": "my-cloned-policy",
  "policy_type": "MANAGED",
  "message": "Policy 'my-cloned-policy' cloned from 'Packaged Policy'."
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `new_name` | yes | Must be unique |

---

### Get pending changes diff

```
GET /api/policies/{id}/diff/
```

**Required role:** admin

Compares the current live policy state against the last deployed revision. Returns the full
`current` and `previous` snapshots and a count of changed sections.

Changed sections counted: `logstash_yml`, `jvm_options`, `log4j2_properties`, pipelines,
keystore entries, keystore password, and global paths (`settings_path`, `logs_path`,
`binary_path`).

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/policies/5/diff/
```

```json
{
  "success": true,
  "policy_name": "my-policy",
  "current_revision": 4,
  "last_deployed_revision": 4,
  "has_undeployed_changes": false,
  "pending_changes": 0,
  "current": {
    "logstash_yml": "pipeline.workers: 4\n",
    "jvm_options": "-Xms1g\n-Xmx1g\n",
    "log4j2_properties": "# ...",
    "settings_path": "/etc/logstash/",
    "logs_path": "/var/log/logstash",
    "binary_path": "/usr/share/logstash/bin",
    "pipelines": [],
    "keystore": [],
    "keystore_password_hash": ""
  },
  "previous": { "...": "same fields, values as of last deploy" }
}
```

When `pending_changes > 0` the `current` and `previous` snapshots can be diffed
field-by-field to show exactly what changed. `pending_changes: 0` means the live state
matches the last deployed revision exactly.

---

### List enrollment tokens

```
GET /api/policies/{id}/tokens/
```

**Required role:** admin

Returns all enrollment tokens for a policy, including the base64-encoded token payload and
the ready-to-run install command for each.

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/policies/5/tokens/
```

```json
{
  "success": true,
  "tokens": [
    {
      "id": 1,
      "name": "default",
      "raw_token": "7CrbDG2Iok-...",
      "encoded_token": "eyJlbnJvbGxtZW50X3Rva2VuIjoi...",
      "enroll_command": "sudo logstash-agent install --enroll=eyJ... --logstash-ui-url=https://logstashui.example.com",
      "agent_ui_url": "https://logstashui.example.com"
    }
  ]
}
```

---

### Create an enrollment token

```
POST /api/policies/{id}/tokens/
```

**Required role:** admin

```bash
curl -X POST https://logstashui.example.com/api/policies/5/tokens/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "production"}'
```

```json
{
  "success": true,
  "id": 2,
  "name": "production",
  "raw_token": "...",
  "encoded_token": "...",
  "enroll_command": "sudo logstash-agent install --enroll=... --logstash-ui-url=...",
  "agent_ui_url": "https://logstashui.example.com",
  "message": "Enrollment token created."
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | no | Label for the token; defaults to `"default"` |

---

### Delete an enrollment token

```
DELETE /api/policies/{id}/tokens/{token_id}/
```

**Required role:** admin

```bash
curl -X DELETE https://logstashui.example.com/api/policies/5/tokens/2/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Token deleted."}
```

---

## Pipelines

Manage Logstash pipelines across two storage backends:

- **Agent pipelines** — stored in the LogstashUI database, scoped to an agent policy, and deployed to Logstash agents on check-in. Identified by an integer `id`.
- **Elasticsearch pipelines** — stored directly in Elasticsearch via the Logstash pipeline API (`/_logstash/pipeline`). Identified by pipeline name within a connection.

All write operations require **admin** role. Reads require any authenticated user.

> [!NOTE]
> Saving an agent pipeline sets `has_undeployed_changes = true` on its policy. The change is
> not pushed to agents until you call `POST /api/pipelines/policies/{id}/deploy/` (or its
> alias `POST /api/policies/{id}/deploy/`).

---

## Agent Pipelines

### List agent pipelines

```
GET /api/pipelines/?policy_id={id}
```

Returns user-authored pipelines for the given policy. The `policy_id` parameter is required.

| Parameter | Notes |
|-----------|-------|
| `policy_id` | Required. Policy primary key |
| `managed_by` | Filter by ownership: `user` (default), `snmp`, or `library` |

```bash
curl -H "Authorization: ApiKey $KEY" \
  "https://logstashui.example.com/api/pipelines/?policy_id=1"
```

```json
{
  "policy_id": 1,
  "policy_name": "Packaged Policy",
  "has_undeployed_changes": false,
  "pipelines": [
    {
      "id": 10,
      "policy_id": 1,
      "name": "apache-logs",
      "managed_by": "user",
      "description": "Parses Apache access logs",
      "pipeline_hash": "abc123",
      "last_updated": "2026-01-01T12:00:00Z",
      "revision_number": 3,
      "no_input": false,
      "non_reloadable": false
    }
  ],
  "count": 1
}
```

---

### Get an agent pipeline

```
GET /api/pipelines/{id}/
```

Returns the full pipeline record including `lscl` and all performance settings.

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/pipelines/10/
```

```json
{
  "success": true,
  "pipeline": {
    "id": 10,
    "policy_id": 1,
    "name": "apache-logs",
    "managed_by": "user",
    "description": "Parses Apache access logs",
    "lscl": "input { beats { port => 5044 } } filter { grok { ... } } output { elasticsearch { ... } }",
    "pipeline_hash": "abc123",
    "last_updated": "2026-01-01T12:00:00Z",
    "revision_number": 3,
    "pipeline_workers": 1,
    "pipeline_batch_size": 128,
    "pipeline_batch_delay": 50,
    "queue_type": "memory",
    "queue_max_bytes": "1gb",
    "queue_checkpoint_writes": 1024,
    "no_input": false,
    "non_reloadable": false
  }
}
```

---

### Create an agent pipeline

```
POST /api/pipelines/
```

**Required role:** admin

```bash
curl -X POST https://logstashui.example.com/api/pipelines/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": 1,
    "name": "apache-logs",
    "lscl": "input { beats { port => 5044 } }\nfilter { grok { match => { \"message\" => \"%{COMBINEDAPACHELOG}\" } } }\noutput { elasticsearch { hosts => [\"localhost:9200\"] } }",
    "description": "Parses Apache access logs",
    "pipeline_workers": 2,
    "pipeline_batch_size": 256,
    "queue_type": "memory"
  }'
```

```json
{"success": true, "id": 10, "message": "Pipeline created successfully."}
```

| Field | Required | Notes |
|-------|----------|-------|
| `policy_id` | yes | Parent policy primary key |
| `name` | yes | Must be unique within the policy |
| `lscl` | yes | Full Logstash config text |
| `description` | no | |
| `pipeline_workers` | no | Default `1` |
| `pipeline_batch_size` | no | Default `128` |
| `pipeline_batch_delay` | no | Milliseconds, default `50` |
| `queue_type` | no | `memory` (default) or `persisted` |
| `queue_max_bytes` | no | Default `"1gb"` |
| `queue_checkpoint_writes` | no | Default `1024` |

---

### Update (save) an agent pipeline

```
PUT /api/pipelines/{id}/
```

**Required role:** admin. `pipeline_hash` is recomputed automatically on save.
Sets `has_undeployed_changes = true` on the parent policy.

```bash
curl -X PUT https://logstashui.example.com/api/pipelines/10/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "lscl": "input { beats { port => 5044 } }\nfilter { mutate { add_field => { \"env\" => \"prod\" } } }\noutput { elasticsearch { hosts => [\"localhost:9200\"] } }",
    "pipeline_workers": 4
  }'
```

```json
{"success": true, "id": 10, "message": "Pipeline saved successfully."}
```

---

### Delete an agent pipeline

```
DELETE /api/pipelines/{id}/
```

**Required role:** admin. Sets `has_undeployed_changes = true` on the parent policy.

```bash
curl -X DELETE https://logstashui.example.com/api/pipelines/10/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Pipeline 'apache-logs' deleted."}
```

---

### Deploy a policy

```
POST /api/pipelines/policies/{policy_id}/deploy/
```

**Required role:** admin

Snapshots the current user-authored pipelines and keystore as a new revision.
`current_revision_number` is incremented and `last_deployed_at` is set. Agents pick up the
change on their next check-in. SNMP-managed pipelines are excluded from the snapshot.

> [!NOTE]
> This endpoint is equivalent to `POST /api/policies/{id}/deploy/`. Both are available;
> use whichever fits your workflow.

```bash
curl -X POST https://logstashui.example.com/api/pipelines/policies/1/deploy/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{
  "success": true,
  "message": "Policy deployed as revision 4.",
  "revision_number": 4,
  "policy_id": 1,
  "policy_name": "Packaged Policy",
  "last_deployed_at": "2026-09-09T23:00:00Z"
}
```

---

## Elasticsearch Pipelines

Manage pipelines stored directly in Elasticsearch via the Logstash pipeline management API.
These pipelines are delivered to Logstash via centralized pipeline management (CPM), not
through the agent check-in flow. There is no deploy step — changes are live immediately.

### List Elasticsearch pipelines

```
GET /api/pipelines/es/{connection_id}/
```

Returns all pipelines stored in Elasticsearch for the given connection.

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/pipelines/es/17/
```

```json
{
  "connection_id": 17,
  "pipelines": [
    {
      "name": "apache-logs",
      "description": "Parses Apache access logs",
      "lscl": "input { beats { ... } } filter { ... } output { ... }",
      "last_modified": "2026-01-01T12:00:00.000Z",
      "username": "admin",
      "pipeline_settings": {
        "pipeline.workers": 2,
        "pipeline.batch.size": 128,
        "pipeline.batch.delay": 50,
        "queue.type": "memory",
        "queue.max_bytes": "1gb",
        "queue.checkpoint.writes": 1024
      }
    }
  ],
  "count": 1
}
```

---

### Get an Elasticsearch pipeline

```
GET /api/pipelines/es/{connection_id}/{name}/
```

```bash
curl -H "Authorization: ApiKey $KEY" \
  https://logstashui.example.com/api/pipelines/es/17/apache-logs/
```

```json
{
  "success": true,
  "pipeline": {
    "name": "apache-logs",
    "connection_id": 17,
    "description": "Parses Apache access logs",
    "lscl": "input { beats { ... } } filter { ... } output { ... }",
    "last_modified": "2026-01-01T12:00:00.000Z",
    "username": "admin",
    "pipeline_settings": { "pipeline.workers": 2 }
  }
}
```

`404` if the pipeline does not exist in Elasticsearch.

---

### Create an Elasticsearch pipeline

```
POST /api/pipelines/es/{connection_id}/
```

**Required role:** admin. Creates or replaces a pipeline in Elasticsearch immediately —
no deploy step required.

```bash
curl -X POST https://logstashui.example.com/api/pipelines/es/17/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "apache-logs",
    "lscl": "input { beats { port => 5044 } }\nfilter { grok { match => { \"message\" => \"%{COMBINEDAPACHELOG}\" } } }\noutput { elasticsearch { hosts => [\"localhost:9200\"] } }",
    "description": "Parses Apache access logs",
    "pipeline_workers": 2,
    "pipeline_batch_size": 128,
    "queue_type": "memory"
  }'
```

```json
{"success": true, "name": "apache-logs", "message": "Pipeline created."}
```

| Field | Required | Notes |
|-------|----------|-------|
| `name` | yes | Pipeline name in Elasticsearch |
| `lscl` | yes | Full Logstash config text |
| `description` | no | |
| `pipeline_workers` | no | Default `1` |
| `pipeline_batch_size` | no | Default `128` |
| `pipeline_batch_delay` | no | Default `50` ms |
| `queue_type` | no | `memory` (default) or `persisted` |
| `queue_max_bytes` | no | Default `"1gb"` |
| `queue_checkpoint_writes` | no | Default `1024` |

---

### Update an Elasticsearch pipeline

```
PUT /api/pipelines/es/{connection_id}/{name}/
```

**Required role:** admin. Fetches the existing pipeline first and merges — unspecified
settings retain their current values. Changes are live immediately.

```bash
curl -X PUT https://logstashui.example.com/api/pipelines/es/17/apache-logs/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "lscl": "input { beats { port => 5044 } }\nfilter { mutate { add_field => { \"env\" => \"prod\" } } }\noutput { elasticsearch { ... } }",
    "pipeline_workers": 4
  }'
```

```json
{"success": true, "name": "apache-logs", "message": "Pipeline updated."}
```

`404` if the pipeline does not exist in Elasticsearch.

---

### Delete an Elasticsearch pipeline

```
DELETE /api/pipelines/es/{connection_id}/{name}/
```

**Required role:** admin. Removes the pipeline from Elasticsearch immediately.

```bash
curl -X DELETE https://logstashui.example.com/api/pipelines/es/17/apache-logs/ \
  -H "Authorization: ApiKey $KEY"
```

```json
{"success": true, "message": "Pipeline 'apache-logs' deleted."}
```

---

## Simulate

Run a pipeline simulation synchronously. The simulation is executed by a running Logstash
simulate agent with per-filter Ruby instrumentation — each filter step captures a snapshot
of the event at that point in the pipeline.

```
POST /api/pipelines/simulate/
```

**Required role:** admin

The request blocks until results are returned or the timeout is reached. The agent must be
reachable and the pipeline filters must be valid Logstash config.

```bash
curl -X POST https://logstashui.example.com/api/pipelines/simulate/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "lscl": "input { beats { port => 5044 } }\nfilter { grok { match => { \"message\" => \"%{COMBINEDAPACHELOG}\" } } mutate { add_field => { \"env\" => \"prod\" } } }\noutput { elasticsearch { ... } }",
    "event": "192.168.1.1 - frank [10/Oct/2000:13:55:36 -0700] \"GET /apache_pb.gif HTTP/1.0\" 200 2326",
    "timeout": 30
  }'
```

**Using a saved pipeline by ID instead of raw LSCL:**

```bash
curl -X POST https://logstashui.example.com/api/pipelines/simulate/ \
  -H "Authorization: ApiKey $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_id": 10,
    "event": "192.168.1.1 - frank [10/Oct/2000:13:55:36 -0700] \"GET /apache_pb.gif HTTP/1.0\" 200 2326",
    "policy_id": 1,
    "timeout": 60
  }'
```

```json
{
  "success": true,
  "run_id": "f3a1b2c4-...",
  "slot_id": "3",
  "count": 1,
  "elapsed_ms": 1240,
  "results": [
    {
      "run_id": "f3a1b2c4-...",
      "message": "192.168.1.1 - frank ...",
      "snapshots": {
        "grok_step1": {
          "clientip": "192.168.1.1",
          "ident": "frank",
          "verb": "GET",
          "request": "/apache_pb.gif",
          "response": "200"
        },
        "mutate_step2": {
          "clientip": "192.168.1.1",
          "env": "prod"
        }
      }
    }
  ]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `lscl` | one of | Raw Logstash config. Mutually exclusive with `pipeline_id` |
| `pipeline_id` | one of | Load LSCL from a saved agent pipeline |
| `event` | yes | Sample log line or JSON string to process |
| `sim_connection_id` | no | Specific simulate-agent connection ID. Defaults to the session-sticky agent |
| `policy_id` | no | Source policy for keystore sync when the pipeline uses `${var}` references |
| `timeout` | no | Seconds to wait for results. Default `30`, maximum `180` |

**Error responses:**

`400` — missing required fields or pipeline has no filter plugins.

`404` — `pipeline_id` not found.

`408` — timeout. The agent may still be starting; retry with a longer `timeout` or preallocate a slot via the UI first.

`502` — the simulate agent rejected the pipeline or is unreachable.
