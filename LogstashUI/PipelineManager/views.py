from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template
from django.conf import settings

from .forms import ConnectionForm # Lives here because UI will only be here

from PipelineManager.models import Connection as ConnectionTable

from Common.decorators import require_admin_role
from Common.logstash_utils import get_logstash_pipeline
from Common.elastic_utils import get_elastic_connection, test_elastic_connectivity, query_elasticsearch_documents, \
    get_elastic_connections_from_list, get_elasticsearch_indices, get_elasticsearch_field_mappings
from Common.validators import validate_pipeline_name
from Common import logstash_config_parse

from datetime import datetime, timezone

import json
import os
import logging
import html
import traceback
import requests
import difflib


logger = logging.getLogger(__name__)




def _load_plugin_data():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(app_dir, 'data', 'plugins.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def PipelineEditor(request):
    context = {
        "plugin_data": _load_plugin_data()
    }

    if request.method == "GET":
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")


        pipeline_config = get_logstash_pipeline(es_id, pipeline_name)

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
            context['component_data'] = parsed_config
        except Exception as e:
            # Capture the parsing error to show to the user
            context['parsing_error'] = str(e)
            context['component_data'] = {
                "input": [],
                "filter": [],
                "output": []
            }

    return render(request, "pipeline_editor.html", context=context)

# Builds the table of pipelines
def PipelineManager(request):

    context = {}
    if request.method == "POST":
        try:
            is_htmx = request.headers.get('HX-Request') == 'true'

            if is_htmx:

                form = ConnectionForm(request.POST)

                if form.is_valid():
                    form.save()
                else:
                    raise Exception(form.errors)

                return HttpResponse("""
                    <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg">
                        Connection created successfully!
                        <script>
                            // Close the flyout after a short delay
                            setTimeout(() => {
                                const flyout = document.getElementById('connectionFormFlyout');
                                if (flyout) {
                                    flyout.classList.add('hidden');
                                }
                                // Reload the page to show the new connection
                                window.location.reload();
                            }, 100000);
                        </script>
                    </div>
                """)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            if request.headers.get('HX-Request') == 'true':
                return HttpResponse(f"""
                    <div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">
                        {error_message}
                    </div>
                """, status=400)

            return redirect('logstash')

    connections = list(ConnectionTable.objects.values("connection_type", "name", "host", "cloud_id", "cloud_url", "pk"))
    
    context['connections'] = connections
    context['has_connections'] = len(connections) > 0
    context['form'] = ConnectionForm()

    return render(request, "pipeline_manager.html", context=context)

def TestConnectivity(request=None, connection_id=None):
    # Allow calling from request (frontend) or directly with connection_id (backend)
    logger.info("Testing connection...")
    if request:
        test_id = request.GET.get('test')
    else:
        test_id = connection_id

    if test_id:
        try:
            elastic_connection = get_elastic_connection(test_id)
            result = test_elastic_connectivity(elastic_connection)

            # If called from request, return HTML response
            if request:
                return HttpResponse("""
                    <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg"
                        onload="setTimeout(() => this.remove(), 3000);">
                        <p>{0}</p>
                    </div>
                """.format(result))
            # If called programmatically, return tuple (success, message)
            else:
                return (True, result)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Connection test against {test_id} failed: {error_msg}")
            # If called from request, return HTML error response
            if request:
                return HttpResponse("""
                    <div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">
                        <p>Connection failed: {0}</p>
                    </div>
                """.format(error_msg))
            # If called programmatically, return tuple (failure, error message)
            else:
                return (False, error_msg)

    return (False, "No connection ID provided") if not request else HttpResponse("No connection ID provided")


def GetConnections(request):
    """Get all connections for dropdown population"""
    try:
        connections = ConnectionTable.objects.all().values('id', 'name', 'connection_type')
        return JsonResponse(list(connections), safe=False, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_admin_role
def AddConnection(request):
    if request.method == "POST":

        form = ConnectionForm(request.POST)

        if form.is_valid():
            # Save the connection temporarily
            new_connection = form.save()

            # Test the connection
            success, message = TestConnectivity(connection_id=new_connection.id)
            logger.info(f"User '{request.user.username}' added a new connection, {new_connection.id}")

            if not success:
                # If test fails, delete the connection and return JSON error
                new_connection.delete()
                logger.error(f"User '{request.user.username}' failed to add connection, {new_connection.id}")
                # Escape HTML in error message to prevent injection but preserve formatting

                escaped_message = html.escape(str(message))
                response = HttpResponse(f"""
                    <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
                        <h3 class="font-bold mb-2 text-lg">❌ Connection Test Failed</h3>
                        <p class="mb-3">The connection could not be established. Please check your credentials and try again.</p>
                        <div class="mt-3 p-3 bg-red-50 border border-red-200 rounded">
                            <p class="font-semibold mb-1 text-sm">Error Details:</p>
                            <pre class="text-xs overflow-auto whitespace-pre-wrap break-words max-h-64">{escaped_message}</pre>
                        </div>
                    </div>
                """)
                response['HX-Retarget'] = '#connectionErrorContainer'
                response['HX-Reswap'] = 'innerHTML'

                return response

            # Connection test succeeded, return JSON response
            logger.info(f"Returning success response with connection ID: {new_connection.id}")
            return JsonResponse({
                'success': True,
                'connection_id': new_connection.id,
                'message': 'Connection created and tested successfully!'
            }, status=200)
        else:
            logger.warning(f"User '{request.user.username}' failed to add connection: {form.errors}")
            response = HttpResponse(f"""
                <div class="p-4 mb-4 text-sm text-red-700 bg-red-100 border border-red-300 rounded-lg">
                    <h3 class="font-bold mb-2">Form Validation Error</h3>
                    <div class="text-sm">{form.errors}</div>
                </div>
            """)
            response['HX-Retarget'] = '#connectionErrorContainer'
            response['HX-Reswap'] = 'innerHTML'
            return response

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@require_admin_role
def DeleteConnection(request, connection_id=None):
    if connection_id:
        connection = ConnectionTable.objects.filter(id=connection_id).first()
        if connection:
            logger.warning(
                f"User '{request.user.username}' deleted connection '{connection.name}' (ID: {connection_id})")
        ConnectionTable.objects.filter(id=connection_id).delete()

    return HttpResponse("""
        <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg">
            Connection deleted successfully!
            <script>
                // Reload the page to show the updated connections
                setTimeout(() => {
                    window.location.reload();
                }, 500);
            </script>
        </div>
    """)


def GetPipelines(request, connection_id):
    context = {}
    connection = ConnectionTable.objects.get(pk=connection_id)

    logstash_pipelines = []
    if connection.connection_type == "CENTRALIZED":
        # --- Gets our pipelines from the connection
        try:
            es = get_elastic_connection(connection.id)
            pipelines = es.logstash.get_pipeline()

            for pipeline_name, pipeline_data in pipelines.items():
                # Format last_modified timestamp
                last_modified_str = pipeline_data.get("last_modified", "")
                formatted_date = ""
                if last_modified_str:
                    try:
                        # Parse ISO 8601 format: 2025-11-23T05:30:52.421Z
                        dt = datetime.fromisoformat(last_modified_str.replace('Z', '+00:00'))
                        # Format as "Tuesday, January 14th 2025"
                        day = dt.day
                        suffix = 'th' if 11 <= day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
                        formatted_date = dt.strftime(f'%A, %B {day}{suffix} %Y')
                    except Exception:
                        formatted_date = last_modified_str  # Fallback to original if parsing fails

                logstash_pipelines.append(
                    {
                        "es_id": connection.id,
                        "es_name": connection.name,
                        "name": pipeline_name,
                        "description": pipeline_data.get("description", ""),
                        "last_modified": formatted_date
                    }
                )

        except Exception as e:
            logger.exception("Couldn't connect to Elastic")

    context['pipelines'] = logstash_pipelines
    context['es_id'] = connection.id

    logstash_template = get_template("components/pipeline_manager/collapsible_row.html")
    html = logstash_template.render(context)
    return HttpResponse(html)


@require_admin_role
def UpdatePipelineSettings(request):
    if request.method == "POST":
        try:
            es_id = request.POST.get("es_id")
            pipeline_name = request.POST.get("pipeline")

            # Validate required fields
            if not es_id or not pipeline_name:
                return HttpResponse(
                    '<div class="text-red-400 text-sm">Error: Missing pipeline ID or connection ID</div>',
                    status=400
                )

            # Validate pipeline name
            is_valid, error_msg = validate_pipeline_name(pipeline_name)
            if not is_valid:
                return HttpResponse(
                    f'<div class="text-red-400 text-sm">{error_msg}</div>',
                    status=400
                )

            # Get form values
            description = request.POST.get("description", "")
            pipeline_workers = request.POST.get("pipeline_workers")
            pipeline_batch_size = request.POST.get("pipeline_batch_size")
            pipeline_batch_delay = request.POST.get("pipeline_batch_delay")
            queue_type = request.POST.get("queue_type")
            queue_max_bytes = request.POST.get("queue_max_bytes")
            queue_max_bytes_unit = request.POST.get("queue_max_bytes_unit")
            queue_checkpoint_writes = request.POST.get("queue_checkpoint_writes")

            # Build settings body - only include non-empty values
            current_pipeline_config = get_logstash_pipeline(es_id, pipeline_name)
            settings_body = {
                "pipeline": current_pipeline_config['pipeline'],
                "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                "pipeline_metadata": {
                    "version": current_pipeline_config['pipeline_metadata']['version'] + 1,
                    "type": "logstash_pipeline"
                },
                "username": "LogstashUI",
                "pipeline_settings": {},

            }

            if 'description' in current_pipeline_config:
                settings_body['description'] = current_pipeline_config['description']

            if description:
                settings_body["description"] = description
            if pipeline_workers:
                settings_body['pipeline_settings']["pipeline.workers"] = int(pipeline_workers)
            if pipeline_batch_size:
                settings_body['pipeline_settings']["pipeline.batch.size"] = int(pipeline_batch_size)
            if pipeline_batch_delay:
                settings_body['pipeline_settings']["pipeline.batch.delay"] = int(pipeline_batch_delay)
            if queue_type:
                settings_body['pipeline_settings']["queue.type"] = queue_type
            if queue_max_bytes:
                settings_body['pipeline_settings']["queue.max_bytes"] = f"{queue_max_bytes}{queue_max_bytes_unit}"
            if queue_checkpoint_writes:
                settings_body['pipeline_settings']["queue.checkpoint.writes"] = int(queue_checkpoint_writes)

            # Get Elasticsearch connection and update pipeline settings
            es = get_elastic_connection(es_id)
            es.logstash.put_pipeline(id=pipeline_name, body=settings_body)

            logger.info(
                f"User '{request.user.username}' updated settings for pipeline '{pipeline_name}' (Connection ID: {es_id})")
            # Return empty response - toast notification handled by JavaScript
            return HttpResponse('', status=200)

        except Exception as e:
            # Return simple error message - toast notification handled by JavaScript
            logger.error(traceback.format_exc())
            return HttpResponse(str(e), status=500)

    return HttpResponse('Invalid request method', status=405)


@require_admin_role
def CreatePipeline(request, simulate=False, pipeline_name=None, pipeline_config=None):
    """
    Create a pipeline in Elasticsearch or LogstashAgent.

    Args:
        request: Django request object
        simulate: If True, send to LogstashAgent instead of Elasticsearch
        pipeline_name: Pipeline name (used when called directly for simulation)
        pipeline_config: Pipeline config string (used when called directly for simulation)
    """

    if request.method == "POST" or simulate:
        # Get parameters from POST or function arguments
        if not simulate:
            es_id = request.POST.get("es_id")
            pipeline_name = request.POST.get("pipeline")
            pipeline_config = request.POST.get("pipeline_config", "").strip()

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        # Use provided config or default empty config
        if pipeline_config:
            pipeline_content = pipeline_config
        else:
            pipeline_content = "input {}\nfilter {}\noutput {}"

        # Build the pipeline body
        pipeline_body = {
            "pipeline": pipeline_content,
            "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "pipeline_metadata": {
                "version": 1,
                "type": "logstash_pipeline"
            },
            "username": "LogstashUI",
            "pipeline_settings": {
                "pipeline.batch.delay": 50,
                "pipeline.batch.size": 125,
                "pipeline.workers": 1,
                "queue.checkpoint.writes": 1024,
                "queue.max_bytes": "1gb",
                "queue.type": "memory"
            },
            "description": ""
        }

        if simulate:
            # Send to LogstashAgent
            logstash_agent_url = f"{settings.LOGSTASH_AGENT_URL}/_logstash/pipeline/{pipeline_name}"

            try:
                response = requests.put(
                    logstash_agent_url,
                    json=pipeline_body,
                    verify=False,  # --insecure equivalent
                    timeout=10
                )
                response.raise_for_status()
                logger.info(
                    f"User '{request.user.username}' created simulation pipeline '{pipeline_name}' in LogstashAgent")
                return HttpResponse("Simulation pipeline created successfully!", status=200)
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to create simulation pipeline in LogstashAgent: {e}")
                return HttpResponse(f"Failed to create simulation pipeline: {str(e)}", status=500)
        else:
            # Send to Elasticsearch
            es = get_elastic_connection(es_id)
            pipeline_doc = es.logstash.put_pipeline(
                id=pipeline_name,
                body=pipeline_body
            )

            logger.info(
                f"User '{request.user.username}' created new pipeline '{pipeline_name}' (Connection ID: {es_id})")
            response = HttpResponse("Pipeline created successfully!")
            response['HX-Redirect'] = f'/ConnectionManager/Pipelines/Editor/?es_id={es_id}&pipeline={pipeline_name}'
            return response


