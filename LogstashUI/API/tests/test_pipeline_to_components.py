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
                    "\"message\"": "%{COMBINEDAPACHELOG}"
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
                                "\"type\"": "apache_access"
                            }
                        }
                    },
                    {
                        "id": "filter_grok_5",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"message\"": "%{COMBINEDAPACHELOG}"
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
                                "\"message\"": "%{COMBINEDAPACHELOG}"
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
                                "\"message\"": "%{SYSLOGTIMESTAMP:syslog_timestamp} %{SYSLOGHOST:syslog_hostname} %{DATA:syslog_program}(?:\\[%{POSINT:syslog_pid}\\])?: %{GREEDYDATA:syslog_message}"
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
    )

]


@pytest.mark.parametrize(
    "name, pipeline, components",
    test_cases,
    ids=[case[0] for case in test_cases]
)
def test_pipeline_to_components(name, pipeline, components):
    assert logstash_config_to_components(pipeline) == components



