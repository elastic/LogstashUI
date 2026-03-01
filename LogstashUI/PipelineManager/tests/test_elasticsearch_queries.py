from Common.test_resources import authenticated_client, test_connection, test_user
from PipelineManager.models import Connection

from unittest.mock import patch, MagicMock, Mock

import json
import pytest


# ============================================================================
# GetElasticsearchConnections Tests
# ============================================================================

@pytest.mark.django_db
class TestGetElasticsearchConnections:
    """Test GetElasticsearchConnections view"""

    @patch('PipelineManager.views.get_elastic_connections_from_list')
    def test_get_elasticsearch_connections_success(self, mock_get_connections, authenticated_client):
        """Test successful retrieval of Elasticsearch connections"""
        mock_get_connections.return_value = [
            {'id': 1, 'name': 'Production ES', 'es_client': Mock()},
            {'id': 2, 'name': 'Development ES', 'es_client': Mock()},
            {'id': 3, 'name': 'Staging ES', 'es_client': Mock()}
        ]

        response = authenticated_client.get('/ConnectionManager/GetElasticsearchConnections/')

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'connections' in data
        assert len(data['connections']) == 3
        assert data['connections'][0]['name'] == 'Production ES'
        assert data['connections'][1]['name'] == 'Development ES'
        # Should only return id and name, not es_client
        assert 'es_client' not in data['connections'][0]

    @patch('PipelineManager.views.get_elastic_connections_from_list')
    def test_get_elasticsearch_connections_empty(self, mock_get_connections, authenticated_client):
        """Test GetElasticsearchConnections when no connections exist"""
        mock_get_connections.return_value = []

        response = authenticated_client.get('/ConnectionManager/GetElasticsearchConnections/')

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['connections'] == []

    @patch('PipelineManager.views.get_elastic_connections_from_list')
    def test_get_elasticsearch_connections_error(self, mock_get_connections, authenticated_client):
        """Test GetElasticsearchConnections when an error occurs"""
        mock_get_connections.side_effect = Exception("Database connection failed")

        response = authenticated_client.get('/ConnectionManager/GetElasticsearchConnections/')

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data


# ============================================================================
# GetElasticsearchIndices Tests
# ============================================================================

