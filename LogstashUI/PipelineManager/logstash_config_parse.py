from lark import Lark, Transformer, v_args
from typing import Dict, List, Any, Union
import json


################################ Logstash config to component JSON ################################
# Define the grammar for Logstash config
# Define the grammar for Logstash config
LOGSTASH_GRAMMAR = r"""
    ?start: section+

    section: section_type "{" [plugin+] "}"

    section_type: "input" -> input_section
               | "filter" -> filter_section
               | "output" -> output_section

    plugin: CNAME "{" [pair (","? pair)*] "}"

    pair: CNAME "=>" value

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
        plugins = items[1:]
        return {"type": section_type, "plugins": plugins}

    def input_section(self, _):
        return "input"

    def filter_section(self, _):
        return "filter"

    def output_section(self, _):
        return "output"

    def start(self, items):
        return list(items)


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

        for section in parsed:
            section_type = section['type']


            for plugin in section['plugins']:

                component = {
                    'id': f"{section_type}_{plugin['name']}_{component_count}",
                    'type': section_type,
                    "plugin": plugin['name'],
                    'config': plugin['settings']
                }
                component_count += 1
                data[section_type].append(component)
        return json.dumps(data, indent=4)

    except Exception as e:
        print(f"Error converting config to components: {str(e)}")
        return []



################################ Component JSON to Logstash config ################################

def components_to_logstash_config(component_dict):
    config = ""
    for section in component_dict['components']:
        config += section + " {\n"
        for plugin in component_dict['components'][section]:
            config += "\t" + plugin['plugin'] + " {\n"
            for plugin_config_name in plugin['config']:
                plugin_config_value = plugin['config'][plugin_config_name]

                print(plugin_config_name, plugin_config_value, type(plugin_config_value))
                if type(plugin_config_value) in [str, int, float]:
                    config += "\t\t" + plugin_config_name + " => " + plugin_config_value + "\n"
                elif type(plugin_config_value) is dict:
                    config += "\t\t" + plugin_config_name + " => {\n"

                    for dict_key in plugin_config_value:
                        config += "\t\t\t" + dict_key + " => " + plugin_config_value[dict_key] + "\n"

                    config += "\t\t}\n"
                elif type(plugin_config_value) is list:
                    #print("LIST", plugin_config, plugin['config'][plugin_config])
                    config += "\t\t" + plugin_config_name + " => " + json.dumps(plugin_config_value) + "\n"


            config += "\t}\n"

        config += "}\n"
    return config


def main():
#     z = logstash_config_to_components("""input {
#   jdbc {
#     jdbc_driver_library => "/usr/share/logstash/vendor/jar/jdbc/mysql-connector-j-9.3.0.jar"
#     jdbc_driver_class => "com.mysql.cj.jdbc.Driver"
#     jdbc_connection_string => "jdbc:mysql://${DB_HOST}:3306/semaphore" #<--- alter to correct DB format, everything after the / is the DB
#     jdbc_user => "${DB_USER}"
#     jdbc_password => "${DB_PASSWORD}"
#     schedule => "* * * * *"
#     statement => "select * from event"
#   }
# }
# filter {
#
# }
# output {
#   elasticsearch {
#     cloud_id => "${ELASTIC_CLOUD_ID}"
#     cloud_auth => "${ELASTIC_CLOUD_AUTH}"
#     index => "db-report-test" #<--- Adjust the index to whatever makes sense
#   }
# }""")

    z = components_to_logstash_config({'input': [{'id': 'input_jdbc_0', 'type': 'input', 'plugin': 'jdbc', 'config': {'jdbc_driver_library': '/usr/share/logstash/vendor/jar/jdbc/mysql-connector-j-9.3.0.jar', 'jdbc_driver_class': 'com.mysql.cj.jdbc.Driver', 'jdbc_connection_string': 'jdbc:mysql://${DB_HOST}:3306/semaphore', 'jdbc_user': '${DB_USER}', 'jdbc_password': '${DB_PASSWORD}', 'schedule': '* * * * *', 'statement': 'select * from event'}}], 'filter': [], 'output': [{'id': 'output_elasticsearch_1', 'type': 'output', 'plugin': 'elasticsearch', 'config': {'cloud_id': '${ELASTIC_CLOUD_ID}', 'cloud_auth': '${ELASTIC_CLOUD_AUTH}', 'index': 'db-report-test'}}]})

    import json
    print(z)

if __name__ == "__main__":
    main()