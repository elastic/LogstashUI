
# Django
from django.shortcuts import render, HttpResponse
from django.http import JsonResponse, HttpResponseRedirect
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

## Tables
from Core.models import Connection as ConnectionTable
from Core.views import get_elastic_connection, test_elastic_connectivity, get_logstash_pipeline, get_elastic_connections_from_list

# Custom libraries
from . import logstash_config_parse
from Core import logstash_metrics

# General libraries
import json
import os
import subprocess
import tempfile
from deepdiff import DeepDiff
from PipelineManager.forms import ConnectionForm
from datetime import datetime, timezone

from django.template.loader import get_template
import traceback
import re
import html

import logging
from django.views.decorators.csrf import csrf_exempt
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)

# Global storage for simulation results (in-memory for now)
simulation_results = deque(maxlen=1000)
simulation_lock = Lock()


def require_admin_role(view_func):
    """
    Decorator to check if user has admin role before allowing access to view.
    Returns error toast message if user is readonly.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check if user is authenticated
        if not request.user.is_authenticated:
            response = HttpResponse('You must be logged in to perform this action', status=403)
            response['HX-Trigger'] = '{"showToastEvent": {"message": "You must be logged in to perform this action", "type": "error"}}'
            return response
        
        # Check if user has admin role
        if hasattr(request.user, 'profile'):
            if request.user.profile.role != 'admin':
                logger.warning(f"User '{request.user.username}' with role '{request.user.profile.role}' attempted to access admin-only function: {view_func.__name__}")
                response = HttpResponse('Access denied: Admin role required', status=403)
                response['HX-Trigger'] = '{"showToastEvent": {"message": "Access denied: Admin role required", "type": "error"}}'
                return response
        
        # User is admin, proceed with the view
        return view_func(request, *args, **kwargs)
    
    return wrapper


def validate_pipeline_name(pipeline_name):
    """
    Validate pipeline name according to Elasticsearch rules.
    
    Pipeline ID must:
    - Begin with a letter or underscore
    - Contain only letters, underscores, dashes, hyphens, and numbers
    
    Args:
        pipeline_name (str): The pipeline name to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not pipeline_name:
        return False, "Pipeline name cannot be empty"
    
    # Check if starts with letter or underscore
    if not re.match(r'^[a-zA-Z_]', pipeline_name):
        return False, f"Invalid pipeline [{pipeline_name}] ID received. Pipeline ID must begin with a letter or underscore and can contain only letters, underscores, dashes, hyphens, and numbers"
    
    # Check if contains only valid characters
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_\-]*$', pipeline_name):
        return False, f"Invalid pipeline [{pipeline_name}] ID received. Pipeline ID must begin with a letter or underscore and can contain only letters, underscores, dashes, hyphens, and numbers"
    
    return True, None


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
                # If test fails, delete the connection and show error
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
            
            # Connection test succeeded, proceed with success response
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

    return HttpResponse("""
        <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg">
            Connection created and tested successfully!
            <script>
                // Close the flyout after a short delay
                setTimeout(() => {
                    const flyout = document.getElementById('connectionFormFlyout');
                    if (flyout) {
                        flyout.classList.add('hidden');
                    }
                    // Reload the page to show the new connection
                    window.location.reload();
                }, 500);
            </script>
        </div>
    """)

@require_admin_role
def DeleteConnection(request, connection_id=None):
    if connection_id:
        connection = ConnectionTable.objects.filter(id=connection_id).first()
        if connection:
            logger.warning(f"User '{request.user.username}' deleted connection '{connection.name}' (ID: {connection_id})")
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
    data = json.loads(request.POST.get("components"))
    if "save_pipeline" in request.POST:
        pipeline_name = request.POST.get("pipeline")
        
        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(
                f'<div class="p-4 bg-red-900/20 border border-red-600 rounded-lg"><p class="text-red-400">{error_msg}</p></div>',
                status=400
            )
        
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
        
        logger.info(f"User '{request.user.username}' saved pipeline '{pipeline_name}' (Connection ID: {request.POST.get('es_id')})")
        return HttpResponse("Pipeline saved successfully!")

