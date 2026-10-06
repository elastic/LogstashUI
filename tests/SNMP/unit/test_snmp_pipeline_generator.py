#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Tests for SNMP.snmp_pipeline_generator — pure utility functions that require
no database or network access.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.conf import settings

from SNMP.snmp_pipeline_generator import (
    _normalize_template_name,
    _deduplicate_normalizers,
    _uses_keystore,
    _community_key_name,
    _auth_pass_key_name,
    _priv_pass_key_name,
    _es_api_key_name,
    _es_user_key_name,
    _es_password_key_name,
    _ref,
    snmp_credential_keystore_entries,
    snmp_credential_keystore_key_names,
    es_connection_keystore_entries,
    es_connection_keystore_key_names,
    _ruby_table_nested_entry,
    _ruby_row_rename_statements,
    _ruby_row_value_expr,
    _ruby_keep_when_statements,
    _avg_var_name,
    _ruby_avg_pre_loop,
    _ruby_avg_in_loop,
    _ruby_avg_post_loop,
    _generate_table_split_filters,
    _generate_snmp_error_cleanup_filter,
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


# ===========================================================================
# _uses_keystore
# ===========================================================================

class TestUsesKeystore:

    def _network(self, deployment_mode='CENTRALIZED', credential_mode='KEYSTORE'):
        n = MagicMock()
        n.deployment_mode = deployment_mode
        n.credential_mode = credential_mode
        return n

    def test_agent_mode_always_uses_keystore(self):
        assert _uses_keystore(self._network(deployment_mode='AGENT')) is True

    def test_agent_mode_ignores_credential_mode(self):
        assert _uses_keystore(self._network(deployment_mode='AGENT', credential_mode='PLAINTEXT')) is True

    def test_centralized_keystore_mode_uses_keystore(self):
        assert _uses_keystore(self._network(deployment_mode='CENTRALIZED', credential_mode='KEYSTORE')) is True

    def test_centralized_plaintext_mode_no_keystore(self):
        assert _uses_keystore(self._network(deployment_mode='CENTRALIZED', credential_mode='PLAINTEXT')) is False

    def test_missing_deployment_mode_attr_defaults_to_centralized(self):
        n = MagicMock(spec=[])  # no attributes at all → getattr returns default
        n.credential_mode = 'KEYSTORE'
        assert _uses_keystore(n) is True

    def test_missing_credential_mode_defaults_to_keystore(self):
        n = MagicMock(spec=[])
        n.deployment_mode = 'CENTRALIZED'
        assert _uses_keystore(n) is True


# ===========================================================================
# Keystore key-name helpers
# ===========================================================================

class TestKeystoreKeyNameHelpers:

    def _cred(self, cred_id, version):
        c = MagicMock()
        c.id = cred_id
        c.version = version
        return c

    def _conn(self, conn_id):
        c = MagicMock()
        c.id = conn_id
        return c

    # _community_key_name
    def test_community_key_v1(self):
        assert _community_key_name(self._cred(5, '1')) == 'snmp_5_v1'

    def test_community_key_v2c(self):
        assert _community_key_name(self._cred(7, '2c')) == 'snmp_7_v2'

    # _auth_pass_key_name
    def test_auth_pass_key_name(self):
        assert _auth_pass_key_name(self._cred(3, '3')) == 'snmp_3_v3_auth'

    # _priv_pass_key_name
    def test_priv_pass_key_name(self):
        assert _priv_pass_key_name(self._cred(3, '3')) == 'snmp_3_v3_priv'

    # _es_api_key_name
    def test_es_api_key_name(self):
        assert _es_api_key_name(self._conn(10)) == 'snmp_es_10_api_key'

    # _es_user_key_name
    def test_es_user_key_name(self):
        assert _es_user_key_name(self._conn(10)) == 'snmp_es_10_user'

    # _es_password_key_name
    def test_es_password_key_name(self):
        assert _es_password_key_name(self._conn(10)) == 'snmp_es_10_password'

    # _ref
    def test_ref_wraps_in_dollar_braces(self):
        assert _ref('my_key') == '${my_key}'

    def test_ref_preserves_underscores(self):
        assert _ref('snmp_5_v2') == '${snmp_5_v2}'


# ===========================================================================
# snmp_credential_keystore_entries
# ===========================================================================

class TestSnmpCredentialKeystoreEntries:

    def _cred(self, cred_id, version, **kwargs):
        c = MagicMock()
        c.id = cred_id
        c.version = version
        for k, v in kwargs.items():
            setattr(c, k, v)
        return c

    def test_none_credential_returns_empty(self):
        assert snmp_credential_keystore_entries(None) == {}

    def test_v2c_community_included(self):
        cred = self._cred(1, '2c')
        cred.get_community.return_value = 'public'
        entries = snmp_credential_keystore_entries(cred)
        assert 'snmp_1_v2' in entries
        assert entries['snmp_1_v2'] == 'public'

    def test_v1_community_uses_v1_suffix(self):
        cred = self._cred(2, '1')
        cred.get_community.return_value = 'private'
        entries = snmp_credential_keystore_entries(cred)
        assert 'snmp_2_v1' in entries

    def test_v2c_empty_community_not_included(self):
        cred = self._cred(3, '2c')
        cred.get_community.return_value = None
        entries = snmp_credential_keystore_entries(cred)
        assert entries == {}

    def test_v3_authpriv_includes_auth_and_priv(self):
        cred = self._cred(4, '3', security_level='authPriv')
        cred.get_auth_pass.return_value = 'authsecret'
        cred.get_priv_pass.return_value = 'privsecret'
        entries = snmp_credential_keystore_entries(cred)
        assert 'snmp_4_v3_auth' in entries
        assert 'snmp_4_v3_priv' in entries
        assert entries['snmp_4_v3_auth'] == 'authsecret'
        assert entries['snmp_4_v3_priv'] == 'privsecret'

    def test_v3_authnopriv_includes_only_auth(self):
        cred = self._cred(5, '3', security_level='authNoPriv')
        cred.get_auth_pass.return_value = 'authsecret'
        entries = snmp_credential_keystore_entries(cred)
        assert 'snmp_5_v3_auth' in entries
        assert 'snmp_5_v3_priv' not in entries

    def test_v3_noauthnopriv_returns_empty(self):
        cred = self._cred(6, '3', security_level='noAuthNoPriv')
        entries = snmp_credential_keystore_entries(cred)
        assert entries == {}


# ===========================================================================
# snmp_credential_keystore_key_names
# ===========================================================================

class TestSnmpCredentialKeystoreKeyNames:

    def _cred(self, cred_id, version, **kwargs):
        c = MagicMock()
        c.id = cred_id
        c.version = version
        for k, v in kwargs.items():
            setattr(c, k, v)
        return c

    def test_none_returns_empty_set(self):
        assert snmp_credential_keystore_key_names(None) == set()

    def test_v2c_with_community_returns_one_key(self):
        cred = self._cred(1, '2c', community='public')
        names = snmp_credential_keystore_key_names(cred)
        assert names == {'snmp_1_v2'}

    def test_v2c_empty_community_returns_empty(self):
        cred = self._cred(2, '2c', community='')
        names = snmp_credential_keystore_key_names(cred)
        assert names == set()

    def test_v3_authpriv_returns_auth_and_priv_keys(self):
        cred = self._cred(3, '3', security_level='authPriv', auth_pass='x', priv_pass='y')
        names = snmp_credential_keystore_key_names(cred)
        assert 'snmp_3_v3_auth' in names
        assert 'snmp_3_v3_priv' in names

    def test_v3_authnopriv_returns_only_auth_key(self):
        cred = self._cred(4, '3', security_level='authNoPriv', auth_pass='x', priv_pass='')
        names = snmp_credential_keystore_key_names(cred)
        assert 'snmp_4_v3_auth' in names
        assert 'snmp_4_v3_priv' not in names


# ===========================================================================
# es_connection_keystore_entries
# ===========================================================================

class TestEsConnectionKeystoreEntries:

    def _conn(self, conn_id, **kwargs):
        c = MagicMock()
        c.id = conn_id
        for k, v in kwargs.items():
            setattr(c, k, v)
        return c

    def test_none_returns_empty(self):
        assert es_connection_keystore_entries(None) == {}

    def test_api_key_preferred(self):
        conn = self._conn(1, api_key='encrypted_key', username='user', password='pass')
        conn.get_api_key.return_value = 'myapikey'
        entries = es_connection_keystore_entries(conn)
        assert 'snmp_es_1_api_key' in entries
        assert entries['snmp_es_1_api_key'] == 'myapikey'
        assert 'snmp_es_1_user' not in entries

    def test_username_password_used_when_no_api_key(self):
        conn = self._conn(2, api_key=None, username='elastic', password='encrypted_pass')
        conn.get_password.return_value = 'secret'
        entries = es_connection_keystore_entries(conn)
        assert 'snmp_es_2_user' in entries
        assert 'snmp_es_2_password' in entries
        assert entries['snmp_es_2_user'] == 'elastic'
        assert entries['snmp_es_2_password'] == 'secret'

    def test_no_credentials_returns_empty(self):
        conn = self._conn(3, api_key=None, username='', password='')
        entries = es_connection_keystore_entries(conn)
        assert entries == {}


# ===========================================================================
# es_connection_keystore_key_names
# ===========================================================================

class TestEsConnectionKeystoreKeyNames:

    def _conn(self, conn_id, **kwargs):
        c = MagicMock()
        c.id = conn_id
        for k, v in kwargs.items():
            setattr(c, k, v)
        return c

    def test_none_returns_empty_set(self):
        assert es_connection_keystore_key_names(None) == set()

    def test_api_key_returns_api_key_name(self):
        conn = self._conn(1, api_key='something', username='user', password='pass')
        names = es_connection_keystore_key_names(conn)
        assert names == {'snmp_es_1_api_key'}

    def test_username_password_returns_user_and_password_names(self):
        conn = self._conn(2, api_key=None, username='elastic', password='secret')
        names = es_connection_keystore_key_names(conn)
        assert 'snmp_es_2_user' in names
        assert 'snmp_es_2_password' in names

    def test_no_credentials_returns_empty_set(self):
        conn = self._conn(3, api_key=None, username='', password='')
        names = es_connection_keystore_key_names(conn)
        assert names == set()


# ===========================================================================
# _ruby_table_nested_entry
# ===========================================================================

class TestRubyTableNestedEntry:

    def test_flat_table_name(self):
        result = _ruby_table_nested_entry('ifTable', 'row')
        assert result == '"ifTable" => row'

    def test_dotted_table_name_two_levels(self):
        result = _ruby_table_nested_entry('component.fan', 'row')
        assert result == '"component" => { "fan" => row }'

    def test_dotted_table_name_three_levels(self):
        result = _ruby_table_nested_entry('a.b.c', 'val')
        assert result == '"a" => { "b" => { "c" => val } }'

    def test_value_expr_is_preserved(self):
        result = _ruby_table_nested_entry('ifTable', 'event.get("[myfield]")')
        assert 'event.get("[myfield]")' in result


# ===========================================================================
# _ruby_row_rename_statements
# ===========================================================================

class TestRubyRowRenameStatements:

    def test_empty_columns_returns_empty_string(self):
        assert _ruby_row_rename_statements({}) == ''

    def test_flat_column_rename(self):
        result = _ruby_row_rename_statements({'col_a': 'oid1'})
        assert 'row["col_a"] = row.delete("oid1")' in result

    def test_dotted_column_initializes_parent(self):
        result = _ruby_row_rename_statements({'component.speed': 'oid2'})
        assert 'row["component"] ||= {}' in result
        assert 'row["component"]["speed"] = row.delete("oid2")' in result

    def test_two_columns_sharing_parent_initializes_parent_once(self):
        result = _ruby_row_rename_statements({
            'iface.in_octets': 'oid1',
            'iface.out_octets': 'oid2',
        })
        assert result.count('row["iface"] ||= {}') == 1

    def test_multiple_flat_columns(self):
        result = _ruby_row_rename_statements({'a': '1', 'b': '2'})
        assert 'row["a"] = row.delete("1")' in result
        assert 'row["b"] = row.delete("2")' in result

    def test_leaf_siblings_under_shared_nested_parent(self):
        result = _ruby_row_rename_statements({
            'inodes.used.count': 'oid7',
            'inodes.used.pct': 'oid9',
        })
        assert result.count('row["inodes"] ||= {}') == 1
        assert result.count('row["inodes"]["used"] ||= {}') == 1
        assert 'row["inodes"]["used"]["count"] = row.delete("oid7")' in result
        assert 'row["inodes"]["used"]["pct"] = row.delete("oid9")' in result
        assert 'row["inodes"]["used"] = row.delete' not in result


# ===========================================================================
# _avg_var_name
# ===========================================================================

class TestAvgVarName:

    def _normalizer(self, output_field='', target_field='unknown'):
        return {
            'params': {'output_field': output_field},
            'target': {'field': target_field},
        }

    def test_output_field_used_when_set(self):
        n = self._normalizer(output_field='interface.avg_in_octets')
        assert _avg_var_name(n) == 'avg_interface_avg_in_octets'

    def test_dots_replaced_with_underscores(self):
        n = self._normalizer(output_field='a.b.c')
        assert _avg_var_name(n) == 'avg_a_b_c'

    def test_hyphens_replaced_with_underscores(self):
        n = self._normalizer(output_field='some-field')
        assert _avg_var_name(n) == 'avg_some_field'

    def test_fallback_to_target_field_when_no_output_field(self):
        n = self._normalizer(output_field='', target_field='interface.load')
        result = _avg_var_name(n)
        assert result.startswith('avg_')
        assert 'interface' in result


# ===========================================================================
# _ruby_avg_pre_loop / _ruby_avg_in_loop / _ruby_avg_post_loop
# ===========================================================================

class TestRubyAvgLoops:

    def _avg_normalizer(self, output_field, target_field='interface.in_octets'):
        return {
            'operation': 'average',
            'target': {'scope': 'table', 'field': target_field},
            'params': {'output_field': output_field},
        }

    def test_pre_loop_empty_returns_empty_string(self):
        assert _ruby_avg_pre_loop([]) == ''

    def test_pre_loop_declares_sum_and_count(self):
        n = self._avg_normalizer('interface.avg_in_octets', 'interface.in_octets')
        result = _ruby_avg_pre_loop([n])
        assert '_sum = 0.0' in result
        assert '_count = 0' in result

    def test_pre_loop_multiple_normalizers(self):
        n1 = self._avg_normalizer('interface.avg_in', 'interface.in_octets')
        n2 = self._avg_normalizer('interface.avg_out', 'interface.out_octets')
        result = _ruby_avg_pre_loop([n1, n2])
        assert result.count('_sum = 0.0') == 2

    def test_in_loop_empty_returns_empty_string(self):
        assert _ruby_avg_in_loop([], 'interface') == ''

    def test_in_loop_generates_accumulation_statements(self):
        n = self._avg_normalizer('interface.avg_in_octets', 'interface.in_octets')
        result = _ruby_avg_in_loop([n], 'interface')
        assert 'Float(_avg_v)' in result
        assert '_count +=' in result
        assert 'row["in_octets"]' in result
        assert 'is_a?(Numeric)' not in result

    def test_in_loop_strips_dotted_table_prefix(self):
        n = self._avg_normalizer('system.cpu.total.norm.pct', 'component.cpu.load_pct')
        result = _ruby_avg_in_loop([n], 'component.cpu')
        assert 'row["load_pct"]' in result

    def test_post_loop_empty_returns_empty_string(self):
        assert _ruby_avg_post_loop([]) == ''

    def test_post_loop_generates_event_set(self):
        n = self._avg_normalizer('interface.avg_in_octets', 'interface.in_octets')
        result = _ruby_avg_post_loop([n])
        assert 'event.set(' in result
        assert '_count > 0' in result

    def test_post_loop_skips_normalizer_without_output_field(self):
        n = {'operation': 'average', 'target': {}, 'params': {'output_field': ''}}
        assert _ruby_avg_post_loop([n]) == ''

    def test_post_loop_includes_multiply_when_set(self):
        n = self._avg_normalizer('interface.avg_in_octets', 'interface.in_octets')
        n['params']['multiply_value'] = 8
        result = _ruby_avg_post_loop([n])
        assert '* 8' in result


class TestRubyRowValueExpr:

    def test_single_level_column(self):
        assert _ruby_row_value_expr('component.cpu', 'component.cpu.load_pct') == 'row["load_pct"]'

    def test_nested_column(self):
        assert _ruby_row_value_expr(
            'system.filesystem', 'system.filesystem.total.bytes'
        ) == 'row.dig("total", "bytes")'


class TestHostSystemMetricsSplit:

    def test_cpu_average_writes_ecs_field_on_metrics_doc(self):
        oid_mappings = {
            'table': {
                'component.cpu': {
                    'columns': {'load_pct': '1.3.6.1.2.1.25.3.3.1.2'}
                },
            }
        }
        averages = [{
            'operation': 'average',
            'target': {
                'scope': 'table',
                'table': 'component.cpu',
                'field': 'component.cpu.load_pct',
            },
            'params': {
                'output_field': 'system.cpu.total.norm.pct',
                'multiply_value': 0.01,
            },
        }]
        filters = _generate_table_split_filters(oid_mappings, averages)
        cpu = filters[0]['config']['code']
        assert '[system][cpu][total][norm][pct]' in cpu
        assert 'Float(_avg_v)' in cpu
        assert '* 0.01' in cpu

    def test_official_profile_averages_cores_to_ecs_cpu_field(self):
        import json

        path = (
            Path(settings.BASE_DIR)
            / 'SNMP' / 'data' / 'official_profiles' / 'generic_host_system_metrics.json'
        )
        profile = json.loads(path.read_text(encoding='utf-8'))
        average = next(n for n in profile['normalizers'] if n['operation'] == 'average')
        assert average['params']['output_field'] == 'system.cpu.total.norm.pct'
        assert average['params']['multiply_value'] == 0.01
        assert 'promote_output_field' not in average.get('params', {})
        ratio = next(n for n in profile['normalizers'] if n['operation'] == 'ratio')
        assert 'promote_output_field' not in ratio['params']
        assert 'promote_when_type' not in ratio['params']


class TestRubyKeepWhenStatements:

    def test_empty_table_returns_empty_string(self):
        assert _ruby_keep_when_statements({}) == ''
        assert _ruby_keep_when_statements(None) == ''

    def test_emits_delete_and_include_check(self):
        result = _ruby_keep_when_statements({
            'keep_when': {'column': 'type', 'equals': ['10']},
        })
        assert 'row.delete("type")' in result
        assert '["10"].include?(_keep_v.to_s)' in result

    def test_rejects_unsafe_column_names(self):
        result = _ruby_keep_when_statements({
            'keep_when': {'column': 'type"; exit', 'equals': ['10']},
        })
        assert result == ''

    def test_table_split_injects_keep_when_before_event_emit(self):
        oid_mappings = {
            'table': {
                'component.fan': {
                    'columns': {
                        'description': '1.3.6.1.2.1.47.1.1.1.1.2',
                        'type': '1.3.6.1.2.1.99.1.1.1.1',
                    },
                    'keep_when': {'column': 'type', 'equals': ['10']},
                }
            }
        }
        filters = _generate_table_split_filters(oid_mappings)
        code = filters[0]['config']['code']
        assert 'row.delete("type")' in code
        assert '["10"].include?(_keep_v.to_s)' in code
        assert code.index('row.delete("type")') < code.index('LogStash::Event.new')

    def test_tables_without_keep_when_are_unchanged(self):
        oid_mappings = {
            'table': {
                'component.cpu': {
                    'columns': {'load_pct': '1.3.6.1.2.1.25.3.3.1.2'}
                }
            }
        }
        filters = _generate_table_split_filters(oid_mappings)
        code = filters[0]['config']['code']
        assert 'row.delete("type")' not in code
        assert '_keep_v' not in code


class TestPaloaltoComponentsProfile:

    def _profile(self):
        import json
        path = (
            Path(settings.BASE_DIR)
            / 'SNMP' / 'data' / 'official_profiles' / 'paloalto_components.json'
        )
        return json.loads(path.read_text(encoding='utf-8'))

    def test_maps_entity_sensor_onto_cisco_schema(self):
        profile = self._profile()
        fans = profile['table']['component.fan']
        sensors = profile['table']['component.sensor']
        assert fans['columns']['description'] == '1.3.6.1.2.1.47.1.1.1.1.2'
        assert fans['columns']['state'] == '1.3.6.1.2.1.99.1.1.1.5'
        assert fans['columns']['rpm'] == '1.3.6.1.2.1.99.1.1.1.4'
        assert fans['keep_when'] == {'column': 'type', 'equals': ['10']}
        assert sensors['columns']['description'] == '1.3.6.1.2.1.47.1.1.1.1.2'
        assert sensors['columns']['temp.celsius'] == '1.3.6.1.2.1.99.1.1.1.4'
        assert sensors['columns']['state'] == '1.3.6.1.2.1.99.1.1.1.5'
        assert sensors['keep_when'] == {'column': 'type', 'equals': ['8']}
        assert 'temp.threshold' not in sensors['columns']
        assert 'temp.last_shutdown' not in sensors['columns']

    def test_firewall_template_uses_components_not_generic_entity_sensor(self):
        import json
        path = (
            Path(settings.BASE_DIR)
            / 'SNMP' / 'data' / 'official_device_templates' / 'palo_alto_firewall.json'
        )
        template = json.loads(path.read_text(encoding='utf-8'))
        assert 'paloalto_components' in template['profiles']
        assert 'generic_entity_sensor' not in template['profiles']


def _prefix_colliding_paths(names):
    """Return (prefix, child) pairs where prefix is a dotted parent of child.

    Args:
        names: Iterable of dotted field or column names.

    Returns:
        List of colliding pairs. Sibling leaves such as ``used.kb`` and
        ``used.pct`` are not collisions.

    Examples:
        >>> _prefix_colliding_paths(['inodes.used', 'inodes.used.pct'])
        [('inodes.used', 'inodes.used.pct')]
        >>> _prefix_colliding_paths(['used.kb', 'used.pct'])
        []
    """
    names = [n for n in names if isinstance(n, str) and n]
    return [
        (a, b)
        for a in names
        for b in names
        if a != b and b.startswith(a + '.')
    ]


class TestNetapp7modeVolumesProfile:

    def _profile(self):
        import json
        path = (
            Path(settings.BASE_DIR)
            / 'SNMP' / 'data' / 'official_profiles' / 'netapp_7mode_volumes.json'
        )
        return json.loads(path.read_text(encoding='utf-8'))

    def _table_code(self, table_name):
        profile = self._profile()
        filters = _generate_table_split_filters({'table': profile['table']})
        for filt in filters:
            code = filt['config']['code']
            if f'event.get("[{table_name}]")' in code:
                return code
        raise AssertionError(f'no table-split filter for {table_name}')

    def test_filesystem_uses_64bit_kb_oids_and_inode_count(self):
        cols = self._profile()['table']['storage.filesystem']['columns']
        assert cols['total.kb'] == '1.3.6.1.4.1.789.1.5.4.1.29'
        assert cols['used.kb'] == '1.3.6.1.4.1.789.1.5.4.1.30'
        assert cols['avail.kb'] == '1.3.6.1.4.1.789.1.5.4.1.31'
        assert cols['inodes.used.count'] == '1.3.6.1.4.1.789.1.5.4.1.7'
        assert 'inodes.used' not in cols
        assert 'total.kb.64' not in cols
        assert 'used.kb.64' not in cols
        assert 'avail.kb.64' not in cols
        dropped = {
            '1.3.6.1.4.1.789.1.5.4.1.3',
            '1.3.6.1.4.1.789.1.5.4.1.4',
            '1.3.6.1.4.1.789.1.5.4.1.5',
        }
        assert dropped.isdisjoint(cols.values())

    def test_aggregate_uses_64bit_kb_oids(self):
        cols = self._profile()['table']['storage.aggregate']['columns']
        assert cols['total.kb'] == '1.3.6.1.4.1.789.1.17.15.2.1.14'
        assert cols['used.kb'] == '1.3.6.1.4.1.789.1.17.15.2.1.15'
        assert cols['avail.kb'] == '1.3.6.1.4.1.789.1.17.15.2.1.16'
        assert 'total.kb.64' not in cols
        dropped = {
            '1.3.6.1.4.1.789.1.17.15.2.1.5',
            '1.3.6.1.4.1.789.1.17.15.2.1.6',
            '1.3.6.1.4.1.789.1.17.15.2.1.7',
        }
        assert dropped.isdisjoint(cols.values())

    def test_inode_percent_normalizer_path_unchanged(self):
        inode_pct = next(
            n for n in self._profile()['normalizers']
            if n.get('target', {}).get('field') == 'storage.filesystem.inodes.used.pct'
        )
        assert inode_pct['operation'] == 'multiply'
        assert inode_pct['params']['multiply_value'] == 0.01

    def test_filesystem_ruby_does_not_index_into_scalars(self):
        code = self._table_code('storage.filesystem')
        assert 'row["inodes"]["used"]["count"]' in code
        assert 'row["inodes"]["used"]["pct"]' in code
        assert 'row["inodes"]["used"] = row.delete' not in code
        assert '["kb"]["64"]' not in code
        assert 'row.delete("1.3.6.1.4.1.789.1.5.4.1.29")' in code
        assert 'row.delete("1.3.6.1.4.1.789.1.5.4.1.3")' not in code

    def test_aggregate_ruby_does_not_nest_kb_width(self):
        code = self._table_code('storage.aggregate')
        assert '["kb"]["64"]' not in code
        assert 'row.delete("1.3.6.1.4.1.789.1.17.15.2.1.14")' in code
        assert 'row.delete("1.3.6.1.4.1.789.1.17.15.2.1.5")' not in code


class TestOfficialProfileFieldPaths:

    def test_no_prefix_colliding_dotted_paths(self):
        import json
        profile_dir = Path(settings.BASE_DIR) / 'SNMP' / 'data' / 'official_profiles'
        collisions = []
        for path in sorted(profile_dir.glob('*.json')):
            data = json.loads(path.read_text(encoding='utf-8'))
            for section in ('get', 'walk'):
                hits = _prefix_colliding_paths((data.get(section) or {}).keys())
                collisions.extend((path.name, section, a, b) for a, b in hits)
            for table_name, table_data in (data.get('table') or {}).items():
                cols = (table_data or {}).get('columns') or {}
                hits = _prefix_colliding_paths(cols.keys())
                collisions.extend(
                    (path.name, f'table:{table_name}', a, b) for a, b in hits
                )
        assert collisions == []


# ===========================================================================
# _generate_snmp_error_cleanup_filter
# ===========================================================================

class TestGenerateSnmpErrorCleanupFilter:

    def test_returns_a_dict(self):
        result = _generate_snmp_error_cleanup_filter()
        assert isinstance(result, dict)

    def test_plugin_is_ruby(self):
        result = _generate_snmp_error_cleanup_filter()
        assert result['plugin'] == 'ruby'

    def test_has_id(self):
        result = _generate_snmp_error_cleanup_filter()
        assert 'id' in result and result['id']

    def test_code_contains_error_cleanup_logic(self):
        result = _generate_snmp_error_cleanup_filter()
        code = result['config']['code']
        assert 'error' in code.lower()
