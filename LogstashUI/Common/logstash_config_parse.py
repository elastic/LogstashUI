from lark import Lark, Transformer, UnexpectedToken, UnexpectedCharacters
from typing import Dict, List, Any
import json

import logging
logger = logging.getLogger(__name__)

################################ Logstash config to component JSON ################################
LOGSTASH_GRAMMAR = r"""
?start: [comment+] section+

section: section_type "{" [statement+] "}"

statement: plugin | conditional | comment

comment: COMMENT

conditional: "if" condition "{" [statement+] "}" (else_if_condition | else_condition)*
condition: CMP_OPERATORS
else_if_condition: "else" "if" condition "{" [statement+] "}"
else_condition: "else" "{" [statement+] "}"

CMP_OPERATORS: /(?:[^\n{"']|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')+/  // Matches anything except newline and unquoted {, handles quoted strings
section_type: "input" -> input_section
            | "filter" -> filter_section
            | "output" -> output_section


// Define plugin with flexible parameter formatting
plugin: CNAME "{" [pair (WS | ";")*]* "}"


pair: "codec" "=>" CNAME "{" codec_config "}"  -> codec_pair_with_config
    | "codec" "=>" (CNAME | MULTILINE_STRING | ESCAPED_STRING)     -> codec_pair_simple
    | (CNAME | ESCAPED_STRING) "=>" (UNQUOTED_STRING | CNAME | value)  -> regular_pair

codec_config: [codec_setting (","? codec_setting)*]
codec_setting: (CNAME | ESCAPED_STRING) "=>" (UNQUOTED_STRING | CNAME | value)

?value: multiline_string
      | string
      | number
      | array
      | hash
      | env_var
      | plugin

multiline_string: MULTILINE_STRING
string: ESCAPED_STRING
number: SIGNED_NUMBER
array: "[" [value ("," value)*] "]"
hash: "{" [pair (","? pair)*] "}"
env_var: "${" CNAME "}"

// Multi-line string: matches strings that can span multiple lines
// Handles both single and double quotes with escaped quotes inside
MULTILINE_STRING.3: /"([^"\\]|\\.|\n)*"/s | /'([^'\\]|\\.|\n)*'/s

%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER
%import common.CNAME
%import common.WS
%import common.NEWLINE

UNQUOTED_STRING.2: /[a-zA-Z_][a-zA-Z0-9_-]*/
COMMENT: /#[^\n]*/
%ignore WS
"""


