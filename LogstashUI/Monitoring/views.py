#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from django.http import JsonResponse
from PipelineManager.models import Connection as ConnectionTable

from Common.elastic_utils import (
    get_elastic_connections_from_list,
    get_elastic_connection
)

from Common.formatters import (
    _safe_get_numeric,
    _safe_extract_value,
    _format_uptime
)

import json
import logging

logger = logging.getLogger(__name__)

def Monitoring(request):
    """Monitoring page showing Logstash metrics and health"""
    connections = list(ConnectionTable.objects.values("connection_type", "name", "host", "cloud_id", "cloud_url", "pk"))

    context = {
        "Connections": connections,
        "has_connections": len(connections) > 0
    }

    try:
        context['monitoring_indices'] = check_for_monitoring_indices(
            get_elastic_connections_from_list()
        )
    except Exception as e:
        logger.error(f"Couldn't connect!, {e}")

    return render(request, "monitoring.html", context=context)





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

        indices_response = es.cat.indices(index="*logstash*")
        
        # Handle both string and list responses from cat.indices
        if isinstance(indices_response, list):
            # List of dicts like [{'index': 'name'}, ...]
            index_names = [idx.get('index', '') for idx in indices_response]
            logger.debug(f"[{connection['name']}] Got list response with {len(index_names)} indices")
        else:
            # String response - parse index names from table format
            # Format: "health status index uuid pri rep docs.count ..."
            # Index name is the 3rd column (index 2)
            lines = indices_response.split('\n') if indices_response else []
            index_names = []
            for line in lines:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 3:
                        index_names.append(parts[2])  # 3rd column is the index name
            logger.debug(f"[{connection['name']}] Got string response, parsed {len(index_names)} index names")
            logger.debug(f"[{connection['name']}] First 3 indices: {index_names[:3]}")

        monitoring_indices[connection['name']] = {}
        monitoring_indices[connection['name']]['has_all'] = True
        monitoring_indices[connection['name']]['missing'] = []
        
        for required_stream in required_data_streams:
            # Check if any index name contains the required stream pattern
            # Handle both regular indices (metrics-logstash.node-*) and data streams (.ds-metrics-logstash.node-*)
            found = any(required_stream in idx for idx in index_names)
            if not found:
                monitoring_indices[connection['name']]['has_all'] = False
                monitoring_indices[connection['name']]['missing'].append(required_stream)
                logger.debug(f"[{connection['name']}] Missing: {required_stream}")

        if len(monitoring_indices[connection['name']]['missing']) == len(required_data_streams):
            monitoring_indices[connection['name']]['has_none'] = True
            logger.warning(f"[{connection['name']}] ALL monitoring indices missing!")
        else:
            monitoring_indices[connection['name']]['has_none'] = False
            
        logger.info(f"[{connection['name']}] Result: has_all={monitoring_indices[connection['name']]['has_all']}, has_none={monitoring_indices[connection['name']]['has_none']}, missing={len(monitoring_indices[connection['name']]['missing'])} streams")

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

    # We lazily just get the top 1000 hits.
    # This will be changed to a paginated scroll later
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
    logger.info(
        f"get_node_metrics called with: connection_name='{connection_name}', logstash_host='{logstash_host}', pipeline='{pipeline}'")
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
                        logger.error(f"Unable to fetch last_hit for {node['key']}")
                        continue

                    # Use safe numeric extraction to handle lists and missing values
                    meta_agg_stats['reloads']['successes'] += _safe_get_numeric(
                        last_hit_doc['node']['stats']['reloads'].get('successes'))
                    meta_agg_stats['reloads']['failures'] += _safe_get_numeric(
                        last_hit_doc['node']['stats']['reloads'].get('failures'))
                    meta_agg_stats['events']['in'] += _safe_get_numeric(
                        last_hit_doc['node']['stats']['events'].get('in'))
                    meta_agg_stats['events']['out'] += _safe_get_numeric(
                        last_hit_doc['node']['stats']['events'].get('out'))
                    meta_agg_stats['events']['queued'] += _safe_get_numeric(
                        last_hit_doc['node']['stats'].get('queue', {}).get('events_count'))
                    meta_agg_stats['cpu'] += _safe_get_numeric(
                        last_hit_doc['node']['stats'].get('os', {}).get('cpu', {}).get('percent'))
                    meta_agg_stats['heap_memory'] += _safe_get_numeric(
                        last_hit_doc['node']['stats'].get('jvm', {}).get('mem', {}).get('heap_used_percent'))

    if meta_agg_stats['cpu'] and meta_agg_stats['nodes']:
        meta_agg_stats['cpu'] = round(meta_agg_stats['cpu'] / len(meta_agg_stats['nodes']), 2)
    if meta_agg_stats['heap_memory'] and meta_agg_stats['nodes']:
        meta_agg_stats['heap_memory'] = round(meta_agg_stats['heap_memory'] / len(meta_agg_stats['nodes']), 2)

    return meta_agg_stats


