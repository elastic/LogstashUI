from Core.models import Connection as ConnectionTable


def check_for_monitoring_indices(es_connections):
    monitoring_indices = {}

    required_data_streams = [
        "metrics-logstash.plugins",
        "metrics-logstash.node",
        "metrics-logstash.pipeline",
        "logs-logstash.log",
        "metrics-logstash.health_report"
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
    if not logstash_node and not pipeline_name:
        query = {
            "match_all": {}
        }
    else:
        query = {"bool": {"filter": []}}
        if logstash_node:
            query['bool']['filter'].append({
                "term": {
                    "host.hostname": logstash_node
                }
            })
        if pipeline_name:
            query['bool']['filter'].append({
                "term": {
                    "logstash.log.pipeline_id": pipeline_name
                }
            })
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


def get_node_metrics(es_connections, connection_name="", logstash_host="", pipeline=""):
    """
    Get node-level metrics for Logstash instances.
    Query parameters:
    - connection: Filter by connection ID (optional)
    - host: Filter by host name (optional)
    - pipeline: Filter by pipeline name (optional)
    """

    meta_agg_stats = {
        "nodes": [],
        "node_buckets": [],
        "reloads": {
            "successes": 0,
            "failures": 0
        },
        "events": {
            "in": 0,
            "out": 0,
            "queued": 0
        },
        "cpu": 0,
        "heap_memory": 0
    }

    for connection in es_connections:

        if connection_name:
            if connection['name'] != connection_name:
                continue
        if connection['connection_type'] == "CENTRALIZED":
            es = connection['es']
            query = {
                "bool": {
                    "filter": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": "now-30m"
                                }
                            }
                        }
                    ]
                }
            }

            if logstash_host:
                query['bool']['filter'].append({
                    "term": {
                        "host.hostname": logstash_host
                    }
                })

            node_stats = es.search(
                index="metrics-logstash.node-*",
                query=query,
                aggs={
                    "nodes": {
                        "terms": {
                            "field": "host.hostname",
                            "size": 1000
                        },
                        "aggs": {
                            "last_hit": {
                                "top_hits": {
                                    "size": 1
                                }
                            }
                        }
                    }
                },
                size=0
            )
            if 'aggregations' not in node_stats:
                continue
            else:
                node_bucket = [bucket for bucket in node_stats['aggregations']['nodes']['buckets']]
                meta_agg_stats['node_buckets'] += node_bucket
                for node in node_bucket:
                    meta_agg_stats['nodes'].append(node['key'])
                    try:
                        last_hit_doc = node['last_hit']['hits']['hits'][0]['_source']['logstash']
                    except KeyError as e:

                        print(f"Unable to fetch last_hit for {node['key']}", e)
                        continue

                    meta_agg_stats['reloads']['successes'] += last_hit_doc['node']['stats']['reloads']['successes']
                    meta_agg_stats['reloads']['failures'] += last_hit_doc['node']['stats']['reloads']['failures']
                    meta_agg_stats['events']['in'] += last_hit_doc['node']['stats']['events']['in']
                    meta_agg_stats['events']['out'] += last_hit_doc['node']['stats']['events']['out']
                    try:
                        meta_agg_stats['events']['queued'] += last_hit_doc['node']['stats']['queue']['events_count']
                    except Exception as e:

                        print(f"Unable to fetch events_count for {node['key']}", e)
                    meta_agg_stats['cpu'] += last_hit_doc['node']['stats']['os']['cpu']['percent']

                    meta_agg_stats['heap_memory'] += last_hit_doc['node']['stats']['jvm']['mem']['heap_used_percent']

    if meta_agg_stats['cpu']:
        meta_agg_stats['cpu'] = round(meta_agg_stats['cpu'] / len(meta_agg_stats['nodes']), 2)
    if meta_agg_stats['heap_memory']:
        meta_agg_stats['heap_memory'] = round(meta_agg_stats['heap_memory'] / len(meta_agg_stats['nodes']), 2)

    return meta_agg_stats


