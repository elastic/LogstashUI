#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Tests for SNMP.snmp_normalizers — all pure functions, no DB or network required.
"""

import pytest

from SNMP.snmp_normalizers import (
    _apply_normalizers,
    _generate_multiply_get_filter,
    _generate_ratio_get_filter,
    _generate_translate_filter,
)


# ===========================================================================
# _generate_multiply_get_filter
# ===========================================================================

class TestGenerateMultiplyGetFilter:

    def test_returns_none_for_empty_list(self):
        assert _generate_multiply_get_filter([]) is None

    def test_returns_comment_and_ruby_filter(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'get', 'field': 'system.cpu.total.norm.pct'},
                'params': {'multiply_value': 0.01}
            }
        ]
        result = _generate_multiply_get_filter(normalizers)
        assert isinstance(result, list)
        assert len(result) == 2
        comment, ruby = result
        assert comment['plugin'] == 'comment'
        assert ruby['plugin'] == 'ruby'

    def test_ruby_code_contains_field_path(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'get', 'field': 'system.cpu.total.norm.pct'},
                'params': {'multiply_value': 0.01}
            }
        ]
        result = _generate_multiply_get_filter(normalizers)
        ruby_code = result[1]['config']['code']
        assert '[system][cpu][total][norm][pct]' in ruby_code

    def test_ruby_code_contains_multiply_value(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'get', 'field': 'some.metric'},
                'params': {'multiply_value': 100}
            }
        ]
        result = _generate_multiply_get_filter(normalizers)
        ruby_code = result[1]['config']['code']
        assert '100' in ruby_code

    def test_skips_normalizer_missing_field(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'get'},  # no 'field'
                'params': {'multiply_value': 0.01}
            }
        ]
        result = _generate_multiply_get_filter(normalizers)
        assert result is None

    def test_skips_normalizer_missing_multiply_value(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'get', 'field': 'some.metric'},
                'params': {}  # no 'multiply_value'
            }
        ]
        result = _generate_multiply_get_filter(normalizers)
        assert result is None

    def test_multiple_normalizers_in_single_filter(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'get', 'field': 'metric.a'},
                'params': {'multiply_value': 2}
            },
            {
                'operation': 'multiply',
                'target': {'scope': 'get', 'field': 'metric.b'},
                'params': {'multiply_value': 3}
            }
        ]
        result = _generate_multiply_get_filter(normalizers)
        # Both fields consolidated into single ruby filter
        assert isinstance(result, list)
        ruby_code = result[1]['config']['code']
        assert '[metric][a]' in ruby_code
        assert '[metric][b]' in ruby_code

    def test_comment_mentions_multiply(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'get', 'field': 'metric.a'},
                'params': {'multiply_value': 0.5}
            }
        ]
        result = _generate_multiply_get_filter(normalizers)
        comment_text = result[0]['config']['text']
        assert 'Multiply' in comment_text


# ===========================================================================
# _generate_ratio_get_filter
# ===========================================================================

class TestGenerateRatioGetFilter:

    def test_returns_none_for_empty_list(self):
        assert _generate_ratio_get_filter([]) is None

    def test_returns_comment_and_ruby_filter(self):
        normalizers = [
            {
                'operation': 'ratio',
                'target': {'scope': 'get'},
                'params': {
                    'value1_field': 'memory.used',
                    'value2_field': 'memory.free',
                    'total_output_field': 'memory.total',
                }
            }
        ]
        result = _generate_ratio_get_filter(normalizers)
        assert isinstance(result, list)
        assert len(result) == 2
        comment, ruby = result
        assert comment['plugin'] == 'comment'
        assert ruby['plugin'] == 'ruby'

    def test_skips_normalizer_missing_value_fields(self):
        normalizers = [
            {
                'operation': 'ratio',
                'target': {'scope': 'get'},
                'params': {
                    'value1_field': 'memory.used',
                    # no value2_field
                }
            }
        ]
        result = _generate_ratio_get_filter(normalizers)
        assert result is None

    def test_ruby_code_contains_field_paths(self):
        normalizers = [
            {
                'operation': 'ratio',
                'target': {'scope': 'get'},
                'params': {
                    'value1_field': 'memory.used',
                    'value2_field': 'memory.free',
                }
            }
        ]
        result = _generate_ratio_get_filter(normalizers)
        ruby_code = result[1]['config']['code']
        assert '[memory][used]' in ruby_code
        assert '[memory][free]' in ruby_code

    def test_optional_output_fields_included_when_specified(self):
        normalizers = [
            {
                'operation': 'ratio',
                'target': {'scope': 'get'},
                'params': {
                    'value1_field': 'mem.used',
                    'value2_field': 'mem.free',
                    'total_output_field': 'mem.total',
                    'ratio1_output_field': 'mem.used_pct',
                    'ratio2_output_field': 'mem.free_pct',
                    'complement_ratio_output_field': 'mem.complement',
                    'divide_output_field': 'mem.divided',
                }
            }
        ]
        result = _generate_ratio_get_filter(normalizers)
        ruby_code = result[1]['config']['code']
        assert '[mem][total]' in ruby_code
        assert '[mem][used_pct]' in ruby_code
        assert '[mem][free_pct]' in ruby_code
        assert '[mem][complement]' in ruby_code
        assert '[mem][divided]' in ruby_code

    def test_multiple_ratio_normalizers_use_unique_variable_names(self):
        normalizers = [
            {
                'operation': 'ratio',
                'target': {'scope': 'get'},
                'params': {'value1_field': 'a.used', 'value2_field': 'a.free'}
            },
            {
                'operation': 'ratio',
                'target': {'scope': 'get'},
                'params': {'value1_field': 'b.used', 'value2_field': 'b.free'}
            }
        ]
        result = _generate_ratio_get_filter(normalizers)
        ruby_code = result[1]['config']['code']
        # With multiple normalizers, suffixes are added to variable names
        assert 'value1_0' in ruby_code
        assert 'value1_1' in ruby_code

    def test_comment_mentions_ratio(self):
        normalizers = [
            {
                'operation': 'ratio',
                'target': {'scope': 'get'},
                'params': {'value1_field': 'a.used', 'value2_field': 'a.free'}
            }
        ]
        result = _generate_ratio_get_filter(normalizers)
        comment_text = result[0]['config']['text']
        assert 'Ratio' in comment_text


# ===========================================================================
# _generate_translate_filter
# ===========================================================================

class TestGenerateTranslateFilter:

    def test_returns_none_for_empty_list(self):
        assert _generate_translate_filter([]) is None

    def test_returns_comment_and_translate_filter(self):
        normalizers = [
            {
                'operation': 'translate',
                'target': {'scope': 'table', 'field': 'interface.admin_status'},
                'params': {
                    'mapping': {'1': 'UP', '2': 'DOWN', '3': 'TESTING'}
                }
            }
        ]
        result = _generate_translate_filter(normalizers)
        assert isinstance(result, list)
        assert len(result) == 2
        comment, translate = result
        assert comment['plugin'] == 'comment'
        assert translate['plugin'] == 'translate'

    def test_translate_config_has_correct_source_and_destination(self):
        normalizers = [
            {
                'operation': 'translate',
                'target': {'scope': 'table', 'field': 'interface.oper_status'},
                'params': {'mapping': {'1': 'UP', '2': 'DOWN'}}
            }
        ]
        result = _generate_translate_filter(normalizers)
        translate_config = result[1]['config']
        assert translate_config['source'] == '[interface][oper_status]'
        assert translate_config['destination'] == '[interface][oper_status]'

    def test_translate_config_has_override_true(self):
        normalizers = [
            {
                'operation': 'translate',
                'target': {'scope': 'table', 'field': 'interface.admin_status'},
                'params': {'mapping': {'1': 'UP'}}
            }
        ]
        result = _generate_translate_filter(normalizers)
        assert result[1]['config']['override'] is True

    def test_translate_config_contains_mapping(self):
        mapping = {'1': 'UP', '2': 'DOWN', '3': 'TESTING'}
        normalizers = [
            {
                'operation': 'translate',
                'target': {'scope': 'table', 'field': 'interface.admin_status'},
                'params': {'mapping': mapping}
            }
        ]
        result = _generate_translate_filter(normalizers)
        assert result[1]['config']['dictionary'] == mapping

    def test_skips_normalizer_without_field(self):
        normalizers = [
            {
                'operation': 'translate',
                'target': {'scope': 'table'},  # no 'field'
                'params': {'mapping': {'1': 'UP'}}
            }
        ]
        result = _generate_translate_filter(normalizers)
        assert result is None

    def test_skips_normalizer_without_mapping(self):
        normalizers = [
            {
                'operation': 'translate',
                'target': {'scope': 'table', 'field': 'interface.admin_status'},
                'params': {}  # no 'mapping'
            }
        ]
        result = _generate_translate_filter(normalizers)
        assert result is None

    def test_multiple_translate_normalizers_each_get_own_filter(self):
        normalizers = [
            {
                'operation': 'translate',
                'target': {'scope': 'table', 'field': 'interface.admin_status'},
                'params': {'mapping': {'1': 'UP', '2': 'DOWN'}}
            },
            {
                'operation': 'translate',
                'target': {'scope': 'table', 'field': 'interface.oper_status'},
                'params': {'mapping': {'1': 'UP', '2': 'DOWN', '3': 'TESTING'}}
            }
        ]
        result = _generate_translate_filter(normalizers)
        # Two normalizers → 2 comment + 2 translate = 4 total
        assert len(result) == 4


# ===========================================================================
# _apply_normalizers
# ===========================================================================

class TestApplyNormalizers:

    def test_returns_empty_list_for_none(self):
        assert _apply_normalizers(None) == []

    def test_returns_empty_list_for_empty_list(self):
        assert _apply_normalizers([]) == []

    def test_skips_normalizer_missing_operation(self):
        normalizers = [
            {
                'target': {'scope': 'get', 'field': 'some.field'},
                'params': {'multiply_value': 2}
            }
        ]
        result = _apply_normalizers(normalizers)
        assert result == []

    def test_skips_normalizer_missing_scope(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'field': 'some.field'},  # no 'scope'
                'params': {'multiply_value': 2}
            }
        ]
        result = _apply_normalizers(normalizers)
        assert result == []

    def test_applies_multiply_normalizer(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'get', 'field': 'system.cpu.total.norm.pct'},
                'params': {'multiply_value': 0.01}
            }
        ]
        result = _apply_normalizers(normalizers)
        assert len(result) > 0
        plugin_types = [c['plugin'] for c in result]
        assert 'ruby' in plugin_types

    def test_applies_ratio_normalizer(self):
        normalizers = [
            {
                'operation': 'ratio',
                'target': {'scope': 'get'},
                'params': {
                    'value1_field': 'memory.used',
                    'value2_field': 'memory.free',
                }
            }
        ]
        result = _apply_normalizers(normalizers)
        assert len(result) > 0
        plugin_types = [c['plugin'] for c in result]
        assert 'ruby' in plugin_types

    def test_applies_translate_normalizer(self):
        normalizers = [
            {
                'operation': 'translate',
                'target': {'scope': 'table', 'field': 'interface.admin_status'},
                'params': {'mapping': {'1': 'UP', '2': 'DOWN'}}
            }
        ]
        result = _apply_normalizers(normalizers)
        assert len(result) > 0
        plugin_types = [c['plugin'] for c in result]
        assert 'translate' in plugin_types

    def test_applies_multiple_normalizer_types(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'get', 'field': 'metric.a'},
                'params': {'multiply_value': 0.01}
            },
            {
                'operation': 'translate',
                'target': {'scope': 'table', 'field': 'interface.admin_status'},
                'params': {'mapping': {'1': 'UP'}}
            }
        ]
        result = _apply_normalizers(normalizers)
        plugin_types = [c['plugin'] for c in result]
        assert 'ruby' in plugin_types
        assert 'translate' in plugin_types

    def test_ignores_unknown_operation(self):
        normalizers = [
            {
                'operation': 'unknown_op',
                'target': {'scope': 'get', 'field': 'some.field'},
                'params': {}
            }
        ]
        result = _apply_normalizers(normalizers)
        assert result == []

    def test_table_scope_multiply_is_handled(self):
        normalizers = [
            {
                'operation': 'multiply',
                'target': {'scope': 'table', 'field': 'interface.speed'},
                'params': {'multiply_value': 1000}
            }
        ]
        result = _apply_normalizers(normalizers)
        assert len(result) > 0


# ===========================================================================
# Scope-qualified filter IDs (regression: duplicate Logstash plugin IDs)
# ===========================================================================

class TestScopeQualifiedFilterIds:
    """
    _generate_multiply_get_filter / _generate_ratio_get_filter run for BOTH
    'get' and 'table' scope normalizers, so their generated Logstash filter
    component IDs must be scope-qualified. Otherwise a profile pairing a
    get-scope op with a table-scope op of the same type emits two components
    with an identical plugin ID, and Logstash rejects pipelines with duplicate
    plugin IDs at compile time (the merged pipeline never builds).
    """

    # Mirrors cisco_system_metrics.json (get scope) combined with a Cisco
    # OpenConfig interface-table profile (table scope).
    GET_MULTIPLY = {
        'operation': 'multiply',
        'target': {'scope': 'get', 'field': 'system.cpu.total.norm.pct'},
        'params': {'multiply_value': 0.01},
    }
    TABLE_MULTIPLY = {
        'operation': 'multiply',
        'target': {'scope': 'table', 'field': 'interface.state.speed'},
        'params': {'multiply_value': 1000000},
    }
    GET_RATIO = {
        'operation': 'ratio',
        'target': {'scope': 'get'},
        'params': {
            'value1_field': 'system.memory.actual.used.bytes',
            'value2_field': 'system.memory.actual.free.bytes',
            'total_output_field': 'system.memory.total.bytes',
            'ratio1_output_field': 'system.memory.actual.used.pct',
        },
    }
    TABLE_RATIO = {
        'operation': 'ratio',
        'target': {'scope': 'table'},
        'params': {
            'value1_field': 'interface.state.counters.in_octets',
            'value2_field': 'interface.state.counters.out_octets',
            'total_output_field': 'interface.state.counters.total_octets',
        },
    }

    @staticmethod
    def _assert_unique(components):
        ids = [c['id'] for c in components]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        assert not dupes, f"duplicate filter component IDs: {dupes}"

    def test_multiply_get_and_table_scope_ids_are_scope_qualified(self):
        components = _apply_normalizers([self.GET_MULTIPLY, self.TABLE_MULTIPLY])
        self._assert_unique(components)
        ids = [c['id'] for c in components]
        assert 'normalizer_multiply_get_1' in ids
        assert 'normalizer_multiply_table_1' in ids
        assert 'normalizer_multiply_get_comment_1' in ids
        assert 'normalizer_multiply_table_comment_1' in ids

    def test_ratio_get_and_table_scope_ids_are_scope_qualified(self):
        components = _apply_normalizers([self.GET_RATIO, self.TABLE_RATIO])
        self._assert_unique(components)
        ids = [c['id'] for c in components]
        assert 'normalizer_ratio_get_1' in ids
        assert 'normalizer_ratio_table_1' in ids
        assert 'normalizer_ratio_get_comment_1' in ids
        assert 'normalizer_ratio_table_comment_1' in ids

    def test_combined_profile_all_component_ids_unique(self):
        # The exact scenario that triggered the bug: cisco_system_metrics
        # (get-scope CPU multiply + memory ratio) merged with a Cisco
        # OpenConfig interface-table profile (table-scope multiply + ratio).
        components = _apply_normalizers(
            [self.GET_MULTIPLY, self.GET_RATIO, self.TABLE_MULTIPLY, self.TABLE_RATIO]
        )
        self._assert_unique(components)
        ids = [c['id'] for c in components]
        for expected in (
            'normalizer_multiply_get_1',
            'normalizer_multiply_table_1',
            'normalizer_ratio_get_1',
            'normalizer_ratio_table_1',
        ):
            assert expected in ids, f"missing generated component: {expected}"

    def test_single_get_scope_multiply_keeps_stable_id(self):
        # IDs are always suffixed with _N by _next_id, even on the first call.
        components = _apply_normalizers([self.GET_MULTIPLY])
        ids = [c['id'] for c in components]
        assert ids == ['normalizer_multiply_get_comment_1', 'normalizer_multiply_get_1']
