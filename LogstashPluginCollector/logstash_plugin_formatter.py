import csv
import json

CSV_FILE = "logstash_plugin_params.csv"
OUTPUT_FILE = "logstash_plugin_params.json"

plugin_data = {
    "output": {},
    "input": {},
    "filter": {}
}

with open(CSV_FILE, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)

    for row in reader:
        plugin_type = row["type"]
        plugin_friendly_name = row["name"].split("-")[0]
        plugin_version = row["name"].split("-")[1]
        param = row["param"]
        validate = row["validate"] or None
        default = row["default"] or None
        required = row["required"].lower() == "true" if row["required"] else None

        if plugin_friendly_name not in plugin_data[plugin_type]:
            plugin_data[plugin_type][plugin_friendly_name] = {
                "name": plugin_friendly_name,
                "version": plugin_version,
                "params": {}
            }

        plugin_data[plugin_type][plugin_friendly_name]["params"][param] = {
            "name": param,
            "datatype": validate,
            "default": default,
            "required": required
        }

with open(OUTPUT_FILE, "w") as f:
    json.dump(plugin_data, f, indent=4)

