#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""REST API views for LogstashUI.

Authentication
--------------
All mutating endpoints (POST, PUT, DELETE) require an admin-role user.
Callers supply ``Authorization: ApiKey <token>`` which is resolved by
``Common.middleware.ApiTokenCsrfMiddleware`` / ``ApiTokenUserMiddleware``
before the view runs.  In NO_AUTH_MODE the middleware injects a user
automatically, so no token is needed.

Read endpoints (GET) are open to any authenticated user — the same rule as
the browser UI list views.
"""

import json
import logging
from functools import wraps

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from PipelineManager.models import Connection
from PipelineManager.forms import ConnectionForm
from PipelineManager import manager_views
from PipelineManager.agent_modes import is_embedded_connection

logger = logging.getLogger(__name__)


def _api_require_auth(view_func):
    """Return 401 JSON for unauthenticated callers.

    Placed before mutating decorators so that missing credentials produce a
    401 (not a 403 or an htmx HTML response).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'success': False, 'error': 'Authentication required. Provide Authorization: ApiKey <token>.'},
                status=401,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def _api_require_admin(view_func):
    """Return 401/403 JSON for callers without an admin role.

    Stacks on top of ``_api_require_auth``: unauthenticated → 401,
    authenticated-but-not-admin → 403.  Always JSON — no htmx toasts.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'success': False, 'error': 'Authentication required. Provide Authorization: ApiKey <token>.'},
                status=401,
            )
        if not hasattr(request.user, 'profile') or request.user.profile.role != 'admin':
            logger.warning(
                "API: user '%s' attempted admin operation without admin role: %s",
                request.user.username, view_func.__name__,
            )
            return JsonResponse(
                {'success': False, 'error': 'Access denied: Admin role required.'},
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Helpers
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


def _parse_body(request):
    """Return request data as a plain dict.

    Accepts JSON body (``Content-Type: application/json``) or falls back to
    ``request.POST`` for form-encoded submissions.

    Args:
        request: Django request object.

    Returns:
        dict of submitted data, or an empty dict on parse failure.
    """
    content_type = request.content_type or ''
    if 'application/json' in content_type:
        try:
            return json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return {}
    return dict(request.POST)


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


@_api_require_auth
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


@_api_require_admin
def _create_connection(request):
    data = _parse_body(request)
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


@_api_require_auth
def _get_connection(request, connection_id):
    conn = Connection.objects.filter(id=connection_id).first()
    if not conn:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)
    return JsonResponse({'success': True, 'connection': _safe_connection_data(conn)})


@_api_require_admin
def _update_connection(request, connection_id):
    conn = Connection.objects.filter(id=connection_id).first()
    if not conn:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)

    data = _parse_body(request)
    form = ConnectionForm(data, instance=conn)

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


@_api_require_admin
def _delete_connection(request, connection_id):
    conn = Connection.objects.filter(id=connection_id).first()
    if not conn:
        return JsonResponse({'success': False, 'error': 'Connection not found'}, status=404)

    name = conn.name
    conn.delete()
    logger.warning("API: connection '%s' (ID: %s) deleted by %s", name, connection_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Connection '{name}' deleted."}, status=200)
