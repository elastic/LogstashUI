#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Tests for SNMP.overview — Elasticsearch query functions for the Overview page.
All Elasticsearch I/O is mocked; only the Django DB layer is real.
"""

import pytest
from unittest.mock import patch, MagicMock

from SNMP.overview import (
    get_discovered_devices_count,
    get_high_resource_usage,
    get_template_data_categories,
)
from SNMP.models import Network, Device, Credential
from PipelineManager.models import Connection


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def test_connection(db):
    return Connection.objects.create(
        name='Overview Test Connection',
        connection_type='CENTRALIZED',
        host='https://localhost:9200',
        username='elastic',
        password='changeme'
    )


@pytest.fixture
def test_credential(db):
    return Credential.objects.create(
        name='overview_test_cred',
        version='2c',
        community='public'
    )


@pytest.fixture
def test_network(db, test_connection, test_credential):
    return Network.objects.create(
        name='Overview Test Network',
        network_range='10.0.0.0/24',
        connection=test_connection,
        discovery_credential=test_credential,
        interval=30
    )


@pytest.fixture
def test_device(db, test_network, test_credential):
    return Device.objects.create(
        name='overview_test_device',
        ip_address='10.0.0.1',
        port=161,
        retries=1,
        timeout=500,
        credential=test_credential,
        network=test_network,
    )


def _make_es_client(cardinality_value=5):
    """Return a mock ES client with a canned discovered-devices response."""
    mock_es = MagicMock()
    mock_es.search.return_value = {
        'aggregations': {
            'unique_hosts': {
                'value': cardinality_value
            }
        }
    }
    return mock_es


# ===========================================================================
# get_discovered_devices_count
# ===========================================================================

@pytest.mark.django_db
class TestGetDiscoveredDevicesCount:

    def test_no_networks_returns_success_false(self):
        result = get_discovered_devices_count()
        assert result['success'] is False
        assert result['count'] == 0
        assert 'No Elasticsearch connections' in result['error']

    def test_network_without_connection_not_queried(self, db, test_credential):
        Network.objects.create(
            name='Unconnected Network',
            network_range='192.168.0.0/24',
            discovery_credential=test_credential,
            interval=30,
            connection=None
        )
        result = get_discovered_devices_count()
        assert result['success'] is False

    @patch('SNMP.overview.get_elastic_connection')
    def test_returns_count_from_es_aggregation(self, mock_get_es, test_network):
        mock_get_es.return_value = _make_es_client(cardinality_value=7)

        result = get_discovered_devices_count()
        assert result['success'] is True
        assert result['count'] == 7

    @patch('SNMP.overview.get_elastic_connection')
    def test_merges_counts_across_multiple_connections(self, mock_get_es, db, test_credential):
        conn1 = Connection.objects.create(
            name='OV Conn 1', connection_type='CENTRALIZED',
            host='https://es1:9200', username='e', password='p'
        )
        conn2 = Connection.objects.create(
            name='OV Conn 2', connection_type='CENTRALIZED',
            host='https://es2:9200', username='e', password='p'
        )
        Network.objects.create(
            name='Net 1', network_range='10.1.0.0/24',
            connection=conn1, discovery_credential=test_credential, interval=30
        )
        Network.objects.create(
            name='Net 2', network_range='10.2.0.0/24',
            connection=conn2, discovery_credential=test_credential, interval=30
        )

        mock_es1 = _make_es_client(cardinality_value=3)
        mock_es2 = _make_es_client(cardinality_value=4)
        mock_get_es.side_effect = [mock_es1, mock_es2]

        result = get_discovered_devices_count()
        assert result['success'] is True
        assert result['count'] == 7

    @patch('SNMP.overview.get_elastic_connection')
    def test_es_error_tracked_in_errors_list(self, mock_get_es, test_network):
        mock_get_es.side_effect = Exception('Connection refused')

        result = get_discovered_devices_count()
        assert result['success'] is True   # overall success even with per-connection error
        assert result['count'] == 0
        assert result['errors'] is not None
        assert len(result['errors']) == 1

    @patch('SNMP.overview.get_elastic_connection')
    def test_no_errors_returns_none_for_errors_key(self, mock_get_es, test_network):
        mock_get_es.return_value = _make_es_client(cardinality_value=2)

        result = get_discovered_devices_count()
        assert result['errors'] is None

    @patch('SNMP.overview.get_elastic_connection')
    def test_response_without_aggregations_treated_as_zero(self, mock_get_es, test_network):
        mock_es = MagicMock()
        mock_es.search.return_value = {}   # no 'aggregations' key
        mock_get_es.return_value = mock_es

        result = get_discovered_devices_count()
        assert result['success'] is True
        assert result['count'] == 0


# ===========================================================================
# get_high_resource_usage
# ===========================================================================

@pytest.mark.django_db
class TestGetHighResourceUsage:

    def test_no_devices_returns_empty_lists(self):
        result = get_high_resource_usage()
        assert result['success'] is True
        assert result['high_cpu'] == []
        assert result['high_memory'] == []

    def test_device_without_network_connection_skipped(self, db, test_credential, test_network):
        # Create a network with no ES connection
        net_no_conn = Network.objects.create(
            name='No Conn Net',
            network_range='172.16.0.0/24',
            discovery_credential=test_credential,
            interval=30,
            connection=None
        )
        Device.objects.create(
            name='disconnected_device',
            ip_address='172.16.0.1',
            port=161,
            retries=1,
            timeout=500,
            credential=test_credential,
            network=net_no_conn,
        )

        result = get_high_resource_usage()
        assert result['success'] is True
        assert result['high_cpu'] == []
        assert result['high_memory'] == []

    @patch('SNMP.overview.get_elastic_connection')
    def test_device_with_high_cpu_appears_in_high_cpu_list(self, mock_get_es, test_device):
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'devices': {
                    'buckets': [
                        {
                            'key': '10.0.0.1',
                            'latest_cpu': {
                                'hits': {
                                    'hits': [
                                        {'_source': {'system': {'cpu': {'total': {'norm': {'pct': 0.95}}}}}}
                                    ]
                                }
                            },
                            'latest_memory': {'hits': {'hits': []}}
                        }
                    ]
                }
            }
        }
        mock_get_es.return_value = mock_es

        result = get_high_resource_usage()
        assert result['success'] is True
        assert len(result['high_cpu']) == 1
        assert result['high_cpu'][0]['cpu_pct'] == 95.0
        assert result['high_cpu'][0]['ip_address'] == '10.0.0.1'

    @patch('SNMP.overview.get_elastic_connection')
    def test_device_with_high_memory_appears_in_high_memory_list(self, mock_get_es, test_device):
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'devices': {
                    'buckets': [
                        {
                            'key': '10.0.0.1',
                            'latest_cpu': {'hits': {'hits': []}},
                            'latest_memory': {
                                'hits': {
                                    'hits': [
                                        {'_source': {'system': {'memory': {'actual': {'used': {'pct': 0.87}}}}}}
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        }
        mock_get_es.return_value = mock_es

        result = get_high_resource_usage()
        assert result['success'] is True
        assert len(result['high_memory']) == 1
        assert result['high_memory'][0]['memory_pct'] == 87.0

    @patch('SNMP.overview.get_elastic_connection')
    def test_device_below_threshold_not_included(self, mock_get_es, test_device):
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'devices': {
                    'buckets': [
                        {
                            'key': '10.0.0.1',
                            'latest_cpu': {
                                'hits': {
                                    'hits': [
                                        {'_source': {'system': {'cpu': {'total': {'norm': {'pct': 0.5}}}}}}
                                    ]
                                }
                            },
                            'latest_memory': {'hits': {'hits': []}}
                        }
                    ]
                }
            }
        }
        mock_get_es.return_value = mock_es

        result = get_high_resource_usage()
        assert result['high_cpu'] == []

    @patch('SNMP.overview.get_elastic_connection')
    def test_high_cpu_sorted_highest_first(self, mock_get_es, db, test_network, test_credential):
        Device.objects.create(
            name='device_b', ip_address='10.0.0.2', port=161,
            retries=1, timeout=500, credential=test_credential, network=test_network
        )

        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'devices': {
                    'buckets': [
                        {
                            'key': '10.0.0.1',
                            'latest_cpu': {
                                'hits': {
                                    'hits': [{'_source': {'system': {'cpu': {'total': {'norm': {'pct': 0.85}}}}}}]
                                }
                            },
                            'latest_memory': {'hits': {'hits': []}}
                        },
                        {
                            'key': '10.0.0.2',
                            'latest_cpu': {
                                'hits': {
                                    'hits': [{'_source': {'system': {'cpu': {'total': {'norm': {'pct': 0.95}}}}}}]
                                }
                            },
                            'latest_memory': {'hits': {'hits': []}}
                        }
                    ]
                }
            }
        }
        mock_get_es.return_value = mock_es

        result = get_high_resource_usage()
        assert result['high_cpu'][0]['cpu_pct'] == 95.0
        assert result['high_cpu'][1]['cpu_pct'] == 85.0

    @patch('SNMP.overview.get_elastic_connection')
    def test_es_error_tracked_in_errors_list(self, mock_get_es, test_device):
        mock_get_es.side_effect = Exception('Connection refused')

        result = get_high_resource_usage()
        assert result['success'] is True
        assert result['errors'] is not None

    @patch('SNMP.overview.get_elastic_connection')
    def test_no_errors_returns_none_for_errors_key(self, mock_get_es, test_device):
        mock_es = MagicMock()
        mock_es.search.return_value = {'aggregations': {'devices': {'buckets': []}}}
        mock_get_es.return_value = mock_es

        result = get_high_resource_usage()
        assert result['errors'] is None


# ===========================================================================
# get_template_data_categories
# ===========================================================================

@pytest.mark.django_db
class TestGetTemplateDataCategories:

    def test_no_networks_returns_empty_templates(self):
        result = get_template_data_categories()
        assert result['success'] is True
        assert result['templates'] == []

    @patch('SNMP.overview.get_elastic_connection')
    def test_returns_templates_with_categories(self, mock_get_es, test_network):
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'templates': {
                    'buckets': [
                        {
                            'key': 'dell_idrac',
                            'categories': {
                                'buckets': [
                                    {'key': 'system'},
                                    {'key': 'interface'},
                                ]
                            }
                        }
                    ]
                }
            }
        }
        mock_get_es.return_value = mock_es

        result = get_template_data_categories()
        assert result['success'] is True
        assert len(result['templates']) == 1
        assert result['templates'][0]['template_name'] == 'dell_idrac'
        assert 'system' in result['templates'][0]['categories']
        assert 'interface' in result['templates'][0]['categories']

    @patch('SNMP.overview.get_elastic_connection')
    def test_categories_sorted_alphabetically(self, mock_get_es, test_network):
        mock_es = MagicMock()
        mock_es.search.return_value = {
            'aggregations': {
                'templates': {
                    'buckets': [
                        {
                            'key': 'generic',
                            'categories': {
                                'buckets': [
                                    {'key': 'system'},
                                    {'key': 'interface'},
                                    {'key': 'entity_sensor'},
                                ]
                            }
                        }
                    ]
                }
            }
        }
        mock_get_es.return_value = mock_es

        result = get_template_data_categories()
        cats = result['templates'][0]['categories']
        assert cats == sorted(cats)

    @patch('SNMP.overview.get_elastic_connection')
    def test_merges_categories_across_connections(self, mock_get_es, db, test_credential):
        conn1 = Connection.objects.create(
            name='Cat Conn 1', connection_type='CENTRALIZED',
            host='https://es1:9200', username='e', password='p'
        )
        conn2 = Connection.objects.create(
            name='Cat Conn 2', connection_type='CENTRALIZED',
            host='https://es2:9200', username='e', password='p'
        )
        Network.objects.create(
            name='CatNet1', network_range='10.10.0.0/24',
            connection=conn1, discovery_credential=test_credential, interval=30
        )
        Network.objects.create(
            name='CatNet2', network_range='10.11.0.0/24',
            connection=conn2, discovery_credential=test_credential, interval=30
        )

        def side_effect(conn_id):
            mock_es = MagicMock()
            if conn_id == conn1.id:
                mock_es.search.return_value = {
                    'aggregations': {
                        'templates': {
                            'buckets': [{'key': 'cisco', 'categories': {'buckets': [{'key': 'system'}]}}]
                        }
                    }
                }
            else:
                mock_es.search.return_value = {
                    'aggregations': {
                        'templates': {
                            'buckets': [{'key': 'cisco', 'categories': {'buckets': [{'key': 'interface'}]}}]
                        }
                    }
                }
            return mock_es

        mock_get_es.side_effect = side_effect

        result = get_template_data_categories()
        assert result['success'] is True
        cisco_template = next(t for t in result['templates'] if t['template_name'] == 'cisco')
        assert 'system' in cisco_template['categories']
        assert 'interface' in cisco_template['categories']

    @patch('SNMP.overview.get_elastic_connection')
    def test_es_error_tracked_continues(self, mock_get_es, test_network):
        mock_get_es.side_effect = Exception('ES down')

        result = get_template_data_categories()
        assert result['success'] is True
        assert result['errors'] is not None

    @patch('SNMP.overview.get_elastic_connection')
    def test_response_without_aggregations_returns_empty(self, mock_get_es, test_network):
        mock_es = MagicMock()
        mock_es.search.return_value = {}
        mock_get_es.return_value = mock_es

        result = get_template_data_categories()
        assert result['success'] is True
        assert result['templates'] == []
