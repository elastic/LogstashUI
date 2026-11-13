# MCP Server

LogstashUI serves a [Model Context Protocol](https://modelcontextprotocol.io) endpoint so AI
clients such as Cursor, Claude, and VS Code can manage pipelines, policies, connections, and
SNMP. Each MCP tool runs the matching [REST API](/docs/docs/logstashui/rest_api.md) endpoint, so permissions,
validation, and responses are identical.

---

## Connecting a client

Open **[Connection Manager](/ConnectionManager/) → MCP**, paste an API key, and copy the
generated client configuration. If you don't have a key yet, **+ Create** takes you to
**[Management](/Management) → [API Keys](/Management/ApiTokens)**.

| Setting | Value |
|---------|-------|
| URL | `https://<your-logstashui>/api/mcp` |
| Transport | Streamable HTTP |
| Header | `Authorization: ApiKey lsui_<prefix>_<secret>` |

Clients that only accept a bearer token can send `Authorization: Bearer lsui_<prefix>_<secret>`.

Each client spells a remote server differently. The MCP dialog has a tab for each of these;
the examples below use the same placeholders. To check the connection, reload the client and
ask it to "List the LogstashUI guides." Keep files that contain your key out of source control.

**Cursor:** `~/.cursor/mcp.json`, or `.cursor/mcp.json` in a project.

```json
{
  "mcpServers": {
    "logstashui": {
      "url": "https://logstashui.example.com/api/mcp",
      "headers": { "Authorization": "ApiKey lsui_<prefix>_<secret>" }
    }
  }
}
```

**Claude Code:** run in a terminal. Add `--scope user` to use it in every project. In a
`.mcp.json` file, the entry needs `"type": "http"`, as in the VS Code example.

```bash
claude mcp add --transport http logstashui "https://logstashui.example.com/api/mcp" \
  --header "Authorization: ApiKey lsui_<prefix>_<secret>"
```

**VS Code / GitHub Copilot:** `~/.copilot/mcp-config.json`, or `.mcp.json` at the workspace root.

```json
{
  "mcpServers": {
    "logstashui": {
      "type": "http",
      "url": "https://logstashui.example.com/api/mcp",
      "headers": { "Authorization": "ApiKey lsui_<prefix>_<secret>" }
    }
  }
}
```

**Codex:** `~/.codex/config.toml`. To keep the key out of the file, replace `http_headers`
with `bearer_token_env_var = "LOGSTASHUI_API_KEY"` and export that variable.

```toml
[mcp_servers.logstashui]
url = "https://logstashui.example.com/api/mcp"
http_headers = { "Authorization" = "ApiKey lsui_<prefix>_<secret>" }
```

**Other clients:** use the URL, transport, and header from the table above. A client that
only runs local (stdio) servers, such as Claude Desktop's config file, needs a bridge such as
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote).

A tool call acts as the key's owner. A key belonging to a `readonly` user only sees the tools
that role can use: admin-only tools (writes, deploys, simulation) are left out of the tool
list, and calling one anyway returns a 403.

> [!NOTE]
> LogstashUI serves TLS from its own product CA. Download it from
> `/.well-known/logstashui/ca.crt` and trust it in your client. For Node-based clients, set
> `NODE_EXTRA_CA_CERTS=/path/to/ca.crt`.

---

## Toolsets

There are about 55 tools. Many clients get slower or warn when there are too many tools, so
limit the list with `?toolsets=`:

```
https://logstashui.example.com/api/mcp?toolsets=pipelines,policies
```

| Toolset | Covers |
|---------|--------|
| `guides` | How-to guides for agents (`guides_list`, `guides_get`); keep this in any filtered list |
| `connections` | Elasticsearch and agent connections, connectivity tests |
| `pipelines` | Agent and Centralized Pipeline Management (CPM) pipelines, search, simulation |
| `policies` | Agent policies, deploy, clone, diff, enrollment tokens |
| `snmp` | Devices, credentials, networks, profiles, templates, deploy |

