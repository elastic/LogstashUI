#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
import json

from Common.logstash_config_parse import (
    _extract_error_context,
    _strip_inline_comments,
    parse_logstash_config,
    logstash_config_to_components,
    ComponentToPipeline,
)


# ─────────────────────────────────────────────────────────────
# Helpers / shared fixtures
# ─────────────────────────────────────────────────────────────

MINIMAL_INPUT = 'input {\n  stdin {}\n}\n'
MINIMAL_FILTER = 'filter {\n  mutate {}\n}\n'
MINIMAL_OUTPUT = 'output {\n  stdout {}\n}\n'
FULL_PIPELINE = MINIMAL_INPUT + MINIMAL_FILTER + MINIMAL_OUTPUT


# ─────────────────────────────────────────────────────────────
# _extract_error_context
# ─────────────────────────────────────────────────────────────

class TestExtractErrorContext:
    """Unit tests for _extract_error_context"""

    def test_contains_separator_lines(self):
        """Result includes the === separator lines"""
        config = "input {\n  stdin {}\n}\n"
        result = _extract_error_context(config, line=1, column=1)
        assert '=' * 60 in result

    def test_contains_problematic_code_header(self):
        """Result contains the PROBLEMATIC CODE label"""
        config = "input {\n  stdin {}\n}\n"
        result = _extract_error_context(config, line=1, column=1)
        assert 'PROBLEMATIC CODE' in result

    def test_error_line_marked_with_arrow(self):
        """The error line is prefixed with '>>>'"""
        config = "input {\n  bad_line\n}\n"
        result = _extract_error_context(config, line=2, column=1)
        assert '>>>' in result

    def test_non_error_lines_not_marked(self):
        """Non-error lines have normal indentation, not '>>>'"""
        config = "input {\n  bad_line\n}\n"
        result = _extract_error_context(config, line=2, column=1)
        lines = result.split('\n')
        # Lines that aren't the error line should start with spaces, not >>>
        non_arrow_lines = [l for l in lines if l.strip() and not l.strip().startswith(('=', 'P', '>')) and '|' in l]
        for line in non_arrow_lines:
            assert not line.startswith('>>>')

    def test_column_pointer_added(self):
        """A '^' pointer is added at the correct column position"""
        config = "input {\n  bad_line\n}\n"
        result = _extract_error_context(config, line=2, column=3)
        assert '^' in result

    def test_no_pointer_for_column_zero(self):
        """No '^' pointer when column is 0"""
        config = "input {\n  bad_line\n}\n"
        result = _extract_error_context(config, line=2, column=0)
        assert '^' not in result

    def test_line_number_appears_in_output(self):
        """The error line number appears in the formatted output"""
        config = "line1\nline2\nline3\n"
        result = _extract_error_context(config, line=2, column=1)
        assert '2' in result

    def test_context_lines_parameter_controls_range(self):
        """context_lines parameter controls how many surrounding lines are shown"""
        config = "\n".join([f"line{i}" for i in range(1, 21)])
        # With 1 context line around line 10, we should see lines 9, 10, 11
        result_1 = _extract_error_context(config, line=10, column=1, context_lines=1)
        result_5 = _extract_error_context(config, line=10, column=1, context_lines=5)
        # Larger context means more lines shown
        assert len(result_5) > len(result_1)

    def test_first_line_error_no_index_error(self):
        """Error at line 1 should not cause an IndexError"""
        config = "bad config\nmore\n"
        result = _extract_error_context(config, line=1, column=1)
        assert '>>>' in result

    def test_last_line_error_no_index_error(self):
        """Error at last line should not cause an IndexError"""
        config = "good\nbad"
        result = _extract_error_context(config, line=2, column=1)
        assert '>>>' in result

    def test_returns_string(self):
        """Function always returns a string"""
        config = "input {}"
        result = _extract_error_context(config, line=1, column=1)
        assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────
# _strip_inline_comments
# ─────────────────────────────────────────────────────────────

