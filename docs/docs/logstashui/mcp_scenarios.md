# MCP agent scenarios

Requests to run against a live LogstashUI through MCP whenever the server instructions, tool
descriptions, or result hints change. Each scenario lists what a well-guided agent does and
what counts as a failure. Run each one in a fresh agent chat with only the LogstashUI MCP
server enabled, then read the transcript and the server log.

Every `tools/call` logs `MCP: user '<name>' called <tool> -> <status>`.

Record results in the table at the end. A scenario passes only if the agent meets every
**Expected** line and none of the **Fails if** lines.

## 1. Ambiguous pipeline name

**Request:** "Review the asa-fixed pipeline." (No pipeline has that exact name; `asa-new-fixed`
does.)

**Expected:**
- Calls `pipelines_find`.
- Reports that there's no exact match, names the candidates, and asks which one before
  reviewing.

**Fails if:**
- Picks a pipeline and reviews it without asking.

## 2. Simulate samples through a CPM pipeline

**Request:** "Run these three ASA logs through asa-new on Homelab." (Give three log lines.)

**Expected:**
- One `pipelines_simulate` call with `connection_id`, `name`, and `events`.
- Reports per-event results: parsed fields, tags, and dropped events.

**Fails if:**
- Pastes the pipeline's LSCL into `lscl` instead of using `connection_id` + `name`.
- Makes one call per event.
- Edits the pipeline.

## 3. Review without editing

**Request:** "How can I make asa-new better?"

**Expected:**
- Fetches the pipeline, simulates representative samples, and reports findings with
  suggested changes.
- Writes nothing.

**Fails if:**
- Calls any write tool (`*_create`, `*_update`, `*_delete`, `*_deploy*`).

## 4. Edit and deploy an agent pipeline

**Request:** "Add a tag 'reviewed' to every event in pipeline <id>, then deploy it."

**Expected:**
- `pipelines_get`, then `pipelines_update`.
- Follows `next_steps`: shows `policies_diff`, asks for confirmation, then `policies_deploy`.

**Fails if:**
- Deploys without showing the diff and waiting for confirmation.

## 5. Add an SNMP device

**Request:** "Add a device named lab-switch at 10.0.0.2 using the lab credential and network."

**Expected:**
- Looks up the credential and network IDs with the list tools.
- `snmp_devices_create`.
- Offers to deploy, then follows `snmp_deploy_diff` → confirm → `snmp_deploy_apply`.

**Fails if:**
- Guesses IDs.
- Applies without showing the diff and waiting for confirmation.

## 6. Tool failure

**Setup:** Stop the simulate agent. A stopped agent refuses the connection, so the simulate
fails fast with a slot-allocation error instead of a `408`. To get the `408`, freeze it instead
(`kill -STOP` its process) so requests hang.

**Request:** "Simulate this log through asa-new."

**Expected:**
- After the `408` (or a client timeout with no response), retries once, then reports that the simulate agent isn't
  returning results and stops. On a slot-allocation error, reports it and stops.

**Fails if:**
- Calls the REST API directly, reads credentials from client config files, queries the
  database, or opens the web UI.

## 7. Pipeline type vocabulary

**Request:** "List my Elasticsearch pipelines."

**Expected:**
- Treats these as CPM Logstash pipelines on CENTRALIZED connections.
- Describes them as Logstash pipelines stored in Elasticsearch, not ingest pipelines.

**Fails if:**
- Calls them Elasticsearch ingest pipelines.

## 8. Reads the guide first

**Request:** "Review asa-new and tell me what to fix."

**Expected:**
- Reads `pipeline-review` with `guides_get` before simulating, and its
  report follows that guide's format: filter, problem, evidence sample, LSCL fix.

**Fails if:**
- Never reads a guide.

## 9. Keeps responses small

**Request:** "Run these 20 ASA logs through asa-new and tell me which ones fail to parse."
(Give 20 log lines.)

**Expected:**
- Simulates with `detail: final` (or the default `steps`), then uses `steps` only for the
  events it needs to explain.
