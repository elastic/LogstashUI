#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from unittest.mock import Mock, patch, MagicMock
from elasticsearch import Elasticsearch

from Common.elastic_utils import (
    test_elastic_connectivity as es_test_connectivity,
    get_elastic_connections_from_list,
    get_elastic_connection,
    _get_creds,
    get_elasticsearch_indices,
    get_elasticsearch_field_mappings,
    _extract_field_names,
    query_elasticsearch_documents
)
from PipelineManager.models import Connection


@pytest.fixture
def mock_connection(db):
    """Create a mock connection for testing"""
    connection = Connection.objects.create(
        name='Test Connection',
        connection_type='CENTRALIZED',
        host='https://localhost:9200',
        username='elastic',
        password='changeme'
    )
    return connection


@pytest.fixture
def mock_cloud_connection(db):
    """Create a mock cloud connection for testing"""
    connection = Connection.objects.create(
        name='Cloud Connection',
        connection_type='CENTRALIZED',
        cloud_id='test-cloud-id:dGVzdA==',
        api_key='test-api-key'
    )
    return connection


class TestGetCreds:
    """Test _get_creds function"""

    def test_get_creds_with_host_and_password(self, mock_connection):
        """Test getting credentials with host and password auth"""
        creds = _get_creds(mock_connection.id)
        
        assert 'hosts' in creds
        assert creds['hosts'] == 'https://localhost:9200'
        assert 'http_auth' in creds
        assert creds['http_auth'][0] == 'elastic'

    def test_get_creds_with_cloud_id_and_api_key(self, mock_cloud_connection):
        """Test getting credentials with cloud_id and api_key"""
        creds = _get_creds(mock_cloud_connection.id)
        
        assert 'cloud_id' in creds
        assert creds['cloud_id'] == 'test-cloud-id:dGVzdA=='
        assert 'api_key' in creds
        assert 'http_auth' not in creds
        assert 'hosts' not in creds


class TestGetElasticConnection:
    """Test get_elastic_connection function"""

    @patch('Common.elastic_utils.Elasticsearch')
    def test_get_elastic_connection(self, mock_es_class, mock_connection):
        """Test getting Elasticsearch connection"""
        mock_es_instance = Mock()
        mock_es_class.return_value = mock_es_instance
        
        result = get_elastic_connection(mock_connection.id)
        
        assert result == mock_es_instance
        mock_es_class.assert_called_once()
        call_kwargs = mock_es_class.call_args[1]
        assert 'hosts' in call_kwargs or 'cloud_id' in call_kwargs


class TestGetElasticConnectionsFromList:
    """Test get_elastic_connections_from_list function"""

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_connections_from_list(self, mock_get_connection, mock_connection):
        """Test getting list of connections"""
        mock_es = Mock()
        mock_get_connection.return_value = mock_es
        
        connections = get_elastic_connections_from_list()
        
        assert len(connections) == 1
        assert connections[0]['name'] == 'Test Connection'
        assert connections[0]['es'] == mock_es
        assert connections[0]['id'] == mock_connection.id
        assert connections[0]['connection_type'] == 'CENTRALIZED'

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_multiple_connections(self, mock_get_connection, db):
        """Test getting multiple connections"""
        Connection.objects.create(
            name='Connection 1',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme'
        )
        Connection.objects.create(
            name='Connection 2',
            connection_type='CENTRALIZED',
            cloud_id='test-id',
            api_key='test-api-key'
        )
        
        mock_get_connection.return_value = Mock()
        
        connections = get_elastic_connections_from_list()
        
        assert len(connections) == 2
        assert connections[0]['name'] == 'Connection 1'
        assert connections[1]['name'] == 'Connection 2'


