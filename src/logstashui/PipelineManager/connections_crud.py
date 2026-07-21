#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.template.loader import get_template
from django.db import transaction

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
def GetConnection(request, connection_id):
    """
    Return connection details (excluding credentials) for pre-filling the edit modal.
    Only supports CENTRALIZED connections.
    """
    if request.method != "GET":
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    connection = ConnectionTable.objects.filter(id=connection_id).first()
    if not connection:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)

    if connection.connection_type != ConnectionTable.ConnectionType.CENTRALIZED:
        return JsonResponse({'success': False, 'error': 'Only centralized connections can be edited via this endpoint'}, status=400)

    auth_type = 'apiKey' if connection.api_key else 'basic'

    return JsonResponse({
        'success': True,
        'connection': {
            'id': connection.id,
            'name': connection.name,
            'connection_mode': 'cloud' if connection.cloud_id else 'url',
            'cloud_id': connection.cloud_id or '',
            'host': connection.host or '',
            'port': connection.port or '',
            'auth_type': auth_type,
            'username': connection.username or '',
        }
    })


@require_admin_role
def UpdateConnection(request, connection_id):
    """
    Update an existing CENTRALIZED connection.
    Credentials must be re-supplied — they are tested before the change is committed.
    On connectivity test failure the database record is rolled back.
    """
    if request.method != "POST":
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    connection = ConnectionTable.objects.filter(id=connection_id).first()
    if not connection:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)

    if connection.connection_type != ConnectionTable.ConnectionType.CENTRALIZED:
        return JsonResponse({'success': False, 'error': 'Only centralized connections can be edited'}, status=400)

    # Enforce credential re-entry
    auth_type = request.POST.get('auth_type', 'basic')
    if auth_type == 'basic':
        if not request.POST.get('password', '').strip():
            return JsonResponse({'success': False, 'error': 'Password is required when updating a connection'}, status=200)
    else:
        if not request.POST.get('api_key', '').strip():
            return JsonResponse({'success': False, 'error': 'API Key is required when updating a connection'}, status=200)

    # Clear the opposing credential on the instance before form binding so that
    # ConnectionForm.save()'s "keep existing if empty" logic doesn't silently
    # preserve a stale credential from the previous auth type.
    if auth_type == 'basic':
        connection.api_key = None
    else:
        connection.username = None
        connection.password = None

    form = ConnectionForm(request.POST, instance=connection)
    if not form.is_valid():
        logger.warning(f"User '{request.user.username}' submitted invalid update for connection {connection_id}: {form.errors}")
        return JsonResponse({'success': False, 'error': str(form.errors)}, status=200)

    test_success = False
    test_message = ""
    try:
        with transaction.atomic():
            updated_connection = form.save()
            test_success, test_message = manager_views.test_connectivity(updated_connection.id)
            if not test_success:
                transaction.set_rollback(True)
    except Exception as e:
        logger.error(f"User '{request.user.username}' encountered error updating connection {connection_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=200)

    if not test_success:
        logger.warning(f"User '{request.user.username}' failed connectivity test when updating connection {connection_id}")
        return JsonResponse({'success': False, 'error': str(test_message)}, status=200)

    logger.info(f"User '{request.user.username}' updated connection {connection_id}")
    return JsonResponse({
        'success': True,
        'connection_id': connection_id,
        'message': 'Connection updated and tested successfully!'
    }, status=200)


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

                # Infer SNMP management for centralized pipelines from the
                # naming convention + [MANAGED] tag (no managed_by column in ES).
                description = pipeline_data.get("description", "")
                inferred_managed_by = (
                    'snmp'
                    if pipeline_name.startswith('snmp-') and '[MANAGED]' in description
                    else 'user'
                )

                logstash_pipelines.append(
                    {
                        "es_id": connection.id,
                        "es_name": connection.name,
                        "name": pipeline_name,
                        "description": description,
                        "last_modified": formatted_date,
                        "managed_by": inferred_managed_by,
                    }
                )

        except Exception as e:
            logger.exception("Couldn't connect to Elastic")

    else:  # AGENT connection type
        # Fetch pipelines from the associated policy for agent connections.
        #
        # An agent hosts (a) every user-authored pipeline on its base policy,
        # shared across all agents on that policy, plus (b) ONLY the SNMP
        # pipelines belonging to networks assigned to THIS specific agent.
        # SNMP pipelines for sibling agents on the same policy are excluded so
        # each agent sees exactly what it will actually run.
        if connection.policy:
            from django.db.models import Q
            from SNMP.snmp_crud import agent_snmp_pipeline_names

            own_snmp_names = agent_snmp_pipeline_names(connection)
            pipelines = Pipeline.objects.filter(policy=connection.policy).filter(
                Q(managed_by='user') | Q(managed_by='snmp', name__in=own_snmp_names)
            ).values(
                'id', 'name', 'description', 'last_updated', 'managed_by'
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
                    "policy_id": connection.policy.id,  # Add policy_id to each pipeline for delete/clone
                    "managed_by": p['managed_by'],
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

        # The policy tab lists user-authored pipelines only. SNMP/managed
        # pipelines are surfaced per-agent on the Connections page, never here.
        pipelines = Pipeline.objects.filter(policy=policy, managed_by='user').values(
            'id', 'name', 'description', 'last_updated', 'managed_by'
        )

        pipelines_list = []
        for p in pipelines:
            pipelines_list.append({
                'id': p['id'],
                'name': p['name'],
                'description': p['description'] or '',
                'last_modified': p['last_updated'].strftime('%Y-%m-%d %H:%M:%S') if p['last_updated'] else 'N/A',
                'es_id': policy_id,  # Use policy_id as es_id for compatibility with frontend
                'policy_id': policy_id,  # Tells pipeline_list.js to use ls_id= in the editor URL
                'managed_by': p['managed_by'],
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

