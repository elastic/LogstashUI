#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from PipelineManager.models import Connection as ConnectionTable

from elasticsearch import Elasticsearch

import json
import logging

logger = logging.getLogger(__name__)


def test_elastic_connectivity(elastic_connection):
    return json.dumps(dict(elastic_connection.info()), indent=4)

def get_elastic_connections_from_list():
    es_connections = list(ConnectionTable.objects.values("connection_type", "name", "host", "cloud_id", "cloud_url", "pk"))

    return [{
        "es": get_elastic_connection(es_connection['pk']),
        "name": es_connection['name'],
        "id": es_connection['pk'],
        "connection_type": es_connection['connection_type']
    } for es_connection in es_connections]

def get_elastic_connection(connection_id):
    elastic_creds = _get_creds(connection_id)
    return Elasticsearch(**elastic_creds)

def _get_creds(connection_id):

    connection = ConnectionTable.objects.get(id=connection_id)
    connection_data = {}

    if connection.cloud_id:
        connection_data['cloud_id'] = connection.cloud_id
    else:
        connection_data['hosts'] = connection.host

    if connection.api_key:
        connection_data['api_key'] = connection.get_api_key()
    else:
        # This is how we allow user to use a username/password instead of an API key
        connection_data['http_auth'] = (connection.username, connection.get_password())

    return connection_data

def get_elasticsearch_indices(connection_id, pattern="*"):
    """
    Get Elasticsearch indices using cat.indices API with pattern matching
    Returns top 50 indices matching the pattern
    """
    es = get_elastic_connection(connection_id)

    try:
        # Use cat.indices API with pattern
        indices_response = es.cat.indices(index=pattern, format='json', h='index')

        # Extract index names and sort
        indices = [idx['index'] for idx in indices_response]
        indices.sort()

        # Return top 50
        return indices[:50]
    except Exception as e:
        logger.error(f"Error fetching indices with pattern {pattern}: {e}")
        return []

def get_elasticsearch_field_mappings(connection_id, index):
    """
    Get field mappings from an Elasticsearch index
    Returns a list of field names
    """
    es = get_elastic_connection(connection_id)

    try:
        # Get mappings for the index
        mappings = es.indices.get_mapping(index=index)

        # Extract field names from mappings
        fields = []
        for index_name, index_data in mappings.items():
            properties = index_data.get('mappings', {}).get('properties', {})
            fields.extend(_extract_field_names(properties))

        # Remove duplicates and sort
        fields = sorted(list(set(fields)))
        return fields
    except Exception as e:
        logger.error(f"Error fetching field mappings for index {index}: {e}")
        return []


def _extract_field_names(properties, prefix=''):
    """
    Recursively extract field names from Elasticsearch mappings
    """
    fields = []
    for field_name, field_info in properties.items():
        full_name = f"{prefix}.{field_name}" if prefix else field_name
        fields.append(full_name)

        # Check for nested properties
        if 'properties' in field_info:
            fields.extend(_extract_field_names(field_info['properties'], full_name))

    return fields


def query_elasticsearch_documents(connection_id, index, doc_ids=None, field=None, size=10, query_string=""):
    """
    Query Elasticsearch documents for simulation

    Args:
        connection_id: ES connection ID
        index: Index name
        doc_ids: List of document IDs (for docid method)
        field: Field name to retrieve (for field method)
        size: Number of documents to retrieve
        query_string: Lucene query string

    Returns:
        List of document _source data
    """
    es = get_elastic_connection(connection_id)

    try:
        if doc_ids:
            # Query by document IDs
            response = es.mget(index=index, ids=doc_ids)
            documents = [doc['_source'] for doc in response['docs'] if doc.get('found')]
        else:
            # Query by field with optional query string
            query = {
                "size": size,
                "_source": [field] if field else True
            }

            # Add query string if provided
            if query_string:
                query["query"] = {
                    "query_string": {
                        "query": query_string
                    }
                }
            else:
                query["query"] = {"match_all": {}}

            response = es.search(index=index, size=query['size'], source=query['_source'], query=query['query'])
            documents = [hit['_source'] for hit in response['hits']['hits']]

        return documents
    except Exception as e:
        logger.error(f"Error querying Elasticsearch documents: {e}")
        return []
