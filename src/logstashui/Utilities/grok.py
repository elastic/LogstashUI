"""Logstash grok matching for the Grok Debugger.

Follows jls-grok 0.11 (pattern expansion, captures) and logstash-filter-grok 4.4
(how captures become event fields), using the logstash-patterns-core 4.3.4
pattern sets bundled in ``data/grok-patterns``. Oniguruma regex syntax is
translated to the ``regex`` module where the two differ.
"""

import difflib
import functools
import os
import re

import regex

from .dissect import MISSING, get_field, set_field

PATTERNS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'grok-patterns')
PATTERN_SETS = {'v8': 'ecs-v1', 'v1': 'ecs-v1', 'disabled': 'legacy'}
MAX_EXPANSIONS = 10000

# jls-grok's Grok::PATTERN_RE, with Ruby's \g<curly> written as (?&curly).
_PATTERN_RE = regex.compile(
    r"%\{(?<name>(?<pattern>[A-z0-9]+)(?::(?<subname>[@\[\]A-z0-9_:.-]+))?)"
    r"(?:=(?<definition>(?:(?:[^{}\\]+|\\.+)+|(?<curly>\{(?:(?>[^{}]+|(?>\\[{}])+)|((?&curly)))*\})+)+))?"
    r"[^}]*\}"
)
_NAMED_GROUP_RE = regex.compile(r"\(\?(?:<(?![=!])([^>]*)>|'([^']*)')")
# Ruby's (?m) is dotall; Python spells that (?s).
_INLINE_FLAGS_RE = regex.compile(r"\(\?[imx]*(?:-[imx]*)?[:)]")
# Oniguruma's \w \d \s are ASCII-only and \h is a hex digit.
_ESCAPE_CLASSES = {'w': 'a-zA-Z0-9_', 'd': '0-9', 's': r' \t\n\x0b\f\r', 'h': '0-9a-fA-F'}
_TO_I_RE = re.compile(r"\s*([+-]?\d+(?:_\d+)*)")
_TO_F_RE = re.compile(r"\s*([+-]?(?:\d+(?:_\d+)*(?:\.\d+(?:_\d+)*)?|\.\d+(?:_\d+)*)(?:[eE][+-]?\d+)?)")
_FLAGS = regex.V1 | regex.MULTILINE | regex.DOTALL


class GrokError(ValueError):
    """A grok pattern that Logstash would refuse to compile at pipeline start."""


def ruby_to_i(value):
    """Convert like Ruby's ``String#to_i``, which grok uses for ``:int``.

    Example:
        >>> [ruby_to_i(v) for v in ("42", "3.9", "-7 apples", "1_000", "abc")]
        [42, 3, -7, 1000, 0]
    """
    match = _TO_I_RE.match(value)
    return int(match.group(1).replace('_', '')) if match else 0


def ruby_to_f(value):
    """Convert like Ruby's ``String#to_f``, which grok uses for ``:float``.

    Example:
        >>> [ruby_to_f(v) for v in ("0.043", "1e3", ".5", "12abc", "abc")]
        [0.043, 1000.0, 0.5, 12.0, 0.0]
    """
    match = _TO_F_RE.match(value)
    return float(match.group(1).replace('_', '')) if match else 0.0


_CONVERTERS = {'int': ruby_to_i, 'float': ruby_to_f}


def parse_patterns(text):
    """Parse pattern-file text (``NAME regex`` per line) like jls-grok does.

    Comments start with ``#``. The definition is everything after the first
    run of whitespace, including trailing spaces.

    Example:
        >>> parse_patterns("# ids\\nQUEUEID [0-9A-F]{10,11}\\n")
        {'QUEUEID': '[0-9A-F]{10,11}'}
    """
    patterns = {}
    lines = text.split('\n')
    for line in [line + '\n' for line in lines[:-1]] + lines[-1:]:
        if re.match(r"\s*#", line):
            continue
        parts = re.split(r"\s+", line.lstrip(), maxsplit=1)
        if len(parts) == 2:
            patterns[parts[0]] = parts[1].removesuffix('\n').removesuffix('\r')
    return patterns


@functools.cache
def load_patterns(ecs_compatibility='v8'):
    """Return the bundled patterns Logstash loads for an ``ecs_compatibility`` mode.

    Args:
        ecs_compatibility: ``"v8"`` or ``"v1"`` (ECS patterns) or ``"disabled"`` (legacy).

    Example:
        >>> load_patterns("disabled")["USERNAME"]
        '[a-zA-Z0-9._-]+'
    """
    directory = os.path.join(PATTERNS_DIR, PATTERN_SETS[ecs_compatibility])
    patterns = {}
    for file_name in sorted(os.listdir(directory)):
        with open(os.path.join(directory, file_name), encoding='utf-8') as f:
            patterns.update(parse_patterns(f.read()))
    return patterns


