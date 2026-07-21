#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse, HttpResponse
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models import Q, Prefetch

from Common.encryption import decrypt_credential
from Common.elastic_utils import get_elastic_connection
from Common.logstash_config_parse import ComponentToPipeline
from Common.decorators import require_admin_role
from Common.formatters import _sanitize_pipeline_name_component, format_display_name

from .snmp_pipeline_generator import (
    _generate_input, 
    _generate_output, 
    _generate_discovery_input, 
    _generate_discovery_filters, 
    _generate_filters,
    _OFFICIAL_PROFILE_CACHE,
    snmp_credential_keystore_entries,
    es_connection_keystore_entries,
    snmp_credential_keystore_key_names,
    es_connection_keystore_key_names,
    _uses_keystore,
)

from PipelineManager.models import Connection, Pipeline, Keystore

from .models import Credential, Network, Profile, Device, DeviceTemplate, SNMPDeploymentState

from datetime import datetime, timedelta, timezone

import json
import os
import re
import logging

logger = logging.getLogger(__name__)


# Matches keystore key names generated for SNMP device credentials, e.g.
# "snmp_16_v2" or "snmp_16_v3_auth" (see snmp_pipeline_generator.py naming
# convention docstring).
_SNMP_CRED_KEY_RE = re.compile(r'^snmp_(\d+)_(v1|v2|v3_auth|v3_priv)$')

# Matches keystore key names generated for Elasticsearch output connection
# credentials, e.g. "snmp_es_1_password".
_SNMP_ES_KEY_RE = re.compile(r'^snmp_es_(\d+)_(api_key|user|password)$')


def _resolve_manual_keystore_values(keys):
    """
    Resolve a list of ${KEY} names (extracted from a generated pipeline) back
    to their plaintext credential values, for display in the "manual keystore"
    deploy diff banner. Only used when the network manages its keystore
    manually — the operator needs the actual values to run `logstash-keystore
    add` on the Logstash node themselves.

    Returns {key_name: plaintext_value}, omitting any key that can't be
    resolved (unknown format, missing record, or empty value).
    """
    parsed = {}
    cred_ids = set()
    conn_ids = set()

    for key in keys:
        m = _SNMP_ES_KEY_RE.match(key)
        if m:
            conn_id = int(m.group(1))
            conn_ids.add(conn_id)
            parsed[key] = ('es', conn_id, m.group(2))
            continue
        m = _SNMP_CRED_KEY_RE.match(key)
        if m:
            cred_id = int(m.group(1))
            cred_ids.add(cred_id)
            parsed[key] = ('snmp', cred_id, m.group(2))

    credentials = {c.id: c for c in Credential.objects.filter(id__in=cred_ids)} if cred_ids else {}
    connections = {c.id: c for c in Connection.objects.filter(id__in=conn_ids)} if conn_ids else {}

    values = {}
    for key, (kind, obj_id, field) in parsed.items():
        try:
            if kind == 'es':
                conn = connections.get(obj_id)
                if not conn:
                    continue
                if field == 'api_key':
                    values[key] = conn.get_api_key()
                elif field == 'user':
                    values[key] = conn.username
                elif field == 'password':
                    values[key] = conn.get_password()
            else:
                cred = credentials.get(obj_id)
                if not cred:
                    continue
                if field in ('v1', 'v2'):
                    values[key] = cred.get_community()
                elif field == 'v3_auth':
                    values[key] = cred.get_auth_pass()
                elif field == 'v3_priv':
                    values[key] = cred.get_priv_pass()
        except Exception:
            logger.warning(f"Could not resolve manual keystore value for key {key}", exc_info=True)

    return {k: v for k, v in values.items() if v}


def _get_unique_templates_for_network(devices):
    """
    Get unique device templates used by devices in a network.
    
    Args:
        devices: QuerySet or list of Device objects
        
    Returns:
        List of unique DeviceTemplate objects (including None for devices without templates)
    """
    templates_dict = {}
    has_none_template = False
    
    for device in devices:
        if device.device_template:
            templates_dict[device.device_template.id] = device.device_template
        else:
            has_none_template = True
    
    templates = list(templates_dict.values())
    
    # Add None as a "template" if any devices don't have a template
    if has_none_template:
        templates.append(None)
    
    return templates


def _get_template_pipeline_name(network, template, pipeline_type='polling'):
    """
    Generate pipeline name for a network+template combination.
    
    Args:
        network: Network object
        template: DeviceTemplate object or None
        pipeline_type: Type of pipeline ('polling', 'trap', 'discovery')
        
    Returns:
        Pipeline name string
    """
    network_name = _sanitize_pipeline_name_component(network.name)
    
    if template:
        template_name = _sanitize_pipeline_name_component(template.name)
        return f"snmp-{network_name}-{template_name}-{pipeline_type}"
    else:
        return f"snmp-{network_name}-no-template-{pipeline_type}"


def GetCredentials(request):
    """Get all SNMP credentials"""
    try:
        from django.db.models import Count
        credentials = Credential.objects.annotate(
            device_count=Count('devices')
        ).values('id', 'name', 'version', 'description', 'security_level', 'device_count')
        return JsonResponse(list(credentials), safe=False, status=200)
    except Exception as e:
        return HttpResponse(f"Error fetching credentials: {str(e)}", status=500)


def GetNetworks(request):
    """Get all SNMP networks"""
    try:
        from django.db.models import Count

        networks = Network.objects.select_related('connection', 'agent_connection').annotate(
            device_count=Count('devices')
        ).all()
        networks_data = []
        for network in networks:
            namespace_value = getattr(network, 'namespace', 'default')
            network_dict = {
                'id': network.id,
                'name': network.name,
                'network_range': network.network_range,
                'namespace': namespace_value,
                'interval': network.interval,
                'discovery_enabled': network.discovery_enabled,
                'traps_enabled': network.traps_enabled,
                'discovery_credential': network.discovery_credential_id,
                'credential': network.credential_id,
                'connection': network.connection_id,
                'connection_name': network.connection.name if network.connection else None,
                'deployment_mode': network.deployment_mode,
                'credential_mode': network.credential_mode,
                'agent_connection': network.agent_connection_id,
                'agent_connection_name': network.agent_connection.name if network.agent_connection else None,
                'device_count': network.device_count
            }
            networks_data.append(network_dict)
        return JsonResponse(networks_data, safe=False, status=200)
    except Exception as e:
        return HttpResponse(f"Error fetching networks: {str(e)}", status=500)


@require_admin_role
def AddCredential(request):
    """Add a new SNMP credential"""
    try:
        # Extract form data
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        version = request.POST.get('version')

        # Create credential object
        credential = Credential(
            name=name,
            description=description,
            version=version
        )

        # Set version-specific fields
        if version in ['1', '2c']:
            credential.community = request.POST.get('community', 'public')
        elif version == '3':
            credential.security_name = request.POST.get('security_name')
            credential.security_level = request.POST.get('security_level')

            # Set auth fields if needed
            if credential.security_level in ['authNoPriv', 'authPriv']:
                credential.auth_protocol = request.POST.get('auth_protocol')
                credential.auth_pass = request.POST.get('auth_pass')

            # Set priv fields if needed
            if credential.security_level == 'authPriv':
                credential.priv_protocol = request.POST.get('priv_protocol')
                credential.priv_pass = request.POST.get('priv_pass')

        # Save (this will trigger validation and encryption.py)
        credential.save()

        # Mark config as changed: a new secret may need to be provisioned into
        # keystores on the next deploy (Agent/CPM-keystore mode).
        SNMPDeploymentState.mark_config_changed()

        return JsonResponse({'id': credential.id, 'message': 'Credential created successfully!'}, status=200)

    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        return HttpResponse(f"Error creating credential: {str(e)}", status=500)


@require_admin_role
def UpdateCredential(request, credential_id):
    """Update an existing SNMP credential"""
    try:
        credential = Credential.objects.get(pk=credential_id)

        # Update basic fields
        credential.name = request.POST.get('name', credential.name)
        credential.description = request.POST.get('description', credential.description)
        credential.version = request.POST.get('version', credential.version)

        # Clear all version-specific fields first
        credential.community = ''
        credential.security_name = ''
        credential.security_level = ''
        credential.auth_protocol = ''
        credential.auth_pass = ''
        credential.priv_protocol = ''
        credential.priv_pass = ''

        # Set version-specific fields
        if credential.version in ['1', '2c']:
            credential.community = request.POST.get('community', 'public')
        elif credential.version == '3':
            credential.security_name = request.POST.get('security_name')
            credential.security_level = request.POST.get('security_level')

            # Set auth fields if needed
            if credential.security_level in ['authNoPriv', 'authPriv']:
                credential.auth_protocol = request.POST.get('auth_protocol')
                auth_pass = request.POST.get('auth_pass')
                # Only update password if provided (not empty)
                if auth_pass:
                    credential.auth_pass = auth_pass

            # Set priv fields if needed
            if credential.security_level == 'authPriv':
                credential.priv_protocol = request.POST.get('priv_protocol')
                priv_pass = request.POST.get('priv_pass')
                # Only update password if provided (not empty)
                if priv_pass:
                    credential.priv_pass = priv_pass

        # Save (this will trigger validation and encryption.py)
        credential.save()

        # Mark config as changed: a rotated secret changes keystore values even
        # though no pipeline LSCL changes, so the deploy indicator must light up.
        SNMPDeploymentState.mark_config_changed()

        return JsonResponse({'id': credential.id, 'message': 'Credential updated successfully!'}, status=200)

    except Credential.DoesNotExist:
        return JsonResponse({'error': 'Credential not found'}, status=404)
    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        return HttpResponse(f"Error updating credential: {str(e)}", status=500)


def GetCredential(request, credential_id):
    """Get a single credential (without sensitive data)"""
    try:
        credential = Credential.objects.get(pk=credential_id)

        data = {
            'id': credential.id,
            'name': credential.name,
            'description': credential.description,
            'version': credential.version,
        }

        # Add version-specific fields (without passwords)
        if credential.version in ['1', '2c']:
            # Don't send community string for security
            data['community'] = '***'
        elif credential.version == '3':
            data['security_name'] = credential.security_name
            data['security_level'] = credential.security_level

            if credential.security_level in ['authNoPriv', 'authPriv']:
                data['auth_protocol'] = credential.auth_protocol
                # Don't send password
                data['auth_pass'] = '***' if credential.auth_pass else ''

            if credential.security_level == 'authPriv':
                data['priv_protocol'] = credential.priv_protocol
                # Don't send password
                data['priv_pass'] = '***' if credential.priv_pass else ''

        return JsonResponse(data)

    except Credential.DoesNotExist:
        return JsonResponse({'error': 'Credential not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_admin_role
def DeleteCredential(request, credential_id):
    """Delete a credential"""
    try:
        credential = Credential.objects.get(pk=credential_id)
        credential.delete()

        # Mark config as changed: removing a credential may orphan keystore
        # entries that need to be pruned on the next deploy.
        SNMPDeploymentState.mark_config_changed()

        return JsonResponse({
            'success': True,
            'message': 'Credential deleted successfully!'
        })

    except Credential.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Credential not found'
        }, status=404)
    except Exception as e:
        return HttpResponse(f"Error deleting credential: {str(e)}", status=500)


def _get_pipeline_name(network):
    """
    Generate a sanitized pipeline name for a network (legacy single-pipeline format).
    Format: snmp-{network_name}-polling
    This is kept for backward compatibility to detect and delete old pipelines.
    """
    sanitized_network_name = _sanitize_pipeline_name_component(network.name)
    return f"snmp-{sanitized_network_name}-polling"


def _create_or_update_pipeline(es_connection, pipeline_name, pipeline_content, description=""):
    """
    Helper function to create or update a Logstash pipeline in Elasticsearch.
    Only updates if the pipeline content has actually changed.

    Args:
        es_connection: Elasticsearch connection object
        pipeline_name: Name of the pipeline
        pipeline_content: Pipeline configuration string
        description: Optional description for the pipeline

    Returns:
        tuple: (success: bool, is_new: bool, error: str or None)
    """

    try:
        # Check if pipeline already exists
        pipeline_exists = False
        existing_settings = None
        existing_metadata = None
        existing_pipeline_content = None

        try:
            existing = es_connection.logstash.get_pipeline(id=pipeline_name)
            if pipeline_name in existing:
                pipeline_exists = True
                existing_settings = existing[pipeline_name].get('pipeline_settings', {})
                existing_metadata = existing[pipeline_name].get('pipeline_metadata', {})
                existing_pipeline_content = existing[pipeline_name].get('pipeline', '')
        except:
            pipeline_exists = False

        # If pipeline exists and content is identical, skip the update
        if pipeline_exists:
            content_match = existing_pipeline_content == pipeline_content
            logger.debug(
                f"Pipeline {pipeline_name} comparison: existing_len={len(existing_pipeline_content)}, new_len={len(pipeline_content)}, match={content_match}")

            if content_match:
                # No changes needed - return success=True, is_new=False, error=None, was_updated=False
                logger.info(f"Pipeline {pipeline_name} unchanged - skipping update")
                return (True, False, None, False)
            else:
                logger.info(f"Pipeline {pipeline_name} has changes - updating")

        # Prepare pipeline body
        pipeline_body = {
            "pipeline": pipeline_content,
            "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "username": "logstashui",
            "description": description
        }

        # Use existing settings/metadata if updating, otherwise use defaults
        if pipeline_exists and existing_settings:
            pipeline_body["pipeline_settings"] = existing_settings
        else:
            pipeline_body["pipeline_settings"] = {
                "pipeline.batch.delay": 50,
                "pipeline.batch.size": 125,
                "pipeline.workers": 1,
                "queue.checkpoint.writes": 1024,
                "queue.max_bytes": "1gb",
                "queue.type": "memory"
            }

        if pipeline_exists and existing_metadata:
            pipeline_body["pipeline_metadata"] = existing_metadata
        else:
            pipeline_body["pipeline_metadata"] = {
                "version": 1,
                "type": "logstash_pipeline"
            }

        # Create or update the pipeline
        es_connection.logstash.put_pipeline(id=pipeline_name, body=pipeline_body)

        return (True, not pipeline_exists, None, True)

    except Exception as e:
        return (False, False, str(e), False)


# ============================================================================
# Agent-mode pipeline generation helpers
#
# These centralize per-network pipeline generation so the Agent deploy path
# (which stores pipelines as Django Pipeline records instead of ES CPM) can
# reuse the exact same generation logic. Generation is mode-agnostic; the
# generator itself decides keystore-vs-inline credentials from
# network.deployment_mode.
# ============================================================================


def _build_trap_components(network, input_data=None):
    """
    Build the trap pipeline component dict for a network (traps input + output).

    Mode-agnostic: credentials are emitted as keystore references or inline
    based on _uses_keystore(network), which covers both Agent mode and
    Centralized mode with credential_mode='KEYSTORE'.
    """
    if input_data is None:
        input_data = {
            "network": network,
            "devices": {"v1_v2c": {}, "v3": {}},
            "connection": network.connection,
        }

    credential = network.credential
    trap_input_config = {
        "host": "0.0.0.0",
        "port": 1662,
        "oid_map_field_values": False,
        "oid_mapping_format": "dotted_string",
        "supported_versions": []
    }

    use_keystore = _uses_keystore(network)

    if credential.version in ['1', '2c']:
        trap_input_config["supported_versions"].append(credential.version)
        if credential.community:
            if use_keystore:
                suffix = 'v1' if credential.version == '1' else 'v2'
                trap_input_config["community"] = ["${" + f"snmp_{credential.id}_{suffix}" + "}"]
            else:
                trap_input_config["community"] = [decrypt_credential(credential.community)]
    elif credential.version == '3':
        trap_input_config["supported_versions"].append("3")
        if credential.security_name:
            trap_input_config["security_name"] = credential.security_name
        if credential.auth_protocol:
            trap_input_config["auth_protocol"] = credential.auth_protocol
        if credential.auth_pass:
            trap_input_config["auth_pass"] = (
                "${" + f"snmp_{credential.id}_v3_auth" + "}"
                if use_keystore else decrypt_credential(credential.auth_pass)
            )
        if credential.priv_protocol:
            trap_input_config["priv_protocol"] = credential.priv_protocol
        if credential.priv_pass:
            trap_input_config["priv_pass"] = (
                "${" + f"snmp_{credential.id}_v3_priv" + "}"
                if use_keystore else decrypt_credential(credential.priv_pass)
            )
        if credential.security_level:
            trap_input_config["security_level"] = credential.security_level

    return {
        "input": [{
            "id": "input_snmptrap_1",
            "type": "input",
            "plugin": "snmptrap",
            "config": trap_input_config
        }],
        "filter": [
            {
                "id": "filter_mutate_trap_1",
                "type": "filter",
                "plugin": "mutate",
                "config": {
                    "add_field": {
                        "[event][category]": "traps"
                    }
                }
            }
        ],
        "output": _generate_output(network, snmp_type="traps")
    }


