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

Elasticsearch / centralized pipelines (identified by name)
-----------------------------------------------------------
GET    /api/pipelines/es/{connection_id}/               es_pipeline_list
POST   /api/pipelines/es/{connection_id}/               es_pipeline_list
GET    /api/pipelines/es/{connection_id}/{name}/         es_pipeline_detail
PUT    /api/pipelines/es/{connection_id}/{name}/         es_pipeline_detail
DELETE /api/pipelines/es/{connection_id}/{name}/         es_pipeline_detail

Simulation
----------
POST   /api/pipelines/simulate/             pipeline_simulate
"""

import json
import logging
import re
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import requests
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.test import RequestFactory
from django.views.decorators.csrf import csrf_exempt

from Common import logstash_config_parse
from Common.elastic_utils import get_elastic_connection
from PipelineManager.models import Pipeline, Policy
from PipelineManager.simulation import (
    SimulatePipeline,
    simulation_lock,
    simulation_results,
)

from API.auth import api_require_admin, api_require_auth, parse_request_body

logger = logging.getLogger(__name__)

_PIPELINE_WRITE_FIELDS = frozenset([
    'name', 'description', 'lscl',
    'pipeline_workers', 'pipeline_batch_size', 'pipeline_batch_delay',
    'queue_type', 'queue_max_bytes', 'queue_checkpoint_writes',
])

_SIMULATE_MAX_TIMEOUT = 180  # seconds
_SIMULATE_DEFAULT_TIMEOUT = 30


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
        pipeline.name = (data['name'] or '').strip() or pipeline.name
    if 'description' in data:
        pipeline.description = data['description'] or ''
    if 'lscl' in data:
        pipeline.lscl = data['lscl'] or ''

    for int_field in ('pipeline_workers', 'pipeline_batch_size',
                      'pipeline_batch_delay', 'queue_checkpoint_writes'):
        if int_field in data and data[int_field] is not None:
            pipeline.__setattr__(int_field, int(data[int_field]))

    for str_field in ('queue_type', 'queue_max_bytes'):
        if str_field in data and data[str_field] is not None:
            pipeline.__setattr__(str_field, str(data[str_field]))


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
    return JsonResponse({'error': 'Method not allowed'}, status=405)


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

    managed_by = request.GET.get('managed_by', 'user').strip() or 'user'
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
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

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
    return JsonResponse({'error': 'Method not allowed'}, status=405)


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
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

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
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    from PipelineManager.models import Revision

    policy.current_revision_number += 1
    new_revision_number = policy.current_revision_number

    snapshot_data = {
        'logstash_yml': policy.logstash_yml,
        'jvm_options': policy.jvm_options,
        'log4j2_properties': policy.log4j2_properties,
        'settings_path': policy.settings_path,
        'logs_path': policy.logs_path,
        'binary_path': policy.binary_path,
        'pipelines': list(
            policy.pipelines.filter(managed_by='user').values(
                'name', 'description', 'lscl', 'no_input', 'non_reloadable'
            )
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
    policy.save(update_fields=['current_revision_number', 'last_deployed_at', 'has_undeployed_changes'])

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
# GET/POST /api/pipelines/es/{connection_id}/ — ES pipeline list + create
# ---------------------------------------------------------------------------

@csrf_exempt
def es_pipeline_list(request, connection_id):
    """List or create Elasticsearch-managed pipelines for a connection.

    GET  /api/pipelines/es/{connection_id}/
        List all pipelines stored in Elasticsearch Logstash pipeline API.
        Any authenticated user.

    POST /api/pipelines/es/{connection_id}/
        Create a pipeline. Required body fields: ``name``, ``lscl``.
        Admin only.
    """
    if request.method == 'GET':
        return _es_list_pipelines(request, connection_id)
    if request.method == 'POST':
        return _es_create_pipeline(request, connection_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def _check_es_connection_exists(connection_id):
    """Return a 404 JsonResponse if the connection row doesn't exist, else None.

    Bug 4 fix: ``get_elastic_connection`` raises DoesNotExist which previously
    bubbled up as a 502.  Checking up-front lets us return the correct 404.
    """
    from PipelineManager.models import Connection as _Conn
    if not _Conn.objects.filter(pk=connection_id).exists():
        return JsonResponse(
            {'success': False, 'error': 'Connection not found.'}, status=404
        )
    return None


@api_require_auth
def _es_list_pipelines(request, connection_id):
    early = _check_es_connection_exists(connection_id)
    if early:
        return early
    try:
        es = get_elastic_connection(connection_id)
        raw = es.logstash.get_pipeline()
    except Exception as exc:
        logger.error("API ES list pipelines (conn %s): %s", connection_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=502)

    pipelines = []
    for name, body in (raw or {}).items():
        pipelines.append({
            'name': name,
            'description': body.get('description', ''),
            'lscl': body.get('pipeline', ''),
            'last_modified': body.get('last_modified', ''),
            'username': body.get('username', ''),
            'pipeline_settings': body.get('pipeline_settings', {}),
        })

    return JsonResponse({
        'connection_id': connection_id,
        'pipelines': sorted(pipelines, key=lambda p: p['name']),
        'count': len(pipelines),
    })


@api_require_admin
def _es_create_pipeline(request, connection_id):
    early = _check_es_connection_exists(connection_id)
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
        logger.error("API ES create pipeline '%s' (conn %s): %s", name, connection_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=502)

    logger.info("API: ES pipeline '%s' created in conn %s by %s.", name, connection_id, request.user.username)
    return JsonResponse({'success': True, 'name': name, 'message': 'Pipeline created.'}, status=201)


# ---------------------------------------------------------------------------
# GET/PUT/DELETE /api/pipelines/es/{connection_id}/{name}/ — ES pipeline detail
# ---------------------------------------------------------------------------

@csrf_exempt
def es_pipeline_detail(request, connection_id, name):
    """Read, update, or delete a single ES-managed pipeline.

    GET    /api/pipelines/es/{connection_id}/{name}/   any authenticated user
    PUT    /api/pipelines/es/{connection_id}/{name}/   admin only
    DELETE /api/pipelines/es/{connection_id}/{name}/   admin only
    """
    if request.method == 'GET':
        return _es_get_pipeline(request, connection_id, name)
    if request.method == 'PUT':
        return _es_update_pipeline(request, connection_id, name)
    if request.method == 'DELETE':
        return _es_delete_pipeline(request, connection_id, name)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _es_get_pipeline(request, connection_id, name):
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
def _es_update_pipeline(request, connection_id, name):
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
        logger.error("API ES update pipeline '%s' (conn %s): %s", name, connection_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=502)

    logger.info("API: ES pipeline '%s' updated in conn %s by %s.", name, connection_id, request.user.username)
    return JsonResponse({'success': True, 'name': name, 'message': 'Pipeline updated.'})


@api_require_admin
def _es_delete_pipeline(request, connection_id, name):
    try:
        es = get_elastic_connection(connection_id)
        es.logstash.delete_pipeline(id=name)
    except Exception as exc:
        status = 404 if '404' in str(exc) or 'not found' in str(exc).lower() else 502
        return JsonResponse({'success': False, 'error': str(exc)}, status=status)

    logger.warning("API: ES pipeline '%s' deleted from conn %s by %s.", name, connection_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Pipeline '{name}' deleted."})


# ---------------------------------------------------------------------------
# POST /api/pipelines/simulate/ — synchronous simulation
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_admin
def pipeline_simulate(request):
    """Run a pipeline simulation synchronously and return results.

    POST /api/pipelines/simulate/

    Body fields:
        pipeline_id (int): Load LSCL from a saved agent pipeline. Mutually
            exclusive with ``lscl``.
        lscl (str): Raw Logstash config. Mutually exclusive with ``pipeline_id``.
        event (str, required): Sample log line or JSON to process.
        sim_connection_id (int, optional): Specific simulate-agent connection.
        policy_id (int, optional): Source policy for keystore sync.
        timeout (int, optional): Max seconds to wait for results.
            Default %(default)s, max %(max)s.

    Returns:
        JSON with ``results`` list (per-event snapshots), ``elapsed_ms``,
        ``slot_id``, and ``run_id``.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    data = parse_request_body(request)

    # --- Resolve LSCL ---
    lscl = (data.get('lscl') or '').strip()
    pipeline_id = data.get('pipeline_id')
    event_text = (data.get('event') or '').strip()

    if pipeline_id and not lscl:
        try:
            p = Pipeline.objects.get(pk=pipeline_id)
            lscl = p.lscl or ''
        except Pipeline.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'pipeline_id not found.'}, status=404)

    if not lscl:
        return JsonResponse({'success': False, 'error': 'lscl or pipeline_id is required.'}, status=400)
    if not event_text:
        return JsonResponse({'success': False, 'error': 'event is required.'}, status=400)

    # --- Timeout ---
    try:
        timeout = min(int(data.get('timeout', _SIMULATE_DEFAULT_TIMEOUT)), _SIMULATE_MAX_TIMEOUT)
    except (ValueError, TypeError):
        timeout = _SIMULATE_DEFAULT_TIMEOUT

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

    run_id = str(uuid.uuid4())

    # --- Build a synthetic request to hand to SimulatePipeline ---
    rf = RequestFactory()
    post_payload = {
        'components': json.dumps(components),
        'log_text': event_text,
    }
    if data.get('policy_id'):
        post_payload['policy_id'] = str(data['policy_id'])
    if data.get('sim_connection_id'):
        post_payload['sim_connection_id'] = str(data['sim_connection_id'])

    fake_req = rf.post('/api/pipelines/simulate/', post_payload)
    fake_req.user = request.user
    fake_req.session = {}
    if data.get('sim_connection_id'):
        fake_req.session['sim_connection_id'] = data['sim_connection_id']

    # Provide build_absolute_uri so the sim callback URL resolves correctly
    _base = request.build_absolute_uri('/').rstrip('/')
    fake_req.build_absolute_uri = lambda path='': _base + (path if path else '/')

    # --- Trigger simulation (allocates slot + forwards event) ---
    t_start = time.time()
    try:
        sim_response = SimulatePipeline(fake_req)
    except Exception as exc:
        logger.error("API simulate: SimulatePipeline raised: %s", exc)
        return JsonResponse({'success': False, 'error': f'Simulation error: {exc}'}, status=500)

    response_text = sim_response.content.decode('utf-8', errors='replace')

    # Extract run_id from HTML response (data-run-id attribute or fallback to ours)
    run_id_match = re.search(r'data-run-id=["\']([^"\']+)["\']', response_text)
    effective_run_id = run_id_match.group(1) if run_id_match else run_id

    slot_id_match = re.search(r'data-slot-id=["\']([^"\']+)["\']', response_text)
    slot_id = slot_id_match.group(1) if slot_id_match else None

    # Surface hard failures (no run_id returned, non-"preallocation" text)
    if sim_response.status_code >= 400:
        plain = re.sub(r'<[^>]+>', '', response_text).strip()
        return JsonResponse({'success': False, 'error': plain[:500] or 'Simulation failed.'}, status=502)

    if 'data-pipeline-failed' in response_text:
        plain = re.sub(r'<[^>]+>', '', response_text).strip()
        return JsonResponse({'success': False, 'error': plain[:500] or 'Agent rejected pipeline.'}, status=502)

    # --- Poll simulation_results deque ---
    results = []
    while time.time() - t_start < timeout:
        with simulation_lock:
            matching = [r for r in simulation_results if r.get('run_id') == effective_run_id]
            if matching:
                remaining = deque(
                    (r for r in simulation_results if r.get('run_id') != effective_run_id),
                    maxlen=1000,
                )
                simulation_results.clear()
                simulation_results.extend(remaining)
                results = matching
                break
        time.sleep(0.25)

    elapsed_ms = int((time.time() - t_start) * 1000)

    if not results:
        return JsonResponse(
            {
                'success': False,
                'error': f'Simulation timed out after {timeout}s. The pipeline may still be starting.',
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
    return JsonResponse({
        'success': True,
        'run_id': effective_run_id,
        'slot_id': slot_id,
        'results': results,
        'count': len(results),
        'elapsed_ms': elapsed_ms,
    })
