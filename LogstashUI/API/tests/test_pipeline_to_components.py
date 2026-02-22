from API.logstash_config_parse import logstash_config_to_components
import pytest
import json


test_cases = [
    (
        "test-elasticdocs-configuring_filters",
        '''input { stdin { } }

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
''',
        r'''{
    "input": [
        {
            "id": "input_stdin_0",
            "type": "input",
            "plugin": "stdin",
            "config": {}
        }
    ],
    "filter": [
        {
            "id": "filter_grok_2",
            "type": "filter",
            "plugin": "grok",
            "config": {
                "match": {
                    "message": "%{COMBINEDAPACHELOG}"
                }
            }
        },
        {
            "id": "filter_date_4",
            "type": "filter",
            "plugin": "date",
            "config": {
                "match": [
                    "timestamp",
                    "dd/MMM/yyyy:HH:mm:ss Z"
                ]
            }
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_6",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "hosts": [
                    "localhost:9200"
                ]
            }
        },
        {
            "id": "output_stdout_8",
            "type": "output",
            "plugin": "stdout",
            "config": {
                "codec": {
                    "rubydebug": {}
                }
            }
        }
    ]
}'''
    ),
    (
        "test-elasticdocs-apache",
        '''input {
	file {
		path => "/tmp/access_log"
		start_position => "beginning"
	}
}
filter {
	if [path] =~ "access" {
		mutate {
			replace => {
				"type" => "apache_access"
			}
		}
		grok {
			match => {
				"message" => "%{COMBINEDAPACHELOG}"
			}
		}
	}
	date {
		match => ["timestamp", "dd/MMM/yyyy:HH:mm:ss Z"]
	}
}
output {
	elasticsearch {
		hosts => ["localhost:9200"]
	}
	stdout {
		codec => rubydebug
	}
}
''',
        r'''{
    "input": [
        {
            "id": "input_file_0",
            "type": "input",
            "plugin": "file",
            "config": {
                "path": "/tmp/access_log",
                "start_position": "beginning"
            }
        }
    ],
    "filter": [
        {
            "id": "filter_if_2",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[path] =~ \"access\"",
                "plugins": [
                    {
                        "id": "filter_mutate_3",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "replace": {
                                "type": "apache_access"
                            }
                        }
                    },
                    {
                        "id": "filter_grok_5",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "message": "%{COMBINEDAPACHELOG}"
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_date_7",
            "type": "filter",
            "plugin": "date",
            "config": {
                "match": [
                    "timestamp",
                    "dd/MMM/yyyy:HH:mm:ss Z"
                ]
            }
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_9",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "hosts": [
                    "localhost:9200"
                ]
            }
        },
        {
            "id": "output_stdout_11",
            "type": "output",
            "plugin": "stdout",
            "config": {
                "codec": {
                    "rubydebug": {}
                }
            }
        }
    ]
}'''
    ),
    (
        "test_elasticdocs-conditional",
        '''input {
	file {
		path => "/tmp/*_log"
	}
}
filter {
	if [path] =~ "access" {
		mutate {
			replace => {
				type => "apache_access"
			}
		}
		grok {
			match => {
				"message" => "%{COMBINEDAPACHELOG}"
			}
		}
		date {
			match => ["timestamp", "dd/MMM/yyyy:HH:mm:ss Z"]
		}
	}
	else if [path] =~ "error" {
		mutate {
			replace => {
				type => "apache_error"
			}
		}
	}
	else {
		mutate {
			replace => {
				type => "random_logs"
			}
		}
	}
}
output {
	elasticsearch {
		hosts => ["localhost:9200"]
	}
	stdout {
		codec => rubydebug
	}
}
''',
        r'''{
    "input": [
        {
            "id": "input_file_0",
            "type": "input",
            "plugin": "file",
            "config": {
                "path": "/tmp/*_log"
            }
        }
    ],
    "filter": [
        {
            "id": "filter_if_2",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[path] =~ \"access\"",
                "plugins": [
                    {
                        "id": "filter_mutate_3",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "replace": {
                                "type": "apache_access"
                            }
                        }
                    },
                    {
                        "id": "filter_grok_5",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "message": "%{COMBINEDAPACHELOG}"
                            }
                        }
                    },
                    {
                        "id": "filter_date_7",
                        "type": "filter",
                        "plugin": "date",
                        "config": {
                            "match": [
                                "timestamp",
                                "dd/MMM/yyyy:HH:mm:ss Z"
                            ]
                        }
                    }
                ],
                "else_ifs": [
                    {
                        "condition": "[path] =~ \"error\"",
                        "plugins": [
                            {
                                "id": "filter_mutate_9",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "replace": {
                                        "type": "apache_error"
                                    }
                                }
                            }
                        ]
                    }
                ],
                "else": {
                    "plugins": [
                        {
                            "id": "filter_mutate_11",
                            "type": "filter",
                            "plugin": "mutate",
                            "config": {
                                "replace": {
                                    "type": "random_logs"
                                }
                            }
                        }
                    ]
                }
            }
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_13",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "hosts": [
                    "localhost:9200"
                ]
            }
        },
        {
            "id": "output_stdout_15",
            "type": "output",
            "plugin": "stdout",
            "config": {
                "codec": {
                    "rubydebug": {}
                }
            }
        }
    ]
}'''
    ),
    (
        "test-elasticdocs-syslog",
        '''input {
  tcp {
    port => 5000
    type => syslog
  }
  udp {
    port => 5000
    type => syslog
  }
}

filter {
  if [type] == "syslog" {
    grok {
      match => { "message" => "%{SYSLOGTIMESTAMP:syslog_timestamp} %{SYSLOGHOST:syslog_hostname} %{DATA:syslog_program}(?:\[%{POSINT:syslog_pid}\])?: %{GREEDYDATA:syslog_message}" }
      add_field => [ "received_at", "%{@timestamp}" ]
      add_field => [ "received_from", "%{host}" ]
    }
    date {
      match => [ "syslog_timestamp", "MMM  d HH:mm:ss", "MMM dd HH:mm:ss" ]
    }
  }
}

output {
  elasticsearch { hosts => ["localhost:9200"] }
  stdout { codec => rubydebug }
}''',
        r'''{
    "input": [
        {
            "id": "input_tcp_0",
            "type": "input",
            "plugin": "tcp",
            "config": {
                "port": 5000,
                "type": "syslog"
            }
        },
        {
            "id": "input_udp_2",
            "type": "input",
            "plugin": "udp",
            "config": {
                "port": 5000,
                "type": "syslog"
            }
        }
    ],
    "filter": [
        {
            "id": "filter_if_4",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[type] == \"syslog\"",
                "plugins": [
                    {
                        "id": "filter_grok_5",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "message": "%{SYSLOGTIMESTAMP:syslog_timestamp} %{SYSLOGHOST:syslog_hostname} %{DATA:syslog_program}(?:\\[%{POSINT:syslog_pid}\\])?: %{GREEDYDATA:syslog_message}"
                            },
                            "add_field": [
                                "received_at",
                                "%{@timestamp}",
                                "received_from",
                                "%{host}"
                            ]
                        }
                    },
                    {
                        "id": "filter_date_7",
                        "type": "filter",
                        "plugin": "date",
                        "config": {
                            "match": [
                                "syslog_timestamp",
                                "MMM  d HH:mm:ss",
                                "MMM dd HH:mm:ss"
                            ]
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_9",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "hosts": [
                    "localhost:9200"
                ]
            }
        },
        {
            "id": "output_stdout_11",
            "type": "output",
            "plugin": "stdout",
            "config": {
                "codec": {
                    "rubydebug": {}
                }
            }
        }
    ]
}'''
    ),
    (
        "test-devopsschool-1",
        """input {
    beats {
        port => "5044"
    }
}
filter {
    grok {
        match => { "message" => "%{COMBINEDAPACHELOG}"}
    }
}
output {
    elasticsearch {
        hosts => ["http://elasticsearch:9200"]
        index => "%{[@metadata][beat]}-%{[@metadata][version]}-%{+YYYY.MM.dd}"
    }
    stdout { 
        codec => rubydebug 
      }
}
""",
        r'''{
    "input": [
        {
            "id": "input_beats_0",
            "type": "input",
            "plugin": "beats",
            "config": {
                "port": "5044"
            }
        }
    ],
    "filter": [
        {
            "id": "filter_grok_2",
            "type": "filter",
            "plugin": "grok",
            "config": {
                "match": {
                    "message": "%{COMBINEDAPACHELOG}"
                }
            }
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_4",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "hosts": [
                    "http://elasticsearch:9200"
                ],
                "index": "%{[@metadata][beat]}-%{[@metadata][version]}-%{+YYYY.MM.dd}"
            }
        },
        {
            "id": "output_stdout_6",
            "type": "output",
            "plugin": "stdout",
            "config": {
                "codec": {
                    "rubydebug": {}
                }
            }
        }
    ]
}'''
    ),
    (
        "test-devopsschool-2",
        """input {
    beats {
        port => "5044"
    }
}
filter {
    grok {
        match => { "message" => "%{SYSLOGLINE}"}
    }
}
output {
    stdout { codec => rubydebug }
}
""",
        r'''{
    "input": [
        {
            "id": "input_beats_0",
            "type": "input",
            "plugin": "beats",
            "config": {
                "port": "5044"
            }
        }
    ],
    "filter": [
        {
            "id": "filter_grok_2",
            "type": "filter",
            "plugin": "grok",
            "config": {
                "match": {
                    "message": "%{SYSLOGLINE}"
                }
            }
        }
    ],
    "output": [
        {
            "id": "output_stdout_4",
            "type": "output",
            "plugin": "stdout",
            "config": {
                "codec": {
                    "rubydebug": {}
                }
            }
        }
    ]
}'''
    ),
    (
        "test-devopsschool-4",
        """input {
  file {
         path => "/var/log/apache2/access.log"
    start_position => "beginning"
    sincedb_path => "/dev/null"
  }
}
filter {
    grok {
      match => { "message" => "%{COMBINEDAPACHELOG}" }
    }
    date {
    match => [ "timestamp" , "dd/MMM/yyyy:HH:mm:ss Z" ]
  }
  geoip {
      source => "clientip"
    }
}
output {
  elasticsearch {
    hosts => ["localhost:9200"]
  }
}
""",
        r'''{
    "input": [
        {
            "id": "input_file_0",
            "type": "input",
            "plugin": "file",
            "config": {
                "path": "/var/log/apache2/access.log",
                "start_position": "beginning",
                "sincedb_path": "/dev/null"
            }
        }
    ],
    "filter": [
        {
            "id": "filter_grok_2",
            "type": "filter",
            "plugin": "grok",
            "config": {
                "match": {
                    "message": "%{COMBINEDAPACHELOG}"
                }
            }
        },
        {
            "id": "filter_date_4",
            "type": "filter",
            "plugin": "date",
            "config": {
                "match": [
                    "timestamp",
                    "dd/MMM/yyyy:HH:mm:ss Z"
                ]
            }
        },
        {
            "id": "filter_geoip_6",
            "type": "filter",
            "plugin": "geoip",
            "config": {
                "source": "clientip"
            }
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_8",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "hosts": [
                    "localhost:9200"
                ]
            }
        }
    ]
}'''
    ),
    (
        "test-devopsschool-5",
        """input {
    beats {
        port => "5044"
    }
}
 filter {
    grok {
        match => { "message" => "%{COMBINEDAPACHELOG}"}
    }
    geoip {
        source => "clientip"
    }
}
output {
    elasticsearch {
        hosts => [ "localhost:9200" ]
    }
}
""",
        r'''{
    "input": [
        {
            "id": "input_beats_0",
            "type": "input",
            "plugin": "beats",
            "config": {
                "port": "5044"
            }
        }
    ],
    "filter": [
        {
            "id": "filter_grok_2",
            "type": "filter",
            "plugin": "grok",
            "config": {
                "match": {
                    "message": "%{COMBINEDAPACHELOG}"
                }
            }
        },
        {
            "id": "filter_geoip_4",
            "type": "filter",
            "plugin": "geoip",
            "config": {
                "source": "clientip"
            }
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_6",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "hosts": [
                    "localhost:9200"
                ]
            }
        }
    ]
}'''
    ),
    (
        "test_complex1",
        r"""#
# "LogstashUI kitchen sink" pipeline
# Goal: be extremely feature-rich while staying within known-valid plugin options.
#

input {

  # Beats / Elastic Agent style shippers
  beats {
    id => "in_beats_5044"
    port => 5044
    add_field => { "ingest_transport" => "beats" }
    tags => ["from_beats"]
  }

  # JSON-over-TCP (common for app logs)
  tcp {
    id => "in_tcp_json_5514"
    port => 5514
    mode => "server"
    codec => json
    add_field => { "ingest_transport" => "tcp" }
    tags => ["from_tcp"]
  }

  # Syslog-ish UDP
  udp {
    id => "in_udp_5515"
    port => 5515
    codec => plain
    add_field => { "ingest_transport" => "udp" }
    tags => ["from_udp"]
  }

  # HTTP event intake (webhooks, apps posting JSON, etc.)
  http {
    id => "in_http_8080"
    port => 8080
    codec => json
    add_field => { "ingest_transport" => "http" }
    tags => ["from_http"]
  }

  # Local dev/testing input
  stdin {
    id => "in_stdin"
    codec => line
    add_field => { "ingest_transport" => "stdin" }
    tags => ["from_stdin"]
  }

  # Synthetic test data (makes it easy to validate end-to-end quickly)
  generator {
    id => "in_generator"
    lines => [
      "Feb 21 09:12:01 host1 sshd[123]: Failed password for invalid user admin from 10.1.2.3 port 51234 ssh2",
      "{\"@timestamp\":\"2026-02-21T14:12:02Z\",\"message\":\"GET /health 200\",\"source_ip\":\"8.8.8.8\",\"user_agent\":\"Mozilla/5.0\"}",
      "level=info service=api latency_ms=42 source_ip=192.168.1.50 msg=\"request completed\""
    ]
    count => 1
    add_field => { "ingest_transport" => "generator" }
    tags => ["from_generator"]
  }
}

filter {

  #
  # Normalize a few shared fields
  #
  mutate {
    id => "f_mutate_bootstrap"
    add_field => {
      "[@metadata][pipeline]" => "logstashui_kitchen_sink"
      "event.module" => "logstashui"
    }
  }

  # Keep a canonical message field
  if ![message] and [event][original] {
    mutate { id => "f_mutate_event_original_to_message" copy => { "[event][original]" => "message" } }
  }

  #
  # Try to parse JSON *if* message looks like JSON (common when tcp/udp/plain feed JSON strings)
  #
  if [message] =~ "^[[:space:]]*\\{" {
    json {
      id => "f_json_from_message"
      source => "message"
      target => "json"
      tag_on_failure => ["_jsonparsefailure_message"]
    }
    # If json parsed, promote a few expected keys (only if present)
    if [json][@timestamp] { mutate { id => "f_promote_json_ts" copy => { "[json][@timestamp]" => "@timestamp" } } }
    if [json][source_ip]    { mutate { id => "f_promote_json_source_ip" copy => { "[json][source_ip]" => "source_ip" } } }
    if [json][user_agent]   { mutate { id => "f_promote_json_ua" copy => { "[json][user_agent]" => "user_agent" } } }
  }

  #
  # Syslog-ish parsing (UDP and some TCP)
  #
  if "from_udp" in [tags] or "from_tcp" in [tags] {
    # Try dissect first (fast) and fall back to grok
    dissect {
      id => "f_dissect_syslogish"
      mapping => { "message" => "%{syslog_timestamp} %{syslog_host} %{syslog_program}[%{syslog_pid}]: %{syslog_message}" }
      tag_on_failure => ["_dissectfailure_syslogish"]
    }

    if "_dissectfailure_syslogish" in [tags] {
      grok {
        id => "f_grok_syslogish"
        match => {
          "message" => [
            "%{SYSLOGTIMESTAMP:syslog_timestamp} %{HOSTNAME:syslog_host} %{DATA:syslog_program}(?:\\[%{POSINT:syslog_pid}\\])?: %{GREEDYDATA:syslog_message}"
          ]
        }
        tag_on_failure => ["_grokparsefailure_syslogish"]
      }
    }

    # If we extracted a syslog timestamp, use it
    if [syslog_timestamp] {
      date {
        id => "f_date_syslog"
        match => ["syslog_timestamp", "MMM  d HH:mm:ss", "MMM dd HH:mm:ss"]
        tag_on_failure => ["_dateparsefailure_syslog"]
      }
    }
  }

  #
  # key=value parsing for “flat” log lines
  #
  if [message] =~ "([A-Za-z0-9_.-]+)=([^\"]\\S+|\"[^\"]*\")" {
    kv {
      id => "f_kv_message"
      source => "message"
      trim_key => " "
      trim_value => " "
      value_split => "="
      field_split_pattern => "\\s+"
      tag_on_failure => ["_kvfailure_message"]
    }
  }

  #
  # Basic typing / normalization
  #
  mutate {
    id => "f_mutate_normalize"
    rename => { "msg" => "message_short" }
    convert => { "latency_ms" => "integer" }
    lowercase => ["level"]
  }

  #
  # Enrichments: useragent, geoip, cidr, dns
  #
  if [user_agent] {
    useragent {
      id => "f_useragent"
      source => "user_agent"
      target => "user_agent_parsed"
    }
  }

  # Canonicalize IP into source_ip if it exists elsewhere
  if ![source_ip] and [source][ip] {
    mutate { id => "f_copy_source_ip" copy => { "[source][ip]" => "source_ip" } }
  }

  if [source_ip] {
    # Tag private vs public
    cidr {
      id => "f_cidr_private"
      address => [ "%{source_ip}" ]
      network => [ "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16" ]
      add_tag => [ "src_private" ]
    }

    # GeoIP typically only makes sense for public IPs, so do it only if not private-tagged
    if "src_private" not in [tags] {
      geoip {
        id => "f_geoip"
        source => "source_ip"
        target => "source_geo"
      }
    }

    # Reverse DNS lookup; replace source_ip with hostname when possible (or leave as-is)
    dns {
      id => "f_dns_reverse"
      reverse => [ "source_ip" ]
      action => "replace"
    }
  }

  #
  # Translate severity/level into a normalized numeric
  #
  translate {
    id => "f_translate_level_to_severity"
    source => "level"
    target => "severity"
    dictionary => {
      "trace" => "0"
      "debug" => "1"
      "info"  => "2"
      "warn"  => "3"
      "error" => "4"
      "fatal" => "5"
    }
    fallback => "2"
  }
  mutate { id => "f_convert_severity_int" convert => { "severity" => "integer" } }

  #
  # Stable fingerprint for dedup / correlation
  #
  fingerprint {
    id => "f_fingerprint_message"
    source => ["message"]
    method => "MURMUR3"
    target => "[@metadata][fingerprint]"
  }

  #
  # Example branching: treat auth-ish messages specially
  #
  if [syslog_program] == "sshd" or [message] =~ "(?i)failed password|authentication failure|invalid user" {
    mutate {
      id => "f_tag_auth"
      add_tag => ["category_auth"]
      add_field => { "event.category" => "authentication" }
    }
  } else if [message] =~ "(?i)GET\\s+/health|/ready|/live" {
    mutate {
      id => "f_tag_health"
      add_tag => ["category_healthcheck"]
      add_field => { "event.category" => "availability" }
    }
  } else {
    mutate {
      id => "f_tag_generic"
      add_tag => ["category_generic"]
    }
  }

  #
  # Prune down noisy fields (keeps top-level essentials)
  #
  prune {
    id => "f_prune"
    whitelist_names => [
      "^@timestamp$",
      "^message$",
      "^message_short$",
      "^host$",
      "^source_ip$",
      "^source_geo$",
      "^severity$",
      "^level$",
      "^tags$",
      "^event\\..*$",
      "^user_agent.*$",
      "^syslog_.*$",
      "^ingest_transport$"
    ]
  }
}

output {

  # Always see something in console during dev
  stdout {
    id => "out_stdout_rubydebug"
    codec => rubydebug { metadata => true }
  }

  # Write to disk (great for debugging replay)
  file {
    id => "out_file_jsonl"
    path => "/tmp/logstashui-%{+YYYY.MM.dd}.jsonl"
    codec => json_lines
  }

  # Elasticsearch (local default)
  elasticsearch {
    id => "out_es_local"
    hosts => ["http://localhost:9200"]
    index => "logstashui-%{+YYYY.MM.dd}"
    ilm_enabled => false
  }

  # Webhook back to your UI/API (example)
  http {
    id => "out_http_callback"
    url => "http://localhost:9000/logstash/callback"
    http_method => "post"
    format => "json"
  }

  # Kafka (example)
  kafka {
    id => "out_kafka"
    bootstrap_servers => "localhost:9092"
    topic_id => "logstashui-events"
  }

  # Pipeline-to-pipeline (requires another pipeline with pipeline input address => "downstream")
  pipeline {
    id => "out_pipeline_downstream"
    send_to => ["downstream"]
  }
}""",
        r"""{
    "input": [
        {
            "id": "input_comment_0",
            "type": "input",
            "plugin": "comment",
            "config": {
                "text": "\n\"LogstashUI kitchen sink\" pipeline\nGoal: be extremely feature-rich while staying within known-valid plugin options.\n"
            }
        },
        {
            "id": "input_comment_1",
            "type": "input",
            "plugin": "comment",
            "config": {
                "text": "Beats / Elastic Agent style shippers"
            }
        },
        {
            "id": "input_beats_2",
            "type": "input",
            "plugin": "beats",
            "config": {
                "id": "in_beats_5044",
                "port": 5044,
                "add_field": {
                    "ingest_transport": "beats"
                },
                "tags": [
                    "from_beats"
                ]
            }
        },
        {
            "id": "input_comment_4",
            "type": "input",
            "plugin": "comment",
            "config": {
                "text": "JSON-over-TCP (common for app logs)"
            }
        },
        {
            "id": "input_tcp_5",
            "type": "input",
            "plugin": "tcp",
            "config": {
                "id": "in_tcp_json_5514",
                "port": 5514,
                "mode": "server",
                "codec": {
                    "json": {}
                },
                "add_field": {
                    "ingest_transport": "tcp"
                },
                "tags": [
                    "from_tcp"
                ]
            }
        },
        {
            "id": "input_comment_7",
            "type": "input",
            "plugin": "comment",
            "config": {
                "text": "Syslog-ish UDP"
            }
        },
        {
            "id": "input_udp_8",
            "type": "input",
            "plugin": "udp",
            "config": {
                "id": "in_udp_5515",
                "port": 5515,
                "codec": {
                    "plain": {}
                },
                "add_field": {
                    "ingest_transport": "udp"
                },
                "tags": [
                    "from_udp"
                ]
            }
        },
        {
            "id": "input_comment_10",
            "type": "input",
            "plugin": "comment",
            "config": {
                "text": "HTTP event intake (webhooks, apps posting JSON, etc.)"
            }
        },
        {
            "id": "input_http_11",
            "type": "input",
            "plugin": "http",
            "config": {
                "id": "in_http_8080",
                "port": 8080,
                "codec": {
                    "json": {}
                },
                "add_field": {
                    "ingest_transport": "http"
                },
                "tags": [
                    "from_http"
                ]
            }
        },
        {
            "id": "input_comment_13",
            "type": "input",
            "plugin": "comment",
            "config": {
                "text": "Local dev/testing input"
            }
        },
        {
            "id": "input_stdin_14",
            "type": "input",
            "plugin": "stdin",
            "config": {
                "id": "in_stdin",
                "codec": {
                    "line": {}
                },
                "add_field": {
                    "ingest_transport": "stdin"
                },
                "tags": [
                    "from_stdin"
                ]
            }
        },
        {
            "id": "input_comment_16",
            "type": "input",
            "plugin": "comment",
            "config": {
                "text": "Synthetic test data (makes it easy to validate end-to-end quickly)"
            }
        },
        {
            "id": "input_generator_17",
            "type": "input",
            "plugin": "generator",
            "config": {
                "id": "in_generator",
                "lines": [
                    "Feb 21 09:12:01 host1 sshd[123]: Failed password for invalid user admin from 10.1.2.3 port 51234 ssh2",
                    "{\"@timestamp\":\"2026-02-21T14:12:02Z\",\"message\":\"GET /health 200\",\"source_ip\":\"8.8.8.8\",\"user_agent\":\"Mozilla/5.0\"}",
                    "level=info service=api latency_ms=42 source_ip=192.168.1.50 msg=\"request completed\""
                ],
                "count": 1,
                "add_field": {
                    "ingest_transport": "generator"
                },
                "tags": [
                    "from_generator"
                ]
            }
        }
    ],
    "filter": [
        {
            "id": "filter_comment_19",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nNormalize a few shared fields\n"
            }
        },
        {
            "id": "filter_mutate_20",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "id": "f_mutate_bootstrap",
                "add_field": {
                    "[@metadata][pipeline]": "logstashui_kitchen_sink",
                    "event.module": "logstashui"
                }
            }
        },
        {
            "id": "filter_comment_22",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "Keep a canonical message field"
            }
        },
        {
            "id": "filter_if_23",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "![message] and [event][original]",
                "plugins": [
                    {
                        "id": "filter_mutate_24",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "id": "f_mutate_event_original_to_message",
                            "copy": {
                                "[event][original]": "message"
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_comment_26",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nTry to parse JSON *if* message looks like JSON (common when tcp/udp/plain feed JSON strings)\n"
            }
        },
        {
            "id": "filter_if_27",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[message] =~ \"^[[:space:]]*\\\\{\"",
                "plugins": [
                    {
                        "id": "filter_json_28",
                        "type": "filter",
                        "plugin": "json",
                        "config": {
                            "id": "f_json_from_message",
                            "source": "message",
                            "target": "json",
                            "tag_on_failure": [
                                "_jsonparsefailure_message"
                            ]
                        }
                    },
                    {
                        "id": "filter_comment_30",
                        "type": "filter",
                        "plugin": "comment",
                        "config": {
                            "text": "If json parsed, promote a few expected keys (only if present)"
                        }
                    },
                    {
                        "id": "filter_if_31",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "[json][@timestamp]",
                            "plugins": [
                                {
                                    "id": "filter_mutate_32",
                                    "type": "filter",
                                    "plugin": "mutate",
                                    "config": {
                                        "id": "f_promote_json_ts",
                                        "copy": {
                                            "[json][@timestamp]": "@timestamp"
                                        }
                                    }
                                }
                            ],
                            "else_ifs": [],
                            "else": null
                        }
                    },
                    {
                        "id": "filter_if_34",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "[json][source_ip]",
                            "plugins": [
                                {
                                    "id": "filter_mutate_35",
                                    "type": "filter",
                                    "plugin": "mutate",
                                    "config": {
                                        "id": "f_promote_json_source_ip",
                                        "copy": {
                                            "[json][source_ip]": "source_ip"
                                        }
                                    }
                                }
                            ],
                            "else_ifs": [],
                            "else": null
                        }
                    },
                    {
                        "id": "filter_if_37",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "[json][user_agent]",
                            "plugins": [
                                {
                                    "id": "filter_mutate_38",
                                    "type": "filter",
                                    "plugin": "mutate",
                                    "config": {
                                        "id": "f_promote_json_ua",
                                        "copy": {
                                            "[json][user_agent]": "user_agent"
                                        }
                                    }
                                }
                            ],
                            "else_ifs": [],
                            "else": null
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_comment_40",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nSyslog-ish parsing (UDP and some TCP)\n"
            }
        },
        {
            "id": "filter_if_41",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "\"from_udp\" in [tags] or \"from_tcp\" in [tags]",
                "plugins": [
                    {
                        "id": "filter_comment_42",
                        "type": "filter",
                        "plugin": "comment",
                        "config": {
                            "text": "Try dissect first (fast) and fall back to grok"
                        }
                    },
                    {
                        "id": "filter_dissect_43",
                        "type": "filter",
                        "plugin": "dissect",
                        "config": {
                            "id": "f_dissect_syslogish",
                            "mapping": {
                                "message": "%{syslog_timestamp} %{syslog_host} %{syslog_program}[%{syslog_pid}]: %{syslog_message}"
                            },
                            "tag_on_failure": [
                                "_dissectfailure_syslogish"
                            ]
                        }
                    },
                    {
                        "id": "filter_if_45",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "\"_dissectfailure_syslogish\" in [tags]",
                            "plugins": [
                                {
                                    "id": "filter_grok_46",
                                    "type": "filter",
                                    "plugin": "grok",
                                    "config": {
                                        "id": "f_grok_syslogish",
                                        "match": {
                                            "message": [
                                                "%{SYSLOGTIMESTAMP:syslog_timestamp} %{HOSTNAME:syslog_host} %{DATA:syslog_program}(?:\\[%{POSINT:syslog_pid}\\])?: %{GREEDYDATA:syslog_message}"
                                            ]
                                        },
                                        "tag_on_failure": [
                                            "_grokparsefailure_syslogish"
                                        ]
                                    }
                                }
                            ],
                            "else_ifs": [],
                            "else": null
                        }
                    },
                    {
                        "id": "filter_comment_48",
                        "type": "filter",
                        "plugin": "comment",
                        "config": {
                            "text": "If we extracted a syslog timestamp, use it"
                        }
                    },
                    {
                        "id": "filter_if_49",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "[syslog_timestamp]",
                            "plugins": [
                                {
                                    "id": "filter_date_50",
                                    "type": "filter",
                                    "plugin": "date",
                                    "config": {
                                        "id": "f_date_syslog",
                                        "match": [
                                            "syslog_timestamp",
                                            "MMM  d HH:mm:ss",
                                            "MMM dd HH:mm:ss"
                                        ],
                                        "tag_on_failure": [
                                            "_dateparsefailure_syslog"
                                        ]
                                    }
                                }
                            ],
                            "else_ifs": [],
                            "else": null
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_comment_52",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nkey=value parsing for \u201cflat\u201d log lines\n"
            }
        },
        {
            "id": "filter_if_53",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[message] =~ \"([A-Za-z0-9_.-]+)=([^\\\"]\\\\S+|\\\"[^\\\"]*\\\")\"",
                "plugins": [
                    {
                        "id": "filter_kv_54",
                        "type": "filter",
                        "plugin": "kv",
                        "config": {
                            "id": "f_kv_message",
                            "source": "message",
                            "trim_key": " ",
                            "trim_value": " ",
                            "value_split": "=",
                            "field_split_pattern": "\\s+",
                            "tag_on_failure": [
                                "_kvfailure_message"
                            ]
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_comment_56",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nBasic typing / normalization\n"
            }
        },
        {
            "id": "filter_mutate_57",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "id": "f_mutate_normalize",
                "rename": {
                    "msg": "message_short"
                },
                "convert": {
                    "latency_ms": "integer"
                },
                "lowercase": [
                    "level"
                ]
            }
        },
        {
            "id": "filter_comment_59",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nEnrichments: useragent, geoip, cidr, dns\n"
            }
        },
        {
            "id": "filter_if_60",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[user_agent]",
                "plugins": [
                    {
                        "id": "filter_useragent_61",
                        "type": "filter",
                        "plugin": "useragent",
                        "config": {
                            "id": "f_useragent",
                            "source": "user_agent",
                            "target": "user_agent_parsed"
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_comment_63",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "Canonicalize IP into source_ip if it exists elsewhere"
            }
        },
        {
            "id": "filter_if_64",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "![source_ip] and [source][ip]",
                "plugins": [
                    {
                        "id": "filter_mutate_65",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "id": "f_copy_source_ip",
                            "copy": {
                                "[source][ip]": "source_ip"
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_if_67",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[source_ip]",
                "plugins": [
                    {
                        "id": "filter_comment_68",
                        "type": "filter",
                        "plugin": "comment",
                        "config": {
                            "text": "Tag private vs public"
                        }
                    },
                    {
                        "id": "filter_cidr_69",
                        "type": "filter",
                        "plugin": "cidr",
                        "config": {
                            "id": "f_cidr_private",
                            "address": [
                                "%{source_ip}"
                            ],
                            "network": [
                                "10.0.0.0/8",
                                "172.16.0.0/12",
                                "192.168.0.0/16"
                            ],
                            "add_tag": [
                                "src_private"
                            ]
                        }
                    },
                    {
                        "id": "filter_comment_71",
                        "type": "filter",
                        "plugin": "comment",
                        "config": {
                            "text": "GeoIP typically only makes sense for public IPs, so do it only if not private-tagged"
                        }
                    },
                    {
                        "id": "filter_if_72",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "\"src_private\" not in [tags]",
                            "plugins": [
                                {
                                    "id": "filter_geoip_73",
                                    "type": "filter",
                                    "plugin": "geoip",
                                    "config": {
                                        "id": "f_geoip",
                                        "source": "source_ip",
                                        "target": "source_geo"
                                    }
                                }
                            ],
                            "else_ifs": [],
                            "else": null
                        }
                    },
                    {
                        "id": "filter_comment_75",
                        "type": "filter",
                        "plugin": "comment",
                        "config": {
                            "text": "Reverse DNS lookup; replace source_ip with hostname when possible (or leave as-is)"
                        }
                    },
                    {
                        "id": "filter_dns_76",
                        "type": "filter",
                        "plugin": "dns",
                        "config": {
                            "id": "f_dns_reverse",
                            "reverse": [
                                "source_ip"
                            ],
                            "action": "replace"
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_comment_78",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nTranslate severity/level into a normalized numeric\n"
            }
        },
        {
            "id": "filter_translate_79",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "id": "f_translate_level_to_severity",
                "source": "level",
                "target": "severity",
                "dictionary": {
                    "trace": "0",
                    "debug": "1",
                    "info": "2",
                    "warn": "3",
                    "error": "4",
                    "fatal": "5"
                },
                "fallback": "2"
            }
        },
        {
            "id": "filter_mutate_81",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "id": "f_convert_severity_int",
                "convert": {
                    "severity": "integer"
                }
            }
        },
        {
            "id": "filter_comment_83",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nStable fingerprint for dedup / correlation\n"
            }
        },
        {
            "id": "filter_fingerprint_84",
            "type": "filter",
            "plugin": "fingerprint",
            "config": {
                "id": "f_fingerprint_message",
                "source": [
                    "message"
                ],
                "method": "MURMUR3",
                "target": "[@metadata][fingerprint]"
            }
        },
        {
            "id": "filter_comment_86",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nExample branching: treat auth-ish messages specially\n"
            }
        },
        {
            "id": "filter_if_87",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[syslog_program] == \"sshd\" or [message] =~ \"(?i)failed password|authentication failure|invalid user\"",
                "plugins": [
                    {
                        "id": "filter_mutate_88",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "id": "f_tag_auth",
                            "add_tag": [
                                "category_auth"
                            ],
                            "add_field": {
                                "event.category": "authentication"
                            }
                        }
                    }
                ],
                "else_ifs": [
                    {
                        "condition": "[message] =~ \"(?i)GET\\\\s+/health|/ready|/live\"",
                        "plugins": [
                            {
                                "id": "filter_mutate_90",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "id": "f_tag_health",
                                    "add_tag": [
                                        "category_healthcheck"
                                    ],
                                    "add_field": {
                                        "event.category": "availability"
                                    }
                                }
                            }
                        ]
                    }
                ],
                "else": {
                    "plugins": [
                        {
                            "id": "filter_mutate_92",
                            "type": "filter",
                            "plugin": "mutate",
                            "config": {
                                "id": "f_tag_generic",
                                "add_tag": [
                                    "category_generic"
                                ]
                            }
                        }
                    ]
                }
            }
        },
        {
            "id": "filter_comment_94",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": "\nPrune down noisy fields (keeps top-level essentials)\n"
            }
        },
        {
            "id": "filter_prune_95",
            "type": "filter",
            "plugin": "prune",
            "config": {
                "id": "f_prune",
                "whitelist_names": [
                    "^@timestamp$",
                    "^message$",
                    "^message_short$",
                    "^host$",
                    "^source_ip$",
                    "^source_geo$",
                    "^severity$",
                    "^level$",
                    "^tags$",
                    "^event\\..*$",
                    "^user_agent.*$",
                    "^syslog_.*$",
                    "^ingest_transport$"
                ]
            }
        }
    ],
    "output": [
        {
            "id": "output_comment_97",
            "type": "output",
            "plugin": "comment",
            "config": {
                "text": "Always see something in console during dev"
            }
        },
        {
            "id": "output_stdout_98",
            "type": "output",
            "plugin": "stdout",
            "config": {
                "id": "out_stdout_rubydebug",
                "codec": {
                    "rubydebug": {
                        "metadata": "true"
                    }
                }
            }
        },
        {
            "id": "output_comment_100",
            "type": "output",
            "plugin": "comment",
            "config": {
                "text": "Write to disk (great for debugging replay)"
            }
        },
        {
            "id": "output_file_101",
            "type": "output",
            "plugin": "file",
            "config": {
                "id": "out_file_jsonl",
                "path": "/tmp/logstashui-%{+YYYY.MM.dd}.jsonl",
                "codec": {
                    "json_lines": {}
                }
            }
        },
        {
            "id": "output_comment_103",
            "type": "output",
            "plugin": "comment",
            "config": {
                "text": "Elasticsearch (local default)"
            }
        },
        {
            "id": "output_elasticsearch_104",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "id": "out_es_local",
                "hosts": [
                    "http://localhost:9200"
                ],
                "index": "logstashui-%{+YYYY.MM.dd}",
                "ilm_enabled": "false"
            }
        },
        {
            "id": "output_comment_106",
            "type": "output",
            "plugin": "comment",
            "config": {
                "text": "Webhook back to your UI/API (example)"
            }
        },
        {
            "id": "output_http_107",
            "type": "output",
            "plugin": "http",
            "config": {
                "id": "out_http_callback",
                "url": "http://localhost:9000/logstash/callback",
                "http_method": "post",
                "format": "json"
            }
        },
        {
            "id": "output_comment_109",
            "type": "output",
            "plugin": "comment",
            "config": {
                "text": "Kafka (example)"
            }
        },
        {
            "id": "output_kafka_110",
            "type": "output",
            "plugin": "kafka",
            "config": {
                "id": "out_kafka",
                "bootstrap_servers": "localhost:9092",
                "topic_id": "logstashui-events"
            }
        },
        {
            "id": "output_comment_112",
            "type": "output",
            "plugin": "comment",
            "config": {
                "text": "Pipeline-to-pipeline (requires another pipeline with pipeline input address => \"downstream\")"
            }
        },
        {
            "id": "output_pipeline_113",
            "type": "output",
            "plugin": "pipeline",
            "config": {
                "id": "out_pipeline_downstream",
                "send_to": [
                    "downstream"
                ]
            }
        }
    ]
}"""
    )

]


@pytest.mark.parametrize(
    "name, pipeline, components",
    test_cases,
    ids=[case[0] for case in test_cases]
)
def test_pipeline_to_components(name, pipeline, components):
    assert logstash_config_to_components(pipeline) == components



