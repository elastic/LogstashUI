#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Tests for SNMP.network_map — adjacency-to-graph conversion and the
get_networks_list / get_network_map_data view helpers.
All Elasticsearch I/O is mocked.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from django.test import RequestFactory

from SNMP.network_map import (
    convert_adjacency_to_graph,
    get_networks_list,
    get_network_map_data,
    get_cdp_adjacencies,
    get_edge_interface_detail,
)
from SNMP.models import Network, Device, Credential
from PipelineManager.models import Connection


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def test_connection(db):
    return Connection.objects.create(
        name='NM Test Connection',
        connection_type='CENTRALIZED',
        host='https://localhost:9200',
        username='elastic',
        password='changeme'
    )


@pytest.fixture
def test_credential(db):
    return Credential.objects.create(
        name='nm_test_cred',
        version='2c',
        community='public'
    )


@pytest.fixture
def test_network(db, test_connection, test_credential):
    return Network.objects.create(
        name='NM Test Network',
        network_range='10.0.0.0/24',
        connection=test_connection,
        discovery_credential=test_credential,
        interval=30
    )


@pytest.fixture
def test_device(db, test_network, test_credential):
    return Device.objects.create(
        name='switch-a',
        ip_address='10.0.0.1',
        port=161,
        retries=1,
        timeout=500,
        credential=test_credential,
        network=test_network,
    )


@pytest.fixture
def rf():
    return RequestFactory()


# ===========================================================================
# convert_adjacency_to_graph
# ===========================================================================

