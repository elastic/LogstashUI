
# Django
from django.shortcuts import render, HttpResponse
from django.http import JsonResponse, HttpResponseRedirect
from functools import wraps

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
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import re
import html

import logging

logger = logging.getLogger(__name__)


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

@require_http_methods(["GET"])
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
            print(f"Returning success response with connection ID: {new_connection.id}")
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

            for pipeline_name, pipeline_data in pipelines.items():
                # Format last_modified timestamp
                last_modified_str = pipeline_data.get("last_modified", "")
                formatted_date = ""
                if last_modified_str:
                    try:
                        from datetime import datetime
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
def CreatePipeline(request):
    if request.method == "POST":
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

        es = get_elastic_connection(es_id)
        pipeline_doc = es.logstash.put_pipeline(
            id=pipeline_name,
            body={
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