#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse
from datetime import datetime, timedelta, timezone

from Common.elastic_utils import get_elastic_connection
from Common.formatters import format_display_name
from PipelineManager.models import Connection
from .models import Network, Device

import logging

logger = logging.getLogger(__name__)


def get_discovered_devices_count():
    """
    Query all Elasticsearch clusters for discovered devices count.
    Returns the total count of unique discovered devices across all clusters.
    Only queries connections that are associated with SNMP networks.
    """
    try:
        # Get unique connections associated with SNMP networks
        # Use values_list with distinct to get unique connection IDs
        connection_ids = Network.objects.filter(
            connection__isnull=False
        ).values_list('connection_id', flat=True).distinct()
        
        if not connection_ids:
            return {
                'success': False,
                'error': 'No Elasticsearch connections associated with SNMP networks',
                'count': 0
            }
        
        # Get the actual Connection objects
        connections = Connection.objects.filter(id__in=connection_ids)

        if not connections.exists():
            return {
                'success': False,
                'error': 'No Elasticsearch connections configured',
                'count': 0
            }

        total_discovered = 0
        unique_hosts = set()
        errors = []

        # Calculate time range (last 15 minutes — matches GetDiscoveredDevices and online status)
        now = datetime.now(timezone.utc)
        fifteen_minutes_ago = now - timedelta(minutes=15)

        # Query each connection for discovered devices
        for connection in connections:
            try:
                es = get_elastic_connection(connection.id)

                # Build Elasticsearch query to count unique hosts
                query = {
                    "size": 0,
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "range": {
                                        "@timestamp": {
                                            "gte": fifteen_minutes_ago.isoformat(),
                                            "lte": now.isoformat()
                                        }
                                    }
                                }
                            ]
                        }
                    },
                    "aggs": {
                        "unique_hosts": {
                            "cardinality": {
                                "field": "host.ip"
                            }
                        }
                    }
                }

                # Execute search
                response = es.search(
                    index="logs-snmp.discovery-*",
                    body=query
                )

                # Extract count from aggregation
                if 'aggregations' in response and 'unique_hosts' in response['aggregations']:
                    count = response['aggregations']['unique_hosts']['value']
                    total_discovered += count

            except Exception as e:
                logger.warning(f"Error querying connection {connection.name} for discovered devices: {str(e)}")
                errors.append({
                    'connection': connection.name,
                    'error': str(e)
                })
                continue

        return {
            'success': True,
            'count': total_discovered,
            'errors': errors if errors else None
        }

    except Exception as e:
        logger.error(f"Error getting discovered devices count: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'count': 0
        }


def get_template_data_categories():
    """
    Aggregate data coverage by device template.
    For each device template seen in the last hour, return which event.category
    values are present. This gives a high-level picture of what data is flowing
    per template type rather than per individual device.
    """
    try:
        connection_ids = Network.objects.filter(
            connection__isnull=False
        ).values_list('connection_id', flat=True).distinct()

        if not connection_ids:
            return {'success': True, 'templates': []}

        connections = Connection.objects.filter(id__in=connection_ids)
        if not connections.exists():
            return {'success': True, 'templates': []}

        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        # Merge results across all connections keyed by template name
        template_categories = {}
        errors = []

        query = {
            "size": 0,
            "query": {
                "range": {
                    "@timestamp": {
                        "gte": one_hour_ago.isoformat(),
                        "lte": now.isoformat()
                    }
                }
            },
            "aggs": {
                "templates": {
                    "terms": {
                        "field": "host.device_template.keyword",
                        "size": 100,
                        "missing": "No Template"
                    },
                    "aggs": {
                        "categories": {
                            "terms": {
                                "field": "event.category",
                                "size": 50
                            }
                        }
                    }
                }
            }
        }

        for connection in connections:
            try:
                es = get_elastic_connection(connection.id)
                response = es.search(index="metrics-snmp*", body=query)

                if 'aggregations' in response and 'templates' in response['aggregations']:
                    for bucket in response['aggregations']['templates']['buckets']:
                        template_name = bucket['key']
                        categories = [c['key'] for c in bucket['categories']['buckets']]

                        if template_name not in template_categories:
                            template_categories[template_name] = set()
                        template_categories[template_name].update(categories)

            except Exception as e:
                logger.warning(f"Error querying template data categories for connection {connection.name}: {str(e)}")
                errors.append({'connection': connection.name, 'error': str(e)})
                continue

        result = [
            {
                'template_name': name,
                'template_display_name': format_display_name(name),
                'categories': sorted(list(cats)),
            }
            for name, cats in sorted(template_categories.items())
        ]

        return {
            'success': True,
            'templates': result,
            'errors': errors if errors else None
        }

    except Exception as e:
        logger.error(f"Error getting template data categories: {str(e)}")
        return {'success': False, 'error': str(e), 'templates': []}


