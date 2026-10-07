"""Pure-Python port of the Logstash dissect filter.

Lets the Dissect Debugger preview ``logstash-filter-dissect`` results without
a running Logstash. It follows the plugin's Java implementation
(``org.logstash.dissect``), including its quirks. Supported syntax:

* ``%{field}`` capture up to the next delimiter (the last field takes the rest)
* ``%{}`` / ``%{?name}`` skip a value
* ``%{field->}`` skip repeated delimiters after the field (right padding)
* ``%{+field}`` / ``%{+field/N}`` append values, optionally ordered by ``N``
* ``%{?key}`` (or any field named ``key``) with ``%{&key}`` use one value as another's field name
* ``[a][b]`` field references produce nested objects

Example:
    >>> Dissector("%{ts} %{+ts} %{level->} %{msg}").match("Oct 07 INFO   started")
    {'ts': 'Oct 07', 'level': 'INFO', 'msg': 'started'}
"""

import re
from dataclasses import dataclass
from decimal import Decimal

_DELIMITER_FIELD_RE = re.compile(r"(.*?)%\{([^}]*?)}", re.DOTALL)
_FINAL_DELIMITER_RE = re.compile(r"[^}]+$")
_SUFFIX = r"(/\d{1,2}|->|/\d{1,2}->|->/\d{1,2})"
_SUFFIX_ONLY_RE = re.compile(_SUFFIX + "?")
_SUFFIX_RE = re.compile(r"(.+?)" + _SUFFIX + "?")
_FIELD_REFERENCE_RE = re.compile(r"^(\[[^\[\]]+\])+$")
# The number formats java.math.BigDecimal accepts.
_BIG_DECIMAL_RE = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?")
_CONVERTERS = {"int": lambda value: int(Decimal(value)), "float": lambda value: float(Decimal(value))}
_ORDINALS = {"skip": 0, "normal": 1, "append": 100, "indirect": 1000}
_GROK_REFERENCE_RE = re.compile(r"%\{[A-Z][A-Z0-9_]*:[^}]*\}")
_REGEX_ESCAPE_RE = re.compile(r"\\[\[\]().sdwSDW]")
MISSING = object()


def _quote(text):
    return "'" + text.replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r") + "'"


def looks_like_grok(pattern):
    """Guess whether a pattern was written for grok rather than dissect.

    Args:
        pattern: A pattern entered in the Dissect Debugger.

    Returns:
        True if it contains a grok reference like ``%{WORD:name}`` or a regex
        escape like ``\\[`` or ``\\s``.

    Example:
        >>> looks_like_grok("%{DATA:program}\\\\[%{POSINT:pid}\\\\]")
        True
        >>> looks_like_grok("%{IP} [%{ts}]")
        False
    """
    return bool(_GROK_REFERENCE_RE.search(pattern) or _REGEX_ESCAPE_RE.search(pattern))


class DissectError(ValueError):
    """Raised when a dissect pattern or option is invalid."""


class DissectFailure(Exception):
    """Raised when input does not match the pattern (Logstash tags ``_dissectfailure``)."""


@dataclass
class _Field:
    id: int
    raw: str
    name: str
    kind: str  # skip, normal, append, indirect
    ordinal: int
    previous: str
    next: str = None
    previous_greedy: bool = False
    next_greedy: bool = False


def _name_suffix(spec):
    if _SUFFIX_ONLY_RE.fullmatch(spec):
        return "", spec
    match = _SUFFIX_RE.fullmatch(spec)
    if match:
        return match.group(1), match.group(2) or ""
    return spec, ""


def _parse_field(field_id, raw, previous):
    if not raw or raw[0] == "?":
        kind, (name, suffix) = "skip", _name_suffix(raw[1:])
    elif raw.startswith(("+&", "&+")):
        raise DissectError(f"%{{{raw}}} cannot combine the append (+) and indirect (&) prefixes")
    elif raw[0] in "+&":
        if len(raw) == 1:
            raise DissectError(f"%{{{raw}}} is a prefix without a field name")
        kind = "append" if raw[0] == "+" else "indirect"
        name, suffix = _name_suffix(raw[1:])
        if not name:
            raise DissectError(f"%{{{raw}}} is missing a field name")
    else:
        kind, (name, suffix) = "normal", _name_suffix(raw)

    ordinal = _ORDINALS[kind]
    if kind == "append":
        digits = re.search(r"\d+", suffix)
        if digits:
            ordinal += int(digits.group())
    return _Field(field_id, raw, name, kind, ordinal, previous, next_greedy="->" in suffix)


def field_path(name):
    if _FIELD_REFERENCE_RE.match(name):
        return re.findall(r"\[([^\[\]]+)\]", name)
    return [name]


