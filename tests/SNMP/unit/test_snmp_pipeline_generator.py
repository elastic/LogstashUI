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
    _generate_output,
    _es_connection_uses_tls,
    _parse_ssl_certificate_authorities,
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
# _generate_output  --  ssl_verification_mode follows allow_self_signed_certs
# ===========================================================================

class TestGenerateOutputTlsVerification:

    def _network(self, **conn_kwargs):
        conn = MagicMock()
        conn.id = 7
        conn.cloud_id = None
        conn.host = "https://es.example.com"
        conn.port = 9200
        conn.api_key = None
        conn.username = "elastic"
        conn.password = "x"
        conn.allow_self_signed_certs = False
        for k, v in conn_kwargs.items():
            setattr(conn, k, v)
        conn.get_es_hosts.return_value = [f"{conn.host}:{conn.port}"] if conn.host else []
        net = MagicMock()
        net.id = 1
        net.connection = conn
        net.namespace = "default"
        net.deployment_mode = "CENTRALIZED"
        net.credential_mode = "KEYSTORE"
        net.ssl_certificate_authorities = ""
        return net

    def _config(self, net):
        return _generate_output(net)[0]["config"]

    def test_self_signed_allowed_https_sets_mode_none(self):
        cfg = self._config(self._network(allow_self_signed_certs=True))
        assert cfg["ssl_verification_mode"] == "none"

    def test_self_signed_allowed_cloud_id_omits_setting(self):
        """Cloud ID connections keep full verification even when the flag is on."""
        net = self._network(allow_self_signed_certs=True, cloud_id="dep:abc", host=None)
        assert "ssl_verification_mode" not in self._config(net)

    def test_strict_connection_omits_setting(self):
        cfg = self._config(self._network(allow_self_signed_certs=False))
        assert "ssl_verification_mode" not in cfg

    @pytest.mark.parametrize("host", ["http://localhost", "localhost"])
    def test_plain_http_host_omits_setting_even_when_allowed(self, host):
        cfg = self._config(self._network(allow_self_signed_certs=True, host=host))
        assert "ssl_verification_mode" not in cfg

    @pytest.mark.parametrize("snmp_type", ["polling", "traps", "discovery"])
    def test_applies_to_every_snmp_output_type(self, snmp_type):
        net = self._network(allow_self_signed_certs=True)
        cfg = _generate_output(net, snmp_type=snmp_type)[0]["config"]
        assert cfg["ssl_verification_mode"] == "none"


