from API.logstash_config_parse import logstash_config_to_components
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
}''',
        {
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
}
    ),
    (
        "test-db2",
        """input {
	jdbc {
		jdbc_connection_string => "jdbc:mysql://test:3306/semaphore"
		jdbc_driver_class => "com.mysql.cj.jdbc.Driver"
		jdbc_user => "test"
		jdbc_driver_library => "/usr/share/logstash/vendor/jar/jdbc/mysql-connector-j-9.3.0.jar"
		jdbc_password => "test"
		schedule => "* * * * *"
		statement => "select * from event"
	}
}
filter {
	dissect {
	}
}
output {
	elasticsearch {
		cloud_auth => "test"
		cloud_id => "test"
		index => "db-report-test"
	}
}""",
        {
    "input": [
        {
            "id": "input_jdbc_0",
            "type": "input",
            "plugin": "jdbc",
            "config": {
                "jdbc_connection_string": "jdbc:mysql://test:3306/semaphore",
                "jdbc_driver_class": "com.mysql.cj.jdbc.Driver",
                "jdbc_user": "test",
                "jdbc_driver_library": "/usr/share/logstash/vendor/jar/jdbc/mysql-connector-j-9.3.0.jar",
                "jdbc_password": "test",
                "schedule": "* * * * *",
                "statement": "select * from event"
            }
        }
    ],
    "filter": [
        {
            "id": "filter_dissect_2",
            "type": "filter",
            "plugin": "dissect",
            "config": {}
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_4",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "cloud_auth": "test",
                "cloud_id": "test",
                "index": "db-report-test"
            }
        }
    ]
}
    )
]


@pytest.mark.parametrize(
    "name, pipeline, components",
    test_cases,
    ids=[case[0] for case in test_cases]
)
def test_logstash_config_to_components(name, pipeline, components):
    assert logstash_config_to_components(pipeline) == json.dumps(components,indent=4)