def get_field(target, name):
    for part in field_path(name):
        if not isinstance(target, dict) or part not in target:
            return MISSING
        target = target[part]
    return target


def set_field(target, name, value):
    parts = field_path(name)
    for part in parts[:-1]:
        if not isinstance(target.get(part), dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value


class Dissector:
    """A compiled dissect pattern.

    Args:
        pattern: Dissect mapping, e.g. ``"%{clientip} - %{user} [%{ts}]"``.
        convert_datatype: Optional ``{field: "int" | "float"}`` conversions.

    Raises:
        DissectError: If the pattern or conversions are invalid.

    Example:
        >>> Dissector("%{?k}=%{&k}").match("user=alice")
        {'user': 'alice'}
    """

    def __init__(self, pattern, convert_datatype=None):
        self.convert_datatype = dict(convert_datatype or {})
        for field_name, datatype in self.convert_datatype.items():
            if datatype.lower() not in _CONVERTERS:
                raise DissectError(f"Unsupported datatype '{datatype}' for '{field_name}' (use int or float)")

        self._fields = []
        for match in _DELIMITER_FIELD_RE.finditer(pattern):
            field = _parse_field(len(self._fields), match.group(2), match.group(1))
            if self._fields:
                self._fields[-1].next = field.previous
                field.previous_greedy = self._fields[-1].next_greedy
            self._fields.append(field)
        if not self._fields:
            raise DissectError("Pattern contains no %{} fields")

        final = _FINAL_DELIMITER_RE.search(pattern)
        if final:
            skip = _parse_field(len(self._fields), "?auto_added_skip", final.group())
            self._fields[-1].next = skip.previous
            skip.previous_greedy = self._fields[-1].next_greedy
            self._fields.append(skip)

        self._prefix_length = len(self._fields[0].previous)
        self._saveable = sorted((f for f in self._fields if f.kind != "skip"), key=lambda f: f.ordinal)

    def _capture(self, text):
        left = 0
        values = []
        last = len(self._fields) - 1
        for field in self._fields:
            if field.previous_greedy:
                while field.previous and text.startswith(field.previous, left):
                    left += len(field.previous)
            elif left == 0 and self._prefix_length > 0:
                if not text.startswith(field.previous):
                    raise DissectFailure(f"Input does not start with {_quote(field.previous)}")
                left = len(field.previous)
            start = left

            if field.id == last:
                values.append(text[start:])
                break
            if not field.next:
                raise DissectFailure(f"%{{{field.raw}}} has no delimiter before the next field, so it never matches")
            position = text.find(field.next, left)
            if position == -1:
                raise DissectFailure(f"Delimiter {_quote(field.next)} after %{{{field.raw}}} was not found")
            length = 0
            # Logstash only advances when the delimiter is found past the first character.
            if position > 0:
                length = position - left
                left = position + len(field.next)
            values.append(text[start:start + length])
        return values

    def _other_value_by_name(self, name, values, field_id):
        for field in self._fields:
            if field.id != field_id and field.name == name:
                return values[field.id]
        return ""

    def match(self, text):
        """Dissect ``text`` into fields.

        Args:
            text: A single event message.

        Returns:
            Dict of extracted fields, nested for ``[a][b]`` references. Failed
            ``convert_datatype`` conversions add ``_dataconversion*`` entries to
            ``tags``, as Logstash does.

        Raises:
            DissectFailure: If the input is empty or a delimiter cannot be found.

        Example:
            >>> Dissector("%{+a/2} %{+a/1} %{+a/4} %{+a/3}").match("1 2 3 go")
            {'a': '2 1 go 3'}
        """
        if not text:
            raise DissectFailure("Input is empty")
        values = self._capture(text)

        result = {}
        for field in self._saveable:
            value = values[field.id]
            if field.kind == "normal":
                set_field(result, field.name, value)
            elif field.kind == "append":
                existing = get_field(result, field.name)
                if existing is MISSING:
                    set_field(result, field.name, value)
                else:
                    set_field(result, field.name, f"{existing}{field.previous or ' '}{value}")
            else:
                key = get_field(result, field.name)
                key = self._other_value_by_name(field.name, values, field.id) if key is MISSING else str(key)
                if key:
                    set_field(result, key, value)

        tags = []
        for name, datatype in self.convert_datatype.items():
            value = get_field(result, name)
            if value is MISSING:
                tags.append(f"_dataconversionnullvalue_{name}_{datatype}")
            elif _BIG_DECIMAL_RE.fullmatch(str(value)):
                set_field(result, name, _CONVERTERS[datatype.lower()](str(value)))
            else:
                tags.append(f"_dataconversionuncoercible_{name}_{datatype}")
        if tags:
            result["tags"] = tags
        return result