class TestGenerateOutputCertificateAuthorities:
    """``Network.ssl_certificate_authorities`` -> ``ssl_certificate_authorities``."""

    def _net(self, cas, allow_self_signed=False, host="https://es.example.com"):
        conn = MagicMock()
        conn.id = 7
        conn.cloud_id = None
        conn.host = host
        conn.port = 9200
        conn.api_key = None
        conn.username = "elastic"
        conn.password = "x"
        conn.allow_self_signed_certs = allow_self_signed
        conn.get_es_hosts.return_value = [f"{host}:9200"] if host else []
        net = MagicMock()
        net.id = 1
        net.connection = conn
        net.namespace = "default"
        net.deployment_mode = "CENTRALIZED"
        net.credential_mode = "KEYSTORE"
        net.ssl_certificate_authorities = cas
        return net

    def _config(self, net):
        return _generate_output(net)[0]["config"]

    def test_single_path_becomes_one_element_list(self):
        cfg = self._config(self._net("/etc/logstash/ca.crt"))
        assert cfg["ssl_certificate_authorities"] == ["/etc/logstash/ca.crt"]

    def test_comma_separated_paths_are_split_and_trimmed(self):
        cfg = self._config(self._net(" /a/ca.crt ,/b/ca.pem,  /c/ca.cer "))
        assert cfg["ssl_certificate_authorities"] == ["/a/ca.crt", "/b/ca.pem", "/c/ca.cer"]

    def test_empty_entries_are_dropped(self):
        cfg = self._config(self._net("/a/ca.crt,, ,/b/ca.pem,"))
        assert cfg["ssl_certificate_authorities"] == ["/a/ca.crt", "/b/ca.pem"]

    @pytest.mark.parametrize("blank", ["", "   ", ",", " , ,"])
    def test_blank_value_omits_setting(self, blank):
        assert "ssl_certificate_authorities" not in self._config(self._net(blank))

    def test_cas_replace_verification_none_when_self_signed_allowed(self):
        """CAs mean 'verify against these', so verification must not be disabled."""
        cfg = self._config(self._net("/a/ca.crt", allow_self_signed=True))
        assert cfg["ssl_certificate_authorities"] == ["/a/ca.crt"]
        assert "ssl_verification_mode" not in cfg

    def test_without_cas_self_signed_still_sets_verification_none(self):
        cfg = self._config(self._net("", allow_self_signed=True))
        assert cfg["ssl_verification_mode"] == "none"
        assert "ssl_certificate_authorities" not in cfg

    def test_cas_omitted_for_plain_http_connection(self):
        cfg = self._config(self._net("/a/ca.crt", host="http://es.example.com"))
        assert "ssl_certificate_authorities" not in cfg
        assert "ssl_verification_mode" not in cfg

    def test_cas_emitted_for_cloud_id_connection(self):
        net = self._net("/a/ca.crt", host="")
        net.connection.cloud_id = "name:abc123"
        assert self._config(net)["ssl_certificate_authorities"] == ["/a/ca.crt"]

    def test_rendered_pipeline_contains_cas_array(self):
        """The generated component converts to valid LSCL with a quoted array."""
        from Common.logstash_config_parse import ComponentToPipeline

        net = self._net("/etc/logstash/ca one.crt, /etc/logstash/ca2.pem")
        lscl = ComponentToPipeline(
            {"output": _generate_output(net)}, test=False
        ).components_to_logstash_config()
        assert 'ssl_certificate_authorities => ["/etc/logstash/ca one.crt", "/etc/logstash/ca2.pem"]' in lscl
        assert "ssl_verification_mode" not in lscl


class TestParseSslCertificateAuthorities:

    @pytest.mark.parametrize("value, expected", [
        ("/a.crt", ["/a.crt"]),
        ("/a.crt,/b.crt", ["/a.crt", "/b.crt"]),
        (" /a.crt , /b.crt ", ["/a.crt", "/b.crt"]),
        ("/a.crt,,/b.crt,", ["/a.crt", "/b.crt"]),
        ("", []),
        (None, []),
        (123, []),
    ])
    def test_cases(self, value, expected):
        assert _parse_ssl_certificate_authorities(value) == expected


class TestEsConnectionUsesTls:

    @pytest.mark.parametrize("cloud_id, host, expected", [
        ("dep:abc", None, True),
        (None, "https://es.example.com", True),
        (None, "HTTPS://ES.EXAMPLE.COM", True),
        (None, "http://es.example.com", False),
        (None, "es.example.com", False),
        (None, None, False),
    ])
    def test_cases(self, cloud_id, host, expected):
        c = MagicMock()
        c.cloud_id = cloud_id
        c.get_es_hosts.return_value = [host] if host else []
        assert _es_connection_uses_tls(c) is expected


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


# ===========================================================================
# Kibana Hosts page compatibility
# ===========================================================================

def _official_profile(name):
    import json
    path = Path(settings.BASE_DIR) / 'SNMP' / 'data' / 'official_profiles' / f'{name}.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _snmp_template():
    import json
    path = Path(settings.BASE_DIR) / 'SNMP' / 'data' / 'snmp_template.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _mapping_at(properties, dotted):
    node = {'properties': properties}
    for part in dotted.split('.'):
        node = node.get('properties', {}).get(part)
        if node is None:
            return None
    return node


def _elastic_system_mappings():
    import json
    path = Path(__file__).parent / 'data' / 'elastic_system_mappings.json'
    return json.loads(path.read_text(encoding='utf-8'))['fields']


def _template_leaves(properties, prefix=''):
    """Yield dotted paths of mapped leaf fields.

    Example:
        >>> list(_template_leaves({'a': {'properties': {'b': {'type': 'long'}}}}))
        ['a.b']
    """
    for name, child in properties.items():
        if 'properties' in child:
            yield from _template_leaves(child['properties'], f'{prefix}{name}.')
        else:
            yield f'{prefix}{name}'