class TestConvertAdjacencyToGraph:
    """
    Tests for the pure graph-conversion function.
    The only DB touch is the device-ID lookup at the end, which is
    guarded by try/except; we let it fail silently in the test DB.
    """

    def test_empty_adjacency_table_returns_empty_graph(self, db):
        result = convert_adjacency_to_graph({})
        assert result == {'nodes': [], 'edges': []}

    def test_single_device_no_neighbors_creates_node(self, db):
        adjacency = {
            'Production (10.0.0.0/24)': {
                'switch-a': {}
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        assert len(result['nodes']) == 1
        assert result['nodes'][0]['id'] == 'switch-a'
        assert result['edges'] == []

    def test_device_with_one_neighbor_creates_edge(self, db):
        adjacency = {
            'Production': {
                'switch-a': {
                    'GigabitEthernet0/1': {
                        'device_id': 'switch-b',
                        'port': 'GigabitEthernet0/2',
                        'platform': 'Cisco IOS',
                        'capabilities': 'Switch',
                        'address': '10.0.0.2',
                        'version': '15.2'
                    }
                }
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        assert len(result['nodes']) == 2
        assert len(result['edges']) == 1
        edge = result['edges'][0]
        assert edge['source'] == 'switch-a'
        assert edge['target'] == 'switch-b'
        assert edge['source_interface'] == 'GigabitEthernet0/1'
        assert edge['target_interface'] == 'GigabitEthernet0/2'

    def test_bidirectional_connection_creates_single_edge(self, db):
        adjacency = {
            'Production': {
                'switch-a': {
                    'Gi0/1': {
                        'device_id': 'switch-b', 'port': 'Gi0/2',
                        'platform': '', 'capabilities': '', 'address': '', 'version': ''
                    }
                },
                'switch-b': {
                    'Gi0/2': {
                        'device_id': 'switch-a', 'port': 'Gi0/1',
                        'platform': '', 'capabilities': '', 'address': '', 'version': ''
                    }
                }
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        assert len(result['edges']) == 1

    def test_managed_device_has_managed_true(self, db):
        adjacency = {
            'Production': {
                'switch-a': {
                    'Gi0/1': {
                        'device_id': 'external-router', 'port': 'Eth0',
                        'platform': '', 'capabilities': '', 'address': '', 'version': ''
                    }
                }
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        managed_node = next(n for n in result['nodes'] if n['id'] == 'switch-a')
        assert managed_node['managed'] is True

    def test_discovered_only_device_has_managed_false(self, db):
        adjacency = {
            'Production': {
                'switch-a': {
                    'Gi0/1': {
                        'device_id': 'external-router', 'port': 'Eth0',
                        'platform': '', 'capabilities': '', 'address': '', 'version': ''
                    }
                }
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        discovered_node = next(n for n in result['nodes'] if n['id'] == 'external-router')
        assert discovered_node['managed'] is False

    def test_device_that_appears_in_both_sides_is_managed(self, db):
        adjacency = {
            'Production': {
                'switch-a': {
                    'Gi0/1': {
                        'device_id': 'switch-b', 'port': 'Gi0/2',
                        'platform': '', 'capabilities': '', 'address': '', 'version': ''
                    }
                },
                'switch-b': {}
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        b_node = next(n for n in result['nodes'] if n['id'] == 'switch-b')
        assert b_node['managed'] is True

    def test_interface_count_increments_per_neighbor(self, db):
        adjacency = {
            'Production': {
                'switch-a': {
                    'Gi0/1': {
                        'device_id': 'switch-b', 'port': 'Gi0/2',
                        'platform': '', 'capabilities': '', 'address': '', 'version': ''
                    },
                    'Gi0/2': {
                        'device_id': 'switch-c', 'port': 'Gi0/1',
                        'platform': '', 'capabilities': '', 'address': '', 'version': ''
                    }
                }
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        a_node = next(n for n in result['nodes'] if n['id'] == 'switch-a')
        assert a_node['interface_count'] == 2

    def test_neighbor_without_device_id_skipped(self, db):
        adjacency = {
            'Production': {
                'switch-a': {
                    'Gi0/1': {
                        'device_id': '',  # empty — no neighbor name
                        'port': 'Gi0/2',
                        'platform': '', 'capabilities': '', 'address': '', 'version': ''
                    }
                }
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        # No edge should be created for an empty device_id
        assert result['edges'] == []

    def test_multiple_networks_all_included(self, db):
        adjacency = {
            'Network A': {'device-a': {}},
            'Network B': {'device-b': {}},
        }
        result = convert_adjacency_to_graph(adjacency)
        node_ids = {n['id'] for n in result['nodes']}
        assert 'device-a' in node_ids
        assert 'device-b' in node_ids

    def test_db_device_id_enrichment(self, test_device, db):
        """Managed nodes get a device_id from the DB if their id matches."""
        adjacency = {
            'NM Test Network (10.0.0.0/24)': {
                'switch-a': {}
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        # Node 'switch-a' matches the device name in the DB
        a_node = next(n for n in result['nodes'] if n['id'] == 'switch-a')
        assert a_node.get('device_id') == test_device.id

    def test_edge_contains_platform_and_capabilities(self, db):
        adjacency = {
            'Production': {
                'switch-a': {
                    'Gi0/1': {
                        'device_id': 'switch-b',
                        'port': 'Gi0/2',
                        'platform': 'Cisco 3750',
                        'capabilities': 'Switch Router',
                        'address': '10.0.0.2',
                        'version': '15.2'
                    }
                }
            }
        }
        result = convert_adjacency_to_graph(adjacency)
        edge = result['edges'][0]
        assert edge['platform'] == 'Cisco 3750'
        assert edge['capabilities'] == 'Switch Router'


# ===========================================================================
# get_networks_list
# ===========================================================================

@pytest.mark.django_db
class TestGetNetworksList:

    def test_no_networks_returns_empty_list(self, rf):
        request = rf.get('/SNMP/GetNetworksList/')
        response = get_networks_list(request)
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['networks'] == []

    def test_returns_network_with_correct_fields(self, rf, test_network):
        request = rf.get('/SNMP/GetNetworksList/')
        response = get_networks_list(request)
        data = json.loads(response.content)
        assert data['success'] is True
        assert len(data['networks']) == 1
        network = data['networks'][0]
        assert network['id'] == test_network.id
        assert network['name'] == test_network.name
        assert network['network_range'] == test_network.network_range
        assert 'device_count' in network

    def test_device_count_is_correct(self, rf, test_network, test_device):
        request = rf.get('/SNMP/GetNetworksList/')
        response = get_networks_list(request)
        data = json.loads(response.content)
        assert data['networks'][0]['device_count'] == 1

    def test_networks_returned_alphabetically(self, rf, db, test_credential, test_connection):
        Network.objects.create(
            name='Zebra Network', network_range='10.2.0.0/24',
            connection=test_connection, discovery_credential=test_credential, interval=30
        )
        Network.objects.create(
            name='Alpha Network', network_range='10.3.0.0/24',
            connection=test_connection, discovery_credential=test_credential, interval=30
        )
        request = rf.get('/SNMP/GetNetworksList/')
        response = get_networks_list(request)
        data = json.loads(response.content)
        names = [n['name'] for n in data['networks']]
        assert names == sorted(names)


# ===========================================================================
# get_network_map_data
# ===========================================================================

@pytest.mark.django_db
class TestGetNetworkMapData:

    @patch('SNMP.network_map.get_cdp_adjacencies')
    def test_no_networks_returns_empty_graph(self, mock_cdp, rf):
        mock_cdp.return_value = {
            'success': False,
            'error': 'No connections',
            'adjacency_table': {}
        }
        request = rf.get('/SNMP/GetNetworkMap/')
        response = get_network_map_data(request)
        data = json.loads(response.content)
        assert data['graph']['nodes'] == []
        assert data['graph']['edges'] == []

    @patch('SNMP.network_map.get_cdp_adjacencies')
    def test_with_adjacency_data_returns_graph(self, mock_cdp, rf):
        mock_cdp.return_value = {
            'success': True,
            'adjacency_table': {
                'Production': {
                    'switch-a': {
                        'Gi0/1': {
                            'device_id': 'switch-b', 'port': 'Gi0/2',
                            'platform': '', 'capabilities': '', 'address': '', 'version': ''
                        }
                    }
                }
            },
            'errors': None
        }
        request = rf.get('/SNMP/GetNetworkMap/')
        response = get_network_map_data(request)
        data = json.loads(response.content)
        assert data['success'] is True
        assert len(data['graph']['nodes']) == 2
        assert len(data['graph']['edges']) == 1

    @patch('SNMP.network_map.get_cdp_adjacencies')
    def test_network_filter_passed_to_cdp(self, mock_cdp, rf):
        mock_cdp.return_value = {
            'success': False,
            'adjacency_table': {},
            'error': 'none'
        }
        request = rf.get('/SNMP/GetNetworkMap/?networks=1&networks=2')
        get_network_map_data(request)
        mock_cdp.assert_called_once_with(network_ids=[1, 2])

    @patch('SNMP.network_map.get_cdp_adjacencies')
    def test_no_network_filter_passes_none(self, mock_cdp, rf):
        mock_cdp.return_value = {
            'success': False,
            'adjacency_table': {},
            'error': 'none'
        }
        request = rf.get('/SNMP/GetNetworkMap/')
        get_network_map_data(request)
        mock_cdp.assert_called_once_with(network_ids=None)

    @patch('SNMP.network_map.get_cdp_adjacencies')
    def test_exception_returns_500_response(self, mock_cdp, rf):
        mock_cdp.side_effect = Exception('Unexpected failure')
        request = rf.get('/SNMP/GetNetworkMap/')
        response = get_network_map_data(request)
        assert response.status_code == 500
        data = json.loads(response.content)
        assert data['success'] is False


# ===========================================================================
# get_cdp_adjacencies
# ===========================================================================

@pytest.mark.django_db
class TestGetCdpAdjacencies:
    """
    get_cdp_adjacencies queries ES for CDP/LLDP neighbor data.
    All ES I/O is mocked; only the Django ORM layer is real.
    """

    def _empty_cdp_response(self):
        """ES response with no CDP buckets."""
        return {'aggregations': {'cdp_adjacencies': {'buckets': []}}}

    def _cdp_response(self, host_sysname, table_index, neighbor_device_id, neighbor_port,
                      polled_address='10.0.0.1', network_name=''):
        """Minimal ES response with one CDP bucket."""
        return {
            'aggregations': {
                'cdp_adjacencies': {
                    'buckets': [
                        {
                            'key': {'host_name': host_sysname, 'cdp_row_index': table_index},
                            'latest': {
                                'hits': {
                                    'hits': [
                                        {
                                            '_source': {
                                                'host': {
                                                    'sysname': host_sysname,
                                                    'polled_address': polled_address,
                                                    'hostname': '',
                                                },
                                                'network': {
                                                    'name': network_name,
                                                    'neighbor': {
                                                        'index': table_index,
                                                        'device_id': neighbor_device_id,
                                                        'port': neighbor_port,
                                                        'platform': 'Cisco IOS',
                                                        'capabilities': 'Switch',
                                                        'address': '10.0.0.2',
                                                        'version': '15.2',
                                                    }
                                                },
                                                'event': {'category': 'network.neighbor'},
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        }

    def test_no_networks_returns_failure(self):
        result = get_cdp_adjacencies()
        assert result['success'] is False
        assert 'adjacency_table' in result

    def test_network_without_connection_not_queried(self, test_credential, db):
        Network.objects.create(
            name='No Conn',
            network_range='10.99.0.0/24',
            discovery_credential=test_credential,
            interval=30,
            connection=None,
        )
        result = get_cdp_adjacencies()
        assert result['success'] is False

    @patch('SNMP.network_map.get_elastic_connection')
    def test_empty_cdp_response_returns_empty_adjacency(self, mock_get_es, test_network):
        mock_es = MagicMock()
        mock_es.search.return_value = self._empty_cdp_response()
        mock_get_es.return_value = mock_es

        result = get_cdp_adjacencies()
        assert result['success'] is True
        assert result['adjacency_table'] == {}
        assert result['errors'] is None

    @patch('SNMP.network_map.get_elastic_connection')
    def test_cdp_data_populates_adjacency_table(self, mock_get_es, test_network, test_device):
        mock_es = MagicMock()
        mock_es.search.side_effect = [
            self._cdp_response(
                host_sysname='switch-a',
                table_index='1.1',
                neighbor_device_id='switch-b',
                neighbor_port='Gi0/2',
                polled_address='10.0.0.1',
                network_name='NM Test Network (10.0.0.0/24)',
            ),
            {'hits': {'hits': []}},   # interface name lookup returns nothing
        ]
        mock_get_es.return_value = mock_es

        result = get_cdp_adjacencies()
        assert result['success'] is True
        # adjacency table is non-empty
        assert result['adjacency_table']

    @patch('SNMP.network_map.get_elastic_connection')
    def test_es_error_recorded_in_errors_list(self, mock_get_es, test_network):
        mock_get_es.side_effect = Exception('ES down')
        result = get_cdp_adjacencies()
        assert result['success'] is True
        assert result['errors'] is not None
        assert len(result['errors']) == 1

    @patch('SNMP.network_map.get_elastic_connection')
    def test_network_id_filter_restricts_scope(self, mock_get_es, test_network):
        mock_es = MagicMock()
        mock_es.search.return_value = self._empty_cdp_response()
        mock_get_es.return_value = mock_es

        result = get_cdp_adjacencies(network_ids=[test_network.id])
        assert result['success'] is True

    @patch('SNMP.network_map.get_elastic_connection')
    def test_outer_exception_returns_failure(self, mock_get_es, test_network):
        # Trigger the outer try/except by making Network.objects.filter raise
        with patch('SNMP.network_map.Network.objects') as mock_objs:
            mock_objs.filter.side_effect = Exception('DB error')
            result = get_cdp_adjacencies()
        assert result['success'] is False
        assert 'error' in result


# ===========================================================================
# get_edge_interface_detail
# ===========================================================================

@pytest.mark.django_db
class TestGetEdgeInterfaceDetail:

    @pytest.fixture
    def rf(self):
        from django.test import RequestFactory
        return RequestFactory()

    def test_missing_source_returns_400(self, rf):
        request = rf.get('/SNMP/GetEdgeInterfaceDetail/')
        response = get_edge_interface_detail(request)
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['success'] is False

    def test_missing_source_iface_returns_400(self, rf):
        request = rf.get('/SNMP/GetEdgeInterfaceDetail/?source=switch-a')
        response = get_edge_interface_detail(request)
        assert response.status_code == 400

    def test_no_es_connections_returns_400(self, rf):
        request = rf.get(
            '/SNMP/GetEdgeInterfaceDetail/?source=switch-a&source_iface=Gi0/1'
        )
        response = get_edge_interface_detail(request)
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['success'] is False

    @patch('SNMP.network_map.get_elastic_connection')
    def test_returns_interface_data_for_source(self, mock_get_es, rf, test_network):
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'hits': {
                'hits': [
                    {'_source': {'interface': {'name': 'Gi0/1', 'speed': 1000}}}
                ]
            }
        }
        mock_get_es.return_value = mock_es

        request = rf.get(
            '/SNMP/GetEdgeInterfaceDetail/'
            '?source=switch-a&source_iface=Gi0/1'
            '&target=switch-b&target_iface=Gi0/2'
        )
        response = get_edge_interface_detail(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['source']['sysname'] == 'switch-a'
        assert data['source']['iface_name'] == 'Gi0/1'
        assert data['target']['sysname'] == 'switch-b'

    @patch('SNMP.network_map.get_elastic_connection')
    def test_no_hits_returns_none_interface(self, mock_get_es, rf, test_network):
        mock_es = MagicMock()
        mock_es.search.return_value = {'hits': {'hits': []}}
        mock_get_es.return_value = mock_es

        request = rf.get(
            '/SNMP/GetEdgeInterfaceDetail/'
            '?source=unknown-device&source_iface=Gi0/1'
        )
        response = get_edge_interface_detail(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['source']['interface'] is None

    @patch('SNMP.network_map.get_elastic_connection')
    def test_es_exception_on_lookup_still_returns_200(self, mock_get_es, rf, test_network):
        mock_es = MagicMock()
        mock_es.search.side_effect = Exception('ES lookup failed')
        mock_get_es.return_value = mock_es

        request = rf.get(
            '/SNMP/GetEdgeInterfaceDetail/'
            '?source=switch-a&source_iface=Gi0/1'
        )
        response = get_edge_interface_detail(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['success'] is True
        assert data['source']['interface'] is None