class LogstashTransformer(Transformer):
    def _unescape_string(self, s):
        """Unescape special characters in parsed strings."""
        # Process escape sequences in the correct order
        # We need to handle \\\\ -> \\ first, then other escapes
        result = []
        i = 0
        while i < len(s):
            if i < len(s) - 1 and s[i] == '\\':
                next_char = s[i + 1]
                if next_char == 'n':
                    result.append('\n')
                    i += 2
                elif next_char == 't':
                    result.append('\t')
                    i += 2
                elif next_char == 'r':
                    result.append('\r')
                    i += 2
                elif next_char == '"':
                    result.append('"')
                    i += 2
                elif next_char == "'":
                    result.append("'")
                    i += 2
                elif next_char == '\\':
                    result.append('\\')
                    i += 2
                else:
                    # Unknown escape sequence, keep as-is
                    result.append(s[i])
                    i += 1
            else:
                result.append(s[i])
                i += 1
        return ''.join(result)
    
    def multiline_string(self, s):
        # Remove quotes and unescape the content
        raw_value = self._unescape_string(s[0][1:-1])
        
        # For multi-line strings, strip file indentation (tabs) from each line after the first
        # When ComponentToPipeline writes single-quoted strings across multiple lines,
        # each line picks up the file's indentation context (tabs from the f-string).
        # We need to remove these file-context tabs while preserving intentional indentation.
        lines = raw_value.split('\n')
        if len(lines) > 1:
            # Find the common leading tabs on lines after the first (file indentation)
            # Count leading tabs on the second line (first line after opening quote)
            if len(lines) > 1 and lines[1]:
                # Count leading tabs (file indentation)
                file_indent_tabs = len(lines[1]) - len(lines[1].lstrip('\t'))
                
                # Remove file indentation tabs from all lines after the first
                normalized_lines = [lines[0]]
                for line in lines[1:]:
                    # Remove the file indentation tabs, but keep any additional indentation
                    if line.startswith('\t' * file_indent_tabs):
                        normalized_lines.append(line[file_indent_tabs:])
                    else:
                        # Line doesn't have expected file indentation, keep as-is
                        normalized_lines.append(line)
                return '\n'.join(normalized_lines)
        
        return raw_value
    
    def string(self, s):
        # Remove quotes and unescape the content
        return self._unescape_string(s[0][1:-1])

    def condition(self, items):
        return items[0].strip()

    def comment(self, items):
        # Extract the comment text (remove the # prefix and any leading/trailing whitespace)
        comment_text = str(items[0]).lstrip('#').strip()
        return {"type": "comment", "text": comment_text}

    def statement(self, items):
        return items[0]

    def conditional(self, items):
        # First item is the if condition, rest are if_body statements and else clauses
        result = {
            'type': 'conditional',
            'if_condition': items[0],
            'if_body': [],
            'else_ifs': [],
            'else_body': None
        }
        
        # Collect if_body statements and else clauses
        i = 1
        # Collect all statements until we hit an else_if or else
        while i < len(items):
            item = items[i]
            if isinstance(item, dict) and item.get('type') in ['else_if_condition', 'else_condition']:
                break
            result['if_body'].append(item)
            i += 1
        
        # Process remaining items (else ifs and else)
        while i < len(items):
            item = items[i]
            if isinstance(item, dict):
                if item.get('type') == 'else_if_condition':
                    result['else_ifs'].append({
                        'condition': item['condition'],
                        'body': item['body']
                    })
                elif item.get('type') == 'else_condition':
                    result['else_body'] = item['body']
            i += 1
            
        return result

    def else_if_condition(self, items):
        # First item is condition, rest are body statements
        return {
            'type': 'else_if_condition',
            'condition': items[0],
            'body': items[1:] if len(items) > 1 else []
        }

    def else_condition(self, items):
        # All items are body statements
        return {
            'type': 'else_condition',
            'body': items if items else []
        }

    def number(self, n):
        return float(n[0]) if '.' in n[0] else int(n[0])

    def env_var(self, v):
        return {"type": "env_var", "value": v[0]}

    def array(self, items):
        # Filter out None values that may come from parsing
        return [item for item in items if item is not None]

    def hash(self, pairs):
        return dict(pairs)

    def codec_setting(self, items):
        """Transform codec settings into tuples"""
        if len(items) >= 2:
            # Handle ESCAPED_STRING tokens for keys - strip quotes
            key = items[0]
            if hasattr(key, 'type') and key.type == 'ESCAPED_STRING':
                key = str(key)[1:-1]
            return (key, items[1])
        elif len(items) == 1:
            key = items[0]
            if hasattr(key, 'type') and key.type == 'ESCAPED_STRING':
                key = str(key)[1:-1]
            return (key, None)
        else:
            return (None, None)
    
    def codec_config(self, items):
        """Transform codec config into list of tuples"""
        return [item for item in items if item is not None]
    
    def codec_pair_with_config(self, items):
        """Handle codec => name { config } - return as nested dict"""
        codec_name = str(items[0])
        # items[1] is the codec_config (list of tuples)
        config_list = items[1] if len(items) > 1 and isinstance(items[1], list) else []
        
        # Convert list of tuples to dict
        codec_config = {}
        for key, value in config_list:
            codec_config[key] = value
        
        # Return as nested dict: {"codec": {"codec_name": {...}}}
        return ("codec", {codec_name: codec_config})
    def codec_pair_simple(self, items):
        """Handle codec => simple_value - return as nested dict with empty config"""
        codec_name = str(items[0])
        return ("codec", {codec_name: {}})
    
    def regular_pair(self, items):
        """Handle regular key => value pairs"""
        if len(items) >= 2:
            # Handle ESCAPED_STRING tokens for keys - strip quotes
            key = items[0]
            if hasattr(key, 'type') and key.type == 'ESCAPED_STRING':
                key = str(key)[1:-1]  # Remove surrounding quotes
            return (key, items[1])
        elif len(items) == 1:
            # Single item - might be a key with no value
            key = items[0]
            if hasattr(key, 'type') and key.type == 'ESCAPED_STRING':
                key = str(key)[1:-1]
            return (key, None)
        else:
            return (None, None)
    
    def pair(self, items):
        """Fallback for pair - should be handled by codec_pair or regular_pair"""
        if len(items) >= 2:
            key = items[0]
            if hasattr(key, 'type') and key.type == 'ESCAPED_STRING':
                key = str(key)[1:-1]
            return (key, items[1])
        elif len(items) == 1:
            key = items[0]
            if hasattr(key, 'type') and key.type == 'ESCAPED_STRING':
                key = str(key)[1:-1]
            return (key, None)
        else:
            return (None, None)

    def plugin(self, items):
        name = items[0]
        settings = {}
        # If there are items after the name, they are the pairs
        if len(items) > 1 and items[1]:
            # Flatten the list of pairs (handling both direct pairs and nested lists)
            pairs = []
            for item in items[1:]:
                if isinstance(item, list):
                    pairs.extend([p for p in item if p is not None])
                elif item is not None:
                    pairs.append(item)

            # Add pairs to settings with merging logic for duplicate keys
            for pair in pairs:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    k, v = pair
                    
                    # If key already exists, merge the values
                    if k in settings:
                        existing = settings[k]
                        
                        # Both are dicts: merge them
                        if isinstance(existing, dict) and isinstance(v, dict):
                            settings[k] = {**existing, **v}
                        
                        # Both are lists: concatenate them
                        elif isinstance(existing, list) and isinstance(v, list):
                            settings[k] = existing + v
                        
                        # One is a list: append the other to it
                        elif isinstance(existing, list):
                            settings[k] = existing + [v]
                        elif isinstance(v, list):
                            settings[k] = [existing] + v
                        
                        # Both are scalars: convert to list
                        else:
                            settings[k] = [existing, v]
                    else:
                        settings[k] = v
        return {"type": "plugin", "name": name, "settings": settings}

    def section(self, items):
        section_type = items[0]
        statements = items[1:]
        return {"type": section_type, "statements": statements}

    def input_section(self, _):
        return "input"

    def filter_section(self, _):
        return "filter"

    def output_section(self, _):
        return "output"

    def start(self, items):
        return list(items)

    def _format_plugin(self, plugin_data, section_type, component_count):
        """Format a plugin with proper ID and type."""
        if not isinstance(plugin_data, dict) or 'name' not in plugin_data:
            return plugin_data, component_count

        plugin = {
            'id': f"{section_type}_{plugin_data['name']}_{component_count}",
            'type': section_type,
            'plugin': plugin_data['name'],
            'config': plugin_data.get('settings', {})
        }
        return plugin, component_count + 1

    def _process_plugins(self, plugins, section_type, component_count, target_list=None):
        """Process a list of plugins, adding proper IDs and types."""
        result = []
        if not plugins:
            return result, component_count

        if not isinstance(plugins, list):
            plugins = [plugins]

        for plugin in plugins:
            if not plugin:
                continue

            if isinstance(plugin, dict):
                if plugin.get('type') == 'comment':
                    # It's a comment - convert to comment plugin format
                    comment_plugin = {
                        'id': f"{section_type}_comment_{component_count}",
                        'type': section_type,
                        'plugin': 'comment',
                        'config': {
                            'text': plugin.get('text', '')
                        }
                    }
                    result.append(comment_plugin)
                    component_count += 1
                elif 'name' in plugin:  # It's a regular plugin
                    formatted_plugin, component_count = self._format_plugin(plugin, section_type, component_count)
                    result.append(formatted_plugin)
                elif plugin.get('type') == 'conditional':
                    # For conditionals, just process them and add to result
                    conditional_blocks, component_count = self._process_conditional(
                        plugin, section_type, None, component_count
                    )
                    result.extend(conditional_blocks)

        return result, component_count

    def _process_conditional(self, cond, section_type, data, component_count):
        """Process conditional statements and add them to components."""
        # Create the conditional block ID first
        conditional_id = component_count

        # Process plugins in if body
        if_plugins, component_count = self._process_plugins(
            cond.get('if_body', []), section_type, component_count + 1
        )

        # Process else if conditions
        else_ifs = []
        for else_if in cond.get('else_ifs', []):
            # Get the condition string from the else_if_condition
            condition = ''
            if isinstance(else_if, dict) and 'condition' in else_if:
                if isinstance(else_if['condition'], dict):
                    if 'condition' in else_if['condition']:
                        condition = else_if['condition']['condition']
                    elif 'value' in else_if['condition']:
                        condition = else_if['condition']['value']
                else:
                    condition = str(else_if['condition'])
            # Process the plugins in the else if body
            elif_plugins = []
            if 'body' in else_if:
                elif_plugins, component_count = self._process_plugins(
                    else_if['body'], section_type, component_count
                )
            # Add to else_ifs list with proper structure
            if condition:
                else_ifs.append({
                    'condition': condition.strip(),
                    'plugins': elif_plugins
                })

        # Process else condition - only create if it exists
        else_block = None
        if 'else_body' in cond and cond['else_body'] is not None:
            else_plugins, component_count = self._process_plugins(
                cond['else_body'], section_type, component_count
            )
            else_block = {'plugins': else_plugins}
        # Create the conditional block using the original component_count
        conditional_block = {
            'id': f"{section_type}_if_{conditional_id}",
            'type': section_type,
            'plugin': 'if',
            'config': {
                'condition': cond['if_condition'],
                'plugins': if_plugins,
                'else_ifs': else_ifs,
                'else': else_block
            }
        }

        # If data is provided, append to it (for nested conditionals)
        if data is not None:
            data.append(conditional_block)

        return [conditional_block], component_count


