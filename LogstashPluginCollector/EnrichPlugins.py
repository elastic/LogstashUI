
import json
from bs4 import BeautifulSoup

class EnrichPlugins:
    def __init__(self):
        self.file_path = "plugins.json"

    def get_plugin_params(self, table_data, plugin_name, plugin_type):
        soup = BeautifulSoup(table_data, 'html.parser')
        all_tables = soup.find_all("table")

        for table in all_tables:
            headers = table.find_all("th")
            if headers[0].text == "Setting" and len(headers) == 3:
                table_data = table.find_all("td")
                table_data_split_by_3 = [table_data[i:i + 3] for i in range(0, len(table_data), 3)]
                for table_row in table_data_split_by_3:
                    try:
                        self.plugins[plugin_type][plugin_name]['options'][table_row[0].text] = {
                            "setting": table_row[0].text,
                            "input_type": table_row[1].text,
                            "required": table_row[2].text,
                            "setting_link": table_row[0].find("a").get('href')
                        }
                    except Exception as e:
                        print("ERROR", e, table_row)

    def start(self):
        f = open(self.file_path, "r")
        self.plugins = json.loads(f.read())
        f.close()

        broken_plugins = self._look_for_broken_plugins()
        if broken_plugins:
            # This is basically a bandage to resolve issues with how our docs are shaped
            self._fix_broken_plugins(broken_plugins)

        else:
            self._enrich_important_fields()

        f = open("enriched_plugins.json", "w+")
        f.write(json.dumps(self.plugins, indent=4))
        f.close()


    def _fix_broken_plugins(self, broken_plugins):
        for plugin in broken_plugins:
            section = plugin['section']
            plugin = plugin['plugin']

            if section == "integrations":
                if plugin in ["aws", "kafka", "logstash", "rabbitmq", "snmp"]:
                    # Because all of the plugins are listed in their respective input/output/filter
                    del self.plugins[section][plugin]
                    continue

                if plugin == "jdbc":
                    # Need to re-fetch these because they DON'T appear in the plugin list

                    print(f"Adding these manually {section}-{plugin}")

                    self.plugins['filter']['jdbc_static'] = {
                        "name": "jdbc_static",
                        "link": "https://www.elastic.co/docs/reference/logstash/plugins/plugins-filters-jdbc_static",
                        "description": "This filter enriches events with data pre-loaded from a remote database.",
                        "options":{}
                    }
                    copypaste = '''<div class="table-wrapper">
<table>
<thead>
<tr>
<th style="text-align: left;">Setting</th>
<th style="text-align: left;">Input type</th>
<th style="text-align: left;">Required</th>
</tr>
</thead>
<tbody>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-jdbc_connection_string"><code>jdbc_connection_string</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#string" hx-select-oob="#content-container,#toc-nav" preload="mousedown">string</a></td>
<td style="text-align: left;">Yes</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-jdbc_driver_class"><code>jdbc_driver_class</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#string" hx-select-oob="#content-container,#toc-nav" preload="mousedown">string</a></td>
<td style="text-align: left;">Yes</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-jdbc_driver_library"><code>jdbc_driver_library</code></a></td>
<td style="text-align: left;">a valid filesystem path</td>
<td style="text-align: left;">No</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-jdbc_password"><code>jdbc_password</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#password" hx-select-oob="#content-container,#toc-nav" preload="mousedown">password</a></td>
<td style="text-align: left;">No</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-jdbc_user"><code>jdbc_user</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#string" hx-select-oob="#content-container,#toc-nav" preload="mousedown">string</a></td>
<td style="text-align: left;">No</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-tag_on_failure"><code>tag_on_failure</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#array" hx-select-oob="#content-container,#toc-nav" preload="mousedown">array</a></td>
<td style="text-align: left;">No</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-tag_on_default_use"><code>tag_on_default_use</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#array" hx-select-oob="#content-container,#toc-nav" preload="mousedown">array</a></td>
<td style="text-align: left;">No</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-staging_directory"><code>staging_directory</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#string" hx-select-oob="#content-container,#toc-nav" preload="mousedown">string</a></td>
<td style="text-align: left;">No</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-loader_schedule"><code>loader_schedule</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#string" hx-select-oob="#content-container,#toc-nav" preload="mousedown">string</a></td>
<td style="text-align: left;">No</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-loaders"><code>loaders</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#array" hx-select-oob="#content-container,#toc-nav" preload="mousedown">array</a></td>
<td style="text-align: left;">No</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-local_db_objects"><code>local_db_objects</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#array" hx-select-oob="#content-container,#toc-nav" preload="mousedown">array</a></td>
<td style="text-align: left;">No</td>
</tr>
<tr>
<td style="text-align: left;"><a href="#plugins-filters-jdbc_static-local_lookups"><code>local_lookups</code></a></td>
<td style="text-align: left;"><a href="/docs/reference/logstash/plugins/value-types#array" hx-select-oob="#content-container,#toc-nav" preload="mousedown">array</a></td>
<td style="text-align: left;">No</td>
</tr>
</tbody>
</table>
</div>'''
                    self.get_plugin_params(copypaste,'jdbc_static','filter')

                    continue

                del self.plugins[section]

            elif section == "input":
                if plugin == "s3-sns-sqs":

                    print(f"Converting copy/paste from: https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc")
                    copypaste ='''<table>
<thead>
<tr>
<th>Setting</th>
<th>Input type</th>
<th>Required</th>
</tr>
</thead>
<tbody>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-queue"><code>queue</code></a></p></td>
<td><p dir="auto">string</p></td>
<td><p dir="auto">Yes</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-queue_owner_aws_account_id"><code>queue_owner_aws_account_id</code></a></p></td>
<td><p dir="auto"><a href="#string">string</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-s3_options_by_bucket"><code>s3_options_by_bucket</code></a></p></td>
<td><p dir="auto"><a href="#array">array</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-s3_default_options"><code>s3_default_options</code></a></p></td>
<td><p dir="auto"><a href="#hash">hash</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-s3_role_session_name"><code>s3_role_session_name</code></a></p></td>
<td><p dir="auto"><a href="#string">string</a></p></td>
<td><p dir="auto">yes</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-delete_on_success"><code>delete_on_success</code></a></p></td>
<td><p dir="auto"><a href="#boolean">boolean</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-include_object_properties"><code>include_object_properties</code></a></p></td>
<td><p dir="auto"><a href="#array">array</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-from_sns"><code>from_sns</code></a></p></td>
<td><p dir="auto"><a href="#boolean">boolean</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-sqs_skip_delete"><code>sqs_skip_delete</code></a></p></td>
<td><p dir="auto"><a href="#boolean">boolean</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-sqs_delete_on_failure"><code>sqs_delete_on_failure</code></a></p></td>
<td><p dir="auto"><a href="#boolean">boolean</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-temporary_directory"><code>temporary_directory</code></a></p></td>
<td><p dir="auto"><a href="#string">string</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-consumer_threads"><code>consumer_threads</code></a></p></td>
<td><p dir="auto"><a href="#number">number</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-visibility_timeout"><code>visibility_timeout</code></a></p></td>
<td><p dir="auto"><a href="#number">number</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-sqs_wait_time_seconds"><code>sqs_wait_time_seconds</code></a></p></td>
<td><p dir="auto"><a href="#number">number</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/cherweg/logstash-input-s3-sns-sqs/blob/master/docs/index.asciidoc#plugins-inputs-logstash-input-s3-sns-sqs-max_processing_time"><code>max_processing_time</code></a></p></td>
<td><p dir="auto"><a href="#number">number</a></p></td>
<td><p dir="auto">No</p></td>
</tr>
</tbody>
</table>'''

                    self.get_plugin_params(copypaste, plugin, section)

                    continue
            elif section == "output":
                if plugin == "dynatrace":
                    print(f"Converting copy/paste from: https://github.com/dynatrace-oss/logstash-output-dynatrace/blob/main/docs/index.asciidoc")
                    copypaste = '''<table><thead>
<tr>
<th>Setting</th>
<th>Input type</th>
<th>Required</th>
</tr>
</thead>
<tbody>
<tr>
<td><p dir="auto"><a href="https://github.com/dynatrace-oss/logstash-output-dynatrace/blob/main/docs/index.asciidoc#plugins-outputs-dynatrace-ingest_endpoint_url"><code>ingest_endpoint_url</code></a></p></td>
<td><p dir="auto">string</p></td>
<td><p dir="auto">Yes</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/dynatrace-oss/logstash-output-dynatrace/blob/main/docs/index.asciidoc#plugins-outputs-dynatrace-api_key"><code>api_key</code></a></p></td>
<td><p dir="auto">string</p></td>
<td><p dir="auto">Yes</p></td>
</tr>
<tr>
<td><p dir="auto"><a href="https://github.com/dynatrace-oss/logstash-output-dynatrace/blob/main/docs/index.asciidoc#plugins-outputs-dynatrace-ssl_verify_none"><code>ssl_verify_none</code></a></p></td>
<td><p dir="auto">boolean</p></td>
<td><p dir="auto">No</p></td>
</tr>
</tbody>
</table>'''
                    self.get_plugin_params(copypaste, plugin, section)
                    continue
            elif section == "filter":
                if plugin == "threats_classifier":
                    print(f"Hard coded info for {section}-{plugin}, Fetch from here: https://github.com/empow/logstash-filter-threats_classifier/blob/master/README.md")

                    self.plugins[section][plugin]['options'] = {
                        "username": {
                            "setting": "username",
                            "input_type": "string",
                            "required": "Yes",
                            "setting_link": "https://github.com/empow/logstash-filter-threats_classifier/blob/master/README.md"
                        },
                        "password": {
                            "setting": "password",
                            "input_type": "string",
                            "required": "Yes",
                            "setting_link": "https://github.com/empow/logstash-filter-threats_classifier/blob/master/README.md"
                        }
                    }
                    continue

                if plugin == "wurfl_device_detection":
                    print(f"Hard coding {section}-{plugin} Fetch from here: https://github.com/WURFL/logstash-filter-wurfl_device_detection/blob/master/README.md")
                    self.plugins[section][plugin]['options'] = {
                        "source": {
                            "setting": "source",
                            "input_type": "string",
                            "required": "No",
                            "settings_link": "https://github.com/WURFL/logstash-filter-wurfl_device_detection/blob/master/README.md"
                        },
                        "cache_size": {
                            "setting": "cache_size",
                            "input_type": "number",
                            "required": "No",
                            "settings_link": "https://github.com/WURFL/logstash-filter-wurfl_device_detection/blob/master/README.md"
                        },
                        "inject_wurfl_id": {
                            "setting": "inject_wurfl_id",
                            "input_type": "boolean",
                            "required": "No",
                            "settings_link": "https://github.com/WURFL/logstash-filter-wurfl_device_detection/blob/master/README.md"
                        },
                        "inject_wurfl_info": {
                            "setting": "inject_wurfl_info",
                            "input_type": "boolean",
                            "required": "No",
                            "settings_link": "https://github.com/WURFL/logstash-filter-wurfl_device_detection/blob/master/README.md"
                        },
                        "inject_wurfl_api_version": {
                            "setting": "inject_wurfl_api_version",
                            "input_type": "boolean",
                            "required": "No",
                            "settings_link": "https://github.com/WURFL/logstash-filter-wurfl_device_detection/blob/master/README.md"
                        },
                        "scheme": {
                            "setting": "scheme",
                            "input_type": "string",
                            "required": "No",
                            "settings_link": "https://github.com/WURFL/logstash-filter-wurfl_device_detection/blob/master/README.md"
                        },
                        "host": {
                            "setting": "host",
                            "input_type": "string",
                            "required": "No",
                            "settings_link": "https://github.com/WURFL/logstash-filter-wurfl_device_detection/blob/master/README.md"
                        },
                        "port": {
                            "setting": "port",
                            "input_type": "string",
                            "required": "No",
                            "settings_link": "https://github.com/WURFL/logstash-filter-wurfl_device_detection/blob/master/README.md"
                        }
                    }
                    continue

            elif section == "codec":
                if plugin in ["dots", "jdots"]:
                    print(f"No need to edit codec {plugin} - no values")
                    continue





            print(section, plugin)

    def _look_for_broken_plugins(self):
        broken_plugins = []
        for section in self.plugins:
            for plugin in self.plugins[section]:
                if not self.plugins[section][plugin]['options']:
                    broken_plugins.append({"section": section, "plugin": plugin})

        return broken_plugins

    def _enrich_important_fields(self):
        pass



def main():
    enrich = EnrichPlugins()
    enrich.start()

if __name__ == "__main__":
    main()