# Simulating pipelines

`pipelines_simulate` sends sample events through a pipeline's filters on a simulate agent. Nothing is saved or deployed.

## Finding the pipeline

When the user names or describes a pipeline, call `pipelines_find`. Pass the name, or a keyword when they describe one ("ASA logs" → `asa`). It searches every policy and every `CENTRALIZED` connection in one call; don't list policies or connections yourself. Its `next_steps` tells you what to do with the result:

- **One match:** simulate it with the `connection_id` + `name` or `pipeline_id` it returns. If the user only described the pipeline and there are also similar names, the match is just your keyword; list them all and ask which.
- **Several matches, or only similar names:** show the user each one's name, location, and `last_modified`, and ask which. Don't pick one yourself.
- **A connection couldn't be searched:** the pipeline may be there. Tell the user and ask how to proceed.
- **No match anywhere:** ask the user:

> This pipeline doesn't exist on any of your connections. Would you like for me to build one to simulate with? I won't save it until you tell me to, though.

Write your own config and simulate it with `lscl` only after the user says yes, and save it only if they ask.

## Choosing the config source

Pass exactly one:

- `connection_id` + `name` for a CPM pipeline.
- `pipeline_id` for an agent pipeline.
- `lscl` for config that isn't saved, such as a proposed fix. Input and output blocks are ignored.

Pass `policy_id` when the config uses `${VAR}` keystore references, so the simulate agent gets that policy's keystore.

## Events

- `event`: one log line or JSON string.
- `events`: up to 100 log lines or JSON objects, run on one slot. Each event takes about 1.5 seconds, so keep a call under about 30 events to fit a 60-second client timeout. Split larger sets into several calls.

## Detail levels

Choose the smallest level that answers the question:

| `detail` | Returns per event | Use for |
|---|---|---|
| `final` | `final` event, `dropped`, `dropped_by` | Checking many samples for parse failures or drops |
| `steps` (MCP default) | Same plus `steps`: each filter's `plugin`, config `id`, `ms`, and the fields it `added`, `changed`, or `removed`. Filters that changed nothing are left out | Finding which filter broke an event |
| `full` | Raw `results` with a full event copy per filter | Only when `steps` is missing something; it is large |

Field names in `steps` use Logstash references: top-level `message` or a literal dotted `event.code`, nested `[log][syslog][priority]`. Values longer than 200 characters are cut. `branches` appears when the conditional path changes.

## Reading results

- `complete: false` on an event means it timed out before the final event arrived.
- `dropped: true` means a `drop` filter ended the event; `dropped_by` names it.
- `ms` is one event's wall time per filter, and it is noisy. Compare across many samples before calling something slow.

## Errors

- **408**: the simulate agent didn't return results in time. The first run on a new config loads the pipeline and can be slow. Retry once with the same arguments; if it fails again, report it and stop. If your client times out the call with no response, treat it as a 408.
- **502**: the agent rejected the pipeline (often an LSCL error) or slot allocation failed. Report the error text.
- **404**: the config source wasn't found. List pipelines to get the exact ID or name.
