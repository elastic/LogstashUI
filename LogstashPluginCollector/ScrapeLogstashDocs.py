from bs4 import BeautifulSoup
import requests
import json
from threading import Thread

class ScrapeLogstashDocs:
    def __init__(self,document_sources):
        self.document_sources = document_sources
        self.plugin_data = {}

    def get_plugins(self):
        threads = []
        for document_source in self.document_sources:
            self.plugin_data[document_source] = {}
            threads.append(Thread(target=self.get_plugin_type_document, args=(self.document_sources[document_source], document_source)))
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]


    def get_plugin_type_document(self,document_source, plugin_type):
        print("=== Getting " + plugin_type + " plugins ===")
        response = requests.get(document_source)
        soup = BeautifulSoup(response.text, 'html.parser')
        plugin_table = soup.find_all(class_="table-wrapper")[0]
        table_data = plugin_table.find_all("td")
        table_data_split_by_3 = [table_data[i:i + 3] for i in range(0, len(table_data), 3)]
        for plugin_row in table_data_split_by_3:
            plugin_name = plugin_row[0].text
            plugin_link = plugin_row[0].find("a").get('href')
            #print(plugin_type)
            self.plugin_data[plugin_type][plugin_name] = {
                "name": plugin_name,
                "link": "https://elastic.co" +plugin_link,
                "description": plugin_row[1].text,
                "repo_link": plugin_row[2].find("a").get('href'),
                "options": {}
            }
            if plugin_type in ['input', 'filter', 'output', 'codec']:
                self.get_plugin_params(plugin_name, plugin_type)


        return soup

    def get_integration_plugin_params(self):
        print(" === Getting integration plugins params ===")
        response = requests.get(self.document_sources['integrations'])
        soup = BeautifulSoup(response.text, 'html.parser')
        all_tables = soup.find_all("table")

    def get_plugin_params(self, plugin_name, plugin_type):
        print(" === Getting " + plugin_name + " params ===")
        response = requests.get(self.plugin_data[plugin_type][plugin_name]['link'])
        soup = BeautifulSoup(response.text, 'html.parser')
        all_tables = soup.find_all("table")

        for table in all_tables:
            headers = table.find_all("th")
            if headers[0].text == "Setting" and len(headers) == 3:
                table_data = table.find_all("td")
                table_data_split_by_3 = [table_data[i:i + 3] for i in range(0, len(table_data), 3)]
                for table_row in table_data_split_by_3:
                    try:
                        self.plugin_data[plugin_type][plugin_name]['options'][table_row[0].text] = {
                            "setting": table_row[0].text,
                            "input_type": table_row[1].text,
                            "required": table_row[2].text,
                            "setting_link": table_row[0].find("a").get('href')
                        }
                    except Exception as e:
                        print(e, table_row)

    def save_json(self):
        with open("plugins.json", "w") as f:
            json.dump(self.plugin_data, f, indent=4)

def main():
    crawler = ScrapeLogstashDocs({
        "integrations":"https://www.elastic.co/docs/reference/logstash/plugins/plugin-integrations",
        "input":"https://www.elastic.co/docs/reference/logstash/plugins/input-plugins",
        "output":"https://www.elastic.co/docs/reference/logstash/plugins/output-plugins",
        "filter":"https://www.elastic.co/docs/reference/logstash/plugins/filter-plugins",
        "codec":"https://www.elastic.co/docs/reference/logstash/plugins/codec-plugins"
    })

    crawler.get_plugins()
    crawler.save_json()


if __name__ == "__main__":
    main()