Omit `toolsets` to expose everything. An unknown name returns an error that lists the valid
toolsets. The old `security` toolset was removed; URLs that still name it keep working and
it is ignored.

---

## Tool behavior

- Tool names follow `<toolset>_<action>`, e.g. `pipelines_get`, `policies_deploy`,
  `snmp_devices_update`.
- Arguments are flat: path parameters (`pipeline_id`), query parameters (`policy_id` on
  `pipelines_list`), and body fields share one object.
- A few common slips are accepted and renamed before the call: `id` for a tool's only path
  parameter (`network_id`, `credential_id`, and so on), and `query` for `pipelines_find`'s
  `name`. Aliases aren't listed in the input schema; sending an alias and its argument with
  different values is an error.
- Read tools carry `readOnlyHint`, as do `connections_test`, `pipelines_simulate`, and
  `snmp_deploy_diff`, which use `POST` but change nothing. Deletes, deploys, SNMP apply, and key revocation carry
  `destructiveHint`, so clients can ask before running them.
- A REST error status (400 and above) comes back as a tool result with `isError: true` and the
  API's JSON error body, plus a `hint` field that tells the agent what to do next (for example,
  `pipelines_find` after a pipeline `404`).
- Successful writes whose effect isn't obvious add a `next_steps` field. Agent pipeline and
  policy edits say they aren't live until `policies_deploy`, CPM edits say they're live now,
  and SNMP edits point to `snmp_deploy_diff` → `snmp_deploy_apply`.
- `pipelines_find` locates a pipeline by name in every policy and on every CENTRALIZED
  connection in one call. Its `next_steps` depends on the result: which arguments to use for
  a single match, ask the user when there are several or only similar names, and say so when
  a connection couldn't be searched.
- `pipelines_recent` lists pipelines from every policy and CENTRALIZED connection, newest
  `last_modified` first, optionally `since` a timestamp. It answers "what changed lately" in one
  call; it records nothing, so it can't say who changed a pipeline or what changed.
- `snmp_deploy_diff` never returns `manual_keystore_values` (the plaintext secrets the UI shows
  for manual keystore setup); they come back as `[redacted]`. Community strings, passwords, and
  API keys inside the generated config are also `[redacted]` in `changes` and `full`.
- Every pipeline tool works on Logstash pipelines (LSCL). None of them touch Elasticsearch
  ingest pipelines. The same `pipelines_list`, `_get`, `_create`, `_update`, and `_delete`
  handle agent and CPM pipelines and pick the route from the arguments: `pipeline_id` (or
  `policy_id` to list and create) for agent pipelines, which go live on `policies_deploy`;
  `connection_id` (+ `name`) for CPM pipelines, which Logstash picks up without a deploy step.
  Passing both, or neither, is an error that says which to send, as is an argument that only
  applies to the other kind (`include_lscl` with `policy_id`).
- `pipelines_simulate` blocks until results arrive. Keep `timeout` under your client's tool
  timeout, which is often 60 seconds. Pass `events` (up to 100) instead of `event` to simulate
  a batch in one call on a single slot; events run about 1.5 seconds apart. Pass
  `connection_id` + `name` to simulate a CPM pipeline without copying its LSCL.

### Response size

Agents pay for every byte a tool returns, so a few tools default to a compact response over
MCP and take an argument to ask for more. The REST API keeps its full response by default.