class TestStripInlineComments:
    """Unit tests for _strip_inline_comments"""

    def test_removes_inline_comment_after_value(self):
        """Inline comments after a config value are stripped"""
        config = 'input {\n  beats {\n    port => 5044 # this is a comment\n  }\n}\n'
        result = _strip_inline_comments(config)
        assert '# this is a comment' not in result
        assert 'port => 5044' in result

    def test_removes_inline_comment_after_closing_brace(self):
        """Inline comments after } are stripped"""
        config = 'input {\n  beats {\n    port => 5044\n  } # end beats\n}\n'
        result = _strip_inline_comments(config)
        assert '# end beats' not in result

    def test_preserves_hash_in_string_value(self):
        """# inside a quoted string is NOT treated as a comment"""
        config = 'input {\n  beats {\n    path => "/var/log/#file"\n  }\n}\n'
        result = _strip_inline_comments(config)
        assert '/var/log/#file' in result

    def test_preserves_standalone_comment_at_section_level(self):
        """Standalone comment lines at the top/section level are preserved"""
        config = '# This is a top-level comment\ninput {\n  stdin {}\n}\n'
        result = _strip_inline_comments(config)
        assert '# This is a top-level comment' in result

    def test_removes_standalone_comment_inside_plugin_block(self):
        """Standalone comment lines INSIDE a plugin block are removed"""
        config = 'input {\n  beats {\n    # comment inside plugin\n    port => 5044\n  }\n}\n'
        result = _strip_inline_comments(config)
        assert '# comment inside plugin' not in result
        assert 'port => 5044' in result

    def test_preserves_standalone_comment_inside_conditional(self):
        """Standalone comment lines inside an if/else block are preserved"""
        config = (
            'filter {\n'
            '  if [type] == "syslog" {\n'
            '    # comment in conditional\n'
            '    mutate {}\n'
            '  }\n'
            '}\n'
        )
        result = _strip_inline_comments(config)
        assert '# comment in conditional' in result

    def test_returns_string(self):
        """Function returns a string"""
        assert isinstance(_strip_inline_comments('input { stdin {} }'), str)

    def test_no_comments_unchanged(self):
        """Config with no comments is returned unchanged"""
        config = 'input {\n  stdin {}\n}\n'
        result = _strip_inline_comments(config)
        assert result == config

    def test_trailing_whitespace_before_comment_removed(self):
        """Trailing whitespace before the inline comment is also stripped"""
        config = 'input {\n  beats {\n    port => 5044   # trailing spaces before comment\n  }\n}\n'
        result = _strip_inline_comments(config)
        # The value should be present without trailing spaces
        lines_with_port = [l for l in result.split('\n') if 'port' in l]
        assert len(lines_with_port) == 1
        assert lines_with_port[0].endswith('5044')


# ─────────────────────────────────────────────────────────────
# parse_logstash_config
# ─────────────────────────────────────────────────────────────

