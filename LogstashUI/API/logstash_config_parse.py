from lark import Lark, Transformer, v_args
from typing import Dict, List, Any, Union
import json


################################ Logstash config to component JSON ################################
LOGSTASH_GRAMMAR = r"""
?start: section+

section: section_type "{" [statement+] "}"

statement: plugin | conditional

conditional: "if" condition "{" [statement+] "}" else_if_condition* [else_condition]
condition: CMP_OPERATORS
else_if_condition: "else" "if" condition "{" [statement+] "}"
else_condition: "else" "{" [statement+] "}"

CMP_OPERATORS: /[^\n{]+/  // Matches anything except newline and {

section_type: "input" -> input_section
            | "filter" -> filter_section
            | "output" -> output_section


plugin: CNAME "{" [pair (","? pair)* ] "}"


pair: (CNAME | ESCAPED_STRING) "=>" (CNAME | value)

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
%ignore WS
%ignore /#[^\n]*/
"""


class LogstashTransformer(Transformer):
    def string(self, s):
        return s[0][1:-1]  # Remove quotes
        
    def condition(self, items):
        return items[0].strip()
        
    def statement(self, items):
        return items[0]
        
    def conditional(self, items):
        result = {
            'type': 'conditional',
            'if_condition': items[0],
            'if_body': items[1] if len(items) > 1 else [],
            'else_ifs': [],
            'else_body': None
        }
        
        # Process else ifs and else
        i = 2
        while i < len(items):
            if isinstance(items[i], dict) and 'else_if_condition' in str(items[i]):
                # For else if, the next item is the body
                result['else_ifs'].append({
                    'condition': items[i],
                    'body': items[i+1] if i+1 < len(items) else []
                })
                i += 2
            else:
                # This is the else body
                result['else_body'] = items[i] if i < len(items) else []
                i += 1
                
        return result
        
    def else_if_condition(self, items):
        return {
            'type': 'else_if_condition',
            'condition': items[0],
            'body': items[1] if len(items) > 1 else []
        }
        
    def else_condition(self, items):
        return items[0] if items else []

    def number(self, n):
        return float(n[0]) if '.' in n[0] else int(n[0])

    def env_var(self, v):
        return {"type": "env_var", "value": v[0]}

    def array(self, items):
        return list(items)

    def hash(self, pairs):
        return dict(pairs)

    def pair(self, items):
        return (items[0], items[1])

    def plugin(self, items):
        name = items.pop(0)
        settings = {}
        for k, v in items:
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
                if isinstance(else_if['condition'], dict) and 'condition' in else_if['condition']:
                    condition = else_if['condition']['condition']
                else:
                    condition = str(else_if['condition'])
            
            # Process the plugins in the else if body
            elif_plugins, component_count = self._process_plugins(
                else_if.get('body', []), section_type, component_count
            )
            
            # Add to else_ifs list with proper structure
            if condition:
                else_ifs.append({
                    'condition': condition,
                    'plugins': elif_plugins
                })
        
        # Process else condition - ensure it's always an object with a plugins array
        else_plugins, component_count = self._process_plugins(
            cond.get('else_body', []), section_type, component_count
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

def components_to_logstash_config(component_dict, test=False):
    config = ""
    # "test" is used for simulating pipelines so that we can send input via stdin
    # and receive output via stdout
    if test:
        component_dict['components']['input'] = [{
            'id': 'stdin',
            'type': 'input',
            'plugin': 'stdin',
            'config': {
                "codec": "json"
            }
        }]
        component_dict['components']['output'] = [{
            'id': 'stdout',
            'type': 'output',
            'plugin': 'stdout',
            'config': {
                "codec": "json_lines"
            }
        }]
    for section in component_dict['components']:
        config += section + " {\n"

        # plugin_num used for running simulations
        plugin_num = 0
        for plugin in component_dict['components'][section]:

            # Setup testing
            if section == "filter" and test == True:
                config += f"\tif [plugin_num] >= {plugin_num} {{\n"
            config += f'\t{plugin["plugin"]} {{\n'
            for plugin_config_name in plugin['config']:
                plugin_config_value = plugin['config'][plugin_config_name]

                #print(plugin_config_name, plugin_config_value, type(plugin_config_value))
                if type(plugin_config_value) in [str, int, float]:
                    config += f'\t\t{plugin_config_name} => "{plugin_config_value}"\n'

                elif type(plugin_config_value) is dict:

                    config += f"\t\t{plugin_config_name} => {{\n"

                    for dict_key in plugin_config_value:
                        print(dict_key)
                        config += f'\t\t\t{dict_key} => "{plugin_config_value[dict_key]}"\n'



                    config += "\t\t}\n"
                elif type(plugin_config_value) is list:
                    #print("LIST", plugin_config, plugin['config'][plugin_config])
                    config += "\t\t" + plugin_config_name + " => " + json.dumps(plugin_config_value) + "\n"


            config += "\t}\n"
            if section == "filter" and test == True:
                config += "\t}\n"
            plugin_num += 1

        config += "}\n"
    #print(config)
    return config


def main():



    condition_output_no_filter = logstash_config_to_components("""    input { beats { port => 5044 } }
    output {
        if [type] == "apache" {
          pipeline { send_to => weblogs }
        } else if [type] == "system" {
          pipeline { send_to => syslog }
        } else {
          pipeline { send_to => fallback }
        }
    }""")
    print(condition_output_no_filter)

    #z = components_to_logstash_config({'input': [{'id': 'input_jdbc_0', 'type': 'input', 'plugin': 'jdbc', 'config': {'jdbc_driver_library': '/usr/share/logstash/vendor/jar/jdbc/mysql-connector-j-9.3.0.jar', 'jdbc_driver_class': 'com.mysql.cj.jdbc.Driver', 'jdbc_connection_string': 'jdbc:mysql://${DB_HOST}:3306/semaphore', 'jdbc_user': '${DB_USER}', 'jdbc_password': '${DB_PASSWORD}', 'schedule': '* * * * *', 'statement': 'select * from event'}}], 'filter': [], 'output': [{'id': 'output_elasticsearch_1', 'type': 'output', 'plugin': 'elasticsearch', 'config': {'cloud_id': '${ELASTIC_CLOUD_ID}', 'cloud_auth': '${ELASTIC_CLOUD_AUTH}', 'index': 'db-report-test'}}]})
    #print(z)

if __name__ == "__main__":
    main()