@require_admin_role
def DeletePipeline(request):
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        pipeline_name = request.POST.get("pipeline")

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        es = get_elastic_connection(es_id)
        es.logstash.delete_pipeline(id=pipeline_name)

        logger.warning(f"User '{request.user.username}' deleted pipeline '{pipeline_name}' (Connection ID: {es_id})")
        return HttpResponse("Pipeline deleted successfully!")


@require_admin_role
def ClonePipeline(request):
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        source_pipeline = request.POST.get("source_pipeline")
        new_pipeline = request.POST.get("new_pipeline")

        # Validate source pipeline name
        is_valid, error_msg = validate_pipeline_name(source_pipeline)
        if not is_valid:
            return HttpResponse(f"Invalid source pipeline name: {error_msg}", status=400)

        # Validate new pipeline name
        is_valid, error_msg = validate_pipeline_name(new_pipeline)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        try:
            es = get_elastic_connection(es_id)

            # Get the source pipeline configuration
            source_config = es.logstash.get_pipeline(id=source_pipeline)

            if source_pipeline not in source_config:
                return HttpResponse(f"Source pipeline '{source_pipeline}' not found", status=404)

            source_data = source_config[source_pipeline]

            # Check if new pipeline name already exists
            existing_pipelines = es.logstash.get_pipeline()
            if new_pipeline in existing_pipelines:
                return HttpResponse(f"Pipeline '{new_pipeline}' already exists. Please choose a different name.",
                                    status=400)

            # Create the new pipeline with the same configuration as the source
            es.logstash.put_pipeline(
                id=new_pipeline,
                body={
                    "pipeline": source_data['pipeline'],
                    "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                    "pipeline_metadata": {
                        "version": 1,
                        "type": "logstash_pipeline"
                    },
                    "username": "LogstashUI",
                    "pipeline_settings": source_data.get('pipeline_settings', {}),
                    "description": source_data.get('description', f"Cloned from {source_pipeline}")
                }
            )

            logger.info(
                f"User '{request.user.username}' cloned pipeline '{source_pipeline}' to '{new_pipeline}' (Connection ID: {es_id})")

            # Close the modal and refresh the pipeline list
            response = HttpResponse("""
                <script>
                    document.getElementById('clonePipelineModal').close();
                    htmx.ajax('GET', '/ConnectionManager/GetPipelines/""" + str(
                es_id) + """/', {target: '#pipelines-""" + str(es_id) + """', swap: 'innerHTML'});
                </script>
            """)
            return response

        except Exception as e:
            logger.error(f"Error cloning pipeline: {str(e)}")
            return HttpResponse(f"Error cloning pipeline: {str(e)}", status=500)


