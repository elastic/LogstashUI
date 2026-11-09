#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""REST API views for pipeline management.

Agent/policy pipelines (Django ORM — identified by integer id)
--------------------------------------------------------------
GET    /api/pipelines/?policy_id=X          pipeline_list
POST   /api/pipelines/                       pipeline_list
GET    /api/pipelines/{id}/                  pipeline_detail
PUT    /api/pipelines/{id}/                  pipeline_detail
DELETE /api/pipelines/{id}/                  pipeline_detail
POST   /api/pipelines/policies/{id}/deploy/  policy_deploy

Centralized Pipeline Management (CPM) Logstash pipelines (identified by name)
------------------------------------------------------------------------------
Logstash pipelines stored through the Elasticsearch ``_logstash/pipeline`` API
and pulled by Logstash nodes running CPM. Not Elasticsearch ingest pipelines.
``/api/pipelines/es/...`` is a deprecated alias for the same views.

GET    /api/pipelines/centralized/{connection_id}/          centralized_pipeline_list
POST   /api/pipelines/centralized/{connection_id}/          centralized_pipeline_list
GET    /api/pipelines/centralized/{connection_id}/{name}/   centralized_pipeline_detail
PUT    /api/pipelines/centralized/{connection_id}/{name}/   centralized_pipeline_detail
DELETE /api/pipelines/centralized/{connection_id}/{name}/   centralized_pipeline_detail

Lookup
------
GET    /api/pipelines/find/?name=X          pipeline_find
GET    /api/pipelines/recent/               pipeline_recent