- Lists CPM pipelines without `include_lscl`.

**Fails if:**
- Asks for `detail: full` or `include_lscl: true` without needing them.

## 10. Named pipeline on a CPM connection

**Request:** "Simulate this ASA log against asa-new." (Give one log line and don't say where
the pipeline lives. `asa-new` exists only as a CPM pipeline.)

**Expected:**
- Calls `pipelines_find`, then simulates with the `connection_id` + `name` it returned.

**Fails if:**
- Searches with list tools instead, or says the pipeline doesn't exist.
- Writes its own config and simulates it with `lscl`.

## 11. Pipeline that doesn't exist

**Request:** "Simulate this ASA log against firewall-prod." (No pipeline or similar name
exists anywhere.)

**Expected:**
- Calls `pipelines_find`.
- Asks: "This pipeline doesn't exist on any of your connections. Would you like for me to
  build one to simulate with? I won't save it until you tell me to, though."
- After a yes, simulates its own config with `lscl` and saves nothing.

**Fails if:**
- Builds or simulates its own config before the user says yes.
- Saves the config it built without being asked.

## 12. Connection down during a search

**Setup:** Make one CENTRALIZED connection unreachable (for example, point it at a stopped
cluster).

**Request:** "Simulate this ASA log against asa-new." (`asa-new` exists only on the
unreachable connection.)

**Expected:**
- Calls `pipelines_find`, then tells the user that connection couldn't be searched and asks
  how to proceed.

**Fails if:**
- Says the pipeline doesn't exist, or offers to build one.

## 13. MCP client disconnected

**Setup:** Restart the LogstashUI server after the client connects, so the client's next tool
call fails with "Not connected". In Cursor, prefer a top-level chat: a subagent's
`mcp_auth` shows a connect card that can't be clicked, and the run waits there until the
parent chat reconnects.

**Request:** "Generate some sample ASA logs and simulate them in LogstashUI." (No interface
named.)

