#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.decorators import require_admin_role
from PipelineManager.models import Policy, EnrollmentToken, Pipeline, Keystore, Connection as ConnectionTable
from django.http import JsonResponse

import json
import secrets
import base64
import logging
import os

logger = logging.getLogger(__name__)

@require_admin_role
def get_policies(request):
    """
    Get all policies
    """
    try:
        from django.db.models import Count, Q
        policies = list(Policy.objects.annotate(
            connection_count=Count(
                'connections',
                filter=Q(connections__connection_type='AGENT', connections__is_active=True)
            )
        ).values(
            'id', 'name', 'settings_path', 'logs_path', 'binary_path',
            'logstash_yml', 'jvm_options', 'log4j2_properties',
            'current_revision_number', 'last_deployed_at',
            'connection_count', 'created_at', 'updated_at'
        ))

        # Serialize datetime fields to ISO strings
        for p in policies:
            if p['last_deployed_at']:
                p['last_deployed_at'] = p['last_deployed_at'].isoformat()
            if p['created_at']:
                p['created_at'] = p['created_at'].isoformat()
            if p['updated_at']:
                p['updated_at'] = p['updated_at'].isoformat()

        return JsonResponse({
            "success": True,
            "policies": policies
        })

    except Exception as e:
        logger.error(f"Error fetching policies: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def add_policy(request):
    """
    Create a new policy
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)

        name = data.get('name', '').strip()
        settings_path = data.get('settings_path', '/etc/logstash/')
        logs_path = data.get('logs_path', '/var/log/logstash')
        binary_path = data.get('binary_path', '/usr/share/logstash/bin')

        # Use defaults if values are empty or not provided
        logstash_yml = data.get('logstash_yml') or get_default_logstash_yml()
        jvm_options = data.get('jvm_options') or get_default_jvm_options()
        log4j2_properties = data.get('log4j2_properties') or get_default_log4j2_properties()

        if not name:
            return JsonResponse({"success": False, "error": "Policy name is required"}, status=400)

        # Check if policy already exists
        if Policy.objects.filter(name=name).exists():
            return JsonResponse({"success": False, "error": f"Policy '{name}' already exists"}, status=400)

        # Create the policy
        policy = Policy.objects.create(
            name=name,
            settings_path=settings_path,
            logs_path=logs_path,
            binary_path=binary_path,
            logstash_yml=logstash_yml,
            jvm_options=jvm_options,
            log4j2_properties=log4j2_properties
        )

        # Generate enrollment token for the new policy
        enrollment_token = secrets.token_urlsafe(32)

        # Create enrollment token record in database with name 'default'
        EnrollmentToken.objects.create(
            policy=policy,
            name='default',
            token=enrollment_token
        )

        logger.info(f"User '{request.user.username}' created policy '{name}' with enrollment token")

        return JsonResponse({
            "success": True,
            "message": f"Policy '{name}' created successfully",
            "policy_id": policy.id,
            "policy_name": policy.name
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error creating policy: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def update_policy(request):
    """
    Update an existing policy
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)

        policy_name = data.get('policy_name', '').strip()

        if not policy_name:
            return JsonResponse({"success": False, "error": "Policy name is required"}, status=400)

        # Don't allow updating Default policy
        if policy_name.lower() == 'default policy':
            return JsonResponse({"success": False, "error": "Cannot update Default Policy"}, status=403)

        try:
            policy = Policy.objects.get(name=policy_name)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": f"Policy '{policy_name}' not found"}, status=404)

        # Update fields if provided
        if 'settings_path' in data:
            policy.settings_path = data['settings_path']
        if 'logs_path' in data:
            policy.logs_path = data['logs_path']
        if 'binary_path' in data:
            policy.binary_path = data['binary_path']
        if 'logstash_yml' in data:
            policy.logstash_yml = data['logstash_yml']
        if 'jvm_options' in data:
            policy.jvm_options = data['jvm_options']
        if 'log4j2_properties' in data:
            policy.log4j2_properties = data['log4j2_properties']

        policy.save()

        logger.info(f"User '{request.user.username}' updated policy '{policy_name}'")

        return JsonResponse({
            "success": True,
            "message": f"Policy '{policy_name}' updated successfully"
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error updating policy: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def delete_policy(request):
    """
    Delete a policy
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)

        policy_name = data.get('policy_name', '').strip()

        if not policy_name:
            return JsonResponse({"success": False, "error": "Policy name is required"}, status=400)

        # Don't allow deleting Default policy
        if policy_name.lower() == 'default policy':
            return JsonResponse({"success": False, "error": "Cannot delete Default Policy"}, status=403)

        try:
            policy = Policy.objects.get(name=policy_name)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": f"Policy '{policy_name}' not found"}, status=404)

        # Check if policy is in use
        connections_count = policy.connections.count()
        if connections_count > 0:
            return JsonResponse({
                "success": False,
                "error": f"Cannot delete policy '{policy_name}' - it is currently assigned to {connections_count} connection(s)"
            }, status=400)

        policy.delete()

        logger.info(f"User '{request.user.username}' deleted policy '{policy_name}'")

        return JsonResponse({
            "success": True,
            "message": f"Policy '{policy_name}' deleted successfully"
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error deleting policy: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def clone_policy(request):
    """
    Clone an existing policy with all its pipelines and keystore entries
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)

        source_policy_id = data.get('source_policy_id')
        new_policy_name = data.get('new_policy_name', '').strip()

        if not source_policy_id:
            return JsonResponse({"success": False, "error": "Source policy ID is required"}, status=400)

        if not new_policy_name:
            return JsonResponse({"success": False, "error": "New policy name is required"}, status=400)

        # Check if new policy name already exists
        if Policy.objects.filter(name=new_policy_name).exists():
            return JsonResponse({"success": False, "error": f"Policy '{new_policy_name}' already exists"}, status=400)

        # Get source policy
        try:
            source_policy = Policy.objects.get(pk=source_policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": f"Source policy not found"}, status=404)

        # Create new policy with same configuration as source
        new_policy = Policy.objects.create(
            name=new_policy_name,
            settings_path=source_policy.settings_path,
            logs_path=source_policy.logs_path,
            binary_path=source_policy.binary_path,
            logstash_yml=source_policy.logstash_yml,
            jvm_options=source_policy.jvm_options,
            log4j2_properties=source_policy.log4j2_properties,
            keystore_password=source_policy.keystore_password,
            keystore_password_hash=source_policy.keystore_password_hash
        )

        # Generate default enrollment token for new policy (same as add_policy)
        enrollment_token = secrets.token_urlsafe(32)
        EnrollmentToken.objects.create(
            policy=new_policy,
            name='default',
            token=enrollment_token
        )

        # Clone all pipelines from source policy
        source_pipelines = Pipeline.objects.filter(policy=source_policy)
        for source_pipeline in source_pipelines:
            Pipeline.objects.create(
                policy=new_policy,
                name=source_pipeline.name,
                description=source_pipeline.description,
                lscl=source_pipeline.lscl,
                pipeline_workers=source_pipeline.pipeline_workers,
                pipeline_batch_size=source_pipeline.pipeline_batch_size,
                pipeline_batch_delay=source_pipeline.pipeline_batch_delay,
                queue_type=source_pipeline.queue_type,
                queue_max_bytes=source_pipeline.queue_max_bytes,
                queue_checkpoint_writes=source_pipeline.queue_checkpoint_writes
            )

        # Clone all keystore entries from source policy
        source_keystore_entries = Keystore.objects.filter(policy=source_policy)
        for source_entry in source_keystore_entries:
            Keystore.objects.create(
                policy=new_policy,
                key_name=source_entry.key_name,
                key_value=source_entry.key_value,
                kv_hash=source_entry.kv_hash
            )

        logger.info(
            f"User '{request.user.username}' cloned policy '{source_policy.name}' to '{new_policy_name}' "
            f"(ID: {new_policy.id}) with {source_pipelines.count()} pipelines and "
            f"{source_keystore_entries.count()} keystore entries"
        )

        return JsonResponse({
            "success": True,
            "message": f"Policy '{new_policy_name}' created successfully",
            "policy_id": new_policy.id,
            "policy_name": new_policy.name
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error cloning policy: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def get_enrollment_tokens(request):
    """
    Get all enrollment tokens for a specific policy.
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

        # Get all enrollment tokens for this policy
        tokens = EnrollmentToken.objects.filter(policy=policy)

        # Serialize tokens with encoded payload
        tokens_data = []
        for token in tokens:
            # Create token payload (same as generate_enrollment_token)
            token_payload = {
                "enrollment_token": token.token
            }

            # Encode as base64
            json_string = json.dumps(token_payload)
            encoded_token = base64.b64encode(json_string.encode('utf-8')).decode('utf-8')

            tokens_data.append({
                "id": token.id,
                "name": token.name,
                "raw_token": token.token,
                "encoded_token": encoded_token
            })

        return JsonResponse({
            "success": True,
            "tokens": tokens_data
        })

    except Exception as e:
        logger.error(f"Error fetching enrollment tokens: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def add_enrollment_token(request):
    """
    Create a new enrollment token for a policy.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        policy_id = data.get('policy_id')
        token_name = data.get('name', 'default')

        if not policy_id:
            return JsonResponse({"success": False, "error": "Policy ID is required"}, status=400)

        # Get the policy
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            return JsonResponse({"success": False, "error": "Policy not found"}, status=404)

        # Generate enrollment token
        enrollment_token = secrets.token_urlsafe(32)

        # Create enrollment token record in database
        token = EnrollmentToken.objects.create(
            policy=policy,
            name=token_name,
            token=enrollment_token
        )

        logger.info(f"User '{request.user.username}' created enrollment token {token.id} for policy '{policy.name}'")

        return JsonResponse({
            "success": True,
            "message": "Enrollment token created successfully",
            "token_id": token.id
        })

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error creating enrollment token: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@require_admin_role
def delete_enrollment_token(request):
    """
    Delete an enrollment token.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        token_id = data.get('token_id')

        if not token_id:
            return JsonResponse({"success": False, "error": "Token ID is required"}, status=400)

        # Get and delete the token
        try:
            token = EnrollmentToken.objects.get(id=token_id)
            policy_name = token.policy.name
            token.delete()

            logger.info(
                f"User '{request.user.username}' deleted enrollment token {token_id} for policy '{policy_name}'")

            return JsonResponse({
                "success": True,
                "message": "Enrollment token deleted successfully"
            })

        except EnrollmentToken.DoesNotExist:
            return JsonResponse({"success": False, "error": "Enrollment token not found"}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as e:
        logger.error(f"Error deleting enrollment token: {str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)

def load_default_config(filename):
    """Load default configuration file from the data directory"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, 'data', filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Default config file not found: {file_path}")
        return ""
    except Exception as e:
        logger.error(f"Error loading default config file {filename}: {str(e)}")
        return ""



def get_default_logstash_yml():
    """Get default logstash.yml configuration"""
    return load_default_config('default_logstash.yml')


def get_default_jvm_options():
    """Get default jvm.options configuration"""
    return load_default_config('default_jvm.options')


def get_default_log4j2_properties():
    """Get default log4j2.properties configuration"""
    return load_default_config('default_log4j2.properties')
