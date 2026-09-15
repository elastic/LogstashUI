#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""HTTP views for the connections page, inspect flyout, and status SSE."""

from django.shortcuts import render
from django.http import HttpResponse, StreamingHttpResponse
from django.db import connections as db_connections

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


def _logstash_yml_cpm_enabled(yml):
    """True when ``logstash.yml`` enables Centralized Pipeline Management.

    Logstash accepts both flat dotted keys and nested YAML for
    ``xpack.management.enabled``, so YAML is parsed and flattened to dotted
    keys. Falls back to a whitespace-tolerant string match if the YAML
    cannot be parsed.

    Args:
        yml: Policy ``logstash_yml`` text.
    """
    if not yml:
        return False

    try:
        import yaml

        data = yaml.safe_load(yml)
        if isinstance(data, dict):
            flat = {}

            def _flatten(prefix, obj):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        _flatten(f"{prefix}{key}.", value)
                else:
                    flat[prefix[:-1]] = obj

            _flatten('', data)
            value = flat.get('xpack.management.enabled')
            if value is not None:
                return str(value).strip().lower() == 'true'
    except Exception:
        pass

    normalized = yml.lower().replace(' ', '').replace('\t', '')
    return 'xpack.management.enabled:true' in normalized


@require_admin_role
def AgentPolicies(request):
    """Render the Agent Policies management page."""
    context = {}
    return render(request, "components/pipeline_manager/agent_policies.html", context=context)


def PipelineManager(request):
    """Render the connections page shell.

    The connection rows are loaded asynchronously by ``connections_table.js``
    via :func:`~PipelineManager.connections_crud.GetConnectionsTable`.
    This view only needs to know whether *any* connections exist so it can
    choose between the empty-state and the table shell.
    """
    # Refresh sticky embedded row in the background (probe is blocking; daemon
    # thread keeps page render fast and SSE picks up result shortly after).
    try:
        from PipelineManager.agent_modes import (
            is_embedded_connection,
            refresh_embedded_connection_async,
        )
        refresh_embedded_connection_async()
    except Exception:
        pass

    try:
        from PipelineManager.agent_modes import is_embedded_connection

        has_connections = any(
            not is_embedded_connection(c)
            for c in ConnectionTable.objects.values(
                'connection_type', 'agent_id', 'policy__policy_type'
            )
        )
    except Exception:
        has_connections = ConnectionTable.objects.exists()

    return render(request, "pipeline_manager.html", {
        'has_connections': has_connections,
        'form': ConnectionForm(),
        'preferred_agent_version': settings.__PREFERRED_LS_AGENT_VERSION__,
    })

