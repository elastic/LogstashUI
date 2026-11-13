# Concepts and vocabulary

How LogstashUI's objects fit together and when a change goes live. Read this before changing anything.

## Objects

| Object | Tools | Live when |
|---|---|---|
| Connection | `connections_*` | Immediately. `CENTRALIZED` connections point at Elasticsearch; `AGENT` connections are enrolled LogstashAgent nodes. |
| Policy | `policies_*` | On `policies_deploy`. Holds agent pipelines, `logstash.yml`, `jvm.options`, `log4j2.properties`, and keystore entries. Agents pick up a deployed revision on their next check-in. |
| Agent pipeline | `pipelines_*` with `pipeline_id` (or `policy_id` to list and create) | On `policies_deploy` of its policy. Stored in LogstashUI. Identified by an integer `pipeline_id`. |
| CPM pipeline | `pipelines_*` with `connection_id` + `name` | Immediately on write. Stored in Elasticsearch through Centralized Pipeline Management; Logstash nodes using CPM on that connection pull it. Identified by `connection_id` + `name`. |
| SNMP objects | `snmp_*` | On `snmp_deploy_apply`. Devices, credentials, networks, profiles, and templates generate pipelines. |

Agent pipelines and CPM pipelines are both **Logstash pipelines** written in LSCL (Logstash configuration language), and the same `pipelines_*` tools handle both: pass the identifiers `pipelines_find` returns and the tool picks the right place. Neither is an Elasticsearch ingest pipeline. When a user says "ES pipeline" in LogstashUI they usually mean a CPM pipeline.

## Things that look alike

- **Same name, different place.** `asa-fixed` can exist as an agent pipeline in a policy and as a CPM pipeline on a connection. `pipelines_find` returns both; if the user doesn't say which, ask.
- **Generated pipelines.** Agent pipelines with `managed_by` set to `snmp` or `library` are generated. Change their source (the SNMP objects, or the library entry), not the pipeline.
- **Simulate agents.** `pipelines_simulate` runs on a policy of type `SIMULATE`. It changes nothing in any policy or connection.

## Roles

Tools whose description ends in "Admin only." need an `admin` API key; that includes every write, deploy, apply, and simulation. A `readonly` key isn't shown them. If the user asks for something no listed tool can do, or a call returns 403, tell them their key's role can't do it instead of looking for another way.
