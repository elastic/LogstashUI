"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

from django.http import JsonResponse, HttpResponse
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models import Q, Prefetch

from Common.encryption import decrypt_credential
from Common.elastic_utils import get_elastic_connection
from Common.logstash_config_parse import ComponentToPipeline
from Common.decorators import require_admin_role
from Common.formatters import _sanitize_pipeline_name_component

from PipelineManager.models import Connection

from .models import Credential, Network, Profile, Device

from datetime import datetime, timedelta, timezone

import json
import os
import re
import ipaddress

import traceback
import logging

logger = logging.getLogger(__name__)


def GetCredentials(request):
    """Get all SNMP credentials"""
    try:
        credentials = Credential.objects.all().values('id', 'name', 'version', 'description')
        return JsonResponse(list(credentials), safe=False, status=200)
    except Exception as e:
        return HttpResponse(f"Error fetching credentials: {str(e)}", status=500)


def GetNetworks(request):
    """Get all SNMP networks"""
    try:
        networks = Network.objects.select_related('connection').all()
        networks_data = []
        for network in networks:
            networks_data.append({
                'id': network.id,
                'name': network.name,
                'network_range': network.network_range,
                'logstash_name': network.logstash_name,
                'discovery_enabled': network.discovery_enabled,
                'traps_enabled': network.traps_enabled,
                'discovery_credential': network.discovery_credential_id,
                'connection': network.connection_id,
                'connection_name': network.connection.name if network.connection else None
            })
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

        # Save (this will trigger validation and encryption)
        credential.save()

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

        # Save (this will trigger validation and encryption)
        credential.save()

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

        return HttpResponse("""
            <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg">
                Credential deleted successfully!
                <script>
                    setTimeout(() => {
                        window.location.reload();
                    }, 500);
                </script>
            </div>
        """)

    except Credential.DoesNotExist:
        return HttpResponse("Credential not found", status=404)
    except Exception as e:
        return HttpResponse(f"Error deleting credential: {str(e)}", status=500)