def _build_network_pipeline_configs(network, profile_cache=None):
    """
    Generate all pipeline configs a network should produce.

    Mode-agnostic: the generator embeds credentials inline for CENTRALIZED
    networks and emits keystore references for AGENT networks.

    Returns:
        list of dicts: {pipeline_name, config, pipeline_type, template_name}
    """
    if profile_cache is None:
        profile_cache = {}

    results = []
    devices = list(network.devices.all())
    templates = _get_unique_templates_for_network(devices)

    # Per-template polling pipelines
    for template in templates:
        template_id = template.id if template else None
        template_name = template.name if template else 'no-template'

        input_data = {
            "network": network,
            "devices": {"v1_v2c": {}, "v3": {}},
            "connection": network.connection
        }

        has_template_devices = False
        for device in devices:
            if not device.credential:
                continue
            device_template_id = device.device_template.id if device.device_template else None
            if device_template_id != template_id:
                continue
            has_template_devices = True
            credential = device.credential
            if credential.version in ['1', '2c']:
                input_data["devices"]["v1_v2c"][device.name] = device
            elif credential.version == '3':
                input_data["devices"]["v3"][device.name] = device

        if not has_template_devices:
            continue

        input_components, oid_mappings, normalizers = _generate_input(
            input_data, profile_cache, template_filter=template_id
        )
        filter_components = _generate_filters(oid_mappings, network, normalizers, input_data=input_data)
        components = {
            "input": input_components,
            "filter": filter_components,
            "output": _generate_output(network, snmp_type="polling", device_template=template)
        }
        config = ComponentToPipeline(components, test=False).components_to_logstash_config()
        results.append({
            'pipeline_name': _get_template_pipeline_name(network, template, 'polling'),
            'config': config,
            'pipeline_type': 'polling',
            'template_name': template_name,
        })

    # Trap pipeline
    if network.traps_enabled and network.credential:
        trap_components = _build_trap_components(network)
        config = ComponentToPipeline(trap_components, test=False).components_to_logstash_config()
        results.append({
            'pipeline_name': f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps",
            'config': config,
            'pipeline_type': 'trap',
            'template_name': None,
        })

    # Discovery pipeline
    if network.discovery_enabled and network.discovery_credential:
        discovery_input_data = {
            "network": network,
            "devices": {"v1_v2c": {}, "v3": {}},
            "connection": network.connection
        }
        discovery_input_components, discovery_oid_mappings = _generate_discovery_input(network)
        discovery_filter_components = _generate_discovery_filters(discovery_oid_mappings, network)
        discovery_components = {
            "input": discovery_input_components,
            "filter": discovery_filter_components,
            "output": _generate_output(network, snmp_type="discovery")
        }
        config = ComponentToPipeline(discovery_components, test=False).components_to_logstash_config()
        results.append({
            'pipeline_name': f"snmp-{_sanitize_pipeline_name_component(network.name)}-discovery",
            'config': config,
            'pipeline_type': 'discovery',
            'template_name': None,
        })

    return results


def _collect_network_keystore_entries(network):
    """
    Return {key_name: plaintext_value} of all keystore entries an Agent-mode
    network's pipelines reference (SNMP device creds + ES output creds).
    """
    entries = {}
    entries.update(es_connection_keystore_entries(network.connection))

    for device in network.devices.all():
        if device.credential:
            entries.update(snmp_credential_keystore_entries(device.credential))

    if network.traps_enabled and network.credential:
        entries.update(snmp_credential_keystore_entries(network.credential))

    if network.discovery_enabled and network.discovery_credential:
        entries.update(snmp_credential_keystore_entries(network.discovery_credential))

    return entries


def _network_keystore_key_names(network):
    """
    Names-only mirror of _collect_network_keystore_entries(): the set of
    keystore key names a network's pipelines reference, WITHOUT decrypting any
    secret. Kept in lockstep with _collect_network_keystore_entries so scoping
    never diverges from what actually gets provisioned.
    """
    names = set()
    names.update(es_connection_keystore_key_names(network.connection))

    for device in network.devices.all():
        if device.credential:
            names.update(snmp_credential_keystore_key_names(device.credential))

    if network.traps_enabled and network.credential:
        names.update(snmp_credential_keystore_key_names(network.credential))

    if network.discovery_enabled and network.discovery_credential:
        names.update(snmp_credential_keystore_key_names(network.discovery_credential))

    return names


def _network_has_pipeline_devices(network):
    """True if a network should generate at least one pipeline."""
    has_devices = any(d.credential for d in network.devices.all())
    return has_devices or (network.traps_enabled and network.credential) \
        or (network.discovery_enabled and network.discovery_credential)


