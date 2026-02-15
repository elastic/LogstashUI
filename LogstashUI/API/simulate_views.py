
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


def flatten_filter_plugins(filter_plugins):
    """
    Flatten filter plugins, expanding conditionals into individual trackable steps.
    Uses branch markers to handle field mutations and else blocks cleanly.
    
    Each conditional gets:
    - A unique branch marker field (__branch_cond_N) for execution control
    - User-visible metadata fields (conditional_N_*) for tracking which branch was taken
    - Individual steps for each plugin inside the conditional
    
    Args:
        filter_plugins: List of filter plugin dictionaries
        
    Returns:
        List of dicts with:
        - 'plugin': the plugin config
        - 'condition': the condition under which it should execute (or None)
        - 'branch_info': metadata about which branch this came from
    """
    flattened = []
    conditional_counter = 0
    
    def convert_logstash_fields_to_ruby(condition):
        """
        Convert Logstash field references to Ruby event.get() calls.
        Examples:
          [network.transport] -> event.get("[network.transport]")
          [type] -> event.get("[type]")
          [event.code] -> event.get("[event.code]")
        """
        import re
        # Match field references: [fieldname] or [field.subfield]
        # Pattern: \[([a-zA-Z0-9_.@-]+)\]
        pattern = r'\[([a-zA-Z0-9_.@-]+)\]'
        
        def replace_field(match):
            field_name = match.group(1)
            return f'event.get("[{field_name}]")'
        
        return re.sub(pattern, replace_field, condition)
    
    def normalize_condition_quotes(condition):
        """
        Convert single quotes to double quotes in conditions so the Ruby code
        only contains double quotes, allowing ComponentToPipeline to wrap in single quotes.
        This handles array syntax like: in ['a', 'b'] -> in ["a", "b"]
        """
        return condition.replace("'", '"')
    
    def escape_for_ruby_double_quoted_string(text):
        """
        Escape text for storing inside Ruby double-quoted strings.
        Since we're using double quotes in our Ruby code, we need to escape
        double quotes and backslashes for the metadata storage.
        """
        # Escape backslashes first, then double quotes, then newlines
        return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    
    for plugin in filter_plugins:
        if plugin['plugin'] == 'if':
            conditional_counter += 1
            branch_marker = f"__branch_cond_{conditional_counter}"
            original_plugin_id = plugin['id']
            
            if_condition = plugin['config']['condition']
            if_plugins = plugin['config']['plugins']
            else_ifs = plugin['config'].get('else_ifs', [])
            else_block = plugin['config'].get('else')
            
            # Convert Logstash field references to Ruby, normalize quotes, and escape for storage
            ruby_condition = convert_logstash_fields_to_ruby(if_condition)
            ruby_condition = normalize_condition_quotes(ruby_condition)
            escaped_if_condition = escape_for_ruby_double_quoted_string(normalize_condition_quotes(if_condition))
            
            # Step 1: Set branch marker for if - this determines which branch to take
            # Use double quotes consistently so ComponentToPipeline wraps in single quotes
            ruby_code = f"""
if !event.get("[{branch_marker}]") && ({ruby_condition})
  event.set("[{branch_marker}]", "if")
  event.set("[conditional_{conditional_counter}_branch]", "if")
  event.set("[conditional_{conditional_counter}_id]", "{original_plugin_id}")
  event.set("[conditional_{conditional_counter}_condition]", "{escaped_if_condition}")
end
""".strip()
            
            flattened.append({
                'plugin': {
                    'id': f"{original_plugin_id}_set_if",
                    'type': 'filter',
                    'plugin': 'ruby',
                    'config': {
                        'code': ruby_code
                    }
                },
                'condition': None,  # Always execute to check
                'branch_info': {
                    'type': 'branch_decision',
                    'conditional_id': conditional_counter,
                    'original_plugin_id': original_plugin_id,
                    'branch': 'if'
                }
            })
            
            # Step 2: Add plugins from if block, conditioned on branch marker
            for if_plugin in if_plugins:
                # Recursively flatten if there are nested conditionals
                if if_plugin['plugin'] == 'if':
                    nested_flattened = flatten_filter_plugins([if_plugin])
                    for nested_item in nested_flattened:
                        # Wrap nested conditions with parent condition
                        if nested_item['condition']:
                            nested_item['condition'] = f"[{branch_marker}] == 'if' and ({nested_item['condition']})"
                        else:
                            nested_item['condition'] = f"[{branch_marker}] == 'if'"
                        flattened.append(nested_item)
                else:
                    flattened.append({
                        'plugin': if_plugin,
                        'condition': f"[{branch_marker}] == 'if'",
                        'branch_info': {
                            'type': 'if',
                            'condition': if_condition,
                            'conditional_id': conditional_counter,
                            'original_plugin_id': original_plugin_id
                        }
                    })
            
            # Step 3: Set branch markers for else if blocks
            for idx, else_if in enumerate(else_ifs):
                elif_condition = else_if['condition']
                elif_label = f"elif_{idx}"
                ruby_elif_condition = convert_logstash_fields_to_ruby(elif_condition)
                ruby_elif_condition = normalize_condition_quotes(ruby_elif_condition)
                escaped_elif_condition = escape_for_ruby_double_quoted_string(normalize_condition_quotes(elif_condition))
                
                ruby_code = f"""
if !event.get("[{branch_marker}]") && ({ruby_elif_condition})
  event.set("[{branch_marker}]", "{elif_label}")
  event.set("[conditional_{conditional_counter}_branch]", "else_if")
  event.set("[conditional_{conditional_counter}_id]", "{original_plugin_id}")
  event.set("[conditional_{conditional_counter}_condition]", "{escaped_elif_condition}")
end
""".strip()
                
                flattened.append({
                    'plugin': {
                        'id': f"{original_plugin_id}_set_elif_{idx}",
                        'type': 'filter',
                        'plugin': 'ruby',
                        'config': {
                            'code': ruby_code
                        }
                    },
                    'condition': None,
                    'branch_info': {
                        'type': 'branch_decision',
                        'conditional_id': conditional_counter,
                        'original_plugin_id': original_plugin_id,
                        'branch': f'else_if_{idx}'
                    }
                })
                
                # Add plugins from else if block
                for elif_plugin in else_if['plugins']:
                    if elif_plugin['plugin'] == 'if':
                        nested_flattened = flatten_filter_plugins([elif_plugin])
                        for nested_item in nested_flattened:
                            if nested_item['condition']:
                                nested_item['condition'] = f"[{branch_marker}] == '{elif_label}' and ({nested_item['condition']})"
                            else:
                                nested_item['condition'] = f"[{branch_marker}] == '{elif_label}'"
                            flattened.append(nested_item)
                    else:
                        flattened.append({
                            'plugin': elif_plugin,
                            'condition': f"[{branch_marker}] == '{elif_label}'",
                            'branch_info': {
                                'type': 'else_if',
                                'condition': elif_condition,
                                'conditional_id': conditional_counter,
                                'original_plugin_id': original_plugin_id
                            }
                        })
            
            # Step 4: Set branch marker for else block
            if else_block and else_block.get('plugins'):
                ruby_code = f"""
if !event.get("[{branch_marker}]")
  event.set("[{branch_marker}]", "else")
  event.set("[conditional_{conditional_counter}_branch]", "else")
  event.set("[conditional_{conditional_counter}_id]", "{original_plugin_id}")
  event.set("[conditional_{conditional_counter}_condition]", "else")
end
""".strip()
                
                flattened.append({
                    'plugin': {
                        'id': f"{original_plugin_id}_set_else",
                        'type': 'filter',
                        'plugin': 'ruby',
                        'config': {
                            'code': ruby_code
                        }
                    },
                    'condition': None,
                    'branch_info': {
                        'type': 'branch_decision',
                        'conditional_id': conditional_counter,
                        'original_plugin_id': original_plugin_id,
                        'branch': 'else'
                    }
                })
                
                # Add plugins from else block
                for else_plugin in else_block['plugins']:
                    if else_plugin['plugin'] == 'if':
                        nested_flattened = flatten_filter_plugins([else_plugin])
                        for nested_item in nested_flattened:
                            if nested_item['condition']:
                                nested_item['condition'] = f"[{branch_marker}] == 'else' and ({nested_item['condition']})"
                            else:
                                nested_item['condition'] = f"[{branch_marker}] == 'else'"
                            flattened.append(nested_item)
                    else:
                        flattened.append({
                            'plugin': else_plugin,
                            'condition': f"[{branch_marker}] == 'else'",
                            'branch_info': {
                                'type': 'else',
                                'conditional_id': conditional_counter,
                                'original_plugin_id': original_plugin_id
                            }
                        })
        else:
            # Regular plugin (not conditional)
            flattened.append({
                'plugin': plugin,
                'condition': None,
                'branch_info': None
            })
    
    return flattened


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
        
        # Build a single instrumented filter list with Ruby metadata after each filter
        instrumented_filters = []
        
        for idx, filter_plugin in enumerate(filter_plugins, start=1):
            # Add the actual filter plugin
            instrumented_filters.append(filter_plugin)
            
            # Add Ruby instrumentation after the filter to capture event snapshot
            # Save the entire event state in snapshots[plugin_id]
            instrumentation_code = f"""
# Update step tracking
event.set('[simulation_step]', {idx})
event.set('[step_id]', '{filter_plugin['id']}')

# Create snapshot of current event state
snapshot = {{}}
event.to_hash.each do |key, value|
  # Skip metadata and snapshots field itself to avoid recursion
  next if key.start_with?('@metadata') || key == 'snapshots'
  snapshot[key] = value
end

# Store snapshot under the plugin ID
event.set('[snapshots][{filter_plugin['id']}]', snapshot)
""".strip()
            
            instrumentation_plugin = {
                "id": f"instrumentation_{idx}",
                "type": "filter",
                "plugin": "ruby",
                "config": {
                    "code": instrumentation_code
                }
            }
            
            instrumented_filters.append(instrumentation_plugin)
        
        # Add HTTP output that only sends cloned events (identified by type field)
        output_plugins = [
            {
                "id": "http_output",
                "type": "output",
                "plugin": "http",
                "config": {
                    "url": "http://host.docker.internal:8080/API/StreamSimulate/",
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
        
        # Determine protocol based on DEBUG mode
        protocol = "http" if settings.DEBUG else "https"
        logstash_agent_url = f"{protocol}://127.0.0.1:9500"
        
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
        
        try:
            response = requests.post(
                f"{logstash_agent_url}/_logstash/slots/allocate",
                json=slot_allocation_body,
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            slot_data = response.json()
            slot_id = slot_data.get('slot_id')
            reused = slot_data.get('reused', False)
            logger.info(f"Allocated slot {slot_id} (reused: {reused})")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to allocate slot: {e}")
            return HttpResponse(f'<div class="text-red-400">Error allocating slot: {str(e)}</div>')
        
        # Wait for Logstash to reload the pipeline (only if new slot)
        import time
        if not reused:
            time.sleep(2)
        
        # Use the slot-based pipeline name
        pipeline_name = f"slot{slot_id}-filter1"
        
        # If log_text is provided, send it through the pipeline
        if log_text:
            # Send the user's log input to the simulation HTTP input
            simulation_input_url = f"{protocol}://127.0.0.1:8082"
            try:
                # Parse log_text as JSON if it looks like JSON, otherwise send as message field
                try:
                    log_data = json.loads(log_text)
                except json.JSONDecodeError:
                    # Not JSON, wrap it in a message field
                    log_data = {"message": log_text}
                
                # Add slot field for routing in simulate_start.conf
                log_data["slot"] = slot_id
                
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
            <div class="p-4 bg-blue-900/30 border border-blue-600 rounded-lg">
                <h3 class="text-lg font-semibold text-blue-400 mb-2">✓ Slot Allocated</h3>
                <p class="text-blue-200">Slot {slot_id} {"(reused - same config)" if reused else "(new)"} with {len(filter_plugins)} instrumented filter(s)</p>
            </div>
            '''
            return HttpResponse(result_html)
        
        # Return success message - results will be streamed via StreamSimulate endpoint
        # Render the template with context
        template = get_template('components/pipeline_editor/simulation_results.html')
        context = {
            'filter_count': len(filter_plugins),
            'slot_id': slot_id,
            'reused': reused
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