def _get_pipeline_name(network):
    """
    Generate a sanitized pipeline name for a network.
    Format: snmp-{logstash_name}-{network_name}
    """
    sanitized_logstash_name = _sanitize_pipeline_name_component(network.logstash_name)
    sanitized_network_name = _sanitize_pipeline_name_component(network.name)
    return f"snmp-{sanitized_logstash_name}-{sanitized_network_name}"


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
            logger.info(
                f"Pipeline {pipeline_name} comparison: existing_len={len(existing_pipeline_content)}, new_len={len(pipeline_content)}, match={content_match}")

            if content_match:
                # No changes needed - return success=True, is_new=False, error=None, was_updated=False
                logger.info(f"Pipeline {pipeline_name} unchanged - skipping update")
                return (True, False, None, False)
            else:
                logger.info(f"Pipeline {pipeline_name} has changes - updating")
                # Log first 500 chars of each to see the difference
                logger.info(f"Existing (first 500): {existing_pipeline_content[:500]}")
                logger.info(f"New (first 500): {pipeline_content[:500]}")

        # Prepare pipeline body
        pipeline_body = {
            "pipeline": pipeline_content,
            "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "username": "LogstashUI",
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
# Network CRUD Operations
# ============================================================================

@require_admin_role
def AddNetwork(request):
    """Add a new SNMP network"""
    try:
        # Extract form data
        name = request.POST.get('name')
        network_range = request.POST.get('network_range')
        logstash_name = request.POST.get('logstash_name')
        connection_id = request.POST.get('connection')
        credential_id = request.POST.get('credential')
        discovery_credential_id = request.POST.get('discovery_credential')
        discovery_enabled = request.POST.get('discovery_enabled', 'true') == 'true'
        traps_enabled = request.POST.get('traps_enabled', 'false') == 'true'
        interval = int(request.POST.get('interval', 30))

        # Create network object
        network = Network(
            name=name,
            network_range=network_range,
            logstash_name=logstash_name,
            discovery_enabled=discovery_enabled,
            traps_enabled=traps_enabled,
            interval=interval
        )

        # Set connection if provided
        if connection_id:
            network.connection_id = connection_id

        # Set discovery credential if provided
        if discovery_credential_id:
            network.discovery_credential_id = discovery_credential_id

        # Set trap credential if provided
        if credential_id:
            network.credential_id = credential_id

        # Save (this will trigger validation)
        network.save()

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
        network.logstash_name = request.POST.get('logstash_name', network.logstash_name)
        network.discovery_enabled = request.POST.get('discovery_enabled', 'true') == 'true'
        network.traps_enabled = request.POST.get('traps_enabled', 'false') == 'true'

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
            'logstash_name': network.logstash_name,
            'connection': network.connection_id if network.connection else None,
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
        trap_pipeline_name = f"snmp-{network.logstash_name}-traps"
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
    """Get the pipeline name for a network based on its logstash_name and network name"""
    try:
        network = Network.objects.get(pk=network_id)

        # Generate sanitized pipeline name pattern: snmp-{logstash_name}-*
        sanitized_logstash_name = _sanitize_pipeline_name_component(network.logstash_name)
        pipeline_name = f"snmp-{sanitized_logstash_name}-*"

        return JsonResponse({
            'success': True,
            'pipeline_name': pipeline_name,
            'network_name': network.name,
            'logstash_name': network.logstash_name
        })

    except Network.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Network not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# Cache for official profile data to avoid repeated file I/O
_OFFICIAL_PROFILE_CACHE = {}


def _get_device_profiles(device, profile_cache=None):
    """
    Get all profiles for a device and return merged OID data.
    Returns a tuple: (profile_ids_tuple, merged_oids_dict)

    Args:
        device: Device object with prefetched profiles
        profile_cache: Optional dict to cache loaded profile data
    """

    if profile_cache is None:
        profile_cache = _OFFICIAL_PROFILE_CACHE

    # Get all profiles for this device (should already be prefetched)
    profiles = list(device.profiles.all())

    if not profiles:
        return (tuple(), {'get': {}, 'walk': {}, 'table': {}})

    # Create a tuple of profile IDs for grouping (sorted for consistency)
    profile_ids = tuple(sorted([p.id for p in profiles]))

    # Merge OIDs from all profiles
    merged_oids = {
        'get': {},
        'walk': {},
        'table': {}
    }

    for profile in profiles:
        profile_data = profile.profile_data or {}

        # Check if this is an official profile placeholder
        if profile_data.get('is_official_placeholder'):
            profile_name = profile.name.replace('.json', '')

            # Check cache first
            if profile_name in profile_cache:
                profile_data = profile_cache[profile_name]
            else:
                # Load the actual profile data from JSON file
                official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
                profile_path = os.path.join(official_profiles_dir, f"{profile_name}.json")

                if os.path.exists(profile_path):
                    try:
                        with open(profile_path, 'r') as f:
                            profile_data = json.load(f)
                            # Cache it for future use
                            profile_cache[profile_name] = profile_data
                    except Exception as e:
                        # If we can't load the file, skip this profile
                        continue
                else:
                    # Profile file doesn't exist, skip
                    continue

        # Merge get OIDs (handle conflicts by appending profile name)
        if 'get' in profile_data and isinstance(profile_data['get'], dict):
            for key, value in profile_data['get'].items():
                if key in merged_oids['get'] and merged_oids['get'][key] != value:
                    # Key exists with different value - append profile name to make it unique
                    profile_suffix = profile.name.replace('.json', '').replace('_', '-')
                    unique_key = f"{key}.{profile_suffix}"
                    merged_oids['get'][unique_key] = value
                else:
                    merged_oids['get'][key] = value

        # Merge walk OIDs (handle conflicts by appending profile name)
        if 'walk' in profile_data and isinstance(profile_data['walk'], dict):
            for key, value in profile_data['walk'].items():
                if key in merged_oids['walk'] and merged_oids['walk'][key] != value:
                    # Key exists with different value - append profile name to make it unique
                    profile_suffix = profile.name.replace('.json', '').replace('_', '-')
                    unique_key = f"{key}.{profile_suffix}"
                    merged_oids['walk'][unique_key] = value
                else:
                    merged_oids['walk'][key] = value

        # Merge table OIDs
        if 'table' in profile_data and isinstance(profile_data['table'], dict):
            merged_oids['table'].update(profile_data['table'])

    return (profile_ids, merged_oids)


def _generate_input(input_data, profile_cache=None):
    """
    Generate SNMP input components grouped by:
    1. Credential version (v1/v2c vs v3)
    2. Profile combination (devices with same set of profiles)

    Args:
        input_data: Dict containing network and device information
        profile_cache: Optional dict to cache loaded profile data

    Returns: (input_components, oid_mappings)
    """
    input_components = []
    network_id = input_data['network'].id

    # Collect all OID mappings (key-value pairs) for filter generation
    oid_mappings = {
        'get': {},
        'walk': {},
        'table': {}
    }

    global_input_config = {
        "ecs_compatibility": "disabled",
        "oid_mapping_format": "dotted_string"
    }

    # Process v1/v2c devices
    if input_data['devices']['v1_v2c']:
        # Group v1/v2c devices by their profile combinations
        v1_v2c_groups = {}

        for device_name, device in input_data['devices']['v1_v2c'].items():
            profile_ids, merged_oids = _get_device_profiles(device, profile_cache)

            # Use profile_ids tuple as grouping key
            if profile_ids not in v1_v2c_groups:
                v1_v2c_groups[profile_ids] = {
                    'devices': [],
                    'oids': merged_oids
                }

            v1_v2c_groups[profile_ids]['devices'].append(device)

        # Create an input for each profile group
        for group_idx, (profile_ids, group_data) in enumerate(v1_v2c_groups.items()):
            hosts = []

            for device in group_data['devices']:
                credential = device.credential
                hosts.append({
                    "host": f"udp:{device.ip_address}/{device.port}",
                    "community": credential.get_community(),
                    "version": credential.version,
                    "timeout": device.timeout,
                    "retries": device.retries
                })

            if hosts:
                interval_value = getattr(input_data['network'], 'interval', 30) or 30
                logger.info(
                    f"Network {input_data['network'].name} interval: {interval_value} (type: {type(interval_value)})")
                config = {
                             "hosts": hosts,
                             "interval": interval_value
                         } | global_input_config

                # Add OIDs from merged profiles
                oids = group_data['oids']
                if oids['get']:
                    config['get'] = list(oids['get'].values())
                    # Collect OID mappings for filter generation
                    oid_mappings['get'].update(oids['get'])
                if oids['walk']:
                    config['walk'] = list(oids['walk'].values())
                    # Collect OID mappings for filter generation
                    oid_mappings['walk'].update(oids['walk'])
                if oids['table']:
                    # Tables have structure: {"ifTable": {"columns": {"ifIndex": "oid", "ifDescr": "oid", ...}}}
                    config['tables'] = [
                        {
                            'name': table_name,
                            'columns': list(table_data.get('columns', {}).values()) if isinstance(table_data,
                                                                                                  dict) and isinstance(
                                table_data.get('columns'), dict) else []
                        }
                        for table_name, table_data in oids['table'].items()
                    ]
                    # Collect OID mappings for filter generation
                    oid_mappings['table'].update(oids['table'])

                input_components.append({
                    "id": f"input_snmp_v1_v2c_{network_id}_group_{group_idx}",
                    "type": "input",
                    "plugin": "snmp",
                    "config": config
                })

    # Process v3 devices
    if input_data['devices']['v3']:
        # Group v3 devices by their profile combinations AND credential
        # (v3 devices with different credentials need separate inputs even with same profiles)
        v3_groups = {}

        for device_name, device in input_data['devices']['v3'].items():
            profile_ids, merged_oids = _get_device_profiles(device, profile_cache)
            credential = device.credential

            # Use both profile_ids and credential_id as grouping key
            group_key = (profile_ids, credential.id)

            if group_key not in v3_groups:
                v3_groups[group_key] = {
                    'devices': [],
                    'oids': merged_oids,
                    'credential': credential
                }

            v3_groups[group_key]['devices'].append(device)

        # Create an input for each profile+credential group
        for group_idx, (group_key, group_data) in enumerate(v3_groups.items()):
            hosts = []

            for device in group_data['devices']:
                hosts.append({
                    "host": f"udp:{device.ip_address}/{device.port}",
                    "version": device.credential.version,
                    "timeout": device.timeout,
                    "retries": device.retries
                })

            if hosts:
                credential = group_data['credential']
                interval_value = getattr(input_data['network'], 'interval', 30) or 30
                logger.info(
                    f"Network {input_data['network'].name} (v3) interval: {interval_value} (type: {type(interval_value)})")

                config = {
                             "hosts": hosts,
                             "interval": interval_value,
                             "security_name": credential.security_name,
                             "security_level": credential.security_level
                         } | global_input_config

                # Add auth settings based on security level
                if credential.security_level in ['authNoPriv', 'authPriv']:
                    config["auth_protocol"] = credential.auth_protocol
                    config["auth_pass"] = credential.get_auth_pass()

                if credential.security_level == 'authPriv':
                    config["priv_protocol"] = credential.priv_protocol
                    config["priv_pass"] = credential.get_priv_pass()

                # Add OIDs from merged profiles
                oids = group_data['oids']
                if oids['get']:
                    config['get'] = list(oids['get'].values())
                    # Collect OID mappings for filter generation
                    oid_mappings['get'].update(oids['get'])
                if oids['walk']:
                    config['walk'] = list(oids['walk'].values())
                    # Collect OID mappings for filter generation
                    oid_mappings['walk'].update(oids['walk'])
                if oids['table']:
                    # Tables have structure: {"ifTable": {"columns": {"ifIndex": "oid", "ifDescr": "oid", ...}}}
                    config['tables'] = [
                        {
                            'name': table_name,
                            'columns': list(table_data.get('columns', {}).values()) if isinstance(table_data,
                                                                                                  dict) and isinstance(
                                table_data.get('columns'), dict) else []
                        }
                        for table_name, table_data in oids['table'].items()
                    ]
                    # Collect OID mappings for filter generation
                    oid_mappings['table'].update(oids['table'])

                input_components.append({
                    "id": f"input_snmp_v3_{network_id}_group_{group_idx}",
                    "type": "input",
                    "plugin": "snmp",
                    "config": config
                })

    return input_components, oid_mappings


def _load_system_profile_oids():
    """
    Load the System profile OIDs for discovery.
    Returns a dictionary with 'get', 'walk', 'table' keys.
    """
    system_profile_path = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles', 'system.json')

    try:
        with open(system_profile_path, 'r') as f:
            profile_data = json.load(f)
            return {
                'get': profile_data.get('get', {}),
                'walk': profile_data.get('walk', {}),
                'table': profile_data.get('table', {})
            }
    except Exception as e:
        # If we can't load the system profile, return empty OIDs
        return {'get': {}, 'walk': {}, 'table': {}}


def _get_discovery_ip_addresses(network):
    """
    Get all IP addresses in the network range, excluding existing devices.

    Args:
        network: Network object with network_range field

    Returns:
        List of IP addresses (as strings) to scan for discovery
    """
    try:
        # Parse the network range
        network_obj = ipaddress.ip_network(network.network_range, strict=False)

        # Get all IP addresses in the range (excluding network and broadcast)
        all_ips = set(str(ip) for ip in network_obj.hosts())

        # Get existing devices in this network
        existing_devices = Device.objects.filter(network=network).values_list('ip_address', flat=True)

        # Filter out IPs that are already devices (only if they're valid IP addresses)
        for device_ip in existing_devices:
            try:
                # Check if device IP is a valid IP address (not a hostname)
                ipaddress.ip_address(device_ip)
                # If it's a valid IP and in our network range, remove it
                if device_ip in all_ips:
                    all_ips.discard(device_ip)
            except ValueError:
                # Not a valid IP address (probably a hostname), skip it
                continue

        result = sorted(list(all_ips))
        logger.debug(f"Network {network.name}: Generated {len(result)} discovery IPs")
        return result
    except Exception as e:
        logger.error(f"Error generating discovery IPs for network {network.name}: {str(e)}", exc_info=True)
        return []


def _generate_discovery_input(network):
    """
    Generate SNMP input components for network discovery.
    Uses the System profile OIDs and scans all IPs in the network range
    (excluding existing devices).

    Args:
        network: Network object

    Returns:
        Tuple of (input_components, oid_mappings)
    """
    input_components = []

    # Check if discovery is enabled and has a credential
    if not network.discovery_enabled or not network.discovery_credential:
        return input_components, {'get': {}, 'walk': {}, 'table': {}}

    # Load System profile OIDs
    oid_mappings = _load_system_profile_oids()

    # Get IP addresses to scan
    ip_addresses = _get_discovery_ip_addresses(network)

    # If no IPs to scan, still create a minimal pipeline with a dummy host
    # This ensures the pipeline exists and can be updated when devices are removed
    if not ip_addresses:
        # Use a non-routable IP as placeholder - pipeline will exist but won't actually scan anything
        ip_addresses = ['192.0.2.1']  # RFC 5737 TEST-NET-1 address

    # Get the discovery credential
    credential = network.discovery_credential

    # Global input configuration
    global_input_config = {
        "ecs_compatibility": "disabled",
        "oid_mapping_format": "dotted_string"
    }

    # Build hosts list with credential info
    hosts = []
    for ip in ip_addresses:
        host_config = {
            "host": f"udp:{ip}/161"
        }

        # Add version-specific configuration
        if credential.version in ['1', '2c']:
            host_config["community"] = credential.get_community()
            host_config["version"] = credential.version

        hosts.append(host_config)

    # Create input configuration with 5-minute interval for discovery
    config = {
                 "hosts": hosts,
                 "interval": 300  # 5 minutes in seconds
             } | global_input_config

    # Add SNMPv3 configuration if needed
    if credential.version == '3':
        config["security_name"] = credential.security_name
        config["security_level"] = credential.security_level

        if credential.security_level in ['authNoPriv', 'authPriv']:
            config["auth_protocol"] = credential.auth_protocol
            config["auth_pass"] = credential.get_auth_pass()

        if credential.security_level == 'authPriv':
            config["priv_protocol"] = credential.priv_protocol
            config["priv_pass"] = credential.get_priv_pass()

    # Add OIDs from System profile
    if oid_mappings['get']:
        config['get'] = list(oid_mappings['get'].values())

    input_components.append({
        "id": f"input_snmp_discovery_{network.id}",
        "type": "input",
        "plugin": "snmp",
        "config": config
    })

    return input_components, oid_mappings


def _generate_discovery_filters(oid_mappings, network):
    """
    Generate filter components for discovery pipeline.
    Adds event.kind: discovery field to distinguish from regular metrics.

    Args:
        oid_mappings: Dictionary with 'get', 'walk', 'table' keys containing OID key-value pairs
        network: Network object for accessing network name

    Returns:
        List of filter components
    """
    # Build rename mappings for get OIDs
    get_renames = {value: _format_field_name(key) for key, value in oid_mappings['get'].items()}

    filter_components = [
        {
            "id": "filter_mutate_discovery_1",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "rename": {
                              "host": "[host][hostname]"
                          } | get_renames
            }
        },
        {
            "id": "filter_mutate_discovery_2",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "add_field": {
                    "[network][name]": f"{network.name}",
                    "[metricset][module]": "snmp",
                    "[event][kind]": "discovery"
                }
            }
        }
    ]

    return filter_components


