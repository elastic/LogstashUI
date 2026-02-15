
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
        
        # If no filter plugins and no log text, this is just a preallocation request
        if not filter_plugins and not log_text:
            return HttpResponse('<div class="text-gray-400">No filters to simulate - slot ready for when you add filters</div>')
        
        if not filter_plugins:
            return HttpResponse('<div class="text-yellow-400">Warning: No filter plugins found in pipeline</div>')
        
        # Flatten filter plugins to expand conditionals into individual trackable steps
        flattened_filters = flatten_filter_plugins(filter_plugins)
        
        # Determine protocol based on DEBUG mode
        protocol = "http" if settings.DEBUG else "https"
        logstash_agent_url = f"{protocol}://127.0.0.1:9500"
        
        # Build pipeline list for slot allocation
        pipeline_list = []
        for idx, filter_item in enumerate(flattened_filters, start=1):
            filter_plugin = filter_item['plugin']
            condition = filter_item['condition']
            branch_info = filter_item['branch_info']
            
            # Build instrumented filter list with ruby component after each filter
            instrumented_filters = [
                # The actual filter plugin
                filter_plugin,
                # Post-instrumentation ruby filter to add step metadata for result ordering and mapping
                {
                    "id": f"comp_post_{idx}",
                    "type": "filter",
                    "plugin": "ruby",
                    "config": {
                        "code": f"event.set('[simulation_step]', {idx}); event.set('[step_id]', '{filter_plugin['id']}')"
                    }
                }
            ]
            
            # Build output components - HTTP output for streaming results
            output_components = [
                {
                    "id": f"comp_output_{idx}",
                    "type": "output",
                    "plugin": "http",
                    "config": {
                        "content_type": "application/json",
                        "format": "json",
                        "http_method": "post",
                        "url": "http://host.docker.internal:8080/API/StreamSimulate/"
                    }
                }
            ]
            
            # Convert the instrumented filter list to Logstash config format
            filter_converter = logstash_config_parse.ComponentToPipeline({'filter': instrumented_filters}, test=False)
            filter_config = filter_converter.components_to_logstash_config()
            
            # Convert the output components to Logstash config format
            output_converter = logstash_config_parse.ComponentToPipeline({'output': output_components}, test=False)
            output_config = output_converter.components_to_logstash_config()
            
            # Extract just the filter block content (remove 'filter {' and closing '}')
            filter_lines = filter_config.strip().split('\n')
            filter_content = '\n'.join(filter_lines[1:-1])  # Skip first and last lines
            
            # Extract just the output block content (remove 'output {' and closing '}')
            output_lines = output_config.strip().split('\n')
            output_content = '\n'.join(output_lines[1:-1])  # Skip first and last lines
            
            # Wrap filter content with condition if present
            # Important: We only wrap the filter, not the output
            # The output should always fire to pass the event to the next pipeline
            if condition:
                # Indent the filter content
                indented_filter = '\n'.join(['\t' + line if line.strip() else line for line in filter_content.split('\n')])
                filter_content = f"if {condition} {{\n{indented_filter}\n}}"
                
                # Also wrap the HTTP output with the same condition
                # This ensures we only send results when the filter actually executed
                indented_output = '\n'.join(['\t' + line if line.strip() else line for line in output_content.split('\n')])
                output_content = f"if {condition} {{\n{indented_output}\n}}"
            
            pipeline_list.append({
                "filter_config": filter_content,
                "output_config": output_content,
                "index": idx
            })
        
        # Allocate a slot for these pipelines
        slot_allocation_body = {
            "pipeline_name": request.GET.get('pipeline', 'unknown'),
            "pipelines": pipeline_list
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
            slot_id = slot_data['slot_id']
            reused = slot_data['reused']
            logger.info(f"Allocated slot {slot_id} (reused: {reused})")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to allocate slot: {e}")
            return HttpResponse(f'<div class="text-red-400">Error allocating slot: {str(e)}</div>')
        
        # Wait a moment for Logstash to reload the pipelines (only if new slot)
        import time
        if not reused:
            time.sleep(4)
        
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
                
                # Add slot field to route to the correct slot
                log_data["slot"] = slot_id
                
                response = requests.post(
                    simulation_input_url,
                    json=log_data,
                    verify=False,
                    timeout=10
                )
                response.raise_for_status()
                logger.info(f"Sent simulation input to {simulation_input_url} with slot {slot_id}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to send simulation input: {e}")
                return HttpResponse(f'<div class="text-red-400">Error sending simulation input: {str(e)}</div>')
        
        # Note: Pipelines are now persistent in slots and will be reused
        # No cleanup needed - slots will be evicted when needed
        
        # Build pipeline chain display
        slot_pipelines = [f"slot{slot_id}-filter{i}" for i in range(1, len(flattened_filters) + 1)]
        
        # If no log_text was provided, this was just a preallocation - return simple success message
        if not log_text:
            result_html = f'''
            <div class="p-4 bg-blue-900/30 border border-blue-600 rounded-lg">
                <h3 class="text-lg font-semibold text-blue-400 mb-2">✓ Slot Allocated</h3>
                <p class="text-blue-200">Slot {slot_id} {"(reused)" if reused else "(created)"} with {len(flattened_filters)} step(s) ready for simulation ({len(filter_plugins)} original filter(s))</p>
            </div>
            '''
            return HttpResponse(result_html)
        
        # Return success message - results will be streamed via StreamSimulate endpoint
        result_html = f'''
        <div class="space-y-4">
            <div class="p-4 bg-green-900/30 border border-green-600 rounded-lg">
                <h3 class="text-lg font-semibold text-green-400 mb-2">✓ Simulation Started</h3>
                <p class="text-green-200">Processing {len(flattened_filters)} step(s) in slot {slot_id} {"(reused)" if reused else "(new)"} - results streaming below</p>
            </div>
            
            <div class="p-4 bg-gray-700 rounded-lg">
                <h4 class="text-sm font-semibold text-gray-300 mb-2">Pipeline Chain:</h4>
                <pre class="text-xs text-gray-300 overflow-auto bg-gray-800 p-3 rounded">simulate-start → slot{slot_id} → {' → '.join(slot_pipelines)} → filter-final → output-block → StreamSimulate</pre>
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
            const pollInterval = 250; // Poll every 250ms for faster updates
            
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
            
            // Start polling immediately
            setTimeout(pollResults, 100);
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