@pytest.mark.django_db
class TestGetElasticsearchIndices:
    """Test GetElasticsearchIndices view"""

    @patch('PipelineManager.views.get_elasticsearch_indices')
    def test_get_elasticsearch_indices_success(self, mock_get_indices, authenticated_client, test_connection):
        """Test successful retrieval of Elasticsearch indices"""
        mock_get_indices.return_value = [
            'logs-2024.01.01',
            'logs-2024.01.02',
            'metrics-2024.01.01',
            'application-logs'
        ]

        response = authenticated_client.get(
            f'/ConnectionManager/GetElasticsearchIndices/?connection_id={test_connection.id}&pattern=*'
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'indices' in data
        assert len(data['indices']) == 4
        assert 'logs-2024.01.01' in data['indices']

    @patch('PipelineManager.views.get_elasticsearch_indices')
    def test_get_elasticsearch_indices_with_pattern(self, mock_get_indices, authenticated_client, test_connection):
        """Test GetElasticsearchIndices with specific pattern"""
        mock_get_indices.return_value = [
            'logs-2024.01.01',
            'logs-2024.01.02'
        ]

        response = authenticated_client.get(
            f'/ConnectionManager/GetElasticsearchIndices/?connection_id={test_connection.id}&pattern=logs-*'
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data['indices']) == 2
        assert all(idx.startswith('logs-') for idx in data['indices'])

    def test_get_elasticsearch_indices_missing_connection_id(self, authenticated_client):
        """Test GetElasticsearchIndices without connection_id parameter"""
        response = authenticated_client.get('/ConnectionManager/GetElasticsearchIndices/?pattern=*')

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'connection_id' in data['error']

    def test_get_elasticsearch_indices_missing_pattern(self, authenticated_client, test_connection):
        """Test GetElasticsearchIndices without pattern parameter (should use default)"""
        with patch('PipelineManager.views.get_elasticsearch_indices') as mock_get_indices:
            mock_get_indices.return_value = ['index1', 'index2']

            response = authenticated_client.get(
                f'/ConnectionManager/GetElasticsearchIndices/?connection_id={test_connection.id}'
            )

            assert response.status_code == 200
            # Should use default pattern '*'
            mock_get_indices.assert_called_once_with(str(test_connection.id), '*')

    @patch('PipelineManager.views.get_elasticsearch_indices')
    def test_get_elasticsearch_indices_missing_pattern(self, mock_get_indices, authenticated_client, test_connection):
        """Test GetElasticsearchIndices with missing pattern (should default to '*')"""
        mock_get_indices.return_value = ['index1', 'index2']

        response = authenticated_client.get(
            f'/ConnectionManager/GetElasticsearchIndices/?connection_id={test_connection.id}'
        )

        assert response.status_code == 200
        # Should use default pattern '*' - connection_id comes as string from GET params
        mock_get_indices.assert_called_once_with(str(test_connection.id), '*')

    @patch('PipelineManager.views.get_elasticsearch_indices')
    def test_get_elasticsearch_indices_error(self, mock_get_indices, authenticated_client, test_connection):
        """Test GetElasticsearchIndices when an error occurs"""
        mock_get_indices.side_effect = Exception("Connection timeout")

        response = authenticated_client.get(
            f'/ConnectionManager/GetElasticsearchIndices/?connection_id={test_connection.id}&pattern=*'
        )

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data

    @patch('PipelineManager.views.get_elasticsearch_indices')
    def test_get_elasticsearch_indices_typeahead_support(self, mock_get_indices, authenticated_client, test_connection):
        """Test GetElasticsearchIndices supports typeahead functionality"""
        # Simulate typeahead search for 'log'
        mock_get_indices.return_value = [
            'logs-app',
            'logs-system',
            'logs-security'
        ]

        response = authenticated_client.get(
            f'/ConnectionManager/GetElasticsearchIndices/?connection_id={test_connection.id}&pattern=log*'
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert all('log' in idx.lower() for idx in data['indices'])


# ============================================================================
# GetElasticsearchFields Tests
# ============================================================================

@pytest.mark.django_db
class TestGetElasticsearchFields:
    """Test GetElasticsearchFields view"""

    @patch('PipelineManager.views.get_elasticsearch_field_mappings')
    def test_get_elasticsearch_fields_success(self, mock_get_fields, authenticated_client, test_connection):
        """Test successful retrieval of Elasticsearch field mappings"""
        mock_get_fields.return_value = [
            '@timestamp',
            'message',
            'host.name',
            'log.level',
            'user.id',
            'response.status_code'
        ]

        response = authenticated_client.get(
            f'/ConnectionManager/GetElasticsearchFields/?connection_id={test_connection.id}&index=logs-2024.01.01'
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'fields' in data
        assert len(data['fields']) == 6
        assert '@timestamp' in data['fields']
        assert 'message' in data['fields']

    def test_get_elasticsearch_fields_missing_connection_id(self, authenticated_client):
        """Test GetElasticsearchFields without connection_id parameter"""
        response = authenticated_client.get('/ConnectionManager/GetElasticsearchFields/?index=logs-2024.01.01')

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'connection_id' in data['error']

    def test_get_elasticsearch_fields_missing_index(self, authenticated_client, test_connection):
        """Test GetElasticsearchFields without index parameter"""
        response = authenticated_client.get(
            f'/ConnectionManager/GetElasticsearchFields/?connection_id={test_connection.id}'
        )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'index' in data['error']

    @patch('PipelineManager.views.get_elasticsearch_field_mappings')
    def test_get_elasticsearch_fields_error(self, mock_get_fields, authenticated_client, test_connection):
        """Test GetElasticsearchFields when an error occurs"""
        mock_get_fields.side_effect = Exception("Index not found")

        response = authenticated_client.get(
            f'/ConnectionManager/GetElasticsearchFields/?connection_id={test_connection.id}&index=nonexistent'
        )

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data

    @patch('PipelineManager.views.get_elasticsearch_field_mappings')
    def test_get_elasticsearch_fields_nested_fields(self, mock_get_fields, authenticated_client, test_connection):
        """Test GetElasticsearchFields with nested field names"""
        mock_get_fields.return_value = [
            'user.name',
            'user.email',
            'user.address.city',
            'user.address.country',
            'metadata.tags'
        ]

        response = authenticated_client.get(
            f'/ConnectionManager/GetElasticsearchFields/?connection_id={test_connection.id}&index=users'
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'user.name' in data['fields']
        assert 'user.address.city' in data['fields']


# ============================================================================
# QueryElasticsearchDocuments Tests
# ============================================================================

@pytest.mark.django_db
class TestQueryElasticsearchDocuments:
    """Test QueryElasticsearchDocuments view"""

    @patch('PipelineManager.views.query_elasticsearch_documents')
    def test_query_elasticsearch_documents_field_method(self, mock_query, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments with field method"""
        mock_query.return_value = [
            {"message": "Error occurred"},
            {"message": "Warning: disk space low"},
            {"message": "Critical failure"}
        ]

        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'field',
            'field': 'message',
            'size': '10',
            'query': 'level:ERROR'
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'documents' in data
        assert len(data['documents']) == 3

    @patch('PipelineManager.views.query_elasticsearch_documents')
    def test_query_elasticsearch_documents_entire_method(self, mock_query, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments with entire document method"""
        mock_query.return_value = [
            {
                "@timestamp": "2024-01-01T12:00:00Z",
                "message": "Test message",
                "host": "server1",
                "level": "INFO"
            }
        ]

        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'entire',
            'size': '5',
            'query': ''
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data['documents']) == 1
        assert '@timestamp' in data['documents'][0]
        assert 'message' in data['documents'][0]

    @patch('PipelineManager.views.query_elasticsearch_documents')
    def test_query_elasticsearch_documents_docid_method(self, mock_query, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments with document ID method"""
        mock_query.return_value = [
            {"_id": "doc1", "message": "Document 1"},
            {"_id": "doc2", "message": "Document 2"}
        ]

        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'docid',
            'doc_ids': 'doc1\ndoc2\ndoc3'
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data['documents']) == 2

    def test_query_elasticsearch_documents_missing_connection_id(self, authenticated_client):
        """Test QueryElasticsearchDocuments without connection_id"""
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'index': 'logs-2024.01.01',
            'query_method': 'field',
            'field': 'message'
        })

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'connection_id' in data['error']

    def test_query_elasticsearch_documents_missing_index(self, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments without index"""
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'query_method': 'field',
            'field': 'message'
        })

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'index' in data['error']

    def test_query_elasticsearch_documents_field_method_missing_field(self, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments field method without field parameter"""
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'field',
            'size': '10'
        })

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'field is required' in data['error']

    @patch('PipelineManager.views.query_elasticsearch_documents')
    def test_query_elasticsearch_documents_query_injection_attempt(self, mock_query, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments with potential query injection"""
        # Attempt Lucene query injection
        malicious_query = 'status:200 OR 1=1; DROP TABLE users; --'
        
        mock_query.return_value = []

        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'field',
            'field': 'message',
            'size': '10',
            'query': malicious_query
        })

        assert response.status_code == 200
        # Query should be passed to Elasticsearch as-is (Elasticsearch handles query parsing safely)
        mock_query.assert_called_once()
        call_args = mock_query.call_args
        # Verify the malicious query was passed but will be handled by ES query parser
        assert malicious_query in str(call_args)

    @patch('PipelineManager.views.query_elasticsearch_documents')
    def test_query_elasticsearch_documents_size_validation(self, mock_query, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments with various size values"""
        mock_query.return_value = []

        # Test with valid size
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'entire',
            'size': '50'
        })
        assert response.status_code == 200

        # Test with default size (when not provided)
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'entire'
        })
        assert response.status_code == 200

    @patch('PipelineManager.views.query_elasticsearch_documents')
    def test_query_elasticsearch_documents_error_handling(self, mock_query, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments error handling"""
        mock_query.side_effect = Exception("Elasticsearch cluster unavailable")

        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'entire',
            'size': '10'
        })

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data

    @patch('PipelineManager.views.query_elasticsearch_documents')
    def test_query_elasticsearch_documents_empty_results(self, mock_query, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments with no matching documents"""
        mock_query.return_value = []

        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'field',
            'field': 'message',
            'size': '10',
            'query': 'nonexistent:value'
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['documents'] == []

    @patch('PipelineManager.views.query_elasticsearch_documents')
    def test_query_elasticsearch_documents_docid_multiline(self, mock_query, authenticated_client, test_connection):
        """Test QueryElasticsearchDocuments with multiple document IDs"""
        mock_query.return_value = [
            {"_id": "id1", "data": "doc1"},
            {"_id": "id2", "data": "doc2"},
            {"_id": "id3", "data": "doc3"}
        ]

        # Test with newlines and whitespace
        doc_ids = """
        id1
        id2
        
        id3
        
        """

        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': test_connection.id,
            'index': 'logs-2024.01.01',
            'query_method': 'docid',
            'doc_ids': doc_ids
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert len(data['documents']) == 3

        # Verify empty lines were filtered out
        call_args = mock_query.call_args
        doc_ids_arg = call_args[1]['doc_ids']
        assert '' not in doc_ids_arg
        assert len(doc_ids_arg) == 3
