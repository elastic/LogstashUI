#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from datetime import datetime, timezone

import base64
import hashlib
import json
import logging
import secrets

from cryptography.fernet import Fernet

from .models import ApiKey, Connection as ConnectionTable, EnrollmentToken


logger = logging.getLogger(__name__)


def _encrypt_for_agent(raw_api_key: str, plaintext: str) -> str:
    """
    Encrypt a plaintext value for transport to a specific agent.
    Uses the agent's raw API key (SHA-256 -> base64) as the Fernet key so that
    only that agent, which holds the same API key, can decrypt it.
    """
    key = base64.urlsafe_b64encode(hashlib.sha256(raw_api_key.encode("utf-8")).digest())
    return Fernet(key).encrypt(plaintext.encode("utf-8")).decode("utf-8")


@csrf_exempt
def enroll(request):
    """
    Enroll a Logstash Agent using an enrollment token
    Validates token in database, creates connection, and generates API key
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        encoded_token = data.get("enrollment_token")
        host = data.get("host")
        agent_id = data.get("agent_id")

        if not encoded_token or not host or not agent_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Missing required fields: enrollment_token, host, agent_id",
                },
                status=400,
            )

        try:
            decoded_json = base64.b64decode(encoded_token.encode("utf-8")).decode("utf-8")
            token_payload = json.loads(decoded_json)
        except Exception as exc:
            logger.error(f"Failed to decode enrollment token: {exc}")
            return JsonResponse({"success": False, "error": "Invalid enrollment token format"}, status=400)

        enrollment_token = token_payload.get("enrollment_token")
        if not enrollment_token:
            return JsonResponse({"success": False, "error": "Invalid token payload"}, status=400)

        try:
            enrollment_token_obj = EnrollmentToken.objects.get(token=enrollment_token)
        except EnrollmentToken.DoesNotExist:
            return JsonResponse({"success": False, "error": "Invalid enrollment token"}, status=401)

        try:
            existing_connection = ConnectionTable.objects.filter(agent_id=agent_id).first()
            if existing_connection:
                logger.info(
                    f"Agent {agent_id} is re-enrolling. Deleting old connection {existing_connection.id}"
                )
                existing_connection.delete()
        except Exception as exc:
            logger.warning(f"Error checking for existing agent_id: {exc}")

        try:
            connection = ConnectionTable.objects.create(
                name=host,
                connection_type="AGENT",
                host=host,
                agent_id=agent_id,
                is_active=True,
                policy=enrollment_token_obj.policy,
            )

            raw_api_key = secrets.token_urlsafe(32)
            ApiKey.objects.create(connection=connection, api_key=raw_api_key)

            logger.info(
                f"Agent enrolled successfully with host '{host}', agent_id '{agent_id}', "
                f"and policy '{enrollment_token_obj.policy.name}'"
            )

            policy = enrollment_token_obj.policy
            return JsonResponse(
                {
                    "success": True,
                    "api_key": raw_api_key,
                    "policy_id": policy.id,
                    "connection_id": connection.id,
                    "policy_config": {
                        "settings_path": policy.settings_path,
                        "logs_path": policy.logs_path,
                        "binary_path": policy.binary_path,
                        "logstash_yml": policy.logstash_yml,
                        "jvm_options": policy.jvm_options,
                        "log4j2_properties": policy.log4j2_properties,
                    },
                }
            )
        except Exception as exc:
            logger.error(f"Error creating connection during enrollment: {exc}")
            return JsonResponse(
                {"success": False, "error": f"Failed to create connection: {exc}"},
                status=500,
            )

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as exc:
        logger.error(f"Error during enrollment: {exc}")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
def check_in(request):
    """
    Handle agent check-in requests
    Authenticates via API key and updates last_check_in timestamp
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("ApiKey "):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Missing or invalid Authorization header. Expected: 'Authorization: ApiKey <key>'",
                },
                status=401,
            )

        raw_api_key = auth_header[7:]
        if not raw_api_key:
            return JsonResponse({"success": False, "error": "API key is empty"}, status=401)

        data = json.loads(request.body)
        connection_id = data.get("connection_id")
        if not connection_id:
            return JsonResponse({"success": False, "error": "Missing connection_id"}, status=400)

        try:
            connection = ConnectionTable.objects.get(id=connection_id)
        except ConnectionTable.DoesNotExist:
            return JsonResponse({"success": False, "error": "Invalid connection_id"}, status=401)

        api_key_obj = connection.api_keys.first()
        if not api_key_obj or not api_key_obj.verify_api_key(raw_api_key):
            return JsonResponse({"success": False, "error": "Invalid API key"}, status=401)

        connection.last_check_in = datetime.now(timezone.utc)

        status_blob = data.get("status_blob")
        if status_blob:
            connection.status_blob = status_blob
            logger.debug(f"Updated status_blob: {status_blob}")

        should_restart = connection.restart_on_next_checkin
        if should_restart:
            connection.restart_on_next_checkin = False

        connection.save()

        logger.info(f"Agent check-in: connection_id={connection_id}, agent_id={connection.agent_id}")
        logger.debug(f"Check-in data: {data}")

        policy = connection.policy
        if not policy:
            return JsonResponse({"success": False, "error": "No policy assigned to this connection"}, status=400)

        return JsonResponse(
            {
                "success": True,
                "message": "Check-in successful",
                "timestamp": connection.last_check_in.isoformat(),
                "current_revision_number": policy.current_revision_number,
                "settings_path": policy.settings_path,
                "logs_path": policy.logs_path,
                "binary_path": policy.binary_path,
                "restart": should_restart,
                "desired_agent_version": connection.desired_agent_version,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as exc:
        logger.error(f"Error during check-in: {exc}")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
def get_config_changes(request):
    """
    Compare agent-side config state with the assigned policy and return required updates.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        connection_id = data.get("connection_id")
        if not connection_id:
            return JsonResponse({"success": False, "error": "Connection ID is required"}, status=400)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("ApiKey "):
            return JsonResponse({"success": False, "error": "Invalid authorization header"}, status=401)

        raw_api_key = auth_header.replace("ApiKey ", "").strip()

        try:
            connection = ConnectionTable.objects.get(id=connection_id, connection_type="AGENT")
        except ConnectionTable.DoesNotExist:
            return JsonResponse({"success": False, "error": "Connection not found"}, status=404)

        try:
            api_key_obj = connection.api_keys.first()
            if not api_key_obj or not api_key_obj.verify_api_key(raw_api_key):
                return JsonResponse({"success": False, "error": "Invalid API key"}, status=401)
        except Exception as exc:
            logger.error(f"API key verification error: {exc}")
            return JsonResponse({"success": False, "error": "Authentication failed"}, status=401)

        agent_logstash_yml_hash = data.get("logstash_yml_hash", "")
        agent_jvm_options_hash = data.get("jvm_options_hash", "")
        agent_log4j2_properties_hash = data.get("log4j2_properties_hash", "")
        agent_settings_path = data.get("settings_path", "")
        agent_logs_path = data.get("logs_path", "")
        agent_binary_path = data.get("binary_path", "")
        agent_keystore_password_hash = data.get("keystore_password_hash", "")

        if not connection.policy:
            return JsonResponse({"success": False, "error": "No policy assigned to this connection"}, status=400)

        policy = connection.policy
        changes = {}

        changes["logstash_yml"] = policy.logstash_yml if agent_logstash_yml_hash != policy.logstash_yml_hash else False
        changes["jvm_options"] = policy.jvm_options if agent_jvm_options_hash != policy.jvm_options_hash else False
        changes["log4j2_properties"] = (
            policy.log4j2_properties if agent_log4j2_properties_hash != policy.log4j2_properties_hash else False
        )
        changes["settings_path"] = policy.settings_path if agent_settings_path != policy.settings_path else False
        changes["logs_path"] = policy.logs_path if agent_logs_path != policy.logs_path else False
        changes["binary_path"] = policy.binary_path if agent_binary_path != policy.binary_path else False

        agent_keystore = data.get("keystore", {})
        policy_keystore_entries = policy.keystore_entries.all()
        policy_keystore = {
            entry.key_name: {"hash": entry.kv_hash, "value": entry.get_key_value()}
            for entry in policy_keystore_entries
        }

        keystore_changes = {"set": {}, "delete": []}

        for agent_key_name, agent_hash in agent_keystore.items():
            if agent_key_name in policy_keystore:
                if agent_hash != policy_keystore[agent_key_name]["hash"]:
                    plaintext_value = policy_keystore[agent_key_name]["value"]
                    keystore_changes["set"][agent_key_name] = _encrypt_for_agent(raw_api_key, plaintext_value)
            else:
                keystore_changes["delete"].append(agent_key_name)

        for policy_key_name, policy_key_data in policy_keystore.items():
            if policy_key_name not in agent_keystore:
                keystore_changes["set"][policy_key_name] = _encrypt_for_agent(
                    raw_api_key,
                    policy_key_data["value"],
                )

        if policy.keystore_password and (agent_keystore_password_hash != policy.keystore_password_hash):
            plaintext_password = policy.get_keystore_password()
            changes["keystore_password"] = _encrypt_for_agent(raw_api_key, plaintext_password)
            forced_set = {
                policy_key_name: _encrypt_for_agent(raw_api_key, policy_key_data["value"])
                for policy_key_name, policy_key_data in policy_keystore.items()
            }
            if forced_set or keystore_changes.get("delete"):
                changes["keystore"] = {"set": forced_set, "delete": keystore_changes.get("delete", [])}
            else:
                changes["keystore"] = False
        else:
            changes["keystore_password"] = False
            changes["keystore"] = keystore_changes if (keystore_changes["set"] or keystore_changes["delete"]) else False

        agent_pipelines = data.get("pipelines", {})
        policy_pipelines_qs = policy.pipelines.all()
        pipeline_changes = {"set": {}, "delete": []}

        for agent_pipeline_name in agent_pipelines:
            if not policy_pipelines_qs.filter(name=agent_pipeline_name).exists():
                pipeline_changes["delete"].append(agent_pipeline_name)

        for pipeline in policy_pipelines_qs:
            agent_entry = agent_pipelines.get(pipeline.name)
            needs_update = agent_entry is None or agent_entry.get("config_hash") != pipeline.pipeline_hash
            if needs_update:
                pipeline_changes["set"][pipeline.name] = {
                    "lscl": pipeline.lscl,
                    "pipeline_hash": pipeline.pipeline_hash,
                    "no_input": pipeline.no_input,
                    "non_reloadable": pipeline.non_reloadable,
                    "settings": {
                        "pipeline_workers": pipeline.pipeline_workers,
                        "pipeline_batch_size": pipeline.pipeline_batch_size,
                        "pipeline_batch_delay": pipeline.pipeline_batch_delay,
                        "queue_type": pipeline.queue_type,
                        "queue_max_bytes": pipeline.queue_max_bytes,
                        "queue_checkpoint_writes": pipeline.queue_checkpoint_writes,
                    },
                }

        changes["pipelines"] = (
            pipeline_changes if (pipeline_changes["set"] or pipeline_changes["delete"]) else False
        )

        config_statuses = ", ".join(
            [
                f"logstash_yml={'CHANGED' if changes.get('logstash_yml') else 'unchanged'}",
                f"jvm={'CHANGED' if changes.get('jvm_options') else 'unchanged'}",
                f"log4j2={'CHANGED' if changes.get('log4j2_properties') else 'unchanged'}",
                f"settings_path={'CHANGED' if changes.get('settings_path') else 'unchanged'}",
                f"logs_path={'CHANGED' if changes.get('logs_path') else 'unchanged'}",
                f"binary_path={'CHANGED' if changes.get('binary_path') else 'unchanged'}",
            ]
        )
        keystore_summary = (
            f"CHANGED (set={list(changes['keystore']['set'].keys())}, delete={changes['keystore']['delete']})"
            if changes.get("keystore")
            else "unchanged"
        )
        pipeline_summary = (
            f"CHANGED (set={list(changes['pipelines']['set'].keys())}, delete={changes['pipelines']['delete']})"
            if changes.get("pipelines")
            else "unchanged"
        )
        logger.info(
            f"Config change check conn={connection_id}: [{config_statuses}] "
            f"keystore(agent={len(agent_keystore)}, policy={policy_keystore_entries.count()}, {keystore_summary}) "
            f"pipelines(agent={len(agent_pipelines)}, policy={policy_pipelines_qs.count()}, {pipeline_summary})"
        )

        return JsonResponse(
            {
                "success": True,
                "changes": changes,
                "policy_name": policy.name,
                "current_revision": policy.current_revision_number,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as exc:
        logger.error(f"Error checking config changes: {exc}")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