def test_connectivity(connection_id):
    """Test connectivity to an Elasticsearch connection.

    Args:
        connection_id: ``Connection`` primary key.

    Returns:
        ``(success, message)`` where ``message`` is cluster info JSON or an
        error string.
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
    """Test Elasticsearch connectivity and return an htmx HTML snippet.

    Args:
        test: Connection pk.
    """
    test_id = request.GET.get('test')
    
    if not test_id:
        return HttpResponse("No connection ID provided", status=400)
    
    logger.info(f"User '{request.user.username}' testing connection {test_id}")
    success, message = test_connectivity(test_id)
    
    if success:
        # Check if this is a serverless instance
        is_serverless = False
        try:
            info = json.loads(message)
            is_serverless = info.get('name') == 'serverless'
        except (json.JSONDecodeError, AttributeError):
            pass
        
        # Return response with HX-Trigger to update the type column if serverless
        response = HttpResponse("""
            <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg"
                onload="setTimeout(() => this.remove(), 3000);">
                <p>{0}</p>
            </div>
        """.format(escape(str(message))))
        
        if is_serverless:
            response['HX-Trigger'] = json.dumps({"serverlessDetected": {"connectionId": test_id}})
        
        return response
    else:
        return HttpResponse("""
            <div class="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg">
                <p>Connection failed: {0}</p>
            </div>
        """.format(escape(str(message))))




def _normalize_status_blob_api_status(blob):
    """Surface the authoritative Logstash status on a status blob.

    The Logstash node-info root (``GET /``) aggregates all health indicators
    and frequently reports ``status="unknown"`` even when the instance is
    perfectly healthy (e.g. immediately after a pipeline reload). The agent
    also polls the dedicated ``/_health_report`` endpoint, which is the
    authoritative source of the node's status.

    The inspect card hides API details, the health report, and node stats
    whenever ``logstash_api.status == 'unknown'``, so a root status of
    "unknown" leaves the card stuck on the "status hasn't been read yet"
    warmup message — hiding data the agent already collected. When the root
    status is unknown but the health report has a real status, adopt it so
    the full details render.

    Mutates the given ``blob`` dict in place (the caller's in-memory copy
    only; never persisted).

    Args:
        blob: Agent ``status_blob`` dict, or a falsey value (no-op).
    """
    if not blob:
        return
    logstash_api = blob.get('logstash_api') or {}

    if not logstash_api.get('accessible'):
        return
    if logstash_api.get('status') not in (None, 'unknown'):
        return

    health = blob.get('health_report') or {}
    health_status = health.get('status')
    if health.get('accessible') and health_status and health_status != 'unknown':
        logstash_api['status'] = health_status
        blob['logstash_api'] = logstash_api


def _normalize_logstash_api_status(connection):
    """Normalize the Logstash API status on a ``Connection`` instance's blob.

    Args:
        connection: Agent ``Connection`` whose in-memory ``status_blob`` is
            rewritten.
    """
    blob = connection.status_blob or {}
    _normalize_status_blob_api_status(blob)
    connection.status_blob = blob


@require_admin_role
def get_agent_inspect(request, connection_id):
    """Return fresh HTML for the agent inspect flyout.

    Called via ``fetch()`` each time the user opens the flyout so the data
    is never stale.

    Args:
        connection_id: Agent ``Connection`` primary key.
    """
    try:
        connection = ConnectionTable.objects.select_related('policy').get(
            pk=connection_id,
            connection_type=ConnectionTable.ConnectionType.AGENT,
        )
    except ConnectionTable.DoesNotExist:
        return HttpResponse('Agent not found', status=404)

    # Embedded never check-ins; re-probe when inspecting
    try:
        from PipelineManager.agent_modes import ensure_embedded_connection, is_embedded_connection

        if is_embedded_connection(connection):
            ensure_embedded_connection()
            connection.refresh_from_db()
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    if connection.last_check_in:
        connection.is_online = (now - connection.last_check_in).total_seconds() < 600
    else:
        connection.is_online = False

    _normalize_logstash_api_status(connection)

    return render(
        request,
        'components/pipeline_manager/agent_inspect_content.html',
        {'connection': connection},
    )


@require_admin_role
def agent_status_stream(request):
    """Stream agent status for all agent connections every 5 seconds (SSE).

    Each event is a JSON array of objects ``{id, name, status,
    logstash_version}`` where status is one of ``restarting``,
    ``unhealthy``, ``healthy``, or ``offline``, and ``logstash_version`` is
    the running Logstash version or null.

    This mirrors the priority logic in ``pipeline_manager.html`` so the JS
    can update badges without a full page reload.

    Note:
        Under standard WSGI each open SSE connection holds one server
        thread. Fine for small internal deployments; move to ASGI/Channels
        if scale becomes a concern.
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
                # Keep embedded last_check_in fresh while the Connections page is open
                try:
                    from PipelineManager.agent_modes import ensure_embedded_connection

                    ensure_embedded_connection()
                except Exception:
                    pass

                now = datetime.now(timezone.utc)
                from PipelineManager.agent_modes import is_embedded_connection
                from PipelineManager.agent_versions import (
                    resolve_running_logstash_version,
                )

                connections = [
                    conn
                    for conn in ConnectionTable.objects
                    .filter(connection_type=ConnectionTable.ConnectionType.AGENT)
                    .values('pk', 'name', 'last_check_in', 'status_blob', 'agent_id',
                            'policy__policy_type', 'logstash_version_resolved')
                    if not is_embedded_connection(conn)
                ]

                for conn in connections:
                    if conn['last_check_in']:
                        conn['is_online'] = (now - conn['last_check_in']).total_seconds() < 600
                    else:
                        conn['is_online'] = False

                # status_blob is already selected for _compute_status, so the
                # version rides along for free and the LS pill stops needing a
                # page reload to notice a Logstash upgrade.
                payload = json.dumps([
                    {
                        'id': conn['pk'],
                        'name': conn['name'],
                        'status': _compute_status(conn),
                        'logstash_version': resolve_running_logstash_version(
                            logstash_version_resolved=conn.get('logstash_version_resolved'),
                            status_blob=conn.get('status_blob')
                            if isinstance(conn.get('status_blob'), dict) else None,
                        ),
                    }
                    for conn in connections
                ])
                # Return pool slots before the stream waits for its next event.
                db_connections.close_all()
                yield f"data: {payload}\n\n"
                time.sleep(5)
        except GeneratorExit:
            pass
        finally:
            db_connections.close_all()

    response = StreamingHttpResponse(_event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'   # prevent nginx from buffering the stream
    return response