def _expand(pattern, patterns):
    """Replace ``%{...}`` references until none are left (``Grok#compile``)."""
    patterns = dict(patterns)
    expanded = pattern
    for _ in range(MAX_EXPANSIONS):
        match = _PATTERN_RE.search(expanded)
        if not match:
            return expanded
        if match['definition'] is not None:
            patterns[match['pattern']] = match['definition']
        if match['pattern'] not in patterns:
            close = difflib.get_close_matches(match['pattern'], patterns, n=3)
            hint = f" (did you mean {', '.join(close)}?)" if close else ''
            raise GrokError(f"pattern {match[0]} not defined{hint}")
        body = patterns[match['pattern']]
        name = match['name']
        replacement = f"(?<{name}>{body})" if ':' in name else f"(?:{body})"
        expanded = expanded[:match.start()] + replacement + expanded[match.end():]
    raise GrokError(f"Deep recursion pattern compilation of {pattern!r}: "
                    f"more than {MAX_EXPANSIONS} pattern references, so a pattern probably refers to itself")


def _translate(expanded):
    """Rewrite Oniguruma syntax for the ``regex`` module.

    Returns:
        ``(python_regex, names)`` where group ``g{i}`` captures ``names[i]``.
    """
    out, names = [], []
    class_depth, i = 0, 0
    while i < len(expanded):
        char = expanded[i]
        if char == '\\' and i + 1 < len(expanded):
            escape = expanded[i + 1]
            body = _ESCAPE_CLASSES.get(escape.lower())
            if body and escape.islower():
                out.append(body if class_depth else f'[{body}]')
            elif body:
                out.append(f'[^{body}]')
            elif escape == 'z' and not class_depth:
                out.append(r'\Z')
            elif escape == 'Z' and not class_depth:
                out.append(r'(?=\n?\Z)')
            else:
                out.append(char + escape)
            i += 2
            continue
        if char == '[':
            if class_depth and expanded.startswith('[:', i) and (end := expanded.find(':]', i)) > 0:
                out.append(expanded[i:end + 2])
                i = end + 2
                continue
            class_depth += 1
            start = i + 1 + (expanded[i + 1:i + 2] == '^')
            if expanded[start:start + 1] == ']':
                start += 1
            out.append(expanded[i:start])
            i = start
            continue
        if class_depth:
            class_depth -= char == ']'
        elif char == '*' and out and out[-1] in ('?', '+', '*'):
            # Oniguruma reduces stacked repeats like .?* to .*; Python rejects them.
            out[-1] = '*'
            i += 1
            continue
        elif char == '(':
            if group := _NAMED_GROUP_RE.match(expanded, i):
                names.append(group[1] if group[1] is not None else group[2])
                out.append(f'(?P<g{len(names) - 1}>')
                i = group.end()
                continue
            if flags := _INLINE_FLAGS_RE.match(expanded, i):
                out.append(flags[0].replace('m', 's'))
                i = flags.end()
                continue
        out.append(char)
        i += 1
    return ''.join(out), names


def _compile(pattern, patterns):
    python_regex, names = _translate(_expand(pattern, patterns))
    try:
        return regex.compile(python_regex, _FLAGS), names
    except regex.error as e:
        raise GrokError(f"invalid regular expression: {e}") from None


def _capture_order(names):
    """Group indices in the order jls-grok yields them: by name, then position.

    Returns:
        ``(name, index, first)`` tuples. jls-grok overwrites its type variable
        while looping over a repeated name, so only the first group of each
        name gets ``:int``/``:float`` conversion.
    """
    order = {}
    for index, name in enumerate(names):
        order.setdefault(name, []).append(index)
    return [(name, index, n == 0) for name, indices in order.items() for n, index in enumerate(indices)]


def _field_and_type(capture_name):
    """Split ``PATTERN:field:type`` like jls-grok (``name.split(":")``)."""
    parts = capture_name.split(':')
    while parts and parts[-1] == '':
        parts.pop()
    parts += [None] * 3
    return parts[1] if parts[1] is not None else parts[0], parts[2]


def _cut_points(pattern):
    """Top-level positions around ``%{...}`` references, for failure hints."""
    cuts, depth, class_depth, i = set(), 0, 0, 0
    while i < len(pattern):
        char = pattern[i]
        if char == '\\':
            i += 2
            continue
        if class_depth:
            class_depth += (char == '[') - (char == ']')
        elif char == '[':
            class_depth = 1
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == '|' and depth == 0:
            return []
        elif char == '%' and depth == 0 and (ref := _PATTERN_RE.match(pattern, i)):
            cuts.update((i, ref.end()))
            i = ref.end()
            continue
        i += 1
    return sorted(c for c in cuts if 0 < c < len(pattern) and pattern[c] not in '?*+{')