class TestGetElasticsearchIndices:
    """Test get_elasticsearch_indices function"""

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_indices_default_pattern(self, mock_get_connection, mock_connection):
        """Test getting indices with default pattern"""
        mock_es = Mock()
        mock_es.cat.indices.return_value = [
            {'index': 'index-1'},
            {'index': 'index-2'},
            {'index': 'index-3'}
        ]
        mock_get_connection.return_value = mock_es
        
        indices = get_elasticsearch_indices(mock_connection.id)
        
        assert len(indices) == 3
        assert 'index-1' in indices
        assert 'index-2' in indices
        assert 'index-3' in indices
        mock_es.cat.indices.assert_called_once_with(index='*', format='json', h='index')

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_indices_custom_pattern(self, mock_get_connection, mock_connection):
        """Test getting indices with custom pattern"""
        mock_es = Mock()
        mock_es.cat.indices.return_value = [
            {'index': 'logs-2024-01'},
            {'index': 'logs-2024-02'}
        ]
        mock_get_connection.return_value = mock_es
        
        indices = get_elasticsearch_indices(mock_connection.id, pattern='logs-*')
        
        assert len(indices) == 2
        mock_es.cat.indices.assert_called_once_with(index='logs-*', format='json', h='index')

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_indices_sorted(self, mock_get_connection, mock_connection):
        """Test that indices are returned sorted"""
        mock_es = Mock()
        mock_es.cat.indices.return_value = [
            {'index': 'zebra'},
            {'index': 'alpha'},
            {'index': 'beta'}
        ]
        mock_get_connection.return_value = mock_es
        
        indices = get_elasticsearch_indices(mock_connection.id)
        
        assert indices == ['alpha', 'beta', 'zebra']

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_indices_limited_to_50(self, mock_get_connection, mock_connection):
        """Test that only top 50 indices are returned"""
        mock_es = Mock()
        mock_es.cat.indices.return_value = [
            {'index': f'index-{i:03d}'} for i in range(100)
        ]
        mock_get_connection.return_value = mock_es
        
        indices = get_elasticsearch_indices(mock_connection.id)
        
        assert len(indices) == 50

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_indices_error_handling(self, mock_get_connection, mock_connection):
        """Test error handling when fetching indices fails"""
        mock_es = Mock()
        mock_es.cat.indices.side_effect = Exception("Connection error")
        mock_get_connection.return_value = mock_es
        
        indices = get_elasticsearch_indices(mock_connection.id)
        
        assert indices == []


class TestGetElasticsearchFieldMappings:
    """Test get_elasticsearch_field_mappings function"""

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_field_mappings(self, mock_get_connection, mock_connection):
        """Test getting field mappings from index"""
        mock_es = Mock()
        mock_es.indices.get_mapping.return_value = {
            'test-index': {
                'mappings': {
                    'properties': {
                        'field1': {'type': 'text'},
                        'field2': {'type': 'keyword'},
                        'nested_field': {
                            'properties': {
                                'subfield1': {'type': 'long'}
                            }
                        }
                    }
                }
            }
        }
        mock_get_connection.return_value = mock_es
        
        fields = get_elasticsearch_field_mappings(mock_connection.id, 'test-index')
        
        assert 'field1' in fields
        assert 'field2' in fields
        assert 'nested_field' in fields
        assert 'nested_field.subfield1' in fields
        assert len(fields) == 4

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_field_mappings_sorted(self, mock_get_connection, mock_connection):
        """Test that field mappings are sorted"""
        mock_es = Mock()
        mock_es.indices.get_mapping.return_value = {
            'test-index': {
                'mappings': {
                    'properties': {
                        'zebra': {'type': 'text'},
                        'alpha': {'type': 'keyword'},
                        'beta': {'type': 'long'}
                    }
                }
            }
        }
        mock_get_connection.return_value = mock_es
        
        fields = get_elasticsearch_field_mappings(mock_connection.id, 'test-index')
        
        assert fields == ['alpha', 'beta', 'zebra']

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_field_mappings_deduplication(self, mock_get_connection, mock_connection):
        """Test that duplicate fields are removed"""
        mock_es = Mock()
        mock_es.indices.get_mapping.return_value = {
            'test-index-1': {
                'mappings': {
                    'properties': {
                        'field1': {'type': 'text'}
                    }
                }
            },
            'test-index-2': {
                'mappings': {
                    'properties': {
                        'field1': {'type': 'text'}
                    }
                }
            }
        }
        mock_get_connection.return_value = mock_es
        
        fields = get_elasticsearch_field_mappings(mock_connection.id, 'test-index-*')
        
        assert fields.count('field1') == 1

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_get_field_mappings_error_handling(self, mock_get_connection, mock_connection):
        """Test error handling when fetching mappings fails"""
        mock_es = Mock()
        mock_es.indices.get_mapping.side_effect = Exception("Index not found")
        mock_get_connection.return_value = mock_es
        
        fields = get_elasticsearch_field_mappings(mock_connection.id, 'nonexistent-index')
        
        assert fields == []


