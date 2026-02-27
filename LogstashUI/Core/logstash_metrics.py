from Core.models import Connection as ConnectionTable

import logging
logger = logging.getLogger(__name__)

def _safe_get_numeric(data, default=0):
    """
    Safely extract a numeric value from data.
    Handles cases where data might be a list, None, or invalid.
    Returns default if value cannot be converted to a number.
    """
    if data is None:
        return default
    
    # If it's a list, try to get the first element
    if isinstance(data, list):
        if len(data) == 0:
            return default
        data = data[0]
    
    # Try to convert to the appropriate numeric type
    try:
        if isinstance(data, (int, float)):
            return data
        return float(data) if '.' in str(data) else int(data)
    except (ValueError, TypeError):
        return default


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
        sort=[
            {
                "@timestamp": {
                    "order": "desc"
                }
            }
        ],
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
    logger.info(f"get_node_metrics called with: connection_name='{connection_name}', logstash_host='{logstash_host}', pipeline='{pipeline}'")
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
                                    "gte": "now-2h"
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
                                    "size": 1,
                                    "sort": [
                                        {
                                            "@timestamp": {
                                                "order": "desc"
                                            }
                                        }
                                    ],
                                    "_source": {
                                        "includes": ["logstash.node.*", "host.*", "@timestamp"]
                                    }
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
                # Add connection_id to each node bucket for linking
                conn_id = connection.get('id') or connection.get('_id') or connection.get('es_id')
                for bucket in node_bucket:
                    bucket['connection_id'] = conn_id
                    bucket['connection_name'] = connection.get('name')
                meta_agg_stats['node_buckets'] += node_bucket
                for node in node_bucket:
                    meta_agg_stats['nodes'].append(node['key'])
                    try:
                        last_hit_doc = node['last_hit']['hits']['hits'][0]['_source']['logstash']
                    except KeyError as e:
                        logger.error(f"Unable to fetch last_hit for {node['key']}", e)
                        continue

                    # Use safe numeric extraction to handle lists and missing values
                    meta_agg_stats['reloads']['successes'] += _safe_get_numeric(last_hit_doc['node']['stats']['reloads'].get('successes'))
                    meta_agg_stats['reloads']['failures'] += _safe_get_numeric(last_hit_doc['node']['stats']['reloads'].get('failures'))
                    meta_agg_stats['events']['in'] += _safe_get_numeric(last_hit_doc['node']['stats']['events'].get('in'))
                    meta_agg_stats['events']['out'] += _safe_get_numeric(last_hit_doc['node']['stats']['events'].get('out'))
                    meta_agg_stats['events']['queued'] += _safe_get_numeric(last_hit_doc['node']['stats'].get('queue', {}).get('events_count'))
                    meta_agg_stats['cpu'] += _safe_get_numeric(last_hit_doc['node']['stats'].get('os', {}).get('cpu', {}).get('percent'))
                    meta_agg_stats['heap_memory'] += _safe_get_numeric(last_hit_doc['node']['stats'].get('jvm', {}).get('mem', {}).get('heap_used_percent'))

    if meta_agg_stats['cpu']:
        meta_agg_stats['cpu'] = round(meta_agg_stats['cpu'] / len(meta_agg_stats['nodes']), 2)
    if meta_agg_stats['heap_memory']:
        meta_agg_stats['heap_memory'] = round(meta_agg_stats['heap_memory'] / len(meta_agg_stats['nodes']), 2)

    return meta_agg_stats


