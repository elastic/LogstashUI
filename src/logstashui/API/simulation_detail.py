"""Shape raw simulation results to a chosen level of detail.

A simulation run produces a step-0 copy of the input and a final event whose
``snapshots`` hold the event after every filter. Returned as-is that is large
(each snapshot repeats the whole event), so callers pick a level:

``full``
    The raw results, unchanged.
``steps``
    The final event plus, for each filter that changed the event, only the
    fields it added, changed, or removed. Filters that changed nothing are
    left out; ``filter_ms`` still counts them.
``final``
    Only the final event.

Examples:
    >>> shape_results([], 'final', {})
    {'final': None, 'dropped': False}
"""

import json

DETAIL_LEVELS = ('final', 'steps', 'full')

#: Fields the simulation harness adds to every event.
_HARNESS_KEYS = frozenset({'snapshots', 'simulation', 'run_id', 'slot'})

#: Longer step values are cut to this many characters.
_MAX_STEP_VALUE_CHARS = 200


def component_index(components):
    """Map each parsed filter component ID to its plugin name and config ``id``.

    Args:
        components: Parsed pipeline components (``{'filter': [...]}``).

    Returns:
        dict: ``{component_id: {'plugin': name, 'id': config_id_or_None}}``.

    Examples:
        >>> component_index({'filter': [{'id': 'filter_grok_0', 'plugin': 'grok',
        ...                              'config': {'id': 'asa_header'}}]})
        {'filter_grok_0': {'plugin': 'grok', 'id': 'asa_header'}}
    """
    index = {}

    def walk(plugins):
        for plugin in plugins or []:
            config = plugin.get('config') or {}
            index[plugin.get('id')] = {'plugin': plugin.get('plugin'), 'id': config.get('id')}
            walk(config.get('plugins'))
            for branch in config.get('else_ifs') or []:
                walk(branch.get('plugins'))
            walk((config.get('else') or {}).get('plugins'))

    walk(components.get('filter'))
    return index


def shape_results(results, detail, index):
    """Return the response fields for one simulated event at ``detail``.

    Args:
        results: Raw results for one run (step-0 event, then the final event).
        detail: One of :data:`DETAIL_LEVELS`.
        index: Output of :func:`component_index` for the simulated pipeline.

    Returns:
        dict: ``{'results': [...]}`` for ``full``. Otherwise ``final`` (the
        cleaned final event, or ``None`` if the run did not finish),
        ``dropped``, ``dropped_by`` when a drop filter ended the run, and for
        ``steps`` also ``steps`` and ``filter_ms``.
    """
    if detail == 'full':
        return {'results': results}

    original = next((r for r in results if not r.get('snapshots')), {})
    final = next((r for r in reversed(results) if r.get('snapshots')), None)
    if final is None:
        return {'final': None, 'dropped': False}

    run_id = final.get('run_id')
    shaped = {'final': _clean(final, run_id), 'dropped': False}
    sim = final.get('simulation') or {}
    if str(sim.get('final')).lower() == 'true':
        shaped['dropped'] = True
        shaped['dropped_by'] = _describe(sim.get('id'), index)

    if detail == 'steps':
        shaped['steps'], total_ns = _steps(final['snapshots'], _clean(original, run_id), run_id, index)
        shaped['filter_ms'] = round(total_ns / 1e6, 3)
    return shaped


def _steps(snapshots, previous, run_id, index):
    ordered = sorted(
        snapshots.items(),
        key=lambda item: int((item[1].get('simulation') or {}).get('step') or 0),
    )
    steps, total_ns, last_branches = [], 0, {}
    prev_flat = _flatten(previous)
    for component_id, snapshot in ordered:
        sim = snapshot.get('simulation') or {}
        execution_ns = (sim.get('timing') or {}).get('execution_ns') or 0
        total_ns += execution_ns
        flat = _flatten(_clean(snapshot, run_id))

        step = {'step': int(sim.get('step') or 0), **_describe(component_id, index),
                'ms': round(execution_ns / 1e6, 3)}
        added = {k: _short(v) for k, v in flat.items() if k not in prev_flat}
        changed = {k: _short(v) for k, v in flat.items() if k in prev_flat and prev_flat[k] != v}
        removed = [k for k in prev_flat if k not in flat]
        if added:
            step['added'] = added
        if changed:
            step['changed'] = changed
        if removed:
            step['removed'] = removed
        branches = sim.get('conditional_branches') or {}
        if branches and branches != last_branches:
            step['branches'] = branches
        last_branches = branches

        if added or changed or removed or 'branches' in step:
            steps.append(step)
        prev_flat = flat
    return steps, total_ns


def _describe(component_id, index):
    info = index.get(component_id) or {}
    described = {'plugin': info.get('plugin'), 'component': component_id}
    if info.get('id'):
        described['id'] = info['id']
    return described


def _clean(event, run_id):
    cleaned = {k: v for k, v in event.items() if k not in _HARNESS_KEYS}
    meta = cleaned.get('event')
    if isinstance(meta, dict) and run_id and run_id in str(meta.get('original', '')):
        meta = {k: v for k, v in meta.items() if k != 'original'}
        if meta:
            cleaned['event'] = meta
        else:
            del cleaned['event']
    return cleaned


def _flatten(value, path=()):
    """Flatten nested objects to Logstash field references.

    Top-level keys stay bare (``message``, or a literal dotted ``event.code``);
    nested keys use bracket form (``[log][syslog][priority]``).
    """
    if isinstance(value, dict) and (value or not path):
        flat = {}
        for key, child in value.items():
            flat.update(_flatten(child, (*path, key)))
        return flat
    ref = path[0] if len(path) == 1 else ''.join(f'[{p}]' for p in path)
    return {ref: value}


def _short(value):
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) <= _MAX_STEP_VALUE_CHARS:
        return value
    return text[:_MAX_STEP_VALUE_CHARS] + '…'