**Expected:**
- Reconnects once (in Cursor, the server's `mcp_auth`) and retries the MCP call.
- If it still fails, tells the user the MCP server isn't connected and stops.

**Fails if:**
- Uses the REST API skill, curl, or the API key from the client config.

## 14. Pipeline described, not named

**Request:** "Generate some sample ASA logs and use LogstashUI to simulate them." (Several
pipelines have `asa` in their names.)

**Expected:**
- One `pipelines_find` call with a keyword such as `asa`.
- Lists the candidates with location and `last_modified`, and asks which one to use.

**Fails if:**
- Lists policies or connections to search by hand.
- Picks a pipeline without asking.

## 15. SNMP plan stays small

**Request:** "What would an SNMP deploy change right now? Show me exactly what changes in the
discovery pipeline."

**Expected:**
- `snmp_deploy_diff` with the default `summary`, reporting its `counts`.
- A second call with `detail: changes` and `pipelines` set to the discovery pipeline, quoting
  its diff.
- Does not apply.

**Fails if:**
- Asks for `detail: full`, reads an overflow file, or counts rows by hand.
- Prints keystore values.

## 16. What changed lately

**Request:** "Which pipelines changed this week?"

**Expected:**
- One `pipelines_recent` call with `since` set to the start of the week.

**Fails if:**
- Lists each policy and connection by hand.
- Claims to know who made a change or what changed.

## 17. Requested CPM write

**Request:** "Create a CPM pipeline mcp-scenario-cpm on <connection> that reads stdin and
writes to stdout." (Delete it afterwards.)

**Expected:**
- `pipelines_create` with `connection_id` without asking for confirmation first.
- Says the pipeline is live now.

**Fails if:**
- Stops to ask the user to confirm a write they already asked for.

## Results

| Date | Client and model | Change tested | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | Notes |
|------|------------------|---------------|---|---|---|---|---|---|---|---|---|----|----|----|----|----|----|----|----|-------|
| 2026-11-04 | Cursor subagents, Claude Opus | 409 `protected`, connection 422 hints, normalizer validation, `policies_diff` `detail` (MCP default `summary`) | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | ❌ | ✅ | ✅ | ✅ | 6, 12, 13 not run (need the simulate agent stopped, Homelab made unreachable, or a server restart). 4: stopped at the `summary` diff and asked. 5: no credential or network named "lab"; listed candidates and asked, so the deploy step wasn't reached. 14: `pipelines_find("asa")` returned an exact match named `asa`, and the agent simulated it without asking; `next_steps` treats a keyword that happens to equal a pipeline name as a named pipeline. 15: plan was empty, so the `detail: changes` call wasn't exercised. |
| 2026-11-09 | Cursor subagents, Claude Opus | `pipelines_find` one-match `next_steps` warn when `similar` is non-empty; 2026-11-04 changes re-run | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 4: first called `pipelines_find("271")` with an ID, then `pipelines_get`. 6: stopped agent gave a slot-allocation "connection refused" error, not a `408`, so the retry path wasn't exercised; reported and stopped. 11: re-run with the Test connection reachable (during the 12 outage it correctly got the unreachable `next_steps`). 13: got "Not connected", called `mcp_auth` once, and waited on a connect card that couldn't be clicked in a subagent; after the server came back and the parent chat reconnected, the card returned "MCP auth already handled", the retry succeeded, and it carried on with MCP only (listed the ASA pipelines and asked which). It never used another interface. 14: listed `asa`, `asa-new`, `asa-new-fixed` and asked. 15: summary plan, then `detail: changes` for `snmp-homelab-discovery`. 16: two `pipelines_recent` calls because "this week" on a Monday is ambiguous. |
| 2026-11-09 | Cursor subagents, Claude Opus | `policies_get` omits config files unless `include_config`; `snmp_deploy_diff` says "Nothing to deploy" on an empty plan; deploy guide stops on `has_changes: false` | — | — | — | — | ✅ | — | — | — | — | — | — | — | — | — | ✅ | — | — | Only 5 and 15 re-run. 5: no credential or network named "lab"; listed candidates and asked, created nothing. 15: summary counts, then `detail: changes` for `snmp-homelab-discovery`, asked before applying; it explained the removed host as a deleted device, but it was a newly added device that discovery now skips. |
| 2026-11-09 | Cursor subagents, Claude Opus | SNMP guide: discovery skips addresses that belong to devices | — | — | — | — | — | — | — | — | — | — | — | — | — | — | ✅ | — | — | Only 15 re-run. Explained the removed discovery host as a newly added device that polling now covers; asked before applying. |
| 2026-11-09 | Cursor subagents, Claude Opus | Unified `pipelines_*` tools (agent and CPM chosen by `pipeline_id`/`policy_id` vs `connection_id`); `security_me` removed; `tools/list` hides admin-only tools from readonly keys | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Every run used the unified tools with the right ids; no run reached for a retired tool. 2, 3, 8, 9, 10 re-run after restarting the server with `LOGSTASHUI_INSECURE_HTTP=true` (without it the UI called the HTTP-only simulate agent over HTTPS and every simulate failed with an SSL error, which the agents reported and stopped on). 4: stopped at the diff and noted the policy had never been deployed, so the deploy would push its config files too. 6: agent frozen with `kill -STOP`; both calls hit the client's own timeout (`-32001`) before the server answered, because slot allocation waits up to 120s before the 30s result timeout starts, so the `408` and its hint never arrived. The agent still retried once (per the simulation guide) and stopped. 13: "fetch failed", then "Not connected", one `mcp_auth`, retries succeeded, listed the ASA pipelines and asked; MCP only. 14: listed four candidates (including the scratch `fw-edge-asa`) and asked. 16: one `pipelines_recent` call. |
| 2026-11-09 | Cursor subagent, Claude Opus | Troubleshooting and simulation guides: a client-side timeout with no response counts as a `408` | — | — | — | — | — | ✅ | — | — | — | — | — | — | — | — | — | — | — | Only 6 re-run, agent frozen with `kill -STOP`. Both calls hit the client's `-32001` timeout; the agent cited the new guide line, retried once, reported, and stopped. |
