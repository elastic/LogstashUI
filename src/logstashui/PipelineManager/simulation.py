#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import HttpResponse
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.template.loader import get_template
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from Common import logstash_config_parse

from Common.decorators import require_admin_role
from PipelineManager.agent_modes import list_simulation_targets, resolve_simulation_target
from datetime import datetime, timezone as dt_timezone
from PipelineManager.models import Connection as ConnectionTable

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
from Common.product_ca import agent_requests_verify

logger = logging.getLogger(__name__)

# Global storage for simulation results (in-memory for now)
simulation_results = deque(maxlen=1000)
simulation_lock = Lock()


def _sim_agent_url(request):
    """
    Resolve LogstashAgent base URL for simulation traffic.

    Prefer explicit connection_id (POST/GET); else sticky session / single target;
    fall back to settings.LOGSTASH_AGENT_URL when no enrolled sim agents exist
    (legacy embedded static URL).
    """
    connection_id = (
        request.POST.get("sim_connection_id")
        or request.GET.get("sim_connection_id")
        or request.POST.get("connection_id")
    )
    # Avoid colliding with other connection_id uses if body is JSON later
    if connection_id in (None, "", "null", "undefined"):
        connection_id = None

    target, err = resolve_simulation_target(connection_id, session=request.session)
    if target and target.get("base_url"):
        request.session["sim_connection_id"] = target["connection_id"]
        try:
            ConnectionTable.objects.filter(pk=target["connection_id"]).update(
                last_selected_at=datetime.now(dt_timezone.utc)
            )
        except Exception:
            pass
        return target["base_url"], target, None

    # Fallback: historical static setting (embedded docker / host.docker.internal)
    fallback = getattr(settings, "LOGSTASH_AGENT_URL", None)
    if fallback:
        return fallback, None, None
    return None, None, err or "No simulation agent URL available"