def _format_field_name(field_name):
    """
    Format field name for Logstash filter usage.

    Rules:
    - If starts with [ and ends with ], leave it alone
    - If doesn't start with [ and has a dot, convert to bracket notation: system.cpu -> [system][cpu]
    - Otherwise, leave it alone

    Args:
        field_name: The field name to format

    Returns:
        Formatted field name
    """
    # Already in bracket notation
    if field_name.startswith('[') and field_name.endswith(']'):
        return field_name

    # Has dots, convert to bracket notation
    if '.' in field_name:
        parts = field_name.split('.')
        return ''.join(f'[{part}]' for part in parts)

    # No dots and not in bracket notation, leave alone
    return field_name


def _get_special_case_filters(oid_mappings):
    special_case_filters = {
        'get': {
            "system.cpu.total.norm.pct": [
                {
                    "id": "comp_1770526174120",
                    "type": "filter",
                    "plugin": "ruby",
                    "config": {
                        "code": "    v = event.get(\"[system][cpu][total][norm][pct]\")\n    if v\n      event.set(\"[system][cpu][total][norm][pct]\", v.to_f / 100.0)\n    end"
                    }
                }
            ],
            "system.memory.actual.used.bytes": [
                {
                    "id": "comp_1770526174120",
                    "type": "filter",
                    "plugin": "ruby",
                    "config": {
                        "code": '''
      used = event.get("[system][memory][actual][used][bytes]")
      free = event.get("[system][memory][actual][free][bytes]")

      if used && free
        used_f  = used.to_f
        free_f  = free.to_f
        total_f = used_f + free_f

        if total_f > 0
          event.set("[system][memory][total]", total_f)
          event.set("[system][memory][actual][used][pct]", (used_f / total_f))
          event.set("[system][memory][actual][free][pct]", (free_f / total_f))
        end
      end
    '''
                    }
                }
            ]
        },
        'walk': {}
    }

    special_filters = []

    # Add special case filters for get and walk
    types = ['get', 'walk']
    for snmp_type in types:
        for name_of_oid in oid_mappings[snmp_type]:
            if name_of_oid in special_case_filters[snmp_type]:
                for entry in special_case_filters[snmp_type][name_of_oid]:
                    special_filters.append(entry)

    # Generate dynamic table splitters for all tables in oid_mappings
    for table_name, table_data in oid_mappings.get('table', {}).items():
        if isinstance(table_data, dict) and 'columns' in table_data:
            columns = table_data.get('columns', {})
            if isinstance(columns, dict) and columns:
                # Generate the row rename statements using list comprehension
                rename_statements = '\n'.join([
                    f"    row[\"{field_name}\"] = row.delete(\"{oid}\")"
                    for field_name, oid in columns.items()
                ])

                # Build the Ruby code for this table
                ruby_code = (
                    f"rows = event.get(\"[{table_name}]\")\n"
                    f"if rows.is_a?(Array)\n"
                    f"  host_name = event.get(\"[host][name]\")\n"
                    f"  host_hostname = event.get(\"[host][hostname]\")\n"
                    f"  network_name = event.get(\"[network][name]\")\n"
                    f"  timestamp = event.get(\"@timestamp\")\n"
                    f"  rows.each do |row|\n"
                    f"    next unless row.is_a?(Hash)\n"
                    f"{rename_statements}\n"
                    f"    new_event = LogStash::Event.new({{\n"
                    f"      \"@timestamp\" => timestamp,\n"
                    f"      \"host\" => {{ \"name\" => host_name, \"hostname\" => host_hostname }},\n"
                    f"      \"network\" => {{ \"name\" => network_name }},\n"
                    f"      \"table\" => row,\n"
                    f"      \"metricset\" => {{ \"module\" => \"snmp\" }},\n"
                    f"      \"event\" => {{ \"kind\" => \"{table_name.lower()}\" }}\n"
                    f"    }})\n"
                    f"    new_event_block.call(new_event)\n"
                    f"  end\n"
                    f"  event.remove(\"[{table_name}]\")\n"
                    f"  event.set(\"[event][kind]\", \"metrics\")\n"
                    f"end"
                )

                special_filters.append({
                    "id": f"comp_table_split_{table_name}",
                    "type": "filter",
                    "plugin": "ruby",
                    "config": {
                        "code": ruby_code
                    }
                })

    return special_filters


