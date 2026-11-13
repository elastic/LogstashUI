# When a tool fails

Error results carry a `hint`; follow it. The general rules:

| Status | Meaning | Do |
|---|---|---|
| 400 | Bad arguments | Fix the argument named in the error. If you don't know the right value, ask. |
| 401 | API key missing or invalid | Tell the user. Don't look for another key. |
| 403 | The key's role can't do this | Tell the user. Don't try another route. |
| 404 | No such ID or name | For a pipeline, use `pipelines_find`; for anything else, list the resource. Use the exact value, and ask if several could match. |
| 408 | Timed out | Retry once with the same arguments, then report and stop. If your client times out the call with no response, treat it as a 408. |
| 409 | A name is taken, or `code` is `protected`: the object ships with LogstashUI and no role can change it | For a name clash, ask for another name. For `protected`, don't retry; offer to create a custom copy under a new name. |
| 502 | Elasticsearch or a LogstashAgent failed | Report the error. `connections_test` can check a connection. |

## Stay on the interface

Use only the LogstashUI tools. If they fail or can't do the task, report what you tried and what came back, then stop. Don't switch to the REST API, the database, the Django shell, the web UI, config files, or credentials found on disk unless the user explicitly asks you to.

## Reporting a failure

Say which tool, the arguments that matter (no secrets), the status, and the error text. If you retried, say so. Suggest what the user can check, such as whether the simulate agent is running or the connection is reachable.