Simulation
----------
POST   /api/pipelines/simulate/             pipeline_simulate
"""

import difflib
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from Common import logstash_config_parse
from Common.elastic_utils import get_elastic_connection
from PipelineManager.models import Connection, Pipeline, Policy, SimulationResult
from PipelineManager.simulation import send_simulation_event, start_simulation

from API.auth import api_require_admin, api_require_auth, parse_request_body
from API.simulation_detail import DETAIL_LEVELS, component_index, shape_results

logger = logging.getLogger(__name__)

_PIPELINE_WRITE_FIELDS = frozenset([
    'name', 'description', 'lscl',
    'pipeline_workers', 'pipeline_batch_size', 'pipeline_batch_delay',
    'queue_type', 'queue_max_bytes', 'queue_checkpoint_writes',
])

_SIMULATE_MAX_TIMEOUT = 180  # seconds
_SIMULATE_DEFAULT_TIMEOUT = 30
_SIMULATE_MAX_EVENTS = 100

_FIND_ES_TIMEOUT = 10  # seconds per connection, queried in parallel


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _pipeline_data(pipeline):
    """Full serialization of a Pipeline model instance."""
    return {
        'id': pipeline.id,
        'policy_id': pipeline.policy_id,
        'name': pipeline.name,
        'managed_by': pipeline.managed_by,
        'description': pipeline.description,
        'lscl': pipeline.lscl,
        'pipeline_hash': pipeline.pipeline_hash,
        'last_updated': pipeline.last_updated.isoformat(),
        'revision_number': pipeline.revision_number,
        'pipeline_workers': pipeline.pipeline_workers,
        'pipeline_batch_size': pipeline.pipeline_batch_size,
        'pipeline_batch_delay': pipeline.pipeline_batch_delay,
        'queue_type': pipeline.queue_type,
        'queue_max_bytes': pipeline.queue_max_bytes,
        'queue_checkpoint_writes': pipeline.queue_checkpoint_writes,
        'no_input': pipeline.no_input,
        'non_reloadable': pipeline.non_reloadable,
    }


def _pipeline_list_data(pipeline):
    """Lighter serialization for list responses."""
    return {
        'id': pipeline.id,
        'policy_id': pipeline.policy_id,
        'name': pipeline.name,
        'managed_by': pipeline.managed_by,
        'description': pipeline.description,
        'pipeline_hash': pipeline.pipeline_hash,
        'last_updated': pipeline.last_updated.isoformat(),
        'revision_number': pipeline.revision_number,
        'no_input': pipeline.no_input,
        'non_reloadable': pipeline.non_reloadable,
    }


def _apply_pipeline_fields(data, pipeline):
    """Apply parsed request data onto a Pipeline instance (mutates in place)."""
    if 'name' in data:
        new_name = (data['name'] or '').strip()
        # L3 fix: an empty name on update was silently ignored; raise ValueError
        # so the caller returns 400.
        if not new_name:
            raise ValueError('name cannot be empty.')
        pipeline.name = new_name
    if 'description' in data:
        pipeline.description = data['description'] or ''
    if 'lscl' in data:
        pipeline.lscl = data['lscl'] or ''

    for int_field in ('pipeline_workers', 'pipeline_batch_size',
                      'pipeline_batch_delay', 'queue_checkpoint_writes'):
        if int_field in data and data[int_field] is not None:
            # M20 fix: __setattr__ bypasses Django field descriptors; use setattr.
            setattr(pipeline, int_field, int(data[int_field]))

    for str_field in ('queue_type', 'queue_max_bytes'):
        if str_field in data and data[str_field] is not None:
            setattr(pipeline, str_field, str(data[str_field]))


# ---------------------------------------------------------------------------
# GET/POST /api/pipelines/ — agent pipeline list + create
# ---------------------------------------------------------------------------

@csrf_exempt
def pipeline_list(request):
    """List agent pipelines for a policy, or create a new one.

    GET  /api/pipelines/?policy_id=X
        Returns user-managed pipelines for the given policy.
        Requires ``policy_id`` query parameter. Any authenticated user.

    POST /api/pipelines/
        Create a pipeline. Required body fields: ``policy_id``, ``name``, ``lscl``.
        Sets ``policy.has_undeployed_changes = True``. Admin only.
    """
    if request.method == 'GET':
        return _list_pipelines(request)
    if request.method == 'POST':
        return _create_pipeline(request)
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)


@api_require_auth
def _list_pipelines(request):
    policy_id = request.GET.get('policy_id', '').strip()
    if not policy_id:
        return JsonResponse(
            {'success': False, 'error': 'policy_id query parameter is required.'},
            status=400,
        )

    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    # H18 fix: managed_by was passed directly from query params, letting any
    # caller filter SNMP or other system pipelines.  Restrict to known values.
    _ALLOWED_MANAGED_BY = frozenset({'user', 'snmp', 'library'})
    managed_by = request.GET.get('managed_by', 'user').strip() or 'user'
    if managed_by not in _ALLOWED_MANAGED_BY:
        managed_by = 'user'
    pipelines = list(
        policy.pipelines.filter(managed_by=managed_by).order_by('name')
    )
    return JsonResponse({
        'policy_id': policy.id,
        'policy_name': policy.name,
        'has_undeployed_changes': policy.has_undeployed_changes,
        'pipelines': [_pipeline_list_data(p) for p in pipelines],
        'count': len(pipelines),
    })


@api_require_admin
def _create_pipeline(request):
    data = parse_request_body(request)

    policy_id = data.get('policy_id')
    name = (data.get('name') or '').strip()
    lscl = data.get('lscl', '')

    if not policy_id:
        return JsonResponse({'success': False, 'error': 'policy_id is required.'}, status=400)
    if not name:
        return JsonResponse({'success': False, 'error': 'name is required.'}, status=400)
    if not lscl:
        return JsonResponse({'success': False, 'error': 'lscl is required.'}, status=400)

    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    pipeline = Pipeline(
        policy=policy,
        name=name,
        lscl=lscl,
        managed_by='user',
    )

    try:
        _apply_pipeline_fields(data, pipeline)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': f'Invalid field value: {exc}'}, status=400)

    try:
        pipeline.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except IntegrityError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=409)
    except Exception as exc:
        logger.error("API create pipeline: %s", exc)
        return JsonResponse({'success': False, 'error': 'An internal error occurred. Check server logs.'}, status=500)

    policy.has_undeployed_changes = True
    policy.save(update_fields=['has_undeployed_changes'])

    logger.info("API: pipeline '%s' created in policy %s by %s.", name, policy_id, request.user.username)
    return JsonResponse({
        'success': True,
        'id': pipeline.id,
        'message': 'Pipeline created successfully.',
    }, status=201)


# ---------------------------------------------------------------------------
# GET/PUT/DELETE /api/pipelines/{id}/ — agent pipeline detail
# ---------------------------------------------------------------------------

@csrf_exempt
def pipeline_detail(request, pipeline_id):
    """Read, update, or delete a single agent pipeline.

    GET    /api/pipelines/{id}/   any authenticated user
    PUT    /api/pipelines/{id}/   admin only
    DELETE /api/pipelines/{id}/   admin only
    """
    if request.method == 'GET':
        return _get_pipeline(request, pipeline_id)
    if request.method == 'PUT':
        return _update_pipeline(request, pipeline_id)
    if request.method == 'DELETE':
        return _delete_pipeline(request, pipeline_id)
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)


@api_require_auth
def _get_pipeline(request, pipeline_id):
    try:
        pipeline = Pipeline.objects.select_related('policy').get(pk=pipeline_id)
    except Pipeline.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Pipeline not found.'}, status=404)
    return JsonResponse({'success': True, 'pipeline': _pipeline_data(pipeline)})


@api_require_admin
def _update_pipeline(request, pipeline_id):
    try:
        pipeline = Pipeline.objects.select_related('policy').get(pk=pipeline_id)
    except Pipeline.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Pipeline not found.'}, status=404)

    data = parse_request_body(request)

    try:
        _apply_pipeline_fields(data, pipeline)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': f'Invalid field value: {exc}'}, status=400)

    try:
        pipeline.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except IntegrityError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=409)
    except Exception as exc:
        logger.error("API update pipeline %s: %s", pipeline_id, exc)
        return JsonResponse({'success': False, 'error': 'An internal error occurred. Check server logs.'}, status=500)

    policy = pipeline.policy
    policy.has_undeployed_changes = True
    policy.save(update_fields=['has_undeployed_changes'])

    logger.info("API: pipeline %s updated by %s.", pipeline_id, request.user.username)
    return JsonResponse({
        'success': True,
        'id': pipeline.id,
        'message': 'Pipeline saved successfully.',
    })


@api_require_admin
def _delete_pipeline(request, pipeline_id):
    try:
        pipeline = Pipeline.objects.select_related('policy').get(pk=pipeline_id)
    except Pipeline.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Pipeline not found.'}, status=404)

    name = pipeline.name
    policy = pipeline.policy
    pipeline.delete()

    policy.has_undeployed_changes = True
    policy.save(update_fields=['has_undeployed_changes'])

    logger.warning("API: pipeline '%s' (ID: %s) deleted by %s.", name, pipeline_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Pipeline '{name}' deleted."})


# ---------------------------------------------------------------------------
# POST /api/pipelines/policies/{policy_id}/deploy/ — deploy a policy
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_admin
def policy_deploy(request, policy_id):
    """Snapshot the current user pipelines as a new revision.

    Increments ``current_revision_number``, writes a ``Revision`` row, sets
    ``last_deployed_at``. Agents pick up the change on next check-in.

    POST /api/pipelines/policies/{policy_id}/deploy/
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    from PipelineManager.models import Revision

    # H15 fix: a non-atomic read-increment-write allowed two concurrent deploys
    # to get the same revision number. Keep the F() increment, snapshot, Revision
    # insert, and policy update in one atomic block so a later failure cannot
    # leave current_revision_number bumped with no matching Revision row.
    with transaction.atomic():
        Policy.objects.filter(pk=policy.pk).update(
            current_revision_number=F('current_revision_number') + 1
        )
        policy.refresh_from_db(fields=['current_revision_number'])
        new_revision_number = policy.current_revision_number

        snapshot_data = {
            'logstash_yml': policy.logstash_yml,
            'jvm_options': policy.jvm_options,
            'log4j2_properties': policy.log4j2_properties,
            'settings_path': policy.settings_path,
            'logs_path': policy.logs_path,
            'binary_path': policy.binary_path,
            'pipelines': list(
                policy.pipelines.filter(managed_by='user').values(*Pipeline.SNAPSHOT_FIELDS)
            ),
            'keystore': list(
                policy.keystore_entries.filter(managed_by='user').values('key_name', 'key_value')
            ),
            'keystore_password_hash': policy.keystore_password_hash,
        }

        Revision.objects.create(
            policy=policy,
            revision_number=new_revision_number,
            snapshot_json=snapshot_data,
            created_by=request.user.username,
        )

        policy.last_deployed_at = datetime.now(timezone.utc)
        # Bug 5 fix: clear the undeployed-changes flag after a successful deploy.
        policy.has_undeployed_changes = False
        policy.save(update_fields=['last_deployed_at', 'has_undeployed_changes'])

    logger.info(
        "API: policy '%s' deployed as revision %s by %s.",
        policy.name, new_revision_number, request.user.username,
    )
    return JsonResponse({
        'success': True,
        'message': f"Policy deployed as revision {new_revision_number}.",
        'revision_number': new_revision_number,
        'policy_id': policy.id,
        'policy_name': policy.name,
        'last_deployed_at': policy.last_deployed_at.isoformat(),
    })


