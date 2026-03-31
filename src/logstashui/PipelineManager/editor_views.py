#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.conf import settings

from Common.decorators import require_admin_role
from Common.logstash_utils import get_logstash_pipeline
from Common.elastic_utils import get_elastic_connection, query_elasticsearch_documents, \
    get_elastic_connections_from_list, get_elasticsearch_indices, get_elasticsearch_field_mappings
from Common.validators import validate_pipeline_name
from Common import logstash_config_parse

from datetime import datetime, timezone
from html import escape

import json
import os
import logging
import traceback
import difflib

logger = logging.getLogger(__name__)


def _load_plugin_data():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(app_dir, 'data', 'plugins.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def PipelineEditor(request):
    from django.conf import settings
    
    context = {
        "plugin_data": _load_plugin_data(),
        "simulation_mode": settings.LOGSTASHUI_CONFIG.get('simulation', {}).get('mode', 'embedded')
    }

    if request.method == "GET":
        ls_id = request.GET.get("ls_id")
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")

        # Validate required parameters
        if not (ls_id or es_id) or not pipeline_name:
            return HttpResponseBadRequest("Missing required parameters: (es_id or ls_id) and pipeline")

        if ls_id:
            from PipelineManager.models import Pipeline as PipelineModel
            try:
                pipeline_obj = PipelineModel.objects.get(policy_id=ls_id, name=pipeline_name)
            except PipelineModel.DoesNotExist:
                return HttpResponseBadRequest(f"Could not find pipeline '{pipeline_name}' in policy {ls_id}")
            pipeline_config = {
                'pipeline': pipeline_obj.lscl,
                'pipeline_settings': {},
                'description': pipeline_obj.description or '',
            }
            context['ls_id'] = ls_id
        else:
            pipeline_config = get_logstash_pipeline(es_id, pipeline_name)
            if not pipeline_config:
                return HttpResponseBadRequest(f"Could not fetch pipeline '{pipeline_name}' from connection {es_id}")

        context['pipeline_text'] = pipeline_config['pipeline']

        # Flatten pipeline settings with defaults for template access
        settings = pipeline_config.get('pipeline_settings', {})
        context['pipeline_settings'] = {
            'description': pipeline_config.get('description', ''),
            'pipeline_workers': settings.get('pipeline.workers', 1),
            'pipeline_batch_size': settings.get('pipeline.batch.size', 128),
            'pipeline_batch_delay': settings.get('pipeline.batch.delay', 50),
            'queue_type': settings.get('queue.type', 'memory'),
            'queue_max_bytes': settings.get('queue.max_bytes', '1gb'),
            'queue_checkpoint_writes': settings.get('queue.checkpoint.writes', 1024),
        }
        context['pipeline_name'] = pipeline_name
        context['parsing_error'] = None

        try:
            parsed_config = logstash_config_parse.logstash_config_to_components(context['pipeline_text'])
            # logstash_config_to_components returns a JSON string, so parse it back to a dict
            context['component_data'] = json.loads(parsed_config)
        except Exception as e:
            # Capture the parsing error to show to the user
            context['parsing_error'] = str(e)
            context['component_data'] = {
                "input": [],
                "filter": [],
                "output": []
            }

    return render(request, "pipeline_editor.html", context=context)


def GetCurrentPipelineCode(request, components={}):
    if not components:
        data = json.loads(request.POST.get("components"))
    else:
        data = components
    parser = logstash_config_parse.ComponentToPipeline(data)
    config = parser.components_to_logstash_config()

    # Return the code wrapped in a pre tag with proper formatting
    return HttpResponse(
        f'<pre class="bg-gray-900 text-green-400 p-4 rounded overflow-auto"><code class="language-ruby">{escape(config)}</code></pre>',
        content_type="text/html"
    )


@require_admin_role
def SavePipeline(request):
    if "save_pipeline" in request.POST:
        pipeline_name = request.POST.get("pipeline")

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(
                f'<div class="p-4 bg-red-900/20 border border-red-600 rounded-lg"><p class="text-red-400">{error_msg}</p></div>',
                status=400
            )

        # Check if we have raw pipeline config (from Text mode) or components (from UI mode)
        pipeline_config = request.POST.get("pipeline_config")

        if pipeline_config:
            # Use the raw pipeline config directly from Text mode
            config = pipeline_config
            logger.info(f"Saving pipeline from Text mode (raw config)")
        else:
            # Generate config from components (UI mode)
            components_json = request.POST.get("components")
            if not components_json:
                return HttpResponse(
                    f'<div class="p-4 bg-red-900/20 border border-red-600 rounded-lg"><p class="text-red-400">Missing pipeline configuration</p></div>',
                    status=400
                )

            data = json.loads(components_json)
            add_ids = request.POST.get("add_ids", "false").lower() == "true"
            parser = logstash_config_parse.ComponentToPipeline(data, add_ids=add_ids)
            config = parser.components_to_logstash_config()

            # Validate that the generated config can be converted back to components
            try:
                logstash_config_parse.logstash_config_to_components(config)
            except Exception as e:
                # If conversion fails, return detailed error to user
                error_message = escape(str(e))
                return HttpResponse(
                    f"""<div class="p-4 bg-red-900/20 border border-red-600 rounded-lg">
                        <h3 class="text-lg font-semibold text-red-400 mb-2">We're sorry! Something went wrong in the conversion of your pipeline!</h3>
                        <div class="bg-gray-900 p-4 rounded mt-2 text-sm text-gray-300 font-mono whitespace-pre-wrap overflow-auto max-h-96">
{error_message}
                        </div>
                        <p class="mt-4 text-gray-300">Please report this issue to us so we can fix it!!</p>
                    </div>""",
                    status=400
                )

        ls_id = request.POST.get("ls_id") or None
        if ls_id == "null": ls_id = None

        if ls_id:
            from PipelineManager.models import Pipeline as PipelineModel, Policy
            policy = Policy.objects.get(pk=ls_id)
            PipelineModel.objects.filter(policy=policy, name=pipeline_name).update(lscl=config)
            policy.has_undeployed_changes = True
            policy.save(update_fields=['has_undeployed_changes'])
            logger.info(f"User '{request.user.username}' saved pipeline '{pipeline_name}' to policy {ls_id}")
            return HttpResponse("Pipeline saved successfully!")

        es = get_elastic_connection(request.POST.get("es_id"))
        current_pipeline_config = es.logstash.get_pipeline(id=pipeline_name)

        pipeline_data = current_pipeline_config.get(pipeline_name, {})

        es.logstash.put_pipeline(id=pipeline_name, body={
            "pipeline": config,
            "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "pipeline_metadata": pipeline_data.get('pipeline_metadata', {"version": 1, "type": "logstash_pipeline"}),
            "username": "logstashui",
            "pipeline_settings": pipeline_data.get('pipeline_settings', {}),
            "description": pipeline_data.get('description', '')
        }
                                 )

        logger.info(
            f"User '{request.user.username}' saved pipeline '{pipeline_name}' (Connection ID: {request.POST.get('es_id')})")
        return HttpResponse("Pipeline saved successfully!")

    return HttpResponse("Invalid request", status=400)


def ComponentsToConfig(request):
    """Convert components JSON to Logstash configuration text"""
    if request.method == "POST":
        try:
            components_json = request.POST.get("components")
            if not components_json:
                return HttpResponse("No components provided", status=400)

            # Parse components
            components = json.loads(components_json)

            # Convert to config using the same logic as SavePipeline
            parser = logstash_config_parse.ComponentToPipeline(components, add_ids=False)
            config = parser.components_to_logstash_config()

            # Return plain text config
            return HttpResponse(config, content_type="text/plain")
        except Exception as e:
            logger.error(f"Error converting components to config: {str(e)}")
            return HttpResponse(f"Error: {str(e)}", status=500)

    return HttpResponse("Method not allowed", status=405)


def ConfigToComponents(request):
    """Convert Logstash configuration text to components JSON"""
    if request.method == "POST":
        try:
            config_text = request.POST.get("config_text")
            if not config_text:
                return JsonResponse({"error": "No config text provided"}, status=400)

            # Parse config text to components
            components = logstash_config_parse.logstash_config_to_components(config_text)

            # Return components as JSON with safe=False to allow nested structures
            return JsonResponse(components, safe=False)
        except Exception as e:
            logger.error(f"Error converting config to components: {str(e)}")
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def GetDiff(request):
    """Generate a unified diff between current and new pipeline configurations"""
    if request.method == "POST":
        ls_id = request.POST.get("ls_id") or None
        if ls_id == "null": ls_id = None
        es_id = request.POST.get("es_id") or None
        if es_id == "null": es_id = None
        pipeline_name = request.POST.get("pipeline")
        pipeline_text = request.POST.get("pipeline_text")  # Raw text from Text mode
        components_json = request.POST.get("components")
        add_ids = request.POST.get("add_ids", "false").lower() == "true"

        # Need either pipeline_text or components, and either ls_id or es_id
        if not (ls_id or es_id) or not pipeline_name or (not pipeline_text and not components_json):
            return JsonResponse({"error": "Missing required parameters"}, status=400)

        try:
            # Get the current pipeline — from DB for ls_id, or from Elasticsearch for es_id
            if ls_id:
                from PipelineManager.models import Pipeline as PipelineModel
                try:
                    current_pipeline = PipelineModel.objects.get(policy_id=ls_id, name=pipeline_name).lscl
                except PipelineModel.DoesNotExist:
                    return JsonResponse({"error": f"Pipeline '{pipeline_name}' not found in policy {ls_id}"}, status=404)
            else:
                current_pipeline = get_logstash_pipeline(es_id, pipeline_name)['pipeline']

            # Generate the new pipeline - either from raw text or from components
            if pipeline_text:
                # Use the raw text directly from Text mode
                new_pipeline = pipeline_text
            else:
                # Generate from components (UI mode)
                components = json.loads(components_json)
                parser = logstash_config_parse.ComponentToPipeline(components, add_ids=add_ids)
                new_pipeline = parser.components_to_logstash_config()

            # Generate unified diff
            diff = difflib.unified_diff(
                current_pipeline.splitlines(keepends=True),
                new_pipeline.splitlines(keepends=True),
                fromfile='Current Pipeline',
                tofile='New Pipeline (After Save)',
                lineterm=''
            )

            # Convert to string
            diff_text = ''.join(diff)

            # Calculate stats
            current_lines = len(current_pipeline.splitlines())
            new_lines = len(new_pipeline.splitlines())
            line_diff = new_lines - current_lines
            diff_sign = '+' if line_diff > 0 else ''
            stats = f"Current: {current_lines} lines | New: {new_lines} lines ({diff_sign}{line_diff})"

            return JsonResponse({
                'diff': diff_text,
                'stats': stats,
                'current': current_pipeline,
                'new': new_pipeline
            })

        except Exception as e:
            logger.error(f"Error generating diff: {str(e)}")
            return JsonResponse({"error": f"Error generating diff: {str(e)}"}, status=500)

    return JsonResponse({"error": "Method not allowed"}, status=405)


def GetElasticsearchConnections(request):
    """
    Get all Elasticsearch connections for simulation input
    """
    try:
        # Use existing function that returns connections with ES clients
        connections_list = get_elastic_connections_from_list()

        # Format for dropdown: extract id and name
        connections = [{'id': conn['id'], 'name': conn['name']} for conn in connections_list]

        return JsonResponse({"connections": connections})
    except Exception as e:
        logger.error(f"Error fetching Elasticsearch connections: {e}")
        return JsonResponse({"error": str(e)}, status=500)


def GetElasticsearchIndices(request):
    """
    Get Elasticsearch indices with typeahead support
    """

    connection_id = request.GET.get("connection_id")
    pattern = request.GET.get("pattern", "*")

    if not connection_id:
        return JsonResponse({"error": "connection_id is required"}, status=400)

    try:
        indices = get_elasticsearch_indices(connection_id, pattern)
        return JsonResponse({"indices": indices})
    except Exception as e:
        logger.error(f"Error fetching Elasticsearch indices: {e}")
        return JsonResponse({"error": str(e)}, status=500)


def GetElasticsearchFields(request):
    """
    Get field mappings from an Elasticsearch index
    """

    connection_id = request.GET.get("connection_id")
    index = request.GET.get("index")

    if not connection_id or not index:
        return JsonResponse({"error": "connection_id and index are required"}, status=400)

    try:
        fields = get_elasticsearch_field_mappings(connection_id, index)
        return JsonResponse({"fields": fields})
    except Exception as e:
        logger.error(f"Error fetching Elasticsearch fields: {e}")
        return JsonResponse({"error": str(e)}, status=500)


def QueryElasticsearchDocuments(request):
    """
    Query Elasticsearch documents for simulation
    """

    connection_id = request.POST.get("connection_id")
    index = request.POST.get("index")
    query_method = request.POST.get("query_method")  # 'field' or 'docid'

    if not connection_id or not index:
        return JsonResponse({"error": "connection_id and index are required"}, status=400)

    try:
        if query_method == "docid":
            doc_ids = request.POST.get("doc_ids", "").strip().split("\n")
            doc_ids = [d.strip() for d in doc_ids if d.strip()]
            documents = query_elasticsearch_documents(connection_id, index, doc_ids=doc_ids)
        elif query_method == "entire":
            # Entire document - fetch with all fields
            size = int(request.POST.get("size", 10))
            query = request.POST.get("query", "")
            documents = query_elasticsearch_documents(
                connection_id, index, field=None, size=size, query_string=query
            )
        else:  # field method
            field = request.POST.get("field")
            size = int(request.POST.get("size", 10))
            query = request.POST.get("query", "")

            if not field:
                return JsonResponse({"error": "field is required for field-based queries"}, status=400)

            documents = query_elasticsearch_documents(
                connection_id, index, field=field, size=size, query_string=query
            )

        return JsonResponse({"documents": documents})
    except Exception as e:
        logger.error(f"Error querying Elasticsearch documents: {e}")
        return JsonResponse({"error": str(e)}, status=500)


def GetPluginDocumentation(request):
    """
    Securely proxy plugin documentation URLs with allowlist validation.
    Only allows documentation from trusted Elastic/Logstash domains.
    """
    plugin_type = request.GET.get("type")
    plugin_name = request.GET.get("name")
    
    if not plugin_type or not plugin_name:
        return JsonResponse({"error": "type and name are required"}, status=400)
    
    try:
        # Load plugin data to get the documentation URL
        plugin_data = _load_plugin_data()
        
        if plugin_type not in plugin_data:
            return JsonResponse({"error": f"Invalid plugin type: {plugin_type}"}, status=400)
        
        if plugin_name not in plugin_data[plugin_type]:
            return JsonResponse({"error": f"Plugin not found: {plugin_name}"}, status=404)
        
        plugin = plugin_data[plugin_type][plugin_name]
        doc_url = plugin.get("link")
        
        if not doc_url:
            return JsonResponse({"error": "No documentation URL available for this plugin"}, status=404)
        
        # Allowlist of trusted documentation domains
        ALLOWED_DOC_DOMAINS = [
            "www.elastic.co",
            "elastic.co",
            "github.com",
            "rubydoc.info"
        ]
        
        # Parse and validate the URL
        from urllib.parse import urlparse
        parsed_url = urlparse(doc_url)
        
        # Check if domain is in allowlist
        if not any(parsed_url.netloc.endswith(domain) or parsed_url.netloc == domain 
                   for domain in ALLOWED_DOC_DOMAINS):
            logger.warning(f"Blocked documentation URL from untrusted domain: {doc_url}")
            return JsonResponse({"error": "Documentation URL is not from a trusted domain"}, status=403)
        
        # Return the validated URL (frontend will use it in iframe)
        return JsonResponse({
            "url": doc_url,
            "plugin_name": plugin_name,
            "plugin_type": plugin_type
        })
        
    except Exception as e:
        logger.error(f"Error fetching plugin documentation: {e}")
        return JsonResponse({"error": str(e)}, status=500)