def get_pipeline_metrics(es_connections, connection_name="", logstash_host="", pipeline=""):
    logger.info(
        f"Getting pipeline metrics for connection_name='{connection_name}', logstash_host='{logstash_host}', pipeline='{pipeline}'")
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
                            'reason': 'No pipeline metrics found in the last 2 hours'
                        })
                    else:
                        logger.warning(
                            f"No data for {connection['name']} (filtered by connection_name='{connection_name}' or host='{logstash_host}')")

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
                            logger.warning(
                                f"No connection ID found for {connection.get('name')}. Available keys: {connection.keys()}")
                        meta_agg_stats['pipeline_buckets'].append(pipeline_bucket)

                        try:
                            last_hit_doc = pipeline_bucket['last_hit']['hits']['hits'][0]['_source']['logstash']
                        except KeyError as e:
                            logger.warning(f"Unable to fetch last_hit for {pipeline_bucket['key']}")
                            continue

                        # Use safe numeric extraction to handle lists and missing values
                        pipeline_total = last_hit_doc['pipeline']['total']
                        meta_agg_stats['reloads']['successes'] += _safe_get_numeric(
                            pipeline_total.get('reloads', {}).get('successes'))
                        meta_agg_stats['reloads']['failures'] += _safe_get_numeric(
                            pipeline_total.get('reloads', {}).get('failures'))
                        meta_agg_stats['events']['in'] += _safe_get_numeric(pipeline_total.get('events', {}).get('in'))
                        meta_agg_stats['events']['out'] += _safe_get_numeric(
                            pipeline_total.get('events', {}).get('out'))
                        meta_agg_stats['events']['queued'] += _safe_get_numeric(
                            pipeline_total.get('queue', {}).get('events_count'))
                        meta_agg_stats['duration'] += _safe_get_numeric(
                            pipeline_total.get('time', {}).get('duration', {}).get('ms'))

    if meta_agg_stats['duration'] and meta_agg_stats['pipeline_buckets']:
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



def GetNodeMetrics(request):
    connection_name = request.GET.get("connection", "")
    logstash_host = request.GET.get("host", "")
    pipeline = request.GET.get("pipeline", "")

    # Get the metrics data
    metrics_data = get_node_metrics(
        get_elastic_connections_from_list(),
        connection_name,
        logstash_host,
        pipeline
    )

    # Pre-process node_buckets to extract nested data
    processed_buckets = []
    for bucket in metrics_data.get('node_buckets', []):
        try:
            node_data = bucket['last_hit']['hits']['hits'][0]['_source']['logstash']['node']['stats']
            logstash_info = node_data.get('logstash', {})

            node_name = bucket['key']
            status = logstash_info.get('status', 'unknown')
            version = logstash_info.get('version', 'N/A')
            uptime_ms = node_data.get('jvm', {}).get('uptime_in_millis', 0)
            uptime = _format_uptime(uptime_ms)

            # Try to get CPU from os.cpu.percent, fallback to process.cpu.percent
            cpu_percent = node_data.get('os', {}).get('cpu', {}).get('percent') or \
                          node_data.get('process', {}).get('cpu', {}).get('percent', 0)

            heap_percent = node_data.get('jvm', {}).get('mem', {}).get('heap_used_percent', 0)
            events_in = node_data.get('events', {}).get('in', 0)
            events_out = node_data.get('events', {}).get('out', 0)
            queued = node_data.get('queue', {}).get('events_count', 0)
            reload_success = node_data.get('reloads', {}).get('successes', 0)
            reload_failures = node_data.get('reloads', {}).get('failures', 0)

            conn_id = bucket.get('connection_id')
            conn_name = bucket.get('connection_name')

            processed_buckets.append({
                'node_name': node_name,
                'connection_id': conn_id,
                'connection_name': conn_name,
                'status': status,
                'version': version,
                'uptime': uptime,
                'cpu_percent': cpu_percent,
                'heap_percent': heap_percent,
                'events_in': events_in,
                'events_out': events_out,
                'queued': queued,
                'reload_success': reload_success,
                'reload_failures': reload_failures,
            })
        except (KeyError, IndexError) as e:
            logger.error(f"Error processing node bucket: {e}")
            continue

    metrics_data['processed_node_buckets'] = processed_buckets

    # Render as HTML template instead of JSON
    response = render(request, 'components/node_metrics.html', context=metrics_data)

    # Add available hosts to response header for JavaScript to populate dropdown
    response['X-Available-Hosts'] = json.dumps(metrics_data.get('nodes', []))

    return response