# ---------------------------------------------------------------------------
# GET/POST /api/pipelines/centralized/{connection_id}/ — CPM pipeline list + create
# ---------------------------------------------------------------------------

@csrf_exempt
def centralized_pipeline_list(request, connection_id):
    """List or create Centralized Pipeline Management Logstash pipelines.

    These are Logstash pipelines stored via the Elasticsearch
    ``_logstash/pipeline`` API, not Elasticsearch ingest pipelines.

    GET  /api/pipelines/centralized/{connection_id}/
        List all CPM pipelines on the connection. ``?include_lscl=false``
        omits each pipeline's config. Any authenticated user.

    POST /api/pipelines/centralized/{connection_id}/
        Create a pipeline. Required body fields: ``name``, ``lscl``.
        Admin only.

    Example:
        curl -H "Authorization: ApiKey $KEY" \\
          https://logstashui.example.com/api/pipelines/centralized/17/
    """
    if request.method == 'GET':
        return _centralized_list_pipelines(request, connection_id)
    if request.method == 'POST':
        return _centralized_create_pipeline(request, connection_id)
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)


def _check_centralized_connection_exists(connection_id):
    """Return a 404 JsonResponse if the connection row doesn't exist, else None.

    Bug 4 fix: ``get_elastic_connection`` raises DoesNotExist which previously
    bubbled up as a 502.  Checking up-front lets us return the correct 404.
    """
    if not Connection.objects.filter(pk=connection_id).exists():
        return JsonResponse(
            {'success': False, 'error': 'Connection not found.'}, status=404
        )
    return None


@api_require_auth
def _centralized_list_pipelines(request, connection_id):
    early = _check_centralized_connection_exists(connection_id)
    if early:
        return early
    try:
        es = get_elastic_connection(connection_id)
        raw = es.logstash.get_pipeline()
    except Exception as exc:
        logger.error("API CPM list pipelines (conn %s): %s", connection_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=502)

    include_lscl = request.GET.get('include_lscl', 'true').lower() != 'false'
    pipelines = []
    for name, body in (raw or {}).items():
        entry = {
            'name': name,
            'description': body.get('description', ''),
            'last_modified': body.get('last_modified', ''),
            'username': body.get('username', ''),
            'pipeline_settings': body.get('pipeline_settings', {}),
        }
        if include_lscl:
            entry['lscl'] = body.get('pipeline', '')
        pipelines.append(entry)

    return JsonResponse({
        'connection_id': connection_id,
        'pipelines': sorted(pipelines, key=lambda p: p['name']),
        'count': len(pipelines),
    })


