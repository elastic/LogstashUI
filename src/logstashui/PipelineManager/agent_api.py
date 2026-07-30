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

from .models import ApiKey, Connection as ConnectionTable, EnrollmentToken, Policy
from .agent_modes import (
    build_policy_config,
    next_simulate_instance_id,
    simulate_ports,
)

from SNMP.snmp_crud import agent_snmp_pipeline_names, agent_snmp_keystore_keys


logger = logging.getLogger(__name__)


def _sign_csr_if_present(data: dict) -> dict | None:
    """If request includes csr_pem, sign with product CA and return payload fragment."""
    csr_pem = data.get("csr_pem") or data.get("certificate_signing_request")
    if not csr_pem:
        return None
    try:
        from Common.product_ca import sign_agent_csr

        signed = sign_agent_csr(csr_pem if isinstance(csr_pem, bytes) else csr_pem.encode("utf-8"))
        return {
            "server_certificate": signed["certificate_pem"],
            "ca_certificate": signed["ca_pem"],
            "certificate_fingerprint": signed["fingerprint_sha256"],
        }
    except Exception as exc:
        logger.error("Failed to sign agent CSR: %s", exc, exc_info=True)
        raise


def _encrypt_for_agent(raw_api_key: str, plaintext: str) -> str:
    """
    Encrypt a plaintext value for transport to a specific agent.
    Uses the agent's raw API key (SHA-256 -> base64) as the Fernet key so that
    only that agent, which holds the same API key, can decrypt it.
    """
    key = base64.urlsafe_b64encode(hashlib.sha256(raw_api_key.encode("utf-8")).digest())
    return Fernet(key).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def _build_snmp_changes(connection, policy, raw_api_key, agent_snmp_pipelines, agent_snmp_keystore):
    """
    Compute the SNMP-managed pipeline/keystore delta between the agent's current
    state (hash maps) and the SNMP records THIS agent is responsible for.

    SNMP-managed pipelines/keystore entries are delivered independently of the
    policy revision number so that SNMP deploys never touch policy revision
    history. Comparison uses pre-computed hashes (cheap dict diff).

    Scoping is per-agent, never per-policy: a network's pipelines belong to
    exactly one agent (Network.agent_connection), even though many networks can
    share one agent and many agents can share one base policy. Delivering the
    whole policy's SNMP records to every agent on it would make sibling agents
    poll the same devices (duplicate data), so we restrict delivery to the
    pipelines/keys owned by this agent's own networks.

    Args:
        connection: the agent Connection checking in
        policy: the agent's assigned Policy (holds the SNMP records)
        raw_api_key: the agent's raw API key (for encrypting keystore values)
        agent_snmp_pipelines: {pipeline_name: pipeline_hash} reported by the agent
        agent_snmp_keystore: {key_name: kv_hash} reported by the agent

    Returns:
        dict {'pipelines': {...}, 'keystore': {...}} or None if no changes.
    """
    agent_snmp_pipelines = agent_snmp_pipelines or {}
    agent_snmp_keystore = agent_snmp_keystore or {}

    own_pipeline_names = agent_snmp_pipeline_names(connection)
    own_key_names = agent_snmp_keystore_keys(connection)

    snmp_pipelines = policy.pipelines.filter(
        managed_by="snmp", name__in=own_pipeline_names
    )
    snmp_keystore = policy.keystore_entries.filter(
        managed_by="snmp", key_name__in=own_key_names
    )

    pipeline_changes = {"set": {}, "delete": []}
    expected_pipeline_names = set()

    for pipeline in snmp_pipelines:
        expected_pipeline_names.add(pipeline.name)
        agent_hash = agent_snmp_pipelines.get(pipeline.name)
        if agent_hash != pipeline.pipeline_hash:
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

    for agent_pipeline_name in agent_snmp_pipelines:
        if agent_pipeline_name not in expected_pipeline_names:
            pipeline_changes["delete"].append(agent_pipeline_name)

    keystore_changes = {"set": {}, "delete": []}
    expected_key_names = set()

    for entry in snmp_keystore:
        expected_key_names.add(entry.key_name)
        agent_hash = agent_snmp_keystore.get(entry.key_name)
        if agent_hash != entry.kv_hash:
            plaintext_value = entry.get_key_value()
            if plaintext_value is not None:
                keystore_changes["set"][entry.key_name] = _encrypt_for_agent(
                    raw_api_key, plaintext_value
                )
            else:
                # Can't decrypt the stored secret (e.g. app secret/key rotated or
                # DB corruption). We can't deliver it, so the agent will keep
                # reporting this key out-of-sync (cheap rollup stays "dirty")
                # every cycle. Surface it so it's diagnosable rather than a silent
                # perpetual fetch loop; fix by re-provisioning (redeploy the
                # network) or removing the entry.
                logger.warning(
                    "SNMP keystore entry '%s' on policy '%s' could not be decrypted; "
                    "cannot deliver to agent. Redeploy the owning network to re-provision it.",
                    entry.key_name,
                    policy.name,
                )

    for agent_key_name in agent_snmp_keystore:
        if agent_key_name not in expected_key_names:
            keystore_changes["delete"].append(agent_key_name)

    has_pipeline_changes = bool(pipeline_changes["set"] or pipeline_changes["delete"])
    has_keystore_changes = bool(keystore_changes["set"] or keystore_changes["delete"])

    if not has_pipeline_changes and not has_keystore_changes:
        return None

    return {
        "pipelines": pipeline_changes if has_pipeline_changes else {"set": {}, "delete": []},
        "keystore": keystore_changes if has_keystore_changes else {"set": {}, "delete": []},
    }


