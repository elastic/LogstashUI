# Grok Debugger

**Utilities → Grok Debugger** shows what the Logstash [grok filter](https://www.elastic.co/docs/reference/logstash/plugins/plugins-filters-grok) extracts from sample log lines, without a Logstash node.

## Using it

1. Paste one or more log lines into **Sample Data**. Each line is tested as a separate event unless **Multiline Input** is checked.
2. Write a pattern in **Grok Pattern**. Type `%{` to search the built-in patterns. Each line in this box is a separate pattern, and each is reported separately.
3. Click **Simulate** or press **Ctrl+Enter**.

For example, this sample and pattern:

```
Oct  7 11:02:19 web01 sshd[2240]: Failed password for root from 203.0.113.9 port 41882
```

```
%{SYSLOGTIMESTAMP:timestamp} %{HOSTNAME:[host][name]} %{WORD:[process][name]}\[%{POSINT:[process][pid]:int}\]: %{WORD:[ssh][result]} %{DATA:[ssh][method]} for %{USERNAME:[user][name]} from %{IP:[source][ip]} port %{INT:[source][port]:int}
```

give `host.name: "web01"`, `process.pid: 2240` (a number, because of `:int`), `source.ip: "203.0.113.9"`, and so on.

### Pattern syntax

| Syntax | Meaning |
|---|---|
| `%{WORD}` | Match a built-in pattern without capturing it |
| `%{WORD:verb}` | Capture into the field `verb` |
| `%{IP:[source][ip]}` | Capture into a nested field |
| `%{NUMBER:bytes:int}` | Capture and convert. Only `int` and `float` are supported, as in Logstash |
| `(?<queue_id>[0-9A-F]{10,11})` | Inline named capture with your own regex |

Field names with dots, like `%{IP:client.ip}`, are **not** nested: Logstash creates one field literally named `client.ip`. Use `[client][ip]` for nesting.

## Options

### ecs_compatibility

Chooses which set of built-in patterns is loaded, like the filter's `ecs_compatibility` setting:

| Value | Patterns | Field names |
|---|---|---|
| `v8` (default) | ECS (`ecs-v1` folder) | ECS names, like `[source][address]` and `[http][request][method]` |
| `v1` | ECS (`ecs-v1` folder) | Same as v8. Logstash also uses the v1 patterns for v8 |
| `disabled` | Legacy | Older flat names, like `clientip` and `verb` |

Logstash 8 and later default to v8. If your pipelines rely on names like `clientip`, set the filter to `ecs_compatibility => disabled` and pick **disabled** here.

### Custom patterns

Use the same format as a `patterns_dir` file: one `NAME regex` per line, with `#` for comments. Custom patterns can use built-in ones (`MYLOG %{IP:ip} %{GREEDYDATA:rest}`) and override built-ins with the same name. They also appear in autocomplete with a **Custom** badge.

In Logstash, put these in a file under `patterns_dir`, or in the filter's `pattern_definitions`.

## Built-in patterns

The debugger ships the `logstash-patterns-core` 4.3.4 pattern files, byte-for-byte identical to the ones bundled with Logstash 9.5. That covers `grok-patterns`, `httpd`, `firewalls`, `haproxy`, `java`, `aws`, `zeek`, and the other files. Logstash loads all of them automatically, so any pattern that autocomplete suggests works in a stock Logstash without extra configuration.

Some formats, such as Postfix, are not in `logstash-patterns-core`. Patterns for those must be added as custom patterns, both here and in Logstash.

## Reading the results

Each line gets a card:

- **Match Found** shows the event fields grok would add.
- **No Match** shows `_grokparsefailure` (the tag Logstash adds) and where matching stopped. For example:
  - `Matched up to '%{IP:client} ', then '%{WORD:verb}' did not match '(GET) /index.html'`
  - `'%{IP:client}' was not found anywhere in the input`
- **Pattern compilation error** means the pattern itself is invalid. Misspelled names get suggestions: `pattern %{IPV:ip} not defined (did you mean IPV6, IPV4, IP?)`.

The debugger also warns about these common mistakes:

- **A dissect pattern** pasted into the grok debugger, like `%{clientip} %{verb}`.
- **An unescaped `[`**, as in `[%{HTTPDATE:ts}]`. In a regex, `[...]` matches a single character. Write `\[` and `\]` to match literal brackets.
- **Capturing into `message`**, as `%{SYSLOGLINE}` does. Logstash then turns `message` into a list of the original line and the capture. Add `overwrite => ["message"]` to the filter to replace it instead.

### Time limits

A badly written regex can take exponential time on some inputs. Each line is stopped after **2 seconds** and reported as `_groktimeout`, which matches the grok filter's tag. A single simulation request is stopped after **15 seconds**, and any remaining lines are marked as skipped. The server is never tied up by one pattern.

## How closely it matches Logstash

The debugger does not run Logstash. It has its own grok engine (`Utilities/grok.py`) that follows the code of `jls-grok` 0.11.5 and `logstash-filter-grok` 4.4.4, including behaviour that is easy to get wrong:

- How `%{...}` references expand, including the "Deep recursion" error for patterns that refer to themselves.
- Translating Ruby's Oniguruma regex syntax where Python differs. For example, `.` also matches newlines, `\w`, `\d` and `\s` only match ASCII, and `\h` is a hex digit.
- How captures become fields:
  - Empty captures are dropped.
  - A field captured twice becomes a list.
  - `:int` on `3.9` gives `3`, like Ruby's `to_i`.
  - Only the first capture of a repeated name is type-converted.

It was tested by running the same patterns and lines through **Logstash 9.5.5** and comparing the events field by field:

- **7,263 cases with zero differences.** These covered hand-written edge cases, every example from the plugins' own test suites, and custom pattern files, in both the ECS and legacy modes.
- **86 of those cases are kept as regression tests**, with the Logstash output as the expected value (`tests/Utilities/unit/test_grok.py`). Every bundled pattern is also compiled in each ECS mode.

## Differences from the grok filter

The debugger previews a single grok filter that matches the `message` field. These filter options are not available:

- `break_on_match`: each pattern line is tested and reported separately. In Logstash, a `match` list stops at the first pattern that matches.
- `overwrite`, `keep_empty_captures`, `named_captures_only`, `tag_on_failure`, `target`, and `timeout_millis`: the debugger always uses the defaults, apart from its own time limits above.
- Pattern files dropped into a `patterns/` folder in the Logstash home directory are not read. Paste them into **Custom patterns** instead.

## Related documentation

- **[Utilities overview](/docs/docs/logstashui/utilities/index.md)** - Both debuggers and when to use each
- **[Dissect Debugger](/docs/docs/logstashui/utilities/dissect_debugger.md)** - For logs with a fixed layout
- **[Pipeline Simulation](/docs/docs/logstashui/configuration/simulation.md)** - Test a whole pipeline on a real Logstash
