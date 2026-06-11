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
from Common.formatters import _sanitize_pipeline_name_component

from .snmp_pipeline_generator import (
    _generate_input, 
    _generate_output, 
    _generate_discovery_input, 
    _generate_discovery_filters, 
    _generate_filters,
    _OFFICIAL_PROFILE_CACHE
)

from PipelineManager.models import Connection

from .models import Credential, Network, Profile, Device, DeviceTemplate

from datetime import datetime, timedelta, timezone

import json
import os
import logging

logger = logging.getLogger(__name__)


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


import traceback


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
        from django.db.models import Count
        import logging
        logger = logging.getLogger(__name__)
        
        networks = Network.objects.select_related('connection').annotate(
            device_count=Count('devices')
        ).all()
        networks_data = []
        for network in networks:
            namespace_value = getattr(network, 'namespace', 'default')
            logger.info(f"Network {network.id} namespace: {namespace_value}")
            
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
                'device_count': network.device_count
            }
            logger.info(f"Network dict: {network_dict}")
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
# Network CRUD Operations
# ============================================================================

@require_admin_role
def AddNetwork(request):
    """Add a new SNMP network"""
    try:
        # Extract form data
        name = request.POST.get('name')
        network_range = request.POST.get('network_range')
        connection_id = request.POST.get('connection')
        credential_id = request.POST.get('credential')
        discovery_credential_id = request.POST.get('discovery_credential')
        discovery_enabled = request.POST.get('discovery_enabled', 'true') == 'true'
        traps_enabled = request.POST.get('traps_enabled', 'false') == 'true'
        interval = int(request.POST.get('interval', 30))
        namespace = request.POST.get('namespace', 'default')

        # Create network object
        network = Network(
            name=name,
            network_range=network_range,
            discovery_enabled=discovery_enabled,
            traps_enabled=traps_enabled,
            interval=interval,
            namespace=namespace
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
        
        # Mark config as changed to show deployment indicator
        from SNMP.models import SNMPDeploymentState
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
        network.namespace = request.POST.get('namespace', network.namespace)
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
        
        # Mark config as changed to show deployment indicator
        from SNMP.models import SNMPDeploymentState
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
        from SNMP.models import SNMPDeploymentState
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
        from SNMP.models import SNMPDeploymentState
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
        network_pipeline_map = {}

        for network in networks:
            if network.connection:
                conn_id = network.connection.id
                if conn_id not in pipeline_names_by_connection:
                    pipeline_names_by_connection[conn_id] = []

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
            # Get all devices for this network (already prefetched)
            devices = network.devices.all()
            
            # Get unique templates for this network
            templates = _get_unique_templates_for_network(devices)
            
            # Skip networks with no devices (unless they have traps enabled)
            has_devices = bool(devices.filter(credential__isnull=False).exists())
            if not has_devices and not network.traps_enabled:
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
                filter_components = _generate_filters(oid_mappings, network, normalizers)

                components = {
                    "input": input_components,
                    "filter": filter_components,
                    "output": _generate_output(input_data, network, snmp_type="polling")
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
                                    "[event][category]": "traps"
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

        # Check for orphaned pipelines that will be deleted
        # Build a set of expected pipeline names
        expected_pipelines = set()
        for network in networks:
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
        
        # Check each connection for orphaned pipelines
        connections_checked = set()
        for network in networks:
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
                            
                            if '[MANAGED]' in description and pipeline_name not in expected_pipelines:
                                # This is an orphaned pipeline - add to diffs as delete
                                network_diffs.append({
                                    'network_name': 'Orphaned',
                                    'pipeline_name': pipeline_name,
                                    'current': pipeline_data.get('pipeline', ''),
                                    'new': '',
                                    'pipeline_type': 'orphaned',
                                    'action': 'delete',
                                    'note': 'Pipeline no longer matches any configured network/template'
                                })
                except Exception as e:
                    # Connection error or ES error - skip orphan detection for this connection
                    logger.warning(f"Could not check for orphaned pipelines on connection {conn_id}: {str(e)}")
        
        # Check if there are actual changes
        # If user changed config then reverted, indicator may show changes but diff is empty
        from SNMP.models import SNMPDeploymentState
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
            'has_changes': has_actual_changes
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
            
            for diff in cached_plan:
                pipeline_name = diff.get('pipeline_name')
                action = diff.get('action')
                network_name = diff.get('network_name')
                
                try:
                    # Get the network to access its connection
                    if network_name == 'Orphaned':
                        # For orphaned pipelines, we need to find which connection they're on
                        # We'll get the connection from the first network (they should all be on same connection)
                        network = Network.objects.select_related('connection').first()
                    else:
                        network = Network.objects.select_related('connection').get(name=network_name)
                    
                    if not network or not network.connection:
                        errors.append(f"Pipeline '{pipeline_name}': No connection found")
                        continue
                    
                    es = get_elastic_connection(network.connection.id)
                    
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
            
            # Build response message
            if pipelines_created == 0 and pipelines_updated == 0 and pipelines_deleted == 0:
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
            
            message = "Successfully deployed: " + ", ".join(message_parts)
            if errors:
                message += f". Warnings: {'; '.join(errors)}"
            
            # Mark deployment as successful
            from SNMP.models import SNMPDeploymentState
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
                        filter_components = _generate_filters(oid_mappings, network, normalizers)

                        components = {
                            "input": input_components,
                            "filter": filter_components,
                            "output": _generate_output(template_input_data, network, snmp_type="polling")
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
                                                "[event][category]": "traps"
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

        message = "Successfully deployed: " + ", ".join(message_parts)

        if errors:
            message += f". Warnings: {'; '.join(errors)}"

        # Mark deployment as successful to clear the indicator
        from SNMP.models import SNMPDeploymentState
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


@require_admin_role
def GenerateDeployConfiguration(request):
    """Deploy SNMP configuration - builds and deploys Logstash pipelines"""
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
            'message': f'Configuration deployment initiated for {networks.count()} network(s).'
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
        queryset = Device.objects.select_related('credential', 'network', 'device_template').only(
            'id', 'name', 'ip_address', 'port', 'retries', 'timeout', 'created_at',
            'credential__id', 'credential__name',
            'network__id', 'network__name',
            'device_template__id', 'device_template__name'
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
                'device_template_id': device.device_template.id if device.device_template else None,
                'device_template_name': device.device_template.name if device.device_template else None,
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
        device_template_id = request.POST.get('device_template')
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
        if device_template_id:
            device.device_template_id = device_template_id

        # Save (this will trigger validation)
        device.save()
        
        # Mark config as changed to show deployment indicator
        from SNMP.models import SNMPDeploymentState
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

        device_template_id = request.POST.get('device_template')
        if device_template_id:
            device.device_template_id = device_template_id
        else:
            device.device_template = None

        # Save (this will trigger validation)
        device.save()
        
        # Mark config as changed to show deployment indicator
        from SNMP.models import SNMPDeploymentState
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


def GetDevice(request, device_id):
    """Get a single device"""
    try:
        device = Device.objects.get(pk=device_id)

        data = {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
            'port': device.port,
            'retries': device.retries,
            'timeout': device.timeout,
            'credential': device.credential_id if device.credential else None,
            'network': device.network_id if device.network else None,
            'device_template': device.device_template_id if device.device_template else None,
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
        from SNMP.models import SNMPDeploymentState
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

        return JsonResponse({
            'success': True,
            'name': profile_data.get('name', profile_name),
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
            
            # Create friendly display name for official profiles
            if is_official:
                display_name = profile.name[:-5].replace('_', ' ').title()
            else:
                display_name = profile.name
            
            all_profiles.append({
                'id': profile.id,  # Always use database ID
                'name': profile.name,
                'display_name': display_name,
                'is_official': is_official,
                'vendor': profile.vendor or ''
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
        ten_minutes_ago = now - timedelta(minutes=10)
        #two_hours_ago = now - timedelta(hours=2)

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
                                            "gte": ten_minutes_ago.isoformat(),
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
                                    from .views import suggest_device_template
                                    suggested_template_ids = suggest_device_template(sys_descr)
                                    
                                    # Get the name of the first (best) suggested template
                                    if suggested_template_ids:
                                        try:
                                            from .models import DeviceTemplate
                                            best_template = DeviceTemplate.objects.get(id=suggested_template_ids[0])
                                            suggested_template_name = best_template.name.replace('_', ' ').title()
                                        except DeviceTemplate.DoesNotExist:
                                            pass
                                
                                device = {
                                    'host_name': source.get('host', {}).get('name', 'Unknown'),
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
                            "event.category": "interface"
                        }
                    }
                ]
            }
        },
        aggregations={
            "fans": {
                "terms": {
                    "field": "interface.ifDescr",
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
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
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
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
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
                    {
                        "term": {
                            "host.hostname": device.ip_address
                        }
                    },
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

        return JsonResponse({
            'name': template_data.get('name', template_name),
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
                    'display_name': profile.name[:-5].replace('_', ' ').title() if profile.name.endswith('.json') else profile.name
                }
                for profile in template.profiles.all()
            ]
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"GetDeviceTemplate {template_id}: Returning {len(profiles_data)} profiles: {profiles_data}")
            
            return JsonResponse({
                'id': template.id,
                'name': template.name,
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
        from SNMP.models import SNMPDeploymentState
        SNMPDeploymentState.mark_config_changed()
        
        return JsonResponse({
            'success': True,
            'message': 'Device template created successfully',
            'template_id': template.id
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
        from SNMP.models import SNMPDeploymentState
        SNMPDeploymentState.mark_config_changed()
        
        return JsonResponse({
            'success': True,
            'message': 'Device template updated successfully'
        })
    except DeviceTemplate.DoesNotExist:
        return JsonResponse({'error': 'Device template not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
        from SNMP.models import SNMPDeploymentState
        SNMPDeploymentState.mark_config_changed()
        
        return JsonResponse({
            'success': True,
            'message': f'Device template "{template_name}" deleted successfully'
        })
    except DeviceTemplate.DoesNotExist:
        return JsonResponse({'error': 'Device template not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
