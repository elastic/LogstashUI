#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Logstash filter fragments for SNMP profile normalizers.

Normalizers run in the order a profile lists them; consecutive entries with the
same operation and scope share one filter.
"""

import functools
import json
import os
import re

# Ruby `init` that defines `lsui_counter_delta(key, value)`. State lives in a
# global so every pipeline worker sees the previous sample for a key.
COUNTER_DELTA_RUBY_INIT = (
    "$lsui_snmp_counters ||= {}\n"
    "$lsui_snmp_counters_lock ||= Mutex.new\n"
    "def lsui_counter_delta(key, value)\n"
    "  $lsui_snmp_counters_lock.synchronize do\n"
    "    prev = $lsui_snmp_counters[key]\n"
    "    $lsui_snmp_counters[key] = value\n"
    "    return nil if prev.nil? || value < prev\n"
    "    value - prev\n"
    "  end\n"
    "end"
)

_SAFE_FIELD_RE = re.compile(r'^[A-Za-z0-9_@-]+(\.[A-Za-z0-9_@-]+)*$')


def _field_path(field):
    """Return Logstash bracket notation for a dotted field name.

    Examples:
        >>> _field_path('system.cpu.user.pct')
        '[system][cpu][user][pct]'
    """
    return ''.join(f'[{part}]' for part in field.split('.'))

_INPUT_TYPES = {
    'float': ((int, float), 'a number'),
    'string': (str, 'a string'),
    'field_selector': (str, 'a field name'),
    'field_list': (list, 'a list of field names'),
    'key_value_pairs': (dict, 'an object of value mappings'),
}


@functools.cache
def normalizer_definitions():
    """Return the operation definitions from ``SNMP/data/normalizers.json``."""
    path = os.path.join(os.path.dirname(__file__), 'data', 'normalizers.json')
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def split_field_list(value):
    """Return a ``field_list`` param as a list, splitting a comma-separated string.

    The profile editor saves ``field_list`` params from a text box, so older
    profiles hold ``"a, b"`` instead of ``["a", "b"]``.

    Examples:
        >>> split_field_list('cpu.user, cpu.system')
        ['cpu.user', 'cpu.system']
        >>> split_field_list(['cpu.user'])
        ['cpu.user']
    """
    if isinstance(value, str):
        return [part.strip() for part in value.split(',') if part.strip()]
    return value


def coerce_field_lists(normalizers):
    """Rewrite comma-separated ``field_list`` params in place as lists.

    Args:
        normalizers: The profile's ``normalizers`` list; anything else is left alone.

    Examples:
        >>> norms = [{'operation': 'sum', 'params': {'input_fields': 'a, b', 'output_field': 'c'}}]
        >>> coerce_field_lists(norms)
        >>> norms[0]['params']['input_fields']
        ['a', 'b']
    """
    if not isinstance(normalizers, list):
        return
    definitions = normalizer_definitions()
    for norm in normalizers:
        if not isinstance(norm, dict) or not isinstance(norm.get('params'), dict):
            continue
        spec = definitions.get(norm.get('operation')) if isinstance(norm.get('operation'), str) else None
        for name, definition in (spec or {}).get('inputs', {}).items():
            if definition.get('type') == 'field_list' and name in norm['params']:
                norm['params'][name] = split_field_list(norm['params'][name])


def validate_normalizers(normalizers):
    """Check profile normalizers against ``normalizers.json``.

    Args:
        normalizers: The profile's ``normalizers`` list.

    Returns:
        list[str]: One message per problem; empty when valid.

    Examples:
        >>> validate_normalizers([{'operation': 'multiply',
        ...                        'target': {'scope': 'get', 'field': 'ups.voltage'},
        ...                        'params': {'multiply_value': 0.1}}])
        []
        >>> validate_normalizers([{'operation': 'multiply',
        ...                        'target': {'scope': 'get', 'field': 'ups.voltage'},
        ...                        'params': {'factor': 0.1}}])
        ["normalizers[0] (multiply): unknown param 'factor'; allowed: multiply_value."]
    """
    if not normalizers:
        return []
    if not isinstance(normalizers, list):
        return ['normalizers must be a list.']
    definitions = normalizer_definitions()
    errors = []
    for i, norm in enumerate(normalizers):
        where = f'normalizers[{i}]'
        if not isinstance(norm, dict):
            errors.append(f'{where} must be an object.')
            continue
        operation = norm.get('operation')
        spec = definitions.get(operation) if isinstance(operation, str) else None
        if spec is None:
            errors.append(f"{where}: unknown operation {operation!r}; use one of: {', '.join(definitions)}.")
            continue
        where = f'{where} ({operation})'

        target = norm.get('target')
        if not isinstance(target, dict):
            errors.append(f'{where}: target must be an object with a scope.')
        else:
            scope = target.get('scope')
            if scope not in spec['applies_to']:
                errors.append(f"{where}: target.scope must be one of: {', '.join(spec['applies_to'])}.")
            field = target.get('field')
            if spec.get('has_target_field') and not (isinstance(field, str) and field.strip()):
                errors.append(f'{where}: target.field must be a non-empty string.')

        params = norm.get('params', {})
        if not isinstance(params, dict):
            errors.append(f'{where}: params must be an object.')
            continue
        inputs = spec.get('inputs', {})
        for name, value in params.items():
            if name not in inputs:
                errors.append(f"{where}: unknown param {name!r}; allowed: {', '.join(inputs)}.")
                continue
            input_type = inputs[name].get('type')
            expected, label = _INPUT_TYPES.get(input_type, (object, 'a value'))
            if (not isinstance(value, expected) or isinstance(value, bool)
                    or (input_type == 'field_list'
                        and not all(isinstance(f, str) and f.strip() for f in value))):
                errors.append(f'{where}: param {name!r} must be {label}.')
        for name, definition in inputs.items():
            if definition.get('required') and params.get(name) in (None, '', [], {}):
                errors.append(f'{where}: param {name!r} is required.')
    return errors


def _next_id(base, counter):
    """Return `base` plus an incrementing suffix, mutating `counter` in place.

    Share one counter across `_apply_normalizers` calls so IDs stay unique when
    several profiles merge into a single pipeline.

    Args:
        base: ID prefix (e.g. ``normalizer_multiply_get``).
        counter: Mutable dict of base → last issued integer.

    Returns:
        Unique ID such as ``normalizer_multiply_get_1``.
    """
    n = counter.get(base, 0) + 1
    counter[base] = n
    return f"{base}_{n}"


def _apply_normalizers(normalizers, id_counter=None):
    """Build Logstash filter components from profile normalizer configs.

    Runs in listed order so chained normalizers (e.g. KB→bytes, then a
    difference of the bytes) see their inputs. Consecutive entries with the same
    operation and scope share one filter. Pass the same `id_counter` for every
    profile in a pipeline so plugin IDs stay unique (Logstash rejects duplicate
    IDs). `average` and `sum_column` are handled by the table splitter, not here.

    Args:
        normalizers: Normalizer dicts from a profile.
        id_counter: Optional shared ID map; a new dict is used when omitted.

    Returns:
        List of Logstash filter component dicts.
    """
    if not normalizers:
        return []

    if id_counter is None:
        id_counter = {}

    generators = {
        'multiply': lambda group, scope: _generate_multiply_get_filter(group, scope, id_counter),
        'ratio': lambda group, scope: _generate_ratio_get_filter(group, scope, id_counter),
        'sum': lambda group, scope: _generate_sum_get_filter(group, scope, id_counter),
        'translate': lambda group, scope: _generate_translate_filter(group, id_counter),
        'counter_delta': lambda group, scope: _generate_counter_delta_filter(group, scope, id_counter),
        'share': lambda group, scope: _generate_share_filter(group, scope, id_counter),
    }

    runs = []
    for normalizer in normalizers:
        operation = normalizer.get('operation')
        scope = normalizer.get('target', {}).get('scope')
        if operation not in generators or scope not in ('get', 'table'):
            continue
        if runs and runs[-1][0] == (operation, scope):
            runs[-1][1].append(normalizer)
        else:
            runs.append(((operation, scope), [normalizer]))

    filters = []
    for (operation, scope), group in runs:
        components = generators[operation](group, scope)
        if isinstance(components, list):
            filters.extend(components)
        elif components:
            filters.append(components)
    return filters


def _generate_multiply_get_filter(normalizers, scope='get', id_counter=None):
    """Emit one Ruby filter that applies multiply ops for a get or table scope.

    Args:
        normalizers: Multiply normalizers for `scope`.
        scope: ``get`` or ``table``; included in plugin IDs so scopes cannot collide.
        id_counter: Shared mutable ID map.

    Returns:
        Logstash filter component dict.
    """
    if id_counter is None:
        id_counter = {}
    if not normalizers:
        return None
    
    ruby_lines = []
    field_list = []

    for normalizer in normalizers:
        field = normalizer.get('target', {}).get('field')
        params = normalizer.get('params', {})
        multiply_value = params.get('multiply_value')
        multiply_field = str(params.get('multiply_field', '') or '').strip()
        if multiply_field and not _SAFE_FIELD_RE.match(multiply_field):
            multiply_field = ''

        if not field or (multiply_value is None and not multiply_field):
            continue
        if multiply_value is None:
            multiply_value = 1.0

        # Convert dot-separated field to Logstash field path
        # e.g., "system.cpu.total.norm.pct" -> "[system][cpu][total][norm][pct]"
        field_path = _field_path(field)

        # Use output_field if specified, otherwise overwrite the source field in-place
        output_field = params.get('output_field', '').strip()
        output_path = _field_path(output_field) if output_field else field_path

        if multiply_field:
            ruby_lines.append(
                f'v = event.get("{field_path}")\n'
                f'm = event.get("{_field_path(multiply_field)}")\n'
                f'if v && m\n'
                f'  event.set("{output_path}", v.to_f * {multiply_value} * m.to_f)\n'
                f'end'
            )
        else:
            ruby_lines.append(
                f'v = event.get("{field_path}")\n'
                f'if v\n'
                f'  event.set("{output_path}", v.to_f * {multiply_value})\n'
                f'end'
            )

        factor = f"{multiply_value} × {multiply_field}" if multiply_field else f"{multiply_value}"
        dest = f" → {output_field}" if output_field and output_field != field else ""
        field_list.append(f"  - {field} × {factor}{dest}")

    if not ruby_lines:
        return None

    ruby_code = '\n'.join(ruby_lines)
    
    comment_text = "Normalizer: Multiply\n"
    comment_text += "Multiplies field values by configured factors:\n"
    comment_text += '\n'.join(field_list)
    
    base = f"normalizer_multiply_{scope}"
    return [
        {
            "id": _next_id(f"{base}_comment", id_counter),
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": comment_text
            }
        },
        {
            "id": _next_id(base, id_counter),
            "type": "filter",
            "plugin": "ruby",
            "config": {
                "code": ruby_code
            }
        }
    ]


def _generate_ratio_get_filter(normalizers, scope='get', id_counter=None):
    """Emit one Ruby filter that computes ratios (and optional totals) for a scope.

    Args:
        normalizers: Ratio normalizers for `scope`.
        scope: ``get`` or ``table``; included in plugin IDs so scopes cannot collide.
        id_counter: Shared mutable ID map.

    Returns:
        Logstash filter component dict.
    """
    if id_counter is None:
        id_counter = {}
    if not normalizers:
        return None
    
    ruby_lines = []
    
    for idx, normalizer in enumerate(normalizers):
        params = normalizer.get('params', {})
        value1_field = params.get('value1_field')
        value2_field = params.get('value2_field')
        total_output = params.get('total_output_field', '').strip()
        ratio1_output = params.get('ratio1_output_field', '').strip()
        ratio2_output = params.get('ratio2_output_field', '').strip()
        complement_output = params.get('complement_ratio_output_field', '').strip()
        divide_output = params.get('divide_output_field', '').strip()
        difference_output = params.get('difference_output_field', '').strip()

        if not value1_field or not value2_field:
            continue
        
        # Convert dot-separated fields to Logstash field paths
        value1_path = ''.join(f'[{part}]' for part in value1_field.split('.'))
        value2_path = ''.join(f'[{part}]' for part in value2_field.split('.'))
        
        # Use unique variable names for each ratio to avoid collisions
        var_suffix = f'_{idx}' if len(normalizers) > 1 else ''
        
        # Build Ruby code for this ratio calculation
        ruby_code_block = f'value1{var_suffix} = event.get("{value1_path}")\n'
        ruby_code_block += f'value2{var_suffix} = event.get("{value2_path}")\n\n'
        ruby_code_block += f'if value1{var_suffix} && value2{var_suffix}\n'
        ruby_code_block += f'  value1_f{var_suffix} = value1{var_suffix}.to_f\n'
        ruby_code_block += f'  value2_f{var_suffix} = value2{var_suffix}.to_f\n'
        ruby_code_block += f'  total_f{var_suffix} = value1_f{var_suffix} + value2_f{var_suffix}\n\n'
        ruby_code_block += f'  if total_f{var_suffix} > 0\n'
        
        # Add total output if specified
        if total_output:
            total_output_path = ''.join(f'[{part}]' for part in total_output.split('.'))
            ruby_code_block += f'    event.set("{total_output_path}", total_f{var_suffix})\n'
        
        # Add ratio1 output if specified
        if ratio1_output:
            ratio1_output_path = ''.join(f'[{part}]' for part in ratio1_output.split('.'))
            ruby_code_block += f'    event.set("{ratio1_output_path}", (value1_f{var_suffix} / total_f{var_suffix}))\n'
        
        # Add ratio2 output if specified
        if ratio2_output:
            ratio2_output_path = ''.join(f'[{part}]' for part in ratio2_output.split('.'))
            ruby_code_block += f'    event.set("{ratio2_output_path}", (value2_f{var_suffix} / total_f{var_suffix}))\n'

        # Add complement ratio output if specified: (value1 - value2) / value1
        # Useful when value1 is total and value2 is free/available, yielding used fraction.
        if complement_output:
            complement_output_path = ''.join(f'[{part}]' for part in complement_output.split('.'))
            ruby_code_block += f'    event.set("{complement_output_path}", (value1_f{var_suffix} - value2_f{var_suffix}) / value1_f{var_suffix})\n'

        # Add divide output if specified: value2 / value1
        if divide_output:
            divide_output_path = ''.join(f'[{part}]' for part in divide_output.split('.'))
            ruby_code_block += f'    event.set("{divide_output_path}", value2_f{var_suffix} / value1_f{var_suffix}) if value1_f{var_suffix} > 0\n'

        # Add difference output if specified: value1 - value2 (e.g. total - used = free)
        if difference_output:
            ruby_code_block += f'    event.set("{_field_path(difference_output)}", value1_f{var_suffix} - value2_f{var_suffix})\n'

        ruby_code_block += '  end\n'
        ruby_code_block += 'end'
        
        ruby_lines.append(ruby_code_block)
    
    if not ruby_lines:
        return None
    
    ruby_code = '\n\n'.join(ruby_lines)
    
    # Build description of ratio calculations
    calc_list = []
    for normalizer in normalizers:
        params = normalizer.get('params', {})
        value1_field = params.get('value1_field')
        value2_field = params.get('value2_field')
        total_output = params.get('total_output_field', '').strip()
        ratio1_output = params.get('ratio1_output_field', '').strip()
        ratio2_output = params.get('ratio2_output_field', '').strip()
        complement_output = params.get('complement_ratio_output_field', '').strip()
        divide_output = params.get('divide_output_field', '').strip()
        difference_output = params.get('difference_output_field', '').strip()

        if value1_field and value2_field:
            calc_list.append(f"  Inputs: {value1_field}, {value2_field}")
            if total_output:
                calc_list.append(f"    → {total_output} = sum")
            if ratio1_output:
                calc_list.append(f"    → {ratio1_output} = value1 / (value1 + value2)")
            if ratio2_output:
                calc_list.append(f"    → {ratio2_output} = value2 / (value1 + value2)")
            if complement_output:
                calc_list.append(f"    → {complement_output} = (value1 - value2) / value1")
            if divide_output:
                calc_list.append(f"    → {divide_output} = value2 / value1")
            if difference_output:
                calc_list.append(f"    → {difference_output} = value1 - value2")
    
    comment_text = "Normalizer: Ratio\n"
    comment_text += "Calculates ratios and derived fields from two input values:\n"
    comment_text += '\n'.join(calc_list)
    
    base = f"normalizer_ratio_{scope}"
    return [
        {
            "id": _next_id(f"{base}_comment", id_counter),
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": comment_text
            }
        },
        {
            "id": _next_id(base, id_counter),
            "type": "filter",
            "plugin": "ruby",
            "config": {
                "code": ruby_code
            }
        }
    ]


def _generate_sum_get_filter(normalizers, scope='get', id_counter=None):
    """Emit one Ruby filter that sums lists of fields for a get or table scope.

    Each normalizer entry must supply ``input_fields`` (a list of field names to
    add together) and ``output_field`` (the field to write the result to).  All
    input fields must be non-nil for the sum to be written; missing fields are
    silently skipped so partially-populated events do not produce misleading
    zeros.

    Args:
        normalizers: Sum normalizers for ``scope``.
        scope: ``get`` or ``table``; included in plugin IDs so scopes cannot
            collide with other sum filters in the same pipeline.
        id_counter: Shared mutable ID map.

    Returns:
        List of Logstash filter component dicts, or ``None`` when there is
        nothing to emit.

    Examples:
        >>> n = [{
        ...     'operation': 'sum',
        ...     'target': {'scope': 'get'},
        ...     'params': {
        ...         'input_fields': ['system.cpu.pct.user', 'system.cpu.pct.system'],
        ...         'output_field': 'system.cpu.active.pct',
        ...     },
        ... }]
        >>> result = _generate_sum_get_filter(n)
        >>> result[1]['plugin']
        'ruby'
    """
    if id_counter is None:
        id_counter = {}
    if not normalizers:
        return None

    ruby_lines = []
    desc_lines = []

    for normalizer in normalizers:
        params = normalizer.get('params', {})
        input_fields = split_field_list(params.get('input_fields', []))
        output_field = params.get('output_field', '').strip()

        if not input_fields or not output_field:
            continue

        output_path = ''.join(f'[{part}]' for part in output_field.split('.'))
        input_paths = [
            ''.join(f'[{part}]' for part in f.split('.'))
            for f in input_fields
        ]

        # Guard: only write when every input field is present.
        nil_checks = ' && '.join(f'event.get("{p}")' for p in input_paths)
        sum_expr = ' + '.join(f'event.get("{p}").to_f' for p in input_paths)

        ruby_lines.append(
            f'if {nil_checks}\n'
            f'  event.set("{output_path}", {sum_expr})\n'
            f'end'
        )
        fields_list = ' + '.join(input_fields)
        desc_lines.append(f'  - {fields_list} → {output_field}')

    if not ruby_lines:
        return None

    ruby_code = '\n'.join(ruby_lines)

    comment_text = 'Normalizer: Sum\n'
    comment_text += 'Sums input fields into a single output field:\n'
    comment_text += '\n'.join(desc_lines)

    base = f'normalizer_sum_{scope}'
    return [
        {
            'id': _next_id(f'{base}_comment', id_counter),
            'type': 'filter',
            'plugin': 'comment',
            'config': {'text': comment_text},
        },
        {
            'id': _next_id(base, id_counter),
            'type': 'filter',
            'plugin': 'ruby',
            'config': {'code': ruby_code},
        },
    ]


def _generate_translate_filter(normalizers, id_counter=None):
    """Emit translate filters that map raw SNMP values to display strings in place.

    Args:
        normalizers: Translate normalizer configs.
        id_counter: Shared mutable ID map.

    Returns:
        List of filter component dicts, or None when there is nothing to emit.
    """
    if not normalizers:
        return None

    if id_counter is None:
        id_counter = {}

    components = []

    for normalizer in normalizers:
        field = normalizer.get('target', {}).get('field')
        mapping = normalizer.get('params', {}).get('mapping', {})

        if not field or not mapping:
            continue

        field_path = ''.join(f'[{part}]' for part in field.split('.'))

        pairs = ', '.join(f'{k}→{v}' for k, v in mapping.items())
        comment_text = f"Normalizer: Translate\nMaps {field}: {pairs}"

        base = f"normalizer_translate_{field.replace('.', '_')}"
        components.append({
            "id": _next_id(f"{base}_comment", id_counter),
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": comment_text
            }
        })
        components.append({
            "id": _next_id(base, id_counter),
            "type": "filter",
            "plugin": "translate",
            "config": {
                "source": field_path,
                "destination": field_path,
                "dictionary": mapping,
                "override": True
            }
        })

    return components if components else None


def _generate_counter_delta_filter(normalizers, scope='get', id_counter=None):
    """Emit one Ruby filter that writes each counter's change since the last poll.

    State is keyed by network, polled address, ``tsds.category``, ``tsds.index``
    and field, so GET scalars and individual table rows are tracked separately.
    The first sample for a key and any sample lower than the previous one
    (counter reset or wrap) write nothing.

    Args:
        normalizers: ``counter_delta`` normalizers for ``scope``.
        scope: ``get`` or ``table``; included in plugin IDs.
        id_counter: Shared mutable ID map.

    Returns:
        List of Logstash filter component dicts, or ``None`` when there is
        nothing to emit.

    Examples:
        >>> n = [{'operation': 'counter_delta',
        ...       'target': {'scope': 'get', 'field': 'system.cpu.raw.user'},
        ...       'params': {'output_field': 'system.cpu.delta.user'}}]
        >>> result = _generate_counter_delta_filter(n)
        >>> 'lsui_counter_delta' in result[1]['config']['code']
        True
    """
    if id_counter is None:
        id_counter = {}

    ruby_lines = []
    desc_lines = []
    for normalizer in normalizers or []:
        field = normalizer.get('target', {}).get('field', '')
        output_field = normalizer.get('params', {}).get('output_field', '').strip()
        if not _SAFE_FIELD_RE.match(field) or not _SAFE_FIELD_RE.match(output_field):
            continue
        ruby_lines.append(
            f'v = event.get("{_field_path(field)}")\n'
            f'if v\n'
            f'  begin\n'
            f'    d = lsui_counter_delta("#{{_cd_key}}|{field}", Float(v))\n'
            f'    event.set("{_field_path(output_field)}", d) unless d.nil?\n'
            f'  rescue ArgumentError, TypeError\n'
            f'  end\n'
            f'end'
        )
        desc_lines.append(f'  - {field} → {output_field}')

    if not ruby_lines:
        return None

    ruby_code = (
        '_cd_key = [event.get("[network][name]"), event.get("[host][polled_address]"), '
        'event.get("[tsds][category]"), event.get("[tsds][index]")].join("|")\n'
        + '\n'.join(ruby_lines)
    )
    comment_text = 'Normalizer: Counter delta\nChange since the previous poll:\n' + '\n'.join(desc_lines)

    base = f'normalizer_counter_delta_{scope}'
    return [
        {
            'id': _next_id(f'{base}_comment', id_counter),
            'type': 'filter',
            'plugin': 'comment',
            'config': {'text': comment_text},
        },
        {
            'id': _next_id(base, id_counter),
            'type': 'filter',
            'plugin': 'ruby',
            'config': {'init': COUNTER_DELTA_RUBY_INIT, 'code': ruby_code},
        },
    ]


def _generate_share_filter(normalizers, scope='get', id_counter=None):
    """Emit one Ruby filter that writes each input's share of the inputs' total.

    ``output_fields[i] = input_fields[i] / sum(input_fields) * multiply_value
    [* multiply_field]``. Nothing is written unless every input (and
    ``multiply_field``, when set) is present and the total is positive. Used to
    turn per-state CPU tick deltas into Elastic's ``system.cpu.<state>.pct``,
    which is summed across cores.

    Args:
        normalizers: ``share`` normalizers for ``scope``.
        scope: ``get`` or ``table``; included in plugin IDs.
        id_counter: Shared mutable ID map.

    Returns:
        List of Logstash filter component dicts, or ``None`` when there is
        nothing to emit.

    Examples:
        >>> n = [{'operation': 'share', 'target': {'scope': 'get'},
        ...       'params': {'input_fields': ['a.user', 'a.idle'],
        ...                  'output_fields': ['b.user.pct', 'b.idle.pct'],
        ...                  'multiply_field': 'system.cpu.cores'}}]
        >>> result = _generate_share_filter(n)
        >>> result[1]['plugin']
        'ruby'
    """
    if id_counter is None:
        id_counter = {}

    ruby_lines = []
    desc_lines = []
    for normalizer in normalizers or []:
        params = normalizer.get('params', {})
        inputs = split_field_list(params.get('input_fields', []))
        outputs = split_field_list(params.get('output_fields', []))
        multiply_value = params.get('multiply_value')
        multiply_value = 1.0 if multiply_value is None else float(multiply_value)
        multiply_field = str(params.get('multiply_field', '') or '').strip()
        fields = inputs + outputs + ([multiply_field] if multiply_field else [])
        if not inputs or len(inputs) != len(outputs) or not all(_SAFE_FIELD_RE.match(f) for f in fields):
            continue

        values = ', '.join(f'event.get("{_field_path(f)}")' for f in inputs)
        factor = f'{multiply_value}'
        lines = [f'_sh = [{values}]']
        if multiply_field:
            lines.append(f'_shm = event.get("{_field_path(multiply_field)}")')
            lines.append('if _sh.all? && _shm')
            factor = f'{multiply_value} * _shm.to_f'
        else:
            lines.append('if _sh.all?')
        lines.append('  _sh = _sh.map(&:to_f)')
        lines.append('  _sht = _sh.sum')
        lines.append('  if _sht > 0')
        for i, output in enumerate(outputs):
            lines.append(f'    event.set("{_field_path(output)}", _sh[{i}] / _sht * {factor})')
        lines.append('  end')
        lines.append('end')
        ruby_lines.append('\n'.join(lines))

        scale = f' × {multiply_field}' if multiply_field else ''
        desc_lines.append(f'  - {", ".join(inputs)} → {", ".join(outputs)}{scale}')

    if not ruby_lines:
        return None

    comment_text = 'Normalizer: Share\nEach input divided by the inputs\' total:\n' + '\n'.join(desc_lines)
    base = f'normalizer_share_{scope}'
    return [
        {
            'id': _next_id(f'{base}_comment', id_counter),
            'type': 'filter',
            'plugin': 'comment',
            'config': {'text': comment_text},
        },
        {
            'id': _next_id(base, id_counter),
            'type': 'filter',
            'plugin': 'ruby',
            'config': {'code': '\n'.join(ruby_lines)},
        },
    ]
