#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""REST API views for Connection management.

Endpoints
---------
GET    /api/connections/              list_connections
POST   /api/connections/              list_connections
GET    /api/connections/{id}/         connection_detail
PUT    /api/connections/{id}/         connection_detail
DELETE /api/connections/{id}/         connection_detail
POST   /api/connections/{id}/test/    connection_test
"""

import logging

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from PipelineManager.models import Connection
from PipelineManager.forms import ConnectionForm
from PipelineManager import manager_views
from PipelineManager.agent_modes import is_embedded_connection

from API.auth import api_require_auth, api_require_admin, parse_request_body

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _safe_connection_data(conn):
    """Serialize a Connection to a dict safe for API responses.

    Credentials (password, ssh_key, api_key) are never included.

    Args:
        conn: A ``Connection`` model instance.

    Returns:
        dict with all non-sensitive fields.
    """
    return {
        'id': conn.id,
        'name': conn.name,
        'connection_type': conn.connection_type,
        'agent_id': conn.agent_id,
        'host': conn.host,
        'port': conn.port,
        'username': conn.username,
        'cloud_id': conn.cloud_id,
        'cloud_url': conn.cloud_url,
        'policy_id': conn.policy_id,
        'is_active': conn.is_active,
        'last_check_in': conn.last_check_in.isoformat() if conn.last_check_in else None,
        'created_at': conn.created_at.isoformat(),
        'updated_at': conn.updated_at.isoformat(),
        'desired_agent_version': conn.desired_agent_version,
        'restart_on_next_checkin': conn.restart_on_next_checkin,
    }


# ---------------------------------------------------------------------------
# /api/connections/  — list + create
# ---------------------------------------------------------------------------

@csrf_exempt
def connection_list(request):
    """List all connections or create a new one.

    GET  /api/connections/
        Returns a JSON array of all non-embedded connections.  Safe for any
        authenticated user (no admin role required).

    POST /api/connections/
        Create a connection.  Connectivity is tested immediately after save;
        the row is deleted and a 422 returned on test failure.
        Requires admin role.
    """
    if request.method == 'GET':
        return _list_connections(request)
    if request.method == 'POST':
        return _create_connection(request)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _list_connections(request):
    connections_qs = Connection.objects.values(
        'id', 'name', 'connection_type', 'agent_id',
        'policy__policy_type', 'host', 'port', 'username',
        'cloud_id', 'cloud_url', 'is_active',
        'last_check_in', 'created_at', 'updated_at',
        'desired_agent_version', 'restart_on_next_checkin',
        'policy_id',
    )
    connections = [c for c in connections_qs if not is_embedded_connection(c)]

    # Normalize datetime fields to ISO strings
    for c in connections:
        for field in ('last_check_in', 'created_at', 'updated_at'):
            val = c.get(field)
            c[field] = val.isoformat() if val else None

    return JsonResponse(connections, safe=False, status=200)


@api_require_admin
def _create_connection(request):
    data = parse_request_body(request)

    # Bug 1 fix: enforce unique name before saving
    name = (data.get('name') or '').strip()
    if name and Connection.objects.filter(name=name).exists():
        return JsonResponse(
            {'success': False, 'error': f"A connection named '{name}' already exists."},
            status=409,
        )

    form = ConnectionForm(data)

    if not form.is_valid():
        logger.warning("API create connection: invalid form — %s", form.errors)
        return JsonResponse({'success': False, 'error': form.errors}, status=400)

    new_connection = form.save()

    success, message = manager_views.test_connectivity(new_connection.id)
    if not success:
        new_connection.delete()
        logger.error("API create connection: connectivity test failed — %s", message)
        return JsonResponse({'success': False, 'error': str(message)}, status=422)

    logger.info("API: connection %s created by %s", new_connection.id, request.user.username)
    return JsonResponse({
        'success': True,
        'connection_id': new_connection.id,
        'message': 'Connection created and tested successfully.',
    }, status=201)


# ---------------------------------------------------------------------------
# /api/connections/<id>/  — read, update, delete
# ---------------------------------------------------------------------------

@csrf_exempt
def connection_detail(request, connection_id):
    """Retrieve, update, or delete a single connection.

    GET    /api/connections/{id}/   — return safe fields; any authenticated user.
    PUT    /api/connections/{id}/   — update; admin role required.
    DELETE /api/connections/{id}/   — delete; admin role required.
    """
    if request.method == 'GET':
        return _get_connection(request, connection_id)
    if request.method == 'PUT':
        return _update_connection(request, connection_id)
    if request.method == 'DELETE':
        return _delete_connection(request, connection_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _get_connection(request, connection_id):
    conn = Connection.objects.filter(id=connection_id).first()
    if not conn:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)
    return JsonResponse({'success': True, 'connection': _safe_connection_data(conn)})


def _connection_form_defaults(conn):
    """Build a form-data dict from an existing Connection for partial-update support.

    Infers the current ``connection_mode`` and ``auth_type`` radio values from the
    stored connection so that the form's ``clean()`` branches correctly and does not
    zero out whichever credential field is already stored.

    Sensitive fields (``api_key``, ``password``) are deliberately omitted from the
    returned dict.  The form's ``save()`` treats an empty value as "keep existing",
    so callers only need to supply the fields they actually want to change.
    """
    # Infer connection_mode (cloud vs url)
    connection_mode = 'cloud' if conn.cloud_id else 'url'

    # Infer auth_type so clean() doesn't zero the wrong credential field.
    # The fields are stored encrypted, so a non-empty string means "has a key".
    if conn.connection_type == Connection.ConnectionType.AGENT:
        auth_type = 'apiKey'          # AGENT always uses api_key table; basic unused
    elif conn.api_key:
        auth_type = 'apiKey'
    else:
        auth_type = 'basic'

    return {
        'name':            conn.name,
        'connection_type': conn.connection_type,
        'host':            conn.host or '',
        'port':            conn.port or '',
        'username':        conn.username or '',
        'cloud_id':        conn.cloud_id or '',
        'cloud_url':       conn.cloud_url or '',
        # Include radio-button values so the form's clean() zeros the correct
        # opposing fields and does NOT zero the credential field we're keeping.
        'connection_mode': connection_mode,
        'auth_type':       auth_type,
        # api_key / password deliberately omitted: empty string → keep existing
    }


@api_require_admin
def _update_connection(request, connection_id):
    conn = Connection.objects.filter(id=connection_id).first()
    if not conn:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)

    data = parse_request_body(request)

    # Bug 2 fix: support partial PUT by merging existing values as form defaults.
    # The caller only needs to supply the fields they want to change; omitted
    # fields retain their current values.
    merged = _connection_form_defaults(conn)
    merged.update(data)

    # Bug 1 fix (update path): check for name collision against other connections.
    new_name = (merged.get('name') or '').strip()
    if new_name and new_name != conn.name and Connection.objects.filter(name=new_name).exists():
        return JsonResponse(
            {'success': False, 'error': f"A connection named '{new_name}' already exists."},
            status=409,
        )

    form = ConnectionForm(merged, instance=conn)

    if not form.is_valid():
        logger.warning("API update connection %s: invalid form — %s", connection_id, form.errors)
        return JsonResponse({'success': False, 'error': form.errors}, status=400)

    test_success = False
    test_message = ''
    try:
        with transaction.atomic():
            updated = form.save()
            test_success, test_message = manager_views.test_connectivity(updated.id)
            if not test_success:
                transaction.set_rollback(True)
    except Exception as exc:
        logger.error("API update connection %s: exception — %s", connection_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    if not test_success:
        logger.warning("API update connection %s: connectivity test failed — %s", connection_id, test_message)
        return JsonResponse({'success': False, 'error': str(test_message)}, status=422)

    logger.info("API: connection %s updated by %s", connection_id, request.user.username)
    return JsonResponse({
        'success': True,
        'connection_id': connection_id,
        'message': 'Connection updated and tested successfully.',
    })


@api_require_admin
def _delete_connection(request, connection_id):
    conn = Connection.objects.filter(id=connection_id).first()
    if not conn:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)

    name = conn.name
    conn.delete()
    logger.warning("API: connection '%s' (ID: %s) deleted by %s", name, connection_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Connection '{name}' deleted."}, status=200)


# ---------------------------------------------------------------------------
# /api/connections/<id>/test/  — live connectivity check
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_auth
def connection_test(request, connection_id):
    """Test connectivity to an existing connection.

    POST /api/connections/{id}/test/
        Runs a live connectivity check against the stored connection and
        returns the cluster info on success or an error message on failure.
        No data is modified.  Requires any authenticated user (not admin-only
        — same rule as the browser UI test button).

    Args:
        connection_id: ``Connection`` primary key.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    conn = Connection.objects.filter(id=connection_id).first()
    if not conn:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)

    logger.info("API: connectivity test for connection %s by %s", connection_id, request.user.username)
    success, message = manager_views.test_connectivity(connection_id)

    if success:
        return JsonResponse({'success': True, 'detail': message})
    return JsonResponse({'success': False, 'error': str(message)}, status=422)