_PROFILE_OUTPUT_PARAMS = (
    'output_field', 'total_output_field', 'ratio1_output_field', 'ratio2_output_field',
    'complement_ratio_output_field', 'divide_output_field', 'difference_output_field',
)


def _fields_written_by_official_profiles():
    """Return every field an official profile or the generator writes."""
    import json
    fields = {'host.name', 'host.hostname', 'host.ip', 'metricset.period'}
    base = Path(settings.BASE_DIR) / 'SNMP' / 'data' / 'official_profiles'
    for path in base.glob('*.json'):
        profile = json.loads(path.read_text(encoding='utf-8'))
        for section in ('get', 'walk'):
            fields.update(profile.get(section) or {})
        for table, table_data in (profile.get('table') or {}).items():
            fields.update(f'{table}.{col}' for col in (table_data.get('columns') or {}))
        for normalizer in profile.get('normalizers') or []:
            params = normalizer.get('params') or {}
            fields.update(params[k] for k in _PROFILE_OUTPUT_PARAMS if params.get(k))
            fields.update(params.get('output_fields') or [])
    return fields


class TestGenerateFiltersHostFields:

    def _add_fields(self, network):
        from SNMP.snmp_pipeline_generator import _generate_filters
        filters = _generate_filters({'get': {}, 'walk': {}, 'table': {}}, network)
        return next(f['config']['add_field'] for f in filters if f['id'] == 'filter_mutate_2')

    def test_metricset_period_is_interval_in_ms(self):
        network = MagicMock(interval=60)
        network.__str__.return_value = 'net'
        fields = self._add_fields(network)
        assert fields['[metricset][period]'] == '60000'
        assert fields['[metricset][module]'] == 'snmp'

    def test_metricset_period_defaults_to_30s(self):
        network = MagicMock(interval=None)
        network.__str__.return_value = 'net'
        assert self._add_fields(network)['[metricset][period]'] == '30000'


class TestHostsPageModule:

    def _filters(self):
        from SNMP.snmp_pipeline_generator import _generate_filters
        network = MagicMock(interval=60)
        network.__str__.return_value = 'net'
        normalizers = [
            {'operation': 'multiply', 'target': {'scope': 'get', 'field': 'system.cpu.active.pct'},
             'params': {'multiply_value': 0.01, 'output_field': 'system.cpu.total.norm.pct'}},
            {'operation': 'ratio', 'target': {'scope': 'table', 'table': 'interface'},
             'params': {'value1_field': 'interface.a', 'value2_field': 'interface.b',
                        'ratio1_output_field': 'interface.r'}},
        ]
        oids = {'get': {}, 'walk': {}, 'table': {'interface': {'columns': {'a': '1.2', 'b': '1.3'}}}}
        return _generate_filters(oids, network, normalizers)

    def test_checks_every_hosts_page_field_on_metrics_doc_only(self):
        from SNMP.snmp_pipeline_generator import HOSTS_PAGE_FIELDS, _format_field_name
        config = next(f for f in self._filters() if f['id'] == 'filter_hosts_page_module')['config']
        condition = config['condition']
        assert condition.startswith('[tsds][category] == "metrics" and (')
        for field in HOSTS_PAGE_FIELDS:
            assert _format_field_name(field) in condition
        assert config['plugins'][0]['config'] == {'replace': {'[metricset][module]': 'system'}}

    def test_runs_after_normalizers_and_table_splits(self):
        ids = [f['id'] for f in self._filters()]
        position = ids.index('filter_hosts_page_module')
        later = ids[position + 1:]
        assert not any(i.startswith(('normalizer_', 'comp_table_split_')) for i in later)

    def test_network_traffic_does_not_qualify(self):
        from SNMP.snmp_pipeline_generator import HOSTS_PAGE_FIELDS
        assert not any(f.startswith('host.network') for f in HOSTS_PAGE_FIELDS)


