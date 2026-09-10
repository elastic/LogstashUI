#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""REST API views for agent policy management.

Endpoints
---------
GET    /api/policies/                     policy_list     (admin)
POST   /api/policies/                     policy_list     (admin)
GET    /api/policies/{id}/                policy_detail   (admin)
PUT    /api/policies/{id}/                policy_detail   (admin)
DELETE /api/policies/{id}/                policy_detail   (admin)
POST   /api/policies/{id}/deploy/         policy_deploy   (admin)
POST   /api/policies/{id}/clone/          policy_clone    (admin)
GET    /api/policies/{id}/diff/           policy_diff     (admin)
GET    /api/policies/{id}/tokens/         policy_tokens   (admin)
POST   /api/policies/{id}/tokens/         policy_tokens   (admin)
DELETE /api/policies/{id}/tokens/{tid}/   policy_token_detail (admin)
"""

import json
import logging
import secrets

from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from PipelineManager.models import (
    Connection as ConnectionTable,
    EnrollmentToken,
    Policy,
    Revision,
)
from PipelineManager.policies_crud import (
    get_default_jvm_options,
    get_default_log4j2_properties,
    get_default_logstash_yml,
)
from PipelineManager.agent_policies import _strip_nonuser_from_snapshot

from API.auth import api_require_admin, parse_request_body

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _policy_data(policy, active_agent_count=None):
    """Serialize a Policy instance to a JSON-safe dict.

    Sensitive fields (``keystore_password``, ``*_hash``) are excluded.
    Large text config fields (``logstash_yml``, ``jvm_options``,
    ``log4j2_properties``) are included as plain strings.
    """
    if active_agent_count is None:
        active_agent_count = ConnectionTable.objects.filter(
            policy=policy,
            connection_type=ConnectionTable.ConnectionType.AGENT,
            is_active=True,
        ).count()

    return {
        'id': policy.id,
        'name': policy.name,
        'policy_type': policy.policy_type,
        'is_system': policy.is_system,
        'cloned_from_id': policy.cloned_from_id,
        'settings_path': policy.settings_path,
        'logs_path': policy.logs_path,
        'binary_path': policy.binary_path,
        'data_path': policy.data_path,
        'agent_api_port': policy.agent_api_port,
        'logstash_api_port': policy.logstash_api_port,
        'keystore_env_file': policy.keystore_env_file,
        'logstash_source': policy.logstash_source,
        'logstash_version': policy.logstash_version,
        'logstash_download_dir': policy.logstash_download_dir,
        'logstash_via_ui': policy.logstash_via_ui,
        'logstash_yml': policy.logstash_yml,
        'jvm_options': policy.jvm_options,
        'log4j2_properties': policy.log4j2_properties,
        'has_undeployed_changes': policy.has_undeployed_changes,
        'current_revision_number': policy.current_revision_number,
        'last_deployed_at': policy.last_deployed_at.isoformat() if policy.last_deployed_at else None,
        'active_agent_count': active_agent_count,
        'created_at': policy.created_at.isoformat(),
        'updated_at': policy.updated_at.isoformat(),
    }


def _token_data(token, include_enroll_command=False):
    """Serialize an EnrollmentToken to a dict."""
    data = {
        'id': token.id,
        'name': token.name,
        'raw_token': token.token,
    }
    if include_enroll_command:
        import base64
        from Common.product_ca import build_enrollment_token_payload, get_agent_ui_url_default
        agent_ui_url = get_agent_ui_url_default()
        payload = build_enrollment_token_payload(token.token)
        encoded = base64.b64encode(
            json.dumps(payload, separators=(',', ':')).encode()
        ).decode()
        if agent_ui_url:
            enroll_cmd = (
                f"sudo logstash-agent install --enroll={encoded} "
                f"--logstash-ui-url={agent_ui_url}"
            )
        else:
            enroll_cmd = (
                f"sudo logstash-agent install --enroll={encoded} "
                f"--logstash-ui-url=<UI_URL>"
            )
        data['encoded_token'] = encoded
        data['enroll_command'] = enroll_cmd
        data['agent_ui_url'] = agent_ui_url or ''
    return data


# ---------------------------------------------------------------------------
# /api/policies/  — list + create
# ---------------------------------------------------------------------------

@csrf_exempt
def policy_list(request):
    """List all non-EMBEDDED policies or create a new one.

    GET  /api/policies/
        Returns all non-EMBEDDED policies with active agent count.
        Admin only.

    POST /api/policies/
        Create a new policy (PACKAGED, MANAGED, or SIMULATE).
        Mints a default enrollment token automatically.
        Admin only.
    """
    if request.method == 'GET':
        return _list_policies(request)
    if request.method == 'POST':
        return _create_policy(request)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_admin
def _list_policies(request):
    qs = Policy.objects.annotate(
        active_agent_count=Count(
            'connections',
            filter=Q(connections__connection_type='AGENT', connections__is_active=True),
        )
    ).exclude(policy_type=Policy.PolicyType.EMBEDDED).order_by('name')

    policies = []
    for p in qs:
        d = _policy_data(p, active_agent_count=p.active_agent_count)
        policies.append(d)

    return JsonResponse({'success': True, 'policies': policies, 'total': len(policies)})


@api_require_admin
def _create_policy(request):
    from PipelineManager.agent_modes import (
        MANAGED_AGENT_API_BASE,
        MANAGED_LOGSTASH_API_BASE,
        PACKAGED_AGENT_API_PORT,
        PACKAGED_LOGSTASH_API_PORT,
        SIMULATE_AGENT_API_BASE,
        SIMULATE_LOGSTASH_API_BASE,
        apply_managed_path_bundle,
        apply_simulate_path_bundle,
        normalize_agent_opt_path,
        parse_creatable_policy_type,
        uses_packaged_default_paths,
    )
    from PipelineManager.agent_versions import resolve_persisted_binary_path

    data = parse_request_body(request)

    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'Policy name is required.'}, status=400)

    if Policy.objects.filter(name=name).exists():
        return JsonResponse(
            {'success': False, 'error': f"Policy '{name}' already exists."}, status=409
        )

    policy_type, type_error = parse_creatable_policy_type(data.get('policy_type'))
    if type_error:
        return JsonResponse({'success': False, 'error': type_error}, status=400)

    def _optional_int(key, default):
        raw = data.get(key, default)
        if raw is None or raw == '':
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    if policy_type == Policy.PolicyType.MANAGED:
        agent_port_default, ls_port_default = MANAGED_AGENT_API_BASE, MANAGED_LOGSTASH_API_BASE
    elif policy_type == Policy.PolicyType.SIMULATE:
        agent_port_default, ls_port_default = SIMULATE_AGENT_API_BASE, SIMULATE_LOGSTASH_API_BASE
    else:
        agent_port_default, ls_port_default = PACKAGED_AGENT_API_PORT, PACKAGED_LOGSTASH_API_PORT

    logstash_yml = data.get('logstash_yml') or get_default_logstash_yml()
    jvm_options = data.get('jvm_options') or get_default_jvm_options()
    log4j2_properties = data.get('log4j2_properties') or get_default_log4j2_properties()

    try:
        policy = Policy.objects.create(
            name=name,
            policy_type=policy_type,
            settings_path=normalize_agent_opt_path(data.get('settings_path', '/etc/logstash/')) or '/etc/logstash/',
            logs_path=normalize_agent_opt_path(data.get('logs_path', '/var/log/logstash')) or '/var/log/logstash',
            binary_path=normalize_agent_opt_path(data.get('binary_path', '/usr/share/logstash/bin')) or '/usr/share/logstash/bin',
            data_path=normalize_agent_opt_path(data.get('data_path', '')),
            keystore_env_file=normalize_agent_opt_path(
                data.get('keystore_env_file') or '/etc/default/logstash'
            ) or '/etc/default/logstash',
            logstash_source=data.get('logstash_source') or Policy.LogstashSource.SYSTEM,
            logstash_version=data.get('logstash_version') or '',
            logstash_download_dir=normalize_agent_opt_path(
                data.get('logstash_download_dir') or '/opt/logstash-agent/logstash-versions'
            ) or '/opt/logstash-agent/logstash-versions',
            logstash_via_ui=bool(data.get('logstash_via_ui', False)),
            agent_api_port=_optional_int('agent_api_port', agent_port_default),
            logstash_api_port=_optional_int('logstash_api_port', ls_port_default),
            logstash_yml=logstash_yml,
            jvm_options=jvm_options,
            log4j2_properties=log4j2_properties,
        )
    except Exception as exc:
        logger.error("API create policy: %s", exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    if policy_type == Policy.PolicyType.MANAGED and uses_packaged_default_paths(policy):
        apply_managed_path_bundle(policy)
        policy.save()
    elif policy_type == Policy.PolicyType.SIMULATE and uses_packaged_default_paths(policy):
        apply_simulate_path_bundle(policy)
        policy.save()

    resolved_binary = resolve_persisted_binary_path(
        source=policy.logstash_source,
        version=policy.logstash_version,
        download_dir=policy.logstash_download_dir,
        binary_path=policy.binary_path,
    )
    if resolved_binary != policy.binary_path:
        policy.binary_path = resolved_binary
        policy.save(update_fields=['binary_path'])

    # Auto-mint default enrollment token
    enrollment_token = secrets.token_urlsafe(32)
    EnrollmentToken.objects.create(policy=policy, name='default', token=enrollment_token)

    logger.info(
        "API: policy '%s' (%s) created by %s.", name, policy.policy_type, request.user.username
    )
    return JsonResponse({
        'success': True,
        'message': f"Policy '{name}' created successfully.",
        'id': policy.id,
        'name': policy.name,
        'policy_type': policy.policy_type,
    }, status=201)


# ---------------------------------------------------------------------------
# /api/policies/{id}/  — read, update, delete
# ---------------------------------------------------------------------------

@csrf_exempt
def policy_detail(request, policy_id):
    """Read, update, or delete a single policy.

    GET    /api/policies/{id}/   admin only
    PUT    /api/policies/{id}/   admin only; type immutable, system path-lock enforced
    DELETE /api/policies/{id}/   admin only; non-system, no connections
    """
    if request.method == 'GET':
        return _get_policy(request, policy_id)
    if request.method == 'PUT':
        return _update_policy(request, policy_id)
    if request.method == 'DELETE':
        return _delete_policy(request, policy_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_admin
def _get_policy(request, policy_id):
    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)
    return JsonResponse({'success': True, 'policy': _policy_data(policy)})


@api_require_admin
def _update_policy(request, policy_id):
    from PipelineManager.agent_modes import normalize_agent_opt_path, normalize_policy_type
    from PipelineManager.agent_versions import resolve_persisted_binary_path

    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    if policy.policy_type == Policy.PolicyType.EMBEDDED:
        return JsonResponse(
            {'success': False, 'error': 'Cannot update EMBEDDED policy (immutable).'}, status=403
        )

    data = parse_request_body(request)

    # Guard: type cannot change (Bug 6 fix: was incorrectly 403; 400 is correct for
    # a bad-request / validation error, not a permission error)
    if 'policy_type' in data and data['policy_type'] is not None and str(data['policy_type']).strip():
        if normalize_policy_type(data['policy_type']) != normalize_policy_type(policy.policy_type):
            return JsonResponse(
                {'success': False, 'error': 'Cannot change policy type.'}, status=400
            )

    is_system_path_locked = (
        policy.is_system and policy.policy_type in (
            Policy.PolicyType.SIMULATE, Policy.PolicyType.MANAGED
        )
    )

    if is_system_path_locked:
        # Allowlisted fields only
        allowed = ('jvm_options', 'logstash_yml', 'log4j2_properties', 'logstash_source',
                   'logstash_version', 'logstash_download_dir', 'logstash_via_ui', 'binary_path')
        for field in allowed:
            if field not in data:
                continue
            if field in ('logstash_download_dir', 'binary_path'):
                setattr(policy, field,
                        normalize_agent_opt_path(data[field]) or data[field])
            elif field == 'logstash_via_ui':
                policy.logstash_via_ui = bool(data[field])
            else:
                setattr(policy, field, data[field])
        # Force-correct legacy opt root on locked path fields
        for path_field in ('settings_path', 'logs_path', 'data_path', 'keystore_env_file'):
            val = getattr(policy, path_field, '')
            setattr(policy, path_field, normalize_agent_opt_path(val) or val)
    else:
        # Full editable fields for user-owned policies
        str_path_fields = {
            'settings_path', 'logs_path', 'binary_path', 'data_path', 'keystore_env_file',
            'logstash_download_dir',
        }
        for field in str_path_fields:
            if field in data:
                setattr(policy, field, normalize_agent_opt_path(data[field]) or data[field])

        for field in ('logstash_source', 'logstash_version', 'logstash_yml',
                      'jvm_options', 'log4j2_properties'):
            if field in data:
                setattr(policy, field, data[field])

        if 'logstash_via_ui' in data:
            policy.logstash_via_ui = bool(data['logstash_via_ui'])

        for port_field in ('agent_api_port', 'logstash_api_port'):
            if port_field in data and data[port_field] is not None:
                try:
                    setattr(policy, port_field, int(data[port_field]))
                except (TypeError, ValueError):
                    pass

    policy.binary_path = resolve_persisted_binary_path(
        source=policy.logstash_source,
        version=policy.logstash_version,
        download_dir=policy.logstash_download_dir,
        binary_path=policy.binary_path,
    )

    try:
        policy.save()
    except Exception as exc:
        logger.error("API update policy %s: %s", policy_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    logger.info("API: policy '%s' updated by %s.", policy.name, request.user.username)
    return JsonResponse({
        'success': True,
        'message': f"Policy '{policy.name}' updated successfully.",
    })


@api_require_admin
def _delete_policy(request, policy_id):
    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    if policy.is_system:
        return JsonResponse(
            {'success': False, 'error': f"Cannot delete system policy '{policy.name}'."}, status=403
        )

    connections_count = policy.connections.count()
    if connections_count > 0:
        return JsonResponse(
            {'success': False,
             'error': f"Cannot delete '{policy.name}' — it is assigned to {connections_count} connection(s)."},
            status=400,
        )

    name = policy.name
    policy.delete()
    logger.warning("API: policy '%s' (id=%s) deleted by %s.", name, policy_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Policy '{name}' deleted."})


# ---------------------------------------------------------------------------
# /api/policies/{id}/deploy/
# ---------------------------------------------------------------------------

@csrf_exempt
def policy_deploy(request, policy_id):
    """Snapshot user-authored policy state as a new Revision.

    POST /api/policies/{id}/deploy/
        Increments ``current_revision_number``, writes a ``Revision`` row
        (user pipelines + user keystore only; SNMP excluded), and sets
        ``last_deployed_at``. Admin only.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    return _do_deploy(request, policy_id)