def _extract_error_context(config_text: str, line: int, column: int, context_lines: int = 3) -> str:
    """Extract the code context around an error location.

    Args:
        config_text: The full config text
        line: Line number where error occurred (1-indexed)
        column: Column number where error occurred (1-indexed)
        context_lines: Number of lines to show before and after the error

    Returns:
        Formatted string showing the error context with a pointer
    """
    lines = config_text.split('\n')

    # Calculate the range of lines to show
    start_line = max(0, line - context_lines - 1)
    end_line = min(len(lines), line + context_lines)

    # Build the context string
    context_parts = []
    context_parts.append("\n" + "="*60)
    context_parts.append("PROBLEMATIC CODE:")
    context_parts.append("="*60)

    for i in range(start_line, end_line):
        line_num = i + 1
        line_content = lines[i]

        # Mark the error line with an arrow
        if line_num == line:
            context_parts.append(f">>> {line_num:4d} | {line_content}")
            # Add a pointer to the exact column
            if column > 0:
                pointer = " " * (len(f">>> {line_num:4d} | ") + column - 1) + "^"
                context_parts.append(pointer)
        else:
            context_parts.append(f"    {line_num:4d} | {line_content}")

    context_parts.append("="*60)
    return "\n".join(context_parts)


def parse_logstash_config(config_text: str) -> List[Dict[str, Any]]:
    """Parse Logstash config text into a structured format."""
    parser = Lark(LOGSTASH_GRAMMAR, parser='lalr', transformer=LogstashTransformer())
    try:
        return parser.parse(config_text)
    except UnexpectedToken as e:
        # Extract detailed error information
        error_line = e.line
        error_column = e.column

        # Get the code context
        context = _extract_error_context(config_text, error_line, error_column)

        # Build a detailed error message
        error_msg = f"Failed to parse Logstash config at line {error_line}, column {error_column}\n"
        error_msg += f"Unexpected token: {e.token}\n"
        error_msg += f"Expected one of: {', '.join(e.expected)}\n"
        error_msg += context

        raise ValueError(error_msg)
    except UnexpectedCharacters as e:
        # Extract detailed error information
        error_line = e.line
        error_column = e.column

        # Get the code context
        context = _extract_error_context(config_text, error_line, error_column)

        # Build a detailed error message
        error_msg = f"Failed to parse Logstash config at line {error_line}, column {error_column}\n"
        error_msg += f"Unexpected character(s): {config_text[e.pos_in_stream:e.pos_in_stream+10]}\n"
        error_msg += f"Expected one of: {', '.join(e.allowed)}\n"
        error_msg += context

        raise ValueError(error_msg)
    except Exception as e:
        # Fallback for other errors
        raise ValueError(f"Failed to parse Logstash config: {str(e)}")


