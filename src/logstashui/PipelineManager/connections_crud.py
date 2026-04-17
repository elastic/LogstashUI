#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.template.loader import get_template

from PipelineManager.models import Connection as ConnectionTable, Policy, Pipeline

from .forms import ConnectionForm

from Common.decorators import require_admin_role
from Common.elastic_utils import get_elastic_connection

from . import manager_views

from datetime import datetime

import logging

logger = logging.getLogger(__name__)

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
            success, message = manager_views.test_connectivity(new_connection.id)

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


@require_admin_role
def UpgradeAgent(request, connection_id=None):
    """Set desired agent version to trigger upgrade on next check-in"""
    if request.method != "POST":
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    if not connection_id:
        return JsonResponse({'success': False, 'error': 'Connection ID is required'}, status=400)

    connection = ConnectionTable.objects.filter(id=connection_id).first()
    if not connection:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)

    if connection.connection_type != 'AGENT':
        return JsonResponse({'success': False, 'error': 'Only agent connections can be upgraded'}, status=400)

    # Set desired version to the preferred version from settings
    connection.desired_agent_version = settings.__PREFERRED_LS_AGENT_VERSION__
    connection.save(update_fields=['desired_agent_version'])

    logger.info(
        f"User '{request.user.username}' requested upgrade for agent '{connection.name}' (ID: {connection_id}) "
        f"to version {settings.__PREFERRED_LS_AGENT_VERSION__}"
    )

    return JsonResponse({
        'success': True,
        'message': f'Agent will upgrade to v{settings.__PREFERRED_LS_AGENT_VERSION__} on next check-in'
    })

@require_admin_role
def change_connection_policy(request):
    """
    Change the policy assigned to an agent connection
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    connection_id = request.POST.get('connection_id')
    policy_id = request.POST.get('policy_id')

    connection = ConnectionTable.objects.filter(
        id=connection_id, connection_type=ConnectionTable.ConnectionType.AGENT
    ).first()
    if not connection:
        return JsonResponse({"success": False, "error": "Agent connection not found"}, status=404)

    policy = Policy.objects.filter(id=policy_id).first()
    if not policy:
        return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

    old_policy_name = connection.policy.name if connection.policy else "None"
    connection.policy = policy
    connection.save()
    logger.info(
        f"User '{request.user.username}' changed policy of connection '{connection.name}' "
        f"from '{old_policy_name}' to '{policy.name}'"
    )

    return JsonResponse({"success": True})


@require_admin_role
def restart_logstash(request):
    """
    Set restart_on_next_checkin on an agent connection so the agent restarts Logstash on its next check-in.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    connection_id = request.POST.get('connection_id')

    connection = ConnectionTable.objects.filter(
        id=connection_id, connection_type=ConnectionTable.ConnectionType.AGENT
    ).first()
    if not connection:
        return JsonResponse({"success": False, "error": "Agent connection not found"}, status=404)

    connection.restart_on_next_checkin = True
    connection.save()
    logger.info(
        f"User '{request.user.username}' queued a Logstash restart for connection '{connection.name}' (ID: {connection_id})"
    )

    return JsonResponse({"success": True})


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