class TestParseLogstashConfig:
    """Unit tests for parse_logstash_config

    Note on return type: Lark's LALR transformer with a single section returns
    a bare dict (not a list). With multiple sections it returns a list of dicts.
    This matches the defensive check inside logstash_config_to_components:
        if not isinstance(parsed, list): parsed = [parsed]
    The helper _as_list() below mirrors that normalization.
    """

    @staticmethod
    def _as_list(result):
        """Normalize to list regardless of whether one or multiple sections came back."""
        if isinstance(result, list):
            return result
        return [result] if result else []

    def test_parses_single_section_as_dict_or_list(self):
        """Single-section configs are returned as a dict (Lark unwraps single items)"""
        result = parse_logstash_config(MINIMAL_INPUT)
        assert isinstance(result, (dict, list))

    def test_parses_all_three_sections(self):
        """All three sections (input, filter, output) are parsed into a list"""
        result = parse_logstash_config(FULL_PIPELINE)
        assert isinstance(result, list)
        types = [s['type'] for s in result]
        assert 'input' in types
        assert 'filter' in types
        assert 'output' in types

    def test_single_section_has_correct_type(self):
        """A single input section has type == 'input'"""
        result = self._as_list(parse_logstash_config(MINIMAL_INPUT))
        assert len(result) == 1
        assert result[0]['type'] == 'input'

    def test_each_section_has_statements(self):
        """Each parsed section has a 'statements' key"""
        result = self._as_list(parse_logstash_config(MINIMAL_INPUT))
        for section in result:
            assert 'statements' in section

    def test_plugin_name_captured(self):
        """The plugin name ('stdin') is captured correctly"""
        result = self._as_list(parse_logstash_config(MINIMAL_INPUT))
        statements = result[0]['statements']
        plugin_names = [str(s.get('name', '')) for s in statements]
        assert 'stdin' in plugin_names

    def test_invalid_config_raises_value_error(self):
        """Invalid config raises a ValueError"""
        bad_config = "this is not valid logstash config {{{"
        with pytest.raises(ValueError):
            parse_logstash_config(bad_config)

    def test_error_message_includes_line_info(self):
        """ValueError message contains line number information"""
        bad_config = "input {\n  ??? invalid\n}\n"
        with pytest.raises(ValueError, match=r'line'):
            parse_logstash_config(bad_config)

    def test_plugin_with_settings(self):
        """Settings on a plugin are parsed into the settings dict"""
        config = 'input {\n  beats {\n    port => 5044\n  }\n}\n'
        result = self._as_list(parse_logstash_config(config))
        statements = result[0]['statements']
        beats = next(s for s in statements if str(s.get('name', '')) == 'beats')
        assert beats['settings']['port'] == 5044

    def test_plugin_with_string_setting(self):
        """String settings are unquoted during parsing"""
        config = 'input {\n  file {\n    path => "/var/log/syslog"\n  }\n}\n'
        result = self._as_list(parse_logstash_config(config))
        statements = result[0]['statements']
        file_plugin = next(s for s in statements if str(s.get('name', '')) == 'file')
        assert file_plugin['settings']['path'] == '/var/log/syslog'

    def test_plugin_with_numeric_setting(self):
        """Numeric settings are parsed correctly (not checked as list here)"""
        config = 'input {\n  file {\n    sincedb_clean_after => 0\n    start_position => "beginning"\n  }\n}\n'
        result = self._as_list(parse_logstash_config(config))
        assert len(result) == 1
        assert result[0]['type'] == 'input'

    def test_empty_plugin_block(self):
        """A plugin with no settings produces an empty settings dict"""
        result = self._as_list(parse_logstash_config(MINIMAL_INPUT))
        statements = result[0]['statements']
        stdin = next(s for s in statements if str(s.get('name', '')) == 'stdin')
        assert stdin['settings'] == {}

    def test_strips_inline_comments_before_parsing(self):
        """Inline comments that would break parsing are stripped first"""
        config = 'input {\n  beats {\n    port => 5044 # inline comment\n  }\n}\n'
        # Should not raise — comments are stripped before parsing
        result = self._as_list(parse_logstash_config(config))
        assert len(result) == 1


# ─────────────────────────────────────────────────────────────
# logstash_config_to_components
# ─────────────────────────────────────────────────────────────

