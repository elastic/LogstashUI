# Dissect Debugger

**Utilities → Dissect Debugger** shows what the Logstash [dissect filter](https://www.elastic.co/docs/reference/logstash/plugins/plugins-filters-dissect) extracts from sample log lines, without a Logstash node.

Dissect splits a line on the literal text between fields, with no regular expressions involved. That makes it faster and simpler than grok for logs that always have the same layout.

## Using it

1. Paste one or more log lines into **Sample Data**. Each line is tested as a separate event unless **Multiline Input** is checked.
2. Write a pattern in **Dissect Pattern**. Each line in this box is a separate pattern, and each is reported separately.
3. Click **Simulate** or press **Ctrl+Enter**.

For example:

```
Oct 07 11:02:14 INFO   main: service started
```

```
%{ts} %{+ts} %{+ts} %{level->} %{thread}: %{msg}
```

gives `ts: "Oct 07 11:02:14"`, `level: "INFO"`, `thread: "main"` and `msg: "service started"`.

## Pattern syntax

| Syntax | Meaning |
|---|---|
| `%{field}` | Capture up to the next delimiter. The last field takes the rest of the line |
| `%{}` or `%{?name}` | Match a value but don't keep it |
| `%{field->}` | Skip repeated delimiters after the field, for padded columns |
| `%{+field}` | Append to an earlier field, joined with the delimiter text in between |
| `%{+field/2}` | Append in a set order (`/1`, `/2`, ...) instead of left to right |
| `%{?key}=%{&key}` | Use one captured value as the name of another field (key/value pairs) |
| `%{[a][b]}` | Capture into a nested field |

Everything between fields is a literal delimiter, including spaces. Two spaces in the pattern need two spaces in the line, unless `->` is used. The editor highlights runs of spaces so these are easy to spot.

> [!TIP]
> `->` only skips repeats of the delimiter that follows the field. In `%{level->} [%{thread}]` the delimiter is ` [`, so `INFO   [main]` gives `level: "INFO  "` with the extra spaces kept. Use `%{level->} %{thread}` when the padding is plain spaces.

## Options

### convert_datatype

One conversion per line, in the form `field => int` or `field => float`, like the filter's `convert_datatype` setting. These are the only two types dissect supports.

```
bytes => int
duration => float
```

As in Logstash, converting a field that the pattern never captured adds a tag such as `_dataconversionnullvalue_bytes_int` instead of failing.

## Reading the results

Each line gets a card:

- **Match Found** shows the event fields dissect would add.
- **No Match** shows `_dissectfailure` (the tag Logstash adds) and why it failed. For example:
  - `Delimiter ' [' after %{level} was not found`
  - `Input does not start with '['`
- **Pattern errors** mean the pattern itself is invalid, such as `%{+&x}` (append and indirect can't be combined).

If the pattern looks like grok (`%{IP:client}` or `%{WORD:verb}`), the debugger says so and points to the Grok Debugger.

## How closely it matches Logstash

The debugger does not run Logstash. It has its own dissect engine (`Utilities/dissect.py`), a port of the Java implementation in `logstash-filter-dissect` 1.3.0, the version bundled with Logstash 9.5. It copies the plugin's behaviour, including cases that surprise people:

- Fields with nothing between them, like `%{a}%{b}`, never match, because dissect needs a delimiter to split on.
- `*` is not a prefix: `%{*k}` is just a field named `*k`.
- `->` padding also collapses repeated multi-character delimiters, such as `, , ,`.
- Append order, indirect fields, and the order fields appear in the event follow the plugin, not the documentation's simplified description.
- There is no `append_separator` option, because Logstash doesn't have one.

The tests (`tests/Utilities/unit/test_dissect.py`) cover the examples from the plugin documentation, plus matches and failures whose expected output was captured from real Logstash runs.

## Differences from the dissect filter

The debugger previews one `mapping` against the `message` field, and only `convert_datatype` is configurable. `tag_on_failure` always uses its default, and each pattern line is tested on its own rather than as several mappings in one filter.

## Related documentation

- **[Utilities overview](/docs/docs/logstashui/utilities/index.md)** - Both debuggers and when to use each
- **[Grok Debugger](/docs/docs/logstashui/utilities/grok_debugger.md)** - For logs that need regular expressions
- **[Pipeline Simulation](/docs/docs/logstashui/configuration/simulation.md)** - Test a whole pipeline on a real Logstash
