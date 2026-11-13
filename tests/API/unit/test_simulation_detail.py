"""Tests for API/simulation_detail — shaping simulation results by detail level."""

import pytest

from API.simulation_detail import DETAIL_LEVELS, component_index, shape_results

COMPONENTS = {'filter': [
    {'id': 'filter_grok_0', 'plugin': 'grok', 'config': {'id': 'hdr'}},
    {'id': 'filter_if_1', 'plugin': 'if', 'config': {
        'condition': '[w] == "x"',
        'plugins': [{'id': 'filter_drop_2', 'plugin': 'drop', 'config': {}}],
        'else_ifs': [{'plugins': [{'id': 'filter_date_3', 'plugin': 'date', 'config': {}}]}],
        'else': {'plugins': [{'id': 'filter_mutate_4', 'plugin': 'mutate',
                              'config': {'id': 'norm'}}]},
    }},
]}
INDEX = component_index(COMPONENTS)

ORIGINAL = {
    'run_id': 'r1', 'slot': 3, 'message': 'hi there',
    'event': {'original': '{"message": "hi there", "run_id": "r1"}'},
    'simulation': {'id': 'original', 'step': '0'},
}
STEP_1 = {'message': 'hi there', 'w': 'hi', 'log': {'level': 'info'},
          'simulation': {'step': '1', 'id': 'filter_grok_0',
                         'timing': {'execution_ns': 2_500_000}}}
STEP_2 = {'message': 'hi there', 'w': 'hi', 'log': {'level': 'warn'}, 'tags': ['n'],
          'simulation': {'step': '2', 'id': 'filter_mutate_4',
                         'conditional_branches': {'filter_if_1': 'else'},
                         'timing': {'execution_ns': 1_000_000}}}
FINAL = {**STEP_2, 'run_id': 'r1', 'slot': 3,
         'snapshots': {'filter_mutate_4': STEP_2, 'filter_grok_0': STEP_1}}


def test_component_index_walks_conditionals():
    assert INDEX == {
        'filter_grok_0': {'plugin': 'grok', 'id': 'hdr'},
        'filter_if_1': {'plugin': 'if', 'id': None},
        'filter_drop_2': {'plugin': 'drop', 'id': None},
        'filter_date_3': {'plugin': 'date', 'id': None},
        'filter_mutate_4': {'plugin': 'mutate', 'id': 'norm'},
    }


def test_full_returns_raw_results():
    assert shape_results([ORIGINAL, FINAL], 'full', INDEX) == {'results': [ORIGINAL, FINAL]}


def test_final_strips_harness_fields():
    shaped = shape_results([ORIGINAL, FINAL], 'final', INDEX)
    assert shaped == {
        'final': {'message': 'hi there', 'w': 'hi', 'log': {'level': 'warn'}, 'tags': ['n']},
        'dropped': False,
    }


def test_steps_lists_only_changes_in_step_order():
    shaped = shape_results([ORIGINAL, FINAL], 'steps', INDEX)
    assert shaped['filter_ms'] == 3.5
    assert shaped['steps'] == [
        {'step': 1, 'plugin': 'grok', 'component': 'filter_grok_0', 'id': 'hdr', 'ms': 2.5,
         'added': {'w': 'hi', '[log][level]': 'info'}},
        {'step': 2, 'plugin': 'mutate', 'component': 'filter_mutate_4', 'id': 'norm', 'ms': 1.0,
         'added': {'tags': ['n']}, 'changed': {'[log][level]': 'warn'},
         'branches': {'filter_if_1': 'else'}},
    ]


def test_steps_reports_removed_fields_and_cuts_long_values():
    long_value = 'x' * 500
    step = {'message': long_value, 'simulation': {'step': '1', 'id': 'filter_grok_0'}}
    final = {**step, 'run_id': 'r1', 'snapshots': {'filter_grok_0': step}}
    original = {'run_id': 'r1', 'message': 'short', 'gone': 1}
    (only,) = shape_results([original, final], 'steps', INDEX)['steps']
    assert only['removed'] == ['gone']
    assert only['changed']['message'] == 'x' * 200 + '…'


def test_user_set_event_original_is_kept():
    final = {**FINAL, 'event': {'original': 'raw syslog line'}}
    shaped = shape_results([ORIGINAL, final], 'final', INDEX)
    assert shaped['final']['event'] == {'original': 'raw syslog line'}


def test_drop_is_reported():
    step = {'message': 'm', 'simulation': {'step': '2', 'id': 'filter_drop_2', 'final': 'true'}}
    final = {**step, 'run_id': 'r1', 'snapshots': {'filter_drop_2': step}}
    shaped = shape_results([ORIGINAL, final], 'final', INDEX)
    assert shaped['dropped'] is True
    assert shaped['dropped_by'] == {'plugin': 'drop', 'component': 'filter_drop_2'}


@pytest.mark.parametrize('detail', [d for d in DETAIL_LEVELS if d != 'full'])
def test_incomplete_run_has_no_final(detail):
    assert shape_results([ORIGINAL], detail, INDEX) == {'final': None, 'dropped': False}
