#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse
from datetime import datetime, timedelta, timezone

from Common.elastic_utils import get_elastic_connection
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

        # Calculate time range (last 2 hours for discovery)
        now = datetime.now(timezone.utc)
        two_hours_ago = now - timedelta(hours=2)

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
                                            "gte": two_hours_ago.isoformat(),
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
                                "field": "host.name"
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


def get_device_data_quality():
    """
    Check data quality for all devices by querying Elasticsearch for CPU and memory metrics.
    Returns a list of devices with missing data points.
    Uses a single aggregated query per connection to check all devices at once.
    """
    try:
        # Get all devices with their network connections
        devices = Device.objects.select_related('network', 'network__connection').all()
        
        if not devices.exists():
            return {
                'success': True,
                'devices': []
            }
        
        # Group devices by connection
        devices_by_connection = {}
        device_lookup = {}  # Map IP to device info
        
        for device in devices:
            if not device.network or not device.network.connection:
                continue
            
            connection_id = device.network.connection.id
            if connection_id not in devices_by_connection:
                devices_by_connection[connection_id] = []
            
            devices_by_connection[connection_id].append(device.ip_address)
            device_lookup[device.ip_address] = {
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'network_name': device.network.name if device.network else None,
                'network_id': device.network.id if device.network else None
            }
        
        # Results storage
        devices_with_issues = []
        errors = []
        
        # Calculate time range (last 15 minutes for recent data)
        now = datetime.now(timezone.utc)
        fifteen_minutes_ago = now - timedelta(minutes=15)
        
        # Query each connection
        for connection_id, device_ips in devices_by_connection.items():
            try:
                es = get_elastic_connection(connection_id)
                
                # Build aggregated query to check all devices at once
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
                                },
                                {
                                    "terms": {
                                        "host.hostname": device_ips
                                    }
                                }
                            ]
                        }
                    },
                    "aggs": {
                        "devices": {
                            "terms": {
                                "field": "host.hostname",
                                "size": 1000
                            },
                            "aggs": {
                                "has_cpu": {
                                    "filter": {
                                        "exists": {
                                            "field": "system.cpu.total.norm.pct"
                                        }
                                    }
                                },
                                "has_memory": {
                                    "filter": {
                                        "exists": {
                                            "field": "system.memory.actual.used.bytes"
                                        }
                                    }
                                },
                                "has_uptime": {
                                    "filter": {
                                        "exists": {
                                            "field": "host.uptime"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                
                # Execute search for CPU/Memory/Uptime
                response = es.search(
                    index="metrics-snmp*",
                    body=query
                )
                
                # Build separate query for interfaces (stored in separate documents with event.kind: "interfaces")
                interface_query = {
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
                                },
                                {
                                    "terms": {
                                        "host.hostname": device_ips
                                    }
                                },
                                {
                                    "term": {
                                        "event.kind": "interfaces"
                                    }
                                }
                            ]
                        }
                    },
                    "aggs": {
                        "devices": {
                            "terms": {
                                "field": "host.hostname",
                                "size": 1000
                            }
                        }
                    }
                }
                
                # Execute search for interfaces
                interface_response = es.search(
                    index="metrics-snmp*",
                    body=interface_query
                )
                
                # Build set of devices with interface data
                devices_with_interfaces = set()
                if 'aggregations' in interface_response and 'devices' in interface_response['aggregations']:
                    interface_buckets = interface_response['aggregations']['devices']['buckets']
                    for bucket in interface_buckets:
                        devices_with_interfaces.add(bucket['key'])
                
                # Process results from CPU/Memory/Uptime query
                device_metrics = {}  # Store metrics status for each device
                
                if 'aggregations' in response and 'devices' in response['aggregations']:
                    buckets = response['aggregations']['devices']['buckets']
                    
                    # Track which devices we found
                    found_devices = set()
                    
                    for bucket in buckets:
                        device_ip = bucket['key']
                        found_devices.add(device_ip)
                        
                        has_cpu = bucket['has_cpu']['doc_count'] > 0
                        has_memory = bucket['has_memory']['doc_count'] > 0
                        has_uptime = bucket['has_uptime']['doc_count'] > 0
                        has_interfaces = device_ip in devices_with_interfaces
                        
                        device_metrics[device_ip] = {
                            'has_cpu': has_cpu,
                            'has_memory': has_memory,
                            'has_uptime': has_uptime,
                            'has_interfaces': has_interfaces
                        }
                        
                        # Only add to issues list if missing any metric
                        if not has_cpu or not has_memory or not has_uptime or not has_interfaces:
                            device_info = device_lookup.get(device_ip, {})
                            devices_with_issues.append({
                                'device_id': device_info.get('id'),
                                'name': device_info.get('name', device_ip),
                                'ip_address': device_ip,
                                'network_name': device_info.get('network_name'),
                                'network_id': device_info.get('network_id'),
                                'has_cpu': has_cpu,
                                'has_memory': has_memory,
                                'has_uptime': has_uptime,
                                'has_interfaces': has_interfaces
                            })
                    
                    # Check for devices with no data at all
                    for device_ip in device_ips:
                        if device_ip not in found_devices:
                            # Still check if they have interface data
                            has_interfaces = device_ip in devices_with_interfaces
                            
                            device_info = device_lookup.get(device_ip, {})
                            devices_with_issues.append({
                                'device_id': device_info.get('id'),
                                'name': device_info.get('name', device_ip),
                                'ip_address': device_ip,
                                'network_name': device_info.get('network_name'),
                                'network_id': device_info.get('network_id'),
                                'has_cpu': False,
                                'has_memory': False,
                                'has_uptime': False,
                                'has_interfaces': has_interfaces
                            })
                
            except Exception as e:
                logger.warning(f"Error checking data quality for connection {connection_id}: {str(e)}")
                errors.append({
                    'connection_id': connection_id,
                    'error': str(e)
                })
                continue
        
        return {
            'success': True,
            'devices': devices_with_issues,
            'errors': errors if errors else None
        }
    
    except Exception as e:
        logger.error(f"Error getting device data quality: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'devices': []
        }


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
        device_lookup = {}  # Map IP to device info
        
        for device in devices:
            if not device.network or not device.network.connection:
                continue
            
            connection_id = device.network.connection.id
            if connection_id not in devices_by_connection:
                devices_by_connection[connection_id] = []
            
            devices_by_connection[connection_id].append(device.ip_address)
            device_lookup[device.ip_address] = {
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
                                        "host.hostname": device_ips
                                    }
                                }
                            ]
                        }
                    },
                    "aggs": {
                        "devices": {
                            "terms": {
                                "field": "host.hostname",
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
