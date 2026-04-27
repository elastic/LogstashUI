#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse

from PipelineManager.models import Revision, Policy, Connection as ConnectionTable, Keystore

from Common.decorators import require_admin_role

from datetime import datetime, timezone

import json
import secrets
import base64
import logging

logger = logging.getLogger(__name__)

@require_admin_role
def generate_enrollment_token(request):
    """
    Generate an enrollment token for Logstash Agent
    Token contains: enrollment token only (logstashui URL provided via command-line)
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        policy_name = data.get('policy_name', 'Default')

        # Generate a secure random enrollment token
        enrollment_token = secrets.token_urlsafe(32)

        # Create token payload (only enrollment_token, no URL)
        token_payload = {
            "enrollment_token": enrollment_token,
        }

        # Encode as base64
        json_string = json.dumps(token_payload)
        encoded_token = base64.b64encode(json_string.encode('utf-8')).decode('utf-8')

        logger.info(f"User '{request.user.username}' generated enrollment token for policy '{policy_name}'")

        return JsonResponse({
            "success": True,
            "enrollment_token": encoded_token,
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error generating enrollment token: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def deploy_policy(request):
    """
    Deploy a policy by:
    1. Incrementing the revision number in the Policy table
    2. Creating a new Revision record with a snapshot of the current policy state
    3. Keeping the current data in the policy (no changes to policy fields)
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
            'pipelines': list(policy.pipelines.values('name', 'description', 'lscl', 'no_input', 'non_reloadable')),
            'keystore': list(policy.keystore_entries.values('key_name', 'key_value')),
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
    """
    Get diff between current policy state and last deployed revision.
    Returns structured diff data for logstash.yml, jvm.options, log4j2.properties, pipelines, and keystore.
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

        # Get current policy state
        current_state = {
            'logstash_yml': policy.logstash_yml,
            'jvm_options': policy.jvm_options,
            'log4j2_properties': policy.log4j2_properties,
            'settings_path': policy.settings_path,
            'logs_path': policy.logs_path,
            'binary_path': policy.binary_path,
            'pipelines': list(policy.pipelines.values('name', 'description', 'lscl', 'no_input', 'non_reloadable')),
            'keystore': list(policy.keystore_entries.values('key_name', 'key_value')),
            'keystore_password_hash': policy.keystore_password_hash
        }

        # Get last revision (if any)
        last_revision = policy.revisions.first()  # Already ordered by -revision_number

        if last_revision:
            # Compare with last revision
            previous_state = last_revision.snapshot_json
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
    """
    Get the count of agents (connections) using a specific policy
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
    """
    Returns the number of sections (tabs) that have pending changes compared to the last deployed revision.
    Sections: logstash_yml, jvm_options, log4j2_properties, pipelines, keystore, global_settings
    """
    try:
        policy_id = request.GET.get('policy_id')
        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)

        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

        last_revision = policy.revisions.first()
        if last_revision:
            prev = last_revision.snapshot_json
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

        # Pipelines: compare sorted list of {name, lscl}
        curr_pipelines = sorted(
            [{'name': p['name'], 'lscl': p['lscl']}
             for p in policy.pipelines.values('name', 'lscl')],
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
             for e in policy.keystore_entries.values('key_name', 'key_value')],
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
    """
    Get all keystore entries for a specific policy.
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

        # Get all keystore entries for this policy
        entries = Keystore.objects.filter(policy=policy)

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
    """
    Set or update the keystore password for a policy.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        policy_id = data.get('policy_id')
        password = data.get('password')

        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)
        if not password:
            return JsonResponse({"success": False, "error": "Password cannot be empty"}, status=400)

        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

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
    """
    Create a new keystore entry for a policy.
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
    """
    Update an existing keystore entry.
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
    """
    Delete a keystore entry.
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
    """
    Get all nodes (connections) associated with a specific policy.
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
                "agent_version": node.status_blob.get('agent_version') if node.status_blob else None
            })

        return JsonResponse({
            "success": True,
            "nodes": nodes_data,
            "policy_name": policy.name
        })

    except Exception as e:
        logger.error(f"Error getting policy nodes: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