def _network_pipeline_names(network):
    """
    Names-only mirror of _build_network_pipeline_configs(): the set of SNMP
    pipeline names a single network produces, without regenerating configs.
    Kept in lockstep with _build_network_pipeline_configs so scoping never
    diverges from what actually gets deployed.
    """
    names = set()
    devices = list(network.devices.all())

    for template in _get_unique_templates_for_network(devices):
        template_id = template.id if template else None
        has_template_devices = any(
            d.credential and (d.device_template.id if d.device_template else None) == template_id
            for d in devices
        )
        if has_template_devices:
            names.add(_get_template_pipeline_name(network, template, 'polling'))

    if network.traps_enabled and network.credential:
        names.add(f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps")

    if network.discovery_enabled and network.discovery_credential:
        names.add(f"snmp-{_sanitize_pipeline_name_component(network.name)}-discovery")

    return names


def agent_snmp_pipeline_names(connection):
    """
    The set of SNMP pipeline names a specific agent should host, unioned across
    every Agent-mode network assigned to that agent (agent_connection == it).

    Scoping key is the agent, never the policy: multiple networks can share one
    agent, but a network's pipelines belong to exactly one agent, so agents that
    merely share a base policy must not receive each other's SNMP pipelines.
    """
    if not connection:
        return set()
    names = set()
    networks = Network.objects.filter(
        agent_connection=connection, deployment_mode='AGENT'
    ).prefetch_related('devices__credential', 'devices__device_template')
    for network in networks:
        names.update(_network_pipeline_names(network))
    return names


def agent_snmp_keystore_keys(connection):
    """
    The set of SNMP keystore key names a specific agent needs, unioned across
    every Agent-mode network assigned to that agent. Same agent-scoping rule as
    agent_snmp_pipeline_names().

    Derives names WITHOUT decrypting secrets (names come from credential/
    connection ids + presence of the encrypted columns), so this can run on
    every check-in without materializing plaintext credentials in memory.
    """
    if not connection:
        return set()
    keys = set()
    networks = Network.objects.filter(
        agent_connection=connection, deployment_mode='AGENT'
    ).select_related('connection', 'credential', 'discovery_credential').prefetch_related('devices__credential')
    for network in networks:
        keys.update(_network_keystore_key_names(network))
    return keys


def _reconcile_policy_snmp_keystore(policy):
    """
    Ensure a policy's SNMP-managed keystore entries exactly match what all
    Agent-mode networks assigned to it require. Adds/updates needed entries and
    removes orphaned snmp-managed entries.
    """
    import hashlib

    needed = {}
    agent_networks = Network.objects.filter(
        deployment_mode='AGENT', agent_connection__policy_id=policy.id
    ).select_related('connection', 'credential', 'discovery_credential').prefetch_related(
        'devices__credential'
    )
    for network in agent_networks:
        needed.update(_collect_network_keystore_entries(network))

    # Upsert needed entries (Keystore.save encrypts + hashes plaintext values)
    for key_name, value in needed.items():
        expected_hash = hashlib.sha256(f"{key_name}{value}".encode('utf-8')).hexdigest()
        existing = Keystore.objects.filter(policy=policy, key_name=key_name).first()
        if existing:
            if existing.kv_hash != expected_hash or existing.managed_by != 'snmp':
                existing.key_value = value
                existing.managed_by = 'snmp'
                existing.save()
        else:
            Keystore.objects.create(
                policy=policy, key_name=key_name, key_value=value, managed_by='snmp'
            )

    # Remove orphaned snmp-managed entries no longer referenced by any network
    for entry in Keystore.objects.filter(policy=policy, managed_by='snmp'):
        if entry.key_name not in needed:
            entry.delete()


def _agent_policy_keystore_drift(policy):
    """
    Compare the SNMP keystore entries an agent policy SHOULD have (derived from
    its Agent-mode networks) against the Keystore rows currently stored.

    This catches credential/secret rotation: rotating a secret does not change
    any pipeline LSCL (it only holds a ${ref}), so without this the change would
    never surface in the deploy diff and never propagate to the agent.

    Returns {added: [...], changed: [...], removed: [...]} of key NAMES only
    (never values), or None when there is no drift.
    """
    import hashlib

    needed = {}
    agent_networks = Network.objects.filter(
        deployment_mode='AGENT', agent_connection__policy_id=policy.id
    ).select_related('connection', 'credential', 'discovery_credential').prefetch_related(
        'devices__credential'
    )
    for network in agent_networks:
        needed.update(_collect_network_keystore_entries(network))

    existing = {
        e.key_name: e.kv_hash
        for e in Keystore.objects.filter(policy=policy, managed_by='snmp')
    }

    added, changed = [], []
    for key_name, value in needed.items():
        expected_hash = hashlib.sha256(f"{key_name}{value}".encode('utf-8')).hexdigest()
        if key_name not in existing:
            added.append(key_name)
        elif existing[key_name] != expected_hash:
            changed.append(key_name)

    removed = [k for k in existing if k not in needed]

    if not (added or changed or removed):
        return None
    return {'added': sorted(added), 'changed': sorted(changed), 'removed': sorted(removed)}


def _cleanup_stale_es_pipelines(networks):
    """
    Best-effort removal of leftover [MANAGED] Elasticsearch CPM pipelines for
    networks now managed via Agent mode (handles CPM -> AGENT transition).

    Batched per ES connection (one get_pipeline() call per connection instead of
    one per network). Failures are logged as warnings, never surfaced as deploy
    errors, so a flaky/unreachable ES cluster can't block an Agent deploy.
    Returns the number of pipelines deleted.
    """
    by_conn = {}
    for network in networks:
        if network.connection_id:
            by_conn.setdefault(network.connection_id, []).append(network)

    total = 0
    for conn_id, conn_networks in by_conn.items():
        try:
            es = get_elastic_connection(conn_id)
            all_pipelines = es.logstash.get_pipeline()
        except Exception as e:
            logger.warning(f"Skipping stale-ES cleanup for connection {conn_id}: {e}")
            continue

        prefixes = [f"snmp-{_sanitize_pipeline_name_component(n.name)}-" for n in conn_networks]
        for name, data in all_pipelines.items():
            if '[MANAGED]' not in data.get('description', ''):
                continue
            if any(name.startswith(p) for p in prefixes):
                try:
                    es.logstash.delete_pipeline(id=name)
                    total += 1
                    logger.info(f"Removed stale ES pipeline '{name}' (now Agent-managed)")
                except Exception as e:
                    logger.warning(f"Failed to remove stale ES pipeline '{name}': {e}")
    return total


def _compute_agent_network_diffs(networks, profile_cache=None):
    """
    Build the list of Agent-mode deployment diff entries by comparing freshly
    generated pipeline configs against existing Django Pipeline records.

    Handles create/update for current Agent networks plus policy-level orphan
    detection (networks that switched AGENT -> CPM or were deleted).

    Args:
        networks: iterable of Network objects
        profile_cache: optional shared profile cache dict

    Returns:
        list of diff entries (each with deployment_mode == 'AGENT')
    """
    if profile_cache is None:
        profile_cache = {}

    diffs = []
    agent_expected_by_policy = {}
    policies_by_id = {}

    for network in networks:
        if network.deployment_mode != 'AGENT':
            continue

        policy = network.agent_connection.policy if network.agent_connection else None
        if not policy:
            diffs.append({
                'network_name': network.name,
                'pipeline_name': '(no agent policy)',
                'current': '',
                'new': '',
                'pipeline_type': 'error',
                'action': 'error',
                'deployment_mode': 'AGENT',
                'note': 'Network is in Agent mode but has no agent connection/policy assigned.'
            })
            continue

        agent_expected_by_policy.setdefault(policy.id, set())
        policies_by_id[policy.id] = policy
        agent_name = network.agent_connection.name if network.agent_connection else policy.name

        expected_configs = (
            _build_network_pipeline_configs(network, profile_cache)
            if _network_has_pipeline_devices(network) else []
        )

        for cfg in expected_configs:
            pipeline_name = cfg['pipeline_name']
            agent_expected_by_policy[policy.id].add(pipeline_name)
            new_config = cfg['config']

            existing = Pipeline.objects.filter(
                policy=policy, name=pipeline_name, managed_by='snmp'
            ).first()
            current_config = existing.lscl if existing else ''

            if not existing:
                action = 'create'
            elif current_config != new_config:
                action = 'update'
            else:
                action = 'none'

            if action != 'none':
                diffs.append({
                    'network_name': network.name,
                    'template_name': cfg['template_name'],
                    'pipeline_name': pipeline_name,
                    'current': current_config,
                    'new': new_config,
                    'pipeline_type': cfg['pipeline_type'],
                    'action': action,
                    'deployment_mode': 'AGENT',
                    'agent_policy_id': policy.id,
                    'network_id': network.id,
                    'destination_type': 'agent',
                    'destination_name': agent_name,
                })

    # Policy-level orphan detection (AGENT -> CPM transitions, deleted networks)
    snmp_policy_ids = set(
        Pipeline.objects.filter(managed_by='snmp').values_list('policy_id', flat=True)
    )
    keystore_policy_ids = set(
        Keystore.objects.filter(managed_by='snmp').values_list('policy_id', flat=True)
    )

    def _resolve_policy(pid):
        if pid in policies_by_id:
            return policies_by_id[pid]
        from PipelineManager.models import Policy
        policy = Policy.objects.filter(id=pid).first()
        if policy:
            policies_by_id[pid] = policy
        return policy

    for policy_id in snmp_policy_ids | set(agent_expected_by_policy.keys()):
        expected = agent_expected_by_policy.get(policy_id, set())
        for pl in Pipeline.objects.filter(policy_id=policy_id, managed_by='snmp'):
            if pl.name not in expected:
                orphan_policy = _resolve_policy(policy_id)
                diffs.append({
                    'network_name': 'Orphaned (Agent)',
                    'pipeline_name': pl.name,
                    'current': pl.lscl,
                    'new': '',
                    'pipeline_type': 'orphaned',
                    'action': 'delete',
                    'deployment_mode': 'AGENT',
                    'agent_policy_id': policy_id,
                    'destination_type': 'agent',
                    'destination_name': orphan_policy.name if orphan_policy else str(policy_id),
                    'note': 'Pipeline no longer matches any Agent-mode network.'
                })

    # Keystore drift per affected policy. Secret rotation leaves pipeline LSCL
    # untouched, so it must be surfaced independently or it never deploys.
    for policy_id in set(policies_by_id.keys()) | keystore_policy_ids:
        policy = _resolve_policy(policy_id)
        if not policy:
            continue
        drift = _agent_policy_keystore_drift(policy)
        if not drift:
            continue
        parts = []
        if drift['added']:
            parts.append(f"{len(drift['added'])} added")
        if drift['changed']:
            parts.append(f"{len(drift['changed'])} changed")
        if drift['removed']:
            parts.append(f"{len(drift['removed'])} removed")
        diffs.append({
            'network_name': 'Keystore',
            'pipeline_name': f'Keystore: {policy.name}',
            'current': '\n'.join(sorted(drift['removed'])),
            'new': '\n'.join(sorted(drift['added'] + drift['changed'])),
            'pipeline_type': 'keystore',
            'action': 'update',
            'deployment_mode': 'AGENT',
            'agent_policy_id': policy_id,
            'destination_type': 'agent',
            'destination_name': policy.name,
            'keystore_drift': drift,
            'note': 'Keystore values changed: ' + ', '.join(parts),
        })

    return diffs


def _deploy_agent_diffs(agent_diffs):
    """
    Apply Agent-mode deployment diffs to Django Pipeline/Keystore records.

    Args:
        agent_diffs: list of diff entries with deployment_mode == 'AGENT'

    Returns:
        dict: {created, updated, deleted, errors}
    """
    created = 0
    updated = 0
    deleted = 0
    keystore_changed = 0
    errors = []

    # Group diffs by policy
    diffs_by_policy = {}
    for diff in agent_diffs:
        if diff.get('action') == 'error':
            errors.append(diff.get('note', 'Agent network misconfiguration'))
            continue
        policy_id = diff.get('agent_policy_id')
        if policy_id is None:
            errors.append(f"Pipeline '{diff.get('pipeline_name')}': missing agent policy")
            continue
        diffs_by_policy.setdefault(policy_id, []).append(diff)

    from PipelineManager.models import Policy

    all_affected_network_ids = set()

    for policy_id, diffs in diffs_by_policy.items():
        try:
            policy = Policy.objects.get(id=policy_id)
        except Policy.DoesNotExist:
            errors.append(f"Agent policy {policy_id} not found")
            continue

        # Keystore password gate: required so the agent can decrypt SNMP secrets
        if not policy.keystore_password:
            errors.append(
                f"The policy '{policy.name}' assigned to this agent does not have a "
                f"keystore password set. Please set a keystore password for this policy "
                f"before deploying."
            )
            continue

        for diff in diffs:
            pipeline_name = diff.get('pipeline_name')
            action = diff.get('action')
            network_id = diff.get('network_id')
            if network_id:
                all_affected_network_ids.add(network_id)

            # Keystore-drift entries carry no real pipeline; they exist only to
            # pull the policy into this loop so reconcile (below) runs. Count the
            # affected keys so the deploy doesn't misreport "no changes".
            if diff.get('pipeline_type') == 'keystore':
                drift = diff.get('keystore_drift') or {}
                keystore_changed += (
                    len(drift.get('added', [])) + len(drift.get('changed', []))
                    + len(drift.get('removed', []))
                )
                continue

            try:
                if action in ('create', 'update'):
                    description = f"[MANAGED] SNMP {diff.get('pipeline_type', 'polling')} pipeline"
                    existing = Pipeline.objects.filter(
                        policy=policy, name=pipeline_name, managed_by='snmp'
                    ).first()
                    if existing:
                        existing.lscl = diff.get('new', '')
                        existing.description = description
                        existing.managed_by = 'snmp'
                        existing.save()
                        updated += 1
                    else:
                        Pipeline.objects.create(
                            policy=policy,
                            name=pipeline_name,
                            lscl=diff.get('new', ''),
                            description=description,
                            managed_by='snmp',
                        )
                        created += 1
                elif action == 'delete':
                    Pipeline.objects.filter(
                        policy=policy, name=pipeline_name, managed_by='snmp'
                    ).delete()
                    deleted += 1
            except Exception as e:
                errors.append(f"Pipeline '{pipeline_name}': {str(e)}")

        # Reconcile keystore entries for this policy (SNMP + ES output creds).
        # Always runs for every affected policy, so credential/secret rotation
        # (surfaced as a keystore-drift diff) updates the Keystore rows even when
        # no pipeline LSCL changed.
        try:
            _reconcile_policy_snmp_keystore(policy)
        except Exception as e:
            errors.append(f"Keystore reconciliation failed for policy '{policy.name}': {str(e)}")

    # CPM -> AGENT transition cleanup: remove leftover ES pipelines (batched
    # per connection; best-effort, never blocks the deploy).
    if all_affected_network_ids:
        _cleanup_stale_es_pipelines(
            Network.objects.filter(id__in=all_affected_network_ids).select_related('connection')
        )

    return {
        'created': created,
        'updated': updated,
        'deleted': deleted,
        'keystore_changed': keystore_changed,
        'errors': errors,
    }


# ============================================================================
# Network CRUD Operations
# ============================================================================

@require_admin_role
def AddNetwork(request):
    """Add a new SNMP network"""
    try:
        # Extract form data
        name = request.POST.get('name')
        network_range = request.POST.get('network_range')

        # Reject networks larger than /20 — discovery IP expansion would OOM
        import ipaddress as _ipaddress
        try:
            _net = _ipaddress.ip_network(network_range or '', strict=False)
            if _net.prefixlen < 20:
                return JsonResponse(
                    {'success': False, 'message': f'Network range {network_range} is too large. '
                     'Networks larger than /20 are not supported. '
                     'Please break it into smaller subnets (/20 or smaller).'},
                    status=400
                )
        except ValueError:
            pass  # Invalid CIDR will be caught by model validation below
        connection_id = request.POST.get('connection')
        agent_connection_id = request.POST.get('agent_connection')
        credential_id = request.POST.get('credential')
        discovery_credential_id = request.POST.get('discovery_credential')
        discovery_enabled = request.POST.get('discovery_enabled', 'true') == 'true'
        traps_enabled = request.POST.get('traps_enabled', 'false') == 'true'
        interval = int(request.POST.get('interval', 30))
        namespace = request.POST.get('namespace', 'default')
        namespace_from_device_template = request.POST.get('namespace_from_device_template', 'false') == 'true'
        deployment_mode = request.POST.get('deployment_mode', 'CENTRALIZED')
        credential_mode = request.POST.get('credential_mode', 'KEYSTORE')

        # Create network object
        network = Network(
            name=name,
            network_range=network_range,
            discovery_enabled=discovery_enabled,
            traps_enabled=traps_enabled,
            interval=interval,
            namespace=namespace,
            namespace_from_device_template=namespace_from_device_template,
            deployment_mode=deployment_mode,
            credential_mode=credential_mode,
        )

        # Set connection if provided
        if connection_id:
            network.connection_id = connection_id

        # Set agent connection if provided (AGENT mode only)
        if agent_connection_id:
            network.agent_connection_id = agent_connection_id

        # Set discovery credential if provided
        if discovery_credential_id:
            network.discovery_credential_id = discovery_credential_id

        # Set trap credential if provided
        if credential_id:
            network.credential_id = credential_id

        # Save (this will trigger validation)
        network.save()
        
        # Mark config as changed to show deployment indicator
        SNMPDeploymentState.mark_config_changed()

        return JsonResponse({'id': network.id, 'message': 'Network created successfully!'}, status=200)

    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        return HttpResponse(f"Error creating network: {str(e)}", status=500)


@require_admin_role
def UpdateNetwork(request, network_id):
    """Update an existing SNMP network"""
    try:
        network = Network.objects.get(pk=network_id)

        # Update fields
        network.name = request.POST.get('name', network.name)
        network.network_range = request.POST.get('network_range', network.network_range)

        # Reject networks larger than /20 — discovery IP expansion would OOM
        import ipaddress as _ipaddress
        try:
            _net = _ipaddress.ip_network(network.network_range or '', strict=False)
            if _net.prefixlen < 20:
                return JsonResponse(
                    {'success': False, 'message': f'Network range {network.network_range} is too large. '
                     'Networks larger than /20 are not supported. '
                     'Please break it into smaller subnets (/20 or smaller).'},
                    status=400
                )
        except ValueError:
            pass  # Invalid CIDR will be caught by model validation below
        network.namespace = request.POST.get('namespace', network.namespace)
        network.namespace_from_device_template = request.POST.get('namespace_from_device_template', 'false') == 'true'
        network.discovery_enabled = request.POST.get('discovery_enabled', 'true') == 'true'
        network.traps_enabled = request.POST.get('traps_enabled', 'false') == 'true'
        network.deployment_mode = request.POST.get('deployment_mode', network.deployment_mode)
        network.credential_mode = request.POST.get('credential_mode', network.credential_mode)

        # Update interval (convert to int)
        interval = request.POST.get('interval')
        if interval:
            network.interval = int(interval)

        # Update connection
        connection_id = request.POST.get('connection')
        if connection_id:
            network.connection_id = connection_id
        else:
            network.connection = None

        # Update agent connection
        agent_connection_id = request.POST.get('agent_connection')
        if agent_connection_id:
            network.agent_connection_id = agent_connection_id
        else:
            network.agent_connection = None

        # Update discovery credential
        discovery_credential_id = request.POST.get('discovery_credential')
        if discovery_credential_id:
            network.discovery_credential_id = discovery_credential_id
        else:
            network.discovery_credential = None

        # Update trap credential
        credential_id = request.POST.get('credential')
        if credential_id:
            network.credential_id = credential_id
        else:
            network.credential = None

        # Save (this will trigger validation)
        network.save()
        
        # Mark config as changed to show deployment indicator
        SNMPDeploymentState.mark_config_changed()

        return JsonResponse({'id': network.id, 'message': 'Network updated successfully!'}, status=200)

    except Network.DoesNotExist:
        return HttpResponse("Network not found", status=404)
    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        return HttpResponse(f"Error updating network: {str(e)}", status=500)


def GetNetwork(request, network_id):
    """Get a single network"""
    try:
        network = Network.objects.get(pk=network_id)

        data = {
            'id': network.id,
            'name': network.name,
            'network_range': network.network_range,
            'namespace': network.namespace,
            'namespace_from_device_template': network.namespace_from_device_template,
            'deployment_mode': network.deployment_mode,
            'credential_mode': network.credential_mode,
            'connection': network.connection_id if network.connection else None,
            'agent_connection': network.agent_connection_id if network.agent_connection else None,
            'discovery_credential': network.discovery_credential_id if network.discovery_credential else None,
            'credential': network.credential_id if network.credential else None,
            'discovery_enabled': network.discovery_enabled,
            'traps_enabled': network.traps_enabled,
            'interval': network.interval,
        }

        return JsonResponse(data)

    except Network.DoesNotExist:
        return JsonResponse({'error': 'Network not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_admin_role
def DeleteNetwork(request, network_id):
    """Delete a network and its underlying Logstash pipeline"""
    try:

        network = Network.objects.get(pk=network_id)
        pipeline_name = _get_pipeline_name(network)
        trap_pipeline_name = f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps"
        pipeline_deleted = False
        trap_pipeline_deleted = False
        pipeline_error = None

        # Try to delete the underlying pipelines if connection exists
        if network.connection:
            try:
                es = get_elastic_connection(network.connection.id)

                # Check if main pipeline exists before trying to delete
                try:
                    existing = es.logstash.get_pipeline(id=pipeline_name)
                    if pipeline_name in existing:
                        # Pipeline exists, delete it
                        es.logstash.delete_pipeline(id=pipeline_name)
                        pipeline_deleted = True
                except Exception as e:
                    # Pipeline doesn't exist or error checking, that's okay
                    pass

                # Check if trap pipeline exists before trying to delete
                try:
                    existing = es.logstash.get_pipeline(id=trap_pipeline_name)
                    if trap_pipeline_name in existing:
                        # Trap pipeline exists, delete it
                        es.logstash.delete_pipeline(id=trap_pipeline_name)
                        trap_pipeline_deleted = True
                except Exception as e:
                    # Trap pipeline doesn't exist or error checking, that's okay
                    pass

            except Exception as e:
                # Connection failed or pipeline deletion failed
                pipeline_error = str(e)

        # Delete the network from database
        network.delete()
        
        # Mark config as changed to show deployment indicator
        SNMPDeploymentState.mark_config_changed()

        # Build response message
        deleted_items = []
        if pipeline_deleted:
            deleted_items.append(f'pipeline "{pipeline_name}"')
        if trap_pipeline_deleted:
            deleted_items.append(f'trap pipeline "{trap_pipeline_name}"')

        # Return success response
        if deleted_items:
            return JsonResponse({
                'success': True,
                'message': f'Network and {", ".join(deleted_items)} deleted successfully!'
            })
        elif pipeline_error:
            return JsonResponse({
                'success': True,
                'message': f'Network deleted successfully, but pipeline deletion failed: {pipeline_error}'
            })
        else:
            return JsonResponse({
                'success': True,
                'message': 'Network deleted successfully!'
            })

    except Network.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Network not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Error deleting network: {str(e)}'}, status=500)


def GetNetworkPipelineName(request, network_id):
    """Get the pipeline name pattern for a network based on its name"""
    try:
        network = Network.objects.get(pk=network_id)

        # Generate sanitized pipeline name pattern: snmp-{network_name}-*
        sanitized_network_name = _sanitize_pipeline_name_component(network.name)
        pipeline_name = f"snmp-{sanitized_network_name}-*"

        return JsonResponse({
            'success': True,
            'pipeline_name': pipeline_name,
            'network_name': network.name
        })

    except Network.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Network not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def CheckUndeployedChanges(request):
    """
    Lightweight endpoint to check if there are undeployed SNMP changes.
    Uses timestamp comparison instead of full reconciliation for performance.
    
    Returns:
        JSON with has_changes boolean
    """
    try:
        has_changes = SNMPDeploymentState.has_undeployed_changes()
        
        return JsonResponse({
            'success': True,
            'has_changes': has_changes
        })
    except Exception as e:
        logger.error(f"Error checking undeployed changes: {str(e)}", exc_info=True)
        # On error, assume changes exist to be safe
        return JsonResponse({
            'success': True,
            'has_changes': True
        })


@require_admin_role
def GetDeployDiff(request):
    """Get diff for all network pipeline configurations"""
    try:
        # Clear the official profile cache to ensure we load fresh data from disk
        # This is important when profile JSON files have been edited
        global _OFFICIAL_PROFILE_CACHE
        _OFFICIAL_PROFILE_CACHE.clear()

        # Prefetch all related data in one go to avoid N+1 queries
        networks = Network.objects.select_related('connection', 'credential', 'discovery_credential').prefetch_related(
            Prefetch(
                'devices',
                queryset=Device.objects.select_related('credential', 'device_template').prefetch_related(
                    'device_template__profiles'  # Prefetch profiles from device template
                )
            )
        ).all()

        # Cache for profile data
        profile_cache = {}

        # Collect all pipeline names we need to fetch from ES
        pipeline_names_by_connection = {}
        connection_name_map = {}
        network_pipeline_map = {}

        for network in networks:
            # Agent-mode networks are reconciled against Django Pipeline records,
            # not Elasticsearch CPM. Handled in a dedicated section below.
            if network.deployment_mode == 'AGENT':
                continue
            if network.connection:
                conn_id = network.connection.id
                if conn_id not in pipeline_names_by_connection:
                    pipeline_names_by_connection[conn_id] = []
                connection_name_map[conn_id] = network.connection.name

                # Get unique templates for this network
                devices = network.devices.all()
                templates = _get_unique_templates_for_network(devices)
                
                # Generate pipeline names for each template
                polling_pipelines = {}
                for template in templates:
                    template_id = template.id if template else None
                    pipeline_name = _get_template_pipeline_name(network, template, 'polling')
                    polling_pipelines[template_id] = pipeline_name
                    pipeline_names_by_connection[conn_id].append(pipeline_name)
                
                # Also fetch old single-pipeline format for cleanup (backwards compatibility)
                old_pipeline_name = _get_pipeline_name(network)
                pipeline_names_by_connection[conn_id].append(old_pipeline_name)
                
                # Trap and discovery pipelines remain network-level (not per-template)
                trap_pipeline_name = f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps"
                discovery_pipeline_name = f"snmp-{_sanitize_pipeline_name_component(network.name)}-discovery"

                pipeline_names_by_connection[conn_id].extend(
                    [trap_pipeline_name, discovery_pipeline_name])
                
                network_pipeline_map[network.id] = {
                    'polling': polling_pipelines,  # Changed from 'main' to 'polling' dict
                    'trap': trap_pipeline_name,
                    'discovery': discovery_pipeline_name
                }

        # Batch fetch all pipelines from Elasticsearch
        existing_pipelines = {}
        for conn_id, pipeline_names in pipeline_names_by_connection.items():
            try:
                es_client = get_elastic_connection(conn_id)

                # Fetch ALL pipelines for this connection (avoids URL length limits with many pipelines)
                try:
                    all_pipelines = es_client.logstash.get_pipeline()
                    # Filter to only the ones we care about
                    for pipeline_name in pipeline_names:
                        if pipeline_name in all_pipelines:
                            existing_pipelines[pipeline_name] = all_pipelines[pipeline_name]
                except Exception:
                    # Pipelines don't exist or error, continue
                    pass
            except Exception:
                # Connection failed, continue
                pass

        network_diffs = []

        # Iterate through each network and build pipeline configurations
        for network in networks:
            # Agent-mode networks handled separately (compared vs Django records)
            if network.deployment_mode == 'AGENT':
                continue
            # Get all devices for this network (already prefetched)
            devices = network.devices.all()
            
            # Get unique templates for this network
            templates = _get_unique_templates_for_network(devices)
            
            # Skip networks that have nothing to generate a pipeline for
            has_devices = bool(devices.filter(credential__isnull=False).exists())
            has_special_pipelines = (
                (network.traps_enabled and network.credential)
                or (network.discovery_enabled and network.discovery_credential)
            )
            if not has_devices and not has_special_pipelines:
                continue
            
            # Generate a pipeline for each template
            for template in templates:
                template_id = template.id if template else None
                
                # Initialize pipeline data structure for this template
                input_data = {
                    "network": network,
                    "devices": {
                        "v1_v2c": {},
                        "v3": {}
                    },
                    "connection": network.connection
                }

                # Collect devices for this template
                device_ids = []
                for device in devices:
                    if not device.credential:
                        continue
                    
                    # Skip devices that don't match this template
                    device_template_id = device.device_template.id if device.device_template else None
                    if device_template_id != template_id:
                        continue
                    
                    device_ids.append(device.id)
                    credential = device.credential

                    # Group v1 and v2c together
                    if credential.version in ['1', '2c']:
                        input_data["devices"]["v1_v2c"][device.name] = device

                    # Group v3 devices
                    elif credential.version == '3':
                        input_data["devices"]["v3"][device.name] = device
                
                # Skip if no devices for this template
                if not device_ids:
                    continue
                
                # Generate pipeline configuration
                input_components, oid_mappings, normalizers = _generate_input(
                    input_data, profile_cache, template_filter=template_id
                )
                filter_components = _generate_filters(oid_mappings, network, normalizers, input_data=input_data)

                components = {
                    "input": input_components,
                    "filter": filter_components,
                    "output": _generate_output(network, snmp_type="polling", device_template=template)
                }

                new_config = ComponentToPipeline(components, test=False).components_to_logstash_config()

                # Get current pipeline configuration from pre-fetched data
                current_config = ""
                pipeline_name = network_pipeline_map.get(network.id, {}).get('polling', {}).get(template_id, '')

                if pipeline_name and pipeline_name in existing_pipelines:
                    pipeline_data = existing_pipelines[pipeline_name]
                    if 'pipeline' in pipeline_data:
                        current_config = pipeline_data['pipeline']
                
                # Add this template's pipeline to the network diff
                template_name = template.name if template else 'no-template'
                
                # Determine action based on whether pipeline exists and if it's different
                if not current_config:
                    action = 'create'
                elif current_config != new_config:
                    action = 'update'
                else:
                    action = 'none'  # No changes
                
                # Only add to diffs if there's an actual change
                if action != 'none':
                    network_diffs.append({
                        'network_name': network.name,
                        'template_name': template_name,
                        'pipeline_name': pipeline_name,
                        'current': current_config,
                        'new': new_config,
                        'pipeline_type': 'polling',
                        'action': action,
                        'has_devices': True
                    })
            
            # Check for old single-pipeline format and mark for deletion (backwards compatibility)
            old_pipeline_name = _get_pipeline_name(network)
            if old_pipeline_name in existing_pipelines:
                old_pipeline_data = existing_pipelines[old_pipeline_name]
                if 'pipeline' in old_pipeline_data:
                    old_config = old_pipeline_data['pipeline']
                    network_diffs.append({
                        'network_name': network.name,
                        'pipeline_name': old_pipeline_name,
                        'current': old_config,
                        'new': '',
                        'pipeline_type': 'polling_legacy',
                        'action': 'delete',
                        'note': 'Legacy single-pipeline format - replaced by per-template pipelines'
                    })
                    logger.info(f"Marking legacy pipeline {old_pipeline_name} for deletion")
            
            # Handle trap pipeline if traps are enabled
            if network.traps_enabled and network.credential:
                trap_pipeline_name = network_pipeline_map.get(network.id, {}).get('trap',
                                                                                  f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps")

                # Build trap pipeline components (keystore vs inline credentials
                # is decided by the network's deployment/credential mode).
                trap_components = _build_trap_components(network)

                # Generate new trap pipeline configuration
                new_trap_config = ComponentToPipeline(trap_components, test=False).components_to_logstash_config()

                # Get current trap pipeline configuration from pre-fetched data
                current_trap_config = ""
                if trap_pipeline_name in existing_pipelines:
                    pipeline_data = existing_pipelines[trap_pipeline_name]
                    if 'pipeline' in pipeline_data:
                        current_trap_config = pipeline_data['pipeline']

                # Only add if there's an actual change
                if not current_trap_config:
                    trap_action = 'create'
                elif current_trap_config != new_trap_config:
                    trap_action = 'update'
                else:
                    trap_action = 'none'
                
                if trap_action != 'none':
                    network_diffs.append({
                        'network_name': network.name,
                        'pipeline_name': trap_pipeline_name,
                        'current': current_trap_config,
                        'new': new_trap_config,
                        'pipeline_type': 'trap',
                        'action': trap_action
                    })
            else:
                # Traps disabled or no credential - check if trap pipeline exists and needs to be deleted
                trap_pipeline_name = network_pipeline_map.get(network.id, {}).get('trap',
                                                                                  f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps")
                current_trap_config = ""

                if trap_pipeline_name in existing_pipelines:
                    pipeline_data = existing_pipelines[trap_pipeline_name]
                    if 'pipeline' in pipeline_data:
                        current_trap_config = pipeline_data['pipeline']

                if current_trap_config:
                    network_diffs.append({
                        'network_name': network.name,
                        'pipeline_name': trap_pipeline_name,
                        'current': current_trap_config,
                        'new': '',
                        'pipeline_type': 'trap',
                        'action': 'delete'
                    })

            # Handle discovery pipeline if discovery is enabled
            if network.discovery_enabled and network.discovery_credential:
                discovery_pipeline_name = network_pipeline_map.get(network.id, {}).get('discovery',
                                                                                       f"snmp-{_sanitize_pipeline_name_component(network.name)}-discovery")

                # Generate discovery pipeline components
                discovery_input_components, discovery_oid_mappings = _generate_discovery_input(network)
                discovery_filter_components = _generate_discovery_filters(discovery_oid_mappings, network)

                discovery_components = {
                    "input": discovery_input_components,
                    "filter": discovery_filter_components,
                    "output": _generate_output(network, snmp_type="discovery")
                }

                # Generate new discovery pipeline configuration
                new_discovery_config = ComponentToPipeline(discovery_components,
                                                           test=False).components_to_logstash_config()

                # Get current discovery pipeline configuration from pre-fetched data
                current_discovery_config = ""
                if discovery_pipeline_name in existing_pipelines:
                    pipeline_data = existing_pipelines[discovery_pipeline_name]
                    if 'pipeline' in pipeline_data:
                        current_discovery_config = pipeline_data['pipeline']

                # Only add if there's an actual change
                if not current_discovery_config:
                    discovery_action = 'create'
                elif current_discovery_config != new_discovery_config:
                    discovery_action = 'update'
                else:
                    discovery_action = 'none'
                
                if discovery_action != 'none':
                    network_diffs.append({
                        'network_name': network.name,
                        'pipeline_name': discovery_pipeline_name,
                        'current': current_discovery_config,
                        'new': new_discovery_config,
                        'pipeline_type': 'discovery',
                        'action': discovery_action
                    })
            else:
                # Discovery is disabled or no credential - check if pipeline exists and needs to be deleted
                discovery_pipeline_name = network_pipeline_map.get(network.id, {}).get('discovery',
                                                                                       f"snmp-{_sanitize_pipeline_name_component(network.name)}-discovery")
                current_discovery_config = ""

                if discovery_pipeline_name in existing_pipelines:
                    pipeline_data = existing_pipelines[discovery_pipeline_name]
                    if 'pipeline' in pipeline_data:
                        current_discovery_config = pipeline_data['pipeline']

                if current_discovery_config:
                    network_diffs.append({
                        'network_name': network.name,
                        'pipeline_name': discovery_pipeline_name,
                        'current': current_discovery_config,
                        'new': '',
                        'pipeline_type': 'discovery',
                        'action': 'delete'
                    })

        # ---- Agent-mode networks: compare generated configs vs Django records ----
        network_diffs.extend(_compute_agent_network_diffs(networks, profile_cache))

        # Check for orphaned pipelines that will be deleted
        # Build a set of expected pipeline names
        expected_pipelines = set()
        for network in networks:
            if network.deployment_mode == 'AGENT':
                continue
            if network.connection:
                # Add per-template polling pipelines
                devices = Device.objects.filter(network=network).select_related('device_template')
                if devices.exists():
                    templates = _get_unique_templates_for_network(devices)
                    for template in templates:
                        pipeline_name = _get_template_pipeline_name(network, template, 'polling')
                        expected_pipelines.add(pipeline_name)
                
                # Add trap pipeline if traps are enabled
                if network.traps_enabled:
                    expected_pipelines.add(f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps")
                # Add discovery pipeline if discovery is enabled
                if network.discovery_enabled:
                    expected_pipelines.add(f"snmp-{_sanitize_pipeline_name_component(network.name)}-discovery")
        
        # Pipelines already scheduled for an explicit delete by the per-network
        # branches above (e.g. discovery/traps toggled off). Exclude these from
        # the orphan scan so the same pipeline doesn't get two delete entries.
        already_in_diff = {d['pipeline_name'] for d in network_diffs}

        # Check each connection for orphaned pipelines
        connections_checked = set()
        for network in networks:
            if network.deployment_mode == 'AGENT':
                continue
            if network.connection and network.connection.id not in connections_checked:
                connections_checked.add(network.connection.id)
                conn_id = network.connection.id
                
                try:
                    # Fetch ALL pipelines from this connection to find orphans
                    es_client = get_elastic_connection(conn_id)
                    all_pipelines = es_client.logstash.get_pipeline()
                    
                    # Find orphaned SNMP pipelines
                    for pipeline_name, pipeline_data in all_pipelines.items():
                        # Check if it's a managed SNMP pipeline (starts with "snmp-")
                        if pipeline_name.startswith("snmp-"):
                            description = pipeline_data.get('description', '')
                            
                            if '[MANAGED]' in description and pipeline_name not in expected_pipelines and pipeline_name not in already_in_diff:
                                # This is an orphaned pipeline - add to diffs as delete
                                network_diffs.append({
                                    'network_name': 'Orphaned',
                                    'pipeline_name': pipeline_name,
                                    'current': pipeline_data.get('pipeline', ''),
                                    'new': '',
                                    'pipeline_type': 'orphaned',
                                    'action': 'delete',
                                    'connection_id': conn_id,
                                    'destination_type': 'cpm',
                                    'destination_name': network.connection.name,
                                    'note': 'Pipeline no longer matches any configured network/template'
                                })
                except Exception as e:
                    # Connection error or ES error - skip orphan detection for this connection
                    logger.warning(f"Could not check for orphaned pipelines on connection {conn_id}: {str(e)}")
        
        # Enrich centralized (CPM) diff entries with destination + connection info
        # and, for keystore-credential-mode networks, the ${KEY} names the operator
        # must add manually via logstash-keystore. Agent-mode entries already carry
        # their destination from _compute_agent_network_diffs.
        _ref_re = re.compile(r'\$\{([A-Za-z0-9_]+)\}')
        networks_by_name = {n.name: n for n in networks}
        for d in network_diffs:
            if d.get('deployment_mode') == 'AGENT':
                continue
            net = networks_by_name.get(d.get('network_name'))
            if net and net.connection:
                d.setdefault('connection_id', net.connection.id)
                d.setdefault('destination_type', 'cpm')
                d.setdefault('destination_name', net.connection.name)
                if getattr(net, 'credential_mode', 'KEYSTORE') == 'KEYSTORE' and d.get('action') in ('create', 'update'):
                    keys = sorted(set(_ref_re.findall(d.get('new') or '')))
                    if keys:
                        d['manual_keystore_keys'] = keys
                        d['manual_keystore_values'] = _resolve_manual_keystore_values(keys)

        # ---- Pre-deploy blocking validation ----
        # These misconfigurations make a correct deploy impossible, so we block the
        # entire deploy (not just the offending network) and tell the user why.
        blocking_errors = []
        _seen_block_msgs = set()

        def _add_block(message, policy_id=None):
            if message in _seen_block_msgs:
                return
            _seen_block_msgs.add(message)
            entry = {'message': message}
            if policy_id is not None:
                entry['policy_id'] = policy_id
            blocking_errors.append(entry)

        for network in networks:
            if not _network_has_pipeline_devices(network):
                continue
            # Every SNMP pipeline emits an Elasticsearch output, so a network with
            # no ES connection can never be deployed.
            if not network.connection:
                _add_block(
                    f"Network '{network.name}' no longer has an Elasticsearch connection. "
                    f"Please assign one before deploying."
                )
            if network.deployment_mode == 'AGENT':
                policy = network.agent_connection.policy if network.agent_connection else None
                if not policy:
                    _add_block(
                        f"Network '{network.name}' is in Agent mode but is not assigned to an "
                        f"agent policy. Please assign an agent before deploying."
                    )
                elif not policy.keystore_password:
                    _add_block(
                        f"The policy '{policy.name}' assigned to this agent does not have a "
                        f"keystore password set. Please set a keystore password for this policy "
                        f"before deploying.",
                        policy_id=policy.id,
                    )

        # Check if there are actual changes
        # If user changed config then reverted, indicator may show changes but diff is empty
        has_actual_changes = any(
            diff.get('action') in ['create', 'update', 'delete']
            for diff in network_diffs
        )
        
        # Debug: log the planned changes
        logger.debug(f"Network diffs: {network_diffs}")
        logger.debug(f"Actions found: {[diff.get('action') for diff in network_diffs]}")
        logger.debug(f"has_actual_changes={has_actual_changes}")
        
        if not has_actual_changes:
            # No actual changes found - sync timestamps to clear the indicator
            # This handles the "change then revert" scenario
            state, _ = SNMPDeploymentState.objects.get_or_create(id=1)
            state.last_deployment = state.last_config_change
            state.save(update_fields=['last_deployment'])
            logger.info("No actual changes found in diff - cleared deployment indicator")
        
        # Cache the deployment plan for reuse when user clicks "Confirm Deploy"
        # Short timeout (60 seconds) - just long enough for user to review and click deploy
        from django.core.cache import cache
        cache.set('snmp_deployment_plan', network_diffs, timeout=60)
        logger.info(f"Cached deployment plan with {len(network_diffs)} pipeline changes")
        
        return JsonResponse({
            'success': True,
            'networks': network_diffs,
            'has_changes': has_actual_changes,
            'blocking_errors': blocking_errors,
            'connections': [
                {'id': conn_id, 'name': name}
                for conn_id, name in connection_name_map.items()
            ]
        })

    except Exception as e:
        logger.error(f"Error in GetDeployDiff: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_admin_role
def DeployConfiguration(request):
    """Deploy SNMP configuration - creates/updates Logstash pipelines in Elasticsearch"""
    try:
        # Try to use cached deployment plan from GetDeployDiff
        from django.core.cache import cache
        cached_plan = cache.get('snmp_deployment_plan')
        
        if cached_plan:
            logger.info(f"Using cached deployment plan with {len(cached_plan)} pipeline changes")
            # Clear cache immediately to prevent reuse
            cache.delete('snmp_deployment_plan')
            
            # Execute the cached plan
            pipelines_created = 0
            pipelines_updated = 0
            pipelines_deleted = 0
            errors = []

            # Split by deployment mode: Agent-mode entries go to Django records,
            # Centralized entries go to Elasticsearch CPM.
            agent_diffs = [d for d in cached_plan if d.get('deployment_mode') == 'AGENT']
            centralized_diffs = [d for d in cached_plan if d.get('deployment_mode') != 'AGENT']

            for diff in centralized_diffs:
                pipeline_name = diff.get('pipeline_name')
                action = diff.get('action')
                network_name = diff.get('network_name')
                connection_id = diff.get('connection_id')
                
                try:
                    # Prefer the connection_id captured at diff time (correct even for
                    # orphans and networks that were later edited); fall back to a
                    # name lookup only for older cached plans.
                    if connection_id is None:
                        if network_name == 'Orphaned':
                            errors.append(
                                f"Pipeline '{pipeline_name}': orphaned pipeline has no "
                                f"connection recorded — remove it manually from Elasticsearch."
                            )
                            continue
                        network = Network.objects.select_related('connection').get(name=network_name)
                        if not network or not network.connection:
                            errors.append(f"Pipeline '{pipeline_name}': No connection found")
                            continue
                        connection_id = network.connection.id
                    
                    es = get_elastic_connection(connection_id)
                    
                    if action == 'create' or action == 'update':
                        # Create or update pipeline using helper function
                        new_config = diff.get('new', '')
                        description = f"[MANAGED] SNMP {diff.get('pipeline_type', 'polling')} pipeline"
                        
                        try:
                            success, is_new, error, was_updated = _create_or_update_pipeline(
                                es, pipeline_name, new_config, description
                            )
                            
                            if success:
                                if is_new:
                                    pipelines_created += 1
                                    logger.info(f"Created pipeline: {pipeline_name}")
                                elif was_updated:
                                    pipelines_updated += 1
                                    logger.info(f"Updated pipeline: {pipeline_name}")
                            else:
                                errors.append(f"Failed to {action} '{pipeline_name}': {error}")
                        except Exception as e:
                            errors.append(f"Failed to {action} '{pipeline_name}': {str(e)}")
                    
                    elif action == 'delete':
                        # Delete pipeline
                        try:
                            es.logstash.delete_pipeline(id=pipeline_name)
                            pipelines_deleted += 1
                            logger.info(f"Deleted pipeline: {pipeline_name}")
                        except Exception as e:
                            errors.append(f"Failed to delete '{pipeline_name}': {str(e)}")
                
                except Network.DoesNotExist:
                    errors.append(f"Pipeline '{pipeline_name}': Network '{network_name}' not found")
                except Exception as e:
                    errors.append(f"Pipeline '{pipeline_name}': {str(e)}")

            # Apply Agent-mode diffs to Django Pipeline/Keystore records
            keystore_changed = 0
            if agent_diffs:
                agent_result = _deploy_agent_diffs(agent_diffs)
                pipelines_created += agent_result['created']
                pipelines_updated += agent_result['updated']
                pipelines_deleted += agent_result['deleted']
                keystore_changed += agent_result.get('keystore_changed', 0)
                errors.extend(agent_result['errors'])
            
            # Build response message
            if (pipelines_created == 0 and pipelines_updated == 0
                    and pipelines_deleted == 0 and keystore_changed == 0):
                if errors:
                    return JsonResponse({
                        'success': False,
                        'error': 'Failed to deploy any pipelines. Errors: ' + '; '.join(errors)
                    }, status=500)
                else:
                    return JsonResponse({
                        'success': True,
                        'message': 'All pipelines are already up to date - no changes needed',
                        'pipelines_created': 0,
                        'pipelines_updated': 0,
                        'pipelines_deleted': 0,
                        'errors': None
                    })
            
            message_parts = []
            if pipelines_created > 0:
                message_parts.append(f"{pipelines_created} pipeline(s) created")
            if pipelines_updated > 0:
                message_parts.append(f"{pipelines_updated} pipeline(s) updated")
            if pipelines_deleted > 0:
                message_parts.append(f"{pipelines_deleted} pipeline(s) deleted")
            if keystore_changed > 0:
                message_parts.append(f"{keystore_changed} keystore value(s) updated")
            
            message = "Successfully deployed: " + ", ".join(message_parts)
            if errors:
                message += f". Warnings: {'; '.join(errors)}"
            
            # Mark deployment as successful
            from django.utils import timezone
            state, _ = SNMPDeploymentState.objects.get_or_create(id=1)
            state.last_deployment = timezone.now()
            state.save(update_fields=['last_deployment'])
            logger.info("Deployment completed successfully using cached plan")
            
            return JsonResponse({
                'success': True,
                'message': message,
                'pipelines_created': pipelines_created,
                'pipelines_updated': pipelines_updated,
                'pipelines_deleted': pipelines_deleted,
                'errors': errors if errors else None
            })
        
        # No cached plan - fall back to full reconciliation
        logger.info("No cached deployment plan found, performing full reconciliation")
        
        # Clear the official profile cache to ensure we load fresh data from disk
        # This is important when profile JSON files have been edited
        global _OFFICIAL_PROFILE_CACHE
        _OFFICIAL_PROFILE_CACHE.clear()

        # Query all networks with their credentials
        networks = Network.objects.select_related('credential', 'discovery_credential', 'connection').all()

        if not networks.exists():
            return JsonResponse({
                'success': False,
                'error': 'No networks configured'
            }, status=400)

        pipelines_created = 0
        pipelines_updated = 0
        pipelines_deleted = 0
        errors = []

        # Iterate through each network and create/update pipeline
        for network in networks:
            # Agent-mode networks are deployed to Django records below, not ES CPM
            if network.deployment_mode == 'AGENT':
                continue
            try:
                # Initialize pipeline data structure for this network
                input_data = {
                    "network": network,
                    "devices": {
                        "v1_v2c": {},
                        "v3": {}
                    },
                    "connection": network.connection
                }

                # Get all devices for this network with device template and profiles prefetched
                devices = Device.objects.filter(network=network).select_related(
                    'credential', 'device_template'
                ).prefetch_related(
                    'device_template__profiles'  # Prefetch profiles from device template
                )

                for device in devices:
                    if not device.credential:
                        continue

                    credential = device.credential

                    # Group v1 and v2c together
                    if credential.version in ['1', '2c']:
                        input_data["devices"]["v1_v2c"][device.name] = device

                    # Group v3 devices
                    elif credential.version == '3':
                        input_data["devices"]["v3"][device.name] = device

                # Check if network has a connection
                if not network.connection:
                    errors.append(f"Network '{network.name}' has no Elasticsearch connection configured")
                    continue

                # Get Elasticsearch connection
                es = get_elastic_connection(network.connection.id)

                # Check if network has devices with credentials
                has_devices = devices.exists() and (input_data["devices"]["v1_v2c"] or input_data["devices"]["v3"])

                # Delete old legacy single-pipeline format if it exists
                try:
                    old_pipeline_name = _get_pipeline_name(network)
                    try:
                        existing = es.logstash.get_pipeline(id=old_pipeline_name)
                        if old_pipeline_name in existing:
                            # Legacy pipeline exists, delete it
                            es.logstash.delete_pipeline(id=old_pipeline_name)
                            pipelines_deleted += 1
                            logger.info(f"Deleted legacy pipeline: {old_pipeline_name}")
                    except Exception:
                        # Pipeline doesn't exist, that's okay
                        pass
                except Exception as delete_e:
                    logger.warning(f"Error checking for legacy pipeline: {str(delete_e)}")

                # Generate per-template pipelines if network has devices
                if has_devices:
                    # Get unique templates for this network
                    templates = _get_unique_templates_for_network(devices)
                    
                    # Generate a pipeline for each template
                    for template in templates:
                        template_id = template.id if template else None
                        template_name = template.name if template else 'no-template'
                        
                        # Initialize pipeline data for this template
                        template_input_data = {
                            "network": network,
                            "devices": {
                                "v1_v2c": {},
                                "v3": {}
                            },
                            "connection": network.connection
                        }
                        
                        # Collect devices for this template
                        for device in devices:
                            if not device.credential:
                                continue
                            
                            # Skip devices that don't match this template
                            device_template_id = device.device_template.id if device.device_template else None
                            if device_template_id != template_id:
                                continue
                            
                            credential = device.credential
                            
                            # Group v1 and v2c together
                            if credential.version in ['1', '2c']:
                                template_input_data["devices"]["v1_v2c"][device.name] = device
                            # Group v3 devices
                            elif credential.version == '3':
                                template_input_data["devices"]["v3"][device.name] = device
                        
                        # Skip if no devices for this template
                        if not (template_input_data["devices"]["v1_v2c"] or template_input_data["devices"]["v3"]):
                            continue
                        
                        # Generate components for this template
                        input_components, oid_mappings, normalizers = _generate_input(
                            template_input_data, template_filter=template_id
                        )
                        filter_components = _generate_filters(oid_mappings, network, normalizers, input_data=template_input_data)

                        components = {
                            "input": input_components,
                            "filter": filter_components,
                            "output": _generate_output(network, snmp_type="polling", device_template=template)
                        }

                        # Generate pipeline configuration
                        pipeline_content = ComponentToPipeline(components, test=False).components_to_logstash_config()
                        pipeline_name = _get_template_pipeline_name(network, template, 'polling')

                        # Use helper function to create or update the pipeline
                        success, is_new, error, was_updated = _create_or_update_pipeline(
                            es,
                            pipeline_name,
                            pipeline_content,
                            description=f"[MANAGED] SNMP polling pipeline for network: {network.name}, template: {template_name}"
                        )

                        if success:
                            if is_new:
                                pipelines_created += 1
                                logger.info(f"Created new pipeline: {pipeline_name}")
                            elif was_updated:
                                pipelines_updated += 1
                                logger.info(f"Updated pipeline: {pipeline_name}")
                            else:
                                logger.info(f"Pipeline {pipeline_name} unchanged - skipped")
                        else:
                            errors.append(f"Network '{network.name}', template '{template_name}': {error}")
                            logger.error(f"Failed to create/update pipeline {pipeline_name}: {error}")

                # Handle SNMP Trap pipeline if traps are enabled
                if network.traps_enabled:
                    if not network.credential:
                        errors.append(f"Network '{network.name}': Traps enabled but no credential configured")
                    else:
                        try:
                            # Generate trap pipeline name
                            trap_pipeline_name = f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps"

                            # Build trap pipeline components (keystore vs inline
                            # credentials decided by the network's mode).
                            trap_components = _build_trap_components(network)

                            # Generate trap pipeline configuration
                            trap_pipeline_content = ComponentToPipeline(trap_components,
                                                                        test=False).components_to_logstash_config()

                            # Create or update trap pipeline
                            trap_success, trap_is_new, trap_error, trap_was_updated = _create_or_update_pipeline(
                                es,
                                trap_pipeline_name,
                                trap_pipeline_content,
                                description=f"[MANAGED] SNMP Trap pipeline for network: {network.name}"
                            )

                            if trap_success:
                                if trap_is_new:
                                    pipelines_created += 1
                                elif trap_was_updated:
                                    pipelines_updated += 1
                                # If not new and not updated, it means no changes - don't count it
                            else:
                                errors.append(f"Network '{network.name}' trap pipeline: {trap_error}")
                        except Exception as trap_e:
                            logger.error(f"Network '{network.name}' trap pipeline error: {str(trap_e)}", exc_info=True)
                            errors.append(f"Network '{network.name}' trap pipeline: {str(trap_e)}")
                else:
                    # Traps are disabled, check if trap pipeline exists and delete it
                    try:
                        trap_pipeline_name = f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps"

                        # Check if pipeline exists
                        try:
                            existing = es.logstash.get_pipeline(id=trap_pipeline_name)
                            if trap_pipeline_name in existing:
                                # Pipeline exists, delete it
                                es.logstash.delete_pipeline(id=trap_pipeline_name)
                                pipelines_deleted += 1
                        except Exception:
                            # Pipeline doesn't exist, that's okay
                            pass
                    except Exception as delete_e:
                        errors.append(f"Network '{network.name}' trap pipeline deletion: {str(delete_e)}")

                # Handle Discovery pipeline if discovery is enabled
                if network.discovery_enabled:
                    if not network.discovery_credential:
                        errors.append(f"Network '{network.name}': Discovery enabled but no credential configured")
                    else:
                        try:
                            # Generate discovery pipeline name
                            discovery_pipeline_name = f"snmp-{_sanitize_pipeline_name_component(network.name)}-discovery"

                            # Generate discovery pipeline components
                            discovery_input_components, discovery_oid_mappings = _generate_discovery_input(network)
                            discovery_filter_components = _generate_discovery_filters(discovery_oid_mappings, network)

                            discovery_components = {
                                "input": discovery_input_components,
                                "filter": discovery_filter_components,
                                "output": _generate_output(network, snmp_type="discovery")
                            }

                            # Generate discovery pipeline configuration
                            discovery_pipeline_content = ComponentToPipeline(discovery_components,
                                                                             test=False).components_to_logstash_config()

                            # Create or update discovery pipeline
                            discovery_success, discovery_is_new, discovery_error, discovery_was_updated = _create_or_update_pipeline(
                                es,
                                discovery_pipeline_name,
                                discovery_pipeline_content,
                                description=f"[MANAGED] SNMP Discovery pipeline for network: {network.name}"
                            )

                            if discovery_success:
                                if discovery_is_new:
                                    pipelines_created += 1
                                elif discovery_was_updated:
                                    pipelines_updated += 1
                                # If not new and not updated, it means no changes - don't count it
                            else:
                                errors.append(f"Network '{network.name}' discovery pipeline: {discovery_error}")
                        except Exception as discovery_e:
                            logger.error(f"Network '{network.name}' discovery pipeline error: {str(discovery_e)}",
                                         exc_info=True)
                            errors.append(f"Network '{network.name}' discovery pipeline: {str(discovery_e)}")
                else:
                    # Discovery is disabled, check if discovery pipeline exists and delete it
                    try:
                        discovery_pipeline_name = f"snmp-{_sanitize_pipeline_name_component(network.name)}-discovery"

                        # Check if pipeline exists
                        try:
                            existing = es.logstash.get_pipeline(id=discovery_pipeline_name)
                            if discovery_pipeline_name in existing:
                                # Pipeline exists, delete it
                                es.logstash.delete_pipeline(id=discovery_pipeline_name)
                                pipelines_deleted += 1
                        except Exception:
                            # Pipeline doesn't exist, that's okay
                            pass
                    except Exception as delete_e:
                        errors.append(f"Network '{network.name}' discovery pipeline deletion: {str(delete_e)}")

            except Exception as e:
                errors.append(f"Network '{network.name}': {str(e)}")
                continue

        # Cleanup orphaned pipelines
        # Get all managed SNMP pipelines from Elasticsearch and delete ones that don't match current networks
        try:
            # Build a set of expected pipeline names
            expected_pipelines = set()
            for network in networks:
                if network.deployment_mode == 'AGENT':
                    continue
                if network.connection:
                    # Add per-template polling pipelines
                    devices = Device.objects.filter(network=network).select_related('device_template')
                    if devices.exists():
                        templates = _get_unique_templates_for_network(devices)
                        for template in templates:
                            pipeline_name = _get_template_pipeline_name(network, template, 'polling')
                            expected_pipelines.add(pipeline_name)
                    
                    # Add trap pipeline if traps are enabled
                    if network.traps_enabled:
                        expected_pipelines.add(f"snmp-{_sanitize_pipeline_name_component(network.name)}-traps")
                    # Add discovery pipeline if discovery is enabled
                    if network.discovery_enabled:
                        expected_pipelines.add(f"snmp-{_sanitize_pipeline_name_component(network.name)}-discovery")

            # Get all pipelines from Elasticsearch for each connection
            connections_checked = set()
            for network in networks:
                if network.deployment_mode == 'AGENT':
                    continue
                if network.connection and network.connection.id not in connections_checked:
                    connections_checked.add(network.connection.id)
                    try:
                        es = get_elastic_connection(network.connection.id)
                        all_pipelines = es.logstash.get_pipeline()

                        # Find orphaned SNMP pipelines
                        for pipeline_name in all_pipelines.keys():
                            # Check if it's a managed SNMP pipeline (starts with "snmp-")
                            if pipeline_name.startswith("snmp-"):
                                # Check if it has the [MANAGED] tag in description
                                pipeline_data = all_pipelines[pipeline_name]
                                description = pipeline_data.get('description', '')

                                if '[MANAGED]' in description and pipeline_name not in expected_pipelines:
                                    # This is an orphaned pipeline, delete it
                                    try:
                                        es.logstash.delete_pipeline(id=pipeline_name)
                                        pipelines_deleted += 1
                                        logger.info(f"Deleted orphaned pipeline: {pipeline_name}")
                                    except Exception as delete_err:
                                        errors.append(
                                            f"Failed to delete orphaned pipeline '{pipeline_name}': {str(delete_err)}")
                    except Exception as conn_err:
                        # Connection error, skip this connection
                        pass
        except Exception as cleanup_err:
            errors.append(f"Pipeline cleanup error: {str(cleanup_err)}")

        # Deploy Agent-mode networks to Django Pipeline/Keystore records
        keystore_changed = 0
        try:
            agent_diffs = _compute_agent_network_diffs(networks)
            if agent_diffs:
                agent_result = _deploy_agent_diffs(agent_diffs)
                pipelines_created += agent_result['created']
                pipelines_updated += agent_result['updated']
                pipelines_deleted += agent_result['deleted']
                keystore_changed += agent_result.get('keystore_changed', 0)
                errors.extend(agent_result['errors'])
        except Exception as agent_err:
            errors.append(f"Agent deployment error: {str(agent_err)}")

        # Build response message
        if (pipelines_created == 0 and pipelines_updated == 0
                and pipelines_deleted == 0 and keystore_changed == 0):
            if errors:
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to deploy any pipelines. Errors: ' + '; '.join(errors)
                }, status=500)
            else:
                # No changes needed - all pipelines are already up to date
                return JsonResponse({
                    'success': True,
                    'message': 'All pipelines are already up to date - no changes needed',
                    'pipelines_created': 0,
                    'pipelines_updated': 0,
                    'pipelines_deleted': 0,
                    'errors': None
                })

        message_parts = []
        if pipelines_created > 0:
            message_parts.append(f"{pipelines_created} pipeline(s) created")
        if pipelines_updated > 0:
            message_parts.append(f"{pipelines_updated} pipeline(s) updated")
        if pipelines_deleted > 0:
            message_parts.append(f"{pipelines_deleted} pipeline(s) deleted")
        if keystore_changed > 0:
            message_parts.append(f"{keystore_changed} keystore value(s) updated")

        message = "Successfully deployed: " + ", ".join(message_parts)

        if errors:
            message += f". Warnings: {'; '.join(errors)}"

        # Mark deployment as successful to clear the indicator
        from django.utils import timezone
        state, _ = SNMPDeploymentState.objects.get_or_create(id=1)
        state.last_deployment = timezone.now()
        state.save(update_fields=['last_deployment'])
        logger.info("Deployment completed successfully - updated deployment timestamp")

        return JsonResponse({
            'success': True,
            'message': message,
            'pipelines_created': pipelines_created,
            'pipelines_updated': pipelines_updated,
            'pipelines_deleted': pipelines_deleted,
            'errors': errors if errors else None
        })

    except Exception as e:
        logger.error(f"Unexpected error in DeployConfiguration: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)



# ============================================================================
# Device API Endpoints
# ============================================================================

def GetDevices(request):
    """Get paginated SNMP devices with search, filter, and sort"""
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 25))
        search = request.GET.get('search', '').strip()
        network_filter = request.GET.get('network', '').strip()
        sort_by = request.GET.get('sort_by', '-created_at')

        # Start with all devices - only fetch needed fields for performance
        queryset = Device.objects.select_related('credential', 'network', 'device_template').only(
            'id', 'name', 'ip_address', 'hostname', 'port', 'retries', 'timeout', 'created_at',
            'site', 'building', 'room',
            'credential__id', 'credential__name',
            'network__id', 'network__name', 'network__deployment_mode',
            'device_template__id', 'device_template__name'
        )

        # Apply search filter (name, IP address, or hostname)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(ip_address__icontains=search) | Q(hostname__icontains=search)
            )

        # Apply network filter
        if network_filter:
            queryset = queryset.filter(network_id=network_filter)

        # Apply sorting
        valid_sort_fields = ['name', '-name', 'ip_address', '-ip_address', 'hostname', '-hostname', 'created_at', '-created_at']
        if sort_by in valid_sort_fields:
            queryset = queryset.order_by(sort_by)

        # Manual pagination using limit/offset to avoid expensive COUNT queries
        # We fetch page_size + 1 to determine if there's a next page
        offset = (page - 1) * page_size
        limit = page_size + 1

        # Fetch one extra to check if there's a next page
        devices_page = list(queryset[offset:offset + limit])
        has_next = len(devices_page) > page_size

        # Remove the extra item if present
        if has_next:
            devices_page = devices_page[:page_size]

        has_previous = page > 1

        # Always get total count so users know how many devices they have
        # This is acceptable since it's cached by SQLite and indexes help
        total_count = queryset.count()
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

        # Serialize devices
        devices = []
        for device in devices_page:
            devices.append({
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'hostname': device.hostname,
                'port': device.port,
                'retries': device.retries,
                'timeout': device.timeout,
                'credential_id': device.credential.id if device.credential else None,
                'credential_name': device.credential.name if device.credential else None,
                'network_id': device.network.id if device.network else None,
                'network_name': device.network.name if device.network else None,
                'network_deployment_mode': device.network.deployment_mode if device.network else None,
                'device_template_id': device.device_template.id if device.device_template else None,
                'device_template_name': device.device_template.name if device.device_template else None,
                'device_template_display_name': format_display_name(device.device_template.name) if device.device_template else None,
                'site': device.site,
                'building': device.building,
                'room': device.room,
                'created_at': device.created_at.isoformat(),
            })

        return JsonResponse({
            'devices': devices,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': has_next,
            'has_previous': has_previous,
        })

    except Exception as e:
        return HttpResponse(f"Error fetching devices: {str(e)}", status=500)


def FindDeviceByHost(request):
    """Find a device by exact ip_address, hostname, or name match. Returns device details or null."""
    host = request.GET.get('host', '').strip()
    if not host:
        return JsonResponse({'device': None}, status=200)
    try:
        device = Device.objects.select_related('credential', 'network', 'device_template').filter(
            Q(ip_address=host) | Q(hostname=host) | Q(name=host)
        ).first()
        if not device:
            return JsonResponse({'device': None}, status=200)
        return JsonResponse({
            'device': {
                'id':                   device.id,
                'name':                 device.name,
                'ip_address':           device.ip_address or '',
                'hostname':             device.hostname or '',
                'port':                 device.port,
                'credential_id':        device.credential.id   if device.credential   else None,
                'credential_name':      device.credential.name if device.credential   else None,
                'network_id':           device.network.id      if device.network       else None,
                'network_name':         device.network.name    if device.network       else None,
                'device_template_id':   device.device_template.id   if device.device_template else None,
                'device_template_name': device.device_template.name if device.device_template else None,
                'device_template_display_name': format_display_name(device.device_template.name) if device.device_template else None,
            }
        }, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_admin_role
def AddDevice(request):
    """Add a new SNMP device"""
    try:
        # Extract form data
        name = request.POST.get('name')
        ip_address = request.POST.get('ip_address') or None
        hostname = request.POST.get('hostname') or None
        port = request.POST.get('port', 161)
        retries = request.POST.get('retries', 2)
        timeout = request.POST.get('timeout', 1000)
        credential_id = request.POST.get('credential')
        network_id = request.POST.get('network')
        device_template_id = request.POST.get('device_template')
        profile_names = request.POST.getlist('profiles')  # Get list of profile names

        # Create device object
        device = Device(
            name=name,
            ip_address=ip_address,
            hostname=hostname,
            port=int(port) if port else 161,
            retries=int(retries) if retries else 2,
            timeout=int(timeout) if timeout else 1000
        )

        # Set optional foreign keys
        if credential_id:
            device.credential_id = credential_id
        if network_id:
            device.network_id = network_id
        if device_template_id:
            device.device_template_id = device_template_id

        # Location fields
        device.site = request.POST.get('site') or None
        device.building = request.POST.get('building') or None
        device.room = request.POST.get('room') or None
        _lat = request.POST.get('latitude') or None
        _lon = request.POST.get('longitude') or None
        device.latitude = round(float(_lat), 6) if _lat else None
        device.longitude = round(float(_lon), 6) if _lon else None

        # Metadata JSON blob
        metadata_raw = request.POST.get('metadata', '{}')
        try:
            device.metadata = json.loads(metadata_raw) if metadata_raw else {}
        except (json.JSONDecodeError, ValueError):
            device.metadata = {}

        # Save (this will trigger validation)
        device.save()
        
        # Mark config as changed to show deployment indicator
        SNMPDeploymentState.mark_config_changed()

        # Note: Profiles are now managed through device templates, not directly on devices
        # The device_template relationship handles profile assignment

        return JsonResponse({'id': device.id, 'message': 'Device created successfully!'}, status=200)

    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        return HttpResponse(f"Error creating device: {str(e)}", status=500)


@require_admin_role
def UpdateDevice(request, device_id):
    """Update an existing SNMP device"""
    try:
        device = Device.objects.get(pk=device_id)

        # Update fields
        device.name = request.POST.get('name', device.name)
        device.ip_address = request.POST.get('ip_address') or None
        device.hostname = request.POST.get('hostname') or None
        port = request.POST.get('port')
        if port:
            device.port = int(port)
        retries = request.POST.get('retries')
        if retries:
            device.retries = int(retries)
        timeout = request.POST.get('timeout')
        if timeout:
            device.timeout = int(timeout)

        # Update optional foreign keys
        credential_id = request.POST.get('credential')
        if credential_id:
            device.credential_id = credential_id
        else:
            device.credential = None

        network_id = request.POST.get('network')
        if network_id:
            device.network_id = network_id
        else:
            device.network = None

        device_template_id = request.POST.get('device_template')
        if device_template_id:
            device.device_template_id = device_template_id
        else:
            device.device_template = None

        # Location fields
        device.site = request.POST.get('site') or None
        device.building = request.POST.get('building') or None
        device.room = request.POST.get('room') or None
        device.latitude = request.POST.get('latitude') or None
        device.longitude = request.POST.get('longitude') or None

        # Metadata JSON blob
        metadata_raw = request.POST.get('metadata', '{}')
        try:
            device.metadata = json.loads(metadata_raw) if metadata_raw else {}
        except (json.JSONDecodeError, ValueError):
            device.metadata = {}

        # Save (this will trigger validation)
        device.save()
        
        # Mark config as changed to show deployment indicator
        SNMPDeploymentState.mark_config_changed()

        # Note: Profiles are now managed through device templates, not directly on devices
        # The device_template relationship handles profile assignment

        return JsonResponse({'id': device.id, 'message': 'Device updated successfully!'}, status=200)

    except Device.DoesNotExist:
        return HttpResponse("Device not found", status=404)
    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        return HttpResponse(f"Error updating device: {str(e)}", status=500)


def GetDeviceLocationData(request):
    """
    Return aggregated location data from all devices so the modal can build
    hierarchical combobox suggestions without a dedicated location table.

    Response shape:
      {
        "sites":         ["HQ", ...],                              # all unique non-null site values
        "site_building": [{"site": "HQ", "building": "Bld A"}, ...]  # all (site, building) pairs
        "full":          [{"site":…, "building":…, "room":…, "latitude":…, "longitude":…}, ...]
      }
    """
    sites = list(
        Device.objects
        .exclude(site__isnull=True).exclude(site='')
        .values_list('site', flat=True)
        .distinct()
        .order_by('site')
    )

    site_building = list(
        Device.objects
        .exclude(building__isnull=True).exclude(building='')
        .values('site', 'building')
        .distinct()
        .order_by('site', 'building')
    )

    full = list(
        Device.objects
        .exclude(room__isnull=True).exclude(room='')
        .values('site', 'building', 'room', 'latitude', 'longitude')
        .distinct()
        .order_by('site', 'building', 'room')
    )

    # Coerce Decimal to str so JsonResponse can serialise them
    for entry in full:
        entry['latitude'] = str(entry['latitude']) if entry['latitude'] is not None else None
        entry['longitude'] = str(entry['longitude']) if entry['longitude'] is not None else None

    return JsonResponse({'sites': sites, 'site_building': site_building, 'full': full})


def GetDevice(request, device_id):
    """Get a single device"""
    try:
        device = Device.objects.get(pk=device_id)

        data = {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
            'hostname': device.hostname,
            'port': device.port,
            'retries': device.retries,
            'timeout': device.timeout,
            'credential': device.credential_id if device.credential else None,
            'network': device.network_id if device.network else None,
            'device_template': device.device_template_id if device.device_template else None,
            'site': device.site,
            'building': device.building,
            'room': device.room,
            'latitude': str(device.latitude) if device.latitude is not None else None,
            'longitude': str(device.longitude) if device.longitude is not None else None,
            'metadata': device.metadata,
        }

        return JsonResponse(data)

    except Device.DoesNotExist:
        return JsonResponse({'error': 'Device not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_admin_role
def DeleteDevice(request, device_id):
    """Delete a device"""
    try:
        device = Device.objects.get(pk=device_id)
        device.delete()
        
        # Mark config as changed to show deployment indicator
        SNMPDeploymentState.mark_config_changed()

        return HttpResponse("""
            <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg">
                Device deleted successfully!
                <script>
                    setTimeout(() => {
                        window.location.reload();
                    }, 500);
                </script>
            </div>
        """)

    except Device.DoesNotExist:
        return HttpResponse("Device not found", status=404)
    except Exception as e:
        return HttpResponse(f"Error deleting device: {str(e)}", status=500)


# ==================== Profile API Endpoints ====================

def GetNormalizerDefinitions(request):
    """Get normalizer definitions from JSON file"""
    try:
        normalizers_path = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'normalizers.json')
        
        if not os.path.exists(normalizers_path):
            return JsonResponse({'success': False, 'message': 'Normalizers file not found'}, status=404)
        
        with open(normalizers_path, 'r') as f:
            normalizers = json.load(f)
        
        return JsonResponse({
            'success': True,
            'normalizers': normalizers
        }, status=200)
    
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def GetOfficialProfile(request, profile_name):
    """Get an official profile from JSON file"""
    try:
        official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
        profile_path = os.path.join(official_profiles_dir, f"{profile_name}.json")

        if not os.path.exists(profile_path):
            return JsonResponse({'success': False, 'message': 'Profile not found'}, status=404)

        with open(profile_path, 'r') as f:
            profile_data = json.load(f)

        resolved_name = profile_data.get('name', profile_name)
        return JsonResponse({
            'success': True,
            'name': resolved_name,
            'display_name': format_display_name(resolved_name),
            'description': profile_data.get('description', ''),
            'vendor': profile_data.get('vendor', ''),
            'product': profile_data.get('product', ''),
            'profile_data': profile_data,
            'normalizers': profile_data.get('normalizers', [])
        }, status=200)

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def GetProfile(request, profile_name):
    """Get a user profile from database"""
    try:
        profile = Profile.objects.get(name=profile_name)
        return JsonResponse({
            'success': True,
            'name': profile.name,
            'display_name': format_display_name(profile.name),
            'description': profile.description,
            'vendor': profile.vendor,
            'product': profile.product,
            'profile_data': profile.profile_data,
            'normalizers': profile.normalizers
        }, status=200)

    except Profile.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Profile not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_admin_role
def AddProfile(request):
    """Add a new user profile"""
    try:
        data = json.loads(request.body)

        name = data.get('name')
        description = data.get('description', '')
        vendor = data.get('vendor', '')
        product = data.get('product', '')
        profile_data = data.get('profile_data', {})
        normalizers = data.get('normalizers', [])

        # Validate required fields
        if not name:
            return JsonResponse({'success': False, 'message': 'Profile name is required'}, status=400)

        # Check if profile already exists
        if Profile.objects.filter(name=name).exists():
            return JsonResponse({'success': False, 'message': 'A profile with this name already exists'}, status=400)

        # Create profile
        profile = Profile(
            name=name,
            description=description,
            vendor=vendor,
            product=product,
            profile_data=profile_data,
            normalizers=normalizers
        )
        profile.save()
        SNMPDeploymentState.mark_config_changed()

        return JsonResponse({
            'success': True,
            'message': 'Profile created successfully',
            'profile_id': profile.id
        }, status=200)

    except ValidationError as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_admin_role
def UpdateProfile(request, profile_name):
    """Update an existing user profile"""
    try:
        data = json.loads(request.body)

        # Get existing profile
        profile = Profile.objects.get(name=profile_name)

        # Update fields
        new_name = data.get('name', profile.name)
        profile.description = data.get('description', profile.description)
        profile.vendor = data.get('vendor', profile.vendor)
        profile.product = data.get('product', profile.product)
        profile.profile_data = data.get('profile_data', profile.profile_data)
        profile.normalizers = data.get('normalizers', profile.normalizers)

        # If name changed, check for conflicts
        if new_name != profile.name:
            if Profile.objects.filter(name=new_name).exists():
                return JsonResponse({'success': False, 'message': 'A profile with this name already exists'},
                                    status=400)
            profile.name = new_name

        profile.save()
        SNMPDeploymentState.mark_config_changed()

        return JsonResponse({
            'success': True,
            'message': 'Profile updated successfully'
        }, status=200)

    except Profile.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Profile not found'}, status=404)
    except ValidationError as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_admin_role
def DeleteProfile(request, profile_name):
    """Delete a user profile"""
    try:
        # Prevent deletion of the system profile
        if profile_name in ['system', 'generic_system.json']:
            return JsonResponse({
                'success': False,
                'message': 'The system profile cannot be deleted as it is required for all devices'
            }, status=403)

        profile = Profile.objects.get(name=profile_name)
        profile.delete()
        SNMPDeploymentState.mark_config_changed()

        return JsonResponse({
            'success': True,
            'message': 'Profile deleted successfully'
        }, status=200)

    except Profile.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Profile not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def GetAllProfiles(request):
    """Get all profiles (official and user) for dropdown"""
    try:
        all_profiles = []

        # Load ALL profiles from database (both official and user-created)
        for profile in Profile.objects.all():
            # Determine if it's an official profile (name ends with .json)
            is_official = profile.name.endswith('.json')

            all_profiles.append({
                'id': profile.id,  # Always use database ID
                'name': profile.name,
                'display_name': format_display_name(profile.name),
                'is_official': is_official,
                'vendor': profile.vendor or ''
            })

        # Sort by display name
        all_profiles.sort(key=lambda x: x['display_name'])

        return JsonResponse({'profiles': all_profiles}, status=200)

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def _device_host_filter(device):
    """Return an ES filter matching a device by its SNMP poll address.

    The polling pipeline records the raw address used to reach the device in
    ``host.polled_address`` (the hostname when one is configured, otherwise the
    IP).  Querying this single field is simpler and more reliable than checking
    both ``host.ip`` and ``host.hostname``.
    """
    identifier = device.hostname or device.ip_address
    if not identifier:
        return {"match_none": {}}
    return {"term": {"host.polled_address": identifier}}


def GetDevicesStatus(request):
    """
    Check online status for multiple devices in batch.
    Accepts comma-separated device IDs as query parameter.
    Returns status for all devices in a single response.

    Query params:
        device_ids: Comma-separated list of device IDs (e.g., "123,124,125")

    Returns:
        {
            "success": true,
            "statuses": {
                "123": {"is_online": true},
                "124": {"is_online": false},
                ...
            }
        }
    """
    try:
        # Get device IDs from query parameter
        device_ids_str = request.GET.get('device_ids', '')
        if not device_ids_str:
            return JsonResponse({
                'success': False,
                'error': 'device_ids parameter is required'
            }, status=400)

        # Parse device IDs
        try:
            device_ids = [int(id.strip()) for id in device_ids_str.split(',') if id.strip()]
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid device_ids format. Expected comma-separated integers.'
            }, status=400)

        if not device_ids:
            return JsonResponse({
                'success': False,
                'error': 'No valid device IDs provided'
            }, status=400)

        # Fetch devices with prefetched relationships for efficiency
        devices = Device.objects.filter(id__in=device_ids).select_related('network__connection')

        # Get batch status results
        status_results = get_devices_online_batch(list(devices))

        # Format response
        statuses = {
            str(device_id): {'is_online': is_online}
            for device_id, is_online in status_results.items()
        }

        return JsonResponse({
            'success': True,
            'statuses': statuses
        }, status=200)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def GetDeviceVisualization(request, device_id):
    """Get visualization data for a specific device"""
    try:
        device = Device.objects.get(id=device_id)

        # Prepare device data for visualization
        device_data = {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
            'port': device.port,
            'timeout': device.timeout,
            'retries': device.retries,
            'credential': {
                'id': device.credential.id,
                'name': device.credential.name,
                'version': device.credential.version,
            } if device.credential else None,
            'network': {
                'id': device.network.id,
                'name': device.network.name,
                'network_range': device.network.network_range,
            } if device.network else None,
            'profiles': [
                {
                    'name': profile.name,
                    'vendor': profile.vendor,
                    'product': profile.product,
                }
                for profile in (device.device_template.profiles.all() if device.device_template else [])
            ],
            'created_at': device.created_at.isoformat(),
            'updated_at': device.updated_at.isoformat(),
        }

        # Get visualization data from Elasticsearch
        visualization_data = get_visualizations(device)

        return JsonResponse({
            'success': True,
            'device': device_data,
            'visualizations': visualization_data
        }, status=200)

    except Device.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Device not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def GetDiscoveredDevices(request):
    """
    Query Elasticsearch for discovered devices from logs-snmp.discovery-* indices.
    Aggregates by host.ip and returns top hits from the last 15 minutes.
    """
    try:

        # Only query connections that are assigned to SNMP networks
        connection_ids = Network.objects.filter(
            connection__isnull=False
        ).values_list('connection_id', flat=True).distinct()
        connections = Connection.objects.filter(id__in=connection_ids)

        if not connections.exists():
            return JsonResponse({
                'success': False,
                'error': 'No Elasticsearch connections associated with SNMP networks'
            }, status=400)

        all_discovered_devices = []
        errors = []

        # Calculate time range (last 15 minutes — matches device online status threshold)
        now = datetime.now(timezone.utc)
        fifteen_minutes_ago = now - timedelta(minutes=15)

        # Query each connection for discovered devices
        for connection in connections:
            try:
                es = get_elastic_connection(connection.id)

                # Build Elasticsearch query
                query = {
                    "size": 0,
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "range": {
                                        "@timestamp": {
                                            "gte": fifteen_minutes_ago.isoformat(),
                                            "lte": now.isoformat()
                                        }
                                    }
                                }
                            ]
                        }
                    },
                    "aggs": {
                        "devices_by_host": {
                            "terms": {
                                "field": "host.ip",
                                "size": 1000
                            },
                            "aggs": {
                                "latest_doc": {
                                    "top_hits": {
                                        "size": 1,
                                        "sort": [
                                            {
                                                "@timestamp": {
                                                    "order": "desc"
                                                }
                                            }
                                        ],
                                        "_source": {
                                            "includes": [
                                                "host.sysname",
                                                "host.hostname",
                                                "host.ip",
                                                "network.name",
                                                "@timestamp",
                                                "observer.sys_descr"
                                            ]
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                # Execute search
                response = es.search(
                    index="logs-snmp.discovery-*",
                    body=query
                )

                # Extract devices from aggregation results
                if 'aggregations' in response and 'devices_by_host' in response['aggregations']:
                    buckets = response['aggregations']['devices_by_host']['buckets']

                    for bucket in buckets:
                        if 'latest_doc' in bucket and 'hits' in bucket['latest_doc']:
                            hits = bucket['latest_doc']['hits']['hits']
                            if hits:
                                source = hits[0]['_source']
                                network_name = source.get('network', {}).get('name', '')

                                # Query the Network model to get the discovery credential
                                network_obj = None
                                credential_id = None
                                network_id = None

                                if network_name:
                                    try:
                                        # Try exact match first
                                        network_obj = Network.objects.filter(name=network_name).first()
                                        
                                        # If no exact match, try case-insensitive match
                                        if not network_obj:
                                            network_obj = Network.objects.filter(name__iexact=network_name).first()
                                        
                                        # If still no match, try case-insensitive contains (for cases like 'Homelab' -> 'homelab-segment1')
                                        if not network_obj:
                                            network_obj = Network.objects.filter(name__icontains=network_name).first()
                                        
                                        if network_obj:
                                            network_id = network_obj.id
                                            if network_obj.discovery_credential:
                                                credential_id = network_obj.discovery_credential.id
                                    except Exception as e:
                                        logger.warning(f"Could not query network '{network_name}': {str(e)}")

                                # Get suggested device template based on observer.sys_descr (sysDescr)
                                sys_descr = source.get('observer', {}).get('sys_descr', '')
                                suggested_template_ids = []
                                suggested_template_name = None
                                
                                if sys_descr:
                                    suggested_template_ids = suggest_device_template(sys_descr)
                                    
                                    # Get the name of the first (best) suggested template
                                    if suggested_template_ids:
                                        try:
                                            best_template = DeviceTemplate.objects.get(id=suggested_template_ids[0])
                                            suggested_template_name = best_template.name.replace('_', ' ').title()
                                        except DeviceTemplate.DoesNotExist:
                                            pass
                                
                                device = {
                                    'host_name': source.get('host', {}).get('sysname', 'Unknown'),
                                    'host_hostname': source.get('host', {}).get('hostname', ''),
                                    'sys_descr': sys_descr,
                                    'host_ip': source.get('host', {}).get('ip', ''),
                                    'network_name': network_name,
                                    'network_id': network_id,
                                    'credential_id': credential_id,
                                    'timestamp': source.get('@timestamp', ''),
                                    'connection_name': connection.name,
                                    'connection_id': connection.id,
                                    'suggested_template_id': suggested_template_ids[0] if suggested_template_ids else None,
                                    'suggested_template_name': suggested_template_name
                                }
                                all_discovered_devices.append(device)

            except Exception as e:
                errors.append(f"Connection '{connection.name}': {str(e)}")
                continue

        # Filter out devices already registered in the DB.
        # A polled address lands in host.ip (when it's an IP) or host.hostname
        # (when it's a hostname) — both stored in the Device model as ip_address
        # and hostname respectively. Build one set covering all known addresses
        # then drop any ES result that matches.
        known_addresses = set(
            Device.objects.exclude(ip_address='').exclude(ip_address__isnull=True)
                          .values_list('ip_address', flat=True)
        ) | set(
            Device.objects.exclude(hostname='').exclude(hostname__isnull=True)
                          .values_list('hostname', flat=True)
        )

        all_discovered_devices = [
            d for d in all_discovered_devices
            if d['host_ip'] not in known_addresses
            and d['host_hostname'] not in known_addresses
        ]

        return JsonResponse({
            'success': True,
            'devices': all_discovered_devices,
            'total': len(all_discovered_devices),
            'errors': errors if errors else None
        })

    except Exception as e:
        logger.exception("Error in GetDiscoveredDevices")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _get_device_interfaces(device, es_connection):
    results = es_connection.search(
        size=0,
        index="metrics-snmp*",
        sort=[{"@timestamp": {"order": "desc"}}],
        query={
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    _device_host_filter(device),
                    {
                        "term": {
                            "event.category": "interface"
                        }
                    }
                ]
            }
        },
        aggregations={
            "fans": {
                "terms": {
                    "field": "interface.name",
                    "size": 1000
                },
                "aggregations": {
                    "top_if_doc": {
                        "top_hits": {
                            "size": 1
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "interfaces": []
    }

    for fan in results['aggregations']['fans']['buckets']:
        for doc in fan['top_if_doc']['hits']['hits']:
            visualization_data['interfaces'].append(doc['_source']['interface'])

    return visualization_data


def _get_device_metrics(device, es_connection):
    results = es_connection.search(
        size=1000,
        index="metrics-snmp*",
        sort=[{"@timestamp": {"order": "desc"}}],
        query={

            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    _device_host_filter(device),
                    {
                        "term": {
                            "event.category": "metrics"
                        }
                    }
                ]
            }
        }
    )

    visualization_data = {
        "Uptime": 0,
        "CPU": [],
        "Memory": [],
        "Time": []
    }

    for result in results['hits']['hits']:
        try:
            cpu = result['_source']['system']['cpu']['total']['norm']['pct']
            memory = result['_source']['system']['memory']['actual']['used']['pct']
            timestamp = result['_source']['@timestamp']

            visualization_data['CPU'].append(cpu)
            visualization_data['Memory'].append(memory)
            visualization_data['Time'].append(timestamp)
        except (KeyError, TypeError):
            # Skip documents that don't have the required CPU/Memory fields
            continue

    try:
        visualization_data['Uptime'] = results['hits']['hits'][0]['_source']['host']['uptime']
    except (KeyError, TypeError, IndexError):
        visualization_data['Uptime'] = 0

    return visualization_data


def _get_device_fans(device, es_connection):
    results = es_connection.search(
        size=0,
        index="metrics-snmp*",
        sort=[{"@timestamp": {"order": "desc"}}],
        query={
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    _device_host_filter(device),
                    {
                        "term": {
                            "event.category": "fans"
                        }
                    }
                ]
            }
        },
        aggregations={
            "fans": {
                "terms": {
                    "field": "fans.description",
                    "size": 1000
                },
                "aggregations": {
                    "top_fan_doc": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["fans.state", "fans.description"]
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "fans": []
    }

    for fan in results['aggregations']['fans']['buckets']:
        for doc in fan['top_fan_doc']['hits']['hits']:
            visualization_data['fans'].append(doc['_source']['fans'])

    return visualization_data


def _get_device_sensors(device, es_connection):
    results = es_connection.search(
        size=0,
        index="metrics-snmp*",
        sort=[{"@timestamp": {"order": "desc"}}],
        query={

            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    _device_host_filter(device),
                    {
                        "term": {
                            "event.category": "sensors"
                        }
                    }
                ]
            }
        },
        aggregations={
            "sensors": {
                "terms": {
                    "field": "sensors.description",
                    "size": 1000
                },
                "aggregations": {
                    "top_sensor_doc": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["sensors.state", "sensors.description", "sensors.temp_celsius",
                                        "sensors.temp_threshold"]
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "sensors": []
    }

    for sensor in results['aggregations']['sensors']['buckets']:
        for doc in sensor['top_sensor_doc']['hits']['hits']:
            visualization_data['sensors'].append(doc['_source']['sensors'])

    return visualization_data


def _get_device_cpu_cores(device, es_connection):
    results = es_connection.search(
        size=0,
        index="metrics-snmp*",
        query={
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    _device_host_filter(device),
                    {
                        "term": {
                            "event.category": "component.cpu"
                        }
                    }
                ]
            }
        },
        aggregations={
            "cores": {
                "terms": {
                    "field": "component.cpu.index",
                    "size": 1000
                },
                "aggregations": {
                    "latest_doc": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": ["component.cpu.index", "component.cpu.load_pct"]
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "cores": []
    }

    for bucket in results['aggregations']['cores']['buckets']:
        for doc in bucket['latest_doc']['hits']['hits']:
            cpu = doc['_source'].get('component', {}).get('cpu', {})
            visualization_data['cores'].append({
                "index": cpu.get('index', bucket['key']),
                "load_pct": cpu.get('load_pct', 0)
            })

    # Sort cores by index so they render in a consistent order
    visualization_data['cores'].sort(key=lambda c: int(c['index']) if str(c['index']).isdigit() else 0)

    return visualization_data


def _get_device_neighbors(device, es_connection):
    results = es_connection.search(
        size=0,
        index="metrics-snmp*",
        query={
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    _device_host_filter(device),
                    {
                        "term": {
                            "event.category": "network.neighbor"
                        }
                    }
                ]
            }
        },
        aggregations={
            "neighbors": {
                "terms": {
                    "field": "network.neighbor.index",
                    "size": 1000
                },
                "aggregations": {
                    "latest_doc": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": [
                                "network.neighbor.index",
                                "network.neighbor.device_id",
                                "network.neighbor.port",
                                "network.neighbor.platform",
                                "network.neighbor.version",
                                "network.neighbor.address",
                                "network.neighbor.capabilities",
                                "network.neighbor.local_interface"
                            ]
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "neighbors": []
    }

    for bucket in results['aggregations']['neighbors']['buckets']:
        for doc in bucket['latest_doc']['hits']['hits']:
            neighbor = doc['_source'].get('network', {}).get('neighbor', {})
            visualization_data['neighbors'].append({
                "index": neighbor.get('index', bucket['key']),
                "device_id": neighbor.get('device_id', ''),
                "port": neighbor.get('port', ''),
                "platform": neighbor.get('platform', ''),
                "version": neighbor.get('version', ''),
                "address": neighbor.get('address', ''),
                "capabilities": neighbor.get('capabilities', ''),
                "local_interface": neighbor.get('local_interface', {})
            })

    visualization_data['neighbors'].sort(key=lambda n: n['device_id'].lower())

    return visualization_data


def _get_device_wireless_radios(device, es_connection):
    results = es_connection.search(
        size=0,
        index="metrics-snmp*",
        query={
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    _device_host_filter(device),
                    {
                        "term": {
                            "event.category": "wireless.radio"
                        }
                    }
                ]
            }
        },
        aggregations={
            "radios": {
                "terms": {
                    "field": "wireless.radio.index",
                    "size": 100
                },
                "aggregations": {
                    "latest_doc": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": [
                                "wireless.radio.index",
                                "wireless.radio.name",
                                "wireless.radio.band",
                                "wireless.radio.channel",
                                "wireless.radio.in_bytes",
                                "wireless.radio.out_bytes",
                                "wireless.radio.out_discards",
                                "wireless.radio.out_errors"
                            ]
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "radios": []
    }

    for bucket in results['aggregations']['radios']['buckets']:
        for doc in bucket['latest_doc']['hits']['hits']:
            radio = doc['_source'].get('wireless', {}).get('radio', {})
            visualization_data['radios'].append({
                "index": radio.get('index', bucket['key']),
                "name": radio.get('name', ''),
                "band": radio.get('band', ''),
                "channel": radio.get('channel', ''),
                "in_bytes": radio.get('in_bytes', 0),
                "out_bytes": radio.get('out_bytes', 0),
                "out_discards": radio.get('out_discards', 0),
                "out_errors": radio.get('out_errors', 0)
            })

    visualization_data['radios'].sort(key=lambda r: int(r['index']) if str(r['index']).isdigit() else 0)

    return visualization_data


def _get_device_filesystems(device, es_connection):
    results = es_connection.search(
        size=0,
        index="metrics-snmp*",
        query={
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    _device_host_filter(device),
                    {
                        "term": {
                            "event.category": "system.filesystem"
                        }
                    }
                ]
            }
        },
        aggregations={
            "filesystems": {
                "terms": {
                    "field": "system.filesystem.index",
                    "size": 1000
                },
                "aggregations": {
                    "latest_doc": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": [
                                "system.filesystem.index",
                                "system.filesystem.mount_point",
                                "system.filesystem.type",
                                "system.filesystem.used.pct",
                                "system.filesystem.used.bytes",
                                "system.filesystem.total.bytes",
                                "system.filesystem.allocation_units"
                            ]
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "filesystems": []
    }

    for bucket in results['aggregations']['filesystems']['buckets']:
        for doc in bucket['latest_doc']['hits']['hits']:
            fs = doc['_source'].get('system', {}).get('filesystem', {})
            visualization_data['filesystems'].append({
                "index": fs.get('index', bucket['key']),
                "mount_point": fs.get('mount_point', ''),
                "type": fs.get('type', ''),
                "used_pct": fs.get('used', {}).get('pct', 0),
                "used_bytes": fs.get('used', {}).get('bytes', 0),
                "total_bytes": fs.get('total', {}).get('bytes', 0),
                "allocation_units": fs.get('allocation_units', 0)
            })

    visualization_data['filesystems'].sort(key=lambda f: f['mount_point'])

    return visualization_data


def _get_device_printer_supplies(device, es_connection):
    results = es_connection.search(
        size=0,
        index="metrics-snmp*",
        query={
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": "now-6h"
                            }
                        }
                    },
                    _device_host_filter(device),
                    {
                        "term": {
                            "event.category": "printer.supply"
                        }
                    }
                ]
            }
        },
        aggregations={
            "supplies": {
                "terms": {
                    "field": "printer.supply.index",
                    "size": 1000
                },
                "aggregations": {
                    "latest_doc": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": [
                                "printer.supply.index",
                                "printer.supply.description",
                                "printer.supply.level",
                                "printer.supply.capacity_max",
                                "printer.supply.unit"
                            ]
                        }
                    }
                }
            }
        }
    )

    visualization_data = {
        "supplies": []
    }

    for bucket in results['aggregations']['supplies']['buckets']:
        for doc in bucket['latest_doc']['hits']['hits']:
            supply = doc['_source'].get('printer', {}).get('supply', {})
            visualization_data['supplies'].append({
                "index": supply.get('index', bucket['key']),
                "description": supply.get('description', ''),
                "level": supply.get('level', 0),
                "capacity_max": supply.get('capacity_max', 100),
                "unit": supply.get('unit', 0)
            })

    visualization_data['supplies'].sort(key=lambda s: s['description'].lower())

    return visualization_data


def generate_visualizations(visualizations, device, es_connection):
    """
    Generate visualization data based on the decided visualizations.
    """
    visualization_data = {}
    if "metrics" in visualizations:
        visualization_data['metrics'] = _get_device_metrics(device, es_connection)
    if "sensors" in visualizations:
        visualization_data['sensors'] = _get_device_sensors(device, es_connection)
    if "fans" in visualizations:
        visualization_data['fans'] = _get_device_fans(device, es_connection)
    if "interface" in visualizations:
        visualization_data['interfaces'] = _get_device_interfaces(device, es_connection)
    if "component.cpu" in visualizations:
        visualization_data['cpu_cores'] = _get_device_cpu_cores(device, es_connection)
    if "network.neighbor" in visualizations:
        visualization_data['neighbors'] = _get_device_neighbors(device, es_connection)
    if "wireless.radio" in visualizations:
        visualization_data['wireless_radios'] = _get_device_wireless_radios(device, es_connection)
    if "system.filesystem" in visualizations:
        visualization_data['filesystems'] = _get_device_filesystems(device, es_connection)
    if "printer.supply" in visualizations:
        visualization_data['printer_supplies'] = _get_device_printer_supplies(device, es_connection)

    return visualization_data


def get_devices_online_batch(devices):
    """
    Check online status for multiple devices in batch.
    Groups devices by their Elasticsearch connection and makes one query per connection.

    Args:
        devices: List of Device objects (should have network and connection prefetched)

    Returns:
        dict: {device_id: is_online_bool, ...}
    """
    results = {}

    # Group devices by connection_id
    devices_by_connection = {}
    for device in devices:
        # Skip devices without network or connection
        if not device.network or not device.network.connection:
            results[device.id] = False
            continue

        connection_id = device.network.connection.id
        if connection_id not in devices_by_connection:
            devices_by_connection[connection_id] = []
        devices_by_connection[connection_id].append(device)

    # Query each connection once with all its devices
    for connection_id, device_list in devices_by_connection.items():
        try:
            es = get_elastic_connection(connection_id)

            # Each device is polled by hostname (if set) or IP - that value is
            # stored verbatim in host.polled_address
            poll_addresses = [d.hostname or d.ip_address for d in device_list if d.hostname or d.ip_address]
            addr_to_device = {(d.hostname or d.ip_address): d for d in device_list if d.hostname or d.ip_address}

            if not poll_addresses:
                for device in device_list:
                    results[device.id] = False
                continue

            search_results = es.search(
                size=0,
                query={
                    "bool": {
                        "filter": [
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": "now-15m"
                                    }
                                }
                            },
                            {
                                "terms": {
                                    "host.polled_address": poll_addresses
                                }
                            }
                        ]
                    }
                },
                aggregations={
                    "online_devices": {
                        "terms": {
                            "field": "host.polled_address.keyword",
                            "size": len(poll_addresses)
                        }
                    }
                }
            )

            online_addresses = set()
            if 'aggregations' in search_results and 'online_devices' in search_results['aggregations']:
                for bucket in search_results['aggregations']['online_devices']['buckets']:
                    online_addresses.add(bucket['key'])

            for device in device_list:
                addr = device.hostname or device.ip_address
                results[device.id] = addr in online_addresses if addr else False

        except Exception as e:
            # If query fails, mark all devices on this connection as offline
            for device in device_list:
                results[device.id] = False

    return results


