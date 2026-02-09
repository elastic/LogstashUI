from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from SNMP.models import Credential, Network, Profile, Device
from .logstash_config_parse import ComponentToPipeline
from django.core.exceptions import ValidationError
from django.conf import settings
import json
import os
import re


def _sanitize_pipeline_name_component(name):
    """
    Sanitize a name component for use in pipeline names.
    Only allows letters, numbers, underscores, and hyphens.
    Replaces any other characters with underscores.
    """
    # Replace any character that isn't a letter, number, underscore, or hyphen with underscore
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized.lower()


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
    Uses the same logic as CreatePipeline in views.py.
    
    Args:
        es_connection: Elasticsearch connection object
        pipeline_name: Name of the pipeline
        pipeline_content: Pipeline configuration string
        description: Optional description for the pipeline
    
    Returns:
        tuple: (success: bool, is_new: bool, error: str or None)
    """
    from datetime import datetime, timezone
    
    try:
        # Check if pipeline already exists
        pipeline_exists = False
        existing_settings = None
        existing_metadata = None
        
        try:
            existing = es_connection.logstash.get_pipeline(id=pipeline_name)
            if pipeline_name in existing:
                pipeline_exists = True
                existing_settings = existing[pipeline_name].get('pipeline_settings', {})
                existing_metadata = existing[pipeline_name].get('pipeline_metadata', {})
        except:
            pipeline_exists = False
        
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
        
        return (True, not pipeline_exists, None)
        
    except Exception as e:
        return (False, False, str(e))


@require_http_methods(["GET"])
def GetCredentials(request):
    """Get all SNMP credentials"""
    try:
        credentials = Credential.objects.all().values('id', 'name', 'version', 'description')
        return JsonResponse(list(credentials), safe=False, status=200)
    except Exception as e:
        return HttpResponse(f"Error fetching credentials: {str(e)}", status=500)


@require_http_methods(["GET"])
def GetNetworks(request):
    """Get all SNMP networks"""
    try:
        networks = Network.objects.all().values('id', 'name', 'network_range', 'logstash_name')
        return JsonResponse(list(networks), safe=False, status=200)
    except Exception as e:
        return HttpResponse(f"Error fetching networks: {str(e)}", status=500)


@require_http_methods(["POST"])
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


@require_http_methods(["POST"])
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


@require_http_methods(["GET"])
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


@require_http_methods(["POST"])
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


# ============================================================================
# Network CRUD Operations
# ============================================================================

@require_http_methods(["POST"])
def AddNetwork(request):
    """Add a new SNMP network"""
    try:
        # Extract form data
        name = request.POST.get('name')
        network_range = request.POST.get('network_range')
        logstash_name = request.POST.get('logstash_name')
        connection_id = request.POST.get('connection')
        discovery_enabled = request.POST.get('discovery_enabled', 'true') == 'true'
        
        # Create network object
        network = Network(
            name=name,
            network_range=network_range,
            logstash_name=logstash_name,
            discovery_enabled=discovery_enabled
        )
        
        # Set connection if provided
        if connection_id:
            network.connection_id = connection_id
        
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


@require_http_methods(["POST"])
def UpdateNetwork(request, network_id):
    """Update an existing SNMP network"""
    try:
        network = Network.objects.get(pk=network_id)
        
        # Update fields
        network.name = request.POST.get('name', network.name)
        network.network_range = request.POST.get('network_range', network.network_range)
        network.logstash_name = request.POST.get('logstash_name', network.logstash_name)
        network.discovery_enabled = request.POST.get('discovery_enabled', 'true') == 'true'
        
        # Update connection
        connection_id = request.POST.get('connection')
        if connection_id:
            network.connection_id = connection_id
        else:
            network.connection = None
        
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


@require_http_methods(["GET"])
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
            'discovery_enabled': network.discovery_enabled,
        }
        
        return JsonResponse(data)
        
    except Network.DoesNotExist:
        return JsonResponse({'error': 'Network not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def DeleteNetwork(request, network_id):
    """Delete a network"""
    try:
        network = Network.objects.get(pk=network_id)
        network.delete()
        
        return HttpResponse("""
            <div class="p-4 mb-4 text-sm text-green-700 bg-green-100 rounded-lg">
                Network deleted successfully!
                <script>
                    setTimeout(() => {
                        window.location.reload();
                    }, 500);
                </script>
            </div>
        """)
        
    except Network.DoesNotExist:
        return HttpResponse("Network not found", status=404)
    except Exception as e:
        return HttpResponse(f"Error deleting network: {str(e)}", status=500)


@require_http_methods(["GET"])
def GetNetworkPipelineName(request, network_id):
    """Get the pipeline name for a network based on its logstash_name and network name"""
    try:
        network = Network.objects.get(pk=network_id)
        
        # Generate sanitized pipeline name: snmp-{logstash_name}-{network_name}-*
        pipeline_name = _get_pipeline_name(network)
        
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

def _get_device_profiles(device):
    """
    Get all profiles for a device and return merged OID data.
    Returns a tuple: (profile_ids_tuple, merged_oids_dict)
    """
    from SNMP.models import Profile
    from django.conf import settings
    import os
    import json
    
    # Get all profiles for this device (prefetch to avoid N+1 queries)
    profiles = device.profiles.all().order_by('id')
    
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
            # Load the actual profile data from JSON file
            profile_name = profile.name.replace('.json', '')  # Remove .json extension
            official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
            profile_path = os.path.join(official_profiles_dir, f"{profile_name}.json")
            
            if os.path.exists(profile_path):
                try:
                    with open(profile_path, 'r') as f:
                        profile_data = json.load(f)
                except Exception as e:
                    # If we can't load the file, skip this profile
                    continue
            else:
                # Profile file doesn't exist, skip
                continue
        
        # Merge get OIDs
        if 'get' in profile_data and isinstance(profile_data['get'], dict):
            merged_oids['get'].update(profile_data['get'])
        
        # Merge walk OIDs
        if 'walk' in profile_data and isinstance(profile_data['walk'], dict):
            merged_oids['walk'].update(profile_data['walk'])
        
        # Merge table OIDs
        if 'table' in profile_data and isinstance(profile_data['table'], dict):
            merged_oids['table'].update(profile_data['table'])
    
    return (profile_ids, merged_oids)


def _generate_input(input_data):
    """
    Generate SNMP input components grouped by:
    1. Credential version (v1/v2c vs v3)
    2. Profile combination (devices with same set of profiles)
    
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
            profile_ids, merged_oids = _get_device_profiles(device)
            
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
                    "version": credential.version
                })
            
            if hosts:
                config = {
                    "hosts": hosts

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
                            'columns': list(table_data.get('columns', {}).values()) if isinstance(table_data, dict) and isinstance(table_data.get('columns'), dict) else []
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
            profile_ids, merged_oids = _get_device_profiles(device)
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
                    "version": device.credential.version
                })
            
            if hosts:
                credential = group_data['credential']
                
                config = {
                    "hosts": hosts,
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
                            'columns': list(table_data.get('columns', {}).values()) if isinstance(table_data, dict) and isinstance(table_data.get('columns'), dict) else []
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
        'walk':{}
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
                    f"    row['{field_name}'] = row.delete('{oid}')"
                    for field_name, oid in columns.items()
                ])
                
                # Build the Ruby code for this table
                ruby_code = (
                    f"rows = event.get('[{table_name}]')\n"
                    f"if rows.is_a?(Array)\n"
                    f"  host_name = event.get('[host][name]')\n"
                    f"  network_name = event.get('[network][name]')\n"
                    f"  timestamp = event.get('@timestamp')\n"
                    f"  rows.each do |row|\n"
                    f"    next unless row.is_a?(Hash)\n"
                    f"{rename_statements}\n"
                    f"    new_event = LogStash::Event.new({{\n"
                    f"      '@timestamp' => timestamp,\n"
                    f"      'host' => {{ 'name' => host_name }},\n"
                    f"      'network' => {{ 'name' => network_name }},\n"
                    f"      'table' => row,\n"
                    f"      'metricset' => {{ 'module' => 'snmp' }},\n"
                    f"      'event' => {{ 'kind' => '{table_name.lower()}' }}\n"
                    f"    }})\n"
                    f"    new_event_block.call(new_event)\n"
                    f"  end\n"
                    f"  event.remove('[{table_name}]')\n"
                    f"  event.set('[event][kind]', 'metric')\n"
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
                    "host": "[host][name]"
                } | get_renames #| table_renames
            }
        },
        {
            "id": "filter_mutate_2",
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



    
    # TODO: Implement filter generation logic based on OID mappings
    # oid_mappings['get'] contains key-value pairs like {"host.hostname": "1.3.6.1.2.1.1.5.0", ...}
    # oid_mappings['walk'] contains walk OID mappings
    # oid_mappings['table'] contains table OID mappings

    for mapping in oid_mappings['get']:
        pass


    filter_components.extend(_get_special_case_filters(oid_mappings))

    print(filter_components)
    return filter_components


def _generate_output(input_data, network_db_object):
    output_components = []
    
    # Get the connection from the network
    connection = network_db_object.connection
    
    if not connection:
        return output_components
    
    config = {
        "data_stream": True,
        "data_stream_type": "metrics",
        "data_stream_namespace": network_db_object.name.lower().replace(' ', '-'),
        "data_stream_dataset": "snmp"
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

@require_http_methods(["POST"])
def GetCommitDiff(request):
    """Get diff for all network pipeline configurations"""
    try:
        # Query all networks
        networks = Network.objects.all()
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

            # Generate components for this network
            input_components, oid_mappings = _generate_input(input_data)
            filter_components = _generate_filters(oid_mappings, network)
            
            components = {
                "input": input_components,
                "filter": filter_components,
                "output": _generate_output(input_data, network)
            }
            
            # Generate new pipeline configuration
            new_config = ComponentToPipeline(components, test=False).components_to_logstash_config()
            
            # Get current pipeline configuration from Elasticsearch (if exists)
            current_config = ""
            pipeline_name = _get_pipeline_name(network)
            
            # Try to fetch current pipeline from Elasticsearch
            if network.connection:
                try:
                    from Core.views import get_elastic_connection
                    
                    es_client = get_elastic_connection(network.connection.id)
                    
                    # Try to get the pipeline
                    try:
                        response = es_client.logstash.get_pipeline(id=pipeline_name)
                        if pipeline_name in response:
                            pipeline_data = response[pipeline_name]
                            if 'pipeline' in pipeline_data:
                                current_config = pipeline_data['pipeline']
                    except Exception as e:
                        # Pipeline doesn't exist yet, that's okay
                        pass
                except Exception as e:
                    # Connection failed, that's okay - we'll just show empty current
                    pass
            
            # Add to network diffs
            network_diffs.append({
                'network_name': network.name,
                'pipeline_name': pipeline_name,
                'current': current_config,
                'new': new_config
            })
        
        return JsonResponse({
            'success': True,
            'networks': network_diffs
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["POST"])
def CommitConfiguration(request):
    """Commit SNMP configuration - creates/updates Logstash pipelines in Elasticsearch"""
    try:
        from Core.views import get_elastic_connection
        from datetime import datetime, timezone
        
        # Query all networks
        networks = Network.objects.all()
        
        if not networks.exists():
            return JsonResponse({
                'success': False,
                'error': 'No networks configured'
            }, status=400)
        
        pipelines_created = 0
        pipelines_updated = 0
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
                
                # Skip networks with no devices
                if not devices.exists():
                    continue

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

                # Generate components for this network
                input_components, oid_mappings = _generate_input(input_data)
                filter_components = _generate_filters(oid_mappings, network)
                
                components = {
                    "input": input_components,
                    "filter": filter_components,
                    "output": _generate_output(input_data, network)
                }
                
                # Generate pipeline configuration
                pipeline_content = ComponentToPipeline(components, test=False).components_to_logstash_config()
                pipeline_name = _get_pipeline_name(network)
                
                # Check if network has a connection
                if not network.connection:
                    errors.append(f"Network '{network.name}' has no Elasticsearch connection configured")
                    continue
                
                # Get Elasticsearch connection
                es = get_elastic_connection(network.connection.id)
                
                # Use helper function to create or update the pipeline
                success, is_new, error = _create_or_update_pipeline(
                    es,
                    pipeline_name,
                    pipeline_content,
                    description=f"SNMP pipeline for network: {network.name}"
                )
                
                if success:
                    if is_new:
                        pipelines_created += 1
                    else:
                        pipelines_updated += 1
                else:
                    errors.append(f"Network '{network.name}': {error}")
                    continue
                    
            except Exception as e:
                errors.append(f"Network '{network.name}': {str(e)}")
                continue
        
        # Build response message
        if pipelines_created == 0 and pipelines_updated == 0:
            if errors:
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to commit any pipelines. Errors: ' + '; '.join(errors)
                }, status=500)
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'No pipelines to commit (no networks with devices found)'
                }, status=400)
        
        message_parts = []
        if pipelines_created > 0:
            message_parts.append(f"{pipelines_created} pipeline(s) created")
        if pipelines_updated > 0:
            message_parts.append(f"{pipelines_updated} pipeline(s) updated")
        
        message = "Successfully committed: " + ", ".join(message_parts)
        
        if errors:
            message += f". Warnings: {'; '.join(errors)}"
        
        return JsonResponse({
            'success': True,
            'message': message,
            'pipelines_created': pipelines_created,
            'pipelines_updated': pipelines_updated,
            'errors': errors if errors else None
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }, status=500)

