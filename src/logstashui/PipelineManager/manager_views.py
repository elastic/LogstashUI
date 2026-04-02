#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from .forms import ConnectionForm
from PipelineManager.models import Connection as ConnectionTable, Policy, Pipeline, EnrollmentToken, ApiKey, Revision, Keystore

from Common.decorators import require_admin_role
from Common.logstash_utils import get_logstash_pipeline
from Common.elastic_utils import get_elastic_connection, test_elastic_connectivity
from Common.validators import validate_pipeline_name

from datetime import datetime, timedelta, timezone
from html import escape

import logging
import json
import base64
import hashlib
import secrets
import requests
import os
from Common.encryption import encrypt_credential
from cryptography.fernet import Fernet


def _encrypt_for_agent(raw_api_key: str, plaintext: str) -> str:
    """
    Encrypt a plaintext value for transport to a specific agent.
    Uses the agent's raw API key (SHA-256 → base64) as the Fernet key so that
    only that agent — which holds the same API key — can decrypt it.
    """
    key = base64.urlsafe_b64encode(hashlib.sha256(raw_api_key.encode('utf-8')).digest())
    return Fernet(key).encrypt(plaintext.encode('utf-8')).decode('utf-8')

logger = logging.getLogger(__name__)


def load_default_config(filename):
    """Load default configuration file from the data directory"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, 'data', filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Default config file not found: {file_path}")
        return ""
    except Exception as e:
        logger.error(f"Error loading default config file {filename}: {str(e)}")
        return ""


def get_default_logstash_yml():
    """Get default logstash.yml configuration"""
    return load_default_config('default_logstash.yml')


def get_default_jvm_options():
    """Get default jvm.options configuration"""
    return load_default_config('default_jvm.options')


def get_default_log4j2_properties():
    """Get default log4j2.properties configuration"""
    return load_default_config('default_log4j2.properties')



@require_admin_role
def AgentPolicies(request):
    """
    View for managing Logstash Agent Policies
    """
    context = {}
    return render(request, "components/pipeline_manager/agent_policies.html", context=context)


def PipelineManager(request):
    """Builds the table of pipelines"""
    context = {}
    connections = list(ConnectionTable.objects.values("connection_type", "name", "host", "cloud_id", "cloud_url", "pk", "policy__name", "last_check_in", "status_blob"))
    
    # Add is_online flag based on last_check_in time (within 10 minutes)
    now = datetime.now(timezone.utc)
    for conn in connections:
        if conn['last_check_in']:
            time_diff = now - conn['last_check_in']
            conn['is_online'] = time_diff.total_seconds() < 600  # 10 minutes = 600 seconds
        else:
            conn['is_online'] = False
    
    # Sort connections: centralized first, then by policy name
    # This groups agents with the same policy together
    def sort_key(conn):
        if conn['connection_type'] == 'CENTRALIZED':
            return (0, '')  # Centralized first
        else:
            return (1, conn['policy__name'] or 'zzz_no_policy')  # Then by policy name
    
    connections.sort(key=sort_key)
    
    # Add grouping metadata for visual styling
    # Treat each connection (centralized or agent policy) as its own group
    prev_policy = None
    policy_color_index = 0
    colors = ['blue', 'green', 'purple', 'pink', 'yellow', 'cyan']
    
    for i, conn in enumerate(connections):
        if conn['connection_type'] == 'AGENT':
            current_policy = conn['policy__name'] or 'No Policy'
        else:
            # Each centralized connection is its own unique "policy"
            current_policy = f"CENTRALIZED_{conn['pk']}"
        
        # Check if this is the first row of a policy group
        if current_policy != prev_policy:
            conn['is_group_start'] = True
            # Assign a color to this policy group
            conn['group_color'] = colors[policy_color_index % len(colors)]
            policy_color_index += 1
        else:
            conn['is_group_start'] = False
            # Use the same color as the previous connection in the group
            conn['group_color'] = connections[i-1]['group_color']
        
        # Check if this is the last row of a policy group
        is_last = (i == len(connections) - 1)
        if not is_last:
            next_conn = connections[i + 1]
            if next_conn['connection_type'] == 'AGENT':
                next_policy = next_conn.get('policy__name') or 'No Policy'
            else:
                next_policy = f"CENTRALIZED_{next_conn['pk']}"
            conn['is_group_end'] = (current_policy != next_policy)
        else:
            conn['is_group_end'] = True
        
        prev_policy = current_policy
    
    context['connections'] = connections
    context['has_connections'] = len(connections) > 0
    context['form'] = ConnectionForm()

    return render(request, "pipeline_manager.html", context=context)


def test_connectivity(connection_id):
    """
    Test connectivity to an Elasticsearch connection.
    Pure Python function for programmatic use.
    
    Args:
        connection_id: ID of the connection to test
        
    Returns:
        tuple: (success: bool, message: str)
    """
    if not connection_id:
        return (False, "No connection ID provided")
    
    try:
        elastic_connection = get_elastic_connection(connection_id)
        result = test_elastic_connectivity(elastic_connection)
        return (True, result)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Connection test against {connection_id} failed: {error_msg}")
        return (False, error_msg)


def TestConnectivity(request):
    """
    Django view to test connectivity to an Elasticsearch connection.
    Returns HTML response for HTMX.
    """
    test_id = request.GET.get('test')
    
    if not test_id:
        return HttpResponse("No connection ID provided", status=400)
    
    logger.info(f"User '{request.user.username}' testing connection {test_id}")
    success, message = test_connectivity(test_id)
    
    if success:
        return HttpResponse("""
            <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg"
                onload="setTimeout(() => this.remove(), 3000);">
                <p>{0}</p>
            </div>
        """.format(escape(str(message))))
    else:
        return HttpResponse("""
            <div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">
                <p>Connection failed: {0}</p>
            </div>
        """.format(escape(str(message))))


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
            success, message = test_connectivity(new_connection.id)

            if not success:
                # If test fails, delete the connection and return JSON error
                new_connection.delete()
                logger.error(f"User '{request.user.username}' failed to add connection, {new_connection.id}")
                
                return JsonResponse({
                    'success': False,
                    'error': str(message)
                }, status=200)

            # Connection test succeeded, return JSON response
            logger.info(f"User '{request.user.username}' added a new connection, {new_connection.id}")
            logger.info(f"Returning success response with connection ID: {new_connection.id}")
            return JsonResponse({
                'success': True,
                'connection_id': new_connection.id,
                'message': 'Connection created and tested successfully!'
            }, status=200)
        else:
            logger.warning(f"User '{request.user.username}' failed to add connection: {form.errors}")
            return JsonResponse({
                'success': False,
                'error': str(form.errors)
            }, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@require_admin_role
def DeleteConnection(request, connection_id=None):
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)
    
    if not connection_id:
        return HttpResponse("Connection ID is required", status=400)
    
    connection = ConnectionTable.objects.filter(id=connection_id).first()
    if not connection:
        return HttpResponse(
            '<div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">Connection not found</div>',
            status=404
        )
    
    connection_name = connection.name
    connection.delete()
    logger.warning(
        f"User '{request.user.username}' deleted connection '{connection_name}' (ID: {connection_id})")

    return HttpResponse("""
        <script>
            showToast('Connection deleted successfully!', 'success');
            // Reload the page to show the updated connections
            setTimeout(() => {
                window.location.reload();
            }, 500);
        </script>
    """)


def GetPipelines(request, connection_id):
    context = {}
    try:
        connection = ConnectionTable.objects.get(pk=connection_id)
    except ConnectionTable.DoesNotExist:
        return HttpResponse(
            '<div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">Connection not found</div>',
            status=404
        )

    logstash_pipelines = []

    if connection.connection_type == "CENTRALIZED":
        # Fetch pipelines from Elasticsearch for centralized connections
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

    else:  # AGENT connection type
        # Fetch pipelines from the associated policy for agent connections
        if connection.policy:
            pipelines = Pipeline.objects.filter(policy=connection.policy).values(
                'id', 'name', 'description', 'last_updated'
            )

            for p in pipelines:
                # Format last_updated timestamp
                formatted_date = ""
                if p['last_updated']:
                    try:
                        day = p['last_updated'].day
                        suffix = 'th' if 11 <= day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
                        formatted_date = p['last_updated'].strftime(f'%A, %B {day}{suffix} %Y')
                    except Exception:
                        formatted_date = p['last_updated'].strftime('%Y-%m-%d %H:%M:%S')

                logstash_pipelines.append({
                    "es_id": connection.policy.id,  # Use policy ID for compatibility
                    "es_name": connection.name,
                    "name": p['name'],
                    "description": p['description'] or '',
                    "last_modified": formatted_date,
                    "policy_id": connection.policy.id  # Add policy_id to each pipeline for delete/clone
                })

    context['pipelines'] = logstash_pipelines
    context['es_id'] = connection.id
    context['policy_id'] = connection.policy.id if connection.policy else None
    context['editor_id_param'] = 'ls_id' if connection.policy else 'es_id'

    logstash_template = get_template("components/pipeline_manager/collapsible_row.html")
    html = logstash_template.render(context)
    return HttpResponse(html)


@require_admin_role
def GetPolicyPipelines(request):
    """
    Get pipelines for a specific policy (agent policy context).
    Returns JSON response with pipeline data.
    """
    policy_id = request.GET.get('policy_id')

    if not policy_id:
        return JsonResponse({'success': False, 'error': 'Policy ID is required'}, status=400)

    try:
        policy = Policy.objects.get(pk=policy_id)

        # Get all pipelines for this policy
        pipelines = Pipeline.objects.filter(policy=policy).values(
            'id', 'name', 'description', 'last_updated'
        )

        pipelines_list = []
        for p in pipelines:
            pipelines_list.append({
                'id': p['id'],
                'name': p['name'],
                'description': p['description'] or '',
                'last_modified': p['last_updated'].strftime('%Y-%m-%d %H:%M:%S') if p['last_updated'] else 'N/A',
                'es_id': policy_id,  # Use policy_id as es_id for compatibility with frontend
                'policy_id': policy_id  # Tells pipeline_list.js to use ls_id= in the editor URL
            })

        return JsonResponse({
            'success': True,
            'pipelines': pipelines_list
        })

    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'Policy with ID {policy_id} not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching pipelines for policy {policy_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_admin_role
def UpdatePipelineSettings(request):
    if request.method == "POST":
        try:
            es_id = request.POST.get("es_id")
            ls_id = request.POST.get("ls_id")
            pipeline_name = request.POST.get("pipeline")

            # Validate required fields - need either es_id or ls_id
            if not (es_id or ls_id) or not pipeline_name:
                return HttpResponse(
                    'Error: Missing pipeline ID or connection ID',
                    status=400
                )

            # Validate pipeline name
            is_valid, error_msg = validate_pipeline_name(pipeline_name)
            if not is_valid:
                return HttpResponse(error_msg, status=400)

            # Get form values
            description = request.POST.get("description", "")
            pipeline_workers = request.POST.get("pipeline_workers")
            pipeline_batch_size = request.POST.get("pipeline_batch_size")
            pipeline_batch_delay = request.POST.get("pipeline_batch_delay")
            queue_type = request.POST.get("queue_type")
            queue_max_bytes = request.POST.get("queue_max_bytes")
            queue_max_bytes_unit = request.POST.get("queue_max_bytes_unit")
            queue_checkpoint_writes = request.POST.get("queue_checkpoint_writes")

            # Handle ls_id (agent pipeline) vs es_id (centralized pipeline)
            if ls_id:
                # Update Pipeline model for agent policy
                try:
                    pipeline_obj = Pipeline.objects.get(policy_id=ls_id, name=pipeline_name)
                    
                    # Update fields
                    if description is not None:
                        pipeline_obj.description = description
                    if pipeline_workers:
                        pipeline_obj.pipeline_workers = int(pipeline_workers)
                    if pipeline_batch_size:
                        pipeline_obj.pipeline_batch_size = int(pipeline_batch_size)
                    if pipeline_batch_delay:
                        pipeline_obj.pipeline_batch_delay = int(pipeline_batch_delay)
                    if queue_type:
                        pipeline_obj.queue_type = queue_type
                    if queue_max_bytes is not None and queue_max_bytes != '' and queue_max_bytes_unit:
                        pipeline_obj.queue_max_bytes = f"{queue_max_bytes}{queue_max_bytes_unit}"
                    if queue_checkpoint_writes:
                        pipeline_obj.queue_checkpoint_writes = int(queue_checkpoint_writes)
                    
                    pipeline_obj.save()
                    
                    # Mark policy as having undeployed changes
                    policy = Policy.objects.get(pk=ls_id)
                    policy.has_undeployed_changes = True
                    policy.save(update_fields=['has_undeployed_changes'])
                    
                    logger.info(
                        f"User '{request.user.username}' updated settings for pipeline '{pipeline_name}' in policy {ls_id}")
                    return HttpResponse('', status=200)
                    
                except Pipeline.DoesNotExist:
                    return HttpResponse(f"Pipeline '{pipeline_name}' not found in policy {ls_id}", status=404)
            else:
                # Update centralized pipeline via Elasticsearch
                current_pipeline_config = get_logstash_pipeline(es_id, pipeline_name)
                settings_body = {
                    "pipeline": current_pipeline_config['pipeline'],
                    "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                    "pipeline_metadata": {
                        "version": current_pipeline_config['pipeline_metadata']['version'] + 1,
                        "type": "logstash_pipeline"
                    },
                    "username": "logstashui",
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
                if queue_max_bytes is not None and queue_max_bytes != '' and queue_max_bytes_unit:
                    settings_body['pipeline_settings']["queue.max_bytes"] = f"{queue_max_bytes}{queue_max_bytes_unit}"
                if queue_checkpoint_writes:
                    settings_body['pipeline_settings']["queue.checkpoint.writes"] = int(queue_checkpoint_writes)

                # Get Elasticsearch connection and update pipeline settings
                es = get_elastic_connection(es_id)
                es.logstash.put_pipeline(id=pipeline_name, body=settings_body)

                logger.info(
                    f"User '{request.user.username}' updated settings for pipeline '{pipeline_name}' (Connection ID: {es_id})")
                return HttpResponse('', status=200)

        except Exception as e:
            # Return simple error message - toast notification handled by JavaScript
            logger.error(f"Error updating pipeline settings: {str(e)}")
            return HttpResponse(str(e), status=500)

    return HttpResponse('Invalid request method', status=405)


@require_admin_role
def CreatePipeline(request, simulate=False, pipeline_name=None, pipeline_config=None):
    """
    Create a pipeline in Elasticsearch, LogstashAgent, or Django Pipeline model.

    Args:
        request: Django request object
        simulate: If True, send to logstashagent instead of Elasticsearch
        pipeline_name: Pipeline name (used when called directly for simulation)
        pipeline_config: Pipeline config string (used when called directly for simulation)
    """

    if request.method == "POST" or simulate:
        # Get parameters from POST or function arguments
        if not simulate:
            es_id = request.POST.get("es_id")
            policy_id = request.POST.get("policy_id")
            pipeline_name = request.POST.get("pipeline")
            pipeline_config = request.POST.get("pipeline_config", "").strip()
        else:
            es_id = None
            policy_id = None

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        # Use provided config or default empty config
        if pipeline_config:
            pipeline_content = pipeline_config
        else:
            pipeline_content = "input {}\nfilter {}\noutput {}"

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Create pipeline in Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)

                # Check if pipeline already exists
                if Pipeline.objects.filter(policy=policy, name=pipeline_name).exists():
                    return HttpResponse("A pipeline already exists with that name", status=400)

                # Create the pipeline (hash will be computed automatically by the model's save method)
                pipeline = Pipeline.objects.create(
                    policy=policy,
                    name=pipeline_name,
                    description="",
                    lscl=pipeline_content
                )

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.info(
                    f"User '{request.user.username}' created pipeline '{pipeline_name}' in policy '{policy.name}' (ID: {policy_id})")

                # Return success response - redirect to pipeline editor (same as centralized)
                response = HttpResponse("Pipeline created successfully!", status=200)
                response['HX-Redirect'] = f'/ConnectionManager/Pipelines/Editor/?ls_id={policy_id}&pipeline={pipeline_name}'
                return response

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Exception as e:
                logger.error(f"Failed to create pipeline in policy: {e}")
                return HttpResponse(f"Failed to create pipeline: {str(e)}", status=500)

        # Build the pipeline body for Elasticsearch/LogstashAgent
        pipeline_body = {
            "pipeline": pipeline_content,
            "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "pipeline_metadata": {
                "version": 1,
                "type": "logstash_pipeline"
            },
            "username": "logstashui",
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
            # Send to logstashagent
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
                    f"User '{request.user.username}' created simulation pipeline '{pipeline_name}' in logstashagent")
                return HttpResponse("Simulation pipeline created successfully!", status=200)
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to create simulation pipeline in logstashagent: {e}")
                return HttpResponse(f"Failed to create simulation pipeline: {str(e)}", status=500)
        elif es_id:
            # Send to Elasticsearch (centralized pipeline management)
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
        else:
            # No valid context provided
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


@require_admin_role
def DeletePipeline(request):
    if request.method == "POST":
        # Handle both JSON and form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            es_id = data.get("es_id")
            pipeline_name = data.get("pipeline")
            policy_id = data.get("policy_id")
        else:
            es_id = request.POST.get("es_id")
            pipeline_name = request.POST.get("pipeline")
            policy_id = request.POST.get("policy_id")

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Delete from Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)
                pipeline = Pipeline.objects.get(policy=policy, name=pipeline_name)
                pipeline.delete()

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.warning(
                    f"User '{request.user.username}' deleted pipeline '{pipeline_name}' from policy '{policy.name}' (ID: {policy_id})")
                return HttpResponse(status=204)

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Pipeline.DoesNotExist:
                return HttpResponse(f"Pipeline '{pipeline_name}' not found in this policy.", status=404)
            except Exception as e:
                logger.error(f"Failed to delete pipeline from policy: {e}")
                return HttpResponse(f"Failed to delete pipeline: {str(e)}", status=500)

        elif es_id:
            # Delete from Elasticsearch for centralized pipeline management
            try:
                es = get_elastic_connection(es_id)
                es.logstash.delete_pipeline(id=pipeline_name)

                logger.warning(f"User '{request.user.username}' deleted pipeline '{pipeline_name}' (Connection ID: {es_id})")
                return HttpResponse(status=204)
            except Exception as e:
                logger.error(f"Failed to delete pipeline from Elasticsearch: {e}")
                return HttpResponse(f"Failed to delete pipeline: {str(e)}", status=500)
        else:
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


@require_admin_role
def ClonePipeline(request):
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        policy_id = request.POST.get("policy_id")
        source_pipeline = request.POST.get("source_pipeline")
        new_pipeline = request.POST.get("new_pipeline")

        # Debug logging
        logger.info(f"ClonePipeline called with: es_id={es_id}, policy_id={policy_id}, source={source_pipeline}, new={new_pipeline}")

        # Validate source pipeline name
        is_valid, error_msg = validate_pipeline_name(source_pipeline)
        if not is_valid:
            return HttpResponse(f"Invalid source pipeline name: {error_msg}", status=400)

        # Validate new pipeline name
        is_valid, error_msg = validate_pipeline_name(new_pipeline)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Clone within Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)

                # Get the source pipeline
                try:
                    source = Pipeline.objects.get(policy=policy, name=source_pipeline)
                except Pipeline.DoesNotExist:
                    return HttpResponse(f"Source pipeline '{source_pipeline}' not found in this policy.", status=404)

                # Check if new pipeline name already exists
                if Pipeline.objects.filter(policy=policy, name=new_pipeline).exists():
                    # Return 400 status so HTMX triggers response-error event
                    return HttpResponse("A pipeline already exists with that name", status=400)

                # Create the cloned pipeline
                Pipeline.objects.create(
                    policy=policy,
                    name=new_pipeline,
                    description=f"Cloned from {source_pipeline}",
                    lscl=source.lscl
                )

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.info(
                    f"User '{request.user.username}' cloned pipeline '{source_pipeline}' to '{new_pipeline}' in policy '{policy.name}' (ID: {policy_id})")

                # Return success with HX-Trigger to refresh the list
                # Get the connection ID from the policy to trigger the correct event
                connection = ConnectionTable.objects.filter(policy=policy).first()
                connection_id = connection.id if connection else es_id
                response = HttpResponse("Pipeline cloned successfully!", status=200)
                response['HX-Trigger'] = f'pipelineCloned-{connection_id}'
                return response

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Exception as e:
                logger.error(f"Failed to clone pipeline in policy: {e}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Failed to clone pipeline: {str(e)}", status=500)

        elif es_id:
            # Clone in Elasticsearch for centralized pipeline management
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
                    return HttpResponse("A pipeline already exists with that name", status=400)

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
                        "username": "logstashui",
                        "pipeline_settings": source_data.get('pipeline_settings', {}),
                        "description": source_data.get('description', f"Cloned from {source_pipeline}")
                    }
                )

                logger.info(
                    f"User '{request.user.username}' cloned pipeline '{source_pipeline}' to '{new_pipeline}' (Connection ID: {es_id})")

                # Return success with HX-Trigger to refresh the list
                response = HttpResponse("Pipeline cloned successfully!", status=200)
                response['HX-Trigger'] = f'pipelineCloned-{es_id}'
                return response

            except Exception as e:
                logger.error(f"Error cloning pipeline: {str(e)}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Error cloning pipeline: {str(e)}", status=500)
        else:
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


@require_admin_role
def RenamePipeline(request):
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        policy_id = request.POST.get("policy_id")
        source_pipeline = request.POST.get("source_pipeline")
        new_pipeline = request.POST.get("new_pipeline")

        # Debug logging
        logger.info(f"RenamePipeline called with: es_id={es_id}, policy_id={policy_id}, source={source_pipeline}, new={new_pipeline}")

        # Validate source pipeline name
        is_valid, error_msg = validate_pipeline_name(source_pipeline)
        if not is_valid:
            return HttpResponse(f"Invalid source pipeline name: {error_msg}", status=400)

        # Validate new pipeline name
        is_valid, error_msg = validate_pipeline_name(new_pipeline)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Rename within Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)

                # Get the source pipeline
                try:
                    source = Pipeline.objects.get(policy=policy, name=source_pipeline)
                except Pipeline.DoesNotExist:
                    return HttpResponse(f"Source pipeline '{source_pipeline}' not found in this policy.", status=404)

                # Check if new pipeline name already exists
                if Pipeline.objects.filter(policy=policy, name=new_pipeline).exists():
                    return HttpResponse("A pipeline already exists with that name", status=400)

                # Create the renamed pipeline (clone)
                Pipeline.objects.create(
                    policy=policy,
                    name=new_pipeline,
                    description=source.description,
                    lscl=source.lscl
                )

                # Delete the original pipeline
                source.delete()

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.info(
                    f"User '{request.user.username}' renamed pipeline '{source_pipeline}' to '{new_pipeline}' in policy '{policy.name}' (ID: {policy_id})")

                # Return success with HX-Trigger to refresh the list
                # Get the connection ID from the policy to trigger the correct event
                connection = ConnectionTable.objects.filter(policy=policy).first()
                connection_id = connection.id if connection else es_id
                response = HttpResponse("Pipeline renamed successfully!", status=200)
                response['HX-Trigger'] = f'pipelineRenamed-{connection_id}'
                return response

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Exception as e:
                logger.error(f"Failed to rename pipeline in policy: {e}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Failed to rename pipeline: {str(e)}", status=500)

        elif es_id:
            # Rename in Elasticsearch for centralized pipeline management
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
                    return HttpResponse("A pipeline already exists with that name", status=400)

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
                        "username": "logstashui",
                        "pipeline_settings": source_data.get('pipeline_settings', {}),
                        "description": source_data.get('description', '')
                    }
                )

                # Delete the original pipeline
                es.logstash.delete_pipeline(id=source_pipeline)

                logger.info(
                    f"User '{request.user.username}' renamed pipeline '{source_pipeline}' to '{new_pipeline}' (Connection ID: {es_id})")

                # Return success with HX-Trigger to refresh the list
                response = HttpResponse("Pipeline renamed successfully!", status=200)
                response['HX-Trigger'] = f'pipelineRenamed-{es_id}'
                return response

            except Exception as e:
                logger.error(f"Error renaming pipeline: {str(e)}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Error renaming pipeline: {str(e)}", status=500)
        else:
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


@require_admin_role
def UpdatePipelineDescription(request):
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        policy_id = request.POST.get("policy_id")
        pipeline_name = request.POST.get("pipeline_name")
        description = request.POST.get("description", "")

        # Debug logging
        logger.info(f"UpdatePipelineDescription called with: es_id={es_id}, policy_id={policy_id}, pipeline={pipeline_name}")

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(f"Invalid pipeline name: {error_msg}", status=400)

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Update description in Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)

                # Get the pipeline
                try:
                    pipeline = Pipeline.objects.get(policy=policy, name=pipeline_name)
                except Pipeline.DoesNotExist:
                    return HttpResponse(f"Pipeline '{pipeline_name}' not found in this policy.", status=404)

                # Update the description
                pipeline.description = description
                pipeline.save()

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.info(
                    f"User '{request.user.username}' updated description for pipeline '{pipeline_name}' in policy '{policy.name}' (ID: {policy_id})")

                # Return success with HX-Trigger to refresh the list
                connection = ConnectionTable.objects.filter(policy=policy).first()
                connection_id = connection.id if connection else es_id
                response = HttpResponse("Pipeline description updated successfully!", status=200)
                response['HX-Trigger'] = f'pipelineDescriptionUpdated-{connection_id}'
                return response

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Exception as e:
                logger.error(f"Failed to update pipeline description in policy: {e}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Failed to update pipeline description: {str(e)}", status=500)

        elif es_id:
            # Update description in Elasticsearch for centralized pipeline management
            try:
                es = get_elastic_connection(es_id)

                # Get the current pipeline configuration
                current_config = es.logstash.get_pipeline(id=pipeline_name)

                if pipeline_name not in current_config:
                    return HttpResponse(f"Pipeline '{pipeline_name}' not found", status=404)

                current_data = current_config[pipeline_name]

                # Update the pipeline with new description
                es.logstash.put_pipeline(
                    id=pipeline_name,
                    body={
                        "pipeline": current_data['pipeline'],
                        "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                        "pipeline_metadata": {
                            "version": current_data['pipeline_metadata'].get('version', 1) + 1,
                            "type": "logstash_pipeline"
                        },
                        "username": "logstashui",
                        "pipeline_settings": current_data.get('pipeline_settings', {}),
                        "description": description
                    }
                )

                logger.info(
                    f"User '{request.user.username}' updated description for pipeline '{pipeline_name}' (Connection ID: {es_id})")

                # Return success with HX-Trigger to refresh the list
                response = HttpResponse("Pipeline description updated successfully!", status=200)
                response['HX-Trigger'] = f'pipelineDescriptionUpdated-{es_id}'
                return response

            except Exception as e:
                logger.error(f"Error updating pipeline description: {str(e)}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Error updating pipeline description: {str(e)}", status=500)
        else:
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


def GetPipeline(request):
    if request.method == "GET":
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")

        # Validate required parameters
        if not es_id or not pipeline_name:
            return JsonResponse({"error": "Missing required parameters: es_id and pipeline"}, status=400)

        pipeline_config = get_logstash_pipeline(es_id, pipeline_name)
        
        # Handle case where pipeline couldn't be fetched
        if not pipeline_config:
            return JsonResponse({"error": f"Could not fetch pipeline '{pipeline_name}' from connection {es_id}"}, status=400)

        pipeline_string = pipeline_config['pipeline']

        return JsonResponse({"code": pipeline_string})


@require_admin_role
def add_policy(request):
    """
    Create a new policy
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        
        name = data.get('name', '').strip()
        settings_path = data.get('settings_path', '/etc/logstash/')
        logs_path = data.get('logs_path', '/var/log/logstash')
        binary_path = data.get('binary_path', '/usr/share/logstash/bin')

        # Use defaults if values are empty or not provided
        logstash_yml = data.get('logstash_yml') or get_default_logstash_yml()
        jvm_options = data.get('jvm_options') or get_default_jvm_options()
        log4j2_properties = data.get('log4j2_properties') or get_default_log4j2_properties()
        
        if not name:
            return JsonResponse({"success": False, "error": "Policy name is required"}, status=400)
        
        # Check if policy already exists
        if Policy.objects.filter(name=name).exists():
            return JsonResponse({"success": False, "error": f"Policy '{name}' already exists"}, status=400)
        
        # Create the policy
        policy = Policy.objects.create(
            name=name,
            settings_path=settings_path,
            logs_path=logs_path,
            binary_path=binary_path,
            logstash_yml=logstash_yml,
            jvm_options=jvm_options,
            log4j2_properties=log4j2_properties
        )
        
        # Generate enrollment token for the new policy
        enrollment_token = secrets.token_urlsafe(32)
        
        # Create enrollment token record in database with name 'default'
        EnrollmentToken.objects.create(
            policy=policy,
            name='default',
            token=enrollment_token
        )
        
        logger.info(f"User '{request.user.username}' created policy '{name}' with enrollment token")
        
        return JsonResponse({
            "success": True,
            "message": f"Policy '{name}' created successfully",
            "policy_id": policy.id,
            "policy_name": policy.name
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error creating policy: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def update_policy(request):
    """
    Update an existing policy
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        
        policy_name = data.get('policy_name', '').strip()
        
        if not policy_name:
            return JsonResponse({"success": False, "error": "Policy name is required"}, status=400)
        
        # Don't allow updating Default policy
        if policy_name.lower() == 'default policy':
            return JsonResponse({"success": False, "error": "Cannot update Default Policy"}, status=403)
        
        try:
            policy = Policy.objects.get(name=policy_name)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": f"Policy '{policy_name}' not found"}, status=404)
        
        # Update fields if provided
        if 'settings_path' in data:
            policy.settings_path = data['settings_path']
        if 'logs_path' in data:
            policy.logs_path = data['logs_path']
        if 'binary_path' in data:
            policy.binary_path = data['binary_path']
        if 'logstash_yml' in data:
            policy.logstash_yml = data['logstash_yml']
        if 'jvm_options' in data:
            policy.jvm_options = data['jvm_options']
        if 'log4j2_properties' in data:
            policy.log4j2_properties = data['log4j2_properties']
        
        policy.save()
        
        logger.info(f"User '{request.user.username}' updated policy '{policy_name}'")
        
        return JsonResponse({
            "success": True,
            "message": f"Policy '{policy_name}' updated successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error updating policy: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def get_policies(request):
    """
    Get all policies
    """
    try:
        policies = Policy.objects.all().values(
            'id', 'name', 'settings_path', 'logs_path', 'binary_path',
            'logstash_yml', 'jvm_options', 'log4j2_properties',
            'created_at', 'updated_at'
        )
        
        return JsonResponse({
            "success": True,
            "policies": list(policies)
        })
        
    except Exception as e:
        logger.error(f"Error fetching policies: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def get_policy_agent_count(request):
    """
    Get the count of agents (connections) using a specific policy
    """
    try:
        policy_id = request.GET.get('policy_id')

        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)

        # Get the policy
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

        # Count connections using this policy
        agent_count = ConnectionTable.objects.filter(
            policy=policy,
            connection_type=ConnectionTable.ConnectionType.AGENT,
            is_active=True
        ).count()

        return JsonResponse({
            "success": True,
            "agent_count": agent_count,
            "policy_name": policy.name
        })

    except Exception as e:
        logger.error(f"Error getting policy agent count: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def delete_policy(request):
    """
    Delete a policy
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        
        policy_name = data.get('policy_name', '').strip()
        
        if not policy_name:
            return JsonResponse({"success": False, "error": "Policy name is required"}, status=400)
        
        # Don't allow deleting Default policy
        if policy_name.lower() == 'default policy':
            return JsonResponse({"success": False, "error": "Cannot delete Default Policy"}, status=403)
        
        try:
            policy = Policy.objects.get(name=policy_name)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": f"Policy '{policy_name}' not found"}, status=404)
        
        # Check if policy is in use
        connections_count = policy.connections.count()
        if connections_count > 0:
            return JsonResponse({
                "success": False,
                "error": f"Cannot delete policy '{policy_name}' - it is currently assigned to {connections_count} connection(s)"
            }, status=400)
        
        policy.delete()
        
        logger.info(f"User '{request.user.username}' deleted policy '{policy_name}'")
        
        return JsonResponse({
            "success": True,
            "message": f"Policy '{policy_name}' deleted successfully"
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error deleting policy: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def generate_enrollment_token(request):
    """
    Generate an enrollment token for Logstash Agent
    Token contains: enrollment token only (logstashui URL provided via command-line)
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        policy_name = data.get('policy_name', 'Default')

        # Generate a secure random enrollment token
        enrollment_token = secrets.token_urlsafe(32)
        
        # Create token payload (only enrollment_token, no URL)
        token_payload = {
            "enrollment_token": enrollment_token,
        }
        
        # Encode as base64
        json_string = json.dumps(token_payload)
        encoded_token = base64.b64encode(json_string.encode('utf-8')).decode('utf-8')

        logger.info(f"User '{request.user.username}' generated enrollment token for policy '{policy_name}'")
        
        return JsonResponse({
            "success": True,
            "enrollment_token": encoded_token,
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error generating enrollment token: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
def enroll(request):
    """
    Enroll a Logstash Agent using an enrollment token
    Validates token in database, creates connection, and generates API key
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        encoded_token = data.get('enrollment_token')
        host = data.get('host')
        agent_id = data.get('agent_id')
        
        # Validate required fields
        if not encoded_token or not host or not agent_id:
            return JsonResponse({
                "success": False, 
                "error": "Missing required fields: enrollment_token, host, agent_id"
            }, status=400)
        
        # Decode the base64 enrollment token
        try:
            decoded_json = base64.b64decode(encoded_token.encode('utf-8')).decode('utf-8')
            token_payload = json.loads(decoded_json)
        except Exception as e:
            logger.error(f"Failed to decode enrollment token: {str(e)}")
            return JsonResponse({"success": False, "error": "Invalid enrollment token format"}, status=400)
        
        # Extract enrollment token from payload
        enrollment_token = token_payload.get('enrollment_token')
        
        if not enrollment_token:
            return JsonResponse({"success": False, "error": "Invalid token payload"}, status=400)
        
        # Step 1: Check if enrollment token exists in database
        try:
            enrollment_token_obj = EnrollmentToken.objects.get(token=enrollment_token)
        except EnrollmentToken.DoesNotExist:
            return JsonResponse({
                "success": False, 
                "error": "Invalid enrollment token"
            }, status=401)
        
        # Step 2: Check if agent_id already exists (re-enrollment)
        try:
            existing_connection = ConnectionTable.objects.filter(agent_id=agent_id).first()
            if existing_connection:
                logger.info(f"Agent {agent_id} is re-enrolling. Deleting old connection {existing_connection.id}")
                # Delete the old connection (cascade will delete associated ApiKeys)
                existing_connection.delete()
        except Exception as e:
            logger.warning(f"Error checking for existing agent_id: {str(e)}")
        
        # Step 3: Create connection in database
        try:
            # Create the connection with specified fields only
            connection = ConnectionTable.objects.create(
                name=host,
                connection_type='AGENT',
                host=host,
                agent_id=agent_id,
                is_active=True,
                policy=enrollment_token_obj.policy
            )
            
            # Step 4: Generate API Key
            raw_api_key = secrets.token_urlsafe(32)
            
            # Create ApiKey object (it will be hashed automatically on save)
            api_key_obj = ApiKey.objects.create(
                connection=connection,
                api_key=raw_api_key
            )
            
            logger.info(f"Agent enrolled successfully with host '{host}', agent_id '{agent_id}', and policy '{enrollment_token_obj.policy.name}'")
            
            # Step 5: Get policy configuration
            policy = enrollment_token_obj.policy
            
            # Step 6: Reply with the API Key and policy configuration
            return JsonResponse({
                "success": True,
                "api_key": raw_api_key,
                "policy_id": policy.id,
                "connection_id": connection.id,
                "policy_config": {
                    "settings_path": policy.settings_path,
                    "logs_path": policy.logs_path,
                    "binary_path": policy.binary_path,
                    "logstash_yml": policy.logstash_yml,
                    "jvm_options": policy.jvm_options,
                    "log4j2_properties": policy.log4j2_properties
                }
            })
            
        except Exception as e:
            logger.error(f"Error creating connection during enrollment: {str(e)}")
            return JsonResponse({"success": False, "error": f"Failed to create connection: {str(e)}"}, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error during enrollment: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
def check_in(request):
    """
    Handle agent check-in requests
    Authenticates via API key and updates last_check_in timestamp
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        # Get API key from Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('ApiKey '):
            return JsonResponse({
                "success": False,
                "error": "Missing or invalid Authorization header. Expected: 'Authorization: ApiKey <key>'"
            }, status=401)
        
        raw_api_key = auth_header[7:]  # Remove 'ApiKey ' prefix
        
        if not raw_api_key:
            return JsonResponse({"success": False, "error": "API key is empty"}, status=401)
        
        # Parse request body
        data = json.loads(request.body)
        connection_id = data.get('connection_id')
        
        if not connection_id:
            return JsonResponse({"success": False, "error": "Missing connection_id"}, status=400)
        
        # Find the connection and verify API key
        try:
            connection = ConnectionTable.objects.get(id=connection_id)
        except ConnectionTable.DoesNotExist:
            return JsonResponse({"success": False, "error": "Invalid connection_id"}, status=401)
        
        # Verify API key
        api_key_obj = connection.api_keys.first()
        if not api_key_obj or not api_key_obj.verify_api_key(raw_api_key):
            return JsonResponse({"success": False, "error": "Invalid API key"}, status=401)
        
        # Update last_check_in timestamp and status_blob
        connection.last_check_in = datetime.now(timezone.utc)
        
        # Extract and store status_blob if provided
        status_blob = data.get('status_blob')
        if status_blob:
            connection.status_blob = status_blob
            logger.debug(f"Updated status_blob: {status_blob}")
        
        connection.save()
        
        # Log the check-in with configuration hashes
        logger.info(f"Agent check-in: connection_id={connection_id}, agent_id={connection.agent_id}")
        logger.debug(f"Check-in data: {data}")
        
        # Get policy configuration
        policy = connection.policy
        if not policy:
            return JsonResponse({
                "success": False,
                "error": "No policy assigned to this connection"
            }, status=400)
        
        # Return current revision number and paths from policy
        return JsonResponse({
            "success": True,
            "message": "Check-in successful",
            "timestamp": connection.last_check_in.isoformat(),
            "current_revision_number": policy.current_revision_number,
            "settings_path": policy.settings_path,
            "logs_path": policy.logs_path,
            "binary_path": policy.binary_path
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error during check-in: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def get_enrollment_tokens(request):
    """
    Get all enrollment tokens for a specific policy.
    """
    try:
        policy_id = request.GET.get('policy_id')
        
        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)
        
        # Get the policy
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)
        
        # Get all enrollment tokens for this policy
        tokens = EnrollmentToken.objects.filter(policy=policy)
        
        # Serialize tokens with encoded payload
        tokens_data = []
        for token in tokens:
            # Create token payload (same as generate_enrollment_token)
            token_payload = {
                "enrollment_token": token.token
            }
            
            # Encode as base64
            json_string = json.dumps(token_payload)
            encoded_token = base64.b64encode(json_string.encode('utf-8')).decode('utf-8')
            
            tokens_data.append({
                "id": token.id,
                "name": token.name,
                "raw_token": token.token,
                "encoded_token": encoded_token
            })
        
        return JsonResponse({
            "success": True,
            "tokens": tokens_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching enrollment tokens: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def add_enrollment_token(request):
    """
    Create a new enrollment token for a policy.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        policy_id = data.get('policy_id')
        token_name = data.get('name', 'default')
        
        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)
        
        # Get the policy
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)
        
        # Generate enrollment token
        enrollment_token = secrets.token_urlsafe(32)
        
        # Create enrollment token record in database
        token = EnrollmentToken.objects.create(
            policy=policy,
            name=token_name,
            token=enrollment_token
        )
        
        logger.info(f"User '{request.user.username}' created enrollment token {token.id} for policy '{policy.name}'")
        
        return JsonResponse({
            "success": True,
            "message": "Enrollment token created successfully",
            "token_id": token.id
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error creating enrollment token: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def delete_enrollment_token(request):
    """
    Delete an enrollment token.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        token_id = data.get('token_id')
        
        if not token_id:
            return JsonResponse({"success": False, "error": "Token ID is required"}, status=400)
        
        # Get and delete the token
        try:
            token = EnrollmentToken.objects.get(id=token_id)
            policy_name = token.policy.name
            token.delete()
            
            logger.info(f"User '{request.user.username}' deleted enrollment token {token_id} for policy '{policy_name}'")
            
            return JsonResponse({
                "success": True,
                "message": "Enrollment token deleted successfully"
            })
            
        except EnrollmentToken.DoesNotExist:
            return JsonResponse({"success": False, "error": "Enrollment token not found"}, status=404)
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error deleting enrollment token: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def get_policy_diff(request):
    """
    Get diff between current policy state and last deployed revision.
    Returns structured diff data for logstash.yml, jvm.options, log4j2.properties, pipelines, and keystore.
    """
    if request.method != 'GET':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        policy_id = request.GET.get('policy_id')
        
        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)
        
        # Get the policy
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)
        
        # Get current policy state
        current_state = {
            'logstash_yml': policy.logstash_yml,
            'jvm_options': policy.jvm_options,
            'log4j2_properties': policy.log4j2_properties,
            'settings_path': policy.settings_path,
            'logs_path': policy.logs_path,
            'binary_path': policy.binary_path,
            'pipelines': list(policy.pipelines.values('name', 'description', 'lscl')),
            'keystore': list(policy.keystore_entries.values('key_name', 'key_value'))
        }
        
        # Get last revision (if any)
        last_revision = policy.revisions.first()  # Already ordered by -revision_number
        
        if last_revision:
            # Compare with last revision
            previous_state = last_revision.snapshot_json
            revision_number = last_revision.revision_number
        else:
            # No previous revision - compare with empty state
            previous_state = {
                'logstash_yml': '',
                'jvm_options': '',
                'log4j2_properties': '',
                'settings_path': '',
                'logs_path': '',
                'binary_path': '',
                'pipelines': [],
                'keystore': []
            }
            revision_number = 0
        
        # Build diff response
        diff_data = {
            'success': True,
            'policy_name': policy.name,
            'current_revision': policy.current_revision_number,
            'last_deployed_revision': revision_number,
            'has_changes': policy.has_undeployed_changes,
            'current': current_state,
            'previous': previous_state
        }
        
        return JsonResponse(diff_data)
        
    except Exception as e:
        logger.error(f"Error getting policy diff: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def deploy_policy(request):
    """
    Deploy a policy by:
    1. Incrementing the revision number in the Policy table
    2. Creating a new Revision record with a snapshot of the current policy state
    3. Keeping the current data in the policy (no changes to policy fields)
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        policy_id = data.get('policy_id')
        
        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)
        
        # Get the policy
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)
        
        # Increment the revision number
        policy.current_revision_number += 1
        new_revision_number = policy.current_revision_number
        
        # Create snapshot of current policy state
        snapshot_data = {
            'logstash_yml': policy.logstash_yml,
            'jvm_options': policy.jvm_options,
            'log4j2_properties': policy.log4j2_properties,
            'settings_path': policy.settings_path,
            'logs_path': policy.logs_path,
            'pipelines': list(policy.pipelines.values('name', 'description', 'lscl')),
            'keystore': list(policy.keystore_entries.values('key_name', 'key_value'))
        }
        
        # Create new Revision record
        revision = Revision.objects.create(
            policy=policy,
            revision_number=new_revision_number,
            snapshot_json=snapshot_data,
            created_by=request.user.username
        )
        
        # Save the policy with updated revision number
        policy.save()
        
        logger.info(f"Policy '{policy.name}' deployed as revision {new_revision_number} by {request.user.username}")
        
        return JsonResponse({
            "success": True,
            "message": f"Policy deployed successfully as version {new_revision_number}",
            "revision_number": new_revision_number,
            "policy_name": policy.name
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error deploying policy: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
def get_config_changes(request):
    """
    Compare agent's current config file hashes and paths with the policy's expected values.
    Returns which configuration files need to be updated.

    Expected request data:
    {
        "connection_id": int,
        "logstash_yml_hash": str,
        "jvm_options_hash": str,
        "log4j2_properties_hash": str,
        "settings_path": str,
        "logs_path": str,
        "keystore": dict,   # {key_name: hash}
        "pipelines": dict   # {pipeline_name: {config_hash: str, settings: {...}}}
    }
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)
    
    try:
        # Parse request data first to get connection_id
        data = json.loads(request.body)
        connection_id = data.get('connection_id')
        
        if not connection_id:
            return JsonResponse({"success": False, "error": "Connection ID is required"}, status=400)
        
        # Authenticate using API key
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('ApiKey '):
            return JsonResponse({"success": False, "error": "Invalid authorization header"}, status=401)
        
        raw_api_key = auth_header.replace('ApiKey ', '').strip()
        
        # Get the connection and verify API key
        try:
            connection = ConnectionTable.objects.get(id=connection_id, connection_type='AGENT')
        except ConnectionTable.DoesNotExist:
            return JsonResponse({"success": False, "error": "Connection not found"}, status=404)
        
        # Verify API key belongs to this connection
        try:
            api_key_obj = connection.api_keys.first()
            if not api_key_obj or not api_key_obj.verify_api_key(raw_api_key):
                return JsonResponse({"success": False, "error": "Invalid API key"}, status=401)
        except Exception as e:
            logger.error(f"API key verification error: {e}")
            return JsonResponse({"success": False, "error": "Authentication failed"}, status=401)
        agent_logstash_yml_hash = data.get('logstash_yml_hash', '')
        agent_jvm_options_hash = data.get('jvm_options_hash', '')
        agent_log4j2_properties_hash = data.get('log4j2_properties_hash', '')
        agent_settings_path = data.get('settings_path', '')
        agent_logs_path = data.get('logs_path', '')
        agent_binary_path = data.get('binary_path', '')
        agent_keystore_password_hash = data.get('keystore_password_hash', '')

        if not connection.policy:
            return JsonResponse({"success": False, "error": "No policy assigned to this connection"}, status=400)
        
        policy = connection.policy
        
        # Compare hashes and paths, and include new values if changed
        changes = {}

        # Check logstash.yml
        if agent_logstash_yml_hash != policy.logstash_yml_hash:
            changes['logstash_yml'] = policy.logstash_yml
        else:
            changes['logstash_yml'] = False

        # Check jvm.options
        if agent_jvm_options_hash != policy.jvm_options_hash:
            changes['jvm_options'] = policy.jvm_options
        else:
            changes['jvm_options'] = False

        # Check log4j2.properties
        if agent_log4j2_properties_hash != policy.log4j2_properties_hash:
            changes['log4j2_properties'] = policy.log4j2_properties
        else:
            changes['log4j2_properties'] = False

        # Check settings_path
        if agent_settings_path != policy.settings_path:
            changes['settings_path'] = policy.settings_path
        else:
            changes['settings_path'] = False

        # Check logs_path
        if agent_logs_path != policy.logs_path:
            changes['logs_path'] = policy.logs_path
        else:
            changes['logs_path'] = False

        # Check binary_path
        if agent_binary_path != policy.binary_path:
            changes['binary_path'] = policy.binary_path
        else:
            changes['binary_path'] = False

        # Check keystore
        agent_keystore = data.get('keystore', {})  # Dict of {key_name: hash}

        # Get policy's keystore entries
        policy_keystore_entries = policy.keystore_entries.all()
        
        # Build policy keystore dict: {key_name: (hash, decrypted_value)}
        policy_keystore = {}
        for entry in policy_keystore_entries:
            policy_keystore[entry.key_name] = {
                'hash': entry.kv_hash,
                'value': entry.get_key_value()
            }
        
        # Determine keystore changes
        keystore_changes = {
            'set': {},
            'delete': []
        }
        
        # Check each agent key against policy
        for agent_key_name, agent_hash in agent_keystore.items():
            if agent_key_name in policy_keystore:
                # Key exists in both - check if hash matches
                if agent_hash != policy_keystore[agent_key_name]['hash']:
                    # Hash differs - encrypt using API key and send updated value
                    plaintext_value = policy_keystore[agent_key_name]['value']
                    encrypted_value = _encrypt_for_agent(raw_api_key, plaintext_value)
                    keystore_changes['set'][agent_key_name] = encrypted_value
            else:
                # Key exists on agent but NOT in policy - delete it
                keystore_changes['delete'].append(agent_key_name)
        
        # Check for new keys in policy that agent doesn't have
        for policy_key_name in policy_keystore.keys():
            if policy_key_name not in agent_keystore:
                # New key - encrypt using API key and send to agent
                plaintext_value = policy_keystore[policy_key_name]['value']
                encrypted_value = _encrypt_for_agent(raw_api_key, plaintext_value)
                keystore_changes['set'][policy_key_name] = encrypted_value

        # Check keystore_password and determine final keystore changes
        if policy.keystore_password and (agent_keystore_password_hash != policy.keystore_password_hash):
            # Password changed (or agent doesn't have it yet) - send encrypted password to agent
            plaintext_password = policy.get_keystore_password()
            changes['keystore_password'] = _encrypt_for_agent(raw_api_key, plaintext_password)
            # Force ALL policy keystore keys to be sent - keystore will be destroyed/recreated on agent
            forced_set = {}
            for policy_key_name, policy_key_data in policy_keystore.items():
                forced_set[policy_key_name] = _encrypt_for_agent(raw_api_key, policy_key_data['value'])
            if forced_set or keystore_changes.get('delete'):
                changes['keystore'] = {'set': forced_set, 'delete': keystore_changes.get('delete', [])}
            else:
                changes['keystore'] = False
        else:
            changes['keystore_password'] = False
            # Only include keystore changes if there are actual changes
            if keystore_changes['set'] or keystore_changes['delete']:
                changes['keystore'] = keystore_changes
            else:
                changes['keystore'] = False

        # Check pipelines
        agent_pipelines = data.get('pipelines', {})  # {name: {config_hash, settings}}
        policy_pipelines_qs = policy.pipelines.all()

        pipeline_changes = {'set': {}, 'delete': []}

        # Agent pipelines not in policy → delete
        for agent_pipeline_name in agent_pipelines:
            if not policy_pipelines_qs.filter(name=agent_pipeline_name).exists():
                pipeline_changes['delete'].append(agent_pipeline_name)

        # Policy pipelines — send if missing on agent or hash differs
        for p in policy_pipelines_qs:
            agent_entry = agent_pipelines.get(p.name)
            needs_update = (
                agent_entry is None or
                agent_entry.get('config_hash') != p.pipeline_hash
            )
            if needs_update:
                pipeline_changes['set'][p.name] = {
                    'lscl': p.lscl,
                    'pipeline_hash': p.pipeline_hash,
                    'settings': {
                        'pipeline_workers': p.pipeline_workers,
                        'pipeline_batch_size': p.pipeline_batch_size,
                        'pipeline_batch_delay': p.pipeline_batch_delay,
                        'queue_type': p.queue_type,
                        'queue_max_bytes': p.queue_max_bytes,
                        'queue_checkpoint_writes': p.queue_checkpoint_writes,
                    }
                }

        changes['pipelines'] = pipeline_changes if (pipeline_changes['set'] or pipeline_changes['delete']) else False

        config_statuses = ", ".join([
            f"logstash_yml={'CHANGED' if changes.get('logstash_yml') else 'unchanged'}",
            f"jvm={'CHANGED' if changes.get('jvm_options') else 'unchanged'}",
            f"log4j2={'CHANGED' if changes.get('log4j2_properties') else 'unchanged'}",
            f"settings_path={'CHANGED' if changes.get('settings_path') else 'unchanged'}",
            f"logs_path={'CHANGED' if changes.get('logs_path') else 'unchanged'}",
            f"binary_path={'CHANGED' if changes.get('binary_path') else 'unchanged'}",
        ])
        ks = changes.get('keystore')
        if ks:
            ks_summary = f"CHANGED (set={list(ks['set'].keys())}, delete={ks['delete']})"
        else:
            ks_summary = "unchanged"
        pl = changes.get('pipelines')
        if pl:
            pl_summary = f"CHANGED (set={list(pl['set'].keys())}, delete={pl['delete']})"
        else:
            pl_summary = "unchanged"
        logger.info(
            f"Config change check conn={connection_id}: [{config_statuses}] "
            f"keystore(agent={len(agent_keystore)}, policy={policy_keystore_entries.count()}, {ks_summary}) "
            f"pipelines(agent={len(agent_pipelines)}, policy={policy_pipelines_qs.count()}, {pl_summary})"
        )

        return JsonResponse({
            "success": True,
            "changes": changes,
            "policy_name": policy.name,
            "current_revision": policy.current_revision_number
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error checking config changes: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def get_keystore_entries(request):
    """
    Get all keystore entries for a specific policy.
    """
    try:
        policy_id = request.GET.get('policy_id')

        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)

        # Get the policy
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

        # Get all keystore entries for this policy
        entries = Keystore.objects.filter(policy=policy)

        # Serialize entries
        entries_data = []
        for entry in entries:
            entries_data.append({
                "id": entry.id,
                "key_name": entry.key_name,
                "key_value": entry.key_value,
                "last_updated": entry.last_updated.isoformat()
            })

        return JsonResponse({
            "success": True,
            "entries": entries_data,
            "has_keystore_password": bool(policy.keystore_password)
        })

    except Exception as e:
        logger.error(f"Error fetching keystore entries: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def set_keystore_password(request):
    """
    Set or update the keystore password for a policy.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        policy_id = data.get('policy_id')
        password = data.get('password')

        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)
        if not password:
            return JsonResponse({"success": False, "error": "Password cannot be empty"}, status=400)

        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

        policy.keystore_password = password  # save() will encrypt and hash it
        policy.has_undeployed_changes = True
        policy.save()

        logger.info(f"User '{request.user.username}' set keystore password for policy '{policy.name}'")

        return JsonResponse({
            "success": True,
            "message": "Keystore password updated successfully"
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error setting keystore password: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def create_keystore_entry(request):
    """
    Create a new keystore entry for a policy.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        policy_id = data.get('policy_id')
        key_name = data.get('key_name')
        key_value = data.get('key_value')

        if not policy_id or not key_name or not key_value:
            return JsonResponse({"success": False, "error": "Policy ID, key name, and key value are required"},
                                status=400)

        # Get the policy
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

        # Check if key already exists for this policy
        if Keystore.objects.filter(policy=policy, key_name=key_name).exists():
            return JsonResponse({"success": False, "error": f"Key '{key_name}' already exists for this policy"},
                                status=400)

        # Create keystore entry
        entry = Keystore.objects.create(
            policy=policy,
            key_name=key_name,
            key_value=key_value
        )

        logger.info(f"User '{request.user.username}' created keystore entry '{key_name}' for policy '{policy.name}'")

        return JsonResponse({
            "success": True,
            "message": f"Keystore entry '{key_name}' created successfully",
            "entry_id": entry.id
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error creating keystore entry: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def update_keystore_entry(request):
    """
    Update an existing keystore entry.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        entry_id = data.get('entry_id')
        key_value = data.get('key_value')

        if not entry_id or not key_value:
            return JsonResponse({"success": False, "error": "Entry ID and key value are required"}, status=400)

        # Get and update the entry
        try:
            entry = Keystore.objects.get(id=entry_id)
            entry.key_value = key_value
            entry.save()

            logger.info(
                f"User '{request.user.username}' updated keystore entry '{entry.key_name}' for policy '{entry.policy.name}'")

            return JsonResponse({
                "success": True,
                "message": f"Keystore entry '{entry.key_name}' updated successfully"
            })

        except Keystore.DoesNotExist:
            return JsonResponse({"success": False, "error": "Keystore entry not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error updating keystore entry: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def delete_keystore_entry(request):
    """
    Delete a keystore entry.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        entry_id = data.get('entry_id')

        if not entry_id:
            return JsonResponse({"success": False, "error": "Entry ID is required"}, status=400)

        # Get and delete the entry
        try:
            entry = Keystore.objects.get(id=entry_id)
            key_name = entry.key_name
            policy_name = entry.policy.name
            entry.delete()

            logger.info(
                f"User '{request.user.username}' deleted keystore entry '{key_name}' for policy '{policy_name}'")

            return JsonResponse({
                "success": True,
                "message": f"Keystore entry '{key_name}' deleted successfully"
            })

        except Keystore.DoesNotExist:
            return JsonResponse({"success": False, "error": "Keystore entry not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error deleting keystore entry: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
