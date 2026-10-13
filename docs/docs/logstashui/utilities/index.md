# Utilities

LogstashUI includes two pattern debuggers under **Utilities**: one for grok and one for dissect. Paste sample log lines, write a pattern, and see the fields Logstash would extract, line by line, before putting the pattern in a pipeline.

| Debugger | Use it for | Page |
|---|---|---|
| **[Grok Debugger](/docs/docs/logstashui/utilities/grok_debugger.md)** | Logs with variable structure, where fields are found with regular expressions (`%{IP:[source][ip]}`) | **Utilities → Grok Debugger** |
| **[Dissect Debugger](/docs/docs/logstashui/utilities/dissect_debugger.md)** | Logs with a fixed layout, split on delimiters (`%{ts} %{level} %{msg}`). Faster than grok in Logstash, and simpler to write | **Utilities → Dissect Debugger** |

Rule of thumb: if every line puts the same fields in the same order with the same separators, use dissect. If the format varies or a field needs a regex to find, use grok. The two can be combined in a pipeline: dissect splits the line, then grok parses one of the pieces.

## How they work

Both debuggers run **inside LogstashUI**. They do not send anything to Logstash or to a LogstashAgent, so they work with no Logstash nodes connected and give results instantly.

To do that, each debugger is a **re-implementation** of the matching Logstash plugin in Python, not a call into Logstash itself:

- The grok engine follows `logstash-filter-grok` 4.4.4 and `jls-grok` 0.11.5, and ships the same `logstash-patterns-core` 4.3.4 pattern files that Logstash bundles.
- The dissect engine is a port of the `logstash-filter-dissect` 1.3.0 Java implementation.

Because "close to Logstash" is not good enough for a debugger, both engines are tested against real Logstash output, including the plugins' odd edge cases, not just the documented behaviour. The details of what was tested are on each debugger's page.

> [!NOTE]
> A re-implementation can drift from Logstash when the plugins change. The engines match the plugin versions listed above, which are the versions bundled with Logstash 9.5. If a result ever disagrees with your Logstash, trust Logstash and [report it](https://github.com/elastic/LogstashUI/issues/new) with the sample line and pattern.

## Common features

- **Line-by-line results.** Each sample line is an event. Every line gets its own card with the extracted fields, or the reason it failed. Turn on **Multiline Input** to treat the whole sample as one event (for example, a Java stack trace).
- **Code editors.** Inputs have line numbers and syntax highlighting. Runs of spaces and trailing whitespace are highlighted, because both grok and dissect are whitespace sensitive.
- **Explanations, not just "no match".** Failures say where matching stopped, and the debuggers warn about common mistakes, like pasting a dissect pattern into the grok debugger.
- **Keyboard shortcut.** Press **Ctrl+Enter** (**Cmd+Enter** on macOS) anywhere on the page to run the simulation.

## Debuggers vs. pipeline simulation

The debuggers test one filter's pattern against raw lines. To test a whole pipeline (several filters, conditionals, other plugins) on a real Logstash, use [Pipeline Simulation](/docs/docs/logstashui/configuration/simulation.md) in the pipeline editor.

## Documentation

- **[Grok Debugger](/docs/docs/logstashui/utilities/grok_debugger.md)** - Patterns, ECS modes, custom patterns, and how matching was verified
- **[Dissect Debugger](/docs/docs/logstashui/utilities/dissect_debugger.md)** - Dissect syntax, data type conversion, and how matching was verified