def _generate_filters(oid_mappings, network):
    """
    Generate filter components based on OID mappings from profiles.

    Args:
        oid_mappings: Dictionary with 'get', 'walk', 'table' keys containing OID key-value pairs
        network: Network object for accessing network name and other properties

    Returns:
        List of filter components
    """
    # Build rename mappings for get OIDs
    get_renames = {value: _format_field_name(key) for key, value in oid_mappings['get'].items()}

    # Build rename mappings for table columns: [table_name][oid] -> [table_name][column_name]
    table_renames = {}
    for table_name, table_data in oid_mappings['table'].items():
        if isinstance(table_data, dict) and 'columns' in table_data:
            columns = table_data['columns']
            if isinstance(columns, dict):
                for column_name, oid in columns.items():
                    # Create rename from [table_name][oid] to [table_name][column_name]
                    from_field = f"[{table_name}][{oid}]"
                    to_field = f"[{table_name}][{column_name}]"
                    table_renames[from_field] = to_field

    filter_components = [
        {
            "id": "filter_mutate_1",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "rename": {
                    "host": "[host][hostname]"
                }
            }
        },
        {
            "id": "filter_mutate_2",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "rename": get_renames
            }
        },
        {
            "id": "filter_mutate_3",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "add_field": {
                    "[network][name]": f"{network}",
                    "[metricset][module]": "system"
                }
            }
        }
    ]

    # ATTENTION: This is where I'm planning on implementing special logic
    # to preprocess some data. I'm avoiding having to have 'magic functions'
    # where the user may not understand why one OID works one way and another works in a different way
    # we'll see if we need to add that.
    # oid_mappings['get'] contains key-value pairs like {"host.hostname": "1.3.6.1.2.1.1.5.0", ...}
    # oid_mappings['walk'] contains walk OID mappings
    # oid_mappings['table'] contains table OID mappings

    for mapping in oid_mappings['get']:
        pass

    filter_components.extend(_get_special_case_filters(oid_mappings))
    return filter_components


def _generate_output(input_data, network_db_object, snmp_type="polling"):
    """
    Generate Elasticsearch output configuration with data stream settings.

    Args:
        input_data: Dict containing network and device information
        network_db_object: Network model instance
        snmp_type: Type of SNMP operation - "discovery", "traps", or "polling" (default)

    Returns:
        List of output components
    """
    output_components = []

    # Get the connection from the network
    connection = network_db_object.connection

    if not connection:
        return output_components

    # Configure data stream based on snmp_type
    if snmp_type == "discovery":
        data_stream_type = "logs"
        data_stream_dataset = "snmp.discovery"
    elif snmp_type == "traps":
        data_stream_type = "logs"
        data_stream_dataset = "snmp.traps"
    else:  # polling (default)
        data_stream_type = "metrics"
        data_stream_dataset = "snmp.polling"

    config = {
        "data_stream": True,
        "data_stream_type": data_stream_type,
        "data_stream_namespace": "default",
        "data_stream_dataset": data_stream_dataset
    }

    # Add connection details based on what's available
    if connection.cloud_id:
        config["cloud_id"] = connection.cloud_id
    elif connection.host:
        config["hosts"] = [connection.host]

    # Add authentication
    if connection.api_key:
        config["api_key"] = connection.get_api_key()
    elif connection.username and connection.password:
        config["user"] = connection.username
        config["password"] = connection.get_password()

    output_components.append(
        {
            "id": f"output_elasticsearch_{network_db_object.id}",
            "type": "output",
            "plugin": "elasticsearch",
            "config": config
        }
    )

    return output_components