def logstash_config_to_components(config_text: str) -> List[Dict[str, Any]]:
    """
    Convert Logstash configuration text to UI components format.

    Args:
        config_text: Raw Logstash configuration text

    Returns:
        List of component dictionaries in the UI format
    """
    try:
        parsed = parse_logstash_config(config_text)

        # Initialize data with all three sections (even if not in input)
        data = {
            "input": [],
            "filter": [],
            "output": []
        }

        component_count = 0
        transformer = LogstashTransformer()

        # Handle case where parsed might not be a list or could be empty
        if not isinstance(parsed, list):
            parsed = [parsed] if parsed else []

        # Collect top-level comments (comments before any section)
        top_level_comments = []
        sections = []

        for item in parsed:
            if isinstance(item, dict) and item.get('type') == 'comment':
                top_level_comments.append(item)
            else:
                sections.append(item)

        # If there are top-level comments, add them to the input section
        if top_level_comments:
            comment_texts = [c.get('text', '') for c in top_level_comments]
            top_comment_plugin = {
                'id': f"input_comment_{component_count}",
                'type': 'input',
                'plugin': 'comment',
                'config': {
                    'text': '\n'.join(comment_texts)
                }
            }
            data['input'].append(top_comment_plugin)
            component_count += 1

        for section in sections:
            # Defensive check: ensure section is a dict with 'type' key
            if not isinstance(section, dict):
                logger.warning(f"Skipping non-dict section: {type(section)}")
                continue

            if 'type' not in section:
                logger.warning(f"Section missing 'type' key: {section}")
                continue

            section_type = section['type']

            # Validate section_type is one of the expected values
            if section_type not in ['input', 'filter', 'output']:
                logger.warning(f"Warning: Unknown section type '{section_type}', skipping")
                continue

            section_components = []

            # Group consecutive comments together
            statements = section.get('statements', [])
            i = 0
            while i < len(statements):
                stmt = statements[i]
                if not isinstance(stmt, dict):
                    i += 1
                    continue

                if stmt.get('type') == 'comment':
                    # Start collecting consecutive comments
                    comment_texts = [stmt.get('text', '')]
                    i += 1

                    # Look ahead for more consecutive comments
                    while i < len(statements) and isinstance(statements[i], dict) and statements[i].get('type') == 'comment':
                        comment_texts.append(statements[i].get('text', ''))
                        i += 1

                    # Create a single comment component with all lines joined
                    comment_plugin = {
                        'id': f"{section_type}_comment_{component_count}",
                        'type': section_type,
                        'plugin': 'comment',
                        'config': {
                            'text': '\n'.join(comment_texts)
                        }
                    }
                    section_components.append(comment_plugin)
                    component_count += 1
                elif 'name' in stmt:  # It's a regular plugin
                    component, component_count = transformer._format_plugin(stmt, section_type, component_count)
                    section_components.append(component)
                    i += 1
                elif stmt.get('type') == 'conditional':
                    # Process conditional and get the updated component count
                    # Pass None as the data parameter to prevent auto-adding to the section
                    conditional_blocks, component_count = transformer._process_conditional(
                        stmt, section_type, None, component_count
                    )
                    section_components.extend(conditional_blocks)
                    i += 1
                else:
                    i += 1

            # Add all components to the section
            data[section_type].extend(section_components)

        return json.dumps(data, indent=4)

    except Exception as e:
        # Re-raise the exception so the view can handle it and show to the user
        error_msg = str(e)
        logger.error(f"Error converting config to components: {error_msg}")
        raise Exception(f"Error converting config to components: {error_msg}")


