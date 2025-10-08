def get_instances_centralized(es):
    instances = es.search(
        size=0,
        index="metrics-logstash*,logs-logstash*",
        aggs={
            "logstash_nodes": {
                "terms": {
                    "field": "host.hostname"
                }
            }
        }
    )

    return [bucket['key'] for bucket in instances['aggregations']['logstash_nodes']['buckets']]

def get_logs(es, connection_type):
    if connection_type == "CENTRALIZED":
        logstash_logs = es.search(
            size=100,
            index="logs-logstash.log-*",
            source=[
                "log.level",
                "message",
                "@timestamp"
            ],
            query={
              "match_all": {}
            }
        )

        return [hit['_source'] for hit in logstash_logs['hits']['hits']]