class TestExtractFieldNames:
    """Test _extract_field_names function"""

    def test_extract_simple_fields(self):
        """Test extracting simple field names"""
        properties = {
            'field1': {'type': 'text'},
            'field2': {'type': 'keyword'}
        }
        
        fields = _extract_field_names(properties)
        
        assert 'field1' in fields
        assert 'field2' in fields
        assert len(fields) == 2

    def test_extract_nested_fields(self):
        """Test extracting nested field names"""
        properties = {
            'parent': {
                'properties': {
                    'child1': {'type': 'text'},
                    'child2': {'type': 'keyword'}
                }
            }
        }
        
        fields = _extract_field_names(properties)
        
        assert 'parent' in fields
        assert 'parent.child1' in fields
        assert 'parent.child2' in fields
        assert len(fields) == 3

    def test_extract_deeply_nested_fields(self):
        """Test extracting deeply nested field names"""
        properties = {
            'level1': {
                'properties': {
                    'level2': {
                        'properties': {
                            'level3': {'type': 'text'}
                        }
                    }
                }
            }
        }
        
        fields = _extract_field_names(properties)
        
        assert 'level1' in fields
        assert 'level1.level2' in fields
        assert 'level1.level2.level3' in fields

    def test_extract_with_prefix(self):
        """Test extracting field names with prefix"""
        properties = {
            'field1': {'type': 'text'}
        }
        
        fields = _extract_field_names(properties, prefix='parent')
        
        assert 'parent.field1' in fields

    def test_extract_empty_properties(self):
        """Test extracting from empty properties"""
        fields = _extract_field_names({})
        
        assert fields == []


class TestQueryElasticsearchDocuments:
    """Test query_elasticsearch_documents function"""

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_query_by_document_ids(self, mock_get_connection, mock_connection):
        """Test querying documents by IDs"""
        mock_es = Mock()
        mock_es.mget.return_value = {
            'docs': [
                {'_source': {'field': 'value1'}, 'found': True},
                {'_source': {'field': 'value2'}, 'found': True}
            ]
        }
        mock_get_connection.return_value = mock_es
        
        docs = query_elasticsearch_documents(
            mock_connection.id,
            'test-index',
            doc_ids=['id1', 'id2']
        )
        
        assert len(docs) == 2
        assert docs[0] == {'field': 'value1'}
        assert docs[1] == {'field': 'value2'}
        mock_es.mget.assert_called_once_with(index='test-index', ids=['id1', 'id2'])

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_query_by_document_ids_not_found(self, mock_get_connection, mock_connection):
        """Test querying documents by IDs with some not found"""
        mock_es = Mock()
        mock_es.mget.return_value = {
            'docs': [
                {'_source': {'field': 'value1'}, 'found': True},
                {'found': False}
            ]
        }
        mock_get_connection.return_value = mock_es
        
        docs = query_elasticsearch_documents(
            mock_connection.id,
            'test-index',
            doc_ids=['id1', 'id2']
        )
        
        assert len(docs) == 1
        assert docs[0] == {'field': 'value1'}

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_query_by_field(self, mock_get_connection, mock_connection):
        """Test querying documents by field"""
        mock_es = Mock()
        mock_es.search.return_value = {
            'hits': {
                'hits': [
                    {'_source': {'field1': 'value1'}},
                    {'_source': {'field1': 'value2'}}
                ]
            }
        }
        mock_get_connection.return_value = mock_es
        
        docs = query_elasticsearch_documents(
            mock_connection.id,
            'test-index',
            field='field1',
            size=10
        )
        
        assert len(docs) == 2
        mock_es.search.assert_called_once()

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_query_with_query_string(self, mock_get_connection, mock_connection):
        """Test querying documents with query string"""
        mock_es = Mock()
        mock_es.search.return_value = {
            'hits': {
                'hits': [
                    {'_source': {'field': 'value'}}
                ]
            }
        }
        mock_get_connection.return_value = mock_es
        
        docs = query_elasticsearch_documents(
            mock_connection.id,
            'test-index',
            query_string='field:value',
            size=5
        )
        
        assert len(docs) == 1
        call_kwargs = mock_es.search.call_args[1]
        assert call_kwargs['query']['query_string']['query'] == 'field:value'

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_query_match_all(self, mock_get_connection, mock_connection):
        """Test querying documents with match_all"""
        mock_es = Mock()
        mock_es.search.return_value = {
            'hits': {
                'hits': [
                    {'_source': {'field': 'value'}}
                ]
            }
        }
        mock_get_connection.return_value = mock_es
        
        docs = query_elasticsearch_documents(
            mock_connection.id,
            'test-index',
            size=10
        )
        
        call_kwargs = mock_es.search.call_args[1]
        assert 'match_all' in call_kwargs['query']

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_query_error_handling(self, mock_get_connection, mock_connection):
        """Test error handling when query fails"""
        mock_es = Mock()
        mock_es.search.side_effect = Exception("Query error")
        mock_get_connection.return_value = mock_es
        
        docs = query_elasticsearch_documents(
            mock_connection.id,
            'test-index'
        )
        
        assert docs == []

    @patch('Common.elastic_utils.get_elastic_connection')
    def test_query_with_specific_field_source(self, mock_get_connection, mock_connection):
        """Test querying with specific field in _source"""
        mock_es = Mock()
        mock_es.search.return_value = {
            'hits': {
                'hits': [
                    {'_source': {'field1': 'value1'}}
                ]
            }
        }
        mock_get_connection.return_value = mock_es
        
        docs = query_elasticsearch_documents(
            mock_connection.id,
            'test-index',
            field='field1',
            size=10
        )
        
        call_kwargs = mock_es.search.call_args[1]
        assert call_kwargs['source'] == ['field1']


