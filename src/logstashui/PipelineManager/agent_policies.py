#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""HTTP views for policy deploy, diffs, keystore, and assigned nodes."""

from django.http import JsonResponse

from PipelineManager.models import Revision, Policy, Connection as ConnectionTable, Keystore
from PipelineManager.agent_versions import resolve_running_logstash_version

from Common.decorators import require_admin_role

from datetime import datetime, timezone

import json
import logging

logger = logging.getLogger(__name__)

def _strip_nonuser_from_snapshot(snapshot, nonuser_pipeline_names, nonuser_key_names):
    """Return a snapshot copy with currently non-user pipeline/keystore names removed.

    Revision snapshots taken before the user-only allowlist may have captured
    SNMP artifacts. Stripping them on read keeps diffs/change-counts honest
    without needing to rewrite historical revision records.

    Args:
        snapshot: Revision ``snapshot_json`` dict.
        nonuser_pipeline_names: Pipeline names to drop.
        nonuser_key_names: Keystore key names to drop.
    """
    if not snapshot:
        return snapshot
    cleaned = dict(snapshot)
    cleaned['pipelines'] = [
        p for p in snapshot.get('pipelines', [])
        if p.get('name') not in nonuser_pipeline_names
    ]
    cleaned['keystore'] = [
        e for e in snapshot.get('keystore', [])
        if e.get('key_name') not in nonuser_key_names
    ]
    return cleaned


