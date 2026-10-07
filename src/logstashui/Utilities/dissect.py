"""Pure-Python implementation of the Logstash dissect filter syntax.

Lets the Dissect Debugger preview ``logstash-filter-dissect`` results without
a running Logstash. Supported syntax:

* ``%{field}`` capture up to the next delimiter (the last field takes the rest)
* ``%{}`` / ``%{?name}`` skip a value
* ``%{field->}`` skip repeated delimiters after the field (right padding)
* ``%{+field}`` / ``%{+field/N}`` append values, optionally ordered by ``N``
* ``%{*key}`` or ``%{?key}`` with ``%{&key}`` use one value as another's field name
* ``[a][b]`` field references produce nested objects

Example:
    >>> Dissector("%{ts} %{+ts} %{level->} %{msg}").match("Oct 07 INFO   started")
    {'ts': 'Oct 07', 'level': 'INFO', 'msg': 'started'}
"""

import re
from dataclasses import dataclass

_FIELD_RE = re.compile(r"%\{([^}]*)\}")
_FIELD_REFERENCE_RE = re.compile(r"^(\[[^\[\]]+\])+$")
_ORDINAL_RE = re.compile(r"^(.*)/(\d+)$")
_PREFIX_KINDS = {"+": "append", "?": "key", "*": "key", "&": "value"}
_CONVERTERS = {"int": int, "float": float}


class DissectError(ValueError):
    """Raised when a dissect pattern or option is invalid."""


class DissectFailure(Exception):
    """Raised when input does not match the pattern (Logstash tags ``_dissectfailure``)."""


@dataclass
class _Field:
    raw: str
    name: str
    kind: str  # normal, skip, append, key, value
    right_pad: bool
    ordinal: int
    delimiter: str = ""


def _parse_field(raw, position):
    spec = raw
    right_pad = spec.endswith("->")
    if right_pad:
        spec = spec[:-2]

    kind = "normal"
    if spec[:1] in _PREFIX_KINDS:
        kind = _PREFIX_KINDS[spec[0]]
        spec = spec[1:]

    ordinal = position
    if kind == "append":
        ordinal_match = _ORDINAL_RE.match(spec)
        if ordinal_match:
            spec, ordinal = ordinal_match.group(1), int(ordinal_match.group(2))

    if not spec:
        if kind not in ("normal", "key"):
            raise DissectError(f"%{{{raw}}} is missing a field name")
        kind = "skip"

    return _Field(raw=raw, name=spec, kind=kind, right_pad=right_pad, ordinal=ordinal)


def _set_field(target, name, value):
    if _FIELD_REFERENCE_RE.match(name):
        parts = re.findall(r"\[([^\[\]]+)\]", name)
    else:
        parts = [name]
    for part in parts[:-1]:
        if not isinstance(target.get(part), dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value


class Dissector:
    """A compiled dissect pattern.

    Args:
        pattern: Dissect mapping, e.g. ``"%{clientip} - %{user} [%{ts}]"``.
        append_separator: String placed between appended values (Logstash default ``" "``).
        convert_datatype: Optional ``{field: "int" | "float"}`` conversions.

    Raises:
        DissectError: If the pattern or conversions are invalid.

    Example:
        >>> Dissector("%{*k}=%{&k}").match("user=alice")
        {'user': 'alice'}
    """

    def __init__(self, pattern, append_separator=" ", convert_datatype=None):
        self.append_separator = append_separator
        self.convert_datatype = dict(convert_datatype or {})
        for field_name, datatype in self.convert_datatype.items():
            if datatype not in _CONVERTERS:
                raise DissectError(f"Unsupported datatype '{datatype}' for '{field_name}' (use int or float)")

        matches = list(_FIELD_RE.finditer(pattern))
        if not matches:
            raise DissectError("Pattern contains no %{} fields")

        self._prefix = pattern[:matches[0].start()]
        self._fields = []
        for position, match in enumerate(matches):
            field = _parse_field(match.group(1), position)
            next_start = matches[position + 1].start() if position + 1 < len(matches) else len(pattern)
            field.delimiter = pattern[match.end():next_start]
            if not field.delimiter and position + 1 < len(matches):
                raise DissectError(f"%{{{field.raw}}} must be followed by a delimiter before the next field")
            self._fields.append(field)

        append_names = {f.name for f in self._fields if f.kind == "append"}
        for field in self._fields:
            if field.kind == "normal" and field.name in append_names:
                field.kind = "append"

        key_names = {f.name for f in self._fields if f.kind == "key"}
        for field in self._fields:
            if field.kind == "value" and field.name not in key_names:
                raise DissectError(f"%{{&{field.name}}} has no matching %{{*{field.name}}} or %{{?{field.name}}} field")

    def match(self, text):
        """Dissect ``text`` into fields.

        Args:
            text: A single event message.

        Returns:
            Dict of extracted fields, nested for ``[a][b]`` references.

        Raises:
            DissectFailure: If a delimiter cannot be found.

        Example:
            >>> Dissector("%{a} %{+a/2} %{+a/1}").match("x y z")
            {'a': 'x z y'}
        """
        if not text.startswith(self._prefix):
            raise DissectFailure(f"Input does not start with {self._prefix!r}")

        position = len(self._prefix)
        captured = []
        for field in self._fields:
            if field.delimiter:
                end = text.find(field.delimiter, position)
                if end == -1:
                    raise DissectFailure(f"Delimiter {field.delimiter!r} after %{{{field.raw}}} was not found")
                value = text[position:end]
                position = end + len(field.delimiter)
                if field.right_pad:
                    while text.startswith(field.delimiter, position):
                        position += len(field.delimiter)
            else:
                value = text[position:]
                position = len(text)
            captured.append((field, value))

        keys = {field.name: value for field, value in captured if field.kind == "key"}
        appended = {}
        flat = {}
        for field, value in captured:
            if field.kind == "normal":
                flat[field.name] = value
            elif field.kind == "append":
                flat.setdefault(field.name, None)
                appended.setdefault(field.name, []).append((field.ordinal, value))
            elif field.kind == "value":
                flat[keys[field.name]] = value
        for name, parts in appended.items():
            flat[name] = self.append_separator.join(value for _, value in sorted(parts, key=lambda p: p[0]))

        for name, datatype in self.convert_datatype.items():
            if name in flat:
                try:
                    flat[name] = _CONVERTERS[datatype](flat[name])
                except ValueError:
                    pass

        result = {}
        for name, value in flat.items():
            _set_field(result, name, value)
        return result