def _quote(text, limit=40):
    if len(text) > limit:
        text = text[:limit] + '…'
    return "'" + text.replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r') + "'"


class Grok:
    """A compiled grok pattern, as the Logstash grok filter would build it.

    Args:
        pattern: Grok pattern, e.g. ``"%{IP:[client][ip]} %{WORD:verb}"``.
        patterns: Available pattern definitions, usually ``load_patterns()``
            plus custom patterns.

    Raises:
        GrokError: If the pattern references an undefined pattern or is not a
            valid regular expression.

    Example:
        >>> grok = Grok("%{IP:[client][ip]} %{NUMBER:bytes:int}", load_patterns())
        >>> grok.match("10.0.0.1 512")
        {'client': {'ip': '10.0.0.1'}, 'bytes': 512}
    """

    def __init__(self, pattern, patterns):
        self.pattern = pattern
        self._patterns = patterns
        self._regex, names = _compile(pattern, patterns)
        self._captures = []
        for name, index, first in _capture_order(names):
            field, datatype = _field_and_type(name)
            self._captures.append((f'g{index}', field, datatype if first else None))
        self._prefixes = None

    @property
    def fields(self):
        """Field names this pattern captures into."""
        return [field for _, field, _ in self._captures]

    def match(self, text, timeout=None):
        """Match ``text`` and return the fields grok would set, or None.

        The event starts with ``message`` set to ``text``, so capturing into
        ``message`` turns it into ``[text, capture]`` as it does in Logstash.

        Raises:
            TimeoutError: If matching takes longer than ``timeout`` seconds.

        Example:
            >>> Grok("%{WORD:a} %{WORD:a} %{DATA:empty}$", load_patterns()).match("x y ")
            {'a': ['x', 'y']}
        """
        found = self._regex.search(text, timeout=timeout)
        if found is None:
            return None
        event = {'message': text}
        for group, field, datatype in self._captures:
            value = found.group(group)
            if value is not None and datatype in _CONVERTERS:
                value = _CONVERTERS[datatype](value)
            if value is None or value == '':
                continue
            existing = get_field(event, field)
            if existing is MISSING:
                set_field(event, field, value)
            elif isinstance(existing, list):
                existing.append(value)
            elif isinstance(existing, str):
                set_field(event, field, [existing, value])
        if isinstance(event['message'], str):
            del event['message']
        return event

    def explain_failure(self, text, timeout=None):
        """Describe how far the pattern got before it stopped matching.

        Returns:
            A sentence naming the last part that matched and the part that did
            not, or None if the pattern can't be split into parts.

        Example:
            >>> Grok("%{IP:ip} %{WORD:verb} %{INT:status}", load_patterns()).explain_failure("1.2.3.4 GET ok")
            "Matched up to '%{IP:ip} %{WORD:verb} ', then '%{INT:status}' did not match 'ok'"
        """
        if self._prefixes is None:
            self._prefixes = []
            for cut in _cut_points(self.pattern):
                try:
                    self._prefixes.append((cut, _compile(self.pattern[:cut], self._patterns)[0]))
                except GrokError:
                    pass
        if not self._prefixes:
            return None
        low, high = 0, len(self._prefixes)
        while low < high:
            middle = (low + high) // 2
            if self._prefixes[middle][1].search(text, timeout=timeout):
                low = middle + 1
            else:
                high = middle
        cuts = [cut for cut, _ in self._prefixes]
        next_cut = cuts[low] if low < len(cuts) else len(self.pattern)
        if low == 0:
            return f"{_quote(self.pattern[:next_cut])} was not found anywhere in the input"
        cut = cuts[low - 1]
        end = self._prefixes[low - 1][1].search(text, timeout=timeout).end()
        matched = self.pattern[:cut]
        matched = matched if len(matched) <= 40 else '…' + matched[-39:]
        rest = text[end:]
        return (f"Matched up to {_quote(matched)}, then {_quote(self.pattern[cut:next_cut])} "
                f"did not match {_quote(rest) if rest else 'the end of the input'}")


def looks_like_dissect(pattern):
    """Guess whether a pattern was written for dissect rather than grok.

    Example:
        >>> looks_like_dissect("%{clientip} %{} [%{+ts}]")
        True
        >>> looks_like_dissect("%{IP:client} %{WORD}")
        False
    """
    return bool(re.search(r"%\{(?:[+?&*}]|[a-z_][a-z0-9_.]*(?:->)?\})", pattern))
