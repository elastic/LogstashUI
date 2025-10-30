from lark import Lark, Transformer, UnexpectedToken, UnexpectedCharacters
from typing import Dict, List, Any
import json

################################ Logstash config to component JSON ################################
LOGSTASH_GRAMMAR = r"""
?start: section+

section: section_type "{" [statement+] "}"

statement: plugin | conditional

conditional: "if" condition "{" [statement+] "}" (else_if_condition | else_condition)*
condition: CMP_OPERATORS
else_if_condition: "else" "if" condition "{" [statement+] "}"
else_condition: "else" "{" [statement+] "}"

CMP_OPERATORS: /[^\n{]+/  // Matches anything except newline and {
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
%ignore WS
%ignore /#[^\n]*/
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
        return self._unescape_string(s[0][1:-1])
    
    def string(self, s):
        # Remove quotes and unescape the content
        return self._unescape_string(s[0][1:-1])

    def condition(self, items):
        return items[0].strip()

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
        return list(items)

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
                if 'name' in plugin:  # It's a regular plugin
                    formatted_plugin, component_count = self._format_plugin(plugin, section_type, component_count)
                    result.append(formatted_plugin)
                    component_count += 1
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
        data = {
            "input": [],
            "filter": [],
            "output": []
        }

        component_count = 0
        transformer = LogstashTransformer()

        for section in parsed:
            section_type = section['type']
            section_components = []

            for stmt in section.get('statements', []):
                if not isinstance(stmt, dict):
                    continue

                if 'name' in stmt:  # It's a regular plugin
                    component, component_count = transformer._format_plugin(stmt, section_type, component_count)
                    section_components.append(component)
                    component_count += 1
                elif stmt.get('type') == 'conditional':
                    # Process conditional and get the updated component count
                    # Pass None as the data parameter to prevent auto-adding to the section
                    conditional_blocks, component_count = transformer._process_conditional(
                        stmt, section_type, None, component_count
                    )
                    section_components.extend(conditional_blocks)

            # Add all components to the section
            data[section_type].extend(section_components)

        return json.dumps(data, indent=4)

    except Exception as e:
        print(f"Error converting config to components: {str(e)} Line: {str(e.__traceback__.tb_lineno)}")
        return []


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

    def _escape_string(self, value):
        """Escape special characters in string values for Logstash config."""
        if not isinstance(value, str):
            return value
        # Only escape double quotes and backslashes that precede special chars
        # Preserve backslashes in patterns like \[ \] \d etc.
        result = []
        i = 0
        while i < len(value):
            if value[i] == '"':
                result.append('\\"')
                i += 1
            elif value[i] == '\\' and i + 1 < len(value):
                next_char = value[i + 1]
                # Only escape backslash if it's followed by a char that creates an escape sequence
                # in double-quoted strings: \n, \t, \r, \", \\
                if next_char in ['n', 't', 'r', '"', '\\']:
                    result.append('\\\\')
                else:
                    # Keep backslash as-is for patterns like \[, \], \d, etc.
                    result.append('\\')
                i += 1
            else:
                result.append(value[i])
                i += 1
        return ''.join(result)
    
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

            # print(plugin_config_name, plugin_config_value, type(plugin_config_value))
            if type(plugin_config_value) in [str, int, float]:
                if type(plugin_config_value) is str:
                    escaped_value = self._escape_string(plugin_config_value)
                    config += f'\t{plugin_config_name} => "{escaped_value}"\n'
                else:
                    config += f'\t{plugin_config_name} => "{plugin_config_value}"\n'

            elif type(plugin_config_value) is dict and plugin_config_name == "codec":
                # Special handling for codec: {"codec_name": {config}}
                for codec_name, codec_config in plugin_config_value.items():
                    if codec_config:
                        # Codec with configuration
                        config += f"\t{plugin_config_name} => {codec_name} {{\n"
                        for codec_key, codec_value in codec_config.items():
                            if type(codec_value) in [str]:
                                escaped_value = self._escape_string(codec_value)
                                config += f'\t\t{codec_key} => "{escaped_value}"\n'
                            elif type(codec_value) is bool:
                                config += f'\t\t{codec_key} => {str(codec_value).lower()}\n'
                            elif type(codec_value) in [int, float]:
                                config += f'\t\t{codec_key} => {codec_value}\n'
                            elif type(codec_value) is dict:
                                # Nested hash in codec
                                nested = ', '.join([f'"{k}" => "{self._escape_string(v)}"' for k, v in codec_value.items()])
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
                                escaped_item = self._escape_string(item)
                                config += f'\t\t\t"{escaped_item}"{comma}\n'
                            else:
                                config += f'\t\t\t{json.dumps(item)}{comma}\n'
                        config += "\t\t]\n"
                    elif type(dict_value) is dict:
                        # Nested hash - recursively format it
                        config += f'\t\t"{dict_key}" => {{\n'
                        for nested_key in dict_value:
                            escaped_nested_value = self._escape_string(dict_value[nested_key])
                            config += f'\t\t\t"{nested_key}" => "{escaped_nested_value}"\n'
                        config += "\t\t}\n"
                    elif type(dict_value) is bool:
                        config += f'\t\t"{dict_key}" => {str(dict_value).lower()}\n'
                    elif type(dict_value) in [int, float]:
                        config += f'\t\t"{dict_key}" => {dict_value}\n'
                    else:
                        escaped_dict_value = self._escape_string(dict_value)
                        config += f'\t\t"{dict_key}" => "{escaped_dict_value}"\n'

                config += "\t}\n"
            elif type(plugin_config_value) is list:
                config += "\t" + plugin_config_name + " => " + json.dumps(plugin_config_value) + "\n"
            elif type(plugin_config_value) is bool:

                config += f'\t{plugin_config_name} => {str(plugin_config_value).lower()}\n'

        # Closes the plugin
        config += "}\n"

        if section == "filter" and self.test == True:
            config += "\t}\n"

        self.plugin_num += 1
        return config

    def _add_tab_level(self, input):
        lines = input.split('\n')
        # Don't add tab to the last line if it's empty (trailing newline case)
        tabbed_input = ['\t' + line if line or i < len(lines) - 1 else line 
                        for i, line in enumerate(lines)]
        return '\n'.join(tabbed_input)

    def _extract_condition_values(self, condition, section):
        config = ""

        # --- Start if ---
        config += f"if {condition['config']['condition']} {{\n"
        for plugin in condition['config']['plugins']:
            if plugin['plugin'] == 'if':
                config += self._add_tab_level(self._extract_condition_values(plugin, section))
            else:
                config += self._add_tab_level(self._extract_plugin_values(plugin, section))
        config += "}\n"

        # --- Start else if ---
        if condition['config'].get('else_ifs'):
            for plugin in condition['config']['else_ifs']:
                config += f"else if {plugin['condition']} {{\n"
                for nested_plugin in plugin['plugins']:
                    if nested_plugin['plugin'] == 'if':
                        config += self._add_tab_level(self._extract_condition_values(nested_plugin, section))
                    else:
                        config += self._add_tab_level(self._extract_plugin_values(nested_plugin, section))
                config += "}\n"

        # --- Start else ---
        if condition['config'].get('else') and condition['config']['else'].get('plugins'):
            config += f"else {{\n"

            for plugin in condition['config']['else']['plugins']:
                if plugin['plugin'] == 'if':
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
                if plugin['plugin'] == 'if':
                    config += self._add_tab_level(self._extract_condition_values(plugin, section))
                else:
                    config += self._add_tab_level(self._extract_plugin_values(plugin, section))

            # ending section, this is static and indentation never changes
            config += "}\n"
        # print(config)
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
    print(condition_output_no_filter)

#     z = ComponentToPipeline({
#     "input": [
#         {
#             "id": "input_stdin_0",
#             "type": "input",
#             "plugin": "stdin",
#             "config": {}
#         }
#     ],
#     "filter": [
#         {
#             "id": "filter_grok_2",
#             "type": "filter",
#             "plugin": "grok",
#             "config": {
#                 "match": {
#                     "\"message\"": "%{COMBINEDAPACHELOG}"
#                 }
#             }
#         },
#         {
#             "id": "filter_date_4",
#             "type": "filter",
#             "plugin": "date",
#             "config": {
#                 "match": [
#                     "timestamp",
#                     "dd/MMM/yyyy:HH:mm:ss Z"
#                 ]
#             }
#         }
#     ],
#     "output": [
#         {
#             "id": "output_elasticsearch_6",
#             "type": "output",
#             "plugin": "elasticsearch",
#             "config": {
#                 "hosts": [
#                     "localhost:9200"
#                 ]
#             }
#         },
#         {
#             "id": "output_stdout_8",
#             "type": "output",
#             "plugin": "stdout",
#             "config": {
#                 "codec": {
#                     "rubydebug": {}
#                 }
#             }
#         }
#     ]
# },test=False)
#     print(z.components_to_logstash_config())



if __name__ == "__main__":
    main()