| Tool | Argument | MCP default | Larger option |
|------|----------|-------------|---------------|
| `pipelines_simulate` | `detail` | `steps`: final event plus the fields each filter added, changed, or removed | `full`: raw per-filter snapshots, about 7 times larger. `final` is smaller still: final event only |
| `pipelines_list` with `connection_id` | `include_lscl` | `false`: names, descriptions, settings | `true`: every pipeline's full config |
| `policies_list`, `policies_get` | `include_config` | `false`: no config file contents | `true`: `logstash.yml`, `jvm.options`, `log4j2.properties` |
| `policies_diff` | `detail` | `summary`: pending change count and the names of changed config files, paths, pipelines, and keystore keys | `changes`: plus unified diffs of changed config files and pipeline LSCL. `full`: both complete snapshots |
| `snmp_deploy_diff` | `detail` | `summary`: `counts` and one row per pipeline | `changes`: plus a unified diff per pipeline, narrowed with `pipelines=[names]`. `full`: raw current and new config, often over 1 MB |

The defaults appear as `default` in each tool's input schema. See
[Simulating pipelines](/docs/docs/logstashui/agent_guides/simulation.md) for the `detail` fields.

### Guiding agents

Each piece of guidance goes in the channel the agent is reading at the moment it applies:

| Channel | The agent reads it | Put here | Source |
|---|---|---|---|
| Instructions | Once, when it connects | What LogstashUI is, the vocabulary, and rules for every task: confirm ambiguous names and deploys, find named pipelines with `pipelines_find`, stay on these tools | `_INSTRUCTIONS` in `API/mcp/views.py` |
| Tool description | When it picks a tool | What the tool does, and when not to use it | `TOOLS` in `API/mcp/tools.py` |
| Argument description | When it fills in a call | What each argument means and its limits | The tool's argument schemas |
| `hint` / `next_steps` | When a call returns | What to do with this result. Most tools use fixed text; `pipelines_find` writes it from what it found | `hints`, `next_steps`, and `guidance` on each tool |
| Guides | When it calls `guides_get` | Procedures for multi-step tasks, and the reasons behind them | [`agent_guides/`](/docs/docs/logstashui/agent_guides/concepts.md) |

Some rules appear in more than one channel on purpose. Not every client passes the
instructions to the model, so a rule that must not be missed also goes on the tool where it
applies. Deploy confirmation, for example, is in the instructions, on `policies_deploy`, and in
the `next_steps` of every edit. Anything else lives in one place.

Wording the agent must repeat to the user verbatim is a constant in `API/mcp/tools.py`, such
as `ASK_TO_BUILD_PIPELINE`. A guide that quotes it is tested to match.

Guides are served from the same files by the `guides_get` tool and `GET /api/guides/<topic>/`
(`concepts`, `pipeline-review`, `simulation`, `deploy`, `snmp`, `troubleshooting`). They are a
tool rather than MCP resources or prompts because most clients don't let the model read
resources on its own. Agent-facing text is added only by the MCP layer; REST responses stay
plain data.

When you change any of these, rerun the [MCP agent scenarios](/docs/docs/logstashui/mcp_scenarios.md).

### Not exposed over MCP

MCP keeps secrets and account control out of the model's reach:

- **User and API key management** (`/api/security/users/` and `/api/security/keys/`) is not
  available. Use the UI or the REST API.
- **Creating enrollment tokens** (`POST /api/policies/{id}/tokens/`) is not available, because
  the response contains the raw token.
- **Bootstrap** (`/api/security/bootstrap/`) is an unauthenticated setup flow and is not a tool.
- `policies_tokens_list` and `policies_tokens_get` return token metadata with `raw_token`,
  `encoded_token`, and `enroll_command` redacted. `policies_diff` redacts keystore values.

---

## Protocol details

The server is stateless. Each `POST` carries one JSON-RPC message and receives one
`application/json` response. There is no SSE stream (`GET` returns `405`) and no
`Mcp-Session-Id`. Supported protocol versions are `2025-06-18` and `2025-03-26`. The server
offers only the `tools` capability, without change notifications.

Browser requests with a foreign `Origin` header are rejected (DNS-rebinding protection).
Non-browser clients send no `Origin` and are unaffected.

Test with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector --cli https://logstashui.example.com/api/mcp \
  --transport http --header "Authorization: ApiKey $KEY" --method tools/list
```
