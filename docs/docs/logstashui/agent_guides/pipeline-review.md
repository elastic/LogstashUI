# Reviewing a pipeline

Use this when asked to review, audit, or improve a Logstash pipeline. A review changes nothing; edit only if the user asks afterward.

## Steps

1. **Find the pipeline.** Call `pipelines_find(name)` and follow its `next_steps`. Then read the config with `pipelines_get`, passing the `connection_id` + `name` or `pipeline_id` it returned.
2. **Read the config.** Note each conditional branch and what it expects the event to look like.
3. **Build samples.** Write realistic sample events that reach every branch, including the fallback or `else` paths, and at least one that should fail to parse. Prefer samples the user provides.
4. **Simulate.** Call `pipelines_simulate` with the same source (`pipeline_id`, or `connection_id` + `name`) and `events`, using the default `detail: steps`. For more than about 15 samples use `detail: final` first, then rerun the interesting ones with `steps`.
5. **Report.** Lead with what's broken, backed by simulation evidence, then improvements.

## What to check

- **Parse failures.** `_grokparsefailure`, `_dissectfailure`, `_jsonparsefailure`, `_dateparsefailure` in `tags`. Find which step added the tag in `steps`.
- **Field references.** A filter that reads a field another filter never wrote (for example writing `ciscotag` but reading `[cisco][asa][tag]`). Literal dotted names (`event.code`) and nested ones (`[event][code]`) are different fields.
- **Unintended drops.** `dropped: true` with `dropped_by` naming the filter. Check whether that branch should have matched.
- **Values.** Literal strings where a `%{field}` reference was meant, numbers left as strings, a missing `date` filter so `@timestamp` is ingest time.
- **Schema.** ECS field names and value sets if the output is Elasticsearch.
- **Cost.** Expensive patterns (unanchored grok, many alternatives, regex in conditionals). Per-step `ms` from a single event is noisy; call out relative cost only when it is consistently large across samples.

## Report format

For each finding give: the filter (`id` from the config when present), what goes wrong, the sample that shows it, and the fix as an LSCL snippet. Don't write the fix to the pipeline unless asked.