def GetPipeline(request):
    if request.method == "GET":
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")

        pipeline_string = get_logstash_pipeline(es_id, pipeline_name)['pipeline']

        return JsonResponse({"code": pipeline_string})


def GetCurrentPipelineCode(request, components={}):
    if not components:
        data = json.loads(request.POST.get("components"))
    else:
        data = components
    parser = logstash_config_parse.ComponentToPipeline(data)
    config = parser.components_to_logstash_config()

    # Return the code wrapped in a pre tag with proper formatting
    return HttpResponse(
        f'<pre class="bg-gray-900 text-green-400 p-4 rounded overflow-auto"><code class="language-ruby">{config}</code></pre>',
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
                error_message = str(e)
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

        es = get_elastic_connection(request.POST.get("es_id"))
        current_pipeline_config = es.logstash.get_pipeline(id=pipeline_name)

        es.logstash.put_pipeline(id=pipeline_name, body={
            "pipeline": config,
            "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "pipeline_metadata": current_pipeline_config[pipeline_name]['pipeline_metadata'],
            "username": "LogstashUI",
            "pipeline_settings": current_pipeline_config[pipeline_name]['pipeline_settings'],
            "description": current_pipeline_config[pipeline_name]['description']
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
        es_id = request.POST.get("es_id")
        pipeline_name = request.POST.get("pipeline")
        pipeline_text = request.POST.get("pipeline_text")  # Raw text from Text mode
        components_json = request.POST.get("components")
        add_ids = request.POST.get("add_ids", "false").lower() == "true"

        # Need either pipeline_text or components
        if not es_id or not pipeline_name or (not pipeline_text and not components_json):
            return JsonResponse({"error": "Missing required parameters"}, status=400)

        try:
            # Get the current pipeline from Elasticsearch
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