def get_pipeline_metrics(es_connections, connection_name="", logstash_host="", pipeline=""):
    logger.info(f"Getting pipeline metrics for connection_name='{connection_name}', logstash_host='{logstash_host}', pipeline='{pipeline}'")
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
                                "size": 1,
                                "sort": [
                                    {
                                        "@timestamp": {
                                            "order": "desc"
                                        }
                                    }
                                ],
                                "_source": {
                                    "includes": ["logstash.pipeline.*", "host.*", "@timestamp"]
                                }
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
                                    "gte": "now-2h"
                                }
                            }
                        }
                    ]
                }
            }

            if logstash_host:
                query['bool']['filter'].append({
                    "term": {
                        "logstash.pipeline.host.name": logstash_host
                    }
                })
            pipeline_stats = es.search(
                index="metrics-logstash.pipeline-*,metrics-logstash.health_report-*",
                query=query,
                aggs=aggs,
                size=0
            )


            if 'aggregations' not in pipeline_stats:
                logger.warning(f"No aggregations found for {connection['name']}")
                continue
            else:
                host_buckets = pipeline_stats['aggregations']['hosts']['buckets']
                if len(host_buckets) == 0:
                    # Only add to warnings if we're not filtering (which would naturally exclude data)
                    if not logstash_host and not connection_name:
                        logger.warning(f"No pipeline data found in aggregations for {connection['name']}")
                        meta_agg_stats['connections_with_no_data'].append({
                            'name': connection['name'],
                            'reason': 'No pipeline metrics found in the last 30 minutes'
                        })
                    else:
                        logger.warning(f"No data for {connection['name']} (filtered by connection_name='{connection_name}' or host='{logstash_host}')")

                for bucket in host_buckets:

                    meta_agg_stats['hosts'].append(bucket['key'])
                    for pipeline_bucket in bucket['pipelines']['buckets']:
                        meta_agg_stats['pipelines'].append(pipeline_bucket['key'])
                        # Add connection_id to pipeline_bucket for linking
                        # Try 'id' first, then '_id', then 'es_id'
                        conn_id = connection.get('id') or connection.get('_id') or connection.get('es_id')
                        pipeline_bucket['connection_id'] = conn_id
                        pipeline_bucket['connection_name'] = connection.get('name')
                        if not conn_id:
                            logger.warning(f"No connection ID found for {connection.get('name')}. Available keys: {connection.keys()}")
                        meta_agg_stats['pipeline_buckets'].append(pipeline_bucket)

                        try:
                            last_hit_doc = pipeline_bucket['last_hit']['hits']['hits'][0]['_source']['logstash']
                        except KeyError as e:
                            logger.warning(f"Unable to fetch last_hit for {pipeline_bucket['key']}", e)
                            continue

                        # Use safe numeric extraction to handle lists and missing values
                        pipeline_total = last_hit_doc['pipeline']['total']
                        meta_agg_stats['reloads']['successes'] += _safe_get_numeric(pipeline_total.get('reloads', {}).get('successes'))
                        meta_agg_stats['reloads']['failures'] += _safe_get_numeric(pipeline_total.get('reloads', {}).get('failures'))
                        meta_agg_stats['events']['in'] += _safe_get_numeric(pipeline_total.get('events', {}).get('in'))
                        meta_agg_stats['events']['out'] += _safe_get_numeric(pipeline_total.get('events', {}).get('out'))
                        meta_agg_stats['events']['queued'] += _safe_get_numeric(pipeline_total.get('queue', {}).get('events_count'))
                        meta_agg_stats['duration'] += _safe_get_numeric(pipeline_total.get('time', {}).get('duration', {}).get('ms'))

    if meta_agg_stats['duration']:
        meta_agg_stats['duration'] = round(meta_agg_stats['duration'] / len(meta_agg_stats['pipeline_buckets']), 2)

    return meta_agg_stats



def get_pipeline_health_report(es, pipeline_name=""):

    index = "metrics-logstash.health_report-*"
    query = {
        "bool": {
            "filter": {
                "match": {
                    "logstash.pipeline.id": pipeline_name
                }
            }
        }
    }

    results = es.search(
        query=query,
        index=index,
        size=1
    )


    if results['hits']['hits']:
        return results['hits']['hits'][0]['_source']
    else:
        return {}