def get_high_resource_usage():
    """
    Find devices with high CPU (>80%) or high memory usage (>80%).
    Returns separate lists for high CPU and high memory devices.
    Uses aggregated queries to get the latest values for all devices.
    """
    try:
        # Get all devices with their network connections
        devices = Device.objects.select_related('network', 'network__connection').all()
        
        if not devices.exists():
            return {
                'success': True,
                'high_cpu': [],
                'high_memory': []
            }
        
        # Group devices by connection
        devices_by_connection = {}
        device_lookup = {}  # Map poll_target to device info

        for device in devices:
            if not device.network or not device.network.connection:
                continue

            poll_target = device.hostname or device.ip_address
            if not poll_target:
                continue

            connection_id = device.network.connection.id
            if connection_id not in devices_by_connection:
                devices_by_connection[connection_id] = []

            devices_by_connection[connection_id].append(poll_target)
            device_lookup[poll_target] = {
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'network_name': device.network.name if device.network else None
            }
        
        # Results storage
        high_cpu_devices = []
        high_memory_devices = []
        errors = []
        
        # Calculate time range (last 5 minutes for recent data)
        now = datetime.now(timezone.utc)
        five_minutes_ago = now - timedelta(minutes=5)
        
        # Query each connection
        for connection_id, device_ips in devices_by_connection.items():
            try:
                es = get_elastic_connection(connection_id)
                
                # Build aggregated query to get latest CPU and memory values
                query = {
                    "size": 0,
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "range": {
                                        "@timestamp": {
                                            "gte": five_minutes_ago.isoformat(),
                                            "lte": now.isoformat()
                                        }
                                    }
                                },
                                {
                                    "terms": {
                                        "host.polled_address": device_ips
                                    }
                                }
                            ]
                        }
                    },
                    "aggs": {
                        "devices": {
                            "terms": {
                                "field": "host.polled_address.keyword",
                                "size": 1000
                            },
                            "aggs": {
                                "latest_cpu": {
                                    "top_hits": {
                                        "size": 1,
                                        "sort": [{"@timestamp": {"order": "desc"}}],
                                        "_source": ["system.cpu.total.norm.pct"],
                                        "docvalue_fields": ["system.cpu.total.norm.pct"]
                                    }
                                },
                                "latest_memory": {
                                    "top_hits": {
                                        "size": 1,
                                        "sort": [{"@timestamp": {"order": "desc"}}],
                                        "_source": ["system.memory.actual.used.pct"],
                                        "docvalue_fields": ["system.memory.actual.used.pct"]
                                    }
                                }
                            }
                        }
                    }
                }
                
                # Execute search
                response = es.search(
                    index="metrics-snmp*",
                    body=query
                )
                
                # Process results
                if 'aggregations' in response and 'devices' in response['aggregations']:
                    buckets = response['aggregations']['devices']['buckets']
                    
                    for bucket in buckets:
                        device_ip = bucket['key']
                        device_info = device_lookup.get(device_ip, {})
                        
                        # Check CPU
                        if 'latest_cpu' in bucket and bucket['latest_cpu']['hits']['hits']:
                            hit = bucket['latest_cpu']['hits']['hits'][0]
                            cpu_value = hit.get('_source', {}).get('system', {}).get('cpu', {}).get('total', {}).get('norm', {}).get('pct')
                            
                            if cpu_value is not None and cpu_value > 0.8:
                                high_cpu_devices.append({
                                    'device_id': device_info.get('id'),
                                    'name': device_info.get('name', device_ip),
                                    'ip_address': device_ip,
                                    'cpu_pct': round(cpu_value * 100, 1)
                                })
                        
                        # Check Memory
                        if 'latest_memory' in bucket and bucket['latest_memory']['hits']['hits']:
                            hit = bucket['latest_memory']['hits']['hits'][0]
                            memory_value = hit.get('_source', {}).get('system', {}).get('memory', {}).get('actual', {}).get('used', {}).get('pct')
                            
                            if memory_value is not None and memory_value > 0.8:
                                high_memory_devices.append({
                                    'device_id': device_info.get('id'),
                                    'name': device_info.get('name', device_ip),
                                    'ip_address': device_ip,
                                    'memory_pct': round(memory_value * 100, 1)
                                })
                
            except Exception as e:
                logger.warning(f"Error checking high resource usage for connection {connection_id}: {str(e)}")
                errors.append({
                    'connection_id': connection_id,
                    'error': str(e)
                })
                continue
        
        # Sort by usage (highest first)
        high_cpu_devices.sort(key=lambda x: x['cpu_pct'], reverse=True)
        high_memory_devices.sort(key=lambda x: x['memory_pct'], reverse=True)
        
        return {
            'success': True,
            'high_cpu': high_cpu_devices,
            'high_memory': high_memory_devices,
            'errors': errors if errors else None
        }
    
    except Exception as e:
        logger.error(f"Error getting high resource usage: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'high_cpu': [],
            'high_memory': []
        }