class TestGenerateInputNormalizerDedup:

    def test_groups_sharing_a_filter_chain_emit_each_normalizer_once(self, monkeypatch):
        """Two credentials make two inputs; the shared filters must not run normalizers twice."""
        import SNMP.snmp_pipeline_generator as gen

        count_cpus = {
            'operation': 'sum_column',
            'target': {'scope': 'table', 'table': 'component.cpu', 'field': 'component.cpu.load_pct'},
            'params': {'output_field': 'system.cpu.num_cpus', 'mode': 'count'},
        }
        monkeypatch.setattr(gen, '_get_device_profiles', lambda device, cache=None: (
            [1], {'get': {}, 'walk': {}, 'table': {}}, [dict(count_cpus)]))

        def device(cred_id):
            credential = MagicMock(id=cred_id, version='2c')
            template = MagicMock(id=7, type='server', vendor='net-snmp', product='Linux', model='Any')
            template.name = 'Generic Linux'
            return MagicMock(device_template=template, credential=credential,
                             hostname='h', port=161, timeout=1000, retries=2)

        network = MagicMock(id=1, interval=30, deployment_mode='AGENT')
        inputs, _, normalizers = gen._generate_input({
            'network': network,
            'devices': {'v1_v2c': {'a': device(1), 'b': device(2)}, 'v3': {}},
        })
        assert len(inputs) == 2
        assert normalizers == [count_cpus]


class TestRowMetricsetModule:

    def _code(self, table_name):
        filters = _generate_table_split_filters(
            {'table': {table_name: {'columns': {'index': '1.2.3'}}}})
        return filters[0]['config']['code']

    def test_system_tables_get_system_module(self):
        for table in ('system.filesystem', 'system.storage', 'system.diskio'):
            assert '"metricset" => { "module" => "system" }' in self._code(table)

    def test_other_tables_keep_snmp_module(self):
        for table in ('interface', 'component.cpu', 'systemish'):
            assert '"metricset" => { "module" => "snmp" }' in self._code(table)

    def test_rows_carry_host_ip(self):
        code = self._code('interface')
        assert 'host_ip = event.get("[host][ip]")' in code
        assert 'new_event.set("[host][ip]", host_ip) if host_ip' in code


class TestKeepWhenKeepColumn:

    def test_keep_column_reads_without_deleting(self):
        result = _ruby_keep_when_statements({
            'keep_when': {'column': 'type', 'equals': ['1.3.6.1.2.1.25.2.1.4'], 'keep_column': True},
        })
        assert '_keep_v = row["type"]' in result
        assert 'row.delete' not in result


class TestSumColumn:

    def _sum(self, **params):
        base = {'output_field': 'host.network.ingress.bytes'}
        base.update(params)
        return {
            'operation': 'sum_column',
            'target': {'scope': 'table', 'table': 'interface', 'field': 'interface.in_octets'},
            'params': base,
        }

    def _filter(self, normalizer):
        oid_mappings = {'table': {'interface': {'columns': {
            'index': '1.3.6.1.2.1.2.2.1.1',
            'type': '1.3.6.1.2.1.2.2.1.3',
            'in_octets': '1.3.6.1.2.1.31.1.1.1.6',
        }}}}
        return _generate_table_split_filters(oid_mappings, [normalizer])[0]

    def test_value_mode_sums_onto_metrics_doc(self):
        filt = self._filter(self._sum())
        code = filt['config']['code']
        assert 'sum_host_network_ingress_bytes_sum += _sum_f' in code
        assert ('event.set("[host][network][ingress][bytes]", sum_host_network_ingress_bytes_sum) '
                'if sum_host_network_ingress_bytes_count > 0 && !sum_host_network_ingress_bytes_incomplete') in code
        assert 'init' not in filt['config']
        assert code.index('sum_host_network_ingress_bytes_sum += _sum_f') < code.index('LogStash::Event.new')
        assert code.index('event.remove("[interface]")') < code.index('event.set("[host][network]')

    def test_delta_mode_uses_counter_state_keyed_per_row(self):
        from SNMP.snmp_normalizers import COUNTER_DELTA_RUBY_INIT
        filt = self._filter(self._sum(mode='delta'))
        code = filt['config']['code']
        assert filt['config']['init'] == COUNTER_DELTA_RUBY_INIT
        assert '_sum_f = lsui_counter_delta(_sum_key, _sum_f)' in code
        assert '#{row["index"] || _row_counter}|interface.in_octets' in code
        assert 'sum_host_network_ingress_bytes_incomplete = true' in code

    def test_exclude_values_guard_every_accumulation(self):
        code = self._filter(self._sum(mode='delta', exclude_column='type', exclude_values=['24']))['config']['code']
        guard = 'unless ["24"].include?(row["type"].to_s)'
        assert code.count(guard) == 3

    def test_unsafe_exclude_is_ignored(self):
        code = self._filter(self._sum(exclude_column='type"; exit', exclude_values=['24']))['config']['code']
        assert 'exit' not in code
        assert 'include?(row[' not in code

    def test_count_mode_adds_one_per_row(self):
        code = self._filter(self._sum(mode='count'))['config']['code']
        assert '_sum_f = 1.0' in code

    def test_unsafe_output_field_is_dropped(self):
        code = self._filter(self._sum(output_field='x"; exit'))['config']['code']
        assert 'exit' not in code

    def test_generate_filters_excludes_sum_column_from_standalone_normalizers(self):
        from SNMP.snmp_pipeline_generator import _generate_filters
        network = MagicMock(interval=30)
        network.__str__.return_value = 'net'
        oid_mappings = {'get': {}, 'walk': {}, 'table': {'interface': {'columns': {
            'in_octets': '1.3.6.1.2.1.31.1.1.1.6'}}}}
        filters = _generate_filters(oid_mappings, network, [self._sum(mode='delta')])
        assert not any('sum_column' in f['id'] for f in filters)
        split = next(f for f in filters if f['id'] == 'comp_table_split_interface')
        assert 'lsui_counter_delta' in split['config']['code']


