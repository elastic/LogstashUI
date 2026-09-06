#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Tests for SNMP.snmp_grounding — all pure functions, no DB or network required.
"""

import json
import os
import tempfile
import pytest

from SNMP.snmp_grounding import (
    build_grounding,
    load_grounding,
    reduce_and_ground,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _write_mib(directory, filename, data):
    path = os.path.join(directory, filename)
    with open(path, 'w') as f:
        json.dump(data, f)
    return path


def _minimal_mib(obj_name, oid, nodetype='scalar', typ='Integer32', enum=None, units=None):
    """
    Return a minimal pysmi-style MIB dict for one object.
    build_grounding iterates the file dict directly as {obj_name: obj_body},
    so the file should contain {obj_name: {...}} at the top level.
    """
    syntax = {'type': typ}
    if enum:
        syntax['constraints'] = {'enumeration': enum}
    obj = {
        'oid': oid,
        'nodetype': nodetype,
        'syntax': syntax,
        'maxaccess': 'read-only',
    }
    if units:
        obj['units'] = units
    return {obj_name: obj}


# ===========================================================================
# build_grounding
# ===========================================================================

class TestBuildGrounding:

    def test_empty_directory_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as d:
            result = build_grounding(d)
        assert result == {}

    def test_scalar_object_included(self):
        with tempfile.TemporaryDirectory() as d:
            mib = _minimal_mib('sysDescr', '1.3.6.1.2.1.1.1', nodetype='scalar')
            _write_mib(d, 'RFC1213-MIB.json', mib)
            result = build_grounding(d)
        assert '1.3.6.1.2.1.1.1' in result
        entry = result['1.3.6.1.2.1.1.1']
        assert entry['name'] == 'sysDescr'
        assert entry['nodetype'] == 'scalar'

    def test_column_object_included(self):
        with tempfile.TemporaryDirectory() as d:
            mib = _minimal_mib('ifDescr', '1.3.6.1.2.1.2.2.1.2', nodetype='column')
            _write_mib(d, 'IF-MIB.json', mib)
            result = build_grounding(d)
        assert '1.3.6.1.2.1.2.2.1.2' in result

    def test_enum_is_inverted(self):
        """pysmi stores enums as {name: int}; build_grounding inverts to {int: name}."""
        with tempfile.TemporaryDirectory() as d:
            mib = _minimal_mib(
                'ifOperStatus', '1.3.6.1.2.1.2.2.1.8',
                nodetype='scalar',
                enum={'up': 1, 'down': 2},
            )
            _write_mib(d, 'IF-MIB.json', mib)
            result = build_grounding(d)
        assert result['1.3.6.1.2.1.2.2.1.8']['enum'] == {1: 'up', 2: 'down'}

    def test_invalid_json_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            bad_path = os.path.join(d, 'bad.json')
            with open(bad_path, 'w') as f:
                f.write('this is not json {{{')
            result = build_grounding(d)
        assert result == {}

    def test_non_dict_json_file_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            _write_mib(d, 'list.json', [1, 2, 3])
            result = build_grounding(d)
        assert result == {}

    def test_non_scalar_column_nodetype_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            mib = {'someRow': {'oid': '1.2.3', 'nodetype': 'row', 'syntax': {}}}
            _write_mib(d, 'TEST-MIB.json', mib)
            result = build_grounding(d)
        assert '1.2.3' not in result

    def test_units_included_when_defined(self):
        with tempfile.TemporaryDirectory() as d:
            mib = _minimal_mib('sysUpTime', '1.3.6.1.2.1.1.3',
                                nodetype='scalar', typ='TimeTicks',
                                units='hundredths of a second')
            _write_mib(d, 'MIB.json', mib)
            result = build_grounding(d)
        assert result['1.3.6.1.2.1.1.3']['units'] == 'hundredths of a second'

    def test_multiple_files_merged(self):
        with tempfile.TemporaryDirectory() as d:
            mib1 = _minimal_mib('sysDescr', '1.3.6.1.2.1.1.1', nodetype='scalar')
            mib2 = _minimal_mib('ifDescr', '1.3.6.1.2.1.2.2.1.2', nodetype='column')
            _write_mib(d, 'MIB1.json', mib1)
            _write_mib(d, 'MIB2.json', mib2)
            result = build_grounding(d)
        assert '1.3.6.1.2.1.1.1' in result
        assert '1.3.6.1.2.1.2.2.1.2' in result


# ===========================================================================
# load_grounding
# ===========================================================================

class TestLoadGrounding:

    def test_valid_json_file_loaded(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'1.2.3': {'name': 'sysDescr'}}, f)
            path = f.name
        try:
            result = load_grounding(path)
            assert '1.2.3' in result
        finally:
            os.unlink(path)

    def test_missing_file_returns_empty_dict(self):
        result = load_grounding('/nonexistent/path/grounding.json')
        assert result == {}

    def test_invalid_json_returns_empty_dict(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not valid json !!!')
            path = f.name
        try:
            result = load_grounding(path)
            assert result == {}
        finally:
            os.unlink(path)


# ===========================================================================
# reduce_and_ground
# ===========================================================================

class TestReduceAndGround:
    """
    reduce_and_ground is pure; we supply a synthetic grounding dict so tests
    don't depend on the compiled grounding.json file.
    """

    GROUNDING = {
        '1.3.6.1.2.1.1.1': {
            'name': 'sysDescr', 'mib': 'RFC1213-MIB',
            'type': 'OctetString', 'enum': None,
            'nodetype': 'scalar', 'access': 'read-only',
        },
        '1.3.6.1.2.1.2.2.1.2': {
            'name': 'ifDescr', 'mib': 'IF-MIB',
            'type': 'DisplayString', 'enum': None,
            'nodetype': 'column', 'access': 'read-only',
        },
        '1.3.6.1.2.1.2.2.1.8': {
            'name': 'ifOperStatus', 'mib': 'IF-MIB',
            'type': 'Integer32',
            'enum': {1: 'up', 2: 'down'},
            'nodetype': 'column', 'access': 'read-only',
        },
    }

    def test_empty_walk_returns_empty_results(self):
        grounded, ungrounded = reduce_and_ground('', self.GROUNDING)
        assert grounded == []
        assert ungrounded == []

    def test_known_scalar_oid_grounded(self):
        walk = '1.3.6.1.2.1.1.1.0 = Linux router'
        grounded, ungrounded = reduce_and_ground(walk, self.GROUNDING)
        assert len(grounded) == 1
        assert grounded[0]['name'] == 'sysDescr'

    def test_known_table_oid_with_instance_grounded(self):
        # ifDescr.1 — the '.1' is the instance arc (row index)
        walk = '1.3.6.1.2.1.2.2.1.2.1 = GigabitEthernet0/0'
        grounded, ungrounded = reduce_and_ground(walk, self.GROUNDING)
        names = [r['name'] for r in grounded]
        assert 'ifDescr' in names

    def test_multiple_rows_of_same_column_counted(self):
        walk = (
            '1.3.6.1.2.1.2.2.1.2.1 = GigabitEthernet0/0\n'
            '1.3.6.1.2.1.2.2.1.2.2 = GigabitEthernet0/1\n'
        )
        grounded, _ = reduce_and_ground(walk, self.GROUNDING)
        ifdescr = next(r for r in grounded if r['name'] == 'ifDescr')
        assert ifdescr['instances'] == 2

    def test_unknown_oid_goes_to_ungrounded(self):
        walk = '9.9.9.9.9.9 = SomeValue'
        _, ungrounded = reduce_and_ground(walk, self.GROUNDING)
        assert len(ungrounded) > 0

    def test_grounded_sorted_by_oid_numerically(self):
        walk = (
            '1.3.6.1.2.1.2.2.1.8.1 = 1\n'
            '1.3.6.1.2.1.1.1.0 = router\n'
        )
        grounded, _ = reduce_and_ground(walk, self.GROUNDING)
        oids = [r['oid'] for r in grounded]
        assert oids == sorted(oids, key=lambda o: [int(x) for x in o.split('.')])

    def test_sample_value_truncated_to_50_chars(self):
        long_value = 'X' * 200
        walk = f'1.3.6.1.2.1.1.1.0 = {long_value}'
        grounded, _ = reduce_and_ground(walk, self.GROUNDING)
        assert len(grounded[0]['sample']) <= 50

    def test_malformed_lines_skipped(self):
        walk = 'this is not a valid walk line\n1.3.6.1.2.1.1.1.0 = Linux'
        grounded, _ = reduce_and_ground(walk, self.GROUNDING)
        assert len(grounded) == 1

    def test_enum_propagated_to_grounded_entry(self):
        walk = '1.3.6.1.2.1.2.2.1.8.1 = 1'
        grounded, _ = reduce_and_ground(walk, self.GROUNDING)
        entry = next(r for r in grounded if r['name'] == 'ifOperStatus')
        assert entry['enum'] == {1: 'up', 2: 'down'}

    def test_uses_module_level_grounding_when_none_passed(self):
        # Should not raise even when the module-level GROUNDING may be empty.
        walk = '1.3.6.1.2.1.1.1.0 = test'
        grounded, ungrounded = reduce_and_ground(walk)  # no grounding arg
        # Result depends on the compiled file; just verify it doesn't crash
        assert isinstance(grounded, list)
        assert isinstance(ungrounded, list)

    def test_tab_separated_walk_format(self):
        walk = '1.3.6.1.2.1.1.1.0\tLinux router'
        grounded, _ = reduce_and_ground(walk, self.GROUNDING)
        assert len(grounded) == 1
        assert grounded[0]['name'] == 'sysDescr'
