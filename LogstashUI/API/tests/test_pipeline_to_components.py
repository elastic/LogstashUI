from API.logstash_config_parse import logstash_config_to_components
import pytest
import json

def test_basic_jdbc_input():
    pipeline = """input {
  jdbc {
    jdbc_driver_library => "/usr/share/logstash/vendor/jar/jdbc/mysql-connector-j-9.3.0.jar"
    jdbc_driver_class => "com.mysql.cj.jdbc.Driver"
    jdbc_connection_string => "jdbc:mysql://${DB_HOST}:3306/semaphore" #<--- alter to correct DB format, everything after the / is the DB
    jdbc_user => "${DB_USER}"
    jdbc_password => "${DB_PASSWORD}"
    schedule => "* * * * *"
    statement => "select * from event"
  }
}
filter {

}
output {
  elasticsearch {
    cloud_id => "${ELASTIC_CLOUD_ID}"
    cloud_auth => "${ELASTIC_CLOUD_AUTH}"
    index => "db-report-test" #<--- Adjust the index to whatever makes sense
  }
}"""
    expected_component_output = json.dumps({
    "input": [
        {
            "id": "input_jdbc_0",
            "type": "input",
            "plugin": "jdbc",
            "config": {
                "jdbc_driver_library": "/usr/share/logstash/vendor/jar/jdbc/mysql-connector-j-9.3.0.jar",
                "jdbc_driver_class": "com.mysql.cj.jdbc.Driver",
                "jdbc_connection_string": "jdbc:mysql://${DB_HOST}:3306/semaphore",
                "jdbc_user": "${DB_USER}",
                "jdbc_password": "${DB_PASSWORD}",
                "schedule": "* * * * *",
                "statement": "select * from event"
            }
        }
    ],
    "filter": [],
    "output": [
        {
            "id": "output_elasticsearch_2",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "cloud_id": "${ELASTIC_CLOUD_ID}",
                "cloud_auth": "${ELASTIC_CLOUD_AUTH}",
                "index": "db-report-test"
            }
        }
    ]
},indent=4)

    result = logstash_config_to_components(pipeline)

    assert result == expected_component_output

def test_multiple_output():
    pipeline = """input {
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
}"""
    expected_component_output = json.dumps({
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
                    "\"message\"": "%{COMBINEDAPACHELOG}"
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
                "codec": "rubydebug"
            }
        }
    ]
}, indent=4)

    result = logstash_config_to_components(pipeline)

    assert result == expected_component_output


def test_plugin_no_config():
    pipeline = """input {
	jdbc {
		jdbc_driver_library => "/usr/share/logstash/vendor/jar/jdbc/mysql-connector-j-9.3.0.jar"
		jdbc_driver_class => "com.mysql.cj.jdbc.Driver"
		jdbc_connection_string => "jdbc:mysql://${DB_HOST}:3306/semaphore"
		jdbc_user => "${DB_USER}"
		jdbc_password => "${DB_PASSWORD}"
		schedule => "* * * * *"
		statement => "select * from event"
	}
}
filter {
	bytes {
	}
}
output {
	elasticsearch {
		cloud_id => "${ELASTIC_CLOUD_ID}"
		cloud_auth => "${ELASTIC_CLOUD_AUTH}"
		index => "db-report-test"
	}
}"""
    expected_component_output = json.dumps({
    "input": [
        {
            "id": "input_jdbc_0",
            "type": "input",
            "plugin": "jdbc",
            "config": {
                "jdbc_driver_library": "/usr/share/logstash/vendor/jar/jdbc/mysql-connector-j-9.3.0.jar",
                "jdbc_driver_class": "com.mysql.cj.jdbc.Driver",
                "jdbc_connection_string": "jdbc:mysql://${DB_HOST}:3306/semaphore",
                "jdbc_user": "${DB_USER}",
                "jdbc_password": "${DB_PASSWORD}",
                "schedule": "* * * * *",
                "statement": "select * from event"
            }
        }
    ],
    "filter": [
        {
            "id": "filter_bytes_2",
            "type": "filter",
            "plugin": "bytes",
            "config": {}
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_4",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "cloud_id": "${ELASTIC_CLOUD_ID}",
                "cloud_auth": "${ELASTIC_CLOUD_AUTH}",
                "index": "db-report-test"
            }}]}, indent=4)

    result = logstash_config_to_components(pipeline)

    assert result == expected_component_output


def test_multiple_else_if():
    pipeline = """    input { beats { port => 5044 } }
    output {
        if [type] == "apache" {
          pipeline { send_to => weblogs }
        } else if [type] == "system" {
          pipeline { send_to => syslog }
        } else if [type] == "test" {
          pipeline { send_to => syslog }
        } else {
          pipeline { send_to => fallback }
        }
    }"""
    expected_component_output = json.dumps({
        "input": [
            {
                "id": "input_beats_0",
                "type": "input",
                "plugin": "beats",
                "config": {
                    "port": 5044
                }
            }
        ],
        "filter": [],
        "output": [
            {
                "id": "output_if_2",
                "type": "output",
                "plugin": "if",
                "config": {
                    "condition": "[type] == \"apache\"",
                    "plugins": [
                        {
                            "id": "output_pipeline_3",
                            "type": "output",
                            "plugin": "pipeline",
                            "config": {
                                "send_to": "weblogs"
                            }
                        }
                    ],
                    "else_ifs": [
                        {
                            "condition": "[type] == \"system\"",
                            "plugins": [
                                {
                                    "id": "output_pipeline_5",
                                    "type": "output",
                                    "plugin": "pipeline",
                                    "config": {
                                        "send_to": "syslog"
                                    }
                                }
                            ]
                        },
                        {
                            "condition": "[type] == \"test\"",
                            "plugins": [
                                {
                                    "id": "output_pipeline_7",
                                    "type": "output",
                                    "plugin": "pipeline",
                                    "config": {
                                        "send_to": "syslog"
                                    }
                                }
                            ]
                        }
                    ],
                    "else": {
                        "plugins": [
                            {
                                "id": "output_pipeline_9",
                                "type": "output",
                                "plugin": "pipeline",
                                "config": {
                                    "send_to": "fallback"
                                }
                            }
                        ]
                    }
                }
            }
        ]
    }, indent=4)

    result = logstash_config_to_components(pipeline)

    assert result == expected_component_output