def get_visualizations(device):
    """
    Main entry point to get visualizations for a device.
    Gets the Elasticsearch connection from the device's network and fetches visualization data.
    """
    # Get the connection from the device's network
    if not device.network or not device.network.connection:
        return {
            'success': False,
            'error': 'Device has no network or network has no connection configured'
        }

    connection_id = device.network.connection.id
    es = get_elastic_connection(connection_id)

    # Decide what visualizations to show and fetch the data
    visualizations = decide_visualizations(device, es)
    return generate_visualizations(visualizations['results'], device, es)


def decide_visualizations(device, es):
    """
    Determine which visualizations to show for SNMP devices based on available data.
    Queries Elasticsearch to see what data is available for this device.
    Returns a dict with visualization configuration and query results.
    """
    try:
        results = es.search(
            index="metrics-snmp*",
            size=0,
            query={
                "bool": {
                    "filter": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": "now-6h"
                                }
                            }
                        },
                        _device_host_filter(device)
                    ]
                }
            },
            aggregations={
                "data_kinds": {
                    "terms": {
                        "field": "event.category",
                        "size": 20
                    }
                }
            }
        )

        data_types = [result['key'] for result in results['aggregations']['data_kinds']['buckets']]

        return {
            'success': True,
            'results': data_types
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'has_data': False
        }