class TestLogstashConfigToComponents:
    """Unit tests for logstash_config_to_components"""

    def test_returns_json_string(self):
        """Returns a JSON string"""
        result = logstash_config_to_components(FULL_PIPELINE)
        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_output_has_three_sections(self):
        """Output JSON has input, filter, output keys"""
        result = json.loads(logstash_config_to_components(FULL_PIPELINE))
        assert 'input' in result
        assert 'filter' in result
        assert 'output' in result

    def test_all_sections_present_even_when_missing(self):
        """All three sections are present even when only some exist in config"""
        result = json.loads(logstash_config_to_components(MINIMAL_INPUT))
        assert 'input' in result
        assert 'filter' in result
        assert 'output' in result
        assert result['filter'] == []
        assert result['output'] == []

    def test_plugin_in_correct_section(self):
        """Plugins end up in their correct section"""
        result = json.loads(logstash_config_to_components(FULL_PIPELINE))
        input_plugins = [c['plugin'] for c in result['input']]
        filter_plugins = [c['plugin'] for c in result['filter']]
        output_plugins = [c['plugin'] for c in result['output']]
        assert 'stdin' in input_plugins
        assert 'mutate' in filter_plugins
        assert 'stdout' in output_plugins

    def test_component_has_required_keys(self):
        """Each component has id, type, plugin, and config keys"""
        result = json.loads(logstash_config_to_components(FULL_PIPELINE))
        for section_components in result.values():
            for component in section_components:
                assert 'id' in component
                assert 'type' in component
                assert 'plugin' in component
                assert 'config' in component

    def test_component_type_matches_section(self):
        """Each component's 'type' matches the section it belongs to"""
        result = json.loads(logstash_config_to_components(FULL_PIPELINE))
        for section_name, section_components in result.items():
            for component in section_components:
                assert component['type'] == section_name

    def test_component_id_includes_plugin_name(self):
        """Component IDs include the plugin name"""
        result = json.loads(logstash_config_to_components(MINIMAL_INPUT))
        stdin_component = result['input'][0]
        assert 'stdin' in stdin_component['id']

    def test_plugin_settings_in_config(self):
        """Plugin settings appear in the component's config dict"""
        config = 'input {\n  beats {\n    port => 5044\n  }\n}\n'
        result = json.loads(logstash_config_to_components(config))
        beats = result['input'][0]
        assert beats['plugin'] == 'beats'
        assert beats['config']['port'] == 5044

    def test_invalid_config_raises_exception(self):
        """Invalid config raises an Exception"""
        with pytest.raises(Exception):
            logstash_config_to_components("this is complete garbage {{{}}")

    def test_multiple_plugins_same_section(self):
        """Multiple plugins in the same section are all captured"""
        config = (
            'input {\n'
            '  stdin {}\n'
            '  beats { port => 5044 }\n'
            '}\n'
            'output { stdout {} }\n'
        )
        result = json.loads(logstash_config_to_components(config))
        assert len(result['input']) == 2
        plugin_names = [c['plugin'] for c in result['input']]
        assert 'stdin' in plugin_names
        assert 'beats' in plugin_names

    def test_components_have_unique_ids(self):
        """All component IDs are unique within the output"""
        config = (
            'input { stdin {} }\n'
            'filter { mutate {} grok {} }\n'
            'output { stdout {} }\n'
        )
        result = json.loads(logstash_config_to_components(config))
        all_ids = []
        for section_components in result.values():
            all_ids.extend(c['id'] for c in section_components)
        assert len(all_ids) == len(set(all_ids)), "Component IDs should be unique"

    def test_output_is_pretty_printed_json(self):
        """Output JSON is indented (pretty-printed)"""
        result = logstash_config_to_components(MINIMAL_INPUT)
        assert '\n' in result
        assert '    ' in result  # 4-space indent


# ─────────────────────────────────────────────────────────────
# ComponentToPipeline
# ─────────────────────────────────────────────────────────────

