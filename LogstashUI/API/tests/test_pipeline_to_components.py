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
    ),
    (
        "test-asa",
        """input {
	udp {
		port => "5119"
	}
}
filter {
	mutate {
		rename => {
			"message" => "log.original"
			"host" => "observer.ip"
		}
		copy => {
			"host" => "sysloghost"
		}
	}
	grok {
		match => {
			"log.original" => [
				"%{CISCO_TAGGED_SYSLOG} %{GREEDYDATA:message}",
				"^<%{POSINT:syslog_pri}>%{DATA}: %%{DATA:ciscotag}: %{GREEDYDATA:message}",
				"^<%{POSINT:syslog_pri}>%%{DATA:ciscotag}: %{GREEDYDATA:message}"
			]
		}
	}
	grok {
		match => {
			"ciscotag" => [
				"%{WORD}-%{INT:event.severity}-%{INT:event.code}",
				"%{WORD}-%{WORD}-%{INT:event.severity}-%{INT:event.code}"
			]
		}
	}
	mutate {
		add_field => {
			"event.action" => "firewall-rule"
		}
	}
	if [event.code] == "105012" {
		grok {
			match => {
				"message" => [
					"Teardown dynamic %{WORD:network.transport} translation from %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}/%{INT:destination.port} duration %{DATA:cisco.duration_hms}$"
				]
			}
		}
	}
	else if [event.code] == "106001"{\n	dissect {
			mapping => {
				"message" => "%{network.direction} %{network.transport} connection %{event.outcome} from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} flags %{} on interface %{source_interface}"
			}
		}
		mutate {
			add_field => {
				"event.category" => "network_traffic"
			}
		}
	}\nelse if [event.code] == "106002"{\n	dissect {
			mapping => {
				"message" => "%{network.transport} Connection %{event.outcome} by %{network.direction} list %{cisco.list_id} src %{source.address} dest %{destination.address}"
			}
		}
		mutate {
			add_field => {
				"event.category" => "network_traffic"
			}
		}
	}\nelse if [event.code] == "106006"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.direction} %{network.transport} from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} on interface %{cisco.source_interface}"
			}
		}
		mutate {
			add_field => {
				"event.category" => "network_traffic"
			}
		}
	}\nelse if [event.code] == "106007"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.direction} %{network.transport} from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} due to %{network.protocol} %{}"
			}
		}
		mutate {
			add_field => {
				"event.category" => "network_traffic"
			}
		}
	}\nelse if [event.code] == "106010"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.direction} %{network.transport} src %{cisco.source_interface}:%{source.address}/%{source.port} %{} dst %{cisco.destination_interface}:%{destination.address}/%{destination.port} %{}"
			}
		}
		mutate {
			add_field => {
				"event.category" => "network_traffic"
			}
		}
	}\nelse if [event.code] == "106013"{\n	dissect {
			mapping => {
				"message" => "Dropping echo request from %{source.address} to PAT address %{destination.address}"
			}
		}
		mutate {
			add_field => {
				"network.transport" => "icmp"
				"network.direction" => "inbound"
			}
		}
	}\nelse if [event.code] == "106014"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.direction} %{network.transport} src %{cisco.source_interface}:%{source.address} %{}dst %{cisco.destination_interface}:%{destination.address} %{}"
			}
		}
		mutate {
			add_field => {
				"event.category" => "network_traffic"
			}
		}
	}\nelse if [event.code] == "106015"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.transport} (no connection) from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} flags %{} on interface %{cisco.source_interface}"
			}
		}
		mutate {
			add_field => {
				"event.category" => "nat_translation"
			}
		}
	}\nelse if [event.code] == "106016"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} IP spoof from (%{source.address}) to %{destination.address} on interface %{cisco.source_interface}"
			}
		}
	}\nelse if [event.code] == "106017"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} IP due to Land Attack from %{source.address} to %{destination.address}"
			}
		}
	}\nelse if [event.code] == "106018"{\n	dissect {
			mapping => {
				"message" => "%{network.transport} packet type %{cisco.icmp_type} %{event.outcome} by %{network.direction} list %{cisco.list_id} src %{source.address} dest %{destination.address}"
			}
		}
	}\nelse if [event.code] == "106020"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} IP teardrop fragment (size = %{}, offset = %{}) from %{source.address} to %{destination.address}"
			}
		}
	}\nelse if [event.code] == "106021"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.transport} reverse path check from %{source.address} to %{destination.address} on interface %{cisco.source_interface}"
			}
		}
	}\nelse if [event.code] == "106022"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.transport} connection spoof from %{source.address} to %{destination.address} on interface %{cisco.source_interface}"
			}
		}
	}\nelse if [event.code] == "106023"{\n	grok {
			match => {
				"message" => [
					"%{WORD:event.outcome} %{WORD:network.transport} src %{WORD:cisco.source_interface}:%{IPORHOST:source.address}?(/%{INT:source.port}) dst %{WORD:cisco.destination_interface}:%{IPORHOST:destination.address}?(/%{INT:destination.port}) by access-group \"%{DATA:cisco.list_id}\"",
					"%{WORD:event.outcome} %{WORD:network.transport} src %{WORD:cisco.source_interface}:%{IPORHOST:source.address} dst %{WORD:destination.direction}:%{IPORHOST:destination.address} \(%{DATA}\) by access-group \"%{DATA:cisco.list_id}\"",
					"%{WORD:event.outcome} %{WORD:network.transport} src %{WORD:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} dst %{WORD:cisco.destination.interface}:%{IPORHOST:destination.address}/%{INT:destination.port} by access-group \"%{DATA:cisco.list_id}\""
				]
			}
		}
		mutate {
			add_field => {
				"event.category" => "network_traffic"
			}
		}
	}\nelse if [event.code] == "106027"{\n	dissect {
			mapping => {
				"message" => "%{} %{event.outcome} src %{source.address} dst %{destination.address} by access-group \"%{cisco.list_id}\"%{}"
			}
		}
	}\nelse if [event.code] == "106100"{\n	dissect {
			mapping => {
				"message" => "access-list %{cisco.list_id} %{event.outcome} %{network.transport} %{cisco.source_interface}/%{source.address}(%{source.port}) -> %{cisco.destination_interface}/%{destination.address}(%{destination.port}) %{}"
			}
		}
	}\nelse if [event.code] == "106102"{\n	dissect {
			mapping => {
				"message" => "access-list %{cisco.list_id} %{event.outcome} %{network.transport} for user %{cisco.username} %{cisco.source_interface}/%{source.address} %{source.port} %{cisco.destination_interface}/%{destination.address} %{destination.port} %{}"
			}
		}
	}\nelse if [event.code] == "106103"{\n	dissect {
			mapping => {
				"message" => "access-list %{cisco.list_id} %{event.outcome} %{network.transport} for user %{cisco.username} %{cisco.source_interface}/%{source.address} %{source.port} %{cisco.destination_interface}/%{destination.address} %{destination.port} %{}"
			}
		}
	}\nelse if [event.code] == "113004"{\n	grok {
			match => {
				"message" => [
					"AAA user accounting %{WORD:cisco.auth_outcome} : server =%{SPACE}%{IP:source.address} : user =%{SPACE}%{DATA:source.user.name}$"
				]
			}
		}
		mutate {
			add_field => {
				"event.category" => "authentication"
			}
		}
		if [cisco.auth_outcome] == "Successful" {
			mutate {
				add_field => {
					"event.action" => "authentication_success"
				}
			}
		}
		else {\n	mutate {
				add_field => {
					"event.action" => "authentication_failure"
				}
			}
		}\n}\nelse if [event.code] == "302015" or [event.code] == "302013"{\n	grok {
			match => {
				"message" => [
					"Built %{WORD:network.direction} %{WORD:network.transport} connection %{INT} for %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} \(%{IP}|\) to %{DATA:cisco.destination_interface}:%{IPORHOST:destination.address}/%{INT:destination.port} \(%{DATA}\)",
					"Built %{WORD:network.direction} %{WORD:network.transport} connection %{INT} for %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} \(%{DATA}\)?(\(%{DATA:cisco.source_username}\)) to %{DATA:cisco.destination_interface}:%{IPORHOST:destination.address}/%{INT:destination.port} \(%{DATA}\) ?(\(%{DATA:cisco.username}\))",
					"Built %{WORD:network.direction} %{WORD:network.transport} connection %{INT:cisco.connection_id} for %{WORD:cisco.source_interface}:%{IPORHOST:source.address}\/%{INT:source.port} \(%{DATA}\) to %{WORD:cisco.destination_interface}:%{IPORHOST:destination.address}/%{INT:destination.port}"
				]
			}
		}
		mutate {
			add_field => {
				"event.category" => "nat_translation"
			}
		}
	}\nelse if [event.code] == "110003"{\n	grok {
			match => {
				"message" => [
					"%{DATA:cisco.event_error} for %{WORD:network.transport} from %{DATA:cisco.source_interface}:%{IP:source.address}\/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}\/%{INT:destination.port}"
				]
			}
		}
		mutate {
			add_field => {
				"event.category" => "error"
			}
		}
	}\nelse if [event.code] == "113019"{\n	grok {
			match => {
				"message" => [
					"Group = %{DATA:cisco.group}, Username = %{DATA:user.name}, IP = %{IP:cisco.client_vpn_ip}, %{DATA:cisco.client_vpn_action}\. Session Type: %{DATA:cisco.session_type}, Duration: %{DATA:cisco.duration}, Bytes xmt: %{INT:cisco.vpn_transmit_byte_summary}, Bytes rcv: %{INT:cisco.vpn_receive_byte_summary}, Reason: %{DATA:cisco.client_vpn_outcome}$"
				]
			}
		}
	}\nelse if [event.code] == "304001"{\n	dissect {
			mapping => {
				"message" => "%{source.address} %{}ccessed URL %{destination.address}:%{url.original}"
			}
		}
		mutate {
			add_field => {
				"event.outcome" => "allow"
			}
		}
	}\nelse if [event.code] == "304002"{\n	dissect {
			mapping => {
				"message" => "Access %{event.outcome} URL %{url.original} SRC %{source.address} %{}EST %{destination.address} on interface %{cisco.source_interface}"
			}
		}
	}\nelse if [event.code] == "305011"{\n	grok {
			match => {
				"message" => [
					"Built dynamic %{WORD:network.transport} translation from %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}/%{INT:destination.port}"
				]
			}
		}
		mutate {
			add_field => {
				"event.category" => "nat_translation"
			}
		}
	}\nelse if [event.code] == "305012"{\n	grok {
			match => {
				"message" => [
					"Teardown dynamic %{WORD:network.transport} translation from %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}/%{INT:destination.port}"
				]
			}
		}
		mutate {
			add_field => {
				"event.category" => "nat_translation"
			}
		}
	}\nelse if [event.code] == "313001"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.transport} type=%{cisco.icmp_type}, code=%{cisco.icmp_code} from %{source.address} on interface %{cisco.source_interface}"
			}
		}
	}\nelse if [event.code] == "313004"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.transport} type=%{cisco.icmp_type}, from%{}addr %{source.address} on interface %{cisco.source_interface} to %{destination.address}: no matching session"
			}
		}
	}\nelse if [event.code] == "313005"{\n	dissect {
			mapping => {
				"message" => "No matching connection for %{network.transport} error message: %{} on %{cisco.source_interface} interface.%{}riginal IP payload: %{}"
			}
		}
	}\nelse if [event.code] == "313008"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} %{network.transport} type=%{cisco.icmp_type} , code=%{cisco.icmp_code} from %{source.address} on interface %{cisco.source_interface}"
			}
		}
	}\nelse if [event.code] == "313009"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} invalid %{network.transport} code %{cisco.icmp_code} , for %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}"
			}
		}
	}\nelse if [event.code] == "322001"{\n	dissect {
			mapping => {
				"message" => "%{event.outcome} MAC address %{source.mac}, possible spoof attempt on interface %{cisco.source_interface}"
			}
		}
	}\nelse if [event.code] == "338001"{\n	dissect {
			mapping => {
				"message" => "Dynamic filter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
	}\nelse if [event.code] == "338002"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}"
			}
		}
		mutate {
			add_field => {
				"server.domain" => "[destination.domain]"
			}
		}
	}\nelse if [event.code] == "338003"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
	}\nelse if [event.code] == "338004"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
	}\nelse if [event.code] == "338005"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
		mutate {
			add_field => {
				"server.domain" => "[source.domain]"
			}
		}
	}\nelse if [event.code] == "338006"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
		mutate {
			add_field => {
				"server.domain" => "server.domain"
			}
		}
	}\nelse if [event.code] == "338007"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
	}\nelse if [event.code] == "338008"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
	}\nelse if [event.code] == "338101"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}"
			}
		}
		mutate {
			add_field => {
				"server.domain" => "server.domain"
			}
		}
	}\nelse if [event.code] == "338102"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}"
			}
		}
		mutate {
			add_field => {
				"server.domain" => "server.domain"
			}
		}
	}\nelse if [event.code] == "338103"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{}"
			}
		}
	}\nelse if [event.code] == "338104"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{}"
			}
		}
	}\nelse if [event.code] == "338201"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
		mutate {
			add_field => {
				"server.domain" => "server.domain"
			}
		}
	}\nelse if [event.code] == "338202"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
		mutate {
			add_field => {
				"server.domain" => "server.domain"
			}
		}
	}\nelse if [event.code] == "338203"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
		mutate {
			add_field => {
				"server.domain" => "server.domain"
			}
		}
	}\nelse if [event.code] == "338204"{\n	dissect {
			mapping => {
				"message" => "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
			}
		}
		mutate {
			add_field => {
				"server.domain" => "server.domain"
			}
		}
	}\nelse if [event.code] == "338301"{\n	dissect {
			mapping => {
				"message" => "Intercepted DNS reply for domain %{source.domain} from %{cisco.source_interface}:%{source.address}/%{source.port} to %{cisco.destination_interface}:%{destination.address}/%{destination.port}, matched %{cisco.list_id}"
			}
		}
		mutate {
			add_field => {
				"client.address" => "client.address"
			}
		}
		mutate {
			add_field => {
				"client.port" => "client.port"
			}
		}
		mutate {
			add_field => {
				"server.address" => "server.address"
			}
		}
		mutate {
			add_field => {
				"server.port" => "server.port"
			}
		}
	}\nelse if [event.code] in ["302014", "302016", "302018", "302021", "302036", "302304", "302306", "302020"]{\n	grok {
			pattern_definitions => {
				"NOTCOLON" => "[^:]*"
				"ECSSOURCEIPORHOST" => "(?:%{IP:source.address}|%{HOSTNAME:source.domain})"
				"ECSDESTIPORHOST" => "(?:%{IP:destination.address}|%{HOSTNAME:destination.domain})"
				"MAPPEDSRC" => "(?:%{DATA:cisco.mapped_source_ip}|%{HOSTNAME})"
			}
			match => {
				"message" => [
					"Teardown %{NOTSPACE:network.transport} (?:state-bypass )?connection %{NOTSPACE:cisco.connection_id} (?:for|from) %{NOTCOLON}:%{DATA:source.address}/%{NUMBER:source.port:int}?(\(%{DATA:cisco.source_username}\)|) ?to %{NOTCOLON:cisco.destination_interface}:%{DATA:destination.address}/%{NUMBER:destination.port:int}?(\(%{DATA:cisco.source_username}\)|) ?(?:duration %{TIME:cisco.duration_hms} bytes %{NUMBER:network.bytes:int})%{GREEDYDATA}",
					"Teardown %{NOTSPACE:network.transport} (?:state-bypass )?connection %{NOTSPACE:cisco.connection_id} (?:for|from) %{NOTCOLON}:%{DATA:source.address}/%{NUMBER:source.port:int} (?:%{NOTSPACE:cisco.source_username} )?to %{NOTCOLON:cisco.destination_interface}:%{DATA:destination.address}/%{NUMBER:destination.port:int} (?:%{NOTSPACE:cisco.destination_username} )?(?:duration %{TIME:cisco.duration_hms} bytes %{NUMBER:network.bytes:int})%{GREEDYDATA}",
					"Teardown %{NOTSPACE:network.transport} connection for faddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSDESTIPORHOST}/%{NUMBER} (?:%{NOTSPACE:cisco.destination_username} )?gaddr (?:%{NOTCOLON}:)?%{MAPPEDSRC}/%{NUMBER} laddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSSOURCEIPORHOST}/%{NUMBER}(?: %{NOTSPACE:cisco.source_username})?%{GREEDYDATA}",
					"Built %{WORD:network.direction} %{NOTSPACE:network.transport} connection for faddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSDESTIPORHOST}/%{NUMBER} (?:%{NOTSPACE:cisco.destination_username} )?gaddr (?:%{NOTCOLON}:)?%{MAPPEDSRC}/%{NUMBER} laddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSSOURCEIPORHOST}/%{NUMBER}(?: %{NOTSPACE:cisco.source_username})?%{GREEDYDATA}"
				]
			}
		}
		mutate {
			add_field => {
				"event.category" => "nat_translation"
			}
		}
	}\nelse if [event.code] == "419002"{\n	grok {
			match => {
				"message" => [
					"%{DATA:cisco.event_error} from %{WORD:cisco.source_interface}:%{IPORHOST:source.address}\/%{INT:source.port} to %{WORD:cisco.destination_interface}:%{IPORHOST:destination.address}\/%{INT:destination.port}"
				]
			}
		}
		mutate {
			add_field => {
				"event.category" => "error"
			}
		}
	}\nelse if [event.code] in ["733100", "752015", "752012"]{\n	grok {
			match => {
				"message" => [
					"%{GREEDYDATA:cisco.event_error}"
				]
			}
		}
		mutate {
			add_field => {
				"event.category" => "error"
			}
		}
	}\nelse if [event.code] == "716002"{\n	grok {
			match => {
				"message" => [
					"Group \<%{DATA:cisco.group} User \<%{DATA:user.name}\> IP \<%{IP:cisco.client_vpn_ip}\> WebVPN session %{WORD:cisco.client_vpn_session_outcome}\: %{DATA:cisco.web_vpn_action}\."
				]
			}
		}
	}\nelse if [event.code] in ['722022', '722033', '722055', '722051', '113039', '722023', '722037']{\n	grok {
			match => {
				"message" => [
					"Group \<%{DATA:cisco.group} User \<%{DATA:user.name}\> IP \<%{IP:cisco.client_vpn_ip}\> %{GREEDYDATA:cisco.message}"
				]
			}
		}
	}\nelse {\n	grok {
			match => {
				"message" => [
					"forced_failure"
				]
			}
		}
	}\n	if [event.category] == "nat_translation" {
		drop {
		}
	}
	if [source.address] {
		grok {
			match => {
				"source.address" => [
					"(?:%{IP:source.ip}|%{GREEDYDATA:source.domain})"
				]
			}
		}
	}
	if [destination.address] {
		grok {
			match => {
				"destination.address" => [
					"(?:%{IP:destination.ip}|%{GREEDYDATA:destination.domain})"
				]
			}
		}
	}
	if [client.address] {
		grok {
			match => {
				"client.address" => [
					"(?:%{IP:client.ip}|%{GREEDYDATA:client.domain})"
				]
			}
		}
	}
	if [server.address] {
		grok {
			match => {
				"server.address" => [
					"(?:%{IP:server.ip}|%{GREEDYDATA:server.domain})"
				]
			}
		}
	}
	mutate {
		lowercase => ["network.transport", "network.protocol", "network.direction", "event.outcome"]
	}
	if [event.outcome] == "est-allowed" {
		mutate {
			update => {
				"event.outcome" => "allow"
			}
		}
	}
	else if [event.outcome] == "permitted"{\n	mutate {
			update => {
				"event.outcome" => "allow"
			}
		}
	}\nelse if [event.outcome] == "denied"{\n	mutate {
			update => {
				"event.outcome" => "deny"
			}
		}
	}\nelse if [event.outcome] == "dropped"{\n	mutate {
			update => {
				"event.outcome" => "deny"
			}
		}
	}\n	if [network.transport] == "icmpv6" {
		mutate {
			update => {
				"network.transport" => "ipv6-icmp"
			}
		}
	}
	translate {
		field => "network.transport"
		destination => "network.iana_number"
		dictionary => {
			"icmp" => "1"
			"igmp" => "2"
			"ipv4" => "4"
			"tcp" => "6"
			"egp" => "8"
			"igp" => "9"
			"pup" => "12"
			"udp" => "17"
			"rdp" => "27"
			"irtp" => "28"
			"dccp" => "33"
			"idpr" => "35"
			"ipv6" => "41"
			"ipv6-route" => "43"
			"ipv6-frag" => "44"
			"rsvp" => "46"
			"gre" => "47"
			"esp" => "50"
			"ipv6-icmp" => "58"
			"ipv6-nonxt" => "59"
			"ipv6-opts" => "60"
		}
	}
	mutate {
		remove_field => ["ciscotag", "timestamp"]
	}
	mutate {
		add_field => {
			"event.module" => "cisco"
			"event.dataset" => "asa"
		}
	}
	translate {
		field => "[event.code]"
		destination => "event"
		dictionary_path => ""
	}
	translate {
		field => "[source.ip]"
		destination => "threat"
		dictionary_path => ""
	}
	translate {
		field => "[destination.ip]"
		destination => "threat"
		dictionary_path => ""
	}
	translate {
		field => "[event.severity]"
		destination => "[log.level]"
		dictionary => {
			"0" => "emergency"
			"1" => "alert"
			"2" => "critical"
			"3" => "error"
			"4" => "warning"
			"5" => "notification"
			"6" => "informational"
			"7" => "debug"
		}
	}
}
output {
	elasticsearch {
		user => ""
		password => ""
		hosts => [""]
		pipeline => "asa"
		index => "asa-1.2"
	}
}""",
{
    "input": [
        {
            "id": "input_udp_0",
            "type": "input",
            "plugin": "udp",
            "config": {
                "port": 5119
            }
        }
    ],
    "filter": [
        {
            "id": "filter_mutate_2",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "rename": {
                    "\"message\"": "log.original",
                    "\"host\"": "observer.ip"
                },
                "copy": {
                    "\"host\"": "sysloghost"
                }
            }
        },
        {
            "id": "filter_grok_4",
            "type": "filter",
            "plugin": "grok",
            "config": {
                "match": {
                    "\"log.original\"": [
                        "%{CISCO_TAGGED_SYSLOG} %{GREEDYDATA:message}",
                        "^<%{POSINT:syslog_pri}>%{DATA}: %%{DATA:ciscotag}: %{GREEDYDATA:message}",
                        "^<%{POSINT:syslog_pri}>%%{DATA:ciscotag}: %{GREEDYDATA:message}"
                    ]
                }
            }
        },
        {
            "id": "filter_grok_6",
            "type": "filter",
            "plugin": "grok",
            "config": {
                "match": {
                    "\"ciscotag\"": [
                        "%{WORD}-%{INT:event.severity}-%{INT:event.code}",
                        "%{WORD}-%{WORD}-%{INT:event.severity}-%{INT:event.code}"
                    ]
                }
            }
        },
        {
            "id": "filter_mutate_8",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "add_field": {
                    "\"event.action\"": "firewall-rule"
                }
            }
        },
        {
            "id": "filter_if_10",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[event.code] == \"105012\"",
                "plugins": [
                    {
                        "id": "filter_grok_11",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"message\"": [
                                    "Teardown dynamic %{WORD:network.transport} translation from %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}/%{INT:destination.port} duration %{DATA:cisco.duration_hms}$"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [
                    {
                        "condition": "[event.code] == \"106001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_13",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{network.direction} %{network.transport} connection %{event.outcome} from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} flags %{} on interface %{source_interface}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_15",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106002\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_17",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{network.transport} Connection %{event.outcome} by %{network.direction} list %{cisco.list_id} src %{source.address} dest %{destination.address}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_19",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106006\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_21",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.direction} %{network.transport} from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} on interface %{cisco.source_interface}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_23",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106007\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_25",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.direction} %{network.transport} from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} due to %{network.protocol} %{}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_27",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106010\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_29",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.direction} %{network.transport} src %{cisco.source_interface}:%{source.address}/%{source.port} %{} dst %{cisco.destination_interface}:%{destination.address}/%{destination.port} %{}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_31",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106013\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_33",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dropping echo request from %{source.address} to PAT address %{destination.address}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_35",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"network.transport\"": "icmp",
                                        "\"network.direction\"": "inbound"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106014\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_37",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.direction} %{network.transport} src %{cisco.source_interface}:%{source.address} %{}dst %{cisco.destination_interface}:%{destination.address} %{}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_39",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106015\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_41",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} (no connection) from %{source.address}/%{source.port} to %{destination.address}/%{destination.port} flags %{} on interface %{cisco.source_interface}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_43",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106016\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_45",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} IP spoof from (%{source.address}) to %{destination.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106017\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_47",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} IP due to Land Attack from %{source.address} to %{destination.address}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106018\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_49",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{network.transport} packet type %{cisco.icmp_type} %{event.outcome} by %{network.direction} list %{cisco.list_id} src %{source.address} dest %{destination.address}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106020\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_51",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} IP teardrop fragment (size = %{}, offset = %{}) from %{source.address} to %{destination.address}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106021\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_53",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} reverse path check from %{source.address} to %{destination.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106022\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_55",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} connection spoof from %{source.address} to %{destination.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106023\"",
                        "plugins": [
                            {
                                "id": "filter_grok_57",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "%{WORD:event.outcome} %{WORD:network.transport} src %{WORD:cisco.source_interface}:%{IPORHOST:source.address}?(/%{INT:source.port}) dst %{WORD:cisco.destination_interface}:%{IPORHOST:destination.address}?(/%{INT:destination.port}) by access-group \\\"%{DATA:cisco.list_id}\\\"",
                                            "%{WORD:event.outcome} %{WORD:network.transport} src %{WORD:cisco.source_interface}:%{IPORHOST:source.address} dst %{WORD:destination.direction}:%{IPORHOST:destination.address} \\(%{DATA}\\) by access-group \\\"%{DATA:cisco.list_id}\\\"",
                                            "%{WORD:event.outcome} %{WORD:network.transport} src %{WORD:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} dst %{WORD:cisco.destination.interface}:%{IPORHOST:destination.address}/%{INT:destination.port} by access-group \\\"%{DATA:cisco.list_id}\\\""
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_59",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "network_traffic"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106027\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_61",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{} %{event.outcome} src %{source.address} dst %{destination.address} by access-group \\\"%{cisco.list_id}\\\"%{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106100\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_63",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "access-list %{cisco.list_id} %{event.outcome} %{network.transport} %{cisco.source_interface}/%{source.address}(%{source.port}) -> %{cisco.destination_interface}/%{destination.address}(%{destination.port}) %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106102\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_65",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "access-list %{cisco.list_id} %{event.outcome} %{network.transport} for user %{cisco.username} %{cisco.source_interface}/%{source.address} %{source.port} %{cisco.destination_interface}/%{destination.address} %{destination.port} %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"106103\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_67",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "access-list %{cisco.list_id} %{event.outcome} %{network.transport} for user %{cisco.username} %{cisco.source_interface}/%{source.address} %{source.port} %{cisco.destination_interface}/%{destination.address} %{destination.port} %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"113004\"",
                        "plugins": [
                            {
                                "id": "filter_grok_69",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "AAA user accounting %{WORD:cisco.auth_outcome} : server =%{SPACE}%{IP:source.address} : user =%{SPACE}%{DATA:source.user.name}$"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_71",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "authentication"
                                    }
                                }
                            },
                            {
                                "id": "filter_if_73",
                                "type": "filter",
                                "plugin": "if",
                                "config": {
                                    "condition": "[cisco.auth_outcome] == \"Successful\"",
                                    "plugins": [
                                        {
                                            "id": "filter_mutate_74",
                                            "type": "filter",
                                            "plugin": "mutate",
                                            "config": {
                                                "add_field": {
                                                    "\"event.action\"": "authentication_success"
                                                }
                                            }
                                        }
                                    ],
                                    "else_ifs": [],
                                    "else": {
                                        "plugins": [
                                            {
                                                "id": "filter_mutate_76",
                                                "type": "filter",
                                                "plugin": "mutate",
                                                "config": {
                                                    "add_field": {
                                                        "\"event.action\"": "authentication_failure"
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"302015\" or [event.code] == \"302013\"",
                        "plugins": [
                            {
                                "id": "filter_grok_78",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Built %{WORD:network.direction} %{WORD:network.transport} connection %{INT} for %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} \\(%{IP}|\\) to %{DATA:cisco.destination_interface}:%{IPORHOST:destination.address}/%{INT:destination.port} \\(%{DATA}\\)",
                                            "Built %{WORD:network.direction} %{WORD:network.transport} connection %{INT} for %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} \\(%{DATA}\\)?(\\(%{DATA:cisco.source_username}\\)) to %{DATA:cisco.destination_interface}:%{IPORHOST:destination.address}/%{INT:destination.port} \\(%{DATA}\\) ?(\\(%{DATA:cisco.username}\\))",
                                            "Built %{WORD:network.direction} %{WORD:network.transport} connection %{INT:cisco.connection_id} for %{WORD:cisco.source_interface}:%{IPORHOST:source.address}\\/%{INT:source.port} \\(%{DATA}\\) to %{WORD:cisco.destination_interface}:%{IPORHOST:destination.address}/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_80",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"110003\"",
                        "plugins": [
                            {
                                "id": "filter_grok_82",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "%{DATA:cisco.event_error} for %{WORD:network.transport} from %{DATA:cisco.source_interface}:%{IP:source.address}\\/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}\\/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_84",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "error"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"113019\"",
                        "plugins": [
                            {
                                "id": "filter_grok_86",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Group = %{DATA:cisco.group}, Username = %{DATA:user.name}, IP = %{IP:cisco.client_vpn_ip}, %{DATA:cisco.client_vpn_action}\\. Session Type: %{DATA:cisco.session_type}, Duration: %{DATA:cisco.duration}, Bytes xmt: %{INT:cisco.vpn_transmit_byte_summary}, Bytes rcv: %{INT:cisco.vpn_receive_byte_summary}, Reason: %{DATA:cisco.client_vpn_outcome}$"
                                        ]
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"304001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_88",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{source.address} %{}ccessed URL %{destination.address}:%{url.original}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_90",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.outcome\"": "allow"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"304002\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_92",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Access %{event.outcome} URL %{url.original} SRC %{source.address} %{}EST %{destination.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"305011\"",
                        "plugins": [
                            {
                                "id": "filter_grok_94",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Built dynamic %{WORD:network.transport} translation from %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_96",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"305012\"",
                        "plugins": [
                            {
                                "id": "filter_grok_98",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Teardown dynamic %{WORD:network.transport} translation from %{DATA:cisco.source_interface}:%{IPORHOST:source.address}/%{INT:source.port} to %{DATA:cisco.destination_interface}:%{IP:destination.address}/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_100",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_102",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} type=%{cisco.icmp_type}, code=%{cisco.icmp_code} from %{source.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313004\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_104",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} type=%{cisco.icmp_type}, from%{}addr %{source.address} on interface %{cisco.source_interface} to %{destination.address}: no matching session"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313005\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_106",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "No matching connection for %{network.transport} error message: %{} on %{cisco.source_interface} interface.%{}riginal IP payload: %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313008\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_108",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} %{network.transport} type=%{cisco.icmp_type} , code=%{cisco.icmp_code} from %{source.address} on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"313009\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_110",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} invalid %{network.transport} code %{cisco.icmp_code} , for %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"322001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_112",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "%{event.outcome} MAC address %{source.mac}, possible spoof attempt on interface %{cisco.source_interface}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338001\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_114",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic filter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338002\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_116",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_118",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "[destination.domain]"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338003\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_120",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338004\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_122",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338005\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_124",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_126",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "[source.domain]"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338006\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_128",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_130",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338007\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_132",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338008\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_134",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} black%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338101\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_136",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_138",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338102\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_140",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_142",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338103\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_144",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338104\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_146",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} white%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{}"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338201\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_148",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_150",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338202\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_152",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_154",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338203\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_156",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}source %{} resolved from %{cisco.list_id} list: %{source.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_158",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338204\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_160",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Dynamic %{}ilter %{event.outcome} grey%{}d %{network.transport} traffic from %{cisco.source_interface}:%{source.address}/%{source.port} (%{cisco.mapped_source_ip}/%{cisco.mapped_source_port}) to %{cisco.destination_interface}:%{destination.address}/%{destination.port} (%{cisco.mapped_destination_ip}/%{cisco.mapped_destination_port})%{}destination %{} resolved from %{cisco.list_id} list: %{destination.domain}, threat-level: %{cisco.threat_level}, category: %{cisco.threat_category}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_162",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.domain\"": "server.domain"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"338301\"",
                        "plugins": [
                            {
                                "id": "filter_dissect_164",
                                "type": "filter",
                                "plugin": "dissect",
                                "config": {
                                    "mapping": {
                                        "\"message\"": "Intercepted DNS reply for domain %{source.domain} from %{cisco.source_interface}:%{source.address}/%{source.port} to %{cisco.destination_interface}:%{destination.address}/%{destination.port}, matched %{cisco.list_id}"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_166",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"client.address\"": "client.address"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_168",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"client.port\"": "client.port"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_170",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.address\"": "server.address"
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_172",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"server.port\"": "server.port"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] in [\"302014\", \"302016\", \"302018\", \"302021\", \"302036\", \"302304\", \"302306\", \"302020\"]",
                        "plugins": [
                            {
                                "id": "filter_grok_174",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "pattern_definitions": {
                                        "\"NOTCOLON\"": "[^:]*",
                                        "\"ECSSOURCEIPORHOST\"": "(?:%{IP:source.address}|%{HOSTNAME:source.domain})",
                                        "\"ECSDESTIPORHOST\"": "(?:%{IP:destination.address}|%{HOSTNAME:destination.domain})",
                                        "\"MAPPEDSRC\"": "(?:%{DATA:cisco.mapped_source_ip}|%{HOSTNAME})"
                                    },
                                    "match": {
                                        "\"message\"": [
                                            "Teardown %{NOTSPACE:network.transport} (?:state-bypass )?connection %{NOTSPACE:cisco.connection_id} (?:for|from) %{NOTCOLON}:%{DATA:source.address}/%{NUMBER:source.port:int}?(\\(%{DATA:cisco.source_username}\\)|) ?to %{NOTCOLON:cisco.destination_interface}:%{DATA:destination.address}/%{NUMBER:destination.port:int}?(\\(%{DATA:cisco.source_username}\\)|) ?(?:duration %{TIME:cisco.duration_hms} bytes %{NUMBER:network.bytes:int})%{GREEDYDATA}",
                                            "Teardown %{NOTSPACE:network.transport} (?:state-bypass )?connection %{NOTSPACE:cisco.connection_id} (?:for|from) %{NOTCOLON}:%{DATA:source.address}/%{NUMBER:source.port:int} (?:%{NOTSPACE:cisco.source_username} )?to %{NOTCOLON:cisco.destination_interface}:%{DATA:destination.address}/%{NUMBER:destination.port:int} (?:%{NOTSPACE:cisco.destination_username} )?(?:duration %{TIME:cisco.duration_hms} bytes %{NUMBER:network.bytes:int})%{GREEDYDATA}",
                                            "Teardown %{NOTSPACE:network.transport} connection for faddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSDESTIPORHOST}/%{NUMBER} (?:%{NOTSPACE:cisco.destination_username} )?gaddr (?:%{NOTCOLON}:)?%{MAPPEDSRC}/%{NUMBER} laddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSSOURCEIPORHOST}/%{NUMBER}(?: %{NOTSPACE:cisco.source_username})?%{GREEDYDATA}",
                                            "Built %{WORD:network.direction} %{NOTSPACE:network.transport} connection for faddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSDESTIPORHOST}/%{NUMBER} (?:%{NOTSPACE:cisco.destination_username} )?gaddr (?:%{NOTCOLON}:)?%{MAPPEDSRC}/%{NUMBER} laddr (?:%{NOTCOLON:cisco.source_interface}:)?%{ECSSOURCEIPORHOST}/%{NUMBER}(?: %{NOTSPACE:cisco.source_username})?%{GREEDYDATA}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_176",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "nat_translation"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"419002\"",
                        "plugins": [
                            {
                                "id": "filter_grok_178",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "%{DATA:cisco.event_error} from %{WORD:cisco.source_interface}:%{IPORHOST:source.address}\\/%{INT:source.port} to %{WORD:cisco.destination_interface}:%{IPORHOST:destination.address}\\/%{INT:destination.port}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_180",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "error"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] in [\"733100\", \"752015\", \"752012\"]",
                        "plugins": [
                            {
                                "id": "filter_grok_182",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "%{GREEDYDATA:cisco.event_error}"
                                        ]
                                    }
                                }
                            },
                            {
                                "id": "filter_mutate_184",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "add_field": {
                                        "\"event.category\"": "error"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] == \"716002\"",
                        "plugins": [
                            {
                                "id": "filter_grok_186",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Group \\<%{DATA:cisco.group} User \\<%{DATA:user.name}\\> IP \\<%{IP:cisco.client_vpn_ip}\\> WebVPN session %{WORD:cisco.client_vpn_session_outcome}\\: %{DATA:cisco.web_vpn_action}\\."
                                        ]
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.code] in ['722022', '722033', '722055', '722051', '113039', '722023', '722037']",
                        "plugins": [
                            {
                                "id": "filter_grok_188",
                                "type": "filter",
                                "plugin": "grok",
                                "config": {
                                    "match": {
                                        "\"message\"": [
                                            "Group \\<%{DATA:cisco.group} User \\<%{DATA:user.name}\\> IP \\<%{IP:cisco.client_vpn_ip}\\> %{GREEDYDATA:cisco.message}"
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                ],
                "else": {
                    "plugins": [
                        {
                            "id": "filter_grok_190",
                            "type": "filter",
                            "plugin": "grok",
                            "config": {
                                "match": {
                                    "\"message\"": [
                                        "forced_failure"
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        },
        {
            "id": "filter_if_192",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[event.category] == \"nat_translation\"",
                "plugins": [
                    {
                        "id": "filter_drop_193",
                        "type": "filter",
                        "plugin": "drop",
                        "config": {}
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_if_195",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[source.address]",
                "plugins": [
                    {
                        "id": "filter_grok_196",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"source.address\"": [
                                    "(?:%{IP:source.ip}|%{GREEDYDATA:source.domain})"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_if_198",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[destination.address]",
                "plugins": [
                    {
                        "id": "filter_grok_199",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"destination.address\"": [
                                    "(?:%{IP:destination.ip}|%{GREEDYDATA:destination.domain})"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_if_201",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[client.address]",
                "plugins": [
                    {
                        "id": "filter_grok_202",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"client.address\"": [
                                    "(?:%{IP:client.ip}|%{GREEDYDATA:client.domain})"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_if_204",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[server.address]",
                "plugins": [
                    {
                        "id": "filter_grok_205",
                        "type": "filter",
                        "plugin": "grok",
                        "config": {
                            "match": {
                                "\"server.address\"": [
                                    "(?:%{IP:server.ip}|%{GREEDYDATA:server.domain})"
                                ]
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_mutate_207",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "lowercase": [
                    "network.transport",
                    "network.protocol",
                    "network.direction",
                    "event.outcome"
                ]
            }
        },
        {
            "id": "filter_if_209",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[event.outcome] == \"est-allowed\"",
                "plugins": [
                    {
                        "id": "filter_mutate_210",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "update": {
                                "\"event.outcome\"": "allow"
                            }
                        }
                    }
                ],
                "else_ifs": [
                    {
                        "condition": "[event.outcome] == \"permitted\"",
                        "plugins": [
                            {
                                "id": "filter_mutate_212",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "update": {
                                        "\"event.outcome\"": "allow"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.outcome] == \"denied\"",
                        "plugins": [
                            {
                                "id": "filter_mutate_214",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "update": {
                                        "\"event.outcome\"": "deny"
                                    }
                                }
                            }
                        ]
                    },
                    {
                        "condition": "[event.outcome] == \"dropped\"",
                        "plugins": [
                            {
                                "id": "filter_mutate_216",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "update": {
                                        "\"event.outcome\"": "deny"
                                    }
                                }
                            }
                        ]
                    }
                ],
                "else": null
            }
        },
        {
            "id": "filter_if_218",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": "[network.transport] == \"icmpv6\"",
                "plugins": [
                    {
                        "id": "filter_mutate_219",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "update": {
                                "\"network.transport\"": "ipv6-icmp"
                            }
                        }
                    }
                ],
                "else_ifs": [],
                "else": null
            }
        },
        {
            "id": "filter_translate_221",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "network.transport",
                "destination": "network.iana_number",
                "dictionary": {
                    "\"icmp\"": "1",
                    "\"igmp\"": "2",
                    "\"ipv4\"": "4",
                    "\"tcp\"": "6",
                    "\"egp\"": "8",
                    "\"igp\"": "9",
                    "\"pup\"": "12",
                    "\"udp\"": "17",
                    "\"rdp\"": "27",
                    "\"irtp\"": "28",
                    "\"dccp\"": "33",
                    "\"idpr\"": "35",
                    "\"ipv6\"": "41",
                    "\"ipv6-route\"": "43",
                    "\"ipv6-frag\"": "44",
                    "\"rsvp\"": "46",
                    "\"gre\"": "47",
                    "\"esp\"": "50",
                    "\"ipv6-icmp\"": "58",
                    "\"ipv6-nonxt\"": "59",
                    "\"ipv6-opts\"": "60"
                }
            }
        },
        {
            "id": "filter_mutate_223",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "remove_field": [
                    "ciscotag",
                    "timestamp"
                ]
            }
        },
        {
            "id": "filter_mutate_225",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "add_field": {
                    "\"event.module\"": "cisco",
                    "\"event.dataset\"": "asa"
                }
            }
        },
        {
            "id": "filter_translate_227",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "[event.code]",
                "destination": "event",
                "dictionary_path": ""
            }
        },
        {
            "id": "filter_translate_229",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "[source.ip]",
                "destination": "threat",
                "dictionary_path": ""
            }
        },
        {
            "id": "filter_translate_231",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "[destination.ip]",
                "destination": "threat",
                "dictionary_path": ""
            }
        },
        {
            "id": "filter_translate_233",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "field": "[event.severity]",
                "destination": "[log.level]",
                "dictionary": {
                    "\"0\"": "emergency",
                    "\"1\"": "alert",
                    "\"2\"": "critical",
                    "\"3\"": "error",
                    "\"4\"": "warning",
                    "\"5\"": "notification",
                    "\"6\"": "informational",
                    "\"7\"": "debug"
                }
            }
        }
    ],
    "output": [
        {
            "id": "output_elasticsearch_235",
            "type": "output",
            "plugin": "elasticsearch",
            "config": {
                "user": "",
                "password": "",
                "hosts": [
                    ""
                ],
                "pipeline": "asa",
                "index": "asa-1.2"
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
