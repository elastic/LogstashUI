#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .forms import ConnectionForm
from PipelineManager.models import Connection as ConnectionTable, Policy, EnrollmentToken, ApiKey, Revision

from Common.decorators import require_admin_role
from Common.logstash_utils import get_logstash_pipeline
from Common.elastic_utils import get_elastic_connection, test_elastic_connectivity
from Common.validators import validate_pipeline_name

from datetime import datetime, timedelta
from html import escape

import logging
import json
import base64
import secrets
import requests
import os

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
    connections = list(ConnectionTable.objects.values("connection_type", "name", "host", "cloud_id", "cloud_url", "pk", "policy__name"))
    
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
            logger.error(f"Error updating pipeline settings: {str(e)}")
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
        # Handle both JSON and form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            es_id = data.get("es_id")
            pipeline_name = data.get("pipeline")
        else:
            es_id = request.POST.get("es_id")
            pipeline_name = request.POST.get("pipeline")

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        es = get_elastic_connection(es_id)
        es.logstash.delete_pipeline(id=pipeline_name)

        logger.warning(f"User '{request.user.username}' deleted pipeline '{pipeline_name}' (Connection ID: {es_id})")
        return HttpResponse(status=204)  # No content - prevents text from being inserted into page


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
                    htmx.ajax('GET', '/ConnectionManager/GetPipelines/""" + escape(str(es_id)) + """/', 
                              {target: '#pipelines-""" + escape(str(es_id)) + """', swap: 'innerHTML'});
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
            'id', 'name', 'settings_path', 'logs_path', 
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
    Token contains: enrollment token only (LogstashUI URL provided via command-line)
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
        
        # Update last_check_in timestamp

        connection.last_check_in = timezone.now()
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
            "logs_path": policy.logs_path
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
        "logs_path": str
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
        
        if not connection.policy:
            return JsonResponse({"success": False, "error": "No policy assigned to this connection"}, status=400)
        
        policy = connection.policy
        
        # Log what we're comparing
        logger.info(f"Config change check for connection {connection_id}:")
        logger.info(f"  Agent hashes: logstash_yml={agent_logstash_yml_hash}, jvm={agent_jvm_options_hash}, log4j2={agent_log4j2_properties_hash}")
        logger.info(f"  Policy hashes: logstash_yml={policy.logstash_yml_hash}, jvm={policy.jvm_options_hash}, log4j2={policy.log4j2_properties_hash}")
        
        # Compare hashes and paths, and include new values if changed
        changes = {}
        
        # Check logstash.yml
        if agent_logstash_yml_hash != policy.logstash_yml_hash:
            changes['logstash_yml'] = policy.logstash_yml
            logger.info(f"  logstash.yml: CHANGED")
        else:
            changes['logstash_yml'] = False
            logger.info(f"  logstash.yml: unchanged")
        
        # Check jvm.options
        if agent_jvm_options_hash != policy.jvm_options_hash:
            changes['jvm_options'] = policy.jvm_options
            logger.info(f"  jvm.options: CHANGED")
        else:
            changes['jvm_options'] = False
            logger.info(f"  jvm.options: unchanged")
        
        # Check log4j2.properties
        if agent_log4j2_properties_hash != policy.log4j2_properties_hash:
            changes['log4j2_properties'] = policy.log4j2_properties
            logger.info(f"  log4j2.properties: CHANGED")
        else:
            changes['log4j2_properties'] = False
            logger.info(f"  log4j2.properties: unchanged")
        
        # Check settings_path
        if agent_settings_path != policy.settings_path:
            changes['settings_path'] = policy.settings_path
            logger.info(f"  settings_path: CHANGED")
        else:
            changes['settings_path'] = False
            logger.info(f"  settings_path: unchanged")
        
        # Check logs_path
        if agent_logs_path != policy.logs_path:
            changes['logs_path'] = policy.logs_path
            logger.info(f"  logs_path: CHANGED")
        else:
            changes['logs_path'] = False
            logger.info(f"  logs_path: unchanged")
        
        logger.info(f"Config change check for connection {connection_id} completed")
        
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