@api_require_admin
def _centralized_create_pipeline(request, connection_id):
    early = _check_centralized_connection_exists(connection_id)
    if early:
        return early

    data = parse_request_body(request)
    name = (data.get('name') or '').strip()
    lscl = data.get('lscl', '')

    if not name:
        return JsonResponse({'success': False, 'error': 'name is required.'}, status=400)
    if not lscl:
        return JsonResponse({'success': False, 'error': 'lscl is required.'}, status=400)

    body = {
        'description': data.get('description', ''),
        'last_modified': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
        'username': request.user.username,
        'pipeline': lscl,
        'pipeline_settings': {
            'pipeline.workers': int(data.get('pipeline_workers', 1)),
            'pipeline.batch.size': int(data.get('pipeline_batch_size', 128)),
            'pipeline.batch.delay': int(data.get('pipeline_batch_delay', 50)),
            'queue.type': data.get('queue_type', 'memory'),
            'queue.max_bytes': data.get('queue_max_bytes', '1gb'),
            'queue.checkpoint.writes': int(data.get('queue_checkpoint_writes', 1024)),
        },
    }

    try:
        es = get_elastic_connection(connection_id)
        es.logstash.put_pipeline(id=name, body=body)
    except Exception as exc:
        logger.error("API CPM create pipeline '%s' (conn %s): %s", name, connection_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=502)

    logger.info("API: CPM pipeline '%s' created in conn %s by %s.", name, connection_id, request.user.username)
    return JsonResponse({'success': True, 'name': name, 'message': 'Pipeline created.'}, status=201)


# ---------------------------------------------------------------------------
# GET/PUT/DELETE /api/pipelines/centralized/{connection_id}/{name}/ — CPM pipeline detail
# ---------------------------------------------------------------------------

@csrf_exempt
def centralized_pipeline_detail(request, connection_id, name):
    """Read, update, or delete one Centralized Pipeline Management Logstash pipeline.

    GET    /api/pipelines/centralized/{connection_id}/{name}/   any authenticated user
    PUT    /api/pipelines/centralized/{connection_id}/{name}/   admin only
    DELETE /api/pipelines/centralized/{connection_id}/{name}/   admin only

    Example:
        curl -X DELETE -H "Authorization: ApiKey $KEY" \\
          https://logstashui.example.com/api/pipelines/centralized/17/apache-logs/
    """
    # H16 fix: without this guard an unknown connection_id produced a 502 instead
    # of the expected 404 because get_elastic_connection raised DoesNotExist which
    # was caught by the broad `except Exception` in each sub-handler and reported
    # as a connection error rather than a "not found" error.
    early = _check_centralized_connection_exists(connection_id)
    if early:
        return early

    if request.method == 'GET':
        return _centralized_get_pipeline(request, connection_id, name)
    if request.method == 'PUT':
        return _centralized_update_pipeline(request, connection_id, name)
    if request.method == 'DELETE':
        return _centralized_delete_pipeline(request, connection_id, name)
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)


@api_require_auth
def _centralized_get_pipeline(request, connection_id, name):
    try:
        es = get_elastic_connection(connection_id)
        raw = es.logstash.get_pipeline(id=name)
    except Exception as exc:
        status = 404 if '404' in str(exc) or 'not found' in str(exc).lower() else 502
        return JsonResponse({'success': False, 'error': str(exc)}, status=status)

    body = (raw or {}).get(name, {})
    return JsonResponse({
        'success': True,
        'pipeline': {
            'name': name,
            'connection_id': connection_id,
            'description': body.get('description', ''),
            'lscl': body.get('pipeline', ''),
            'last_modified': body.get('last_modified', ''),
            'username': body.get('username', ''),
            'pipeline_settings': body.get('pipeline_settings', {}),
        },
    })


@api_require_admin
def _centralized_update_pipeline(request, connection_id, name):
    data = parse_request_body(request)

    # Fetch current to merge
    try:
        es = get_elastic_connection(connection_id)
        raw = es.logstash.get_pipeline(id=name)
        current = (raw or {}).get(name, {})
    except Exception as exc:
        status = 404 if '404' in str(exc) or 'not found' in str(exc).lower() else 502
        return JsonResponse({'success': False, 'error': str(exc)}, status=status)

    current_settings = current.get('pipeline_settings', {})

    body = {
        'description': data.get('description', current.get('description', '')),
        'last_modified': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        'pipeline_metadata': current.get('pipeline_metadata', {'version': 1, 'type': 'logstash_pipeline'}),
        'username': request.user.username,
        'pipeline': data.get('lscl', current.get('pipeline', '')),
        'pipeline_settings': {
            'pipeline.workers': int(data.get('pipeline_workers', current_settings.get('pipeline.workers', 1))),
            'pipeline.batch.size': int(data.get('pipeline_batch_size', current_settings.get('pipeline.batch.size', 128))),
            'pipeline.batch.delay': int(data.get('pipeline_batch_delay', current_settings.get('pipeline.batch.delay', 50))),
            'queue.type': data.get('queue_type', current_settings.get('queue.type', 'memory')),
            'queue.max_bytes': data.get('queue_max_bytes', current_settings.get('queue.max_bytes', '1gb')),
            'queue.checkpoint.writes': int(data.get('queue_checkpoint_writes', current_settings.get('queue.checkpoint.writes', 1024))),
        },
    }

    try:
        es.logstash.put_pipeline(id=name, body=body)
    except Exception as exc:
        logger.error("API CPM update pipeline '%s' (conn %s): %s", name, connection_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=502)

    logger.info("API: CPM pipeline '%s' updated in conn %s by %s.", name, connection_id, request.user.username)
    return JsonResponse({'success': True, 'name': name, 'message': 'Pipeline updated.'})