@api_require_admin
def _do_deploy(request, policy_id):
    from datetime import datetime, timezone

    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    policy.current_revision_number += 1
    new_rev = policy.current_revision_number

    snapshot = {
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
        revision_number=new_rev,
        snapshot_json=snapshot,
        created_by=request.user.username,
    )

    policy.last_deployed_at = datetime.now(timezone.utc)
    # Bug 5 fix: clear the undeployed-changes flag after a successful deploy.
    policy.has_undeployed_changes = False
    policy.save()

    logger.info(
        "API: policy '%s' deployed as revision %s by %s.",
        policy.name, new_rev, request.user.username,
    )
    return JsonResponse({
        'success': True,
        'message': f"Policy deployed as revision {new_rev}.",
        'revision_number': new_rev,
        'policy_name': policy.name,
        'last_deployed_at': policy.last_deployed_at.isoformat(),
    })


# ---------------------------------------------------------------------------
# /api/policies/{id}/clone/
# ---------------------------------------------------------------------------

@csrf_exempt
def policy_clone(request, policy_id):
    """Clone a policy with its pipelines and keystore entries.

    POST /api/policies/{id}/clone/
        Body: ``{ "new_name": "..." }``
        PACKAGED/DEFAULT clones become MANAGED (path scheme rewritten).
        EMBEDDED cannot be cloned.
        Admin only.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    return _do_clone(request, policy_id)


@api_require_admin
def _do_clone(request, policy_id):
    from PipelineManager.agent_modes import (
        apply_managed_path_bundle,
        normalize_agent_opt_path,
        normalize_policy_type,
    )
    from PipelineManager.models import Keystore, Pipeline

    try:
        source = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    if source.policy_type == Policy.PolicyType.EMBEDDED:
        return JsonResponse(
            {'success': False, 'error': 'Cannot clone EMBEDDED policy.'}, status=403
        )

    data = parse_request_body(request)
    new_name = (data.get('new_name') or '').strip()
    if not new_name:
        return JsonResponse({'success': False, 'error': 'new_name is required.'}, status=400)

    if Policy.objects.filter(name=new_name).exists():
        return JsonResponse(
            {'success': False, 'error': f"Policy '{new_name}' already exists."}, status=409
        )

    source_type = normalize_policy_type(source.policy_type)
    if source_type in (Policy.PolicyType.PACKAGED, Policy.PolicyType.DEFAULT, 'DEFAULT'):
        cloned_type = Policy.PolicyType.MANAGED
    elif source_type == Policy.PolicyType.SIMULATE:
        cloned_type = Policy.PolicyType.SIMULATE
    else:
        cloned_type = Policy.PolicyType.MANAGED

    try:
        new_policy = Policy.objects.create(
            name=new_name,
            policy_type=cloned_type,
            is_system=False,
            cloned_from=source,
            settings_path=normalize_agent_opt_path(source.settings_path),
            logs_path=normalize_agent_opt_path(source.logs_path),
            binary_path=normalize_agent_opt_path(source.binary_path) or source.binary_path,
            data_path=normalize_agent_opt_path(source.data_path),
            agent_api_port=source.agent_api_port,
            logstash_api_port=source.logstash_api_port,
            keystore_env_file=normalize_agent_opt_path(source.keystore_env_file),
            logstash_source=source.logstash_source,
            logstash_version=source.logstash_version,
            logstash_download_dir=normalize_agent_opt_path(source.logstash_download_dir) or source.logstash_download_dir,
            logstash_via_ui=source.logstash_via_ui,
            logstash_yml=source.logstash_yml,
            jvm_options=source.jvm_options,
            log4j2_properties=source.log4j2_properties,
            keystore_password=source.keystore_password,
            keystore_password_hash=source.keystore_password_hash,
        )
    except Exception as exc:
        logger.error("API clone policy %s: %s", policy_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    if cloned_type == Policy.PolicyType.MANAGED and source_type in (
        Policy.PolicyType.PACKAGED, Policy.PolicyType.DEFAULT, 'DEFAULT'
    ):
        apply_managed_path_bundle(new_policy)
        new_policy.save()

    # Default enrollment token
    EnrollmentToken.objects.create(
        policy=new_policy, name='default', token=secrets.token_urlsafe(32)
    )

    # Clone pipelines
    for p in Pipeline.objects.filter(policy=source):
        Pipeline.objects.create(
            policy=new_policy,
            name=p.name,
            description=p.description,
            lscl=p.lscl,
            pipeline_workers=p.pipeline_workers,
            pipeline_batch_size=p.pipeline_batch_size,
            pipeline_batch_delay=p.pipeline_batch_delay,
            queue_type=p.queue_type,
            queue_max_bytes=p.queue_max_bytes,
            queue_checkpoint_writes=p.queue_checkpoint_writes,
        )

    # Clone keystore entries
    for e in Keystore.objects.filter(policy=source):
        Keystore.objects.create(
            policy=new_policy,
            key_name=e.key_name,
            key_value=e.key_value,
            kv_hash=e.kv_hash,
        )

    logger.info(
        "API: policy '%s' cloned to '%s' (id=%s) by %s.",
        source.name, new_name, new_policy.id, request.user.username,
    )
    return JsonResponse({
        'success': True,
        'message': f"Policy '{new_name}' cloned from '{source.name}'.",
        'id': new_policy.id,
        'name': new_policy.name,
        'policy_type': new_policy.policy_type,
    }, status=201)


# ---------------------------------------------------------------------------
# /api/policies/{id}/diff/
# ---------------------------------------------------------------------------

@csrf_exempt
def policy_diff(request, policy_id):
    """Return current vs last-deployed policy state (user artifacts only).

    GET /api/policies/{id}/diff/
        Returns ``current`` and ``previous`` snapshots and a pending change
        count across yml, jvm, log4j2, pipelines, keystore, paths.
        Admin only.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    return _do_diff(request, policy_id)