def GetDiff(request):
    """Generate a unified diff between current and new pipeline configurations"""
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        pipeline_name = request.POST.get("pipeline")
        components_json = request.POST.get("components")
        add_ids = request.POST.get("add_ids", "false").lower() == "true"
        
        if not es_id or not pipeline_name or not components_json:
            return JsonResponse({"error": "Missing required parameters"}, status=400)
        
        try:
            # Get the current pipeline from Elasticsearch
            current_pipeline = get_logstash_pipeline(es_id, pipeline_name)['pipeline']
            
            # Generate the new pipeline from components
            components = json.loads(components_json)
            parser = logstash_config_parse.ComponentToPipeline(components, add_ids=add_ids)
            new_pipeline = parser.components_to_logstash_config()
            
            # Generate unified diff
            import difflib
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


def GetPipelines(request, connection_id):
    context = {}
    connection = ConnectionTable.objects.get(pk=connection_id)

    logstash_pipelines = []
    if connection.connection_type == "CENTRALIZED":
        # --- Gets our pipelines from the connection
        try:
            es = get_elastic_connection(connection.id)
            pipelines = es.logstash.get_pipeline()

            for pipeline in pipelines:
                logstash_pipelines.append(
                    {
                        "es_id": connection.id,
                        "es_name": connection.name,
                        "name": pipeline
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
                "pipeline": current_pipeline_config['pipeline'],
                "pipeline_settings":{},

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
            # Note: The actual API call depends on your Elasticsearch/Logstash setup
            # This is a placeholder - adjust based on your actual API structure
            response = es.logstash.put_pipeline(
                id=pipeline_name,
                body=settings_body
            )
            
            logger.info(f"User '{request.user.username}' updated settings for pipeline '{pipeline_name}' (Connection ID: {es_id})")
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
    import requests
    from django.conf import settings
    
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
            # Determine protocol based on DEBUG mode
            protocol = "http" if settings.DEBUG else "https"
            logstash_agent_url = f"{protocol}://127.0.0.1:9500/_logstash/pipeline/{pipeline_name}"
            
            try:
                response = requests.put(
                    logstash_agent_url,
                    json=pipeline_body,
                    verify=False,  # --insecure equivalent
                    timeout=10
                )
                response.raise_for_status()
                logger.info(f"User '{request.user.username}' created simulation pipeline '{pipeline_name}' in LogstashAgent")
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
            
            logger.info(f"User '{request.user.username}' created new pipeline '{pipeline_name}' (Connection ID: {es_id})")
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
                return HttpResponse(f"Pipeline '{new_pipeline}' already exists. Please choose a different name.", status=400)
            
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
            
            logger.info(f"User '{request.user.username}' cloned pipeline '{source_pipeline}' to '{new_pipeline}' (Connection ID: {es_id})")
            
            # Close the modal and refresh the pipeline list
            response = HttpResponse("""
                <script>
                    document.getElementById('clonePipelineModal').close();
                    htmx.ajax('GET', '/API/GetPipelines/""" + str(es_id) + """/', {target: '#pipelines-""" + str(es_id) + """', swap: 'innerHTML'});
                </script>
            """)
            return response
            
        except Exception as e:
            logger.error(f"Error cloning pipeline: {str(e)}")
            return HttpResponse(f"Error cloning pipeline: {str(e)}", status=500)


def GetLogstashPipeline(request):
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        pipeline_name = request.POST.get("pipeline")

        pipeline_doc = es.logstash.get_pipeline(id=pipeline_name)

        return HttpResponse(pipeline_doc)

def GetPipeline(request):
    if request.method == "GET":
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")

        pipeline_string = get_logstash_pipeline(es_id, pipeline_name)['pipeline']

        return JsonResponse({"code": pipeline_string})


def _format_uptime(milliseconds):
    """Format uptime from milliseconds to human-readable string"""
    seconds = milliseconds // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    
    if days > 0:
        return f"{days}d {hours % 24}h"
    elif hours > 0:
        return f"{hours}h {minutes % 60}m"
    elif minutes > 0:
        return f"{minutes}m {seconds % 60}s"
    else:
        return f"{seconds}s"


def GetNodeMetrics(request):
    connection_name = request.GET.get("connection", "")
    logstash_host = request.GET.get("host", "")
    pipeline = request.GET.get("pipeline", "")

    # Get the metrics data
    metrics_data = logstash_metrics.get_node_metrics(
        get_elastic_connections_from_list(), 
        connection_name, 
        logstash_host, 
        pipeline
    )
    
    # Pre-process node_buckets to extract nested data
    processed_buckets = []
    for bucket in metrics_data.get('node_buckets', []):
        try:
            node_data = bucket['last_hit']['hits']['hits'][0]['_source']['logstash']['node']['stats']
            logstash_info = node_data.get('logstash', {})
            
            node_name = bucket['key']
            status = logstash_info.get('status', 'unknown')
            version = logstash_info.get('version', 'N/A')
            uptime_ms = node_data.get('jvm', {}).get('uptime_in_millis', 0)
            uptime = _format_uptime(uptime_ms)
            
            # Try to get CPU from os.cpu.percent, fallback to process.cpu.percent
            cpu_percent = node_data.get('os', {}).get('cpu', {}).get('percent') or \
                         node_data.get('process', {}).get('cpu', {}).get('percent', 0)
            
            heap_percent = node_data.get('jvm', {}).get('mem', {}).get('heap_used_percent', 0)
            events_in = node_data.get('events', {}).get('in', 0)
            events_out = node_data.get('events', {}).get('out', 0)
            queued = node_data.get('queue', {}).get('events_count', 0)
            reload_success = node_data.get('reloads', {}).get('successes', 0)
            reload_failures = node_data.get('reloads', {}).get('failures', 0)
            
            conn_id = bucket.get('connection_id')
            conn_name = bucket.get('connection_name')
            
            processed_buckets.append({
                'node_name': node_name,
                'connection_id': conn_id,
                'connection_name': conn_name,
                'status': status,
                'version': version,
                'uptime': uptime,
                'cpu_percent': cpu_percent,
                'heap_percent': heap_percent,
                'events_in': events_in,
                'events_out': events_out,
                'queued': queued,
                'reload_success': reload_success,
                'reload_failures': reload_failures,
            })
        except (KeyError, IndexError) as e:
            logger.error(f"Error processing node bucket: {e}")
            continue
    
    metrics_data['processed_node_buckets'] = processed_buckets
    
    # Render as HTML template instead of JSON
    response = render(request, 'components/node_metrics.html', context=metrics_data)
    
    # Add available hosts to response header for JavaScript to populate dropdown
    import json
    response['X-Available-Hosts'] = json.dumps(metrics_data.get('nodes', []))
    
    return response


def _safe_extract_value(data, default=0):
    """
    Safely extract a value from pipeline data.
    Returns default if value is None, empty list, or invalid.
    """
    if data is None:
        return default
    if isinstance(data, list):
        # If it's an empty list or list with no valid values, return default
        if not data or all(v is None or v == '' for v in data):
            return default
        # If it's a list with values, return the first non-null value
        for v in data:
            if v is not None and v != '':
                return v
        return default
    return data


def GetPipelineHealthReport(request):
    connection_id = request.GET.get("connection_id", "")
    pipeline = request.GET.get("pipeline", "")

    # Get the health report data
    health_report_data = logstash_metrics.get_pipeline_health_report(
        get_elastic_connection(connection_id),
        pipeline
    )

    return JsonResponse(health_report_data)


def GetPipelineMetrics(request):
    connection_name = request.GET.get("connection", "")
    logstash_host = request.GET.get("host", "")
    pipeline = request.GET.get("pipeline", "")
    
    # Get the metrics data
    metrics_data = logstash_metrics.get_pipeline_metrics(
        get_elastic_connections_from_list(), 
        connection_name, 
        logstash_host, 
        pipeline
    )
    
    # Pre-process pipeline_buckets to extract nested data (Django can't access _source)
    processed_buckets = []
    for bucket in metrics_data.get('pipeline_buckets', []):
        try:
            pipeline_data = bucket['last_hit']['hits']['hits'][0]['_source']['logstash']['pipeline']
            pipeline_name = bucket['key']
            
            # Track if pipeline has issues
            has_issues = False
            missing_fields = []
            
            conn_id = bucket.get('connection_id')
            conn_name = bucket.get('connection_name')
            
            # Debug output
            if not conn_id:
                logger.warning(f"WARNING: No connection_id for pipeline {pipeline_name}. Bucket keys: {bucket.keys()}")

            
            results = {
                'pipeline_name': pipeline_name,
                'connection_id': conn_id,
                'connection_name': conn_name,
                'host_name': _safe_extract_value(pipeline_data.get('host', {}).get('name'), 'Unknown'),
                'events_in': _safe_extract_value(pipeline_data.get('total', {}).get('events', {}).get('in')),
                'events_out': _safe_extract_value(pipeline_data.get('total', {}).get('events', {}).get('out')),
                'events_filtered': _safe_extract_value(pipeline_data.get('total', {}).get('events', {}).get('filtered')),
                'duration_ms': _safe_extract_value(pipeline_data.get('total', {}).get('time', {}).get('duration', {}).get('ms')),
                'reload_success': _safe_extract_value(pipeline_data.get('total', {}).get('reloads', {}).get('successes')),
                'reload_failures': _safe_extract_value(pipeline_data.get('total', {}).get('reloads', {}).get('failures')),
            }
            
            # Handle info field (workers and batch_size)
            info = pipeline_data.get('info', {})
            
            # Check if info is an empty list or dict
            if isinstance(info, list) or not info:
                has_issues = True
                missing_fields.extend(['workers', 'batch_size'])
                results['workers'] = 0
                results['batch_size'] = 0
            else:
                workers = _safe_extract_value(info.get('workers'))
                batch_size = _safe_extract_value(info.get('batch_size'))
                
                results['workers'] = workers
                results['batch_size'] = batch_size
                
                if workers == 0:
                    has_issues = True
                    missing_fields.append('workers')
                if batch_size == 0:
                    has_issues = True
                    missing_fields.append('batch_size')
            
            # Flag pipeline if it has issues
            results['has_issues'] = has_issues
            results['missing_fields'] = missing_fields

            processed_buckets.append(results)
        except (KeyError, IndexError) as e:
            logger.error(f"Error processing pipeline bucket: {e}")
            continue
    
    metrics_data['processed_pipeline_buckets'] = processed_buckets
    
    # Render as HTML template instead of JSON
    return render(request, 'components/pipeline_metrics.html', context=metrics_data)


def GetLogs(request):
    logstash_node = request.GET.get("logstash_node", "")
    pipeline_name = request.GET.get("pipeline_name", "")
    connection_id = request.GET.get("connection_id", "")
    
    # Require connection_id to be provided
    if not connection_id:
        return JsonResponse({"error": "connection_id is required"}, status=400)
    
    try:
        es = get_elastic_connection(connection_id)
        all_logs = logstash_metrics.get_logs(es, logstash_node, pipeline_name)
        return JsonResponse(all_logs, safe=False)
    except Exception as e:
        logger.error(f"Error fetching logs for connection {connection_id}: {e}")
        return JsonResponse({"error": f"Failed to fetch logs: {str(e)}"}, status=500)


def _generate_filter_pipeline_config(filter_plugin, filter_num, next_filter_id):
    """
    Generate a mini-pipeline config for a single filter plugin with Ruby instrumentation.
    
    Args:
        filter_plugin: The filter plugin component dict
        filter_num: The filter number (1, 2, 3, etc.)
        next_filter_id: The next pipeline address to send to (or 'filter-final' for last)
    
    Returns:
        String containing the pipeline config
    """
    # Convert the single filter plugin to Logstash config format
    converter = logstash_config_parse.ComponentToPipeline({'filter': [filter_plugin]}, test=False)
    filter_config = converter.components_to_logstash_config()
    
    # Extract just the filter block content (remove 'filter {' and closing '}')
    lines = filter_config.strip().split('\n')
    filter_content = '\n'.join(lines[1:-1])  # Skip first and last lines
    
    # Build the mini-pipeline with Ruby instrumentation
    pipeline_config = f'''input {{ pipeline {{ address => "filter{filter_num}" }} }}

filter {{
  ruby {{
    code => "
      event.set('[@metadata][PIPELINE-ID][f{filter_num:03d}-pre]', event.to_hash)
    "
  }}
  
{filter_content}
  
  ruby {{
    code => "
      event.set('[@metadata][PIPELINE-ID][f{filter_num:03d}-post]', event.to_hash)
    "
  }}
}}

output {{
  pipeline {{ send_to => "{next_filter_id}" }}
  pipeline {{ send_to => "output-block" }}
}}
'''
    return pipeline_config


@require_admin_role
def SimulatePipeline(request):
    """
    Simulate a pipeline by generating dynamic filter pipelines with Ruby instrumentation.
    Each filter plugin gets its own mini-pipeline that captures pre/post event state.
    """
    import requests
    from django.conf import settings
    
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        # Get the components from the request
        components_json = request.POST.get('components')
        log_text = request.POST.get('log_text', '').strip()

        print(request.POST['components'])

        if not components_json:
            return HttpResponse('<div class="text-red-400">Error: No pipeline components provided</div>')
        
        if not log_text:
            return HttpResponse('<div class="text-red-400">Error: No log input provided</div>')
        
        # Parse components
        try:
            components = json.loads(components_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse components JSON: {e}")
            return HttpResponse(f'<div class="text-red-400">Error: Invalid components data</div>')
        
        # Extract filter plugins from components
        filter_plugins = components.get('filter', [])
        
        if not filter_plugins:
            return HttpResponse('<div class="text-yellow-400">Warning: No filter plugins found in pipeline</div>')
        
        # Determine protocol based on DEBUG mode
        protocol = "http" if settings.DEBUG else "https"
        logstash_agent_url = f"{protocol}://127.0.0.1:9500/_logstash/pipeline"
        
        created_pipelines = []
        
        # Generate and create a pipeline for each filter
        for idx, filter_plugin in enumerate(filter_plugins, start=1):
            # Determine next filter address
            if idx < len(filter_plugins):
                next_filter_id = f"filter{idx + 1}"
            else:
                next_filter_id = "filter-final"
            
            # Generate pipeline config for this filter
            try:
                pipeline_config = _generate_filter_pipeline_config(filter_plugin, idx, next_filter_id)
            except Exception as e:
                logger.error(f"Failed to generate config for filter {idx}: {e}")
                logger.error(traceback.format_exc())
                return HttpResponse(f'<div class="text-red-400">Error generating filter {idx} config: {str(e)}</div>')
            
            # Create the pipeline in LogstashAgent
            pipeline_name = f"filter{idx}"
            pipeline_body = {
                "pipeline": pipeline_config,
                "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                "pipeline_metadata": {
                    "version": 1,
                    "type": "logstash_pipeline"
                },
                "username": "LogstashUI",
                "pipeline_settings": {
                    "pipeline.workers": 1
                }
            }
            
            try:
                response = requests.put(
                    f"{logstash_agent_url}/{pipeline_name}",
                    json=pipeline_body,
                    verify=False,
                    timeout=10
                )
                response.raise_for_status()
                created_pipelines.append(pipeline_name)
                logger.info(f"Created simulation pipeline: {pipeline_name}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to create pipeline {pipeline_name}: {e}")
                return HttpResponse(f'<div class="text-red-400">Error creating pipeline {pipeline_name}: {str(e)}</div>')
        
        # Wait a moment for Logstash to reload the pipelines
        import time
        time.sleep(4)
        
        # Send the user's log input to the simulation HTTP input
        simulation_input_url = f"{protocol}://127.0.0.1:8082"
        try:
            # Parse log_text as JSON if it looks like JSON, otherwise send as message field
            try:
                log_data = json.loads(log_text)
            except json.JSONDecodeError:
                # Not JSON, wrap it in a message field
                log_data = {"message": log_text}
            
            response = requests.post(
                simulation_input_url,
                json=log_data,
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Sent simulation input to {simulation_input_url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send simulation input: {e}")
            return HttpResponse(f'<div class="text-red-400">Error sending simulation input: {str(e)}</div>')
        
        # Wait a moment for pipeline processing to complete
        time.sleep(2)
        
        # Cleanup: Delete the dynamically created filter pipelines
        for pipeline_name in created_pipelines:
            try:
                response = requests.delete(
                    f"{logstash_agent_url}/{pipeline_name}",
                    verify=False,
                    timeout=10
                )
                response.raise_for_status()
                logger.info(f"Deleted simulation pipeline: {pipeline_name}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to delete pipeline {pipeline_name}: {e}")
        
        # Return success message - results will be streamed via StreamSimulate endpoint
        result_html = f'''
        <div class="space-y-4">
            <div class="p-4 bg-green-900/30 border border-green-600 rounded-lg">
                <h3 class="text-lg font-semibold text-green-400 mb-2">✓ Simulation Started</h3>
                <p class="text-green-200">Processing {len(created_pipelines)} filter(s) - results streaming below</p>
            </div>
            
            <div class="p-4 bg-gray-700 rounded-lg">
                <h4 class="text-sm font-semibold text-gray-300 mb-2">Pipeline Chain:</h4>
                <pre class="text-xs text-gray-300 overflow-auto bg-gray-800 p-3 rounded">simulate-start → {' → '.join(created_pipelines)} → simulate-end → output-block → StreamSimulate</pre>
            </div>
            
            <div id="simulation-results" class="p-4 bg-gray-800 rounded-lg">
                <h4 class="text-sm font-semibold text-gray-300 mb-2">📊 Results:</h4>
                <div id="results-stream" class="text-xs text-gray-300 font-mono whitespace-pre-wrap max-h-96 overflow-auto bg-gray-900 p-3 rounded"></div>
            </div>
        </div>
        
        <script>
        (function() {{
            let pollCount = 0;
            const maxPolls = 30; // Poll for 30 seconds max
            const pollInterval = 1000; // Poll every 1 second
            
            function pollResults() {{
                if (pollCount >= maxPolls) {{
                    const stream = document.getElementById('results-stream');
                    if (stream && stream.innerHTML.trim() === '') {{
                        stream.innerHTML = '<span class="text-yellow-400">No results received. Check Logstash logs.</span>';
                    }}
                    return;
                }}
                
                fetch('/API/GetSimulationResults/')
                    .then(response => response.json())
                    .then(data => {{
                        console.log('Poll response:', data);
                        console.log('Results count:', data.results ? data.results.length : 0);
                        
                        if (data.results && data.results.length > 0) {{
                            console.log('Processing', data.results.length, 'events');
                            const stream = document.getElementById('results-stream');
                            console.log('Stream element:', stream);
                            
                            if (stream) {{
                                data.results.forEach(event => {{
                                    const eventStr = JSON.stringify(event, null, 2);
                                    stream.innerHTML += eventStr + '\\n\\n---\\n\\n';
                                }});
                                stream.scrollTop = stream.scrollHeight;
                                console.log('Updated stream innerHTML length:', stream.innerHTML.length);
                            }} else {{
                                console.error('results-stream element not found!');
                            }}
                        }}
                        
                        pollCount++;
                        setTimeout(pollResults, pollInterval);
                    }})
                    .catch(error => {{
                        console.error('Error polling results:', error);
                        pollCount++;
                        setTimeout(pollResults, pollInterval);
                    }});
            }}
            
            // Start polling after a short delay
            setTimeout(pollResults, 2000);
        }})();
        </script>
        '''
        
        return HttpResponse(result_html)
        
    except Exception as e:
        logger.error(f"Error in SimulatePipeline: {e}")
        logger.error(traceback.format_exc())
        return HttpResponse(f'<div class="text-red-400">Error: {str(e)}</div>')


@csrf_exempt
def StreamSimulate(request):
    """
    Receive simulation results from Logstash HTTP output and store them.
    This endpoint is called by the output-block pipeline for each event.
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        # Parse the incoming event data
        event_data = json.loads(request.body)
        
        # Store the event in the global results queue
        with simulation_lock:
            simulation_results.append(event_data)
            queue_size = len(simulation_results)
        
        logger.info(f"StreamSimulate: Received event, queue size now: {queue_size}")
        logger.debug(f"StreamSimulate: Event data keys: {list(event_data.keys())}")
        
        return JsonResponse({"status": "ok"}, status=200)
        
    except Exception as e:
        logger.error(f"Error in StreamSimulate: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)


def GetSimulationResults(request):
    """
    Poll endpoint for frontend to retrieve simulation results.
    Returns all stored results and clears the queue.
    """
    if request.method != 'GET':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        # Get all results and clear the queue
        with simulation_lock:
            results = list(simulation_results)
            simulation_results.clear()
        
        logger.info(f"GetSimulationResults: Returning {len(results)} events")
        if results:
            logger.debug(f"GetSimulationResults: First event keys: {list(results[0].keys())}")
        
        return JsonResponse({"results": results}, status=200)
        
    except Exception as e:
        logger.error(f"Error in GetSimulationResults: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)