################################ Component JSON to Logstash config ################################

class ComponentToPipeline:
    def __init__(self, components, test=False, add_ids=False):
        self.components = components
        self.plugin_num = 0
        self.test = test
        self.add_ids = add_ids
        self.plugin_counters = {}  # Track plugin counts for ID generation

    def _generate_plugin_id(self, plugin_name, section):
        """Generate a predictable and reusable ID for a plugin."""
        # Create a counter key for this plugin type in this section
        counter_key = f"{section}_{plugin_name}"
        
        # Increment the counter for this plugin type
        if counter_key not in self.plugin_counters:
            self.plugin_counters[counter_key] = 0
        
        self.plugin_counters[counter_key] += 1
        
        # Generate ID in format: section_pluginname_count
        return f"{section}_{plugin_name}_{self.plugin_counters[counter_key]}"

    def _format_string_value(self, value):
        """Format a string value for Logstash config, choosing appropriate quoting.
        
        If the string contains double quotes (like JSON or Ruby code), use single quotes.
        Otherwise, use double quotes and escape as needed.
        """
        if not isinstance(value, str):
            return value
        
        # For multiline strings (like Ruby code), use single quotes to preserve literal newlines/tabs
        # Single quotes in Logstash don't interpret escape sequences, so \n stays as actual newline
        if '\n' in value:
            # Multiline with newlines - use single quotes if possible
            if "'" not in value:
                return f"'{value}'"
            # Has single quotes - escape them and use single quotes
            escaped_value = value.replace("'", "\\'")
            return f"'{escaped_value}'"
        
        # If string contains double quotes but no single quotes, use single quotes
        if '"' in value and "'" not in value:
            return f"'{value}'"
        
        # If string contains single quotes but no double quotes, use double quotes (no escaping needed)
        if "'" in value and '"' not in value:
            return f'"{value}"'
        
        # If string contains both or neither, use double quotes and escape double quotes
        # Also handle backslashes properly
        result = []
        i = 0
        while i < len(value):
            if value[i] == '"':
                result.append('\\"')
                i += 1
            elif value[i] == '\\' and i + 1 < len(value):
                next_char = value[i + 1]
                # Only escape backslash if it's followed by a char that creates an escape sequence
                # in double-quoted strings: \", \\
                if next_char in ['"', '\\']:
                    result.append('\\\\')
                else:
                    # Keep backslash as-is for patterns like \[, \], \d, \s, etc.
                    result.append('\\')
                i += 1
            else:
                result.append(value[i])
                i += 1
        return f'"{"".join(result)}"'
    
    def _extract_plugin_values(self, plugin, section):
        config = ""
        # Setup testing

        if section == "filter" and self.test == True:
            config += f"\tif [plugin_num] >= {self.plugin_num} {{\n"
        config += f'{plugin["plugin"]} {{\n'
        
        # Add ID if requested and not already present
        if self.add_ids and 'id' not in plugin.get('config', {}):
            generated_id = self._generate_plugin_id(plugin['plugin'], section)
            config += f'\tid => "{generated_id}"\n'
        
        for plugin_config_name in plugin['config']:
            plugin_config_value = plugin['config'][plugin_config_name]


            if type(plugin_config_value) in [str, int, float]:
                if type(plugin_config_value) is str:
                    formatted_value = self._format_string_value(plugin_config_value)
                    config += f'\t{plugin_config_name} => {formatted_value}\n'
                else:
                    # Write numeric values without quotes to preserve their type
                    config += f'\t{plugin_config_name} => {plugin_config_value}\n'

            elif type(plugin_config_value) is dict and plugin_config_name == "codec":
                # Special handling for codec: {"codec_name": {config}}
                for codec_name, codec_config in plugin_config_value.items():
                    if codec_config:
                        # Codec with configuration
                        config += f"\t{plugin_config_name} => {codec_name} {{\n"
                        for codec_key, codec_value in codec_config.items():
                            if type(codec_value) in [str]:
                                formatted_value = self._format_string_value(codec_value)
                                config += f'\t\t{codec_key} => {formatted_value}\n'
                            elif type(codec_value) is bool:
                                config += f'\t\t{codec_key} => {str(codec_value).lower()}\n'
                            elif type(codec_value) in [int, float]:
                                config += f'\t\t{codec_key} => {codec_value}\n'
                            elif type(codec_value) is dict:
                                # Nested hash in codec
                                nested = ', '.join([f'"{k}" => {self._format_string_value(v)}' for k, v in codec_value.items()])
                                config += f'\t\t{codec_key} => {{ {nested} }}\n'
                            else:
                                config += f'\t\t{codec_key} => {json.dumps(codec_value)}\n'
                        config += "\t}\n"
                    else:
                        # Codec without configuration
                        config += f"\t{plugin_config_name} => {codec_name}\n"

            elif type(plugin_config_value) is dict:
                # Regular dict (not codec)
                config += f"\t{plugin_config_name} => {{\n"

                for dict_key in plugin_config_value:
                    dict_value = plugin_config_value[dict_key]
                    # Handle different value types within dictionaries
                    if type(dict_value) is list:
                        # Format list with proper indentation and line breaks
                        config += f'\t\t"{dict_key}" => [\n'
                        for i, item in enumerate(dict_value):
                            comma = "," if i < len(dict_value) - 1 else ""
                            if type(item) is str:
                                formatted_item = self._format_string_value(item)
                                config += f'\t\t\t{formatted_item}{comma}\n'
                            else:
                                config += f'\t\t\t{json.dumps(item)}{comma}\n'
                        config += "\t\t]\n"
                    elif type(dict_value) is dict:
                        # Nested hash - recursively format it
                        config += f'\t\t"{dict_key}" => {{\n'
                        for nested_key in dict_value:
                            formatted_nested_value = self._format_string_value(dict_value[nested_key])
                            config += f'\t\t\t"{nested_key}" => {formatted_nested_value}\n'
                        config += "\t\t}\n"
                    elif type(dict_value) is bool:
                        config += f'\t\t"{dict_key}" => {str(dict_value).lower()}\n'
                    elif type(dict_value) in [int, float]:
                        config += f'\t\t"{dict_key}" => {dict_value}\n'
                    else:
                        formatted_dict_value = self._format_string_value(dict_value)
                        config += f'\t\t"{dict_key}" => {formatted_dict_value}\n'

                config += "\t}\n"
            elif type(plugin_config_value) is list:
                # Check if this is an array of hashes (list of dictionaries)
                if plugin_config_value and isinstance(plugin_config_value[0], dict):
                    # Array of hashes - format each hash using Logstash syntax
                    config += f"\t{plugin_config_name} => [\n"
                    for i, hash_item in enumerate(plugin_config_value):
                        # Build the hash content
                        hash_pairs = []
                        for key, value in hash_item.items():
                            if isinstance(value, str):
                                formatted_value = self._format_string_value(value)
                                hash_pairs.append(f'{key} => {formatted_value}')
                            elif isinstance(value, bool):
                                hash_pairs.append(f'{key} => {str(value).lower()}')
                            elif isinstance(value, (int, float)):
                                hash_pairs.append(f'{key} => {value}')
                            else:
                                # Fallback to JSON for complex types
                                hash_pairs.append(f'{key} => {json.dumps(value)}')
                        
                        # Join pairs with spaces and wrap in braces
                        hash_content = ' '.join(hash_pairs)
                        # Add comma after each entry except the last one
                        comma = ',' if i < len(plugin_config_value) - 1 else ''
                        config += f"\t\t{{ {hash_content} }}{comma}\n"
                    config += "\t]\n"
                else:
                    # Regular array - use JSON format
                    config += "\t" + plugin_config_name + " => " + json.dumps(plugin_config_value) + "\n"
            elif type(plugin_config_value) is bool:

                config += f'\t{plugin_config_name} => {str(plugin_config_value).lower()}\n'

        # Closes the plugin
        config += "}\n"

        if section == "filter" and self.test == True:
            config += "\t}\n"

        self.plugin_num += 1
        return config

    def _add_tab_level(self, input, skip_string_content=False):
        lines = input.split('\n')
        result = []
        in_multiline_string = False
        skip_this_string = False
        
        for i, line in enumerate(lines):
            # Determine if we should add a tab to this line BEFORE updating state
            should_add_tab = True
            
            # Check if we should skip this line (if we're inside a code/script/body string)
            if skip_this_string and in_multiline_string and 'code =>' not in line and 'script =>' not in line and 'body =>' not in line:
                should_add_tab = False
            
            # Now check if this line starts or continues a multi-line string
            if '=>' in line and '"' in line:
                # Check if this is a code/script/body parameter
                if 'code =>' in line or 'script =>' in line or 'body =>' in line:
                    skip_this_string = True
                
                # Count quotes after the =>
                after_arrow = line.split('=>', 1)[1] if '=>' in line else line
                quote_count = after_arrow.count('"')
                # Odd number of quotes means we're starting/ending a multi-line string
                if quote_count % 2 == 1:
                    in_multiline_string = not in_multiline_string
                    if not in_multiline_string:
                        skip_this_string = False  # Reset when exiting string
            elif '"' in line:
                # Check if this line ends the multi-line string
                quote_count = line.count('"')
                if quote_count % 2 == 1:
                    in_multiline_string = not in_multiline_string
                    if not in_multiline_string:
                        skip_this_string = False  # Reset when exiting string
            
            # Add tab unless we're skipping or it's the last empty line
            if not should_add_tab:
                result.append(line)
            elif line or i < len(lines) - 1:
                result.append('\t' + line)
            else:
                result.append(line)
        
        return '\n'.join(result)

    def _extract_condition_values(self, condition, section):
        config = ""

        # --- Start if ---
        config += f"if {condition['config']['condition']} {{\n"
        for plugin in condition['config']['plugins']:
            if plugin['plugin'] == 'comment':
                # Handle comment inside conditional
                comment_text = plugin['config'].get('text', '')
                comment_lines = comment_text.split('\n')
                for line in comment_lines:
                    config += f"\t# {line}\n"
            elif plugin['plugin'] == 'if':
                config += self._add_tab_level(self._extract_condition_values(plugin, section))
            else:
                config += self._add_tab_level(self._extract_plugin_values(plugin, section))
        config += "}\n"

        # --- Start else if ---
        if condition['config'].get('else_ifs'):
            for plugin in condition['config']['else_ifs']:
                config += f"else if {plugin['condition']} {{\n"
                for nested_plugin in plugin['plugins']:
                    if nested_plugin['plugin'] == 'comment':
                        # Handle comment inside else if
                        comment_text = nested_plugin['config'].get('text', '')
                        comment_lines = comment_text.split('\n')
                        for line in comment_lines:
                            config += f"\t# {line}\n"
                    elif nested_plugin['plugin'] == 'if':
                        config += self._add_tab_level(self._extract_condition_values(nested_plugin, section))
                    else:
                        config += self._add_tab_level(self._extract_plugin_values(nested_plugin, section))
                config += "}\n"

        # --- Start else ---
        if condition['config'].get('else') and condition['config']['else'].get('plugins'):
            config += f"else {{\n"

            for plugin in condition['config']['else']['plugins']:
                if plugin['plugin'] == 'comment':
                    # Handle comment inside else
                    comment_text = plugin['config'].get('text', '')
                    comment_lines = comment_text.split('\n')
                    for line in comment_lines:
                        config += f"\t# {line}\n"
                elif plugin['plugin'] == 'if':
                    config += self._add_tab_level(self._extract_condition_values(plugin, section))
                else:
                    config += self._add_tab_level(self._extract_plugin_values(plugin, section))
            config += "}\n"

        return config



    def components_to_logstash_config(self):
        config = ""
        # "test" is used for simulating pipelines so that we can send input via stdin
        # and receive output via stdout
        if self.test:
            self.components['components']['input'] = [{
                'id': 'stdin',
                'type': 'input',
                'plugin': 'stdin',
                'config': {
                    "codec": {"json": {}}
                }
            }]
            self.components['components']['output'] = [{
                'id': 'stdout',
                'type': 'output',
                'plugin': 'stdout',
                'config': {
                    "codec": {"json_lines": {}}
                }
            }]

        for section in self.components:
            # Adding section, this is static and indentation never changes
            config += section + " {\n"

            # plugin_num used for running simulations
            for plugin in self.components[section]:
                if plugin['plugin'] == 'comment':
                    # Convert comment plugin back to comment lines
                    comment_text = plugin['config'].get('text', '')
                    # Split by newlines and prefix each line with # (with space)
                    comment_lines = comment_text.split('\n')
                    for line in comment_lines:
                        config += f"\t# {line}\n"
                elif plugin['plugin'] == 'if':
                    config += self._add_tab_level(self._extract_condition_values(plugin, section))
                else:
                    config += self._add_tab_level(self._extract_plugin_values(plugin, section))

            # ending section, this is static and indentation never changes
            config += "}\n"
        return config



def main():
    condition_output_no_filter = logstash_config_to_components('''input { stdin { } }

filter {
  grok {
    match => { "message" => "%{COMBINEDAPACHELOG}" }
  }
  date {
    match => [ "timestamp" , "dd/MMM/yyyy:HH:mm:ss Z" ]
  }
}

output {
  elasticsearch { hosts => ["localhost:9200"] }
  stdout { codec => rubydebug }
}
''')
    logger.debug(condition_output_no_filter)



if __name__ == "__main__":
    main()