@api_require_admin
def _do_diff(request, policy_id):
    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    current_state = {
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

    nonuser_pipeline_names = set(
        policy.pipelines.exclude(managed_by='user').values_list('name', flat=True)
    )
    nonuser_key_names = set(
        policy.keystore_entries.exclude(managed_by='user').values_list('key_name', flat=True)
    )

    last_revision = policy.revisions.first()
    if last_revision:
        previous_state = _strip_nonuser_from_snapshot(
            last_revision.snapshot_json, nonuser_pipeline_names, nonuser_key_names
        )
        last_deployed_revision = last_revision.revision_number
    else:
        previous_state = {
            'logstash_yml': '', 'jvm_options': '', 'log4j2_properties': '',
            'settings_path': '', 'logs_path': '', 'binary_path': '',
            'pipelines': [], 'keystore': [], 'keystore_password_hash': '',
        }
        last_deployed_revision = 0

    # Count changed sections
    pending_changes = 0
    for field in ('logstash_yml', 'jvm_options', 'log4j2_properties'):
        if current_state[field] != previous_state.get(field, ''):
            pending_changes += 1

    curr_pipes = sorted(
        [{'name': p['name'], 'lscl': p['lscl']} for p in current_state['pipelines']],
        key=lambda x: x['name'],
    )
    prev_pipes = sorted(
        [{'name': p['name'], 'lscl': p['lscl']} for p in previous_state.get('pipelines', [])
         if 'name' in p and 'lscl' in p],
        key=lambda x: x['name'],
    )
    if curr_pipes != prev_pipes:
        pending_changes += 1

    curr_ks = sorted(
        [{'key_name': e['key_name'], 'key_value': e['key_value']} for e in current_state['keystore']],
        key=lambda x: x['key_name'],
    )
    prev_ks = sorted(
        [{'key_name': e['key_name'], 'key_value': e.get('key_value', '')} for e in previous_state.get('keystore', [])
         if 'key_name' in e],
        key=lambda x: x['key_name'],
    )
    if curr_ks != prev_ks:
        pending_changes += 1

    if current_state['keystore_password_hash'] != previous_state.get('keystore_password_hash', ''):
        pending_changes += 1

    if (current_state['settings_path'] != previous_state.get('settings_path', '') or
            current_state['logs_path'] != previous_state.get('logs_path', '') or
            current_state['binary_path'] != previous_state.get('binary_path', '')):
        pending_changes += 1

    # Bug 7 fix: derive has_undeployed_changes from the computed pending_changes
    # count so the two fields are always consistent.  The stored flag can lag
    # (e.g. it starts True on a brand-new policy) but the diff calculation is
    # always authoritative.
    return JsonResponse({
        'success': True,
        'policy_name': policy.name,
        'current_revision': policy.current_revision_number,
        'last_deployed_revision': last_deployed_revision,
        'has_undeployed_changes': pending_changes > 0,
        'pending_changes': pending_changes,
        'current': current_state,
        'previous': previous_state,
    })


# ---------------------------------------------------------------------------
# /api/policies/{id}/tokens/  — list + create
# /api/policies/{id}/tokens/{tid}/  — delete
# ---------------------------------------------------------------------------

@csrf_exempt
def policy_tokens(request, policy_id):
    """List or create enrollment tokens for a policy.

    GET  /api/policies/{id}/tokens/   admin only
    POST /api/policies/{id}/tokens/   body: ``{ "name": "..." }`` (optional, default="default")
    """
    if request.method == 'GET':
        return _list_tokens(request, policy_id)
    if request.method == 'POST':
        return _create_token(request, policy_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_admin
def _list_tokens(request, policy_id):
    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    tokens = EnrollmentToken.objects.filter(policy=policy).order_by('id')
    return JsonResponse({
        'success': True,
        'tokens': [_token_data(t, include_enroll_command=True) for t in tokens],
    })


@api_require_admin
def _create_token(request, policy_id):
    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    data = parse_request_body(request)
    token_name = (data.get('name') or 'default').strip()

    token = EnrollmentToken.objects.create(
        policy=policy,
        name=token_name,
        token=secrets.token_urlsafe(32),
    )

    logger.info(
        "API: enrollment token '%s' (id=%s) created for policy '%s' by %s.",
        token_name, token.id, policy.name, request.user.username,
    )
    return JsonResponse({
        'success': True,
        'message': 'Enrollment token created.',
        **_token_data(token, include_enroll_command=True),
    }, status=201)


@csrf_exempt
def policy_token_detail(request, policy_id, token_id):
    """Retrieve or delete a single enrollment token.

    GET    /api/policies/{id}/tokens/{tid}/   admin only — return token detail
    DELETE /api/policies/{id}/tokens/{tid}/   admin only — permanently delete
    """
    if request.method == 'GET':
        return _get_token(request, policy_id, token_id)
    if request.method == 'DELETE':
        return _delete_token(request, policy_id, token_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_admin
def _get_token(request, policy_id, token_id):
    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    try:
        token = EnrollmentToken.objects.get(pk=token_id, policy=policy)
    except EnrollmentToken.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Token not found.'}, status=404)

    return JsonResponse({
        'success': True,
        'policy_id': policy_id,
        **_token_data(token, include_enroll_command=True),
    })


@api_require_admin
def _delete_token(request, policy_id, token_id):
    try:
        policy = Policy.objects.get(pk=policy_id)
    except Policy.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Policy not found.'}, status=404)

    try:
        token = EnrollmentToken.objects.get(pk=token_id, policy=policy)
    except EnrollmentToken.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Token not found.'}, status=404)

    token.delete()
    logger.info(
        "API: enrollment token id=%s deleted from policy '%s' by %s.",
        token_id, policy.name, request.user.username,
    )
    return JsonResponse({'success': True, 'message': 'Token deleted.'})