@api_require_admin
def _centralized_delete_pipeline(request, connection_id, name):
    try:
        es = get_elastic_connection(connection_id)
        es.logstash.delete_pipeline(id=name)
    except Exception as exc:
        status = 404 if '404' in str(exc) or 'not found' in str(exc).lower() else 502
        return JsonResponse({'success': False, 'error': str(exc)}, status=status)

    logger.warning("API: CPM pipeline '%s' deleted from conn %s by %s.", name, connection_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Pipeline '{name}' deleted."})


# ---------------------------------------------------------------------------
# GET /api/pipelines/find/ — locate a pipeline by name everywhere
# ---------------------------------------------------------------------------

@api_require_auth
def pipeline_find(request):
    """Find Logstash pipelines by name in every policy and on every CPM connection.

    Agent pipelines are searched in every policy except embedded ones, and CPM
    pipelines on every CENTRALIZED connection. Connections that can't be
    listed are reported under ``unreachable`` so callers can tell "not found"
    from "not searched".

    GET /api/pipelines/find/?name=X   any authenticated user

    ``name`` may be part of a name or a topic such as ``asa``: pipelines whose
    names contain it are returned under ``similar``.

    Each pipeline in ``matches`` (exact name) and ``similar`` (up to 10 close
    or overlapping names, closest first) is either
    ``{"type": "agent", "name", "pipeline_id", "policy_id", "policy_name",
    "managed_by", "last_modified"}`` or ``{"type": "cpm", "name",
    "connection_id", "connection_name", "last_modified"}``. Its id fields are
    the arguments other pipeline endpoints, including simulate, take.

    Example:
        curl -H "Authorization: ApiKey $KEY" \\
          "https://logstashui.example.com/api/pipelines/find/?name=asa-new"
    """
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    name = request.GET.get('name', '').strip()
    if not name:
        return JsonResponse(
            {'success': False, 'error': 'name query parameter is required.'}, status=400,
        )

    candidates, unreachable = _list_all_pipelines()
    return JsonResponse({
        'success': True,
        'name': name,
        'matches': [c for c in candidates if c['name'] == name],
        'similar': _similar_pipelines(name, candidates),
        'unreachable': unreachable,
    })


# ---------------------------------------------------------------------------
# GET /api/pipelines/recent/ — pipelines everywhere, newest change first
# ---------------------------------------------------------------------------

@api_require_auth
def pipeline_recent(request):
    """List pipelines in every policy and on every CPM connection, most recently modified first.

    Reads the ``last_modified`` each pipeline already carries; nothing is
    recorded about who changed what.

    GET /api/pipelines/recent/?limit=20&since=2026-11-01T00:00:00Z   any authenticated user

    Query parameters:
        limit: Maximum pipelines to return (default 20, max 200).
        since: ISO 8601 timestamp; only pipelines modified at or after it.

    Returns entries in the :func:`pipeline_find` form, plus ``unreachable``
    connections whose pipelines could not be listed.

    Example:
        curl -H "Authorization: ApiKey $KEY" \\
          "https://logstashui.example.com/api/pipelines/recent/?since=2026-11-01"
    """
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        limit = int(request.GET.get('limit') or 20)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'limit must be an integer.'}, status=400)
    limit = max(1, min(limit, 200))
    since = None
    if request.GET.get('since'):
        since = _parse_timestamp(request.GET['since'])
        if since is None:
            return JsonResponse(
                {'success': False, 'error': 'since must be an ISO 8601 timestamp.'}, status=400,
            )

    candidates, unreachable = _list_all_pipelines()
    dated = [(_parse_timestamp(c['last_modified']), c) for c in candidates]
    dated = [(ts, c) for ts, c in dated if ts and (since is None or ts >= since)]
    dated.sort(key=lambda item: item[0], reverse=True)
    return JsonResponse({
        'success': True,
        'pipelines': [c for _, c in dated[:limit]],
        'total': len(dated),
        'unreachable': unreachable,
    })