@require_admin_role
def deploy_policy(request):
    """Snapshot user-authored policy state as a new revision.

    Increments ``current_revision_number``, writes a ``Revision`` row, and
    leaves live policy fields unchanged. SNMP artifacts are excluded.

    Args:
        policy_id: Policy primary key.
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
            'binary_path': policy.binary_path,
            # Agent policies own ONLY user-authored artifacts. SNMP (and any
            # future managed subsystem) is deployed on its own channel and must
            # never enter policy revisions/rollback history.
            'pipelines': list(policy.pipelines.filter(managed_by='user').values('name', 'description', 'lscl', 'no_input', 'non_reloadable')),
            'keystore': list(policy.keystore_entries.filter(managed_by='user').values('key_name', 'key_value')),
            'keystore_password_hash': policy.keystore_password_hash
        }

        # Create new Revision record
        revision = Revision.objects.create(
            policy=policy,
            revision_number=new_revision_number,
            snapshot_json=snapshot_data,
            created_by=request.user.username
        )

        # Save the policy with updated revision number and deployment timestamp
        policy.last_deployed_at = datetime.now(timezone.utc)
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


@require_admin_role
def get_policy_diff(request):
    """Return current vs last-deployed policy state for the diff UI.

    Args:
        policy_id: Policy primary key.

    Returns:
        JSON with ``current`` and ``previous`` snapshots of yml, jvm,
        log4j2, pipelines, and keystore.
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

        # Get current policy state (user-authored artifacts only; SNMP/managed
        # artifacts live on their own channel and are never part of the policy).
        current_state = {
            'logstash_yml': policy.logstash_yml,
            'jvm_options': policy.jvm_options,
            'log4j2_properties': policy.log4j2_properties,
            'settings_path': policy.settings_path,
            'logs_path': policy.logs_path,
            'binary_path': policy.binary_path,
            'pipelines': list(policy.pipelines.filter(managed_by='user').values('name', 'description', 'lscl', 'no_input', 'non_reloadable')),
            'keystore': list(policy.keystore_entries.filter(managed_by='user').values('key_name', 'key_value')),
            'keystore_password_hash': policy.keystore_password_hash
        }

        # Names of non-user artifacts currently on the policy. Older revision
        # snapshots may have captured these before the allowlist existed; strip
        # them from the previous state so the diff doesn't show phantom removals.
        nonuser_pipeline_names = set(
            policy.pipelines.exclude(managed_by='user').values_list('name', flat=True)
        )
        nonuser_key_names = set(
            policy.keystore_entries.exclude(managed_by='user').values_list('key_name', flat=True)
        )

        # Get last revision (if any)
        last_revision = policy.revisions.first()  # Already ordered by -revision_number

        if last_revision:
            # Compare with last revision
            previous_state = _strip_nonuser_from_snapshot(
                last_revision.snapshot_json, nonuser_pipeline_names, nonuser_key_names
            )
            revision_number = last_revision.revision_number
        else:
            # No previous revision - compare with empty state
            previous_state = {
                'logstash_yml': '',
                'jvm_options': '',
                'log4j2_properties': '',
                'settings_path': '',
                'logs_path': '',
                'binary_path': '',
                'pipelines': [],
                'keystore': [],
                'keystore_password_hash': ''
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
def get_policy_agent_count(request):
    """Return the number of active agents assigned to a policy.

    Args:
        policy_id: Policy primary key.
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

        # Count connections using this policy
        agent_count = ConnectionTable.objects.filter(
            policy=policy,
            connection_type=ConnectionTable.ConnectionType.AGENT,
            is_active=True
        ).count()

        return JsonResponse({
            "success": True,
            "agent_count": agent_count,
            "policy_name": policy.name
        })

    except Exception as e:
        logger.error(f"Error getting policy agent count: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def get_policy_change_count(request):
    """Count policy tabs with pending changes vs the last deployed revision.

    Sections: logstash_yml, jvm_options, log4j2_properties, pipelines,
    keystore, keystore password, global settings.

    Args:
        policy_id: Policy primary key.

    Returns:
        JSON ``{"success": True, "pending_changes": N}``.
    """
    try:
        policy_id = request.GET.get('policy_id')
        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)

        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

        # Names of non-user artifacts to ignore on both sides (SNMP etc.).
        nonuser_pipeline_names = set(
            policy.pipelines.exclude(managed_by='user').values_list('name', flat=True)
        )
        nonuser_key_names = set(
            policy.keystore_entries.exclude(managed_by='user').values_list('key_name', flat=True)
        )

        last_revision = policy.revisions.first()
        if last_revision:
            prev = _strip_nonuser_from_snapshot(
                last_revision.snapshot_json, nonuser_pipeline_names, nonuser_key_names
            )
        else:
            prev = {
                'logstash_yml': '', 'jvm_options': '', 'log4j2_properties': '',
                'settings_path': '', 'logs_path': '', 'binary_path': '',
                'pipelines': [], 'keystore': [], 'keystore_password_hash': ''
            }

        count = 0

        if policy.logstash_yml != prev.get('logstash_yml', ''):
            count += 1
        if policy.jvm_options != prev.get('jvm_options', ''):
            count += 1
        if policy.log4j2_properties != prev.get('log4j2_properties', ''):
            count += 1

        # Pipelines: compare sorted list of {name, lscl} (user-authored only)
        curr_pipelines = sorted(
            [{'name': p['name'], 'lscl': p['lscl']}
             for p in policy.pipelines.filter(managed_by='user').values('name', 'lscl')],
            key=lambda p: p['name']
        )
        prev_pipelines = sorted(
            [{'name': p['name'], 'lscl': p['lscl']}
             for p in prev.get('pipelines', [])
             if 'name' in p and 'lscl' in p],
            key=lambda p: p['name']
        )
        if curr_pipelines != prev_pipelines:
            count += 1

        # Keystore: compare by key names and encrypted values in snapshot
        curr_keystore = sorted(
            [{'key_name': e['key_name'], 'key_value': e['key_value']}
             for e in policy.keystore_entries.filter(managed_by='user').values('key_name', 'key_value')],
            key=lambda e: e['key_name']
        )
        prev_keystore = sorted(
            [{'key_name': e['key_name'], 'key_value': e.get('key_value', '')}
             for e in prev.get('keystore', []) if 'key_name' in e],
            key=lambda e: e['key_name']
        )
        if curr_keystore != prev_keystore:
            count += 1

        # Keystore password: compare hash
        if policy.keystore_password_hash != prev.get('keystore_password_hash', ''):
            count += 1

        # Global settings: settings_path, logs_path, binary_path
        if (policy.settings_path != prev.get('settings_path', '') or
                policy.logs_path != prev.get('logs_path', '') or
                policy.binary_path != prev.get('binary_path', '')):
            count += 1

        return JsonResponse({"success": True, "pending_changes": count})

    except Exception as e:
        logger.error(f"Error getting policy change count: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def get_keystore_entries(request):
    """Return user-authored keystore entries for a policy.

    Args:
        policy_id: Policy primary key.
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

        # User-authored keystore entries only. SNMP/managed secrets are
        # provisioned automatically and are never shown or edited here.
        entries = Keystore.objects.filter(policy=policy, managed_by='user')

        # Serialize entries
        entries_data = []
        for entry in entries:
            entries_data.append({
                "id": entry.id,
                "key_name": entry.key_name,
                "key_value": entry.key_value,
                "last_updated": entry.last_updated.isoformat()
            })

        return JsonResponse({
            "success": True,
            "entries": entries_data,
            "has_keystore_password": bool(policy.keystore_password)
        })

    except Exception as e:
        logger.error(f"Error fetching keystore entries: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def set_keystore_password(request):
    """Set, rotate, or clear the keystore password for a policy.

    Args:
        policy_id: Policy primary key (required).
        password: Non-empty string to set/rotate (required unless ``clear``).
        clear: If true, remove the password so agents migrate back to
            unauthenticated keystores on next check-in.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        policy_id = data.get('policy_id')
        password = data.get('password')
        clear = bool(data.get('clear'))

        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)

        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

        if clear:
            policy.keystore_password = ''
            policy.has_undeployed_changes = True
            policy.save()  # save() clears keystore_password_hash when password empty
            logger.info(
                f"User '{request.user.username}' cleared keystore password for policy '{policy.name}'"
            )
            return JsonResponse({
                "success": True,
                "message": "Keystore password cleared; agents will switch to unauthenticated mode on next check-in",
            })

        if not password:
            return JsonResponse({"success": False, "error": "Password cannot be empty"}, status=400)

        policy.keystore_password = password  # save() will encrypt and hash it
        policy.has_undeployed_changes = True
        policy.save()

        logger.info(f"User '{request.user.username}' set keystore password for policy '{policy.name}'")

        return JsonResponse({
            "success": True,
            "message": "Keystore password updated successfully"
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error setting keystore password: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def create_keystore_entry(request):
    """Create a user-authored keystore entry for a policy.

    Args:
        policy_id: Policy primary key.
        key_name: Unique key within the policy.
        key_value: Plaintext value (encrypted on save).
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        policy_id = data.get('policy_id')
        key_name = data.get('key_name')
        key_value = data.get('key_value')

        if not policy_id or not key_name or not key_value:
            return JsonResponse({"success": False, "error": "Policy ID, key name, and key value are required"},
                                status=400)

        # Get the policy
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

        # Check if key already exists for this policy
        if Keystore.objects.filter(policy=policy, key_name=key_name).exists():
            return JsonResponse({"success": False, "error": f"Key '{key_name}' already exists for this policy"},
                                status=400)

        # Create keystore entry
        entry = Keystore.objects.create(
            policy=policy,
            key_name=key_name,
            key_value=key_value
        )

        logger.info(f"User '{request.user.username}' created keystore entry '{key_name}' for policy '{policy.name}'")

        return JsonResponse({
            "success": True,
            "message": f"Keystore entry '{key_name}' created successfully",
            "entry_id": entry.id
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error creating keystore entry: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def update_keystore_entry(request):
    """Update a keystore entry's value.

    Args:
        entry_id: ``Keystore`` primary key.
        key_value: New plaintext value.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        entry_id = data.get('entry_id')
        key_value = data.get('key_value')

        if not entry_id or not key_value:
            return JsonResponse({"success": False, "error": "Entry ID and key value are required"}, status=400)

        # Get and update the entry
        try:
            entry = Keystore.objects.get(id=entry_id)
            entry.key_value = key_value
            entry.save()

            logger.info(
                f"User '{request.user.username}' updated keystore entry '{entry.key_name}' for policy '{entry.policy.name}'")

            return JsonResponse({
                "success": True,
                "message": f"Keystore entry '{entry.key_name}' updated successfully"
            })

        except Keystore.DoesNotExist:
            return JsonResponse({"success": False, "error": "Keystore entry not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error updating keystore entry: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def delete_keystore_entry(request):
    """Delete a keystore entry.

    Args:
        entry_id: ``Keystore`` primary key.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        entry_id = data.get('entry_id')

        if not entry_id:
            return JsonResponse({"success": False, "error": "Entry ID is required"}, status=400)

        # Get and delete the entry
        try:
            entry = Keystore.objects.get(id=entry_id)
            key_name = entry.key_name
            policy_name = entry.policy.name
            entry.delete()

            logger.info(
                f"User '{request.user.username}' deleted keystore entry '{key_name}' for policy '{policy_name}'")

            return JsonResponse({
                "success": True,
                "message": f"Keystore entry '{key_name}' deleted successfully"
            })

        except Keystore.DoesNotExist:
            return JsonResponse({"success": False, "error": "Keystore entry not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error deleting keystore entry: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def get_policy_nodes(request):
    """Return active agent connections for a policy, with health and SNMP flags.

    Args:
        policy_id: Policy primary key.
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

        # Get all active agent connections for this policy
        nodes = ConnectionTable.objects.filter(
            policy=policy,
            connection_type=ConnectionTable.ConnectionType.AGENT,
            is_active=True
        ).order_by('name')

        # CPM involvement is policy-level: the policy's logstash.yml enabling
        # centralized pipeline management applies to every agent on the policy.
        from .manager_views import _logstash_yml_cpm_enabled
        cpm_enabled = _logstash_yml_cpm_enabled(policy.logstash_yml)

        # Per-agent SNMP involvement (networks assigned to this agent connection)
        from SNMP.models import Network
        snmp_networks_by_conn = {}
        for net_name, conn_id in Network.objects.filter(
            deployment_mode='AGENT', agent_connection__isnull=False
        ).values_list('name', 'agent_connection_id'):
            snmp_networks_by_conn.setdefault(conn_id, []).append(net_name)

        # Serialize nodes
        nodes_data = []
        now = datetime.now(timezone.utc)
        
        for node in nodes:
            # Compute is_online based on last_check_in (within 10 minutes)
            is_online = False
            if node.last_check_in:
                time_diff = now - node.last_check_in
                is_online = time_diff.total_seconds() < 600  # 10 minutes = 600 seconds
            
            # Determine status
            status = 'offline'
            status_class = 'bg-red-100 text-red-800'
            
            if node.status_blob and node.status_blob.get('logwatcher', {}).get('is_restarting'):
                status = 'restarting'
                status_class = 'bg-blue-100 text-blue-800'
            elif not is_online:
                status = 'offline'
                status_class = 'bg-red-100 text-red-800'
            elif node.status_blob and (
                node.status_blob.get('settings_path_found') == False or
                node.status_blob.get('logs_path_found') == False or
                node.status_blob.get('binary_path_found') == False or
                node.status_blob.get('logstash_api', {}).get('accessible') == False or
                node.status_blob.get('logstash_api', {}).get('status') == 'red' or
                node.status_blob.get('last_policy_apply', {}).get('success') == False):
                status = 'unhealthy'
                status_class = 'bg-yellow-100 text-yellow-800'
            else:
                status = 'healthy'
                status_class = 'bg-green-100 text-green-800'

            nodes_data.append({
                "id": node.id,
                "name": node.name,
                "host": node.host or '',
                "connection_type": node.connection_type,
                "status": status,
                "status_class": status_class,
                "last_check_in": node.last_check_in.isoformat() if node.last_check_in else None,
                "agent_version": node.status_blob.get('agent_version') if node.status_blob else None,
                "logstash_version": resolve_running_logstash_version(
                    logstash_version_resolved=node.logstash_version_resolved,
                    status_blob=node.status_blob if isinstance(node.status_blob, dict) else None,
                ),
                "cpm_enabled": cpm_enabled,
                "snmp_networks": sorted(snmp_networks_by_conn.get(node.id, [])),
            })

        return JsonResponse({
            "success": True,
            "nodes": nodes_data,
            "policy_name": policy.name
        })

    except Exception as e:
        logger.error(f"Error getting policy nodes: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