class TestKibanaHostProfiles:

    def test_ucd_load_uses_numeric_la_load_int(self):
        profile = _official_profile('generic_ucd_system_metrics')
        for minutes, suffix in (('1', '1'), ('5', '2'), ('15', '3')):
            assert profile['get'][f'system.load.{minutes}'] == f'1.3.6.1.4.1.2021.10.1.5.{suffix}'
            assert any(
                n['operation'] == 'multiply' and n['target'].get('field') == f'system.load.{minutes}'
                and n['params']['multiply_value'] == 0.01
                for n in profile['normalizers']
            )

    def test_ucd_cpu_states_use_kernel_ticks_not_system(self):
        profile = _official_profile('generic_ucd_system_metrics')
        deltas = {n['target']['field']: n['params']['output_field']
                  for n in profile['normalizers'] if n['operation'] == 'counter_delta'}
        assert deltas['system.cpu.raw.kernel'] == 'system.cpu.delta.system'
        assert 'system.cpu.raw.system' not in deltas
        share = next(n for n in profile['normalizers'] if n['operation'] == 'share')
        assert share['params']['input_fields'] == list(deltas.values())
        assert share['params']['multiply_field'] == 'system.cpu.cores'

    def test_ucd_memory_chain_is_ordered(self):
        ops = [(n['operation'], n['params'].get('output_field') or n['params'].get('difference_output_field'))
               for n in _official_profile('generic_ucd_system_metrics')['normalizers']]
        used_kb = ops.index(('ratio', 'system.memory.actual.used.kb'))
        assert used_kb < ops.index(('sum', 'system.memory.used.kb'))
        assert used_kb < ops.index(('multiply', 'system.memory.actual.used.bytes'))
        assert ops.index(('sum', 'system.memory.used.kb')) < ops.index(('multiply', 'system.memory.used.bytes'))

    def test_host_resources_splits_disks_from_memory(self):
        tables = _official_profile('generic_host_system_metrics')['table']
        disk = set(tables['system.filesystem']['keep_when']['equals'])
        other = set(tables['system.storage']['keep_when']['equals'])
        assert disk == {'1.3.6.1.2.1.25.2.1.4', '1.3.6.1.2.1.25.2.1.10'}
        assert '1.3.6.1.2.1.25.2.1.2' in other
        assert not disk & other
        assert tables['system.filesystem']['keep_when']['keep_column'] is True

    def test_host_resources_scales_blocks_to_bytes(self):
        normalizers = _official_profile('generic_host_system_metrics')['normalizers']
        for table in ('system.filesystem', 'system.storage'):
            for col in ('total', 'used.bytes'):
                assert any(
                    n['operation'] == 'multiply' and n['target']['field'] == f'{table}.{col}'
                    and n['params']['multiply_field'] == f'{table}.allocation_units'
                    for n in normalizers
                ), (table, col)

    def test_interfaces_write_host_network_deltas(self):
        sums = {n['params']['output_field']: n for n in _official_profile('generic_interfaces')['normalizers']
                if n['operation'] == 'sum_column'}
        for output, column in (('host.network.ingress.bytes', 'interface.in_octets'),
                               ('host.network.egress.bytes', 'interface.out_octets')):
            assert sums[output]['target']['field'] == column
            assert sums[output]['params']['mode'] == 'delta'
            assert sums[output]['params']['exclude_values'] == ['24']

    def test_templates_do_not_map_one_key_to_two_oids(self):
        """A collision makes the generator rename the key to ``<key>.<profile>``."""
        import json
        data = Path(settings.BASE_DIR) / 'SNMP' / 'data'
        known = {('eaton_ups', 'observer.model'), ('eaton_ups', 'observer.firmware_version')}
        collisions = []
        for path in sorted((data / 'official_device_templates').glob('*.json')):
            oids = {}
            for name in json.loads(path.read_text(encoding='utf-8')).get('profiles', []):
                profile_path = data / 'official_profiles' / f'{name}.json'
                if not profile_path.exists():
                    continue
                profile = json.loads(profile_path.read_text(encoding='utf-8'))
                for section in ('get', 'walk'):
                    for key, oid in (profile.get(section) or {}).items():
                        oids.setdefault(key, set()).add(oid)
            collisions += [(path.stem, k) for k, v in oids.items() if len(v) > 1]
        assert set(collisions) == known

    def test_no_official_profile_writes_memory_total_object(self):
        import json
        base = Path(settings.BASE_DIR) / 'SNMP' / 'data' / 'official_profiles'
        for path in base.glob('*.json'):
            text = path.read_text(encoding='utf-8')
            assert 'system.memory.total.' not in text, path.name