def _parse_timestamp(value):
    """Parse an ISO 8601 timestamp to an aware UTC datetime, or None.

    Examples:
        >>> _parse_timestamp('2026-11-04T15:17:52.688Z').isoformat()
        '2026-11-04T15:17:52.688000+00:00'
        >>> _parse_timestamp('2026-11-01').isoformat()
        '2026-11-01T00:00:00+00:00'
        >>> _parse_timestamp('yesterday') is None
        True
    """
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _list_all_pipelines():
    """List agent pipelines (except embedded policies) and CPM pipelines.

    Returns:
        tuple: ``(pipelines, unreachable)`` in the :func:`pipeline_find` entry form.
    """
    agent_pipelines = (
        Pipeline.objects.select_related('policy')
        .exclude(policy__policy_type=Policy.PolicyType.EMBEDDED)
        .order_by('policy__name', 'name')
    )
    pipelines = [
        {'type': 'agent', 'name': p.name, 'pipeline_id': p.id, 'policy_id': p.policy_id,
         'policy_name': p.policy.name, 'managed_by': p.managed_by,
         'last_modified': p.last_updated.isoformat()}
        for p in agent_pipelines
    ]
    cpm_pipelines, unreachable = _list_cpm_pipelines()
    return pipelines + cpm_pipelines, unreachable


def _list_cpm_pipelines():
    """List the CPM pipelines on every CENTRALIZED connection.

    Connections are queried in parallel with a short timeout, so one
    unreachable cluster delays the search by at most ``_FIND_ES_TIMEOUT``.

    Returns:
        tuple: ``(pipelines, unreachable)``, both lists of dicts in the
        :func:`pipeline_find` response form.
    """
    clients, unreachable = [], []
    connections = Connection.objects.filter(
        connection_type=Connection.ConnectionType.CENTRALIZED,
    ).order_by('name')
    for conn in connections:
        try:
            es = get_elastic_connection(conn.id).options(request_timeout=_FIND_ES_TIMEOUT)
        except Exception as exc:
            unreachable.append({'connection_id': conn.id, 'connection_name': conn.name,
                                'error': str(exc)})
            continue
        clients.append((conn, es))

    def fetch(client):
        conn, es = client
        try:
            return conn, es.logstash.get_pipeline() or {}, None
        except Exception as exc:
            return conn, None, exc

    pipelines = []
    if clients:
        with ThreadPoolExecutor(max_workers=min(len(clients), 8)) as pool:
            for conn, raw, exc in pool.map(fetch, clients):
                if exc is not None:
                    logger.warning("API find: CPM list failed (conn %s): %s", conn.id, exc)
                    unreachable.append({'connection_id': conn.id, 'connection_name': conn.name,
                                        'error': str(exc)})
                    continue
                pipelines += [
                    {'type': 'cpm', 'name': name, 'connection_id': conn.id,
                     'connection_name': conn.name,
                     'last_modified': (raw[name] or {}).get('last_modified', '')}
                    for name in sorted(raw)
                ]
    return pipelines, unreachable


def _similar_pipelines(name, candidates, limit=10):
    """Return pipelines whose names are close to, contain, or are contained in ``name``.

    Args:
        name: The name searched for.
        candidates: Pipelines in :func:`pipeline_find` entry form.
        limit: Maximum number to return.

    Returns:
        list: Up to ``limit`` candidates not named exactly ``name``, closest first.

    Examples:
        >>> [p['name'] for p in _similar_pipelines('asa-fixed', [
        ...     {'name': 'asa-new-fixed'}, {'name': 'asa'}, {'name': 'syslog'}])]
        ['asa-new-fixed', 'asa']
    """
    wanted = name.lower()
    names = {c['name'] for c in candidates if c['name'] != name}
    close = set(difflib.get_close_matches(name, names, n=limit, cutoff=0.6))
    close |= {n for n in names if wanted in n.lower() or n.lower() in wanted}

    def closeness(candidate):
        return difflib.SequenceMatcher(None, wanted, candidate['name'].lower()).ratio()

    return sorted((c for c in candidates if c['name'] in close), key=closeness, reverse=True)[:limit]


