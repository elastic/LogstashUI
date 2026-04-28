#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse
from datetime import datetime, timedelta, timezone
from Common.elastic_utils import get_elastic_connection
from PipelineManager.models import Connection
from .models import Network

import logging

logger = logging.getLogger(__name__)


def get_cdp_adjacencies():
    """
    Query all Elasticsearch clusters for CDP adjacency data.
    Builds an adjacency table structure for network topology visualization.
    
    Returns:
        dict: Adjacency table structure organized by network -> device -> interface
    """
    try:
        # Step 1: Get unique connections associated with SNMP networks
        connection_ids = Network.objects.filter(
            connection__isnull=False
        ).values_list('connection_id', flat=True).distinct()
        
        if not connection_ids:
            return {
                'success': False,
                'error': 'No Elasticsearch connections associated with SNMP networks',
                'adjacency_table': {}
            }
        
        # Get the actual Connection objects
        connections = Connection.objects.filter(id__in=connection_ids)
        
        if not connections.exists():
            return {
                'success': False,
                'error': 'No Elasticsearch connections configured',
                'adjacency_table': {}
            }
        
        # Initialize adjacency table
        adjacency_table = {}
        errors = []
        
        # Calculate time range (last 15 minutes)
        now = datetime.now(timezone.utc)
        fifteen_minutes_ago = now - timedelta(minutes=15)
        
        # Step 2: For each connection, get all networks
        for connection in connections:
            try:
                es = get_elastic_connection(connection.id)
                
                # Get all networks for this connection
                networks = Network.objects.filter(connection_id=connection.id)
                
                # Step 3: For each network, query CDP adjacencies
                for network in networks:
                    network_name = f"{network.name} ({network.network_range})"
                    
                    # Build Elasticsearch query for CDP adjacencies
                    query = {
                        "size": 0,
                        "track_total_hits": False,
                        "query": {
                            "bool": {
                                "filter": [
                                    {
                                        "term": {
                                            "network.name": network_name
                                        }
                                    },
                                    {
                                        "term": {
                                            "event.kind": "cdpcachetable"
                                        }
                                    },
                                    {
                                        "range": {
                                            "@timestamp": {
                                                "gte": fifteen_minutes_ago.isoformat()
                                            }
                                        }
                                    }
                                ]
                            }
                        },
                        "aggs": {
                            "cdp_adjacencies": {
                                "composite": {
                                    "size": 1000,
                                    "sources": [
                                        {
                                            "host_name": {
                                                "terms": {
                                                    "field": "host.name"
                                                }
                                            }
                                        },
                                        {
                                            "cdp_row_index": {
                                                "terms": {
                                                    "field": "table.index"
                                                }
                                            }
                                        }
                                    ]
                                },
                                "aggs": {
                                    "latest": {
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
                                                "includes": [
                                                    "@timestamp",
                                                    "host.name",
                                                    "host.hostname",
                                                    "network.name",
                                                    "event.kind",
                                                    "table.index",
                                                    "table.cdpCacheDeviceId",
                                                    "table.cdpCacheDevicePort",
                                                    "table.cdpCacheAddress",
                                                    "table.cdpCachePlatform",
                                                    "table.cdpCacheCapabilities"
                                                ]
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    
                    # Execute CDP search
                    cdp_response = es.search(
                        index="metrics-snmp.polling-default",
                        body=query
                    )
                    
                    # Process CDP results to collect device/interface pairs for lookup
                    interface_lookup_pairs = []  # List of (device_name, ifIndex) tuples
                    cdp_data_by_device_index = {}  # Store CDP data keyed by device + index
                    
                    if 'aggregations' in cdp_response and 'cdp_adjacencies' in cdp_response['aggregations']:
                        buckets = cdp_response['aggregations']['cdp_adjacencies']['buckets']
                        
                        for bucket in buckets:
                            if 'latest' in bucket and bucket['latest']['hits']['hits']:
                                hit = bucket['latest']['hits']['hits'][0]
                                source = hit['_source']
                                
                                device_name = source.get('host', {}).get('name', '')
                                table_data = source.get('table', {})
                                table_index = table_data.get('index', '')
                                
                                # Extract ifIndex from table.index (format: "ifIndex.cdpCacheIfIndex")
                                if '.' in table_index:
                                    if_index = table_index.split('.')[0]
                                    interface_lookup_pairs.append((device_name, if_index))
                                    
                                    # Store CDP data for later use
                                    key = f"{device_name}:{table_index}"
                                    cdp_data_by_device_index[key] = table_data
                    
                    # Step 3b: Query for interface names using the collected device/ifIndex pairs
                    interface_name_lookup = {}  # Maps "device_name:ifIndex" -> friendly interface name
                    
                    if interface_lookup_pairs:
                        # Build the should clauses for bulk interface lookup
                        should_clauses = []
                        for device_name, if_index in interface_lookup_pairs:
                            should_clauses.append({
                                "bool": {
                                    "filter": [
                                        {
                                            "term": {
                                                "host.name": device_name
                                            }
                                        },
                                        {
                                            "term": {
                                                "table.ifIndex": int(if_index)
                                            }
                                        }
                                    ]
                                }
                            })
                        
                        # Build interface lookup query
                        interface_query = {
                            "size": 100,
                            "track_total_hits": False,
                            "_source": [
                                "@timestamp",
                                "host.name",
                                "host.hostname",
                                "network.name",
                                "event.kind",
                                "table.ifIndex",
                                "table.ifDescr"
                            ],
                            "query": {
                                "bool": {
                                    "filter": [
                                        {
                                            "term": {
                                                "network.name": network_name
                                            }
                                        },
                                        {
                                            "term": {
                                                "event.kind": "interfaces"
                                            }
                                        },
                                        {
                                            "range": {
                                                "@timestamp": {
                                                    "gte": fifteen_minutes_ago.isoformat()
                                                }
                                            }
                                        }
                                    ],
                                    "should": should_clauses,
                                    "minimum_should_match": 1
                                }
                            },
                            "sort": [
                                {
                                    "@timestamp": {
                                        "order": "desc"
                                    }
                                }
                            ]
                        }
                        
                        # Execute interface lookup query
                        interface_response = es.search(
                            index="metrics-snmp.polling-default",
                            body=interface_query
                        )
                        
                        # Build lookup dictionary
                        if 'hits' in interface_response and 'hits' in interface_response['hits']:
                            for hit in interface_response['hits']['hits']:
                                source = hit['_source']
                                device_name = source.get('host', {}).get('name', '')
                                table_data = source.get('table', {})
                                if_index = table_data.get('ifIndex', '')
                                if_descr = table_data.get('ifDescr', '')
                                
                                if device_name and if_index and if_descr:
                                    lookup_key = f"{device_name}:{if_index}"
                                    interface_name_lookup[lookup_key] = if_descr
                    
                    # Step 3c: Build adjacency table with friendly interface names and full CDP data
                    if network_name not in adjacency_table:
                        adjacency_table[network_name] = {}
                    
                    for key, cdp_data in cdp_data_by_device_index.items():
                        device_name, table_index = key.split(':', 1)
                        
                        # Get friendly interface name from lookup
                        if_index = table_index.split('.')[0] if '.' in table_index else table_index
                        lookup_key = f"{device_name}:{if_index}"
                        friendly_interface_name = interface_name_lookup.get(lookup_key, table_index)
                        
                        # Initialize device in adjacency table if not exists
                        if device_name not in adjacency_table[network_name]:
                            adjacency_table[network_name][device_name] = {}
                        
                        # Add interface with full CDP data
                        adjacency_table[network_name][device_name][friendly_interface_name] = {
                            "cdpCachePlatform": cdp_data.get('cdpCachePlatform', ''),
                            "cdpCacheDevicePort": cdp_data.get('cdpCacheDevicePort', ''),
                            "cdpCacheCapabilities": cdp_data.get('cdpCacheCapabilities', ''),
                            "index": cdp_data.get('index', ''),
                            "cdpCacheDeviceId": cdp_data.get('cdpCacheDeviceId', ''),
                            "cdpCacheAddress": cdp_data.get('cdpCacheAddress', '')
                        }
                        
                        logger.debug(f"Added CDP adjacency: {device_name}[{friendly_interface_name}] -> {cdp_data.get('cdpCacheDeviceId', '')}[{cdp_data.get('cdpCacheDevicePort', '')}]")
                    
            except Exception as e:
                logger.warning(f"Error querying connection {connection.name} for CDP adjacencies: {str(e)}")
                errors.append({
                    'connection': connection.name,
                    'error': str(e)
                })
                continue
        
        logger.debug(f"Adjacency table: {adjacency_table}")
        
        return {
            'success': True,
            'adjacency_table': adjacency_table,
            'errors': errors if errors else None
        }
    
    except Exception as e:
        logger.error(f"Error getting CDP adjacencies: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'adjacency_table': {}
        }


def convert_adjacency_to_graph(adjacency_table):
    """
    Convert adjacency table to D3.js-compatible graph structure with nodes and edges.
    Handles bidirectional connections to avoid duplicate edges.
    Distinguishes between managed devices (in inventory) and discovered-only devices.
    
    Args:
        adjacency_table: Dictionary of network -> device -> interface -> CDP data
        
    Returns:
        dict: {
            'nodes': [{'id': device_name, 'network': network_name, 'managed': bool, ...}],
            'edges': [{'source': device1, 'target': device2, 'source_interface': ..., 'target_interface': ...}]
        }
    """
    nodes = {}  # Use dict to avoid duplicates, keyed by device name
    edges = []
    seen_connections = set()  # Track connections to avoid duplicates
    managed_devices = set()  # Track devices that have their own entry in adjacency table
    
    # First pass: identify all managed devices (devices with their own adjacency entries)
    for network_name, devices in adjacency_table.items():
        for device_name in devices.keys():
            managed_devices.add(device_name)
    
    logger.debug(f"Managed devices: {managed_devices}")
    
    # Second pass: build nodes and edges
    for network_name, devices in adjacency_table.items():
        for device_name, interfaces in devices.items():
            # Add node if not already present
            if device_name not in nodes:
                nodes[device_name] = {
                    'id': device_name,
                    'network': network_name,
                    'interface_count': 0,
                    'managed': True  # This device is in our inventory
                }
            
            # Count interfaces for this device
            nodes[device_name]['interface_count'] += len(interfaces)
            
            # Process each interface connection
            for local_interface, cdp_data in interfaces.items():
                remote_device = cdp_data.get('cdpCacheDeviceId', '')
                remote_interface = cdp_data.get('cdpCacheDevicePort', '')
                
                if not remote_device:
                    continue
                
                # Add remote device as node if not present
                if remote_device not in nodes:
                    # Check if this is a managed device or discovered-only
                    is_managed = remote_device in managed_devices
                    nodes[remote_device] = {
                        'id': remote_device,
                        'network': network_name,  # Assume same network for now
                        'interface_count': 0,
                        'managed': is_managed
                    }
                    
                    if not is_managed:
                        logger.debug(f"Discovered-only device: {remote_device}")
                
                # Create a normalized connection key to detect duplicates
                # Sort device names to ensure bidirectional connections have same key
                device_pair = tuple(sorted([device_name, remote_device]))
                interface_pair = tuple(sorted([
                    f"{device_name}:{local_interface}",
                    f"{remote_device}:{remote_interface}"
                ]))
                connection_key = (device_pair, interface_pair)
                
                # Only add edge if we haven't seen this connection before
                if connection_key not in seen_connections:
                    seen_connections.add(connection_key)
                    
                    edge = {
                        'source': device_name,
                        'target': remote_device,
                        'source_interface': local_interface,
                        'target_interface': remote_interface,
                        'platform': cdp_data.get('cdpCachePlatform', ''),
                        'capabilities': cdp_data.get('cdpCacheCapabilities', ''),
                        'network': network_name
                    }
                    edges.append(edge)
                    
                    logger.debug(f"Added edge: {device_name}[{local_interface}] <-> {remote_device}[{remote_interface}]")
    
    # Convert nodes dict to list
    nodes_list = list(nodes.values())
    
    logger.debug(f"Graph conversion complete: {len(nodes_list)} nodes, {len(edges)} edges")
    
    return {
        'nodes': nodes_list,
        'edges': edges
    }


def get_network_map_data(request):
    """
    Django view endpoint to fetch network map data.
    Returns CDP adjacency data as JSON for frontend visualization.
    """
    try:
        # Get CDP adjacency data
        result = get_cdp_adjacencies()
        
        if result['success'] and result['adjacency_table']:
            # Convert adjacency table to graph structure
            graph = convert_adjacency_to_graph(result['adjacency_table'])
            
            # Add graph data to result
            result['graph'] = graph
            
            logger.debug(f"Returning graph with {len(graph['nodes'])} nodes and {len(graph['edges'])} edges")
        else:
            # No data, return empty graph
            result['graph'] = {
                'nodes': [],
                'edges': []
            }
        
        return JsonResponse(result)
    
    except Exception as e:
        logger.error(f"Error in get_network_map_data endpoint: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'adjacency_table': {},
            'graph': {
                'nodes': [],
                'edges': []
            }
        }, status=500)