def GetCommitDiff(request):
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
                queryset=Device.objects.select_related('credential').prefetch_related('profiles')
            )
        ).all()

        # Cache for profile data
        profile_cache = {}

        # Collect all pipeline names we need to fetch from ES
        pipeline_names_by_connection = {}
        network_pipeline_map = {}

        for network in networks:
            if network.connection:
                conn_id = network.connection.id
                if conn_id not in pipeline_names_by_connection:
                    pipeline_names_by_connection[conn_id] = []

                pipeline_name = _get_pipeline_name(network)
                trap_pipeline_name = f"snmp-{network.logstash_name}-traps"
                discovery_pipeline_name = f"snmp-{network.logstash_name}-discovery"

                pipeline_names_by_connection[conn_id].extend(
                    [pipeline_name, trap_pipeline_name, discovery_pipeline_name])
                network_pipeline_map[network.id] = {
                    'main': pipeline_name,
                    'trap': trap_pipeline_name,
                    'discovery': discovery_pipeline_name
                }

        # Batch fetch all pipelines from Elasticsearch
        existing_pipelines = {}
        for conn_id, pipeline_names in pipeline_names_by_connection.items():
            try:
                es_client = get_elastic_connection(conn_id)

                # Fetch all pipelines for this connection in one call
                try:
                    response = es_client.logstash.get_pipeline(id=','.join(pipeline_names))
                    existing_pipelines.update(response)
                except Exception:
                    # Pipelines don't exist or error, continue
                    pass
            except Exception:
                # Connection failed, continue
                pass

        network_diffs = []

        # Iterate through each network and build pipeline configuration
        for network in networks:
            # Initialize pipeline data structure for this network
            input_data = {
                "network": network,
                "devices": {
                    "v1_v2c": {},
                    "v3": {}
                },
                "connection": network.connection
            }

            # Get all devices for this network (already prefetched)
            devices = network.devices.all()

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

            # Skip networks with no devices (unless they have traps enabled)
            has_devices = bool(input_data["devices"]["v1_v2c"] or input_data["devices"]["v3"])
            if not has_devices and not network.traps_enabled:
                continue

            # Generate components for this network (only if has devices)
            if has_devices:
                input_components, oid_mappings = _generate_input(input_data, profile_cache)
                filter_components = _generate_filters(oid_mappings, network)
            else:
                input_components = []
                filter_components = []

            components = {
                "input": input_components,
                "filter": filter_components,
                "output": _generate_output(input_data, network, snmp_type="polling")
            }

            # Generate new pipeline configuration
            new_config = ComponentToPipeline(components, test=False).components_to_logstash_config()

            # Get current pipeline configuration from pre-fetched data
            current_config = ""
            pipeline_name = network_pipeline_map.get(network.id, {}).get('main', _get_pipeline_name(network))

            if pipeline_name in existing_pipelines:
                pipeline_data = existing_pipelines[pipeline_name]
                if 'pipeline' in pipeline_data:
                    current_config = pipeline_data['pipeline']

            # Build network diff object (only include main pipeline if has devices)
            network_diff = {
                'network_name': network.name,
                'pipeline_name': pipeline_name if has_devices else None,
                'current': current_config if has_devices else "",
                'new': new_config if has_devices else "",
                'trap_pipeline': None,
                'discovery_pipeline': None,
                'has_devices': has_devices
            }

            # Handle trap pipeline if traps are enabled
            if network.traps_enabled and network.credential:
                trap_pipeline_name = network_pipeline_map.get(network.id, {}).get('trap',
                                                                                  f"snmp-{network.logstash_name}-traps")

                # Build trap input configuration
                credential = network.credential
                trap_input_config = {
                    "host": "0.0.0.0",
                    "port": 1662,
                    "oid_map_field_values": False,
                    "oid_mapping_format": "dotted_string",
                    "supported_versions": []
                }

                # Add version-specific configuration
                if credential.version in ['1', '2c']:
                    trap_input_config["supported_versions"].append(credential.version)
                    if credential.community:
                        trap_input_config["community"] = [decrypt_credential(credential.community)]
                elif credential.version == '3':
                    trap_input_config["supported_versions"].append("3")
                    if credential.security_name:
                        trap_input_config["security_name"] = credential.security_name
                    if credential.auth_protocol:
                        trap_input_config["auth_protocol"] = credential.auth_protocol
                    if credential.auth_pass:
                        trap_input_config["auth_pass"] = decrypt_credential(credential.auth_pass)
                    if credential.priv_protocol:
                        trap_input_config["priv_protocol"] = credential.priv_protocol
                    if credential.priv_pass:
                        trap_input_config["priv_pass"] = decrypt_credential(credential.priv_pass)
                    if credential.security_level:
                        trap_input_config["security_level"] = credential.security_level

                # Build trap pipeline components
                trap_components = {
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
                                    "[event][kind]": "traps"
                                }
                            }
                        }
                    ],
                    "output": _generate_output(input_data, network, snmp_type="traps")
                }

                # Generate new trap pipeline configuration
                new_trap_config = ComponentToPipeline(trap_components, test=False).components_to_logstash_config()

                # Get current trap pipeline configuration from pre-fetched data
                current_trap_config = ""
                if trap_pipeline_name in existing_pipelines:
                    pipeline_data = existing_pipelines[trap_pipeline_name]
                    if 'pipeline' in pipeline_data:
                        current_trap_config = pipeline_data['pipeline']

                network_diff['trap_pipeline'] = {
                    'pipeline_name': trap_pipeline_name,
                    'current': current_trap_config,
                    'new': new_trap_config,
                    'action': 'create' if not current_trap_config else 'update'
                }
            else:
                # Traps disabled or no credential - check if trap pipeline exists and needs to be deleted
                trap_pipeline_name = network_pipeline_map.get(network.id, {}).get('trap',
                                                                                  f"snmp-{network.logstash_name}-traps")
                current_trap_config = ""

                if trap_pipeline_name in existing_pipelines:
                    pipeline_data = existing_pipelines[trap_pipeline_name]
                    if 'pipeline' in pipeline_data:
                        current_trap_config = pipeline_data['pipeline']

                if current_trap_config:
                    network_diff['trap_pipeline'] = {
                        'pipeline_name': trap_pipeline_name,
                        'current': current_trap_config,
                        'new': '',
                        'action': 'delete'
                    }

            # Handle discovery pipeline if discovery is enabled
            if network.discovery_enabled and network.discovery_credential:
                discovery_pipeline_name = network_pipeline_map.get(network.id, {}).get('discovery',
                                                                                       f"snmp-{network.logstash_name}-discovery")

                # Generate discovery pipeline components
                discovery_input_components, discovery_oid_mappings = _generate_discovery_input(network)
                discovery_filter_components = _generate_discovery_filters(discovery_oid_mappings, network)

                discovery_components = {
                    "input": discovery_input_components,
                    "filter": discovery_filter_components,
                    "output": _generate_output(input_data, network, snmp_type="discovery")
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

                network_diff['discovery_pipeline'] = {
                    'pipeline_name': discovery_pipeline_name,
                    'current': current_discovery_config,
                    'new': new_discovery_config,
                    'action': 'create' if not current_discovery_config else 'update'
                }
            else:
                # Discovery is disabled or no credential - check if pipeline exists and needs to be deleted
                discovery_pipeline_name = network_pipeline_map.get(network.id, {}).get('discovery',
                                                                                       f"snmp-{network.logstash_name}-discovery")
                current_discovery_config = ""

                if discovery_pipeline_name in existing_pipelines:
                    pipeline_data = existing_pipelines[discovery_pipeline_name]
                    if 'pipeline' in pipeline_data:
                        current_discovery_config = pipeline_data['pipeline']

                if current_discovery_config:
                    network_diff['discovery_pipeline'] = {
                        'pipeline_name': discovery_pipeline_name,
                        'current': current_discovery_config,
                        'new': '',
                        'action': 'delete'
                    }

            network_diffs.append(network_diff)

        return JsonResponse({
            'success': True,
            'networks': network_diffs
        })

    except Exception as e:
        logger.error(f"Error in GetCommitDiff: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_admin_role
def CommitConfiguration(request):
    """Commit SNMP configuration - creates/updates Logstash pipelines in Elasticsearch"""
    try:
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

                # Get all devices for this network
                devices = Device.objects.filter(network=network).select_related('credential')

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

                # Only create main discovery pipeline if there are devices
                if has_devices:
                    # Generate components for this network
                    input_components, oid_mappings = _generate_input(input_data)
                    filter_components = _generate_filters(oid_mappings, network)

                    components = {
                        "input": input_components,
                        "filter": filter_components,
                        "output": _generate_output(input_data, network, snmp_type="polling")
                    }

                    # Generate pipeline configuration
                    pipeline_content = ComponentToPipeline(components, test=False).components_to_logstash_config()
                    pipeline_name = _get_pipeline_name(network)

                    # Use helper function to create or update the pipeline
                    success, is_new, error, was_updated = _create_or_update_pipeline(
                        es,
                        pipeline_name,
                        pipeline_content,
                        description=f"[MANAGED] SNMP pipeline for network: {network.name}"
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
                        errors.append(f"Network '{network.name}': {error}")
                        logger.error(f"Failed to create/update pipeline {pipeline_name}: {error}")
                        continue
                else:
                    # Network has no devices - delete main pipeline if it exists
                    try:
                        pipeline_name = _get_pipeline_name(network)
                        try:
                            existing = es.logstash.get_pipeline(id=pipeline_name)
                            if pipeline_name in existing:
                                # Pipeline exists, delete it
                                es.logstash.delete_pipeline(id=pipeline_name)
                                pipelines_deleted += 1
                        except Exception:
                            # Pipeline doesn't exist, that's okay
                            pass
                    except Exception as delete_e:
                        errors.append(f"Network '{network.name}' main pipeline deletion: {str(delete_e)}")

                # Handle SNMP Trap pipeline if traps are enabled
                if network.traps_enabled:
                    if not network.credential:
                        errors.append(f"Network '{network.name}': Traps enabled but no credential configured")
                    else:
                        try:
                            # Generate trap pipeline name
                            trap_pipeline_name = f"snmp-{network.logstash_name}-traps"

                            # Build trap input configuration
                            credential = network.credential
                            trap_input_config = {
                                "host": "0.0.0.0",
                                "port": 1662,
                                "oid_map_field_values": False,
                                "oid_mapping_format": "dotted_string",
                                "supported_versions": []
                            }

                            # Add version-specific configuration
                            if credential.version in ['1', '2c']:
                                trap_input_config["supported_versions"].append(credential.version)
                                if credential.community:
                                    trap_input_config["community"] = [decrypt_credential(credential.community)]
                            elif credential.version == '3':
                                trap_input_config["supported_versions"].append("3")
                                if credential.security_name:
                                    trap_input_config["security_name"] = credential.security_name
                                if credential.auth_protocol:
                                    trap_input_config["auth_protocol"] = credential.auth_protocol
                                if credential.auth_pass:
                                    trap_input_config["auth_pass"] = decrypt_credential(credential.auth_pass)
                                if credential.priv_protocol:
                                    trap_input_config["priv_protocol"] = credential.priv_protocol
                                if credential.priv_pass:
                                    trap_input_config["priv_pass"] = decrypt_credential(credential.priv_pass)
                                if credential.security_level:
                                    trap_input_config["security_level"] = credential.security_level

                            # Build trap pipeline components
                            trap_components = {
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
                                                "[event][kind]": "traps"
                                            }
                                        }
                                    }
                                ],
                                "output": _generate_output(input_data, network, snmp_type="traps")
                            }

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
                        trap_pipeline_name = f"snmp-{network.logstash_name}-traps"

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
                            discovery_pipeline_name = f"snmp-{network.logstash_name}-discovery"

                            # Generate discovery pipeline components
                            discovery_input_components, discovery_oid_mappings = _generate_discovery_input(network)
                            discovery_filter_components = _generate_discovery_filters(discovery_oid_mappings, network)

                            discovery_components = {
                                "input": discovery_input_components,
                                "filter": discovery_filter_components,
                                "output": _generate_output(input_data, network, snmp_type="discovery")
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
                        discovery_pipeline_name = f"snmp-{network.logstash_name}-discovery"

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
                if network.connection:
                    # Add main pipeline
                    expected_pipelines.add(_get_pipeline_name(network))
                    # Add trap pipeline if traps are enabled
                    if network.traps_enabled:
                        expected_pipelines.add(f"snmp-{network.logstash_name}-traps")
                    # Add discovery pipeline if discovery is enabled
                    if network.discovery_enabled:
                        expected_pipelines.add(f"snmp-{network.logstash_name}-discovery")

            # Get all pipelines from Elasticsearch for each connection
            connections_checked = set()
            for network in networks:
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

        # Build response message
        if pipelines_created == 0 and pipelines_updated == 0 and pipelines_deleted == 0:
            if errors:
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to commit any pipelines. Errors: ' + '; '.join(errors)
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

        message = "Successfully committed: " + ", ".join(message_parts)

        if errors:
            message += f". Warnings: {'; '.join(errors)}"

        return JsonResponse({
            'success': True,
            'message': message,
            'pipelines_created': pipelines_created,
            'pipelines_updated': pipelines_updated,
            'pipelines_deleted': pipelines_deleted,
            'errors': errors if errors else None
        })

    except Exception as e:
        logger.error(f"Unexpected error in CommitConfiguration: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)


@require_admin_role
def GenerateCommitConfiguration(request):
    """Commit SNMP configuration - builds and deploys Logstash pipelines"""
    try:
        # Query all networks
        networks = Network.objects.all()
        components = {
            "input": [],
            "filter": [],
            "output": []
        }

        # Iterate through each network and build pipeline configuration
        for network in networks:
            # Initialize pipeline data structure for this network
            input_data = {
                "network": network,
                "devices": {
                    "v1_v2c": {},
                    "v3": {}
                },
                "connection": network.connection
            }

            # Get all devices for this network
            devices = Device.objects.filter(network=network).select_related('credential')

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

            # Generate inputs
            components["input"] = _generate_input(input_data)
            components["output"] = _generate_output(input_data, network, snmp_type="polling")

            logstash_config = ComponentToPipeline(components, test=False).components_to_logstash_config()

        return JsonResponse({
            'success': True,
            'message': f'Configuration commit initiated for {networks.count()} network(s).'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


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
        queryset = Device.objects.select_related('credential', 'network').prefetch_related('profiles').only(
            'id', 'name', 'ip_address', 'port', 'retries', 'timeout', 'created_at',
            'credential__id', 'credential__name',
            'network__id', 'network__name'
        )

        # Apply search filter (name or IP address)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(ip_address__icontains=search)
            )

        # Apply network filter
        if network_filter:
            queryset = queryset.filter(network_id=network_filter)

        # Apply sorting
        valid_sort_fields = ['name', '-name', 'ip_address', '-ip_address', 'created_at', '-created_at']
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
            # Strip .json extension from profile names for display (using list comprehension for speed)
            profile_names = [
                p.name[:-5] if p.name.endswith('.json') else p.name
                for p in device.profiles.all()
            ]

            devices.append({
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'port': device.port,
                'retries': device.retries,
                'timeout': device.timeout,
                'credential_id': device.credential.id if device.credential else None,
                'credential_name': device.credential.name if device.credential else None,
                'network_id': device.network.id if device.network else None,
                'network_name': device.network.name if device.network else None,
                'profiles': profile_names,
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


@require_admin_role
def AddDevice(request):
    """Add a new SNMP device"""
    try:
        # Extract form data
        name = request.POST.get('name')
        ip_address = request.POST.get('ip_address')
        port = request.POST.get('port', 161)
        retries = request.POST.get('retries', 2)
        timeout = request.POST.get('timeout', 1000)
        credential_id = request.POST.get('credential')
        network_id = request.POST.get('network')
        profile_names = request.POST.getlist('profiles')  # Get list of profile names

        # Create device object
        device = Device(
            name=name,
            ip_address=ip_address,
            port=int(port) if port else 161,
            retries=int(retries) if retries else 2,
            timeout=int(timeout) if timeout else 1000
        )

        # Set optional foreign keys
        if credential_id:
            device.credential_id = credential_id
        if network_id:
            device.network_id = network_id

        # Save (this will trigger validation)
        device.save()

        # Ensure 'system' profile is always included
        if not profile_names:
            profile_names = []
        if 'system' not in profile_names:
            profile_names.insert(0, 'system')  # Add system as first profile

        # Add profiles (ManyToMany must be set after save)
        for profile_name in profile_names:
            # Check if this is an official profile (exists as JSON file)
            official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
            is_official = os.path.exists(os.path.join(official_profiles_dir, f"{profile_name}.json"))

            # Determine the stored name: official profiles get .json extension, custom profiles don't
            stored_name = f"{profile_name}.json" if is_official else profile_name

            # Get or create the profile entry
            profile, created = Profile.objects.get_or_create(
                name=stored_name,
                defaults={
                    'profile_data': {'is_official_placeholder': is_official},
                    'description': f'{"Official" if is_official else "Custom"} profile'
                }
            )
            device.profiles.add(profile)

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
        device.ip_address = request.POST.get('ip_address', device.ip_address)
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

        # Save (this will trigger validation)
        device.save()

        # Update profiles (ManyToMany)
        profile_names = request.POST.getlist('profiles')

        # Ensure 'system' profile is always included
        if not profile_names:
            profile_names = []
        if 'system' not in profile_names:
            profile_names.insert(0, 'system')  # Add system as first profile

        device.profiles.clear()  # Clear existing profiles
        for profile_name in profile_names:
            # Check if this is an official profile (exists as JSON file)
            official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
            is_official = os.path.exists(os.path.join(official_profiles_dir, f"{profile_name}.json"))

            # Determine the stored name: official profiles get .json extension, custom profiles don't
            stored_name = f"{profile_name}.json" if is_official else profile_name

            # Get or create the profile entry
            profile, created = Profile.objects.get_or_create(
                name=stored_name,
                defaults={
                    'profile_data': {'is_official_placeholder': is_official},
                    'description': f'{"Official" if is_official else "Custom"} profile'
                }
            )
            device.profiles.add(profile)

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


def GetDevice(request, device_id):
    """Get a single device"""
    try:
        device = Device.objects.get(pk=device_id)

        # Strip .json extension from profile names for display
        profile_names = []
        for profile in device.profiles.all():
            name = profile.name
            # Remove .json extension if present (official profiles)
            if name.endswith('.json'):
                name = name[:-5]
            profile_names.append(name)

        data = {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
            'port': device.port,
            'retries': device.retries,
            'timeout': device.timeout,
            'credential': device.credential_id if device.credential else None,
            'network': device.network_id if device.network else None,
            'profiles': profile_names,
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

def GetOfficialProfile(request, profile_name):
    """Get an official profile from JSON file"""
    try:
        official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
        profile_path = os.path.join(official_profiles_dir, f"{profile_name}.json")

        if not os.path.exists(profile_path):
            return JsonResponse({'success': False, 'message': 'Profile not found'}, status=404)

        with open(profile_path, 'r') as f:
            profile_data = json.load(f)

        return JsonResponse({
            'success': True,
            'name': profile_data.get('name', profile_name),
            'description': profile_data.get('description', ''),
            'type': profile_data.get('type', ''),
            'vendor': profile_data.get('vendor', ''),
            'pinned': profile_data.get('pinned', False),
            'profile_data': profile_data
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
            'description': profile.description,
            'type': profile.type,
            'vendor': profile.vendor,
            'profile_data': profile.profile_data
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
        profile_type = data.get('type', '')
        vendor = data.get('vendor', '')
        profile_data = data.get('profile_data', {})

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
            type=profile_type,
            vendor=vendor,
            profile_data=profile_data
        )
        profile.save()

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
        profile.type = data.get('type', profile.type)
        profile.vendor = data.get('vendor', profile.vendor)
        profile.profile_data = data.get('profile_data', profile.profile_data)

        # If name changed, check for conflicts
        if new_name != profile.name:
            if Profile.objects.filter(name=new_name).exists():
                return JsonResponse({'success': False, 'message': 'A profile with this name already exists'},
                                    status=400)
            profile.name = new_name

        profile.save()

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
        if profile_name in ['system', 'system.json']:
            return JsonResponse({
                'success': False,
                'message': 'The system profile cannot be deleted as it is required for all devices'
            }, status=403)

        profile = Profile.objects.get(name=profile_name)
        profile.delete()

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

        # Load official profiles from JSON files
        official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
        if os.path.exists(official_profiles_dir):
            for filename in os.listdir(official_profiles_dir):
                if filename.endswith('.json'):
                    profile_name = filename[:-5]
                    display_name = profile_name.replace('_', ' ').title()
                    all_profiles.append({
                        'name': profile_name,
                        'display_name': display_name,
                        'is_official': True
                    })

        # Load user profiles from database (exclude placeholders)
        for profile in Profile.objects.all():
            # Skip placeholder profiles (those with is_official_placeholder flag)
            if profile.profile_data.get('is_official_placeholder'):
                continue
            all_profiles.append({
                'name': profile.name,
                'display_name': profile.name.replace('_', ' ').title(),
                'is_official': False
            })

        # Sort by display name
        all_profiles.sort(key=lambda x: x['display_name'])

        return JsonResponse({'profiles': all_profiles}, status=200)

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


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
                    'type': profile.type,
                    'vendor': profile.vendor,
                }
                for profile in device.profiles.all()
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
    Aggregates by host.name and returns top hits from the last 2 hours.
    """
    try:

        # Get all connections
        connections = Connection.objects.all()

        if not connections.exists():
            return JsonResponse({
                'success': False,
                'error': 'No Elasticsearch connections configured'
            }, status=400)

        all_discovered_devices = []
        errors = []

        # Calculate time range (last 2 hours)
        now = datetime.now(timezone.utc)
        two_hours_ago = now - timedelta(hours=2)

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
                                            "gte": two_hours_ago.isoformat(),
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
                                "field": "host.name",
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
                                                "host.name",
                                                "host.hostname",
                                                "host.os.full",
                                                "host.ip",
                                                "network.name",
                                                "@timestamp"
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
                                        network_obj = Network.objects.filter(name=network_name).first()
                                        if network_obj:
                                            network_id = network_obj.id
                                            if network_obj.discovery_credential:
                                                credential_id = network_obj.discovery_credential.id
                                    except Exception as e:
                                        logger.warning(f"Could not query network '{network_name}': {str(e)}")

                                device = {
                                    'host_name': source.get('host', {}).get('name', 'Unknown'),
                                    'host_hostname': source.get('host', {}).get('hostname', ''),
                                    'host_os_full': source.get('host', {}).get('os', {}).get('full', ''),
                                    'host_ip': source.get('host', {}).get('ip', ''),
                                    'network_name': network_name,
                                    'network_id': network_id,
                                    'credential_id': credential_id,
                                    'timestamp': source.get('@timestamp', ''),
                                    'connection_name': connection.name,
                                    'connection_id': connection.id
                                }
                                all_discovered_devices.append(device)

            except Exception as e:
                errors.append(f"Connection '{connection.name}': {str(e)}")
                continue

        return JsonResponse({
            'success': True,
            'devices': all_discovered_devices,
            'total': len(all_discovered_devices),
            'errors': errors if errors else None
        })

    except Exception as e:
        traceback.print_exc()
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
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
                    {
                        "term": {
                            "event.kind": "interfaces"
                        }
                    }
                ]
            }
        },
        aggregations={
            "fans": {
                "terms": {
                    "field": "table.ifDescr",
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
            visualization_data['interfaces'].append(doc['_source']['table'])

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
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
                    {
                        "term": {
                            "event.kind": "metrics"
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
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
                    {
                        "term": {
                            "event.kind": "fans"
                        }
                    }
                ]
            }
        },
        aggregations={
            "fans": {
                "terms": {
                    "field": "table.description",
                    "size": 1000
                },
                "aggregations": {
                    "top_fan_doc": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["table.state", "table.description"]
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
            visualization_data['fans'].append(doc['_source']['table'])

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
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
                    {
                        "term": {
                            "event.kind": "sensors"
                        }
                    }
                ]
            }
        },
        aggregations={
            "sensors": {
                "terms": {
                    "field": "table.description",
                    "size": 1000
                },
                "aggregations": {
                    "top_sensor_doc": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["table.state", "table.description", "table.temp_celsius",
                                        "table.temp_threshold"]
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
            visualization_data['sensors'].append(doc['_source']['table'])

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
    if "interfaces" in visualizations:
        visualization_data['interfaces'] = _get_device_interfaces(device, es_connection)

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

            # Build list of IP addresses to check
            ip_addresses = [device.ip_address for device in device_list]

            # Single query checking all IPs at once
            search_results = es.search(
                size=0,  # We only need aggregations, not actual documents
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
                                    "host.hostname": ip_addresses
                                }
                            }
                        ]
                    }
                },
                aggregations={
                    "online_devices": {
                        "terms": {
                            "field": "host.hostname",
                            "size": len(ip_addresses)
                        }
                    }
                }
            )

            # Extract which IPs have data (are online)
            online_ips = set()
            if 'aggregations' in search_results and 'online_devices' in search_results['aggregations']:
                for bucket in search_results['aggregations']['online_devices']['buckets']:
                    online_ips.add(bucket['key'])

            # Map back to device IDs
            for device in device_list:
                results[device.id] = device.ip_address in online_ips

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
                        {
                            "term": {
                                "host.hostname": device.ip_address
                            }
                        }
                    ]
                }
            },
            aggregations={
                "data_kinds": {
                    "terms": {
                        "field": "event.kind",
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
