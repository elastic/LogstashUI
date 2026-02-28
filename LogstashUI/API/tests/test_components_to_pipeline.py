from Common.logstash_config_parse import ComponentToPipeline
import pytest
import json


test_cases = [
    (
        "test-elasticdocs-configuring_filters",
        '''input {
	stdin {
	}
}
filter {
	grok {
		match => {
			"message" => "%{COMBINEDAPACHELOG}"
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
				"type" => "apache_access"
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
				"type" => "apache_error"
			}
		}
	}
	else {
		mutate {
			replace => {
				"type" => "random_logs"
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
		port => "5000"
		type => "syslog"
	}
	udp {
		port => "5000"
		type => "syslog"
	}
}
filter {
	if [type] == "syslog" {
		grok {
			match => {
				"message" => "%{SYSLOGTIMESTAMP:syslog_timestamp} %{SYSLOGHOST:syslog_hostname} %{DATA:syslog_program}(?:\[%{POSINT:syslog_pid}\])?: %{GREEDYDATA:syslog_message}"
			}
			add_field => ["received_at", "%{@timestamp}", "received_from", "%{host}"]
		}
		date {
			match => ["syslog_timestamp", "MMM  d HH:mm:ss", "MMM dd HH:mm:ss"]
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
		match => {
			"message" => "%{COMBINEDAPACHELOG}"
		}
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
		match => {
			"message" => "%{SYSLOGLINE}"
		}
	}
}
output {
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
		match => {
			"message" => "%{COMBINEDAPACHELOG}"
		}
	}
	date {
		match => ["timestamp", "dd/MMM/yyyy:HH:mm:ss Z"]
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
		match => {
			"message" => "%{COMBINEDAPACHELOG}"
		}
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
        r"""input {
	beats {
		id => "in_beats_5044"
		port => "5044"
		add_field => {
			"ingest_transport" => "beats"
		}
		tags => ["from_beats"]
	}
	tcp {
		id => "in_tcp_json_5514"
		port => "5514"
		mode => "server"
		codec => json
		add_field => {
			"ingest_transport" => "tcp"
		}
		tags => ["from_tcp"]
	}
	udp {
		id => "in_udp_5515"
		port => "5515"
		codec => plain
		add_field => {
			"ingest_transport" => "udp"
		}
		tags => ["from_udp"]
	}
	http {
		id => "in_http_8080"
		port => "8080"
		codec => json
		add_field => {
			"ingest_transport" => "http"
		}
		tags => ["from_http"]
	}
	stdin {
		id => "in_stdin"
		codec => line
		add_field => {
			"ingest_transport" => "stdin"
		}
		tags => ["from_stdin"]
	}
	generator {
		id => "in_generator"
		lines => ["Feb 21 09:12:01 host1 sshd[123]: Failed password for invalid user admin from 10.1.2.3 port 51234 ssh2", "{\"@timestamp\":\"2026-02-21T14:12:02Z\",\"message\":\"GET /health 200\",\"source_ip\":\"8.8.8.8\",\"user_agent\":\"Mozilla/5.0\"}", "level=info service=api latency_ms=42 source_ip=192.168.1.50 msg=\"request completed\""]
		count => "1"
		add_field => {
			"ingest_transport" => "generator"
		}
		tags => ["from_generator"]
	}
}
filter {
	mutate {
		id => "f_mutate_bootstrap"
		add_field => {
			"[@metadata][pipeline]" => "logstashui_kitchen_sink"
			"event.module" => "logstashui"
		}
	}
	if ![message] and [event][original] {
		mutate {
			id => "f_mutate_event_original_to_message"
			copy => {
				"[event][original]" => "message"
			}
		}
	}
	if [message] =~ "^[[:space:]]*\\{" {
		json {
			id => "f_json_from_message"
			source => "message"
			target => "json"
			tag_on_failure => ["_jsonparsefailure_message"]
		}
		if [json][@timestamp] {
			mutate {
				id => "f_promote_json_ts"
				copy => {
					"[json][@timestamp]" => "@timestamp"
				}
			}
		}
		if [json][source_ip] {
			mutate {
				id => "f_promote_json_source_ip"
				copy => {
					"[json][source_ip]" => "source_ip"
				}
			}
		}
		if [json][user_agent] {
			mutate {
				id => "f_promote_json_ua"
				copy => {
					"[json][user_agent]" => "user_agent"
				}
			}
		}
	}
	if "from_udp" in [tags] or "from_tcp" in [tags] {
		dissect {
			id => "f_dissect_syslogish"
			mapping => {
				"message" => "%{syslog_timestamp} %{syslog_host} %{syslog_program}[%{syslog_pid}]: %{syslog_message}"
			}
			tag_on_failure => ["_dissectfailure_syslogish"]
		}
		if "_dissectfailure_syslogish" in [tags] {
			grok {
				id => "f_grok_syslogish"
				match => {
					"message" => [
						"%{SYSLOGTIMESTAMP:syslog_timestamp} %{HOSTNAME:syslog_host} %{DATA:syslog_program}(?:\[%{POSINT:syslog_pid}\])?: %{GREEDYDATA:syslog_message}"
					]
				}
				tag_on_failure => ["_grokparsefailure_syslogish"]
			}
		}
		if [syslog_timestamp] {
			date {
				id => "f_date_syslog"
				match => ["syslog_timestamp", "MMM  d HH:mm:ss", "MMM dd HH:mm:ss"]
				tag_on_failure => ["_dateparsefailure_syslog"]
			}
		}
	}
	if [message] =~ "([A-Za-z0-9_.-]+)=([^\"]\\S+|\"[^\"]*\")" {
		kv {
			id => "f_kv_message"
			source => "message"
			trim_key => " "
			trim_value => " "
			value_split => "="
			field_split_pattern => "\s+"
			tag_on_failure => ["_kvfailure_message"]
		}
	}
	mutate {
		id => "f_mutate_normalize"
		rename => {
			"msg" => "message_short"
		}
		convert => {
			"latency_ms" => "integer"
		}
		lowercase => ["level"]
	}
	if [user_agent] {
		useragent {
			id => "f_useragent"
			source => "user_agent"
			target => "user_agent_parsed"
		}
	}
	if ![source_ip] and [source][ip] {
		mutate {
			id => "f_copy_source_ip"
			copy => {
				"[source][ip]" => "source_ip"
			}
		}
	}
	if [source_ip] {
		cidr {
			id => "f_cidr_private"
			address => ["%{source_ip}"]
			network => ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
			add_tag => ["src_private"]
		}
		if "src_private" not in [tags] {
			geoip {
				id => "f_geoip"
				source => "source_ip"
				target => "source_geo"
			}
		}
		dns {
			id => "f_dns_reverse"
			reverse => ["source_ip"]
			action => "replace"
		}
	}
	translate {
		id => "f_translate_level_to_severity"
		source => "level"
		target => "severity"
		dictionary => {
			"trace" => "0"
			"debug" => "1"
			"info" => "2"
			"warn" => "3"
			"error" => "4"
			"fatal" => "5"
		}
		fallback => "2"
	}
	mutate {
		id => "f_convert_severity_int"
		convert => {
			"severity" => "integer"
		}
	}
	fingerprint {
		id => "f_fingerprint_message"
		source => ["message"]
		method => "MURMUR3"
		target => "[@metadata][fingerprint]"
	}
	if [syslog_program] == "sshd" or [message] =~ "(?i)failed password|authentication failure|invalid user" {
		mutate {
			id => "f_tag_auth"
			add_tag => ["category_auth"]
			add_field => {
				"event.category" => "authentication"
			}
		}
	}
	else if [message] =~ "(?i)GET\\s+/health|/ready|/live" {
		mutate {
			id => "f_tag_health"
			add_tag => ["category_healthcheck"]
			add_field => {
				"event.category" => "availability"
			}
		}
	}
	else {
		mutate {
			id => "f_tag_generic"
			add_tag => ["category_generic"]
		}
	}
	prune {
		id => "f_prune"
		whitelist_names => ["^@timestamp$", "^message$", "^message_short$", "^host$", "^source_ip$", "^source_geo$", "^severity$", "^level$", "^tags$", "^event\\..*$", "^user_agent.*$", "^syslog_.*$", "^ingest_transport$"]
	}
}
output {
	stdout {
		id => "out_stdout_rubydebug"
		codec => rubydebug {
			metadata => "true"
		}
	}
	file {
		id => "out_file_jsonl"
		path => "/tmp/logstashui-%{+YYYY.MM.dd}.jsonl"
		codec => json_lines
	}
	elasticsearch {
		id => "out_es_local"
		hosts => ["http://localhost:9200"]
		index => "logstashui-%{+YYYY.MM.dd}"
		ilm_enabled => "false"
	}
	http {
		id => "out_http_callback"
		url => "http://localhost:9000/logstash/callback"
		http_method => "post"
		format => "json"
	}
	kafka {
		id => "out_kafka"
		bootstrap_servers => "localhost:9092"
		topic_id => "logstashui-events"
	}
	pipeline {
		id => "out_pipeline_downstream"
		send_to => ["downstream"]
	}
}
""",
        r"""{
    "input": [
        {
            "id": "input_beats_0",
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
            "id": "input_tcp_2",
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
            "id": "input_udp_4",
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
            "id": "input_http_6",
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
            "id": "input_stdin_8",
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
            "id": "input_generator_10",
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
            "id": "filter_mutate_12",
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
            "id": "filter_if_14",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "![message] and [event][original]",
                "plugins": [
                    {
                        "id": "filter_mutate_15",
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
            "id": "filter_if_17",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[message] =~ \"^[[:space:]]*\\\\{\"",
                "plugins": [
                    {
                        "id": "filter_json_18",
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
                        "id": "filter_if_20",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "[json][@timestamp]",
                            "plugins": [
                                {
                                    "id": "filter_mutate_21",
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
                        "id": "filter_if_23",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "[json][source_ip]",
                            "plugins": [
                                {
                                    "id": "filter_mutate_24",
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
                        "id": "filter_if_26",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "[json][user_agent]",
                            "plugins": [
                                {
                                    "id": "filter_mutate_27",
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
            "id": "filter_if_29",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "\"from_udp\" in [tags] or \"from_tcp\" in [tags]",
                "plugins": [
                    {
                        "id": "filter_dissect_30",
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
                        "id": "filter_if_32",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "\"_dissectfailure_syslogish\" in [tags]",
                            "plugins": [
                                {
                                    "id": "filter_grok_33",
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
                        "id": "filter_if_35",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "[syslog_timestamp]",
                            "plugins": [
                                {
                                    "id": "filter_date_36",
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
            "id": "filter_if_38",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[message] =~ \"([A-Za-z0-9_.-]+)=([^\\\"]\\\\S+|\\\"[^\\\"]*\\\")\"",
                "plugins": [
                    {
                        "id": "filter_kv_39",
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
            "id": "filter_mutate_41",
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
            "id": "filter_if_43",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[user_agent]",
                "plugins": [
                    {
                        "id": "filter_useragent_44",
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
            "id": "filter_if_46",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "![source_ip] and [source][ip]",
                "plugins": [
                    {
                        "id": "filter_mutate_47",
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
            "id": "filter_if_49",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[source_ip]",
                "plugins": [
                    {
                        "id": "filter_cidr_50",
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
                        "id": "filter_if_52",
                        "type": "filter",
                        "plugin": "if",
                        "config": {
                            "condition": "\"src_private\" not in [tags]",
                            "plugins": [
                                {
                                    "id": "filter_geoip_53",
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
                        "id": "filter_dns_55",
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
            "id": "filter_translate_57",
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
            "id": "filter_mutate_59",
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
            "id": "filter_fingerprint_61",
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
            "id": "filter_if_63",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[syslog_program] == \"sshd\" or [message] =~ \"(?i)failed password|authentication failure|invalid user\"",
                "plugins": [
                    {
                        "id": "filter_mutate_64",
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
                                "id": "filter_mutate_66",
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
                            "id": "filter_mutate_68",
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
            "id": "filter_prune_70",
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
            "id": "output_stdout_72",
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
            "id": "output_file_74",
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
            "id": "output_elasticsearch_76",
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
            "id": "output_http_78",
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
            "id": "output_kafka_80",
            "type": "output",
            "plugin": "kafka",
            "config": {
                "id": "out_kafka",
                "bootstrap_servers": "localhost:9092",
                "topic_id": "logstashui-events"
            }
        },
        {
            "id": "output_pipeline_82",
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
    ),
]


@pytest.mark.parametrize(
    "name, pipeline, components",
    test_cases,
    ids=[case[0] for case in test_cases]
)
def test_components_to_config(name, pipeline, components):
    parser = ComponentToPipeline(json.loads(components))
    new_config = parser.components_to_logstash_config()

    assert pipeline == new_config
