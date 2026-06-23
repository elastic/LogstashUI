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


def get_cdp_adjacencies():
    """
    Query all Elasticsearch clusters for CDP/LLDP neighbor data.
    Builds an adjacency table structure for network topology visualization.

    network.neighbor documents do NOT carry a network.name field, so we
    query without that filter and resolve each device's network via the DB.

    Returns:
        dict: Adjacency table structure organized by network -> device -> interface
    """
    try:
        # Step 1: Get connections that have at least one SNMP network
        connection_ids = Network.objects.filter(
            connection__isnull=False
        ).values_list('connection_id', flat=True).distinct()

        if not connection_ids:
            return {
                'success': False,
                'error': 'No Elasticsearch connections associated with SNMP networks',
                'adjacency_table': {}
            }

        connections = Connection.objects.filter(id__in=connection_ids)
        if not connections.exists():
            return {
                'success': False,
                'error': 'No Elasticsearch connections configured',
                'adjacency_table': {}
            }

        # Build lookup maps from the Device inventory so we can assign each
        # device to its network using host.polled_address without relying on
        # network.name being present in every document type.
        device_network_map = {}    # device.name (display) → "NetworkName (range)"
        device_poll_target_map = {}  # hostname or ip_address → "NetworkName (range)"
        try:
            for dev in Device.objects.select_related('network').all():
                if dev.network:
                    net_label = f"{dev.network.name} ({dev.network.network_range})"
                    if dev.name:
                        device_network_map[dev.name] = net_label
                    poll_target = dev.hostname or dev.ip_address
                    if poll_target:
                        device_poll_target_map[poll_target] = net_label
        except Exception as e:
            logger.warning(f"Could not build device→network lookup: {e}")

        def resolve_network(host_name, host_poll_target):
            return (
                device_network_map.get(host_name)
                or device_poll_target_map.get(host_poll_target)
                or 'Unknown Network'
            )

        adjacency_table = {}
        errors = []

        now = datetime.now(timezone.utc)
        fifteen_minutes_ago = now - timedelta(minutes=15)

        # Step 2: One query per connection — no network.name filter
        for connection in connections:
            try:
                es = get_elastic_connection(connection.id)

                query = {
                    "size": 0,
                    "track_total_hits": False,
                    "query": {
                        "bool": {
                            "filter": [
                                {
                                    "term": {
                                        "event.category": "network.neighbor"
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
                                                "field": "host.sysname"
                                            }
                                        }
                                    },
                                    {
                                        "cdp_row_index": {
                                            "terms": {
                                                "field": "network.neighbor.index"
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
                                                    "host.polled_address",
                                                    "host.hostname",
                                                    "host.sysname",
                                                    "network.name",
                                                    "network.neighbor.index",
                                                    "network.neighbor.device_id",
                                                    "network.neighbor.port",
                                                    "network.neighbor.address",
                                                    "network.neighbor.platform",
                                                    "network.neighbor.capabilities",
                                                    "network.neighbor.version",
                                                    "event.category"
                                                ]
                                            }
                                    }
                                }
                            }
                        }
                    }
                }

                cdp_response = es.search(
                        index="metrics-snmp.polling-*",
                        body=query
                    )

                # Collect (device_name, ifIndex) pairs for the interface-name lookup
                interface_lookup_pairs = []
                cdp_data_by_device_index = {}

                if 'aggregations' in cdp_response and 'cdp_adjacencies' in cdp_response['aggregations']:
                    buckets = cdp_response['aggregations']['cdp_adjacencies']['buckets']

                    for bucket in buckets:
                        if 'latest' in bucket and bucket['latest']['hits']['hits']:
                            hit = bucket['latest']['hits']['hits'][0]
                            source = hit['_source']

                            device_name      = source.get('host', {}).get('sysname', '')
                            polled_address   = source.get('host', {}).get('polled_address', '')
                            host_hostname    = source.get('host', {}).get('hostname', '')
                            doc_network_name = source.get('network', {}).get('name', '')
                            neighbor_data    = source.get('network', {}).get('neighbor', {})
                            table_index      = neighbor_data.get('index', '')

                            # network.neighbor.index format: "ifIndex.cdpCacheIfIndex"
                            if device_name and '.' in table_index:
                                if_index = table_index.split('.')[0]
                                interface_lookup_pairs.append((device_name, if_index, polled_address))

                                key = f"{device_name}:{table_index}"
                                cdp_data_by_device_index[key] = {
                                    'neighbor': neighbor_data,
                                    'polled_address': polled_address,
                                    'host_hostname': host_hostname,
                                    'doc_network_name': doc_network_name
                                }

                # Step 2b: Resolve local interface names via interface events
                # (interface docs DO have host.name, so no network.name filter needed)
                interface_name_lookup = {}

                if interface_lookup_pairs:
                    should_clauses = []
                    for device_name, if_index, _ in interface_lookup_pairs:
                        should_clauses.append({
                            "bool": {
                                "filter": [
                                    {"term": {"host.sysname": device_name}},
                                    {"term": {"interface.index": int(if_index)}}
                                ]
                            }
                        })

                    interface_query = {
                        "size": 500,
                        "track_total_hits": False,
                        "_source": ["host.sysname", "interface.index", "interface.name"],
                        "query": {
                            "bool": {
                                "filter": [
                                    {"term": {"event.category": "interface"}},
                                    {"range": {"@timestamp": {"gte": fifteen_minutes_ago.isoformat()}}}
                                ],
                                "should": should_clauses,
                                "minimum_should_match": 1
                            }
                        },
                        "sort": [{"@timestamp": {"order": "desc"}}]
                    }

                    interface_response = es.search(
                            index="metrics-snmp.polling-*",
                            body=interface_query
                        )

                    if 'hits' in interface_response and 'hits' in interface_response['hits']:
                        for hit in interface_response['hits']['hits']:
                            src = hit['_source']
                            dn  = src.get('host', {}).get('sysname', '')
                            ifd = src.get('interface', {})
                            idx = ifd.get('index', '')
                            nm  = ifd.get('name', '')
                            if dn and idx and nm:
                                interface_name_lookup[f"{dn}:{idx}"] = nm

                # Step 2c: Build adjacency table
                for key, entry in cdp_data_by_device_index.items():
                    device_name, table_index = key.split(':', 1)
                    cdp_data         = entry['neighbor']
                    polled_address   = entry['polled_address']
                    host_hostname    = entry['host_hostname']
                    doc_network_name = entry['doc_network_name']

                    # Prefer network.name from the document itself; fall back to DB lookup
                    network_name = doc_network_name or resolve_network(device_name, polled_address)

                    if_index = table_index.split('.')[0] if '.' in table_index else table_index
                    friendly_interface_name = interface_name_lookup.get(
                        f"{device_name}:{if_index}", table_index
                    )

                    adjacency_table.setdefault(network_name, {}).setdefault(device_name, {})
                    adjacency_table[network_name][device_name][friendly_interface_name] = {
                        "platform":   cdp_data.get('platform', ''),
                        "port":       cdp_data.get('port', ''),
                        "capabilities": cdp_data.get('capabilities', ''),
                        "device_id":  cdp_data.get('device_id', ''),
                        "address":    cdp_data.get('address', ''),
                        "version":    cdp_data.get('version', '')
                    }

                    logger.debug(
                        f"Added CDP adjacency: {device_name}[{friendly_interface_name}] "
                        f"-> {cdp_data.get('device_id', '')}[{cdp_data.get('port', '')}]"
                    )

            except Exception as e:
                logger.warning(f"Error querying connection {connection.name} for CDP adjacencies: {str(e)}")
                errors.append({'connection': connection.name, 'error': str(e)})
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
                remote_device = cdp_data.get('device_id', '')
                remote_interface = cdp_data.get('port', '')
                
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
                        'platform': cdp_data.get('platform', ''),
                        'capabilities': cdp_data.get('capabilities', ''),
                        'network': network_name
                    }
                    edges.append(edge)
                    
                    logger.debug(f"Added edge: {device_name}[{local_interface}] <-> {remote_device}[{remote_interface}]")
    
    # Convert nodes dict to list
    nodes_list = list(nodes.values())
    
    # Enrich managed nodes with database device IDs for click-through detail panel.
    # node_id is now host.sysname — try matching against device display name, then
    # hostname, then IP as fallbacks.
    try:
        db_devices = list(Device.objects.values('id', 'name', 'ip_address', 'hostname'))
        name_to_device_id     = {d['name']: d['id'] for d in db_devices}
        hostname_to_device_id = {d['hostname']: d['id'] for d in db_devices if d['hostname']}
        ip_to_device_id       = {d['ip_address']: d['id'] for d in db_devices if d['ip_address']}

        for node in nodes_list:
            node_id = node['id']
            device_id = (
                name_to_device_id.get(node_id)
                or hostname_to_device_id.get(node_id)
                or ip_to_device_id.get(node_id)
            )
            if device_id:
                node['device_id'] = device_id
    except Exception as e:
        logger.warning(f"Could not enrich nodes with device IDs: {e}")

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
