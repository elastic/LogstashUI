
# Django
from django.shortcuts import render, HttpResponse
from django.http import JsonResponse, HttpResponseRedirect
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.conf import settings

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
import requests

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


@require_admin_role
def SimulatePipeline(request):
    """
    Simulate a pipeline by building a single pipeline with Ruby instrumentation
    injected after each filter plugin to capture step-by-step event state.
    """
    import requests
    from django.conf import settings
    import hashlib
    import uuid
    
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        # Get the components from the request
        components_json = request.POST.get('components')
        log_text = request.POST.get('log_text', '').strip()

        if not components_json:
            return HttpResponse('<div class="text-red-400">Error: No pipeline components provided</div>')
        
        # Parse components
        try:
            components = json.loads(components_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse components JSON: {e}")
            return HttpResponse(f'<div class="text-red-400">Error: Invalid components data</div>')
        
        # Extract filter plugins from components
        filter_plugins = components.get('filter', [])
        
        if not filter_plugins and not log_text:
            return HttpResponse('<div class="text-gray-400">No filters to simulate</div>')
        
        if not filter_plugins:
            return HttpResponse('<div class="text-yellow-400">Warning: No filter plugins found in pipeline</div>')
        
        # Generate unique run_id for this simulation
        run_id = str(uuid.uuid4())
        logger.info(f"Starting simulation with run_id: {run_id}")
        
        # Recursive function to instrument plugins, including nested conditionals
        step_counter = [0]  # Use list to maintain counter across recursive calls
        
        def instrument_plugins(plugins_list):
            """
            Recursively instrument plugins, handling conditional (if) plugins specially.
            For 'if' plugins, we instrument the nested plugins but not the condition itself.
            """
            instrumented = []
            
            for plugin in plugins_list:
                if plugin.get('plugin') == 'if':
                    # This is a conditional plugin - we need to instrument its nested plugins
                    conditional_plugin = plugin.copy()
                    conditional_plugin['config'] = plugin['config'].copy()
                    conditional_id = plugin['id']
                    
                    # Instrument plugins in the main 'if' block
                    if 'plugins' in conditional_plugin['config']:
                        # Add branch tracking at the start of the if block
                        # Escape single quotes in the condition for Ruby string
                        if_condition = conditional_plugin['config'].get('condition', '').replace("'", "\\'")
                        branch_tracker = {
                            "id": f"{conditional_id}_if_tracker",
                            "type": "filter",
                            "plugin": "ruby",
                            "config": {
                                "code": f"""
event.set('[conditional_branches][{conditional_id}]', 'if')
event.set('[conditional_conditions][{conditional_id}]', '{if_condition}')
""".strip()
                            }
                        }
                        conditional_plugin['config']['plugins'] = [branch_tracker] + instrument_plugins(
                            conditional_plugin['config']['plugins']
                        )
                    
                    # Instrument plugins in 'else_ifs' blocks
                    if 'else_ifs' in conditional_plugin['config']:
                        instrumented_else_ifs = []
                        for else_if_idx, else_if in enumerate(conditional_plugin['config']['else_ifs']):
                            else_if_copy = else_if.copy()
                            if 'plugins' in else_if_copy:
                                # Add branch tracking at the start of the else_if block
                                # Escape single quotes in the condition for Ruby string
                                else_if_condition = else_if.get('condition', '').replace("'", "\\'")
                                branch_tracker = {
                                    "id": f"{conditional_id}_elseif{else_if_idx}_tracker",
                                    "type": "filter",
                                    "plugin": "ruby",
                                    "config": {
                                        "code": f"""
event.set('[conditional_branches][{conditional_id}]', 'else_if_{else_if_idx}')
event.set('[conditional_conditions][{conditional_id}]', '{else_if_condition}')
""".strip()
                                    }
                                }
                                else_if_copy['plugins'] = [branch_tracker] + instrument_plugins(else_if_copy['plugins'])
                            instrumented_else_ifs.append(else_if_copy)
                        conditional_plugin['config']['else_ifs'] = instrumented_else_ifs
                    
                    # Instrument plugins in 'else' block
                    if 'else' in conditional_plugin['config'] and conditional_plugin['config']['else']:
                        else_block = conditional_plugin['config']['else'].copy()
                        if 'plugins' in else_block:
                            # Add branch tracking at the start of the else block
                            branch_tracker = {
                                "id": f"{conditional_id}_else_tracker",
                                "type": "filter",
                                "plugin": "ruby",
                                "config": {
                                    "code": f"""
event.set('[conditional_branches][{conditional_id}]', 'else')
""".strip()
                                }
                            }
                            else_block['plugins'] = [branch_tracker] + instrument_plugins(else_block['plugins'])
                        conditional_plugin['config']['else'] = else_block
                    
                    # Add the conditional plugin with instrumented nested plugins
                    instrumented.append(conditional_plugin)
                else:
                    # Regular plugin - add pre-plugin timing instrumentation
                    # Increment step counter
                    step_counter[0] += 1
                    current_step = step_counter[0]
                    
                    # Add pre-plugin timing instrumentation
                    pre_instrumentation_code = f"""
# Capture start time in nanoseconds before plugin execution
event.set('[simulation][timing][start_ns]', (Time.now.to_f * 1_000_000_000).to_i)
""".strip()

                    pre_instrumentation_plugin = {
                        "id": f"pre_instrumentation_{current_step}",
                        "type": "filter",
                        "plugin": "ruby",
                        "config": {
                            "code": pre_instrumentation_code
                        }
                    }

                    instrumented.append(pre_instrumentation_plugin)

                    # Add the actual plugin
                    instrumented.append(plugin)

                    # Add Ruby instrumentation after this plugin
                    # Note: run_id is NOT included here - it's added to the event data when sent to Logstash
                    # This keeps the instrumentation static so the pipeline config hash is consistent
                    instrumentation_code = f"""
# Update step tracking
event.set('[simulation][step]', {current_step})
event.set('[simulation][id]', '{plugin['id']}')

# Calculate execution time in nanoseconds
end_ns = (Time.now.to_f * 1_000_000_000).to_i
start_ns = event.get('[simulation][timing][start_ns]')
if start_ns
  execution_ns = end_ns - start_ns
  event.set('[simulation][timing][execution_ns]', execution_ns)
  event.set('[simulation][timing][end_ns]', end_ns)
end

# Create snapshot of current event state
snapshot = {{}}
event.to_hash.each do |key, value|
  # Skip metadata and snapshots field itself to avoid recursion
  next if key.start_with?('@metadata') || key == 'snapshots'
  snapshot[key] = value
end

# Store snapshot under the plugin ID
event.set('[snapshots][{plugin['id']}]', snapshot)
""".strip()

                    instrumentation_plugin = {
                        "id": f"instrumentation_{current_step}",
                        "type": "filter",
                        "plugin": "ruby",
                        "config": {
                            "code": instrumentation_code
                        }
                    }

                    instrumented.append(instrumentation_plugin)

            return instrumented

        # Build instrumented filter list
        instrumented_filters = instrument_plugins(filter_plugins)

        # Count total plugins including nested ones in conditionals
        def count_all_plugins(plugins_list):
            """Recursively count all plugins, including those nested in conditionals."""
            count = 0
            for plugin in plugins_list:
                if plugin.get('plugin') == 'if':
                    # Count nested plugins in if block
                    if 'plugins' in plugin.get('config', {}):
                        count += count_all_plugins(plugin['config']['plugins'])

                    # Count nested plugins in else_ifs
                    if 'else_ifs' in plugin.get('config', {}):
                        for else_if in plugin['config']['else_ifs']:
                            if 'plugins' in else_if:
                                count += count_all_plugins(else_if['plugins'])

                    # Count nested plugins in else
                    if 'else' in plugin.get('config', {}) and plugin['config']['else']:
                        if 'plugins' in plugin['config']['else']:
                            count += count_all_plugins(plugin['config']['else']['plugins'])
                else:
                    # Regular plugin - count it
                    count += 1
            return count

        total_plugin_count = count_all_plugins(filter_plugins)
        # Use configured LogstashAgent URL
        logstash_agent_url = settings.LOGSTASH_AGENT_URL
        # Add HTTP output that only sends cloned events (identified by type field)
        output_plugins = [
            {
                "id": "http_output",
                "type": "output",
                "plugin": "http",
                "config": {
                    "url": f"{logstash_agent_url}/API/StreamSimulate/",
                    "http_method": "post",
                    "format": "json",
                    "content_type": "application/json"
                }
            }
        ]

        # Convert filter components to Logstash config
        filter_converter = logstash_config_parse.ComponentToPipeline({'filter': instrumented_filters}, test=False)
        filter_config = filter_converter.components_to_logstash_config()

        # Convert output components to Logstash config
        output_converter = logstash_config_parse.ComponentToPipeline({'output': output_plugins}, test=False)
        output_config = output_converter.components_to_logstash_config()

        # Extract just the content (remove 'filter {' and 'output {' wrappers)
        # The LogstashAgent will add these wrappers when building the complete pipeline
        filter_lines = filter_config.strip().split('\n')
        filter_content = '\n'.join(filter_lines[1:-1]) if len(filter_lines) > 2 else ''

        output_lines = output_config.strip().split('\n')
        output_content = '\n'.join(output_lines[1:-1]) if len(output_lines) > 2 else ''



        # Prepare the pipeline data for slot allocation
        # The slots system will hash this to detect configuration changes
        pipeline_data = {
            "filter_config": filter_content,
            "output_config": output_content,
            "index": 1
        }
        
        # Allocate a slot - the LogstashAgent will detect if config changed
        slot_allocation_body = {
            "pipeline_name": request.GET.get('pipeline', 'simulation'),
            "pipelines": [pipeline_data]
        }
        
        slot_id = None
        try:
            response = requests.post(
                f"{logstash_agent_url}/_logstash/slots/allocate",
                json=slot_allocation_body,
                verify=False,
                timeout=30  # Increased timeout for slot eviction + allocation when slots are full
            )
            
            # Try to extract slot_id from response before checking status
            # This way we have it even if verification fails
            try:
                response_data = response.json()
                slot_id = response_data.get('slot_id')
                reused = response_data.get('reused', False)
            except Exception:
                pass
            
            # Now check if the request was successful
            response.raise_for_status()
            
            logger.info(f"Allocated slot {slot_id} (reused: {reused})")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to allocate slot: {e}")
            logger.error(f"slot_id extracted before error: {slot_id}")
            
            # If slot_id wasn't extracted from successful response, try to get it from error response
            if not slot_id and hasattr(e, 'response') and e.response is not None:
                try:
                    logger.info(f"Error response status: {e.response.status_code}")
                    logger.info(f"Error response content: {e.response.text[:500]}")
                    
                    error_data = e.response.json()
                    logger.info(f"Error response JSON: {error_data}")
                    
                    # Check if detail is a dict with slot_id (new format)
                    detail = error_data.get('detail')
                    logger.info(f"Error detail type: {type(detail)}, value: {detail}")
                    
                    if isinstance(detail, dict):
                        slot_id = detail.get('slot_id')
                        logger.info(f"Extracted slot_id {slot_id} from error response detail dict")
                    elif isinstance(detail, str) and 'Slot' in detail:
                        # Fallback: try to extract from string
                        import re
                        match = re.search(r'Slot (\d+)', detail)
                        if match:
                            slot_id = int(match.group(1))
                            logger.info(f"Extracted slot_id {slot_id} from error detail string")
                except Exception as extract_error:
                    logger.error(f"Could not extract slot_id from error detail: {extract_error}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            # Build error response with slot_id if we have it
            slot_id_attr = f' data-slot-id="{slot_id}"' if slot_id else ""
            # Mark that the pipeline failed so JavaScript doesn't re-check status
            failed_attr = ' data-pipeline-failed="true"'
            
            if slot_id:
                logger.info(f"Including slot_id {slot_id} in error response for logs access")
            else:
                logger.warning("No slot_id available for error response - logs will not be accessible")
            
            error_html = f'<div class="text-red-400"{slot_id_attr}{failed_attr}>Error allocating slot: {str(e)}</div>'
            logger.info(f"Returning error HTML: {error_html}")
            return HttpResponse(error_html)
        
        # Wait for Logstash to reload the pipeline (only if new slot)
        import time
        if not reused:
            time.sleep(2)
        
        # Use the slot-based pipeline name
        pipeline_name = f"slot{slot_id}-filter1"
        
        # If log_text is provided, send it through the pipeline
        if log_text:
            # Send the user's log input via LogstashAgent's simulate endpoint
            # This proxies the request to the local Logstash HTTP input on port 8082
            simulation_input_url = f"{settings.LOGSTASH_AGENT_URL}/_logstash/simulate"
            try:
                # Parse log_text as JSON if it looks like JSON, otherwise send as message field
                try:
                    log_data = json.loads(log_text)
                except json.JSONDecodeError:
                    # Not JSON, wrap it in a message field
                    log_data = {"message": log_text}
                
                # Add slot field for routing in simulate_start.conf
                log_data["slot"] = slot_id
                # Add run_id for tracking this specific simulation run
                log_data["run_id"] = run_id
                
                response = requests.post(
                    simulation_input_url,
                    json=log_data,
                    verify=False,
                    timeout=10
                )
                response.raise_for_status()
                logger.info(f"Sent simulation input to pipeline '{pipeline_name}'")
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to send simulation input: {e}")
                return HttpResponse(f'<div class="text-red-400">Error sending simulation input: {str(e)}</div>')
        
        # If no log_text was provided, this was just a slot allocation - return simple success message
        if not log_text:
            result_html = f'''
            <div class="p-4 bg-blue-900/30 border border-blue-600 rounded-lg" data-slot-id="{slot_id}">
                <h3 class="text-lg font-semibold text-blue-400 mb-2">✓ Slot Allocated</h3>
                <p class="text-blue-200">Slot {slot_id} {"(reused - same config)" if reused else "(new)"} with {len(filter_plugins)} instrumented filter(s)</p>
            </div>
            '''
            return HttpResponse(result_html)
        
        # Return success message - results will be streamed via StreamSimulate endpoint
        # Render the template with context
        template = get_template('components/pipeline_editor/simulation_results.html')
        context = {
            'filter_count': total_plugin_count,
            'slot_id': slot_id,
            'reused': reused,
            'run_id': run_id
        }
        result_html = template.render(context, request)
        
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
    Filters results by run_id to ensure each simulation only gets its own results.
    """
    if request.method != 'GET':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        # Get run_id from query parameters
        run_id = request.GET.get('run_id')
        
        if not run_id:
            return JsonResponse({"error": "Missing run_id parameter"}, status=400)
        
        # Filter results by run_id and remove them from the queue
        with simulation_lock:
            matching_results = []
            remaining_results = deque(maxlen=1000)
            
            for result in simulation_results:
                if result.get('run_id') == run_id:
                    matching_results.append(result)
                else:
                    remaining_results.append(result)
            
            # Replace the queue with non-matching results
            simulation_results.clear()
            simulation_results.extend(remaining_results)
        
        logger.info(f"GetSimulationResults: Returning {len(matching_results)} events for run_id {run_id}")
        if matching_results:
            logger.debug(f"GetSimulationResults: First event keys: {list(matching_results[0].keys())}")
        
        return JsonResponse({"results": matching_results}, status=200)
        
    except Exception as e:
        logger.error(f"Error in GetSimulationResults: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def CheckIfPipelineLoaded(request):
    """
    Check if a pipeline successfully loaded in the Logstash instance.
    Calls LogstashAgent's is_pipeline_running endpoint to verify pipeline status.
    
    Expected GET parameters:
        - pipeline_name: The name of the pipeline to check
    
    Returns:
        JSON response with:
        - is_running: Boolean indicating if pipeline is running
        - pipeline_name: The pipeline name that was checked
        - error: Error message if check failed
    """
    try:
        pipeline_name = request.GET.get('pipeline_name')
        
        if not pipeline_name:
            return JsonResponse({
                "error": "pipeline_name parameter is required"
            }, status=400)
        
        # Call LogstashAgent to check pipeline status
        logstash_agent_url = f"{settings.LOGSTASH_AGENT_URL}/_logstash/pipelines/status"
        
        try:
            response = requests.get(logstash_agent_url, timeout=5, verify=False)
            response.raise_for_status()
            
            data = response.json()
            running_pipelines = data.get('running_pipelines', [])
            is_running = pipeline_name in running_pipelines
            
            logger.info(f"CheckIfPipelineLoaded: Pipeline '{pipeline_name}' running status: {is_running}")
            
            return JsonResponse({
                "is_running": is_running,
                "pipeline_name": pipeline_name,
                "running_pipelines": running_pipelines
            }, status=200)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to LogstashAgent: {e}")
            return JsonResponse({
                "error": f"Failed to connect to LogstashAgent: {str(e)}",
                "is_running": False,
                "pipeline_name": pipeline_name
            }, status=500)
        
    except Exception as e:
        logger.error(f"Error in CheckIfPipelineLoaded: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            "error": str(e),
            "is_running": False
        }, status=500)


@login_required
def GetRelatedLogs(request):
    """
    Get log entries related to a specific slot pipeline.
    Calls LogstashAgent's pipeline logs endpoint to fetch related logs.
    
    Expected GET parameters:
        - slot_id: The slot ID to get logs for
        - max_entries: Maximum number of log entries to return (default: 100, max: 500)
        - min_level: Minimum log level (default: INFO, options: DEBUG, INFO, WARN, ERROR)
    
    Returns:
        JSON response with:
        - pipeline_id: The pipeline ID searched
        - log_count: Number of log entries found
        - logs: List of log entries
        - error: Error message if fetch failed
    """
    try:
        slot_id = request.GET.get('slot_id')
        max_entries = int(request.GET.get('max_entries', 100))
        min_level = request.GET.get('min_level', 'INFO').upper()
        
        if not slot_id:
            return JsonResponse({
                "error": "slot_id parameter is required"
            }, status=400)
        
        # Construct the slot pipeline name
        pipeline_id = f"slot{slot_id}-filter1"
        
        # Get slot creation timestamp from LogstashAgent
        min_timestamp = None
        try:
            slots_response = requests.get(f"{settings.LOGSTASH_AGENT_URL}/_logstash/slots", timeout=5, verify=False)
            slots_response.raise_for_status()
            slots_data = slots_response.json()
            
            # Find the slot and get its creation timestamp
            slot_info = slots_data.get(str(slot_id))
            if slot_info:
                # Subtract 5 seconds to avoid race condition where logs are requested
                # before pipelines have written any logs
                min_timestamp = slot_info.get('created_at_millis')
                if min_timestamp:
                    min_timestamp = min_timestamp - 5000  # 5 seconds buffer
                logger.info(f"Retrieved slot {slot_id} creation timestamp: {min_timestamp}")
        except Exception as e:
            logger.warning(f"Could not retrieve slot creation timestamp: {e}")
        
        # Call LogstashAgent to get pipeline logs
        logstash_agent_url = f"{settings.LOGSTASH_AGENT_URL}/_logstash/pipeline/{pipeline_id}/logs"
        params = {
            "max_entries": min(max_entries, 500),
            "min_level": min_level
        }
        
        # Add min_timestamp if available
        if min_timestamp:
            params["min_timestamp"] = min_timestamp
        
        try:
            response = requests.get(logstash_agent_url, params=params, timeout=10, verify=False)
            response.raise_for_status()
            
            data = response.json()
            
            logger.info(f"GetRelatedLogs: Retrieved {data.get('log_count', 0)} logs for slot {slot_id}")
            
            return JsonResponse(data, status=200)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch logs from LogstashAgent: {e}")
            return JsonResponse({
                "error": f"Failed to fetch logs from LogstashAgent: {str(e)}",
                "pipeline_id": pipeline_id,
                "log_count": 0,
                "logs": []
            }, status=500)
        
    except Exception as e:
        logger.error(f"Error in GetRelatedLogs: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            "error": str(e),
            "log_count": 0,
            "logs": []
        }, status=500)