# Device Template CRUD Operations

def GetOfficialDeviceTemplate(request, template_name):
    """Get an official device template from JSON file"""
    try:
        official_templates_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_device_templates')
        template_path = os.path.join(official_templates_dir, f"{template_name}.json")

        if not os.path.exists(template_path):
            return JsonResponse({'error': 'Device template not found'}, status=404)

        with open(template_path, 'r') as f:
            template_data = json.load(f)

        # Get profile names and convert to IDs if they exist in the database
        profile_names = template_data.get('profiles', [])
        profile_ids = []
        for profile_name in profile_names:
            try:
                # Try to find the profile by name (could be official or user profile)
                profile = Profile.objects.get(name=profile_name)
                profile_ids.append(profile.id)
            except Profile.DoesNotExist:
                # If profile doesn't exist in DB, it's likely an official profile
                # We'll just use the name as-is
                profile_ids.append(profile_name)

        resolved_name = template_data.get('name', template_name)
        return JsonResponse({
            'name': resolved_name,
            'display_name': format_display_name(resolved_name),
            'description': template_data.get('description', ''),
            'vendor': template_data.get('vendor', ''),
            'model': template_data.get('model', ''),
            'product': template_data.get('product', ''),
            'matching_rules': template_data.get('matching_rules', []),
            'official': True,
            'profiles': profile_ids
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def GetDeviceTemplates(request):
    """Get all device templates for dropdown selection (official templates are synced to database)"""
    try:
        templates_list = []
        
        # Load all templates from database (including synced official templates)
        for template in DeviceTemplate.objects.all().order_by('name'):
            templates_list.append({
                'id': template.id,
                'name': template.name,
                'display_name': format_display_name(template.name),
                'vendor': template.vendor,
                'model': template.model,
                'product': template.product,
                'type': template.type,
                'official': template.official
            })
        
        return JsonResponse({'templates': templates_list})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def GetDeviceTemplate(request, template_id):
    """Get a specific device template by ID (or name for official templates)"""
    try:
        # First, try to get from database by ID
        try:
            template = DeviceTemplate.objects.get(id=int(template_id))
            
            # Get profile data with names for display
            profiles_data = [
                {
                    'id': profile.id,
                    'name': profile.name,
                    'display_name': format_display_name(profile.name)
                }
                for profile in template.profiles.all()
            ]
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"GetDeviceTemplate {template_id}: Returning {len(profiles_data)} profiles: {profiles_data}")
            
            return JsonResponse({
                'id': template.id,
                'name': template.name,
                'display_name': format_display_name(template.name),
                'description': template.description,
                'vendor': template.vendor,
                'model': template.model,
                'product': template.product,
                'type': template.type,
                'matching_rules': template.matching_rules,
                'official': template.official,
                'profiles': profiles_data
            })
        except (ValueError, DeviceTemplate.DoesNotExist):
            # If not found by ID, try to load as official template by name
            return GetOfficialDeviceTemplate(request, template_id)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_admin_role
def AddDeviceTemplate(request):
    """Add a new device template"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        vendor = request.POST.get('vendor')
        model = request.POST.get('model', '')
        product = request.POST.get('product', '')
        type_value = request.POST.get('type', '')
        matching_rules_json = request.POST.get('matching_rules', '[]')
        profiles_json = request.POST.get('profiles', '[]')
        
        # Validate required fields
        if not name:
            return JsonResponse({'error': 'Template name is required'}, status=400)
        if not vendor:
            return JsonResponse({'error': 'Vendor is required'}, status=400)
        
        # Parse JSON fields
        matching_rules = json.loads(matching_rules_json)
        profile_ids = json.loads(profiles_json)
        
        # Create the template
        template = DeviceTemplate.objects.create(
            name=name,
            description=description,
            vendor=vendor,
            model=model,
            product=product,
            type=type_value,
            matching_rules=matching_rules,
            official=False
        )
        
        # Add profiles (handle both ID and name formats)
        if profile_ids:
            for profile_id in profile_ids:
                try:
                    # Convert to string for consistent handling
                    profile_id_str = str(profile_id)
                    
                    # Try to get by ID first (for database profiles)
                    if profile_id_str.isdigit():
                        profile = Profile.objects.get(id=int(profile_id_str))
                        template.profiles.add(profile)
                    else:
                        # Try to get by name (for official profiles that might be referenced by name)
                        profile = Profile.objects.get(name=profile_id_str)
                        template.profiles.add(profile)
                except Profile.DoesNotExist:
                    # Log which profile failed to add
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Profile with ID/name '{profile_id}' not found, skipping")
                    pass  # Skip profiles that don't exist
        
        # Mark config as changed to show deployment indicator
        SNMPDeploymentState.mark_config_changed()
        
        return JsonResponse({
            'success': True,
            'message': 'Device template created successfully',
            'template_id': template.id
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_admin_role
def UpdateDeviceTemplate(request, template_id):
    """Update an existing device template"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        
        template = DeviceTemplate.objects.get(id=template_id)
        
        # Don't allow editing official templates
        if template.official:
            return JsonResponse({'error': 'Cannot edit official templates'}, status=403)
        
        # Update fields
        template.name = request.POST.get('name', template.name)
        template.description = request.POST.get('description', template.description)
        template.vendor = request.POST.get('vendor', template.vendor)
        template.model = request.POST.get('model', template.model)
        template.product = request.POST.get('product', template.product)
        template.type = request.POST.get('type', template.type)
        
        # Update matching rules
        matching_rules_json = request.POST.get('matching_rules')
        if matching_rules_json:
            template.matching_rules = json.loads(matching_rules_json)
        
        template.save()
        
        # Update profiles
        profiles_json = request.POST.get('profiles')
        if profiles_json:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Received profiles JSON: {profiles_json}")
            
            profile_ids = json.loads(profiles_json)
            logger.info(f"Parsed profile IDs: {profile_ids} (types: {[type(p).__name__ for p in profile_ids]})")
            
            template.profiles.clear()
            
            for profile_id in profile_ids:
                try:
                    # Convert to string for consistent handling
                    profile_id_str = str(profile_id)
                    
                    # Try to get by ID first (for database profiles)
                    if profile_id_str.isdigit():
                        profile = Profile.objects.get(id=int(profile_id_str))
                        template.profiles.add(profile)
                    else:
                        # Try to get by name (for official profiles)
                        profile = Profile.objects.get(name=profile_id_str)
                        template.profiles.add(profile)
                except Profile.DoesNotExist:
                    # Log which profile failed to add
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Profile with ID/name '{profile_id}' not found, skipping")
                    pass  # Skip profiles that don't exist
        
        # Mark config as changed to show deployment indicator
        SNMPDeploymentState.mark_config_changed()
        
        return JsonResponse({
            'success': True,
            'message': 'Device template updated successfully'
        })
    except DeviceTemplate.DoesNotExist:
        return JsonResponse({'error': 'Device template not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_admin_role
def DeleteDeviceTemplate(request, template_id):
    """Delete a device template"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        template = DeviceTemplate.objects.get(id=template_id)
        
        # Don't allow deleting official templates
        if template.official:
            return JsonResponse({'error': 'Cannot delete official templates'}, status=403)
        
        template_name = template.name
        template.delete()
        
        # Mark config as changed to show deployment indicator
        SNMPDeploymentState.mark_config_changed()
        
        return JsonResponse({
            'success': True,
            'message': f'Device template "{template_name}" deleted successfully'
        })
    except DeviceTemplate.DoesNotExist:
        return JsonResponse({'error': 'Device template not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ---------------------------------------------------------------------------
# Official data sync helpers
# ---------------------------------------------------------------------------

def sync_official_profiles():
    """Sync official profiles from JSON files to database as placeholders"""
    official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')

    if not os.path.exists(official_profiles_dir):
        return

    for filename in os.listdir(official_profiles_dir):
        if filename.endswith('.json'):
            profile_name = filename  # Keep .json extension for database storage

            try:
                profile_path = os.path.join(official_profiles_dir, filename)
                with open(profile_path, 'r') as f:
                    profile_data = json.load(f)

                official_key = profile_data.get('official_key')
                if not official_key:
                    logger.warning(f"Official profile {filename} has no official_key — skipping")
                    continue

                # 1. Already migrated — find by official_key (fast path, rename-safe)
                try:
                    profile = Profile.objects.get(official_key=official_key)
                except Profile.DoesNotExist:
                    # 2. Upgrade path — old record exists by name but has no official_key yet
                    try:
                        profile = Profile.objects.get(name=profile_name, official_key__isnull=True)
                        profile.official_key = official_key
                        logger.debug(f"Backfilled official_key for existing profile '{profile_name}'")
                    except Profile.DoesNotExist:
                        # 3. Genuinely new record
                        profile = Profile(official_key=official_key, name=profile_name)

                # Update all mutable fields and save
                profile.name = profile_name
                profile.description = profile_data.get('description', '')
                profile.vendor = profile_data.get('vendor', 'Any')
                profile.product = profile_data.get('product', '')
                # Always reset to a clean placeholder — clears any stale flags such as
                # 'is_orphaned' that may have been set during a previous cleanup run.
                profile.profile_data = {'is_official_placeholder': True}
                profile.save()

            except Exception as e:
                logger.error(f"Error syncing official profile {filename}: {e}")
                continue


def sync_official_device_templates():
    """Sync official device templates from JSON files to database"""
    official_templates_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_device_templates')

    if not os.path.exists(official_templates_dir):
        return

    for filename in os.listdir(official_templates_dir):
        if filename.endswith('.json'):
            template_name = filename[:-5]  # Remove .json extension

            try:
                template_path = os.path.join(official_templates_dir, filename)
                with open(template_path, 'r') as f:
                    template_data = json.load(f)

                official_key = template_data.get('official_key')
                if not official_key:
                    logger.warning(f"Official template {filename} has no official_key — skipping")
                    continue

                display_name = template_data.get('name', template_name)

                # 1. Already migrated — find by official_key (fast path, rename-safe)
                try:
                    template = DeviceTemplate.objects.get(official_key=official_key)
                except DeviceTemplate.DoesNotExist:
                    # 2. Upgrade path — old record exists by name but has no official_key yet
                    try:
                        template = DeviceTemplate.objects.get(name=display_name, official_key__isnull=True)
                        template.official_key = official_key
                        logger.debug(f"Backfilled official_key for existing template '{display_name}'")
                    except DeviceTemplate.DoesNotExist:
                        # 3. Genuinely new record
                        template = DeviceTemplate(official_key=official_key, name=display_name)

                # Update all mutable fields and save
                template.name = display_name
                template.description = template_data.get('description', '')
                template.vendor = template_data.get('vendor', 'Any')
                template.model = template_data.get('model', '')
                template.product = template_data.get('product', '')
                template.type = template_data.get('type', '')
                template.matching_rules = template_data.get('matching_rules', [])
                template.official = True
                template.save()

                # Sync profiles — look up by official_key first (rename-proof),
                # with fallbacks for profiles that haven't been migrated yet or are user-created
                profile_names = template_data.get('profiles', [])
                if profile_names:
                    template.profiles.clear()
                    profiles_added = 0
                    for profile_name in profile_names:
                        profile = None
                        # Try official_key (already migrated official profile)
                        try:
                            profile = Profile.objects.get(official_key=profile_name)
                        except Profile.DoesNotExist:
                            pass
                        # Try name with .json extension (un-migrated official profile)
                        if profile is None:
                            try:
                                profile = Profile.objects.get(name=f"{profile_name}.json")
                            except Profile.DoesNotExist:
                                pass
                        # Try bare name (user-created custom profile)
                        if profile is None:
                            try:
                                profile = Profile.objects.get(name=profile_name)
                            except Profile.DoesNotExist:
                                pass

                        if profile is not None:
                            template.profiles.add(profile)
                            profiles_added += 1
                        else:
                            logger.warning(f"Profile '{profile_name}' not found for template '{template.name}'")
                    logger.debug(f"Synced template '{template.name}': {profiles_added}/{len(profile_names)} profiles linked")

            except Exception as e:
                logger.error(f"Error syncing official template {filename}: {e}")
                continue


def suggest_device_template(device_info):
    """
    Suggest device templates based on matching rules against device information.

    Args:
        device_info (str): Device identification string (e.g., sysDescr or sysObject)

    Returns:
        list: List of DeviceTemplate IDs ranked by match quality:
              - First: Templates where ALL matching rules match
              - Second: Templates where SOME matching rules match
              - Templates with null/empty matching_rules are excluded
    """
    if not device_info:
        return []

    device_info_lower = device_info.lower()

    # Get all device templates with matching rules
    templates = DeviceTemplate.objects.exclude(matching_rules__isnull=True).exclude(matching_rules=[])

    all_matches = []     # Templates where ALL rules match
    partial_matches = [] # Templates where SOME rules match

    for template in templates:
        if not template.matching_rules:
            continue

        matching_count = 0
        total_rules = len(template.matching_rules)

        for rule in template.matching_rules:
            if rule.lower() in device_info_lower:
                matching_count += 1

        if matching_count == total_rules and total_rules > 0:
            all_matches.append(template.id)
        elif matching_count > 0:
            partial_matches.append((template.id, matching_count / total_rules))

    # Sort partial matches by match percentage (descending)
    partial_matches.sort(key=lambda x: x[1], reverse=True)
    partial_match_ids = [template_id for template_id, _ in partial_matches]

    return all_matches + partial_match_ids