def _managed_rollup(pipelines, keystore):
    """
    Canonical single-hash summary of a managed source's pipeline + keystore hash
    maps, used for the cheap per-source "dirty?" check at check-in (Phase 2).

    MUST stay byte-for-byte identical to the agent's implementation
    (logstashagent.controller._managed_rollup) so both sides derive the same
    rollup from the same {name: hash} maps. Built from stored hashes only — no
    decryption — so it is safe to run on every check-in.
    """
    import hashlib
    parts = []
    for name in sorted(pipelines or {}):
        parts.append(f"p:{name}={pipelines[name]}")
    for name in sorted(keystore or {}):
        parts.append(f"k:{name}={keystore[name]}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _snmp_desired_hashes(connection, policy):
    """
    The SNMP pipeline/keystore hash maps THIS agent should have, scoped to its
    own networks. Uses the SAME scoping/query as _build_snmp_changes() so the
    cheap rollup check agrees exactly with the delta the fetch would return.
    No decryption (stored pipeline_hash/kv_hash only).
    """
    own_pipeline_names = agent_snmp_pipeline_names(connection)
    own_key_names = agent_snmp_keystore_keys(connection)
    pipelines = {
        p.name: p.pipeline_hash
        for p in policy.pipelines.filter(managed_by="snmp", name__in=own_pipeline_names)
    }
    keystore = {
        e.key_name: e.kv_hash
        for e in policy.keystore_entries.filter(managed_by="snmp", key_name__in=own_key_names)
    }
    return pipelines, keystore


def _snmp_changes_available(connection, policy, agent_rollup):
    """
    Cheap check: does this agent's reported SNMP rollup differ from the desired
    (deployed) SNMP state for its networks? No decryption, no payload building.
    The actual delta is fetched via GetConfigChanges when this returns True.
    """
    desired_pipelines, desired_keystore = _snmp_desired_hashes(connection, policy)
    expected_rollup = _managed_rollup(desired_pipelines, desired_keystore)
    return expected_rollup != (agent_rollup or _managed_rollup({}, {}))


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

        policy = enrollment_token_obj.policy
        if policy.policy_type == Policy.PolicyType.EMBEDDED:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Cannot enroll against the Embedded policy; it is reserved for the Docker sim node",
                },
                status=400,
            )

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
            instance_id = None
            agent_api_port = None
            logstash_api_port = None
            if policy.policy_type == Policy.PolicyType.SIMULATE:
                instance_id = next_simulate_instance_id()
                agent_api_port, logstash_api_port = simulate_ports(instance_id)

            conn_name = (
                f"{host}-simulate-{instance_id}"
                if policy.policy_type == Policy.PolicyType.SIMULATE
                else host
            )
            connection = ConnectionTable.objects.create(
                name=conn_name,
                connection_type="AGENT",
                host=host,
                agent_id=agent_id,
                is_active=True,
                policy=policy,
                instance_id=instance_id,
                agent_api_port=agent_api_port,
                logstash_api_port=logstash_api_port,
            )

            raw_api_key = secrets.token_urlsafe(32)
            ApiKey.objects.create(connection=connection, api_key=raw_api_key)

            policy_config = build_policy_config(policy, instance_id=instance_id)

            logger.info(
                f"Agent enrolled successfully with host '{host}', agent_id '{agent_id}', "
                f"policy '{policy.name}' type={policy.policy_type}"
                + (f" instance_id={instance_id}" if instance_id else "")
            )

            response_body = {
                "success": True,
                "api_key": raw_api_key,
                "policy_id": policy.id,
                "connection_id": connection.id,
                "policy_config": policy_config,
            }
            try:
                cert_part = _sign_csr_if_present(data)
                if cert_part:
                    response_body.update(cert_part)
            except Exception as exc:
                return JsonResponse(
                    {"success": False, "error": f"Failed to sign agent certificate: {exc}"},
                    status=400,
                )

            return JsonResponse(response_body)
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
def issue_server_cert(request):
    """
    Issue a product-CA-signed agent server certificate from a CSR.

    Auth (one of):
      - Authorization: ApiKey <key> + connection_id (enrolled agents)
      - X-LogstashUI-Agent-Csr-Secret: matches LOGSTASHUI_AGENT_CSR_SECRET
        (compose/embedded bootstrap without re-enroll)
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        csr_pem = data.get("csr_pem") or data.get("certificate_signing_request")
        if not csr_pem:
            return JsonResponse({"success": False, "error": "Missing csr_pem"}, status=400)

        authorized = False
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("ApiKey "):
            raw_api_key = auth_header[7:]
            connection_id = data.get("connection_id")
            if connection_id and raw_api_key:
                try:
                    connection = ConnectionTable.objects.get(id=connection_id)
                    api_key_obj = connection.api_keys.first()
                    if api_key_obj and api_key_obj.verify_api_key(raw_api_key):
                        authorized = True
                except ConnectionTable.DoesNotExist:
                    pass

        if not authorized:
            import os

            expected = (os.environ.get("LOGSTASHUI_AGENT_CSR_SECRET") or "").strip()
            provided = (
                request.headers.get("X-LogstashUI-Agent-Csr-Secret")
                or data.get("agent_csr_secret")
                or ""
            ).strip()
            if expected and provided and secrets.compare_digest(expected, provided):
                authorized = True

        if not authorized:
            return JsonResponse({"success": False, "error": "Unauthorized"}, status=401)

        from Common.product_ca import sign_agent_csr

        signed = sign_agent_csr(csr_pem if isinstance(csr_pem, bytes) else csr_pem.encode("utf-8"))
        return JsonResponse(
            {
                "success": True,
                "server_certificate": signed["certificate_pem"],
                "ca_certificate": signed["ca_pem"],
                "certificate_fingerprint": signed["fingerprint_sha256"],
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except Exception as exc:
        logger.error(f"Error issuing server cert: {exc}", exc_info=True)
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
            # Surface resolved Logstash version for sim target dropdown
            resolved = status_blob.get("logstash_version_resolved") or status_blob.get(
                "logstash_version"
            )
            if resolved:
                connection.logstash_version_resolved = str(resolved)[:64]
            if status_blob.get("agent_api_port") is not None:
                try:
                    connection.agent_api_port = int(status_blob["agent_api_port"])
                except (TypeError, ValueError):
                    pass
            if status_blob.get("logstash_api_port") is not None:
                try:
                    connection.logstash_api_port = int(status_blob["logstash_api_port"])
                except (TypeError, ValueError):
                    pass

        should_restart = connection.restart_on_next_checkin
        if should_restart:
            connection.restart_on_next_checkin = False

        connection.save()

        logger.info(f"Agent check-in: connection_id={connection_id}, agent_id={connection.agent_id}")
        logger.debug(f"Check-in data: {data}")

        policy = connection.policy
        if not policy:
            return JsonResponse({"success": False, "error": "No policy assigned to this connection"}, status=400)

        # Cheap per-source "dirty?" check (Phase 2). SNMP deltas are NOT built
        # here anymore (no decryption on check-in); when this flag is set the
        # agent fetches the actual delta via GetConfigChanges alongside the
        # policy delta, so both apply in one merged pass. Detection is a rollup
        # hash compare over stored hashes, independent of the policy revision.
        managed_state_hashes = data.get("managed_state_hashes", {}) or {}
        managed_changes_available = {
            "snmp": _snmp_changes_available(connection, policy, managed_state_hashes.get("snmp")),
        }

        response_payload = {
            "success": True,
            "message": "Check-in successful",
            "timestamp": connection.last_check_in.isoformat(),
            "current_revision_number": policy.current_revision_number,
            "settings_path": policy.settings_path,
            "logs_path": policy.logs_path,
            "binary_path": policy.binary_path,
            # Desired Logstash runtime (agent applies VERSION download when these change)
            "logstash_source": getattr(policy, "logstash_source", None) or "SYSTEM",
            "logstash_version": getattr(policy, "logstash_version", None) or "",
            "logstash_download_dir": getattr(policy, "logstash_download_dir", None)
            or "/opt/logstash-agent/logstash-versions",
            "restart": should_restart,
            "desired_agent_version": connection.desired_agent_version,
            "managed_changes_available": managed_changes_available,
        }

        # Upgrade path: agent without server cert sends CSR; re-issue without re-enroll
        try:
            cert_part = _sign_csr_if_present(data)
            if cert_part:
                response_payload.update(cert_part)
                logger.info(
                    "Issued/re-issued agent server cert on check-in connection_id=%s",
                    connection_id,
                )
        except Exception as exc:
            return JsonResponse(
                {"success": False, "error": f"Failed to sign agent certificate: {exc}"},
                status=400,
            )

        return JsonResponse(response_payload)

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
        agent_logstash_source = (data.get("logstash_source") or "SYSTEM").upper()
        agent_logstash_version = data.get("logstash_version") or ""
        agent_logstash_download_dir = data.get("logstash_download_dir") or ""

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

        # Desired Logstash runtime for simulate VERSION/SYSTEM switches
        policy_source = (getattr(policy, "logstash_source", None) or "SYSTEM").upper()
        policy_version = getattr(policy, "logstash_version", None) or ""
        policy_download_dir = (
            getattr(policy, "logstash_download_dir", None)
            or "/opt/logstash-agent/logstash-versions"
        )
        runtime_changed = (
            agent_logstash_source != policy_source
            or (policy_source == "VERSION" and agent_logstash_version != policy_version)
            or (
                policy_source == "VERSION"
                and (agent_logstash_download_dir or policy_download_dir)
                and agent_logstash_download_dir != policy_download_dir
            )
            or (policy_source == "SYSTEM" and agent_binary_path != policy.binary_path)
        )
        if runtime_changed:
            changes["logstash_runtime"] = {
                "source": policy_source,
                "version": policy_version,
                "download_dir": policy_download_dir,
                "binary_path": policy.binary_path,
            }
        else:
            changes["logstash_runtime"] = False

        agent_keystore = data.get("keystore", {})
        policy_keystore_entries = policy.keystore_entries.all()
        policy_keystore = {
            entry.key_name: {"hash": entry.kv_hash, "value": entry.get_key_value()}
            for entry in policy_keystore_entries
        }
        # SNMP-managed keystore entries are synced via the check-in loop. Exclude
        # them from "set" here, but keep them in the delete guard (policy_keystore
        # holds all names) so they are never deleted by this channel.
        snmp_key_names = set(
            policy.keystore_entries.filter(managed_by="snmp").values_list("key_name", flat=True)
        )
        # The policy channel owns ONLY user-authored keys. On a keystore-password
        # change the physical keystore is rebuilt from scratch, so we must rebuild
        # it from user keys only -- pushing every policy SNMP key here would leak
        # sibling agents' secrets (an agent must only ever hold its own networks'
        # SNMP keys, which arrive separately via the agent-scoped check-in loop).
        user_key_names = set(
            policy.keystore_entries.filter(managed_by="user").values_list("key_name", flat=True)
        )

        keystore_changes = {"set": {}, "delete": []}

        for agent_key_name, agent_hash in agent_keystore.items():
            if agent_key_name in policy_keystore:
                if agent_key_name in snmp_key_names:
                    continue
                if agent_hash != policy_keystore[agent_key_name]["hash"]:
                    plaintext_value = policy_keystore[agent_key_name]["value"]
                    keystore_changes["set"][agent_key_name] = _encrypt_for_agent(raw_api_key, plaintext_value)
            else:
                keystore_changes["delete"].append(agent_key_name)

        for policy_key_name, policy_key_data in policy_keystore.items():
            if policy_key_name in snmp_key_names:
                continue
            if policy_key_name not in agent_keystore:
                keystore_changes["set"][policy_key_name] = _encrypt_for_agent(
                    raw_api_key,
                    policy_key_data["value"],
                )

        # Keystore password protocol for the agent:
        #   false  → no change
        #   null   → clear (migrate to unauthenticated; policy has no password)
        #   string → encrypted password to apply (set/rotate)
        if policy.keystore_password:
            if agent_keystore_password_hash != policy.keystore_password_hash:
                plaintext_password = policy.get_keystore_password()
                changes["keystore_password"] = _encrypt_for_agent(raw_api_key, plaintext_password)
                forced_set = {
                    policy_key_name: _encrypt_for_agent(raw_api_key, policy_key_data["value"])
                    for policy_key_name, policy_key_data in policy_keystore.items()
                    if policy_key_name in user_key_names
                }
                if forced_set or keystore_changes.get("delete"):
                    changes["keystore"] = {
                        "set": forced_set,
                        "delete": keystore_changes.get("delete", []),
                    }
                else:
                    changes["keystore"] = False
            else:
                changes["keystore_password"] = False
                changes["keystore"] = (
                    keystore_changes
                    if (keystore_changes["set"] or keystore_changes["delete"])
                    else False
                )
        else:
            # Policy wants unauthenticated keystore
            if agent_keystore_password_hash:
                changes["keystore_password"] = None
            else:
                changes["keystore_password"] = False
            changes["keystore"] = (
                keystore_changes
                if (keystore_changes["set"] or keystore_changes["delete"])
                else False
            )

        agent_pipelines = data.get("pipelines", {})
        policy_pipelines_qs = policy.pipelines.all()
        # SNMP-managed pipelines are synced via the check-in loop, not this
        # channel. Exclude them from "set" so the two channels don't fight, but
        # guard "delete" against ALL policy pipeline names (including SNMP) so we
        # never delete an SNMP pipeline the agent reports in its regular state.
        all_pipeline_names = set(policy_pipelines_qs.values_list("name", flat=True))
        pipeline_changes = {"set": {}, "delete": []}

        for agent_pipeline_name in agent_pipelines:
            if agent_pipeline_name not in all_pipeline_names:
                pipeline_changes["delete"].append(agent_pipeline_name)

        for pipeline in policy_pipelines_qs.exclude(managed_by="snmp"):
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

        # SNMP-managed deltas ride along in this same fetch (Phase 2). The agent
        # calls GetConfigChanges whenever check-in flagged policy OR snmp as
        # dirty, so both are applied together in one merged pass / one restart.
        # This is where the (agent-scoped) decrypt + re-encrypt happens — only
        # for changed keys, and only when something is actually dirty.
        snmp_changes = _build_snmp_changes(
            connection,
            policy,
            raw_api_key,
            data.get("snmp_pipelines", {}),
            data.get("snmp_keystore", {}),
        )

        config_statuses = ", ".join(
            [
                f"logstash_yml={'CHANGED' if changes.get('logstash_yml') else 'unchanged'}",
                f"jvm={'CHANGED' if changes.get('jvm_options') else 'unchanged'}",
                f"log4j2={'CHANGED' if changes.get('log4j2_properties') else 'unchanged'}",
                f"settings_path={'CHANGED' if changes.get('settings_path') else 'unchanged'}",
                f"logs_path={'CHANGED' if changes.get('logs_path') else 'unchanged'}",
                f"binary_path={'CHANGED' if changes.get('binary_path') else 'unchanged'}",
                f"logstash_runtime={'CHANGED' if changes.get('logstash_runtime') else 'unchanged'}",
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

        response = {
            "success": True,
            "changes": changes,
            "policy_name": policy.name,
            "current_revision": policy.current_revision_number,
        }
        if snmp_changes is not None:
            response["snmp_changes"] = snmp_changes

        return JsonResponse(response)

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON data"}, status=400)
    except Exception as exc:
        logger.error(f"Error checking config changes: {exc}")
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