@require_admin_role
def GetSimulationTargets(request):
    """List simulate-capable agents for the pipeline editor dropdown."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    targets = list_simulation_targets(ensure_embedded=True)
    selected = request.session.get("sim_connection_id")
    # Sticky selection may be stale; clear if not in list
    if selected is not None and not any(t["connection_id"] == selected for t in targets):
        selected = None
        try:
            del request.session["sim_connection_id"]
        except KeyError:
            pass
    if selected is None and len(targets) == 1:
        selected = targets[0]["connection_id"]
        request.session["sim_connection_id"] = selected
    return JsonResponse(
        {
            "success": True,
            "targets": targets,
            "selected_connection_id": selected,
            "count": len(targets),
        }
    )


@require_admin_role
def SelectSimulationTarget(request):
    """
    Persist the user's chosen simulation agent in the session (sticky selection).
    Body JSON: { "connection_id": <int> }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        data = {}
    connection_id = data.get("connection_id") or request.POST.get("connection_id")
    if connection_id in (None, "", "null"):
        return JsonResponse({"success": False, "error": "connection_id required"}, status=400)
    target, err = resolve_simulation_target(connection_id, session=None)
    if not target:
        return JsonResponse({"success": False, "error": err or "not found"}, status=404)
    request.session["sim_connection_id"] = target["connection_id"]
    try:
        ConnectionTable.objects.filter(pk=target["connection_id"]).update(
            last_selected_at=datetime.now(dt_timezone.utc)
        )
    except Exception:
        pass
    return JsonResponse(
        {
            "success": True,
            "selected_connection_id": target["connection_id"],
            "label": target.get("label"),
            "base_url": target.get("base_url"),
        }
    )


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
            logger.info(f"[FE->BE] Slot preallocation request - {len(filter_plugins)} filter plugins: {[p.get('plugin', 'unknown') for p in filter_plugins]}")
        else:
            run_id = str(uuid.uuid4())
            logger.info(f"[FE->BE] Starting simulation with run_id: {run_id} - {len(filter_plugins)} filter plugins: {[p.get('plugin', 'unknown') for p in filter_plugins]}")

        # Get logstashagent URL early so we can use it in instrumentation
        logstash_agent_url, sim_target, sim_err = _sim_agent_url(request)
        if not logstash_agent_url:
            return HttpResponse(
                f'<div class="text-red-400">Error: {sim_err or "No simulation agent available"}</div>'
            )

        # Clone source-policy keystore onto the simulate agent when ${...} vars appear
        try:
            from PipelineManager.sim_keystore import maybe_sync_keystore_for_simulation

            ls_id = request.POST.get('ls_id') or request.GET.get('ls_id')
            policy_id = request.POST.get('policy_id') or request.GET.get('policy_id')
            maybe_sync_keystore_for_simulation(
                agent_base_url=logstash_agent_url,
                components=components,
                pipeline_text=request.POST.get('pipeline_text', '') or '',
                ls_id=ls_id,
                policy_id=policy_id,
            )
        except Exception as ks_err:
            logger.error("Keystore sync before simulation failed: %s", ks_err, exc_info=True)
            # Fail closed when refs exist would be safer; allow sim to continue so
            # non-secret paths still work — surface error if components have refs
            from PipelineManager.sim_keystore import find_keystore_refs_in_obj
            if find_keystore_refs_in_obj(components):
                return HttpResponse(
                    f'<div class="text-red-400">Error: Failed to sync keystore to simulation agent: '
                    f'{ks_err}</div>'
                )

        # Callback URL for Ruby instrumentation posts (remote simulate agents need
        # a reachable LogstashUI URL; prefer agent-reported enroll URL later).
        simulation_mode = settings.LOGSTASHUI_CONFIG.get('simulation', {}).get('mode', 'embedded')
        if sim_target and sim_target.get('policy_type') == 'SIMULATE':
            # Enrolled simulate agent is typically not co-located in docker; use
            # public-ish UI base from request if available, else localhost.
            logstash_ui_url = request.build_absolute_uri('/').rstrip('/')
        elif simulation_mode == 'host':
            logstash_ui_url = "https://localhost:8443"
        else:
            if settings.DEBUG:
                logstash_ui_url = "https://host.docker.internal:8443"
            else:
                # Agent container reaches UI service on compose network
                logstash_ui_url = "https://logstashui:8443"

        logger.debug("USING THIS URL: %s", logstash_ui_url)
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
                        # Add branch tracking at the start of the if block using mutate filter
                        # This avoids injecting unique values into Ruby code, allowing JRuby code reuse
                        if_condition = conditional_plugin['config'].get('condition', '')
                        branch_tracker = {
                            "id": f"{conditional_id}_if_tracker",
                            "type": "filter",
                            "plugin": "mutate",
                            "config": {
                                "replace": {
                                    f"[simulation][conditional_branches][{conditional_id}]": "if",
                                    f"[simulation][conditional_conditions][{conditional_id}]": if_condition
                                }
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
                                # Add branch tracking at the start of the else_if block using mutate filter
                                # This avoids injecting unique values into Ruby code, allowing JRuby code reuse
                                else_if_condition = else_if.get('condition', '')
                                branch_tracker = {
                                    "id": f"{conditional_id}_elseif{else_if_idx}_tracker",
                                    "type": "filter",
                                    "plugin": "mutate",
                                    "config": {
                                        "replace": {
                                            f"[simulation][conditional_branches][{conditional_id}]": f"else_if_{else_if_idx}",
                                            f"[simulation][conditional_conditions][{conditional_id}]": else_if_condition
                                        }
                                    }
                                }
                                else_if_copy['plugins'] = [branch_tracker] + instrument_plugins(else_if_copy['plugins'])
                            instrumented_else_ifs.append(else_if_copy)
                        conditional_plugin['config']['else_ifs'] = instrumented_else_ifs

                    # Instrument plugins in 'else' block
                    if 'else' in conditional_plugin['config'] and conditional_plugin['config']['else']:
                        else_block = conditional_plugin['config']['else'].copy()
                        if 'plugins' in else_block:
                            # Add branch tracking at the start of the else block using mutate filter
                            # This avoids injecting unique values into Ruby code, allowing JRuby code reuse
                            branch_tracker = {
                                "id": f"{conditional_id}_else_tracker",
                                "type": "filter",
                                "plugin": "mutate",
                                "config": {
                                    "replace": {
                                        f"[simulation][conditional_branches][{conditional_id}]": "else"
                                    }
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
                        
                        # Add mutate filter to set step and id metadata
                        # Use replace instead of add_field to avoid array accumulation
                        drop_metadata_plugin = {
                            "type": "filter",
                            "plugin": "mutate",
                            "config": {
                                "replace": {
                                    "[simulation][step]": str(current_step),
                                    "[simulation][id]": plugin['id'],
                                    "[simulation][final]": "true"
                                }
                            }
                        }
                        instrumented.append(drop_metadata_plugin)
                        
                        # This code is now IDENTICAL for all drop plugins, allowing JRuby to compile once and reuse
                        pre_drop_code = f"""
require "net/http"
require "uri"
require "json"

# Create snapshot of current event state for the drop plugin
snapshot = {{}}
event.to_hash.each do |key, value|
  # Skip metadata and snapshots field itself to avoid recursion
  next if key.start_with?("@metadata") || key == "snapshots"
  snapshot[key] = value
end

# Get plugin ID from event field
plugin_id = event.get("[simulation][id]")
event.set("[snapshots][#{{plugin_id}}]", snapshot)

# Note: run_id is added to the event at runtime via the simulate endpoint
# Do NOT hardcode it here as it would change the pipeline hash for each simulation

# Convert event to hash and send to API
event_hash = event.to_hash

# Debug: Log run_id to verify it exists
run_id_value = event.get("run_id")
puts "Drop plugin: run_id = #{{run_id_value.inspect}}"

# Send HTTP POST to StreamSimulate endpoint
uri = URI.parse("{logstash_ui_url}/ConnectionManager/StreamSimulate/")
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = (uri.scheme == "https")
http.verify_mode = OpenSSL::SSL::VERIFY_NONE if http.use_ssl?

request = Net::HTTP::Post.new(uri.path, {{"Content-Type" => "application/json"}})
request.body = event_hash.to_json

begin
  response = http.request(request)
  # Log response for debugging
  puts "Drop plugin HTTP response: #{{response.code}} #{{response.message}}"
rescue => e
  # Log error for debugging
  puts "Drop plugin HTTP error: #{{e.class}} - #{{e.message}}"
  puts e.backtrace.join("\\n")
end
""".strip()

                        pre_drop_plugin = {
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
                        # This code is IDENTICAL for all plugins, allowing JRuby to compile once and reuse
                        pre_instrumentation_code = (
                            "# Capture start time in nanoseconds before plugin execution\n"
                            "event.set(\"[simulation][timing][start_ns]\", (Time.now.to_f * 1_000_000_000).to_i)"
                        )

                        pre_instrumentation_plugin = {
                            "type": "filter",
                            "plugin": "ruby",
                            "config": {
                                "code": pre_instrumentation_code
                            }
                        }

                        instrumented.append(pre_instrumentation_plugin)

                        # Add the actual plugin
                        instrumented.append(plugin)

                        # Add mutate filter to set step and id metadata
                        # This avoids embedding unique values in Ruby code, allowing code reuse
                        # Use replace instead of add_field to avoid array accumulation
                        metadata_plugin = {
                            "type": "filter",
                            "plugin": "mutate",
                            "config": {
                                "replace": {
                                    "[simulation][step]": str(current_step),
                                    "[simulation][id]": plugin['id']
                                }
                            }
                        }
                        instrumented.append(metadata_plugin)

                        # Add Ruby instrumentation after this plugin
                        # This code is now IDENTICAL for all plugins, allowing JRuby to compile once and reuse
                        instrumentation_code = (
                            "end_ns = (Time.now.to_f * 1_000_000_000).to_i\n"
                            "start_ns = event.get(\"[simulation][timing][start_ns]\")\n"
                            "if start_ns\n"
                            "  execution_ns = end_ns - start_ns\n"
                            "  event.set(\"[simulation][timing][execution_ns]\", execution_ns)\n"
                            "  event.set(\"[simulation][timing][end_ns]\", end_ns)\n"
                            "end\n"
                            "\n"
                            "snapshot = {}\n"
                            "event.to_hash.each do |key, value|\n"
                            "  next if key.start_with?(\"@metadata\") || key == \"snapshots\"\n"
                            "  snapshot[key] = value\n"
                            "end\n"
                            "\n"
                            "plugin_id = event.get(\"[simulation][id]\")\n"
                            "event.set(\"[snapshots][#{plugin_id}]\", snapshot)"
                        )

                        instrumentation_plugin = {
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
        # Add HTTP output that only sends cloned events (identified by type field).
        # Must target LogstashUI StreamSimulate (not the agent API). On host
        # simulate agents the agent still rebuilds slot conf with pipeline→simulate-end
        # output, but drop-plugin instrumentation posts here directly.
        output_plugins = [
            {
                "id": "http_output",
                "type": "output",
                "plugin": "http",
                "config": {
                    "url": f"{logstash_ui_url}/ConnectionManager/StreamSimulate/",
                    "http_method": "post",
                    "format": "json",
                    "content_type": "application/json",
                    "ssl_verification_mode": "none",
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
        # The logstashagent will add these wrappers when building the complete pipeline
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

        # Session slot: multi-document runs allocate once on the client, then pass
        # slot_id for every document so we never re-allocate mid-session.
        # IMPORTANT: slots are per-agent. A warm slot on host simulate is not valid
        # on embedded (and vice versa). Verify the slot exists on *this* agent before
        # skipping allocate.
        session_slot_raw = (
            request.POST.get("slot_id")
            or request.POST.get("session_slot_id")
            or ""
        ).strip()
        slot_id = None
        reused = False
        use_session_slot = False

        if session_slot_raw and log_text:
            try:
                candidate = int(session_slot_raw)
                if candidate < 1:
                    raise ValueError("slot_id must be >= 1")
                # Confirm this agent actually has the slot (guards host→embedded bleed)
                slots_data = {}
                try:
                    slots_resp = requests.get(
                        f"{logstash_agent_url}/_logstash/slots",
                        verify=agent_requests_verify(),
                        timeout=5,
                    )
                    slots_resp.raise_for_status()
                    slots_data = slots_resp.json() or {}
                    has_slot = (
                        str(candidate) in slots_data
                        or candidate in slots_data
                    )
                except Exception as probe_err:
                    logger.warning(
                        "Could not verify session slot %s on agent: %s — will re-allocate",
                        candidate,
                        probe_err,
                    )
                    has_slot = False

                if has_slot:
                    slot_id = candidate
                    reused = True
                    use_session_slot = True
                    logger.info(
                        "[BE->AGENT] Using session slot %s (skip allocate; document input only)",
                        slot_id,
                    )
                else:
                    logger.warning(
                        "[BE->AGENT] Session slot %s not present on agent (available=%s); "
                        "re-allocating on this target",
                        candidate,
                        list(slots_data.keys()) if isinstance(slots_data, dict) else slots_data,
                    )
            except (TypeError, ValueError) as e:
                return HttpResponse(
                    f'<div class="text-red-400" data-pipeline-failed="true">'
                    f'Error: invalid session slot_id {session_slot_raw!r}: {e}</div>'
                )

        if not use_session_slot:
            # Allocate a slot - the logstashagent will detect if config changed
            slot_allocation_body = {
                "pipeline_name": request.GET.get('pipeline', 'simulation')
                or request.POST.get('pipeline', 'simulation'),
                "pipelines": [pipeline_data]
            }

            logger.info(f"[BE->AGENT] Sending slot allocation with {len(filter_plugins)} filter plugins")
            logger.debug(f"[BE->AGENT] filter_config being sent:\n{filter_content}")

            try:
                # Cold allocate can take well over 30s: optional eviction wait (up to 30s),
                # pipeline create, verify (up to ~20s), and bus settle. Keep UI→agent timeout
                # high so page-load prealloc can finish and Run stays instant on a warm slot.
                response = requests.post(
                    f"{logstash_agent_url}/_logstash/slots/allocate",
                    json=slot_allocation_body,
                    verify=agent_requests_verify(),
                    timeout=120,
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
                agent_detail = None

                # If slot_id wasn't extracted from successful response, try to get it from error response
                if not slot_id and hasattr(e, 'response') and e.response is not None:
                    try:
                        logger.error(
                            "Agent allocate error status=%s body=%s",
                            e.response.status_code,
                            (e.response.text or "")[:800],
                        )

                        error_data = e.response.json()
                        logger.error(f"Agent allocate error JSON: {error_data}")

                        # Check if detail is a dict with slot_id (new format)
                        detail = error_data.get('detail')
                        agent_detail = detail

                        if isinstance(detail, dict):
                            slot_id = detail.get('slot_id')
                            agent_detail = detail.get('message') or detail
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

                # Prefer agent detail message for the chip/tooltip when present
                if isinstance(agent_detail, dict):
                    human = agent_detail.get("message") or str(agent_detail)
                elif agent_detail:
                    human = str(agent_detail)
                else:
                    human = str(e)
                # Escape for HTML
                from html import escape as _html_escape
                human_esc = _html_escape(human[:300])
                error_html = (
                    f'<div class="text-red-400"{slot_id_attr}{failed_attr}>'
                    f'Error allocating slot: {human_esc}</div>'
                )
                logger.debug(f"Returning error HTML: {error_html}")
                return HttpResponse(error_html)

        # Use the slot-based pipeline name
        pipeline_name = f"slot{slot_id}-filter1"

        # Note: No need to verify pipeline here - the slot allocation endpoint already
        # performs comprehensive verification with polling and retries. If we got here,
        # the pipelines are guaranteed to be loaded and ready.

        # If log_text is provided, send it through the pipeline
        if log_text:
            # Send the user's log input via logstashagent's simulate endpoint
            # This proxies the request to the local Logstash HTTP input on port 9449
            simulation_input_url = f"{_sim_agent_url(request)[0]}/_logstash/simulate"
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

                # Send simulation to logstashagent
                # logstashagent handles retries (3x with 1s, 2s, 3s timeouts)
                # If all retries fail, logstashagent triggers restart and queues the request
                response = requests.post(
                    simulation_input_url,
                    json=log_data,
                    verify=agent_requests_verify(),
                    timeout=10  # Timeout to allow logstashagent's 3 retries to complete (1s+2s+3s=6s)
                )
                
                # Check if request was queued (202 status)
                if response.status_code == 202:
                    logger.warning(f"Simulation request queued - Logstash is restarting")
                    return HttpResponse(f'<div class="text-yellow-400">Simulation queued - Logstash is restarting. Results will appear when ready.</div>')
                
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

        # Log detailed information about the received event
        event_run_id = event_data.get('run_id', 'MISSING')
        snapshots = event_data.get('snapshots', {})
        # Logstash may nest as {"plugin-id": {...}} or leave empty on start/end only
        if not snapshots and isinstance(event_data.get('simulation'), dict):
            # Debug empty snapshots: step 0 is expected from simulate-start
            step = event_data.get('simulation', {}).get('step')
            logger.info(
                "[AGENT->BE] Event run_id=%s has no snapshots (simulation.step=%s, id=%s); "
                "keys=%s",
                event_run_id,
                step,
                event_data.get('simulation', {}).get('id'),
                list(event_data.keys())[:30],
            )
        snapshot_count = len(snapshots) if isinstance(snapshots, dict) else 0
        logger.info(f"[AGENT->BE] Received event with run_id={event_run_id}, snapshots={snapshot_count}, queue size now: {queue_size}")
        if snapshots:
            logger.debug(f"[AGENT->BE] Snapshot keys: {list(snapshots.keys()) if isinstance(snapshots, dict) else 'NOT A DICT'}")
        logger.debug(f"StreamSimulate: Event data keys: {list(event_data.keys())}")
        if event_run_id == 'MISSING':
            logger.error(f"StreamSimulate: Event is missing run_id field! Event keys: {list(event_data.keys())}")

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
            
            # Debug: Log all run_ids in the queue
            queue_run_ids = [r.get('run_id', 'MISSING') for r in simulation_results]
            logger.debug(f"GetSimulationResults: Queue has {len(simulation_results)} events with run_ids: {queue_run_ids}")
            logger.debug(f"GetSimulationResults: Looking for run_id: {run_id}")

            for result in simulation_results:
                result_run_id = result.get('run_id')
                if result_run_id == run_id:
                    matching_results.append(result)
                    logger.debug(f"GetSimulationResults: MATCH found for run_id {run_id}")
                else:
                    remaining_results.append(result)
                    logger.debug(f"GetSimulationResults: No match - result has run_id={result_run_id}, looking for {run_id}")

            # Replace the queue with non-matching results
            simulation_results.clear()
            simulation_results.extend(remaining_results)

        # Log snapshot counts for each event being returned
        snapshot_info = []
        for event in matching_results:
            snapshots = event.get('snapshots', {})
            snapshot_info.append(len(snapshots) if snapshots else 0)
        
        logger.info(f"[BE->FE] Returning {len(matching_results)} events for run_id {run_id}, snapshots per event: {snapshot_info}")
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
    Calls logstashagent's is_pipeline_running endpoint to verify pipeline status.

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

        # Call logstashagent to check pipeline status
        logstash_agent_url = f"{_sim_agent_url(request)[0]}/_logstash/pipelines/status"

        try:
            response = requests.get(logstash_agent_url, timeout=5, verify=agent_requests_verify())
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
            logger.error(f"Failed to connect to logstashagent: {e}")
            return JsonResponse({
                "error": f"Failed to connect to logstashagent: {str(e)}",
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
    Calls logstashagent's pipeline logs endpoint to fetch related logs.

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

        # Get slot creation timestamp from logstashagent
        min_timestamp = None
        try:
            slots_response = requests.get(f"{_sim_agent_url(request)[0]}/_logstash/slots", timeout=5, verify=agent_requests_verify())
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

        # Call logstashagent to get pipeline logs
        logstash_agent_url = f"{_sim_agent_url(request)[0]}/_logstash/pipeline/{pipeline_id}/logs"
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
            response = requests.get(logstash_agent_url, params=params, timeout=10, verify=agent_requests_verify())
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
            logger.error(f"Failed to fetch logs from logstashagent: {e}")
            return JsonResponse({
                "error": f"Failed to fetch logs from logstashagent: {str(e)}",
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
    Receives file binary data and transmits it to logstashagent for storage.
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

        # Send to logstashagent
        logstash_agent_url = f"{_sim_agent_url(request)[0]}/_logstash/write-file"

        response = requests.post(
            logstash_agent_url,
            json={
                "filename": filename,
                "content": encoded_content
            },
            verify=agent_requests_verify(),
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
        logger.error(f"Error transmitting file to logstashagent: {e}")
        return JsonResponse({
            "error": f"Failed to upload file to logstashagent: {str(e)}"
        }, status=500)
    except Exception as e:
        logger.error(f"Error in UploadFile: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def GetSimulationNodeStatus(request):
    """
    Check the health status of the logstashagent.
    
    Returns:
        JSON response with:
        - status: "running" if agent is healthy, "not_responding" otherwise
        - message: Human-readable status message
        - agent_info: Additional info from agent (if available)
    """
    try:
        logstash_agent_url, _, _ = _sim_agent_url(request)
        if not logstash_agent_url:
            logstash_agent_url = settings.LOGSTASH_AGENT_URL
        
        try:
            response = requests.get(logstash_agent_url, timeout=3, verify=agent_requests_verify())
            response.raise_for_status()
            
            agent_data = response.json()
            
            return JsonResponse({
                "status": "running",
                "message": "Agent running",
                "agent_info": agent_data
            }, status=200)
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"logstashagent not responding: {e}")
            return JsonResponse({
                "status": "not_responding",
                "message": "Agent offline",
                "error": str(e)
            }, status=200)
    
    except Exception as e:
        logger.error(f"Error in GetSimulationNodeStatus: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            "status": "error",
            "message": "Agent offline",
            "error": str(e)
        }, status=200)


@login_required
def GetSimulationNodeHealth(request):
    """
    Check the health status of Logstash within the simulation node.
    
    Returns:
        JSON response with:
        - healthy: Boolean indicating if Logstash is healthy
        - restarting: Boolean indicating if Logstash is restarting
        - restart_count: Number of times Logstash has restarted
        - queued_requests: Number of queued simulation requests
    """
    try:
        base, _, err = _sim_agent_url(request)
        if not base:
            base = settings.LOGSTASH_AGENT_URL
        if not base:
            return JsonResponse({
                "healthy": False,
                "restarting": False,
                "restart_count": 0,
                "queued_requests": 0,
                "error": err or "No simulation agent available",
            }, status=200)
        logstash_agent_url = f"{base}/_logstash/health"
        
        try:
            response = requests.get(logstash_agent_url, timeout=3, verify=agent_requests_verify())
            response.raise_for_status()
            
            health_data = response.json()
            tls = health_data.get("tls") or {}
            
            return JsonResponse({
                "healthy": health_data.get("healthy", False),
                "restarting": health_data.get("restarting", False),
                "restart_count": health_data.get("restart_count", 0),
                "queued_requests": health_data.get("queued_requests", 0),
                # Agent→UI product CA pin (secure) and bootstrap status
                "tls": tls,
                "secure": bool(tls.get("secure") or tls.get("ca_pinned")),
                "online": bool(health_data.get("healthy", False)),
            }, status=200)
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get Logstash health from agent: {e}")
            return JsonResponse({
                "healthy": False,
                "restarting": False,
                "restart_count": 0,
                "queued_requests": 0,
                "online": False,
                "secure": False,
                "error": str(e)
            }, status=200)
    
    except Exception as e:
        logger.error(f"Error in GetSimulationNodeHealth: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            "healthy": False,
            "restarting": False,
            "restart_count": 0,
            "queued_requests": 0,
            "error": str(e)
        }, status=200)


@require_admin_role
def ValidateLogstashConfig(request):
    """
    Validate a Logstash pipeline configuration by sending it to logstashagent
    for validation using logstash --config.test_and_exit.
    
    Expected POST parameters:
        - components: JSON string of pipeline components
        - pipeline_name: Name of the pipeline (used for temp file naming)
    
    Returns:
        JSON response with:
        - status: "OK" or "ERROR"
        - notifications: List of warning/deprecation messages
        - error: Error message if validation failed
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        components_json = request.POST.get('components')
        pipeline_name = request.POST.get('pipeline_name', 'pipeline')
        
        if not components_json:
            return JsonResponse({
                "status": "ERROR",
                "error": "No pipeline components provided"
            }, status=400)
        
        try:
            components = json.loads(components_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse components JSON: {e}")
            return JsonResponse({
                "status": "ERROR",
                "error": "Invalid components data"
            }, status=400)
        
        # Convert components to Logstash config
        converter = logstash_config_parse.ComponentToPipeline(components, test=False)
        logstash_config = converter.components_to_logstash_config()
        
        # Send to logstashagent for validation
        logstash_agent_url = f"{_sim_agent_url(request)[0]}/_logstash/validate"
        
        try:
            response = requests.post(
                logstash_agent_url,
                json={
                    "pipeline_name": pipeline_name,
                    "config": logstash_config
                },
                verify=agent_requests_verify(),
                timeout=30
            )
            response.raise_for_status()
            
            validation_result = response.json()
            logger.info(f"Validation result for pipeline '{pipeline_name}': {validation_result.get('status')}")
            
            return JsonResponse(validation_result, status=200)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to validate config via logstashagent: {e}")
            return JsonResponse({
                "status": "ERROR",
                "error": f"Failed to connect to logstashagent: {str(e)}"
            }, status=500)
    
    except Exception as e:
        logger.error(f"Error in ValidateLogstashConfig: {e}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            "status": "ERROR",
            "error": str(e)
        }, status=500)