class TestIsilonProfiles:
    """OIDs follow ISILON-MIB (1.3.6.1.4.1.12124)."""

    def test_ifs_capacity_counters_follow_mib_order(self):
        get = _official_profile('isilon_system')['get']
        base = '1.3.6.1.4.1.12124.1.3'
        assert get['storage.disk.total.bytes'] == f'{base}.1.0'
        assert get['storage.disk.used.bytes'] == f'{base}.2.0'
        assert get['storage.disk.avail.bytes'] == f'{base}.3.0'
        assert get['storage.disk.free.bytes'] == f'{base}.4.0'

    def test_used_pct_is_used_over_total(self):
        ratio = next(n for n in _official_profile('isilon_system')['normalizers'] if n['operation'] == 'ratio')
        assert ratio['params']['value1_field'] == 'storage.disk.total.bytes'
        assert ratio['params']['value2_field'] == 'storage.disk.used.bytes'
        assert ratio['params']['divide_output_field'] == 'storage.disk.used.pct'

    def test_node_status_oids_are_not_read_as_metrics(self):
        profiles = [_official_profile(n) for n in ('isilon_system', 'isilon_performance', 'isilon_protocols')]
        status = {f'1.3.6.1.4.1.12124.2.1.{i}.0' for i in range(1, 5)}
        for profile in profiles:
            for key, oid in profile['get'].items():
                if oid in status:
                    assert key.startswith('observer.node.'), key
        assert profiles[0]['get']['observer.node.name'] == '1.3.6.1.4.1.12124.2.1.1.0'

    def test_cpu_scalars_and_table_are_per_mil(self):
        profile = _official_profile('isilon_performance')
        scaled = {n['target']['field'] for n in profile['normalizers']
                  if n['operation'] == 'multiply' and n['params'].get('multiply_value') == 0.001}
        cpu_fields = {k for k in profile['get'] if '.cpu.' in k}
        cpu_fields |= {f'component.node.cpu.{c}' for c in profile['table']['component.node.cpu']['columns']}
        assert cpu_fields and cpu_fields <= scaled

    def test_does_not_override_host_cpu_usage(self):
        import json
        for name in ('isilon_system', 'isilon_performance', 'isilon_protocols'):
            text = json.dumps(_official_profile(name))
            assert 'system.cpu.total.norm.pct' not in text, name

    def test_protocol_table_reads_node_protocol_perf_table(self):
        columns = _official_profile('isilon_protocols')['table']['storage.protocol']['columns']
        assert columns['name'] == '1.3.6.1.4.1.12124.2.2.10.1.1'
        assert all(oid.startswith('1.3.6.1.4.1.12124.2.2.10.1.') for oid in columns.values())


