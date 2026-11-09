# Changing and deploying

Use this whenever a change should reach running Logstash. Confirm with the user before every policy deploy and SNMP apply. CPM writes the user asked for need no extra confirmation.

## Agent pipelines and policies

1. Make the change: `pipelines_update`, `pipelines_create`, or `policies_update`. Nothing is live yet.
2. If the change touches filters, simulate the new config first (`pipelines_simulate` with `pipeline_id`) and show the user the result.
3. Call `policies_diff(policy_id)` and show the user what will change. It returns `pending_changes` and the names of what changed; report those rather than guessing. To show the actual edits, call it again with `detail=changes` for unified diffs of config files and pipeline LSCL. Keystore values are never shown, only key names.
4. Wait for the user to confirm, then call `policies_deploy(policy_id)`. Agents pick up the revision on their next check-in.

## CPM pipelines

CPM writes are live immediately; there is no diff or deploy step.

1. When the user asks for a CPM write, make it with `pipelines_update(connection_id, name)` (or `pipelines_create(connection_id)`, which overwrites a pipeline with the same name). Don't ask them to confirm a change they already asked for.
2. If you are writing filter logic the user didn't spell out, simulate it with `pipelines_simulate` and `lscl` first, and mention the result.
3. Tell the user the change is live.

## SNMP

1. Make the SNMP changes (`snmp_devices_create`, `snmp_credentials_update`, and so on).
2. Call `snmp_deploy_diff` and show the user the plan. It returns `counts` and one row per pipeline; report those counts rather than counting rows yourself. To show what changes inside specific pipelines, call it again with `detail=changes` and `pipelines=[names]`. The plan is cached for 60 seconds. If `has_changes` is false, tell the user there is nothing to deploy and stop.
3. After the user confirms, call `snmp_deploy_apply`. If more than 60 seconds passed, run `snmp_deploy_diff` again first.

## Never

- Deploy a policy or apply SNMP without showing the diff and getting a yes.
- Deploy to fix a problem you were only asked to diagnose.
- Edit a generated pipeline (`managed_by` set); change its source instead.
