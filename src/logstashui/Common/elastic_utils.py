#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Elasticsearch and Kibana helpers used across LogstashUI.

``get_elastic_connection`` is the single entry point for ES clients.
CENTRALIZED connections only — agent rows have no Elasticsearch endpoint.
"""

from PipelineManager.models import Connection as ConnectionTable

from elasticsearch import Elasticsearch

import json
import logging
import re
import requests
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def test_elastic_connectivity(elastic_connection):
    """Return pretty-printed cluster ``info()`` for a live ES client.

    Args:
        elastic_connection: An ``elasticsearch.Elasticsearch`` instance.

    Returns:
        JSON string of the cluster info payload.
    """
    return json.dumps(dict(elastic_connection.info()), indent=4)

def get_elastic_connections_from_list():
    """Build ES clients for every CENTRALIZED ``Connection`` row.

    Agent connections are skipped; they have no Elasticsearch endpoint.

    Returns:
        A list of dicts with keys ``es``, ``name``, ``id``, and
        ``connection_type``.
    """
    # Only query CENTRALIZED connections (not AGENT connections)
    # AGENT connections don't have Elasticsearch endpoints to connect to
    es_connections = list(ConnectionTable.objects.filter(
        connection_type=ConnectionTable.ConnectionType.CENTRALIZED
    ).values("connection_type", "name", "host", "cloud_id", "cloud_url", "pk"))

    return [{
        "es": get_elastic_connection(es_connection['pk']),
        "name": es_connection['name'],
        "id": es_connection['pk'],
        "connection_type": es_connection['connection_type']
    } for es_connection in es_connections]

def get_elastic_connection(connection_id):
    """Return an Elasticsearch client for a LogstashUI Connection pk.

    TLS verification is off and the request timeout is 30s.

    Args:
        connection_id: Primary key of ``PipelineManager.Connection``.

    Returns:
        A configured ``elasticsearch.Elasticsearch`` client.

    Raises:
        Connection.DoesNotExist: If ``connection_id`` is unknown.

    Examples:
        es = get_elastic_connection(connection.pk)
        es.ping()
    """
    elastic_creds = _get_creds(connection_id)
    return Elasticsearch(**elastic_creds, verify_certs=False, request_timeout=30)

def _get_creds(connection_id):

    connection = ConnectionTable.objects.get(id=connection_id)
    connection_data = {}

    if connection.cloud_id:
        connection_data['cloud_id'] = connection.cloud_id
    else:
        # For CENTRALIZED connections, combine host and port fields
        # The frontend stores them separately, so we need to recombine them
        if connection.port:
            connection_data['hosts'] = f"{connection.host}:{connection.port}"
        else:
            connection_data['hosts'] = connection.host

    if connection.api_key:
        connection_data['api_key'] = connection.get_api_key()
    else:
        # This is how we allow user to use a username/password instead of an API key
        connection_data['http_auth'] = (connection.username, connection.get_password())

    return connection_data

def get_elasticsearch_indices(connection_id, pattern="*"):
    """List index names matching ``pattern``, capped at 50.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        pattern: ``cat.indices`` index pattern. Defaults to ``*``.

    Returns:
        Sorted list of index name strings, or ``[]`` on error.
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
    """List dotted field names from an index mapping.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        index: Index (or data-stream) name.

    Returns:
        Sorted unique field names, or ``[]`` on error.
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
    """Walk mapping ``properties`` and return dotted field names.

    Args:
        properties: ``mappings.properties`` dict from ES.
        prefix: Parent path prepended to each name.

    Returns:
        List of dotted field name strings, including nested properties.
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
    """Fetch document ``_source`` payloads for pipeline simulation.

    If ``doc_ids`` is set, uses ``mget``. Otherwise searches with an optional
    Lucene ``query_string`` and optional ``_source`` field filter.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        index: Index name.
        doc_ids: Document ids for the mget path.
        field: Restrict ``_source`` to this field when searching.
        size: Hit cap for the search path.
        query_string: Lucene query. Empty means ``match_all``.

    Returns:
        List of ``_source`` dicts, or ``[]`` on error.
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


def get_inference_models(connection_id):
    """List non-deprecated chat-completion inference endpoints.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.

    Returns:
        Dicts with ``inference_id``, ``service``, ``task_type``, and ``name``.
        Empty list on error.
    """
    logger.info(f"get_inference_models called with connection_id: {connection_id}")
    
    try:
        es = get_elastic_connection(connection_id)
        logger.info("Elasticsearch connection established")
        
        response = es.inference.get()
        logger.info(f"Got response from es.inference.get(), type: {type(response)}")
        
        models = []
        # ObjectApiResponse can be accessed like a dict
        if hasattr(response, 'body'):
            endpoints = response.body.get('endpoints', [])
        else:
            endpoints = response.get('endpoints', []) if hasattr(response, 'get') else []
        
        logger.info(f"Total endpoints received: {len(endpoints)}")
        
        chat_completion_count = 0
        for endpoint in endpoints:
            if endpoint.get('task_type') == 'chat_completion':
                chat_completion_count += 1
                inference_id = endpoint.get('inference_id')
                metadata = endpoint.get('metadata')
                
                logger.info(f"Chat completion endpoint: {inference_id}, has_metadata: {metadata is not None}")
                
                if metadata:
                    heuristics = metadata.get('heuristics', {})
                    status = heuristics.get('status', '')
                    
                    logger.info(f"  - status: '{status}'")
                    
                    if status and status != 'deprecated':
                        display = metadata.get('display', {})
                        model_name = display.get('name', inference_id)
                        models.append({
                            'inference_id': inference_id,
                            'service': endpoint.get('service'),
                            'task_type': endpoint.get('task_type'),
                            'name': model_name
                        })
                        logger.info(f"  - ADDED: {model_name}")
                    else:
                        logger.info(f"  - SKIPPED: status is '{status}'")
                else:
                    logger.info(f"  - SKIPPED: no metadata")
        
        logger.info(f"Found {chat_completion_count} chat_completion endpoints, returning {len(models)} non-deprecated models")
        return models
    except Exception as e:
        logger.error(f"Error fetching inference models: {e}", exc_info=True)
        return []


def stream_chat_completion(connection_id, inference_id, system_prompt, user_message):
    """Yield NDJSON chunks from the ES chat-completion inference API.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        inference_id: Inference endpoint id.
        system_prompt: System message. Must be non-empty.
        user_message: User message. Must be non-empty.

    Yields:
        Parsed JSON objects per stream line, or ``{'error': ...}`` on failure.

    Raises:
        ValueError: If either prompt is empty.
    """
    es = get_elastic_connection(connection_id)
    
    try:
        logger.info(f"Calling streaming inference completion with model: {inference_id}")
        
        # Debug: Log message lengths BEFORE creating messages array
        logger.info(f"System prompt length: {len(system_prompt) if system_prompt else 0}")
        logger.info(f"User message length: {len(user_message) if user_message else 0}")
        
        if not system_prompt or not system_prompt.strip():
            logger.error("System prompt is empty!")
            raise ValueError("System prompt cannot be empty")
        if not user_message or not user_message.strip():
            logger.error("User message is empty!")
            raise ValueError("User message cannot be empty")
        
        # Use the chat_completion inference endpoint
        # For Anthropic via Elasticsearch Inference API, messages need proper structure
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message}
        ]
        
        logger.info(f"Prepared {len(messages)} messages for inference API")
        logger.debug(f"Messages structure: {json.dumps([{'role': m['role'], 'content_length': len(m['content'])} for m in messages])}")
        
        # Use perform_request with the correct endpoint
        response = es.perform_request(
            method='POST',
            path=f'/_inference/chat_completion/{inference_id}/_stream',
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/x-ndjson'
            },
            body={
                'messages': messages
            },
        )
        
        logger.info(f"Got streaming response from completion API")
        
        # Parse the streaming response
        if isinstance(response, bytes):
            response = response.decode('utf-8')
        
        # Split by lines and parse each JSON chunk
        for line in response.split('\n'):
            line = line.strip()
            if line:
                # Skip "data: " prefix if present
                if line.startswith('data: '):
                    line = line[6:]
                
                if line and line != '[DONE]':
                    try:
                        chunk = json.loads(line)
                        yield chunk
                    except json.JSONDecodeError:
                        continue
                    
    except Exception as e:
        logger.error(f"Error in streaming chat completion: {e}", exc_info=True)
        yield {'error': str(e)}


def create_ingest_pipeline(connection_id, pipeline_id, pipeline_definition):
    """Put an ingest pipeline.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        pipeline_id: Pipeline id.
        pipeline_definition: Body with processors (and optional on_failure).

    Returns:
        Elasticsearch response as a dict.

    Raises:
        Exception: Propagates the ES client error after logging.
    """
    try:
        es_client = get_elastic_connection(connection_id)
        response = es_client.ingest.put_pipeline(
            id=pipeline_id,
            body=pipeline_definition
        )
        return dict(response)
    except Exception as e:
        logger.error(f"Error creating ingest pipeline: {e}", exc_info=True)
        raise


def simulate_ingest_pipeline(connection_id, pipeline_definition, documents):
    """Run ingest ``simulate`` on sample documents.

    String documents are wrapped as ``{"message": doc}``.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        pipeline_definition: Pipeline body with processors.
        documents: Strings or ``_source`` dicts.

    Returns:
        Simulation response as a dict.
    """
    try:
        es_client = get_elastic_connection(connection_id)
        
        # Format documents for simulation
        docs = []
        for doc in documents:
            if isinstance(doc, str):
                docs.append({
                    "_index": "test",
                    "_source": {"message": doc}
                })
            else:
                docs.append({
                    "_index": "test",
                    "_source": doc
                })
        
        # Run simulation
        response = es_client.ingest.simulate(
            body={
                "pipeline": pipeline_definition,
                "docs": docs
            }
        )
        return dict(response)
    except Exception as e:
        logger.error(f"Error simulating ingest pipeline: {e}", exc_info=True)
        raise


def create_index_template(connection_id, template_name, template_definition):
    """Put an index template.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        template_name: Template name.
        template_definition: Index template body.

    Returns:
        Elasticsearch response as a dict.
    """
    try:
        es_client = get_elastic_connection(connection_id)
        response = es_client.indices.put_index_template(
            name=template_name,
            body=template_definition
        )
        return dict(response)
    except Exception as e:
        logger.error(f"Error creating index template: {e}", exc_info=True)
        raise


def get_index_template(connection_id, template_name):
    """Fetch one installed index template by name.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        template_name: Template name.

    Returns:
        The ``index_template`` dict if found, or ``None`` if not installed
        (including 404). Re-raises unexpected errors.
    """
    try:
        es_client = get_elastic_connection(connection_id)
        response = es_client.indices.get_index_template(name=template_name)
        templates = response.get('index_templates', [])
        if templates:
            return templates[0].get('index_template', {})
        return None
    except Exception as e:
        error_str = str(e).lower()
        if '404' in error_str or 'index_template_missing_exception' in error_str or 'resource_not_found' in error_str:
            return None
        logger.error(f"Error fetching index template '{template_name}': {e}", exc_info=True)
        raise


# Fields compared when diffing a desired template against the installed version.
# We compare structural keys and _meta.version to detect meaningful changes while
# avoiding false positives from ES-normalized mapping content.
# Note: data_stream is handled separately as a presence-only check because ES
# normalizes {} to {"hidden": false} on retrieval, causing false positives.
_TEMPLATE_COMPARE_KEYS = ['index_patterns', 'composed_of', 'priority']


def check_index_template(connection_id, template_name, template_definition):
    """Compare an installed index template to a desired definition.

    Compares ``index_patterns``, ``composed_of``, ``priority``, and
    ``_meta.version`` when present. Mapping content is skipped so ES
    field-level normalization does not produce false positives.
    ``data_stream`` is a presence-only check (``{}`` vs ``{"hidden": false}``).

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        template_name: Template name.
        template_definition: Desired template body.

    Returns:
        Dict with ``status`` (``not_installed``, ``installed``,
        ``installed_but_outdated``, or ``error``), ``differences`` (field
        names), and ``error``.
    """
    try:
        current = get_index_template(connection_id, template_name)

        if current is None:
            return {'status': 'not_installed', 'differences': [], 'error': None}

        differences = []

        for key in _TEMPLATE_COMPARE_KEYS:
            desired_val = template_definition.get(key)
            current_val = current.get(key)
            if desired_val != current_val:
                differences.append(key)

        # data_stream is a presence-only check: {} and {"hidden": false} are
        # both "yes, this is a data stream template", so we only compare existence.
        desired_has_ds = 'data_stream' in template_definition
        current_has_ds = 'data_stream' in current
        if desired_has_ds != current_has_ds:
            differences.append('data_stream')

        # Compare version string from _meta if the desired template declares one
        desired_version = template_definition.get('_meta', {}).get('version')
        if desired_version is not None:
            current_version = current.get('_meta', {}).get('version')
            if desired_version != current_version:
                differences.append('_meta.version')

        if differences:
            return {'status': 'installed_but_outdated', 'differences': differences, 'error': None}

        return {'status': 'installed', 'differences': [], 'error': None}

    except Exception as e:
        logger.error(f"Error checking index template '{template_name}': {e}", exc_info=True)
        return {'status': 'error', 'differences': [], 'error': str(e)}


def ingest_to_data_stream(connection_id, data_stream_name, documents, pipeline_name=None):
    """Bulk-create documents onto a data stream.

    Derives ``data_stream.{type,dataset,namespace}`` from the stream name
    (``{type}-{dataset}-{namespace}``) so Kibana OOTB dashboards match.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        data_stream_name: Stream name, e.g. ``logs-nginx.access-default``.
        documents: Strings (wrapped as ``message``) or dicts.
        pipeline_name: Optional ingest pipeline for the bulk create.

    Returns:
        Bulk response dict.
    """
    try:
        es_client = get_elastic_connection(connection_id)

        # Derive data_stream.* ECS fields from the stream name so Kibana OOTB
        # dashboards (which filter on data_stream.dataset) work correctly.
        # Format: {type}-{dataset}-{namespace}  e.g. logs-nginx.access-default
        data_stream_meta = {}
        try:
            first_dash = data_stream_name.index('-')
            ds_type = data_stream_name[:first_dash]
            rest = data_stream_name[first_dash + 1:]
            last_dash = rest.rfind('-')
            if last_dash > 0:
                data_stream_meta = {
                    'data_stream': {
                        'type': ds_type,
                        'dataset': rest[:last_dash],
                        'namespace': rest[last_dash + 1:],
                    }
                }
        except (ValueError, IndexError):
            pass

        # Prepare bulk request body
        bulk_body = []
        for doc in documents:
            # Index action
            action = {"create": {"_index": data_stream_name}}
            if pipeline_name:
                action["create"]["pipeline"] = pipeline_name

            bulk_body.append(action)

            # Document source — inject data_stream.* if not already set
            if isinstance(doc, str):
                doc_source = {"message": doc}
            else:
                doc_source = dict(doc)

            if data_stream_meta and 'data_stream' not in doc_source:
                doc_source.update(data_stream_meta)

            bulk_body.append(doc_source)

        # Execute bulk request
        response = es_client.bulk(body=bulk_body, refresh=True)
        response_dict = dict(response)
        
        # Check for errors in the bulk response
        if response_dict.get('errors'):
            logger.error(f"Bulk ingestion had errors: {response_dict}")
            # Log individual item errors
            for item in response_dict.get('items', []):
                if 'error' in item.get('create', {}):
                    logger.error(f"Item error: {item['create']['error']}")
        else:
            logger.info(f"Successfully ingested {len(documents)} documents to {data_stream_name}")
        
        return response_dict
    except Exception as e:
        logger.error(f"Error ingesting to data stream: {e}", exc_info=True)
        raise


def bulk_index_documents(connection_id, index_name, documents):
    """Bulk-index documents into a regular index (not a data stream).

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        index_name: Target index (lowercase, no spaces).
        documents: Dicts to index. Strings are wrapped as ``{"message": ...}``.

    Returns:
        Bulk response dict.
    """
    try:
        es_client = get_elastic_connection(connection_id)

        bulk_body = []
        for doc in documents:
            bulk_body.append({"index": {"_index": index_name}})
            bulk_body.append({"message": doc} if isinstance(doc, str) else doc)

        response = es_client.bulk(body=bulk_body, refresh=True)
        response_dict = dict(response)

        if response_dict.get('errors'):
            logger.error("Bulk index had errors for %s: %s", index_name, response_dict)
        else:
            logger.info("Indexed %d documents into %s", len(documents), index_name)

        return response_dict
    except Exception as e:
        logger.error("Error bulk indexing to %s: %s", index_name, e, exc_info=True)
        raise


# Elastic Cloud hostname: {id}[.{es|kb}].{region}.{provider}.elastic.cloud
_ELASTIC_CLOUD_HOST = re.compile(
    r'^(?P<name>[^.]+)'
    r'(?:\.(?P<svc>es|kb))?'
    r'\.(?P<region>[a-z0-9-]+)'
    r'\.(?P<provider>aws|gcp|azure)'
    r'\.elastic\.cloud$',
    re.IGNORECASE,
)

# Ports that belong to Elasticsearch, not the Kibana pretty-URL origin.
_ES_ONLY_PORTS = {9200, 9243}


def normalize_kibana_url(url):
    """Return a Kibana origin (``scheme://host[:port]``) from a stored URL.

    Cloud ID extraction already produces a Kibana host. URL-based connections
    often store the Elasticsearch endpoint instead; this rewrites Elastic Cloud
    ES hosts (``.es.`` infix, or a project alias with neither ``.es.`` nor
    ``.kb.``) to the matching Kibana host so Agent Builder calls do not sit on
    Elasticsearch until the HTTP timeout.

    Args:
        url: User-supplied or connection-derived URL. Empty values pass through.

    Returns:
        Origin string with no path, or the original empty value.

    Examples:
        normalize_kibana_url("https://my.es.us-east-1.aws.elastic.cloud:9243")
        # "https://my.kb.us-east-1.aws.elastic.cloud"
    """
    if not url:
        return url

    url = str(url).strip()
    if not url:
        return url

    if '://' not in url:
        url = 'https://' + url

    parsed = urlparse(url)
    host = (parsed.hostname or '').rstrip('.')
    if not host:
        return url.rstrip('/')

    scheme = (parsed.scheme or 'https').lower()
    if scheme not in ('http', 'https'):
        scheme = 'https'

    port = parsed.port
    match = _ELASTIC_CLOUD_HOST.match(host)
    rewritten = False

    if match and (match.group('svc') or '').lower() != 'kb':
        host = (
            f"{match.group('name')}.kb.{match.group('region')}."
            f"{match.group('provider')}.elastic.cloud"
        )
        rewritten = True
    else:
        lowered = host.lower()
        idx = lowered.find('.es.')
        if idx != -1:
            host = host[:idx] + '.kb.' + host[idx + 4:]
            rewritten = True

    if rewritten and port in _ES_ONLY_PORTS:
        port = None

    netloc = f"{host}:{port}" if port else host
    if parsed.username:
        auth = parsed.username
        if parsed.password is not None:
            auth += f":{parsed.password}"
        netloc = f"{auth}@{netloc}"

    return urlunparse((scheme, netloc, '', '', '', ''))


def get_kibana_url(connection_id):
    """Derive a Kibana origin from a CENTRALIZED connection.

    Decodes ``cloud_id`` when present; otherwise rewrites the ES ``hosts``
    URL through ``normalize_kibana_url``.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.

    Returns:
        Kibana origin string.

    Raises:
        ValueError: If neither ``cloud_id`` nor ``hosts`` can produce a URL.
    """
    import base64
    
    creds = _get_creds(connection_id)
    
    # Check if cloud_id is present
    if 'cloud_id' in creds:
        cloud_id = creds['cloud_id']
        # Format: "deployment-name:base64encodeddata"
        if ':' in cloud_id:
            encoded_part = cloud_id.split(':', 1)[1]
            decoded = base64.b64decode(encoded_part).decode('utf-8')
            # Format: "domain$es_uuid$kibana_uuid"
            parts = decoded.split('$')
            if len(parts) >= 2:
                domain = parts[0]
                # Construct Kibana URL
                kibana_url = f"https://{parts[2]}.{domain}" if len(parts) > 2 else f"https://{domain}"
                return normalize_kibana_url(kibana_url)
    
    # Check for hosts (URL-based connection)
    if 'hosts' in creds and creds['hosts']:
        es_url = creds['hosts'][0] if isinstance(creds['hosts'], list) else creds['hosts']
        return normalize_kibana_url(es_url)
    
    raise ValueError("Could not determine Kibana URL from connection")


def create_kibana_dashboard(connection_id, dashboard_definition):
    """Create a Kibana dashboard via the Dashboards API (legacy SO fallback).

    New format requires ``title`` and ``panels``. The old saved-objects
    format with ``attributes`` is still accepted.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        dashboard_definition: Dashboard body.

    Returns:
        Dict with ``id``, ``url``, and raw ``response``.

    Raises:
        ValueError: If the payload is the wrong shape, or Kibana rejects it
            (includes the API error body).
    """
    import requests

    try:
        kibana_url = get_kibana_url(connection_id)
        creds = _get_creds(connection_id)

        # Prepare authentication
        auth = None
        headers = {'kbn-xsrf': 'true', 'Content-Type': 'application/json'}

        if 'api_key' in creds:
            headers['Authorization'] = f"ApiKey {creds['api_key']}"
        elif 'http_auth' in creds:
            auth = creds['http_auth']

        # Check if it's the new format (title, panels) or old format (attributes)
        if 'title' in dashboard_definition and 'panels' in dashboard_definition:
            # New Dashboards & Visualizations API format
            dashboard_title = dashboard_definition.get('title', 'dashboard')

            # Use the Dashboards API (requires Elastic-Api-Version header)
            api_url = f"{kibana_url}/api/dashboards"
            headers['Elastic-Api-Version'] = '2023-10-31'

            logger.info(f"Creating dashboard with Dashboards API: {api_url}")

            response = requests.post(
                api_url,
                json=dashboard_definition,
                headers=headers,
                auth=auth,
                verify=False
            )

            if not response.ok:
                try:
                    error_detail = response.json()
                    error_text = json.dumps(error_detail, indent=2)
                    logger.error(f"Dashboard API error response: {error_detail}")
                except Exception:
                    error_text = response.text[:2000]
                    logger.error(f"Dashboard API error response (text): {error_text[:500]}")
                raise ValueError(f"HTTP {response.status_code}: {error_text}")

            result = response.json()
            # The API returns { id, data: { title, panels, ... }, meta, spaces }
            saved_dashboard_id = result.get('id')
            if not saved_dashboard_id:
                saved_dashboard_id = dashboard_title.lower().replace(' ', '-').replace('/', '-')

        elif 'attributes' in dashboard_definition:
            # Old saved objects format (legacy support)
            attributes = dashboard_definition['attributes']
            dashboard_title = attributes.get('title', 'dashboard')
            dashboard_id = dashboard_title.lower().replace(' ', '-').replace('/', '-')

            api_url = f"{kibana_url}/api/saved_objects/dashboard/{dashboard_id}"

            logger.info(f"Creating dashboard with saved objects API: {api_url}")

            payload = {'attributes': attributes}

            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                auth=auth,
                verify=False
            )
            response.raise_for_status()

            result = response.json()
            saved_dashboard_id = result.get('id', dashboard_id)
        else:
            raise ValueError("Dashboard definition must have either 'title' and 'panels' (new format) or 'attributes' (old format)")

        return {
            'id': saved_dashboard_id,
            'url': f"{kibana_url}/app/dashboards#/view/{saved_dashboard_id}",
            'response': result
        }

    except Exception as e:
        logger.error(f"Error creating Kibana dashboard: {e}", exc_info=True)
        raise


def delete_ingest_pipeline(connection_id, pipeline_id):
    """Delete an ingest pipeline.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        pipeline_id: Pipeline id.

    Returns:
        Elasticsearch delete response as a dict.
    """
    try:
        es_client = get_elastic_connection(connection_id)
        response = es_client.ingest.delete_pipeline(id=pipeline_id)
        logger.info(f"Deleted ingest pipeline: {pipeline_id}")
        return dict(response)
    except Exception as e:
        logger.error(f"Error deleting ingest pipeline {pipeline_id}: {e}", exc_info=True)
        raise


def delete_index_template(connection_id, template_name):
    """Delete an index template.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        template_name: Template name.

    Returns:
        Elasticsearch delete response as a dict.
    """
    try:
        es_client = get_elastic_connection(connection_id)
        response = es_client.indices.delete_index_template(name=template_name)
        logger.info(f"Deleted index template: {template_name}")
        return dict(response)
    except Exception as e:
        logger.error(f"Error deleting index template {template_name}: {e}", exc_info=True)
        raise


def delete_data_stream(connection_id, data_stream_name):
    """Delete a data stream.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        data_stream_name: Stream name.

    Returns:
        Elasticsearch delete response as a dict.
    """
    try:
        es_client = get_elastic_connection(connection_id)
        response = es_client.indices.delete_data_stream(name=data_stream_name)
        logger.info(f"Deleted data stream: {data_stream_name}")
        return dict(response)
    except Exception as e:
        logger.error(f"Error deleting data stream {data_stream_name}: {e}", exc_info=True)
        raise


def install_fleet_integration(connection_id, integration_name, version):
    """Install a Fleet EPM package via Kibana.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        integration_name: Package name, e.g. ``nginx``.
        version: Package version, e.g. ``3.1.0``.

    Returns:
        ``{'success': True, 'response': ...}`` on HTTP success.

    Raises:
        ValueError: If the connection has no Kibana URL.
        requests.HTTPError: If Fleet EPM rejects the install.
    """
    try:
        # Get Kibana URL
        kibana_url = get_kibana_url(connection_id)
        
        if not kibana_url:
            raise ValueError("Kibana URL not found in connection credentials")
        
        # Get credentials for auth
        creds = _get_creds(connection_id)
        
        # Fleet EPM API endpoint
        api_url = f"{kibana_url}/api/fleet/epm/packages/{integration_name}/{version}"
        
        headers = {'kbn-xsrf': 'true', 'Content-Type': 'application/json'}
        auth = None
        
        if 'api_key' in creds:
            headers['Authorization'] = f"ApiKey {creds['api_key']}"
        elif 'http_auth' in creds:
            auth = creds['http_auth']
        
        logger.info(f"Installing Fleet integration: {integration_name} v{version}")
        
        response = requests.post(
            api_url,
            headers=headers,
            auth=auth,
            verify=False
        )
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Successfully installed {integration_name} v{version}")
        
        return {
            'success': True,
            'response': result
        }
        
    except Exception as e:
        logger.error(f"Error installing Fleet integration: {e}")
        raise


def delete_kibana_dashboard(connection_id, dashboard_id):
    """Delete a Kibana dashboard via the Dashboards API.

    Args:
        connection_id: Primary key of a CENTRALIZED ``Connection``.
        dashboard_id: Dashboard id.

    Returns:
        Parsed JSON body, or ``{'deleted': True}`` if the body is empty.
    """
    import requests

    try:
        kibana_url = get_kibana_url(connection_id)
        creds = _get_creds(connection_id)

        auth = None
        headers = {
            'kbn-xsrf': 'true',
            'Content-Type': 'application/json',
            'Elastic-Api-Version': '2023-10-31',
        }

        if 'api_key' in creds:
            headers['Authorization'] = f"ApiKey {creds['api_key']}"
        elif 'http_auth' in creds:
            auth = creds['http_auth']

        response = requests.delete(
            f"{kibana_url}/api/dashboards/{dashboard_id}",
            headers=headers,
            auth=auth,
            verify=False
        )
        response.raise_for_status()

        logger.info(f"Deleted Kibana dashboard: {dashboard_id}")
        try:
            return response.json()
        except Exception:
            return {'deleted': True}

    except Exception as e:
        logger.error(f"Error deleting Kibana dashboard {dashboard_id}: {e}", exc_info=True)
        raise