class TestSnmpTemplateHostMappings:

    def test_version_stays_1_8(self):
        assert _snmp_template()['_meta']['version'] == '1.8'

    @pytest.mark.parametrize('field, expected', [
        ('system.load.1', 'scaled_float'),
        ('system.cpu.cores', 'long'),
        ('system.load.cores', 'long'),
        ('system.memory.total', 'long'),
        ('system.memory.actual.free', 'long'),
        ('system.filesystem.total', 'long'),
        ('host.network.ingress.bytes', 'long'),
        ('metricset.period', 'long'),
    ])
    def test_field_types(self, field, expected):
        node = _mapping_at(_snmp_template()['template']['mappings']['properties'], field)
        assert node is not None, field
        assert node['type'] == expected

    def test_shared_fields_match_elastic_exactly(self):
        """Kibana flags a field when indices disagree on type, scaling, metric type, or unit."""
        elastic = _elastic_system_mappings()
        props = _snmp_template()['template']['mappings']['properties']
        shared = (set(_template_leaves(props)) | _fields_written_by_official_profiles()) & set(elastic)
        mismatches = {f: (_mapping_at(props, f), elastic[f]) for f in sorted(shared)
                      if _mapping_at(props, f) != elastic[f]}
        assert mismatches == {}

    def test_no_object_where_elastic_has_a_value(self):
        elastic = _elastic_system_mappings()
        ours = set(_template_leaves(_snmp_template()['template']['mappings']['properties']))
        ours |= _fields_written_by_official_profiles()
        clashes = sorted(
            (field, other)
            for field in ours for other in elastic
            if field.startswith(other + '.') or other.startswith(field + '.')
        )
        assert clashes == []

    def test_ai_authoring_material_writes_nothing_under_a_mapped_value(self):
        """AI-generated profiles copy these names; a sub-key under a mapped value rejects the document."""
        import json
        import re
        data = Path(settings.BASE_DIR) / 'SNMP' / 'data'
        leaves = set(_template_leaves(_snmp_template()['template']['mappings']['properties']))
        names = set()
        for path in (data / 'mib_reference').glob('*.json'):
            ref = json.loads(path.read_text(encoding='utf-8'))
            names.update(ref.get('get') or {})
            for table, spec in (ref.get('table') or {}).items():
                names.update(f'{table}.{col}' for col in (spec.get('columns') or {}))
        instructions = (data / 'authoring_instructions.md').read_text(encoding='utf-8')
        for line in instructions.splitlines():
            if 'Never write' not in line:
                names.update(re.findall(r'[`"]([a-z0-9_]+(?:\.[a-z0-9_]+)+)[`"]', line))
        clashes = sorted((name, leaf) for name in names for leaf in leaves if name.startswith(leaf + '.'))
        assert clashes == []

    def test_memory_total_is_a_leaf(self):
        node = _mapping_at(_snmp_template()['template']['mappings']['properties'], 'system.memory.total')
        assert 'properties' not in node

    def test_aliases_point_at_mapped_fields(self):
        props = _snmp_template()['template']['mappings']['properties']
        aliases = []

        def walk(node, prefix):
            for name, child in node.get('properties', {}).items():
                path = f'{prefix}{name}'
                if child.get('type') == 'alias':
                    aliases.append((path, child['path']))
                walk(child, path + '.')

        walk({'properties': props}, '')
        for alias, target in aliases:
            node = _mapping_at(props, target)
            assert node is not None and node.get('type') not in (None, 'alias'), alias