class TestTestElasticConnectivity:
    """Tests for test_elastic_connectivity function"""

    def test_returns_json_string(self):
        """Test that test_elastic_connectivity returns a JSON-formatted string"""
        import json

        mock_connection = Mock()
        mock_connection.info.return_value = {
            'name': 'node-1',
            'cluster_name': 'my-cluster',
            'version': {'number': '8.0.0'}
        }

        result = es_test_connectivity(mock_connection)

        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed['name'] == 'node-1'
        assert parsed['cluster_name'] == 'my-cluster'

    def test_json_is_pretty_printed(self):
        """Test that the JSON output is indented (pretty-printed)"""
        mock_connection = Mock()
        mock_connection.info.return_value = {'name': 'node-1'}

        result = es_test_connectivity(mock_connection)

        # Pretty-printed JSON contains newlines and spaces for indentation
        assert '\n' in result
        assert '    ' in result  # 4-space indent

    def test_calls_info_on_connection(self):
        """Test that .info() is called on the provided connection object"""
        mock_connection = Mock()
        mock_connection.info.return_value = {'name': 'node-1'}

        es_test_connectivity(mock_connection)

        mock_connection.info.assert_called_once()

    def test_returns_all_cluster_info_fields(self):
        """Test that all fields from cluster info are returned in JSON"""
        import json

        cluster_info = {
            'name': 'node-1',
            'cluster_name': 'test-cluster',
            'cluster_uuid': 'abc-123',
            'version': {
                'number': '8.12.0',
                'build_flavor': 'default'
            },
            'tagline': 'You Know, for Search'
        }
        mock_connection = Mock()
        mock_connection.info.return_value = cluster_info

        result = es_test_connectivity(mock_connection)
        parsed = json.loads(result)

        # All top-level keys should be present
        for key in cluster_info:
            assert key in parsed

    def test_propagates_exception_from_info(self):
        """Test that exceptions from .info() are propagated (not swallowed)"""
        mock_connection = Mock()
        mock_connection.info.side_effect = ConnectionError("Cannot reach Elasticsearch")

        with pytest.raises(ConnectionError):
            es_test_connectivity(mock_connection)

    def test_empty_info_response(self):
        """Test behavior when info() returns an empty dict"""
        import json

        mock_connection = Mock()
        mock_connection.info.return_value = {}

        result = es_test_connectivity(mock_connection)
        parsed = json.loads(result)
        assert parsed == {}
