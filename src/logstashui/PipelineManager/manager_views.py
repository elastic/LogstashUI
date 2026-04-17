#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from django.http import HttpResponse, StreamingHttpResponse

from django.conf import settings

from .forms import ConnectionForm
from PipelineManager.models import Connection as ConnectionTable

from Common.decorators import require_admin_role

from Common.elastic_utils import get_elastic_connection, test_elastic_connectivity


from datetime import datetime, timezone
from html import escape

import logging
import json

import time

logger = logging.getLogger(__name__)


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
    connections = list(ConnectionTable.objects.values("connection_type", "name", "host", "cloud_id", "cloud_url", "pk", "policy__name", "policy_id", "last_check_in", "status_blob", "desired_agent_version"))
    
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
    context['preferred_agent_version'] = settings.__PREFERRED_LS_AGENT_VERSION__

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




@require_admin_role
def get_agent_inspect(request, connection_id):
    """
    Return fresh rendered HTML for the agent inspect modal.

    Called via fetch() each time the user opens the flyout so the data is
    never stale. Renders agent_inspect_content.html with a live DB query.
    """
    try:
        connection = ConnectionTable.objects.select_related('policy').get(
            pk=connection_id,
            connection_type=ConnectionTable.ConnectionType.AGENT,
        )
    except ConnectionTable.DoesNotExist:
        return HttpResponse('Agent not found', status=404)

    now = datetime.now(timezone.utc)
    if connection.last_check_in:
        connection.is_online = (now - connection.last_check_in).total_seconds() < 600
    else:
        connection.is_online = False

    return render(
        request,
        'components/pipeline_manager/agent_inspect_content.html',
        {'connection': connection},
    )


@require_admin_role
def agent_status_stream(request):
    """
    SSE endpoint — streams agent status for all agent connections every 5 seconds.

    Each event is a JSON array of objects: {id, name, status}
    where status is one of: 'restarting' | 'unhealthy' | 'healthy' | 'offline'

    This mirrors the priority logic in the pipeline_manager.html template so the
    JS can update badges without a full page reload.

    NOTE: Under standard WSGI each open SSE connection holds one server thread.
    This is fine for small internal deployments. Move to ASGI/Channels if scale
    becomes a concern.
    """
    def _compute_status(conn):
        blob = conn.get('status_blob') or {}
        logwatcher = blob.get('logwatcher') or {}

        if logwatcher.get('is_restarting'):
            return 'restarting'

        # Check offline status before unhealthy - takes priority
        if not conn.get('is_online'):
            return 'offline'

        if blob:
            logstash_api  = blob.get('logstash_api')  or {}
            health_report = blob.get('health_report') or {}
            last_policy   = blob.get('last_policy_apply') or {}

            if (blob.get('settings_path_found') is False or
                blob.get('logs_path_found')     is False or
                blob.get('binary_path_found')   is False or
                logstash_api.get('accessible')  is False or
                logstash_api.get('status')      == 'red' or
                last_policy.get('success')      is False or
                health_report.get('status')     in ('yellow', 'red')):
                return 'unhealthy'

        return 'healthy'

    def _event_stream():
        try:
            while True:
                now = datetime.now(timezone.utc)
                connections = list(
                    ConnectionTable.objects
                    .filter(connection_type=ConnectionTable.ConnectionType.AGENT)
                    .values('pk', 'name', 'last_check_in', 'status_blob')
                )

                for conn in connections:
                    if conn['last_check_in']:
                        conn['is_online'] = (now - conn['last_check_in']).total_seconds() < 600
                    else:
                        conn['is_online'] = False

                payload = json.dumps([
                    {'id': conn['pk'], 'name': conn['name'], 'status': _compute_status(conn)}
                    for conn in connections
                ])
                yield f"data: {payload}\n\n"
                time.sleep(5)
        except GeneratorExit:
            pass

    response = StreamingHttpResponse(_event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'   # prevent nginx from buffering the stream
    return response