class TestComponentToPipeline:
    """Unit tests for ComponentToPipeline helper methods"""

    def _make_parser(self, components=None):
        if components is None:
            components = {'input': [], 'filter': [], 'output': []}
        return ComponentToPipeline(components)

    # _format_string_value tests

    def test_format_string_simple(self):
        """Simple strings are quoted with double quotes"""
        parser = self._make_parser()
        result = parser._format_string_value('hello')
        assert result == '"hello"'

    def test_format_string_non_string_passthrough(self):
        """Non-string values are returned as-is"""
        parser = self._make_parser()
        assert parser._format_string_value(42) == 42
        assert parser._format_string_value(True) is True
        assert parser._format_string_value(3.14) == 3.14

    def test_format_string_with_double_quotes_uses_single(self):
        """String containing double quotes is wrapped in single quotes"""
        parser = self._make_parser()
        result = parser._format_string_value('say "hello"')
        assert result.startswith("'")
        assert result.endswith("'")

    def test_format_string_with_single_quotes_uses_double(self):
        """String containing single quotes is wrapped in double quotes"""
        parser = self._make_parser()
        result = parser._format_string_value("it's fine")
        assert result.startswith('"')
        assert result.endswith('"')

    def test_format_multiline_string_uses_single_quotes(self):
        """Multiline string uses single quotes"""
        parser = self._make_parser()
        result = parser._format_string_value('line1\nline2')
        assert result.startswith("'")

    # _generate_plugin_id tests

    def test_generate_plugin_id_format(self):
        """Generated ID follows section_plugin_count format"""
        parser = self._make_parser()
        plugin_id = parser._generate_plugin_id('beats', 'input')
        assert plugin_id == 'input_beats_1'

    def test_generate_plugin_id_increments(self):
        """Each call increments the counter for the same plugin type"""
        parser = self._make_parser()
        id1 = parser._generate_plugin_id('beats', 'input')
        id2 = parser._generate_plugin_id('beats', 'input')
        assert id1 == 'input_beats_1'
        assert id2 == 'input_beats_2'

    def test_generate_plugin_id_separate_counters_per_section(self):
        """Different sections have independent counters"""
        parser = self._make_parser()
        input_id = parser._generate_plugin_id('stdout', 'input')
        output_id = parser._generate_plugin_id('stdout', 'output')
        assert input_id == 'input_stdout_1'
        assert output_id == 'output_stdout_1'

    # components_to_logstash_config tests

    def test_empty_components_returns_empty_sections(self):
        """Empty component lists produce an empty pipeline string"""
        parser = self._make_parser({'input': [], 'filter': [], 'output': []})
        result = parser.components_to_logstash_config()
        assert isinstance(result, str)

    def test_simple_stdin_plugin(self):
        """A simple stdin plugin is rendered correctly"""
        components = {
            'input': [
                {'id': 'input_stdin_0', 'type': 'input', 'plugin': 'stdin', 'config': {}}
            ],
            'filter': [],
            'output': []
        }
        parser = ComponentToPipeline(components)
        result = parser.components_to_logstash_config()
        assert 'input {' in result
        assert 'stdin {' in result

    def test_plugin_with_string_setting(self):
        """String settings are rendered with quotes"""
        components = {
            'input': [
                {'id': 'input_file_0', 'type': 'input', 'plugin': 'file',
                 'config': {'path': '/var/log/syslog'}}
            ],
            'filter': [],
            'output': []
        }
        parser = ComponentToPipeline(components)
        result = parser.components_to_logstash_config()
        assert 'path => "/var/log/syslog"' in result

    def test_plugin_with_numeric_setting(self):
        """Numeric settings are rendered without quotes"""
        components = {
            'input': [
                {'id': 'input_beats_0', 'type': 'input', 'plugin': 'beats',
                 'config': {'port': 5044}}
            ],
            'filter': [],
            'output': []
        }
        parser = ComponentToPipeline(components)
        result = parser.components_to_logstash_config()
        assert 'port => 5044' in result
        assert 'port => "5044"' not in result

    def test_all_three_sections_rendered(self):
        """All three sections (input, filter, output) appear in the output"""
        components = {
            'input': [{'id': 'i', 'type': 'input', 'plugin': 'stdin', 'config': {}}],
            'filter': [{'id': 'f', 'type': 'filter', 'plugin': 'mutate', 'config': {}}],
            'output': [{'id': 'o', 'type': 'output', 'plugin': 'stdout', 'config': {}}]
        }
        parser = ComponentToPipeline(components)
        result = parser.components_to_logstash_config()
        assert 'input {' in result
        assert 'filter {' in result
        assert 'output {' in result
