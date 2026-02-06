
import json
from bs4 import BeautifulSoup

class EnrichPlugins:
    def __init__(self):
        self.file_path = "plugins.json"
        self.default_plugins = """logstash-codec-avro
logstash-codec-cef
logstash-codec-collectd
logstash-codec-dots
logstash-codec-edn
logstash-codec-edn_lines
logstash-codec-es_bulk
logstash-codec-fluent
logstash-codec-graphite
logstash-codec-json
logstash-codec-json_lines
logstash-codec-line
logstash-codec-msgpack
logstash-codec-multiline
logstash-codec-netflow
logstash-codec-plain
logstash-codec-rubydebug
logstash-filter-aggregate
logstash-filter-anonymize
logstash-filter-cidr
logstash-filter-clone
logstash-filter-csv
logstash-filter-date
logstash-filter-de_dot
logstash-filter-dissect
logstash-filter-dns
logstash-filter-drop
logstash-filter-elastic_integration
logstash-filter-elasticsearch
logstash-filter-fingerprint
logstash-filter-geoip
logstash-filter-grok
logstash-filter-http
logstash-filter-json
logstash-filter-kv
logstash-filter-memcached
logstash-filter-metrics
logstash-filter-mutate
logstash-filter-prune
logstash-filter-ruby
logstash-filter-sleep
logstash-filter-split
logstash-filter-syslog_pri
logstash-filter-throttle
logstash-filter-translate
logstash-filter-truncate
logstash-filter-urldecode
logstash-filter-useragent
logstash-filter-uuid
logstash-filter-xml
logstash-input-azure_event_hubs
logstash-input-beats
logstash-input-elastic_agent
logstash-input-couchdb_changes
logstash-input-dead_letter_queue
logstash-input-elastic_serverless_forwarder
logstash-input-elasticsearch
logstash-input-exec
logstash-input-file
logstash-input-ganglia
logstash-input-gelf
logstash-input-generator
logstash-input-graphite
logstash-input-heartbeat
logstash-input-http
logstash-input-http_poller
logstash-input-jms
logstash-input-pipe
logstash-input-redis
logstash-input-stdin
logstash-input-syslog
logstash-input-tcp
logstash-input-twitter
logstash-input-udp
logstash-input-unix
logstash-integration-aws
logstash-codec-cloudfront
logstash-codec-cloudtrail
logstash-input-cloudwatch
logstash-input-s3
logstash-input-sqs
logstash-output-cloudwatch
logstash-output-s3
logstash-output-sns
logstash-output-sqs
logstash-integration-jdbc
logstash-input-jdbc
logstash-filter-jdbc_streaming
logstash-filter-jdbc_static
logstash-integration-kafka
logstash-input-kafka
logstash-output-kafka
logstash-integration-logstash
logstash-input-logstash
logstash-output-logstash
logstash-integration-rabbitmq
logstash-input-rabbitmq
logstash-output-rabbitmq
logstash-integration-snmp
logstash-input-snmp
logstash-input-snmptrap
logstash-output-csv
logstash-output-elasticsearch
logstash-output-email
logstash-output-file
logstash-output-graphite
logstash-output-http
logstash-output-lumberjack
logstash-output-nagios
logstash-output-null
logstash-output-pipe
logstash-output-redis
logstash-output-stdout
logstash-output-tcp
logstash-output-udp
logstash-output-webhdfs
logstash-patterns-core"""
        self.default_plugins_dict = {}
        self.plugins = {}
        self.important_fields = {
  "input": {
    "azure_event_hubs": [
      "event_hub_connections",
      "storage_connection",
      "storage_container",
      "consumer_group",
      "codec",
      "tags",
      "type"
    ],

    "beats": [
      "port",
      "host",
      "ssl_certificate",
      "ssl_key",
      "ssl_enabled",
      "client_inactivity_timeout",
      "codec",
      "tags",
      "type"
    ],
    "cloudwatch": [
      "region",
      "namespace",
      "metrics",
      "filters",
      "access_key_id",
      "secret_access_key",
      "codec",
      "tags"
    ],
    "couchdb_changes": [
      "db",
      "host",
      "port",
      "username",
      "password",
      "codec"
    ],
    "dead_letter_queue": [
      "path",
      "pipeline_id",
      "codec"
    ],
    "elastic_agent": [
      "port",
      "host",
      "ssl_certificate",
      "ssl_key",
      "ssl_enabled",
      "codec",
      "tags"
    ],
    "elastic_serverless_forwarder": [
      "host",
      "port",
      "auth_basic_username",
      "auth_basic_password",
      "ssl",
      "tags"
    ],
    "elasticsearch": [
      "hosts",
      "cloud_id",
      "cloud_auth",
      "api_key",
      "user",
      "password",
      "index",
      "query",
      "schedule",
      "codec",
      "tags"
    ],
    "exec": [
      "command",
      "interval",
      "codec"
    ],
    "file": [
      "path",
      "start_position",
      "sincedb_path",
      "exclude",
      "ignore_older",
      "close_older",
      "codec",
      "tags",
      "type"
    ],
    "ganglia": [
      "host",
      "port",
      "codec"
    ],
    "gelf": [
      "host",
      "port",
      "codec"
    ],
    "generator": [
      "message",
      "lines",
      "count",
      "codec"
    ],
    "github": [
      "port",
      "secret_token",
      "codec"
    ],
    "google_cloud_storage": [
      "bucket_id",
      "json_key_file",
      "file_matches",
      "interval",
      "codec"
    ],
    "google_pubsub": [
      "project_id",
      "topic",
      "subscription",
      "json_key_file",
      "codec"
    ],
    "graphite": [
      "host",
      "port",
      "codec"
    ],
    "heartbeat": [
      "interval",
      "message",
      "codec"
    ],
    "http": [
      "host",
      "port",
      "ssl_certificate",
      "ssl_key",
      "ssl_enabled",
      "codec",
      "tags"
    ],
    "http_poller": [
      "urls",
      "schedule",
      "request_timeout",
      "codec",
      "metadata_target"
    ],
    "imap": [
      "host",
      "user",
      "password",
      "folder",
      "check_interval",
      "codec"
    ],
    "irc": [
      "host",
      "channels",
      "nick",
      "codec"
    ],
    "java_generator": [
      "message",
      "count",
      "codec"
    ],
    "java_stdin": [
      "codec"
    ],
    "jdbc": [
      "jdbc_driver_library",
      "jdbc_driver_class",
      "jdbc_connection_string",
      "jdbc_user",
      "jdbc_password",
      "statement",
      "schedule",
      "tracking_column",
      "use_column_value",
      "codec"
    ],
    "jms": [
      "destination",
      "broker_url",
      "username",
      "password",
      "codec"
    ],
    "jmx": [
      "path",
      "polling_frequency",
      "codec"
    ],
    "kafka": [
      "bootstrap_servers",
      "topics",
      "group_id",
      "client_id",
      "consumer_threads",
      "decorate_events",
      "codec",
      "tags"
    ],
    "kinesis": [
      "kinesis_stream_name",
      "region",
      "codec"
    ],
    "log4j": [
      "host",
      "port",
      "codec"
    ],
    "logstash": [
      "host",
      "port",
      "ssl_enabled",
      "tags"
    ],
    "lumberjack": [
      "host",
      "port",
      "ssl_certificate",
      "ssl_key",
      "codec"
    ],
    "meetup": [
      "meetupkey",
      "urlname",
      "codec"
    ],
    "pipe": [
      "command",
      "codec"
    ],
    "puppet_facter": [
      "host",
      "port",
      "interval",
      "codec"
    ],
    "rabbitmq": [
      "host",
      "port",
      "queue",
      "exchange",
      "user",
      "password",
      "durable",
      "codec",
      "tags"
    ],
    "redis": [
      "host",
      "port",
      "data_type",
      "key",
      "password",
      "db",
      "codec"
    ],
    "relp": [
      "host",
      "port",
      "codec"
    ],
    "rss": [
      "url",
      "interval",
      "codec"
    ],
    "s3": [
      "bucket",
      "region",
      "access_key_id",
      "secret_access_key",
      "prefix",
      "interval",
      "codec",
      "tags"
    ],
    "s3-sns-sqs": [
      "queue",
      "region",
      "access_key_id",
      "secret_access_key"
    ],
    "salesforce": [
      "username",
      "password",
      "security_token",
      "client_id",
      "client_secret",
      "sfdc_object_name",
      "codec"
    ],
    "snmp": [
      "hosts",
      "get",
      "walk",
      "interval",
      "codec",
      "security_level",
      "priv_protocol",
      "priv_pass",
      "auth_protocol",
      "auth_pass"
    ],
    "snmptrap": [
      "host",
      "port",
      "community",
      "codec"
    ],
    "sqlite": [
      "path",
      "codec"
    ],
    "sqs": [
      "queue",
      "region",
      "access_key_id",
      "secret_access_key",
      "codec",
      "tags"
    ],
    "stdin": [
      "codec"
    ],
    "stomp": [
      "destination",
      "host",
      "port",
      "user",
      "password",
      "codec"
    ],
    "syslog": [
      "host",
      "port",
      "codec",
      "tags"
    ],
    "tcp": [
      "host",
      "port",
      "mode",
      "ssl_enabled",
      "ssl_certificate",
      "ssl_key",
      "codec",
      "tags"
    ],
    "twitter": [
      "consumer_key",
      "consumer_secret",
      "oauth_token",
      "oauth_token_secret",
      "keywords",
      "codec"
    ],
    "udp": [
      "host",
      "port",
      "codec",
      "tags"
    ],
    "unix": [
      "path",
      "codec"
    ],
    "varnishlog": [
      "codec"
    ],
    "websocket": [
      "url",
      "codec"
    ],
    "wmi": [
      "host",
      "query",
      "interval",
      "codec"
    ],
    "xmpp": [
      "host",
      "user",
      "password",
      "rooms",
      "codec"
    ]
  },
  "filter": {
    "age": [
      "target"
    ],
    "aggregate": [
      "task_id",
      "code",
      "map_action",
      "timeout"
    ],
    "alter": [
      "coalesce",
      "condrewrite"
    ],
    "bytes": [
      "source",
      "target"
    ],
    "cidr": [
      "address",
      "network"
    ],
    "cipher": [
      "algorithm",
      "mode",
      "key",
      "source",
      "target"
    ],
    "clone": [
      "clones"
    ],
    "csv": [
      "source",
      "separator",
      "columns",
      "target"
    ],
    "date": [
      "match",
      "target",
      "timezone"
    ],
    "de_dot": [
      "separator"
    ],
    "dissect": [
      "mapping"
    ],
    "dns": [
      "resolve",
      "action"
    ],
    "drop": [
      "percentage"
    ],
    "elapsed": [
      "start_tag",
      "end_tag",
      "unique_id_field"
    ],
    "elastic_integration": [
      "hosts",
      "cloud_id",
      "cloud_auth",
      "api_key",
      "username",
      "password",
      "pipeline_name"
    ],
    "elasticsearch": [
      "hosts",
      "cloud_id",
      "cloud_auth",
      "api_key",
      "user",
      "password",
      "index",
      "query",
      "fields",
      "target"
    ],
    "environment": [
      "add_metadata_from_env"
    ],
    "extractnumbers": [
      "source"
    ],
    "fingerprint": [
      "source",
      "target",
      "method"
    ],
    "geoip": [
      "source",
      "target",
      "database"
    ],
    "grok": [
      "match",
      "pattern_definitions",
      "patterns_dir"
    ],
    "http": [
      "url",
      "verb",
      "headers",
      "body",
      "target_body",
      "target_headers"
    ],
    "i18n": [
      "transliterate"
    ],
    "java_uuid": [
      "target"
    ],
    "jdbc_streaming": [
      "jdbc_driver_library",
      "jdbc_driver_class",
      "jdbc_connection_string",
      "jdbc_user",
      "jdbc_password",
      "statement",
      "parameters",
      "target"
    ],
    "json": [
      "source",
      "target"
    ],
    "json_encode": [
      "source",
      "target"
    ],
    "kv": [
      "source",
      "field_split",
      "value_split",
      "target"
    ],
    "memcached": [
      "hosts",
      "get",
      "set"
    ],
    "metricize": [
      "metrics"
    ],
    "metrics": [
      "meter",
      "timer",
      "flush_interval"
    ],
    "mutate": [
      "convert",
      "rename",
      "replace",
      "gsub",
      "split",
      "join",
      "merge",
      "lowercase",
      "uppercase",
      "strip",
      "remove_field",
      "add_field"
    ],
    "prune": [
      "whitelist_names",
      "blacklist_names"
    ],
    "range": [
      "ranges"
    ],
    "ruby": [
      "code"
    ],
    "sleep": [
      "time"
    ],
    "split": [
      "field",
      "terminator"
    ],
    "syslog_pri": [
      "syslog_pri_field_name"
    ],
    "threats_classifier": [
      "username",
      "password"
    ],
    "throttle": [
      "key",
      "period",
      "max_age"
    ],
    "tld": [
      "source"
    ],
    "translate": [
      "field",
      "destination",
      "dictionary",
      "dictionary_path",
      "fallback"
    ],
    "truncate": [
      "fields",
      "length_bytes"
    ],
    "urldecode": [
      "field"
    ],
    "useragent": [
      "source",
      "target"
    ],
    "uuid": [
      "target"
    ],
    "wurfl_device_detection": [
      "source"
    ],
    "xml": [
      "source",
      "target",
      "xpath"
    ],
    "jdbc_static": [
      "jdbc_connection_string",
      "jdbc_driver_class",
      "jdbc_driver_library",
      "jdbc_user",
      "jdbc_password",
      "loaders",
      "local_lookups"
    ]
  },
  "output": {
    "boundary": [
      "api_key",
      "org_id"
    ],
    "circonus": [
      "api_token",
      "app_name"
    ],
    "cloudwatch": [
      "namespace",
      "region",
      "access_key_id",
      "secret_access_key"
    ],
    "csv": [
      "path",
      "fields"
    ],
    "datadog": [
      "api_key",
      "title",
      "text"
    ],
    "datadog_metrics": [
      "api_key",
      "metric_name",
      "metric_type"
    ],
    "dynatrace": [
      "ingest_endpoint_url",
      "api_key"
    ],
    "elastic_workplace_search": [
      "url",
      "source",
      "access_token"
    ],
    "elasticsearch": [
      "hosts",
      "cloud_id",
      "cloud_auth",
      "api_key",
      "user",
      "password",
      "index",
      "data_stream",
      "data_stream_type",
      "data_stream_dataset",
      "data_stream_namespace",
      "pipeline",
      "document_id",
      "action",
      "ilm_enabled",
      "ilm_rollover_alias",
      "ilm_policy"
    ],
    "email": [
      "to",
      "from",
      "subject",
      "body",
      "address"
    ],
    "exec": [
      "command"
    ],
    "file": [
      "path"
    ],
    "ganglia": [
      "host",
      "port",
      "metric"
    ],
    "gelf": [
      "host",
      "port"
    ],
    "google_bigquery": [
      "project_id",
      "dataset",
      "json_key_file"
    ],
    "google_cloud_storage": [
      "bucket",
      "json_key_file"
    ],
    "google_pubsub": [
      "project_id",
      "topic",
      "json_key_file"
    ],
    "graphite": [
      "host",
      "port",
      "metrics"
    ],
    "graphtastic": [
      "host",
      "port",
      "metrics"
    ],
    "http": [
      "url",
      "http_method",
      "format",
      "content_type"
    ],
    "influxdb": [
      "host",
      "port",
      "db",
      "measurement",
      "user",
      "password"
    ],
    "irc": [
      "host",
      "channels"
    ],
    "java_stdout": [
      "codec"
    ],
    "juggernaut": [
      "channels",
      "host"
    ],
    "kafka": [
      "bootstrap_servers",
      "topic_id",
      "codec"
    ],
    "librato": [
      "account_id",
      "api_token"
    ],
    "loggly": [
      "key"
    ],
    "logstash": [
      "hosts",
      "ssl_enabled"
    ],
    "lumberjack": [
      "hosts",
      "port",
      "ssl_certificate"
    ],
    "metriccatcher": [
      "host",
      "port"
    ],
    "mongodb": [
      "uri",
      "database",
      "collection"
    ],
    "nagios": [
      "commandfile"
    ],
    "nagios_nsca": [
      "host",
      "nagios_host",
      "nagios_service"
    ],
    "opentsdb": [
      "host",
      "port",
      "metrics"
    ],
    "pagerduty": [
      "service_key",
      "description"
    ],
    "pipe": [
      "command"
    ],
    "rabbitmq": [
      "host",
      "exchange",
      "exchange_type",
      "key",
      "user",
      "password"
    ],
    "redis": [
      "host",
      "port",
      "data_type",
      "key"
    ],
    "redmine": [
      "url",
      "token",
      "project_id"
    ],
    "riak": [
      "nodes",
      "bucket"
    ],
    "riemann": [
      "host",
      "port"
    ],
    "s3": [
      "bucket",
      "region",
      "access_key_id",
      "secret_access_key",
      "prefix"
    ],
    "sink": [],
    "sns": [
      "arn",
      "region",
      "access_key_id",
      "secret_access_key"
    ],
    "solr_http": [
      "solr_url"
    ],
    "sqs": [
      "queue",
      "region",
      "access_key_id",
      "secret_access_key"
    ],
    "statsd": [
      "host",
      "port",
      "namespace"
    ],
    "stdout": [
      "codec"
    ],
    "stomp": [
      "destination",
      "host",
      "port"
    ],
    "syslog": [
      "host",
      "port",
      "protocol"
    ],
    "tcp": [
      "host",
      "port",
      "mode"
    ],
    "timber": [
      "api_key"
    ],
    "udp": [
      "host",
      "port"
    ],
    "webhdfs": [
      "host",
      "port",
      "path",
      "user"
    ],
    "websocket": [
      "host",
      "port"
    ],
    "xmpp": [
      "host",
      "user",
      "password",
      "message"
    ],
    "zabbix": [
      "zabbix_server_host",
      "zabbix_host",
      "zabbix_key"
    ]
  },
  "codec": {
    "avro": [
      "schema_uri"
    ],
    "cef": [
      "vendor",
      "product",
      "version",
      "signature",
      "name",
      "severity"
    ],
    "cloudfront": [],
    "cloudtrail": [],
    "collectd": [
      "typesdb"
    ],
    "csv": [
      "columns",
      "separator"
    ],
    "dots": [],
    "edn": [],
    "edn_lines": [],
    "es_bulk": [],
    "fluent": [],
    "graphite": [
      "metrics_format"
    ],
    "gzip_lines": [],
    "java_line": [
      "format"
    ],
    "java_plain": [
      "format"
    ],
    "jdots": [],
    "json": [],
    "json_lines": [],
    "line": [
      "format"
    ],
    "msgpack": [],
    "multiline": [
      "pattern",
      "what",
      "negate"
    ],
    "netflow": [
      "versions"
    ],
    "nmap": [],
    "plain": [
      "format"
    ],
    "protobuf": [
      "class_name",
      "include_path"
    ],
    "rubydebug": []
  }
}


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

    def _optimize_datatypes(self):

      print("Optimizing datatypes")
      ## Section converts arrays that are composed of hashes into the correct format
      should_be_array_of_hashes = {
        "input": {
          "snmp": {
            "hosts": {
              "host": {
                "type": "string",
              },
              "community": {
                "type": "string",
              },
              "version": {
                "type": "string",
              },
              "retries": {
                "type": "number"
              },
              "timeout": {
                "type": "number"
              }
            }
          }
        }
      }

      for section in should_be_array_of_hashes:
        for plugin in should_be_array_of_hashes[section]:
          for option in should_be_array_of_hashes[section][plugin]:
            self.plugins[section][plugin]['options'][option]['input_type'] = "array_of_hashes"
            self.plugins[section][plugin]['options'][option]['options'] = should_be_array_of_hashes[section][plugin][option]

      # Section detects and converts more generic data types
      for section in self.plugins:
        for plugin in self.plugins[section]:
          for option in self.plugins[section][plugin]['options']:
            input_type = self.plugins[section][plugin]['options'][option]['input_type']
            if "string one of" in input_type or "string, one of" in input_type:
              options = input_type.split(" one of ")[1].strip()

              if "nil" in options:
                options = options.replace("nil", '"nil"')

              if "IPV4" in options:
                options = options.replace("IPV4", '"IPV4')


              try:
                self.plugins[section][plugin]['options'][option]['options'] = json.loads(options)
              except Exception as e:

                print("ERROR", e)
                print("THIS --->", self.plugins[section][plugin]['options'][option]['input_type'].split("one of ")[1])
              self.plugins[section][plugin]['options'][option]['input_type'] = "dropdown"
              #self.plugins[section][plugin]['options'][option]['options'] = json.loads(input_type.split("one of")[1].strip())
            elif "boolean" in input_type:
              self.plugins[section][plugin]['options'][option]['input_type'] = "boolean"
              self.plugins[section][plugin]['options'][option]['options'] = ["true", "false"]

            elif input_type == "bytes":
              self.plugins[section][plugin]['options'][option]['input_type'] = "number"
            elif "list of path" in input_type or "list of string" in input_type:
              self.plugins[section][plugin]['options'][option]['input_type'] = "array"
            elif input_type in ['string', 'number', 'array', "hash", "City or ASN", "password", "path", "a valid filesystem path", "codec", "uri"]:
              continue

            else:
              print("Unaccounted for types", input_type)


    def _add_missing(self):
        missing_plugins = {
            "input": {
                "pipeline": {
                    "name": "pipeline",
                    "link": "https://www.elastic.co/docs/reference/logstash/pipeline-to-pipeline",
                    "description": "receives input from another pipeline",
                    "repo_link": "https://www.elastic.co/docs/reference/logstash/pipeline-to-pipeline",
                    "options": {
                        "address": {
                            "setting":"address",
                            "input_type": "string",
                            "required": "Yes",
                            "setting_link": "https://www.elastic.co/docs/reference/logstash/pipeline-to-pipeline",
                            "important": "Yes"
                        }
                    },
                    "Bundled": "Yes"
                }
            },
            "output": {
                "pipeline": {
                    "name": "pipeline",
                    "link": "https://www.elastic.co/docs/reference/logstash/pipeline-to-pipeline",
                    "description": "Sends output to another pipeline",
                    "repo_link": "https://www.elastic.co/docs/reference/logstash/pipeline-to-pipeline",
                    "options": {
                        "send_to": {
                            "setting": "send_to",
                            "input_type": "list",
                            "required": "Yes",
                            "setting_link": "https://www.elastic.co/docs/reference/logstash/pipeline-to-pipeline",
                            "important": "Yes"
                        },
                        "ensure_delivery": {
                            "setting": "ensure_delivery",
                            "input_type": "boolean",
                            "required": "No",
                            "setting_link": "https://www.elastic.co/docs/reference/logstash/pipeline-to-pipeline",
                            "important": "No"
                        }
                    },
                    "Bundled": "Yes"
                }
            }
        }

        for section in missing_plugins:
            for plugin in missing_plugins[section]:
                self.plugins[section][plugin] = missing_plugins[section][plugin]


    def start(self):
        f = open(self.file_path, "r")
        self.plugins = json.loads(f.read())
        f.close()

        broken_plugins = self._look_for_broken_plugins()

        # This is basically a bandage to resolve issues with how our docs are shaped
        self._fix_broken_plugins(broken_plugins)

        # Our docs don't explicitly say whether or not a plugin is bundled by default
        self._add_bundled_flag()

        # Important fields are required fields, should probably rename
        self._enrich_important_fields()

        # Makes UI elements more descriptive by honoring documented formatting
        self._optimize_datatypes()

        # Add missing plugins
        self._add_missing()

        f = open("enriched_plugins.json", "w+")
        f.write(json.dumps(self.plugins, indent=4))
        f.close()

    # whether or not the plugin is bundled by default
    def _add_bundled_flag(self):
        for plugin in self.default_plugins.split("\n"):
            split_plugin = plugin.split("-")
            plugin_name = split_plugin[2]
            plugin_type = split_plugin[1]

            if not plugin_type in self.default_plugins_dict:
                self.default_plugins_dict[plugin_type] = []

            self.default_plugins_dict[plugin_type].append(plugin_name)


        for section in self.plugins:
            if section == "integrations": continue
            for plugin in self.plugins[section]:
                if not plugin in self.default_plugins_dict[section]:
                    self.plugins[section][plugin]['bundled'] = "No"
                else:
                    self.plugins[section][plugin]['bundled'] = "Yes"

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
        for section in self.plugins:
            if section == "integrations":
                continue
            for plugin in self.plugins[section]:
                for option in self.plugins[section][plugin]['options']:
                    if option in self.important_fields[section][plugin]:
                        self.plugins[section][plugin]['options'][option]['important'] = "Yes"
                    else:
                        self.plugins[section][plugin]['options'][option]['important'] = "No"



def main():
    enrich = EnrichPlugins()
    enrich.start()

if __name__ == "__main__":
    main()