def get_pipeline_metrics(es_connections, connection_name="", logstash_host="", pipeline=""):
    query = {
        "bool": {
            "filter": [
                {
                    "range": {
                        "@timestamp": {
                            "gte": "now-30m"
                        }
                    }
                }
            ]
        }
    }
    aggs = {
        "hosts": {
            "terms": {
                "field": "host.name",
                "size": 1000
            },
            "aggs": {
                "pipelines": {
                    "terms": {
                        "field": "logstash.pipeline.name",
                        "size": 1000
                    },
                    "aggs": {
                        "last_hit": {
                            "top_hits": {
                                "size": 1
                            }
                        }
                    }
                }
            }
        }

    }

    meta_agg_stats = {
        "hosts": [],
        "pipelines": [],
        "pipeline_buckets": [],
        "reloads": {
            "successes": 0,
            "failures": 0
        },
        "events": {
            "in": 0,
            "out": 0,
            "queued": 0
        },
        "duration": 0,
        "connections_with_no_data": []
    }

    for connection in es_connections:
        print(f"Processing connection: {connection.get('name', 'UNKNOWN')}, Type: {connection.get('connection_type', 'UNKNOWN')}")
        if connection_name:
            print(f"  Filtering for: {connection_name}")
            if connection['name'] != connection_name:
                print(f"  Skipping {connection['name']}")
                continue
        if connection['connection_type'] == "CENTRALIZED":
            es = connection['es']
            pipeline_stats = es.search(
                index="metrics-logstash.pipeline-*",
                query=query,
                aggs=aggs,
                size=0
            )
            if 'aggregations' not in pipeline_stats:
                print(f"  No aggregations found for {connection['name']}")
                continue
            else:
                host_buckets = pipeline_stats['aggregations']['hosts']['buckets']
                print(f"  Found {len(host_buckets)} host buckets for {connection['name']}")
                if len(host_buckets) == 0:
                    print(f"  WARNING: No pipeline data found in aggregations for {connection['name']}")
                    print(f"  Total hits: {pipeline_stats.get('hits', {}).get('total', {})}")
                    meta_agg_stats['connections_with_no_data'].append({
                        'name': connection['name'],
                        'reason': 'No pipeline metrics found in the last 30 minutes'
                    })
                for bucket in host_buckets:

                    meta_agg_stats['hosts'].append(bucket['key'])
                    for pipeline_bucket in bucket['pipelines']['buckets']:
                        meta_agg_stats['pipelines'].append(pipeline_bucket['key'])
                        meta_agg_stats['pipeline_buckets'].append(pipeline_bucket)

                        try:
                            last_hit_doc = pipeline_bucket['last_hit']['hits']['hits'][0]['_source']['logstash']
                        except KeyError as e:
                            print(f"Unable to fetch last_hit for {pipeline_bucket['key']}", e)
                            continue

                        meta_agg_stats['reloads']['successes'] += last_hit_doc['pipeline']['total']['reloads'][
                            'successes']
                        meta_agg_stats['reloads']['failures'] += last_hit_doc['pipeline']['total']['reloads'][
                            'failures']

                        try:
                            meta_agg_stats['events']['in'] += last_hit_doc['pipeline']['total']['events']['in']
                        except Exception as e:
                            print(e)

                        try:
                            meta_agg_stats['events']['out'] += last_hit_doc['pipeline']['total']['events']['out']
                        except Exception as e:
                            print(e)
                        try:
                            meta_agg_stats['events']['queued'] += last_hit_doc['pipeline']['total']['queue'][
                                'events_count']
                        except Exception as e:
                            print(f"Unable to fetch events_count for {pipeline_bucket['key']}", e)
                        try:
                            meta_agg_stats['duration'] += last_hit_doc['pipeline']['total']['time']['duration']['ms']
                        except Exception as e:
                            print(e)

    if meta_agg_stats['duration']:
        meta_agg_stats['duration'] = round(meta_agg_stats['duration'] / len(meta_agg_stats['pipeline_buckets']), 2)
    import json
    #print(json.dumps(meta_agg_stats))
    return meta_agg_stats