def GetPipelineHealthReport(request):
    connection_id = request.GET.get("connection_id", "")
    pipeline = request.GET.get("pipeline", "")

    try:
        # Get the health report data
        es = get_elastic_connection(connection_id)
        health_report_data = get_pipeline_health_report(es, pipeline)
        return JsonResponse(health_report_data)
    except Exception as e:
        logger.error(f"Error fetching pipeline health report for connection {connection_id}: {e.__class__.__name__}")
        return JsonResponse({"error": "Failed to fetch pipeline health report"}, status=500)


def GetPipelineMetrics(request):
    connection_name = request.GET.get("connection", "")
    logstash_host = request.GET.get("host", "")
    pipeline = request.GET.get("pipeline", "")

    # Get the metrics data
    metrics_data = get_pipeline_metrics(
        get_elastic_connections_from_list(),
        connection_name,
        logstash_host,
        pipeline
    )

    # Pre-process pipeline_buckets to extract nested data (Django can't access _source)
    processed_buckets = []
    for bucket in metrics_data.get('pipeline_buckets', []):
        try:
            pipeline_data = bucket['last_hit']['hits']['hits'][0]['_source']['logstash']['pipeline']
            pipeline_name = bucket['key']

            # Track if pipeline has issues
            has_issues = False
            missing_fields = []

            conn_id = bucket.get('connection_id')
            conn_name = bucket.get('connection_name')

            # Debug output
            if not conn_id:
                logger.warning(f"WARNING: No connection_id for pipeline {pipeline_name}. Bucket keys: {bucket.keys()}")

            results = {
                'pipeline_name': pipeline_name,
                'connection_id': conn_id,
                'connection_name': conn_name,
                'host_name': _safe_extract_value(pipeline_data.get('host', {}).get('name'), 'Unknown'),
                'events_in': _safe_extract_value(pipeline_data.get('total', {}).get('events', {}).get('in')),
                'events_out': _safe_extract_value(pipeline_data.get('total', {}).get('events', {}).get('out')),
                'events_filtered': _safe_extract_value(
                    pipeline_data.get('total', {}).get('events', {}).get('filtered')),
                'duration_ms': _safe_extract_value(
                    pipeline_data.get('total', {}).get('time', {}).get('duration', {}).get('ms')),
                'reload_success': _safe_extract_value(
                    pipeline_data.get('total', {}).get('reloads', {}).get('successes')),
                'reload_failures': _safe_extract_value(
                    pipeline_data.get('total', {}).get('reloads', {}).get('failures')),
            }

            # Handle info field (workers and batch_size)
            info = pipeline_data.get('info', {})

            # Check if info is an empty list or dict
            if isinstance(info, list) or not info:
                has_issues = True
                missing_fields.extend(['workers', 'batch_size'])
                results['workers'] = 0
                results['batch_size'] = 0
            else:
                workers = _safe_extract_value(info.get('workers'))
                batch_size = _safe_extract_value(info.get('batch_size'))

                results['workers'] = workers
                results['batch_size'] = batch_size

                if workers == 0:
                    has_issues = True
                    missing_fields.append('workers')
                if batch_size == 0:
                    has_issues = True
                    missing_fields.append('batch_size')

            # Flag pipeline if it has issues
            results['has_issues'] = has_issues
            results['missing_fields'] = missing_fields

            processed_buckets.append(results)
        except (KeyError, IndexError) as e:
            logger.error(f"Error processing pipeline bucket: {e}")
            continue

    metrics_data['processed_pipeline_buckets'] = processed_buckets

    # Render as HTML template instead of JSON
    return render(request, 'components/pipeline_metrics.html', context=metrics_data)


def GetLogs(request):
    logstash_node = request.GET.get("logstash_node", "")
    pipeline_name = request.GET.get("pipeline_name", "")
    connection_id = request.GET.get("connection_id", "")

    # Require connection_id to be provided
    if not connection_id:
        return JsonResponse({"error": "connection_id is required"}, status=400)

    try:
        es = get_elastic_connection(connection_id)
        all_logs = get_logs(es, logstash_node, pipeline_name)
        return JsonResponse(all_logs, safe=False)
    except Exception as e:
        logger.error(f"Error fetching logs for connection {connection_id}: {e.__class__.__name__}")
        return JsonResponse({"error": f"Failed to fetch logs"}, status=500)
