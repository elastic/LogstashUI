#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Tests for SNMP.snmp_pipeline_generator — pure utility functions that require
no database or network access.
"""

import pytest

from SNMP.snmp_pipeline_generator import (
    _normalize_template_name,
    _deduplicate_normalizers,
)


# ===========================================================================
# _normalize_template_name
# ===========================================================================

class TestNormalizeTemplateName:
    """Tests for the ES-index-safe name normalizer."""

    def test_empty_string_returns_fallback(self):
        assert _normalize_template_name('') == 'unknown_template'

    def test_none_returns_fallback(self):
        assert _normalize_template_name(None) == 'unknown_template'

    def test_plain_name_lowercased(self):
        assert _normalize_template_name('Cisco') == 'cisco'

    def test_spaces_replaced_with_underscore(self):
        assert _normalize_template_name('My Template') == 'my_template'

    def test_multiple_spaces_collapsed(self):
        assert _normalize_template_name('My  Template') == 'my_template'

    def test_tabs_and_newlines_replaced(self):
        result = _normalize_template_name('a\tb\nc')
        assert result == 'a_b_c'

    def test_es_illegal_chars_replaced(self):
        # Characters: * : / \ ? " < > | , # space
        for char in ['*', ':', '/', '\\', '?', '"', '<', '>', '|', ',', '#']:
            result = _normalize_template_name(f'name{char}value')
            assert result == 'name_value', f"Failed for char {char!r}"

    def test_consecutive_underscores_collapsed(self):
        assert _normalize_template_name('a__b') == 'a_b'

    def test_consecutive_hyphens_collapsed(self):
        assert _normalize_template_name('a--b') == 'a_b'

    def test_mixed_separators_collapsed(self):
        assert _normalize_template_name('a-_b') == 'a_b'

    def test_leading_hyphen_stripped(self):
        assert _normalize_template_name('-name') == 'name'

    def test_leading_underscore_stripped(self):
        assert _normalize_template_name('_name') == 'name'

    def test_leading_plus_stripped(self):
        assert _normalize_template_name('+name') == 'name'

    def test_leading_dot_stripped(self):
        assert _normalize_template_name('.name') == 'name'

    def test_already_clean_name_unchanged(self):
        assert _normalize_template_name('dell_idrac') == 'dell_idrac'

    def test_alphanumeric_with_single_hyphen_preserved(self):
        # Single hyphens are NOT replaced — only runs of 2+ hyphens/underscores are collapsed
        assert _normalize_template_name('cisco-catalyst-9300') == 'cisco-catalyst-9300'

    def test_numeric_only_name(self):
        assert _normalize_template_name('1234') == '1234'

    def test_surrounding_whitespace_stripped(self):
        assert _normalize_template_name('  cisco  ') == 'cisco'

    def test_all_forbidden_leading_chars_stripped(self):
        # Multiple leading forbidden chars
        result = _normalize_template_name('---___name')
        assert result == 'name'

    def test_result_is_255_bytes_max(self):
        # Build a name that would exceed 255 bytes when encoded
        long_name = 'a' * 300
        result = _normalize_template_name(long_name)
        assert len(result.encode('utf-8')) <= 255

    def test_name_that_becomes_empty_after_stripping_returns_fallback(self):
        # A name consisting only of forbidden leading chars
        result = _normalize_template_name('---')
        assert result == 'unknown_template'

    def test_real_world_dell_idrac(self):
        assert _normalize_template_name('Dell iDRAC') == 'dell_idrac'

    def test_real_world_ubiquiti(self):
        assert _normalize_template_name('Ubiquiti UniFi AP') == 'ubiquiti_unifi_ap'

    def test_real_world_brocade(self):
        assert _normalize_template_name('Brocade FC Switch') == 'brocade_fc_switch'


# ===========================================================================
# _deduplicate_normalizers
# ===========================================================================

class TestDeduplicateNormalizers:

    def _make_normalizer(self, operation, field, param_value):
        return {
            'operation': operation,
            'target': {'scope': 'get', 'field': field},
            'params': {'multiply_value': param_value}
        }

    def test_returns_empty_for_none(self):
        assert _deduplicate_normalizers(None) == []

    def test_returns_empty_for_empty_list(self):
        assert _deduplicate_normalizers([]) == []

    def test_single_normalizer_returned_unchanged(self):
        n = self._make_normalizer('multiply', 'metric.a', 0.01)
        result = _deduplicate_normalizers([n])
        assert result == [n]

    def test_identical_normalizers_deduplicated(self):
        n = self._make_normalizer('multiply', 'metric.a', 0.01)
        result = _deduplicate_normalizers([n, n])
        assert len(result) == 1

    def test_different_normalizers_both_kept(self):
        n1 = self._make_normalizer('multiply', 'metric.a', 0.01)
        n2 = self._make_normalizer('multiply', 'metric.b', 0.01)
        result = _deduplicate_normalizers([n1, n2])
        assert len(result) == 2

    def test_different_operations_both_kept(self):
        n1 = {
            'operation': 'multiply',
            'target': {'scope': 'get', 'field': 'metric.a'},
            'params': {'multiply_value': 0.01}
        }
        n2 = {
            'operation': 'ratio',
            'target': {'scope': 'get'},
            'params': {'value1_field': 'metric.a', 'value2_field': 'metric.b'}
        }
        result = _deduplicate_normalizers([n1, n2])
        assert len(result) == 2

    def test_duplicate_with_different_param_value_both_kept(self):
        n1 = self._make_normalizer('multiply', 'metric.a', 0.01)
        n2 = self._make_normalizer('multiply', 'metric.a', 100)
        result = _deduplicate_normalizers([n1, n2])
        assert len(result) == 2

    def test_three_duplicates_only_one_kept(self):
        n = self._make_normalizer('multiply', 'metric.a', 0.01)
        result = _deduplicate_normalizers([n, n, n])
        assert len(result) == 1

    def test_mixed_duplicates_and_unique(self):
        n1 = self._make_normalizer('multiply', 'metric.a', 0.01)
        n2 = self._make_normalizer('multiply', 'metric.b', 0.01)
        result = _deduplicate_normalizers([n1, n1, n2])
        assert len(result) == 2

    def test_order_preserved_for_unique_normalizers(self):
        n1 = self._make_normalizer('multiply', 'metric.a', 0.01)
        n2 = self._make_normalizer('multiply', 'metric.b', 0.01)
        n3 = self._make_normalizer('multiply', 'metric.c', 0.01)
        result = _deduplicate_normalizers([n1, n2, n3])
        assert result[0] == n1
        assert result[1] == n2
        assert result[2] == n3

    def test_first_occurrence_kept_on_duplicate(self):
        n1 = self._make_normalizer('multiply', 'metric.a', 0.01)
        n2 = self._make_normalizer('multiply', 'metric.a', 0.01)
        result = _deduplicate_normalizers([n1, n2])
        assert result[0] is n1