@require_http_methods(["POST"])
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
            print(f"\nNetwork: {network.name}")

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
                    print(f"  WARNING: Device '{device.name}' has no credential assigned, skipping")
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
            components["output"] = _generate_output(input_data, network)

            print(components)
            logstash_config = ComponentToPipeline(components, test=False).components_to_logstash_config()
            print(logstash_config)





        return JsonResponse({
            'success': True,
            'message': f'Configuration commit initiated for {networks.count()} network(s).'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ============================================================================
# Device API Endpoints
# ============================================================================

@require_http_methods(["GET"])
def GetDevices(request):
    """Get paginated SNMP devices with search, filter, and sort"""
    try:
        from SNMP.models import Device
        from django.db.models import Q
        from django.core.paginator import Paginator
        
        # Get query parameters
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 25))
        search = request.GET.get('search', '').strip()
        network_filter = request.GET.get('network', '').strip()
        sort_by = request.GET.get('sort_by', '-created_at')
        
        # Start with all devices
        queryset = Device.objects.select_related('credential', 'network').prefetch_related('profiles')
        
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
        
        # Get total count before pagination
        total_count = queryset.count()
        
        # Apply pagination
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        # Serialize devices
        devices = []
        for device in page_obj:
            # Strip .json extension from profile names for display
            profile_names = []
            for profile in device.profiles.all():
                name = profile.name
                # Remove .json extension if present (official profiles)
                if name.endswith('.json'):
                    name = name[:-5]
                profile_names.append(name)
            
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
            'total_pages': paginator.num_pages,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        })
        
    except Exception as e:
        return HttpResponse(f"Error fetching devices: {str(e)}", status=500)


@require_http_methods(["POST"])
def AddDevice(request):
    """Add a new SNMP device"""
    try:
        from SNMP.models import Device, Profile
        
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
        
        # Add profiles (ManyToMany must be set after save)
        if profile_names:
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


@require_http_methods(["POST"])
def UpdateDevice(request, device_id):
    """Update an existing SNMP device"""
    try:
        from SNMP.models import Device, Profile
        
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
        device.profiles.clear()  # Clear existing profiles
        if profile_names:
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


@require_http_methods(["GET"])
def GetDevice(request, device_id):
    """Get a single device"""
    try:
        from SNMP.models import Device
        
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


@require_http_methods(["POST"])
def DeleteDevice(request, device_id):
    """Delete a device"""
    try:
        from SNMP.models import Device
        
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

@require_http_methods(["GET"])
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


@require_http_methods(["GET"])
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


@require_http_methods(["POST"])
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


@require_http_methods(["POST"])
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
                return JsonResponse({'success': False, 'message': 'A profile with this name already exists'}, status=400)
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


@require_http_methods(["POST"])
def DeleteProfile(request, profile_name):
    """Delete a user profile"""
    try:
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


@require_http_methods(["GET"])
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
