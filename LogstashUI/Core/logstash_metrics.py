
def check_for_monitoring_indices(es_connections):
    monitoring_indices = {}

    required_data_streams = [
        "metrics-logstash.stack_monitoring.node",
        "metrics-logstash.plugins",
        "metrics-logstash.node",
        "metrics-logstash.pipeline",
        "logs-logstash.log",
        "metrics-logstash.health_report",
        "metrics-logstash.stack_monitoring"
    ]

    for connection in es_connections:
        es = connection['es']

        indices = es.cat.indices(index="*logstash*")

        monitoring_indices[connection['name']] = {}
        monitoring_indices[connection['name']]['has_all'] = True

        monitoring_indices[connection['name']]['missing'] = []
        for required_stream in required_data_streams:
            if not required_stream in indices:
                monitoring_indices[connection['name']]['has_all'] = False
                monitoring_indices[connection['name']]['missing'].append(required_stream)

        if len(monitoring_indices[connection['name']]['missing']) == len(required_data_streams):
            monitoring_indices[connection['name']]['has_none'] = True

    return monitoring_indices

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

    if 'aggregations' not in instances:
        return []

    return [bucket['key'] for bucket in instances['aggregations']['logstash_nodes']['buckets']]

def get_logs(es, logstash_node="", pipeline_name=""):
    if not logstash_node:
        query = {
            "match_all": {}
        }
    else:
        query = {
            "term": {
                "host.hostname": logstash_node
            }
        }
    logstash_logs = es.search(
        size=1000,
        index="logs-logstash.log-*",
        source=[
            "log.level",
            "message",
            "@timestamp"
        ],
        query=query
    )

    return [hit['_source'] for hit in logstash_logs['hits']['hits']]