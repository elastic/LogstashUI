from django.shortcuts import HttpResponse
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.template.loader import get_template
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from Common import logstash_config_parse

from Common.decorators import require_admin_role

from collections import deque
from threading import Lock

import json
import traceback
import logging
import requests
import uuid
import base64
import time
import re

logger = logging.getLogger(__name__)

# Global storage for simulation results (in-memory for now)
simulation_results = deque(maxlen=1000)
simulation_lock = Lock()


@require_admin_role
def SimulatePipeline(request):
    """
    Simulate a pipeline by building a single pipeline with Ruby instrumentation
    injected after each filter plugin to capture step-by-step event state.
    """

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

        # Generate run_id for this simulation
        # For slot preallocation (empty log_text), use a deterministic ID to ensure consistent hashing
        # For actual simulations, generate a unique UUID to track results
        if not log_text:
            run_id = "preallocation"
            logger.info(f"Slot preallocation request (using deterministic run_id)")
        else:
            run_id = str(uuid.uuid4())
            logger.info(f"Starting simulation with run_id: {run_id}")

        # Get LogstashAgent URL early so we can use it in instrumentation
        logstash_agent_url = settings.LOGSTASH_AGENT_URL

        # Determine LOGSTASH_URL for Ruby code based on DEBUG mode
        # DEBUG=True: http://host.docker.internal:8080
        # DEBUG=False: https://host.docker.internal
        if settings.DEBUG:
            logstash_ui_url = "http://host.docker.internal:8080"
        else:
            logstash_ui_url = "https://host.docker.internal"

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
                        if_condition = conditional_plugin['config'].get('condition', '')
                        # Escape only double quotes for embedding in Ruby string (not backslashes - that causes double-escaping)
                        escaped_condition = if_condition.replace('"', '\\"')
                        branch_tracker = {
                            "id": f"{conditional_id}_if_tracker",
                            "type": "filter",
                            "plugin": "ruby",
                            "config": {
                                "code": (
                                    f"event.set(\"[simulation][conditional_branches][{conditional_id}]\", \"if\")\n"
                                    f"event.set(\"[simulation][conditional_conditions][{conditional_id}]\", \"{escaped_condition}\")"
                                )
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
                                else_if_condition = else_if.get('condition', '')
                                # Escape only double quotes for embedding in Ruby string (not backslashes - that causes double-escaping)
                                escaped_else_if_condition = else_if_condition.replace('"', '\\"')
                                branch_tracker = {
                                    "id": f"{conditional_id}_elseif{else_if_idx}_tracker",
                                    "type": "filter",
                                    "plugin": "ruby",
                                    "config": {
                                        "code": (
                                            f"event.set(\"[simulation][conditional_branches][{conditional_id}]\", \"else_if_{else_if_idx}\")\n"
                                            f"event.set(\"[simulation][conditional_conditions][{conditional_id}]\", \"{escaped_else_if_condition}\")"
                                        )
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
                                    "code": f"event.set(\"[simulation][conditional_branches][{conditional_id}]\", \"else\")"
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

                    # Check if this is a drop plugin - if so, add Ruby code to send event to API before drop
                    if plugin.get('plugin') == 'drop':
                        # Drop plugins are special - they need to send the event to the API before dropping
                        # We don't use the normal timing instrumentation for drop plugins
                        # Instead, we create a snapshot and send it directly via HTTP POST
                        drop_plugin_id = plugin['id']
                        pre_drop_code = f"""
require "net/http"
require "uri"
require "json"

# Create a snapshot for the drop plugin
event.set("[simulation][step]", {current_step})
event.set("[simulation][id]", "{drop_plugin_id}")

# Create snapshot of current event state for the drop plugin
snapshot = {{}}
event.to_hash.each do |key, value|
  # Skip metadata and snapshots field itself to avoid recursion
  next if key.start_with?("@metadata") || key == "snapshots"
  snapshot[key] = value
end
event.set("[snapshots][{drop_plugin_id}]", snapshot)

# Ensure run_id is set (should already be in the event from input)
if !event.get("run_id")
  event.set("run_id", "{run_id}")
end

# Convert event to hash and send to API
event_hash = event.to_hash

# Send HTTP POST to StreamSimulate endpoint
uri = URI.parse("{logstash_ui_url}/ConnectionManager/StreamSimulate/")
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = (uri.scheme == "https")
http.verify_mode = OpenSSL::SSL::VERIFY_NONE if http.use_ssl?

request = Net::HTTP::Post.new(uri.path, {{"Content-Type" => "application/json"}})
request.body = event_hash.to_json

begin
  response = http.request(request)
rescue => e
  # Log error but don't fail the pipeline
end
""".strip()

                        pre_drop_plugin = {
                            "id": f"pre_drop_api_call_{plugin['id']}",
                            "type": "filter",
                            "plugin": "ruby",
                            "config": {
                                "code": pre_drop_code
                            }
                        }
                        instrumented.append(pre_drop_plugin)

                        # Add the actual drop plugin
                        instrumented.append(plugin)

                        # Skip the normal timing instrumentation for drop plugins
                        # The event is already sent to the API, and the drop will prevent any further processing
                    else:
                        # Regular plugin - add normal timing instrumentation
                        # Add pre-plugin timing instrumentation
                        pre_instrumentation_code = (
                            f"# Capture start time in nanoseconds before plugin execution\n"
                            f"event.set(\"[simulation][timing][start_ns]\", (Time.now.to_f * 1_000_000_000).to_i)"
                        )

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
                        instrumentation_code = (
                            f"event.set(\"[simulation][step]\", {current_step})\n"
                            f"event.set(\"[simulation][id]\", \"{plugin['id']}\")\n"
                            f"end_ns = (Time.now.to_f * 1_000_000_000).to_i\n"
                            f"start_ns = event.get(\"[simulation][timing][start_ns]\")\n"
                            f"if start_ns\n"
                            f"  execution_ns = end_ns - start_ns\n"
                            f"  event.set(\"[simulation][timing][execution_ns]\", execution_ns)\n"
                            f"  event.set(\"[simulation][timing][end_ns]\", end_ns)\n"
                            f"end\n"
                            f"\n"
                            f"snapshot = {{}}\n"
                            f"event.to_hash.each do |key, value|\n"
                            f"  next if key.start_with?(\"@metadata\") || key == \"snapshots\"\n"
                            f"  snapshot[key] = value\n"
                            f"end\n"
                            f"\n"
                            f"# Store snapshot under the plugin ID\n"
                            f"event.set(\"[snapshots][{plugin['id']}]\", snapshot)"
                        )

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
        # Add HTTP output that only sends cloned events (identified by type field)
        output_plugins = [
            {
                "id": "http_output",
                "type": "output",
                "plugin": "http",
                "config": {
                    "url": f"{logstash_agent_url}/ConnectionManager/StreamSimulate/",
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
                    logger.debug(f"Error response status: {e.response.status_code}")
                    logger.debug(f"Error response content: {e.response.text[:500]}")

                    error_data = e.response.json()
                    logger.debug(f"Error response JSON: {error_data}")

                    # Check if detail is a dict with slot_id (new format)
                    detail = error_data.get('detail')
                    logger.debug(f"Error detail type: {type(detail)}, value: {detail}")

                    if isinstance(detail, dict):
                        slot_id = detail.get('slot_id')
                        logger.debug(f"Extracted slot_id {slot_id} from error response detail dict")
                    elif isinstance(detail, str) and 'Slot' in detail:
                        # Fallback: try to extract from string
                        match = re.search(r'Slot (\d+)', detail)
                        if match:
                            slot_id = int(match.group(1))
                            logger.debug(f"Extracted slot_id {slot_id} from error detail string")
                except Exception as extract_error:
                    logger.error(f"Could not extract slot_id from error detail: {extract_error}")
                    logger.error(traceback.format_exc())

            # Build error response with slot_id if we have it
            slot_id_attr = f' data-slot-id="{slot_id}"' if slot_id else ""
            # Mark that the pipeline failed so JavaScript doesn't re-check status
            failed_attr = ' data-pipeline-failed="true"'

            if slot_id:
                logger.debug(f"Including slot_id {slot_id} in error response for logs access")
            else:
                logger.warning("No slot_id available for error response - logs will not be accessible")

            error_html = f'<div class="text-red-400"{slot_id_attr}{failed_attr}>Error allocating slot: {str(e)}</div>'
            logger.debug(f"Returning error HTML: {error_html}")
            return HttpResponse(error_html)

        # Use the slot-based pipeline name
        pipeline_name = f"slot{slot_id}-filter1"

        # If log_text is provided, send it through the pipeline
        if log_text:
            # Send the user's log input via LogstashAgent's simulate endpoint
            # This proxies the request to the local Logstash HTTP input on port 9449
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

            logger.debug(
                f"Slots data type: {type(slots_data)}, Keys: {list(slots_data.keys()) if isinstance(slots_data, dict) else 'N/A'}")
            logger.debug(f"Looking for slot_id: {slot_id} (type: {type(slot_id)})")

            # Find the slot and get its creation timestamp
            # JSON converts int keys to strings, so try both
            slot_info = slots_data.get(str(slot_id)) or slots_data.get(int(slot_id))
            logger.debug(f"Slot info found: {slot_info is not None}")
            if slot_info:
                # Use slot creation time as minimum timestamp to avoid showing logs
                # from previous pipelines that used this slot
                min_timestamp = slot_info.get('created_at_millis')
                current_time_millis = int(time.time() * 1000)
                time_diff_seconds = (current_time_millis - min_timestamp) / 1000 if min_timestamp else 0
                logger.debug(
                    f"Slot {slot_id} - Current time: {current_time_millis}, Min timestamp: {min_timestamp}, Diff: {time_diff_seconds:.1f}s ago")
            else:
                # Slot not found - use recent time window as fallback (last 30 seconds)
                current_time_millis = int(time.time() * 1000)
                min_timestamp = current_time_millis - 30000  # 30 seconds ago
                logger.warning(f"Slot {slot_id} not found in slots data. Available slots: {list(slots_data.keys())}")
                logger.warning(f"Using fallback: filtering logs from last 30 seconds (min_timestamp: {min_timestamp})")
        except Exception as e:
            # If anything fails, use fallback time window
            current_time_millis = int(time.time() * 1000)
            min_timestamp = current_time_millis - 30000  # 30 seconds ago
            logger.warning(f"Could not retrieve slot creation timestamp: {e}")
            logger.warning(f"Using fallback: filtering logs from last 30 seconds (min_timestamp: {min_timestamp})")

        # Call LogstashAgent to get pipeline logs
        logstash_agent_url = f"{settings.LOGSTASH_AGENT_URL}/_logstash/pipeline/{pipeline_id}/logs"
        params = {
            "max_entries": min(max_entries, 500),
            "min_level": min_level
        }

        # Add min_timestamp if available
        if min_timestamp:
            params["min_timestamp"] = min_timestamp
            logger.debug(f"Fetching logs with min_timestamp filter: {min_timestamp}")
        else:
            logger.warning(f"No min_timestamp available - will fetch ALL logs for {pipeline_id}")

        try:
            logger.debug(f"Requesting logs from {logstash_agent_url} with params: {params}")
            response = requests.get(logstash_agent_url, params=params, timeout=10, verify=False)
            response.raise_for_status()

            data = response.json()

            log_count = data.get('log_count', 0)
            logger.info(f"GetRelatedLogs: Retrieved {log_count} logs for slot {slot_id}")

            # Log timestamp range of returned logs for debugging
            if log_count > 0 and 'logs' in data:
                logs = data['logs']
                timestamps = [log.get('timeMillis', 0) for log in logs if 'timeMillis' in log]
                if timestamps:
                    oldest = min(timestamps)
                    newest = max(timestamps)
                    logger.info(
                        f"Log timestamp range - Oldest: {oldest}, Newest: {newest}, Min filter was: {min_timestamp}")
                    if min_timestamp and oldest < min_timestamp:
                        logger.error(
                            f"FILTERING FAILED: Found log older ({oldest}) than min_timestamp ({min_timestamp})")

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


@require_admin_role
def UploadFile(request):
    """
    Upload a file for use in simulation.
    Receives file binary data and transmits it to LogstashAgent for storage.
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        # Get the uploaded file and filename
        uploaded_file = request.FILES.get('file')
        filename = request.POST.get('filename')

        if not uploaded_file:
            return JsonResponse({"error": "No file provided"}, status=400)

        if not filename:
            return JsonResponse({"error": "No filename provided"}, status=400)

        # Read file content
        file_content = uploaded_file.read()
        logger.info(f"Read {len(file_content)} bytes from uploaded file")

        # Encode as base64 for transmission
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        logger.info(f"Encoded content length: {len(encoded_content)} characters")

        # Send to LogstashAgent
        logstash_agent_url = f"{settings.LOGSTASH_AGENT_URL}/_logstash/write-file"

        response = requests.post(
            logstash_agent_url,
            json={
                "filename": filename,
                "content": encoded_content
            },
            verify=False,
            timeout=10
        )

        response.raise_for_status()

        logger.info(f"File uploaded successfully: {filename}")

        return JsonResponse({
            "status": "ok",
            "message": "File uploaded successfully",
            "filename": filename
        }, status=200)

    except requests.exceptions.RequestException as e:
        logger.error(f"Error transmitting file to LogstashAgent: {e}")
        return JsonResponse({
            "error": f"Failed to upload file to LogstashAgent: {str(e)}"
        }, status=500)
    except Exception as e:
        logger.error(f"Error in UploadFile: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)