# ---------------------------------------------------------------------------
# POST /api/pipelines/simulate/ — synchronous simulation
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_admin
def pipeline_simulate(request):
    """Run a pipeline simulation synchronously and return results.

    POST /api/pipelines/simulate/

    Body fields (exactly one LSCL source: ``lscl``, ``pipeline_id``, or
    ``connection_id`` + ``name``):
        lscl (str): Raw Logstash config.
        pipeline_id (int): Load LSCL from a saved agent pipeline.
        connection_id (int): CENTRALIZED connection holding a CPM pipeline.
        name (str): CPM pipeline ID to load LSCL from; requires ``connection_id``.
        event (str): Sample log line or JSON to process. Mutually exclusive
            with ``events``.
        events (list): Bulk mode. Up to 100 log lines (str) or JSON events
            (str or object), run on one simulation slot. Mutually exclusive
            with ``event``.
        sim_connection_id (int, optional): Specific simulate-agent connection.
        policy_id (int, optional): Source policy for keystore sync.
        timeout (int, optional): Max seconds to wait for all results.
            Default 30, max 180.
        detail (str, optional): ``full`` (default; raw ``results`` with every
            filter snapshot), ``steps`` (``final`` event plus per-filter
            ``steps`` listing only fields added, changed, or removed), or
            ``final`` (``final`` event only). See ``API.simulation_detail``.

    Returns:
        Single mode: JSON with ``complete``, ``elapsed_ms``, ``slot_id``,
        ``run_id``, ``detail``, and the fields for that detail level.

        Bulk mode: JSON with ``events`` (one entry per input, in order, each
        with ``index``, ``run_id``, ``complete``, the detail fields, and
        ``error`` on failure), ``count``, ``complete_count``, ``slot_id``, and
        ``elapsed_ms``.

    Examples:
        POST /api/pipelines/simulate/
        {"pipeline_id": 12, "events": ["<164>%ASA-4-106023: Deny tcp ...",
                                        {"message": "second event"}]}

        POST /api/pipelines/simulate/
        {"connection_id": 17, "name": "asa-new", "event": "<164>%ASA-4-106023: ..."}
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    data = parse_request_body(request)

    # --- Resolve LSCL ---
    lscl = (data.get('lscl') or '').strip()
    pipeline_id = data.get('pipeline_id')
    event_text = (data.get('event') or '').strip()
    bulk_events = data.get('events')

    if bulk_events is not None:
        if event_text:
            return JsonResponse(
                {'success': False, 'error': 'Provide event or events, not both.'}, status=400,
            )
        if not isinstance(bulk_events, list) or not bulk_events:
            return JsonResponse(
                {'success': False, 'error': 'events must be a non-empty list.'}, status=400,
            )
        if len(bulk_events) > _SIMULATE_MAX_EVENTS:
            return JsonResponse(
                {'success': False, 'error': f'events is limited to {_SIMULATE_MAX_EVENTS} items.'},
                status=400,
            )
        try:
            bulk_events = [_event_to_text(e) for e in bulk_events]
        except ValueError as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    connection_id = data.get('connection_id')
    cpm_name = (data.get('name') or '').strip()
    if bool(connection_id) != bool(cpm_name):
        return JsonResponse(
            {'success': False, 'error': 'connection_id and name must be provided together.'},
            status=400,
        )

    if sum(bool(s) for s in (lscl, pipeline_id, cpm_name)) > 1:
        return JsonResponse(
            {'success': False,
             'error': 'Provide only one of lscl, pipeline_id, or connection_id + name.'},
            status=400,
        )

    if pipeline_id:
        try:
            p = Pipeline.objects.get(pk=pipeline_id)
            lscl = p.lscl or ''
        except Pipeline.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'pipeline_id not found.'}, status=404)

    if cpm_name:
        early = _check_centralized_connection_exists(connection_id)
        if early:
            return early
        try:
            raw = get_elastic_connection(connection_id).logstash.get_pipeline(id=cpm_name)
        except Exception as exc:
            if '404' in str(exc) or 'not found' in str(exc).lower():
                raw = {}
            else:
                logger.error("API simulate: CPM fetch '%s' (conn %s): %s", cpm_name, connection_id, exc)
                return JsonResponse({'success': False, 'error': str(exc)}, status=502)
        if cpm_name not in (raw or {}):
            return JsonResponse(
                {'success': False,
                 'error': f"CPM pipeline '{cpm_name}' not found on connection {connection_id}."},
                status=404,
            )
        lscl = raw[cpm_name].get('pipeline', '')

    if not lscl:
        return JsonResponse(
            {'success': False, 'error': 'lscl, pipeline_id, or connection_id + name is required.'},
            status=400,
        )
    if not event_text and bulk_events is None:
        return JsonResponse({'success': False, 'error': 'event or events is required.'}, status=400)

    # --- Timeout ---
    try:
        timeout = min(int(data.get('timeout', _SIMULATE_DEFAULT_TIMEOUT)), _SIMULATE_MAX_TIMEOUT)
    except (ValueError, TypeError):
        timeout = _SIMULATE_DEFAULT_TIMEOUT

    detail = data.get('detail') or 'full'
    if detail not in DETAIL_LEVELS:
        return JsonResponse(
            {'success': False, 'error': f"detail must be one of: {', '.join(DETAIL_LEVELS)}."},
            status=400,
        )

    # --- Convert LSCL → components ---
    try:
        raw_components = logstash_config_parse.logstash_config_to_components(lscl)
        # logstash_config_to_components returns a JSON string
        if isinstance(raw_components, str):
            components = json.loads(raw_components)
        else:
            components = raw_components
    except Exception as exc:
        logger.error("API simulate: LSCL parse error: %s", exc)
        return JsonResponse({'success': False, 'error': f'LSCL parse error: {exc}'}, status=400)

    filter_plugins = components.get('filter', [])
    if not filter_plugins:
        return JsonResponse(
            {'success': False, 'error': 'Pipeline has no filter plugins to simulate.'},
            status=400,
        )

    index = component_index(components)

    def shape(results):
        return {'detail': detail, **shape_results(results, detail, index)}

    t_start = time.time()

    if bulk_events is not None:
        return _simulate_bulk(request, data, components, bulk_events, t_start, timeout, shape)

    start = _start_simulation(request, data, components, event_text)
    if start.error:
        return JsonResponse(
            {'success': False, 'error': start.error, 'slot_id': start.slot_id}, status=502,
        )
    effective_run_id, slot_id = start.run_id, start.slot_id

    results = _collect_simulation_results([effective_run_id], t_start + timeout)[effective_run_id]
    elapsed_ms = int((time.time() - t_start) * 1000)

    if not results:
        return JsonResponse(
            {
                'success': False,
                'error': (
                    f'No simulation results within {timeout}s. The simulate agent may still be '
                    'loading the pipeline; retry once. If it times out again, the simulate '
                    'agent is not returning results.'
                ),
                'run_id': effective_run_id,
                'slot_id': slot_id,
                'elapsed_ms': elapsed_ms,
            },
            status=408,
        )

    logger.info(
        "API simulate: run_id=%s returned %d event(s) in %dms.",
        effective_run_id, len(results), elapsed_ms,
    )
    body = {
        'success': True,
        'run_id': effective_run_id,
        'slot_id': slot_id,
        'complete': any(r.get('snapshots') for r in results),
        'elapsed_ms': elapsed_ms,
        **shape(results),
    }
    if detail == 'full':
        body['count'] = len(results)
    return JsonResponse(body)


def _event_to_text(event):
    """Normalize one bulk ``events`` item to the text a simulation event is sent as.

    Args:
        event: A log line (str) or a JSON event (dict).

    Returns:
        str: The stripped log line, or the dict serialized as JSON.

    Raises:
        ValueError: If the item is empty or not a str/dict.

    Examples:
        >>> _event_to_text({"message": "hi"})
        '{"message": "hi"}'
    """
    if isinstance(event, dict):
        return json.dumps(event)
    if isinstance(event, str) and event.strip():
        return event.strip()
    raise ValueError('Each item in events must be a non-empty string or a JSON object.')


def _start_simulation(request, data, components, event_text):
    """Instrument the pipeline, get a slot, and send the first event.

    Args:
        request: The API request; its base URL receives the agent's results.
        data: Parsed API body (``policy_id`` / ``sim_connection_id`` honoured).
        components: Parsed pipeline components.
        event_text: Log line or JSON text for the event.

    Returns:
        SimulationStart: ``error`` is set if the run did not start.
    """
    return start_simulation(
        components,
        event_text,
        ui_base_url=request.build_absolute_uri('/').rstrip('/'),
        # The API is stateless; don't persist a sticky agent on the caller's session.
        session={},
        sim_connection_id=data.get('sim_connection_id'),
        policy_id=data.get('policy_id'),
    )


def _collect_simulation_results(run_ids, deadline):
    """Read results for ``run_ids`` until every run completes or ``deadline`` passes.

    The step-0 "original" event arrives first; a run is done once an event
    carrying filter snapshots arrives (end of pipeline or a drop).

    Args:
        run_ids: Run ids to wait for.
        deadline: ``time.time()`` value after which to stop waiting.

    Returns:
        dict: ``{run_id: [result, ...]}`` for every requested run id.
    """
    collected = {run_id: [] for run_id in run_ids}
    while True:
        pending = [r for r, res in collected.items() if not any(e.get('snapshots') for e in res)]
        if not pending:
            break
        for run_id, results in SimulationResult.take(pending).items():
            collected[run_id].extend(results)
        if time.time() >= deadline:
            break
        time.sleep(0.25)
    return collected


def _simulate_bulk(request, data, components, events, t_start, timeout, shape):
    """Run ``events`` on one simulation slot and return per-event results.

    The first event allocates the slot; the rest are sent straight into it,
    skipping the slot checks and keystore sync that only the first needs.
    All runs share one ``timeout``. ``shape`` turns one run's raw results
    into its response fields.
    """
    start = _start_simulation(request, data, components, events[0])
    if start.error:
        # Slot allocation failed; later events would fail the same way.
        return JsonResponse(
            {'success': False, 'error': start.error, 'slot_id': start.slot_id}, status=502,
        )
    slot_id = start.slot_id
    entries = [{'index': 0, 'run_id': start.run_id, 'error': start.forward_error}]
    for index, event_text in enumerate(events[1:], start=1):
        run_id = str(uuid.uuid4())
        _queued, forward_error = send_simulation_event(start.agent_url, slot_id, run_id, event_text)
        entries.append({'index': index, 'run_id': run_id, 'error': forward_error})

    pending = [e['run_id'] for e in entries]
    collected = _collect_simulation_results(pending, t_start + timeout)
    elapsed_ms = int((time.time() - t_start) * 1000)

    complete_count = 0
    for entry in entries:
        results = collected.get(entry['run_id'], [])
        entry['complete'] = any(r.get('snapshots') for r in results)
        complete_count += entry['complete']
        # A send error only matters if the agent never delivered results.
        forward_error = entry.pop('error')
        if not entry['complete']:
            entry['error'] = forward_error or f'Timed out after {timeout}s.'
        entry.update(shape(results))

    logger.info(
        "API simulate bulk: slot=%s %d/%d event(s) complete in %dms.",
        slot_id, complete_count, len(entries), elapsed_ms,
    )
    return JsonResponse({
        'success': complete_count > 0,
        'slot_id': slot_id,
        'events': entries,
        'count': len(entries),
        'complete_count': complete_count,
        'elapsed_ms': elapsed_ms,
    }, status=200 if complete_count else 408)
