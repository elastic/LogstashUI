from lark import Lark, Transformer
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
    | "codec" "=>" (CNAME | ESCAPED_STRING)     -> codec_pair_simple
    | (CNAME | ESCAPED_STRING) "=>" (UNQUOTED_STRING | CNAME | value)  -> regular_pair

codec_config: [codec_setting (","? codec_setting)*]
codec_setting: (CNAME | ESCAPED_STRING) "=>" (UNQUOTED_STRING | CNAME | value)

?value: string
      | number
      | array
      | hash
      | env_var
      | plugin

string: ESCAPED_STRING
number: SIGNED_NUMBER
array: "[" [value ("," value)*] "]"
hash: "{" [pair (","? pair)*] "}"
env_var: "${" CNAME "}"

%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER
%import common.CNAME
%import common.WS
%import common.NEWLINE

UNQUOTED_STRING.2: /[a-zA-Z_][a-zA-Z0-9_-]*/
%ignore WS
%ignore /#[^\n]*/
%ignore /\n+/
"""


class LogstashTransformer(Transformer):
    def string(self, s):
        return s[0][1:-1]  # Remove quotes

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
            return (items[0], items[1])
        elif len(items) == 1:
            return (items[0], None)
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
            return (items[0], items[1])
        elif len(items) == 1:
            # Single item - might be a key with no value
            return (items[0], None)
        else:
            return (None, None)
    
    def pair(self, items):
        """Fallback for pair - should be handled by codec_pair or regular_pair"""
        if len(items) >= 2:
            return (items[0], items[1])
        elif len(items) == 1:
            return (items[0], None)
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

        # Process else condition - ensure it's always an object with a plugins array
        else_block = {'plugins': []}
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


def parse_logstash_config(config_text: str) -> List[Dict[str, Any]]:
    """Parse Logstash config text into a structured format."""
    parser = Lark(LOGSTASH_GRAMMAR, parser='lalr', transformer=LogstashTransformer())
    try:
        return parser.parse(config_text)
    except Exception as e:
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
    def __init__(self, components, test=False):
        self.components = components
        self.plugin_num = 0
        self.test = test

    def _extract_plugin_values(self, plugin, section):
        config = ""
        # Setup testing

        if section == "filter" and self.test == True:
            config += f"\tif [plugin_num] >= {self.plugin_num} {{\n"
        config += f'{plugin["plugin"]} {{\n'
        for plugin_config_name in plugin['config']:
            plugin_config_value = plugin['config'][plugin_config_name]

            # print(plugin_config_name, plugin_config_value, type(plugin_config_value))
            if type(plugin_config_value) in [str, int, float]:
                config += f'\t{plugin_config_name} => "{plugin_config_value}"\n'

            elif type(plugin_config_value) is dict and plugin_config_name == "codec":
                # Special handling for codec: {"codec_name": {config}}
                for codec_name, codec_config in plugin_config_value.items():
                    if codec_config:
                        # Codec with configuration
                        config += f"\t{plugin_config_name} => {codec_name} {{\n"
                        for codec_key, codec_value in codec_config.items():
                            if type(codec_value) in [str]:
                                config += f'\t\t{codec_key} => "{codec_value}"\n'
                            elif type(codec_value) is bool:
                                config += f'\t\t{codec_key} => {str(codec_value).lower()}\n'
                            elif type(codec_value) in [int, float]:
                                config += f'\t\t{codec_key} => {codec_value}\n'
                            elif type(codec_value) is dict:
                                # Nested hash in codec
                                nested = ', '.join([f'{k} => "{v}"' for k, v in codec_value.items()])
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
                        config += f"\t\t{dict_key} => [\n"
                        for i, item in enumerate(dict_value):
                            comma = "," if i < len(dict_value) - 1 else ""
                            if type(item) is str:
                                config += f'\t\t\t"{item}"{comma}\n'
                            else:
                                config += f'\t\t\t{json.dumps(item)}{comma}\n'
                        config += "\t\t]\n"
                    elif type(dict_value) is dict:
                        # Nested hash - recursively format it
                        config += f"\t\t{dict_key} => {{\n"
                        for nested_key in dict_value:
                            config += f'\t\t\t{nested_key} => "{dict_value[nested_key]}"\n'
                        config += "\t\t}\n"
                    elif type(dict_value) is bool:
                        config += f"\t\t{dict_key} => {str(dict_value).lower()}\n"
                    elif type(dict_value) in [int, float]:
                        config += f"\t\t{dict_key} => {dict_value}\n"
                    else:
                        config += f'\t\t{dict_key} => "{dict_value}"\n'

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
        if condition['config']['else_ifs']:
            for plugin in condition['config']['else_ifs']:
                config += f"else if {plugin['condition']}{{\n"
                for nested_plugin in plugin['plugins']:
                    if nested_plugin['plugin'] == 'if':
                        config += self._add_tab_level(self._extract_condition_values(nested_plugin, section))
                    else:
                        config += self._add_tab_level(self._extract_plugin_values(nested_plugin, section))
                config += "}\n"

        # --- Start else ---
        if condition['config']['else']['plugins']:
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
    # condition_output_no_filter = logstash_config_to_components("""    input { beats { port => 5044 } }
    # output {
    #     if [type] == "apache" {
    #       pipeline { send_to => "nested-weblogs" }
    #       if [type] == "nested-apache" {
    #           pipeline { send_to => "nested-weblogs" }
    #         } else if [type] == "nested-system" {
    #           pipeline { send_to => "nested-syslog" }
    #         } else if [type] == "nested-test" {
    #           pipeline { send_to => "nested-syslog" }
    #         } else {
    #           pipeline { send_to => "nested_fallback" }
    #         }
    #     } else if [type] == "system" {
    #       pipeline { send_to => syslog }
    #     } else if [type] == "test" {
    #       pipeline { send_to => test }
    #     } else {
    #     if [type] == "nested-apache" {
    #           pipeline { send_to => "nested-weblogs" }
    #         } else if [type] == "nested-system" {
    #           pipeline { send_to => "nested-syslog" }
    #         } else if [type] == "nested-test" {
    #           pipeline { send_to => "nested-syslog" }
    #         } else {
    #           pipeline { send_to => "nested_fallback" }
    #         }
    #     } else if [type] == "system" {
    #       pipeline { send_to => syslog }
    #     } else if [type] == "test" {
    #       pipeline { send_to => test }
    #     } else {
    #       pipeline { send_to => fallback-test }
    #                   	elasticsearch {
	# 	hosts => ["http://elasticsearch:9200"]
	# 	index => "%{[@metadata][beat]}-%{[@metadata][version]}-%{+YYYY.MM.dd}"
	# }
    #       pipeline { send_to => fallback-test }
    #                   	elasticsearch {
	# 	hosts => ["http://elasticsearch:9200"]
	# 	index => "%{[@metadata][beat]}-%{[@metadata][version]}-%{+YYYY.MM.dd}"
	# }
    #     }
    # }""")
    # print(condition_output_no_filter)

    z = ComponentToPipeline({
    "input": [
        {
            "id": "input_udp_0",
            "type": "input",
            "plugin": "udp",
            "config": {
                "port": 5119
            }
        }
    ],
    "filter": [
        {
            "id": "filter_mutate_2",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "rename": {
                    "\"message\"": "log.original",
                    "\"host\"": "observer.ip"
                },
                "copy": {
                    "\"host\"": "sysloghost"
                }
            }
        },
        {
            "id": "filter_grok_4",
            "type": "filter",
            "plugin": "grok",
            "config": {
                "match": {
                    "\"log.original\"": [
                        "%{CISCO_TAGGED_SYSLOG} %{GREEDYDATA:message}",
                        "^<%{POSINT:syslog_pri}>%{DATA}: %%{DATA:ciscotag}: %{GREEDYDATA:message}",
                        "^<%{POSINT:syslog_pri}>%%{DATA:ciscotag}: %{GREEDYDATA:message}"
                    ]
                }
            }
        },
        {
            "id": "filter_grok_6",
            "type": "filter",
            "plugin": "grok",
            "config": {
                "match": {
                    "\"ciscotag\"": [
                        "%{WORD}-%{INT:event.severity}-%{INT:event.code}",
                        "%{WORD}-%{WORD}-%{INT:event.severity}-%{INT:event.code}"
                    ]
                }
            }
        },
        {
            "id": "filter_mutate_8",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "add_field": {
                    "\"event.action\"": "firewall-rule"
                }
            }
        },
        {
            "id": "filter_if_10",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[event.code] == \"105012\"",
                "plugins": [
                    {
                        "id": "filter_grok_11",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"message\"": [
                                    "Teardown dynamic %{WORD:network.transport} translation from %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}/%{INT:destination.port} duration %{DATA:cisco.duration_hms}$"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [
                    {
                        "condition": "[event.code] == \"106001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_13",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{network.direction} %{network.transport} connection %{event.outcome} from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} flags %{} on interface %{source_interface}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_15",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106002\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_17",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{network.transport} Connection %{event.outcome} by %{network.direction} list %{cisco.list_id} src %{source.address} dest %{destination.address}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_19",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106006\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_21",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.direction} %{network.transport} from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} on interface %{cisco.source_interface}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_23",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106007\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_25",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.direction} %{network.transport} from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} due to %{network.protocol} %{}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_27",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106010\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_29",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.direction} %{network.transport} src %{cisco.source_interface}:%{source.address}/%{source.port} %{} dst %{cisco.destination_interface}:%{destination.address}/%{destination.port} %{}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_31",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106013\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_33",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dropping echo request from %{source.address} to PAT address %{destination.address}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_35",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"network.transport\"": "icmp",
                                        "\"network.direction\"": "inbound"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106014\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_37",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.direction} %{network.transport} src %{cisco.source_interface}:%{source.address} %{}dst %{cisco.destination_interface}:%{destination.address} %{}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_39",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106015\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_41",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} (no connection) from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} flags %{} on interface %{cisco.source_interface}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_43",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106016\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_45",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} IP spoof from (%{source.address}) to %{destination.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106017\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_47",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} IP due to Land Attack from %{source.address} to %{destination.address}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106018\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_49",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{network.transport} packet type %{cisco.icmp_type} %{event.outcome} by %{network.direction} list %{cisco.list_id} src %{source.address} dest %{destination.address}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106020\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_51",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} IP teardrop fragment (size = %{}, offset = %{}) from %{source.address} to %{destination.address}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106021\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_53",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} reverse path check from %{source.address} to %{destination.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106022\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_55",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} connection spoof from %{source.address} to %{destination.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106023\"",
                        "plugins": [
                            {
                                "id": "filter_grok_57",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "%{WORD:event.outcome} %{WORD:network.transport} src %{WORD:cisco.source_interface}:%{IPORHOST:source.address}?(/%{INT:source.port}) dst %{WORD:cisco.destination_interface}:%{IPORHOST:destination.address}?(/%{INT:destination.port}) by access-group \\\"%{DATA:cisco.list_id}\\\"",
                                            "%{WORD:event.outcome} %{WORD:network.transport} src %{WORD:cisco.source_interface}:%{IPORHOST:source.address} dst %{WORD:destination.direction}:%{IPORHOST:destination.address} \\(%{DATA}\\) by access-group \\\"%{DATA:cisco.list_id}\\\"",
                                            "%{WORD:event.outcome} %{WORD:network.transport} src %{WORD:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} dst %{WORD:cisco.destination.interface}:%{IPORHOST:destination.address}/%{INT:destination.port} by access-group \\\"%{DATA:cisco.list_id}\\\""
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_59",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106027\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_61",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{} %{event.outcome} src %{source.address} dst %{destination.address} by access-group \\\"%{cisco.list_id}\\\"%{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106100\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_63",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "access-list %{cisco.list_id} %{event.outcome} %{network.transport} %{cisco.source_interface}/%{source.address}(%{source.port}) -> %{cisco.destination_interface}/%{destination.address}(%{destination.port}) %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106102\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_65",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "access-list %{cisco.list_id} %{event.outcome} %{network.transport} for user %{cisco.username} %{cisco.source_interface}/%{source.address} %{source.port} %{cisco.destination_interface}/%{destination.address} %{destination.port} %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106103\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_67",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "access-list %{cisco.list_id} %{event.outcome} %{network.transport} for user %{cisco.username} %{cisco.source_interface}/%{source.address} %{source.port} %{cisco.destination_interface}/%{destination.address} %{destination.port} %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"113004\"",
                        "plugins": [
                            {
                                "id": "filter_grok_69",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "AAA user accounting %{WORD:cisco.auth_outcome} : server =%{SPACE}%{IP:source.address} : user =%{SPACE}%{DATA:source.user.name}$"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_71",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "authentication"
                                    }
                                }
                            },
                            {
                                "id": "filter_if_73",
                                "type": "filter",
                                "plugin": "if",
                                "config": {
                                    "condition": "[cisco.auth_outcome] == \"Successful\"",
                                    "plugins": [
                                        {
                                            "id": "filter_mutate_74",
                                            "type": "filter",
                                            "plugin": "mutate",
                                            "config": {
                                                "add_field": {
                                                    "\"event.action\"": "authentication_success"
                                                }
                                            }
                                        }
                                    ],
                                    "else_ifs": [],
                                    "else": {
                                        "plugins": [
                                            {
                                                "id": "filter_mutate_76",
                                                "type": "filter",
                                                "plugin": "mutate",
                                                "config": {
                                                    "add_field": {
                                                        "\"event.action\"": "authentication_failure"
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"302015\" or [event.code] == \"302013\"",
                        "plugins": [
                            {
                                "id": "filter_grok_78",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Built %{WORD:network.direction} %{WORD:network.transport} connection %{INT} for %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} \\(%{IP}|\\) to %{DATA:cisco.destination_interface}:%{IPORHOST:destination.address}/%{INT:destination.port} \\(%{DATA}\\)",
                                            "Built %{WORD:network.direction} %{WORD:network.transport} connection %{INT} for %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} \\(%{DATA}\\)?(\\(%{DATA:cisco.source_username}\\)) to %{DATA:cisco.destination_interface}:%{IPORHOST:destination.address}/%{INT:destination.port} \\(%{DATA}\\) ?(\\(%{DATA:cisco.username}\\))",
                                            "Built %{WORD:network.direction} %{WORD:network.transport} connection %{INT:cisco.connection_id} for %{WORD:cisco.source_interface}:%{IPORHOST:source.address}\\/%{INT:source.port} \\(%{DATA}\\) to %{WORD:cisco.destination_interface}:%{IPORHOST:destination.address}/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_80",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"110003\"",
                        "plugins": [
                            {
                                "id": "filter_grok_82",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "%{DATA:cisco.event_error} for %{WORD:network.transport} from %{DATA:cisco.source_interface}:%{IP:source.address}\\/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}\\/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_84",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "error"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"113019\"",
                        "plugins": [
                            {
                                "id": "filter_grok_86",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Group = %{DATA:cisco.group}, Username = %{DATA:user.name}, IP = %{IP:cisco.client_vpn_ip}, %{DATA:cisco.client_vpn_action}\\. Session Type: %{DATA:cisco.session_type}, Duration: %{DATA:cisco.duration}, Bytes xmt: %{INT:cisco.vpn_transmit_byte_summary}, Bytes rcv: %{INT:cisco.vpn_receive_byte_summary}, Reason: %{DATA:cisco.client_vpn_outcome}$"
                                        ]
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"304001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_88",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{source.address} %{}ccessed URL %{destination.address}:%{url.original}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_90",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.outcome\"": "allow"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"304002\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_92",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Access %{event.outcome} URL %{url.original} SRC %{source.address} %{}EST %{destination.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"305011\"",
                        "plugins": [
                            {
                                "id": "filter_grok_94",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Built dynamic %{WORD:network.transport} translation from %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_96",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"305012\"",
                        "plugins": [
                            {
                                "id": "filter_grok_98",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Teardown dynamic %{WORD:network.transport} translation from %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_100",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_102",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} type=%{cisco.icmp_type}, code=%{cisco.icmp_code} from %{source.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313004\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_104",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} type=%{cisco.icmp_type}, from%{}addr %{source.address} on interface %{cisco.source_interface} to %{destination.address}: no matching session"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313005\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_106",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "No matching connection for %{network.transport} error message: %{} on %{cisco.source_interface} interface.%{}riginal IP payload: %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313008\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_108",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} type=%{cisco.icmp_type} , code=%{cisco.icmp_code} from %{source.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313009\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_110",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} invalid %{network.transport} code %{cisco.icmp_code} , for %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"322001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_112",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} MAC address %{source.mac}, possible spoof attempt on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_114",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic filter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338002\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_116",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_118",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "[destination.domain]"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338003\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_120",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338004\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_122",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338005\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_124",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_126",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "[source.domain]"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338006\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_128",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_130",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338007\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_132",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338008\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_134",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338101\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_136",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_138",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338102\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_140",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_142",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338103\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_144",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338104\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_146",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338201\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_148",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_150",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338202\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_152",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_154",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338203\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_156",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_158",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338204\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_160",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_162",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338301\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_164",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Intercepted DNS reply for domain %{source.domain} from %{cisco.source_interface}:%{source.address}/%{source.port} to %{cisco.destination_interface}:%{destination.address}/%{destination.port}, matched %{cisco.list_id}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_166",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"client.address\"": "client.address"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_168",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"client.port\"": "client.port"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_170",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.address\"": "server.address"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_172",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.port\"": "server.port"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] in [\"302014\", \"302016\", \"302018\", \"302021\", \"302036\", \"302304\", \"302306\", \"302020\"]",
                        "plugins": [
                            {
                                "id": "filter_grok_174",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "pattern_definitions": {
                                        "\"NOTCOLON\"": "[^:]*",
                                        "\"ECSSOURCEIPORHOST\"": "(?:%{IP:source.address}|%{HOSTNAME:source.domain})",
                                        "\"ECSDESTIPORHOST\"": "(?:%{IP:destination.address}|%{HOSTNAME:destination.domain})",
                                        "\"MAPPEDSRC\"": "(?:%{DATA:cisco.mapped_source_ip}|%{HOSTNAME})"
                                    },
                                    "match": {
                                        "\"message\"": [
                                            "Teardown %{NOTSPACE:network.transport} (?:state-bypass )?connection %{NOTSPACE:cisco.connection_id} (?:for|from) %{NOTCOLON}:%{DATA:source.address}/%{NUMBER:source.port:int}?(\\(%{DATA:cisco.source_username}\\)|) ?to %{NOTCOLON:cisco.destination_interface}:%{DATA:destination.address}/%{NUMBER:destination.port:int}?(\\(%{DATA:cisco.source_username}\\)|) ?(?:duration %{TIME:cisco.duration_hms} bytes %{NUMBER:network.bytes:int})%{GREEDYDATA}",
                                            "Teardown %{NOTSPACE:network.transport} (?:state-bypass )?connection %{NOTSPACE:cisco.connection_id} (?:for|from) %{NOTCOLON}:%{DATA:source.address}/%{NUMBER:source.port:int} (?:%{NOTSPACE:cisco.source_username} )?to %{NOTCOLON:cisco.destination_interface}:%{DATA:destination.address}/%{NUMBER:destination.port:int} (?:%{NOTSPACE:cisco.destination_username} )?(?:duration %{TIME:cisco.duration_hms} bytes %{NUMBER:network.bytes:int})%{GREEDYDATA}",
                                            "Teardown %{NOTSPACE:network.transport} connection for faddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSDESTIPORHOST}/%{NUMBER} (?:%{NOTSPACE:cisco.destination_username} )?gaddr (?:%{NOTCOLON}:)?%{MAPPEDSRC}/%{NUMBER} laddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSSOURCEIPORHOST}/%{NUMBER}(?: %{NOTSPACE:cisco.source_username})?%{GREEDYDATA}",
                                            "Built %{WORD:network.direction} %{NOTSPACE:network.transport} connection for faddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSDESTIPORHOST}/%{NUMBER} (?:%{NOTSPACE:cisco.destination_username} )?gaddr (?:%{NOTCOLON}:)?%{MAPPEDSRC}/%{NUMBER} laddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSSOURCEIPORHOST}/%{NUMBER}(?: %{NOTSPACE:cisco.source_username})?%{GREEDYDATA}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_176",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"419002\"",
                        "plugins": [
                            {
                                "id": "filter_grok_178",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "%{DATA:cisco.event_error} from %{WORD:cisco.source_interface}:%{IPORHOST:source.address}\\/%{INT:source.port} to %{WORD:cisco.destination_interface}:%{IPORHOST:destination.address}\\/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_180",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "error"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] in [\"733100\", \"752015\", \"752012\"]",
                        "plugins": [
                            {
                                "id": "filter_grok_182",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "%{GREEDYDATA:cisco.event_error}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_184",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "error"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"716002\"",
                        "plugins": [
                            {
                                "id": "filter_grok_186",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Group \\<%{DATA:cisco.group} User \\<%{DATA:user.name}\\> IP \\<%{IP:cisco.client_vpn_ip}\\> WebVPN session %{WORD:cisco.client_vpn_session_outcome}\\: %{DATA:cisco.web_vpn_action}\\."
                                        ]
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] in ['722022', '722033', '722055', '722051', '113039', '722023', '722037']",
                        "plugins": [
                            {
                                "id": "filter_grok_188",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Group \\<%{DATA:cisco.group} User \\<%{DATA:user.name}\\> IP \\<%{IP:cisco.client_vpn_ip}\\> %{GREEDYDATA:cisco.message}"
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                ],
                "else": {
                    "plugins": [
                        {
                            "id": "filter_grok_190",
                            "type": "filter",
                            "plugin": "grok",
                            "config": {
                                "match": {
                                    "\"message\"": [
                                        "forced_failure"
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        },
        {
            "id": "filter_if_192",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[event.category] == \"nat_translation\"",
                "plugins": [
                    {
                        "id": "filter_drop_193",
                        "type": "filter",
                        "plugin": "drop",
                        "config": {}
                    }
                ],
                "else_ifs": [],
                "else": {
                    "plugins": []
                }
            }
        },
        {
            "id": "filter_if_195",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[source.address]",
                "plugins": [
                    {
                        "id": "filter_grok_196",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"source.address\"": [
                                    "(?:%{IP:source.ip}|%{GREEDYDATA:source.domain})"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": {
                    "plugins": []
                }
            }
        },
        {
            "id": "filter_if_198",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[destination.address]",
                "plugins": [
                    {
                        "id": "filter_grok_199",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"destination.address\"": [
                                    "(?:%{IP:destination.ip}|%{GREEDYDATA:destination.domain})"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": {
                    "plugins": []
                }
            }
        },
        {
            "id": "filter_if_201",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[client.address]",
                "plugins": [
                    {
                        "id": "filter_grok_202",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"client.address\"": [
                                    "(?:%{IP:client.ip}|%{GREEDYDATA:client.domain})"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": {
                    "plugins": []
                }
            }
        },
        {
            "id": "filter_if_204",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[server.address]",
                "plugins": [
                    {
                        "id": "filter_grok_205",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"server.address\"": [
                                    "(?:%{IP:server.ip}|%{GREEDYDATA:server.domain})"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": {
                    "plugins": []
                }
            }
        },
        {
            "id": "filter_mutate_207",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "lowercase": [
                    "network.transport",
                    "network.protocol",
                    "network.direction",
                    "event.outcome"
                ]
            }
        },
        {
            "id": "filter_if_209",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[event.outcome] == \"est-allowed\"",
                "plugins": [
                    {
                        "id": "filter_mutate_210",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "update": {
                                "\"event.outcome\"": "allow"
                            }
                        }
                    }
                ],
                "else_ifs": [
                    {
                        "condition": "[event.outcome] == \"permitted\"",
                        "plugins": [
                            {
                                "id": "filter_mutate_212",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "update": {
                                        "\"event.outcome\"": "allow"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.outcome] == \"denied\"",
                        "plugins": [
                            {
                                "id": "filter_mutate_214",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "update": {
                                        "\"event.outcome\"": "deny"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.outcome] == \"dropped\"",
                        "plugins": [
                            {
                                "id": "filter_mutate_216",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "update": {
                                        "\"event.outcome\"": "deny"
                                    }
                                }
                            }
                        ]
                    }
                ],
                "else": {
                    "plugins": []
                }
            }
        },
        {
            "id": "filter_if_218",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[network.transport] == \"icmpv6\"",
                "plugins": [
                    {
                        "id": "filter_mutate_219",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "update": {
                                "\"network.transport\"": "ipv6-icmp"
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": {
                    "plugins": []
                }
            }
        },
        {
            "id": "filter_translate_221",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "network.transport",
                "destination": "network.iana_number",
                "dictionary": {
                    "\"icmp\"": "1",
                    "\"igmp\"": "2",
                    "\"ipv4\"": "4",
                    "\"tcp\"": "6",
                    "\"egp\"": "8",
                    "\"igp\"": "9",
                    "\"pup\"": "12",
                    "\"udp\"": "17",
                    "\"rdp\"": "27",
                    "\"irtp\"": "28",
                    "\"dccp\"": "33",
                    "\"idpr\"": "35",
                    "\"ipv6\"": "41",
                    "\"ipv6-route\"": "43",
                    "\"ipv6-frag\"": "44",
                    "\"rsvp\"": "46",
                    "\"gre\"": "47",
                    "\"esp\"": "50",
                    "\"ipv6-icmp\"": "58",
                    "\"ipv6-nonxt\"": "59",
                    "\"ipv6-opts\"": "60"
                }
            }
        },
        {
            "id": "filter_mutate_223",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "remove_field": [
                    "ciscotag",
                    "timestamp"
                ]
            }
        },
        {
            "id": "filter_mutate_225",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "add_field": {
                    "\"event.module\"": "cisco",
                    "\"event.dataset\"": "asa"
                }
            }
        },
        {
            "id": "filter_translate_227",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "[event.code]",
                "destination": "event",
                "dictionary_path": ""
            }
        },
        {
            "id": "filter_translate_229",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "[source.ip]",
                "destination": "threat",
                "dictionary_path": ""
            }
        },
        {
            "id": "filter_translate_231",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "[destination.ip]",
                "destination": "threat",
                "dictionary_path": ""
            }
        },
        {
            "id": "filter_translate_233",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "[event.severity]",
                "destination": "[log.level]",
                "dictionary": {
                    "\"0\"": "emergency",
                    "\"1\"": "alert",
                    "\"2\"": "critical",
                    "\"3\"": "error",
                    "\"4\"": "warning",
                    "\"5\"": "notification",
                    "\"6\"": "informational",
                    "\"7\"": "debug"
                }
            }
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_235",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "user": "",
                "password": "",
                "hosts": [
                    ""
                ],
                "pipeline": "asa",
                "index": "asa-1.2"
            }
        }
    ]
},test=False)
    print(z.components_to_logstash_config())



if __name__ == "__main__":
    main()