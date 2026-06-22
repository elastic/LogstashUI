#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.conf import settings
import os
import re
import ipaddress
import logging
import json

logger = logging.getLogger(__name__)

# Import Device model for discovery IP address filtering
from .models import Device
from .snmp_normalizers import _apply_normalizers

# Cache for official profile data to avoid repeated file I/O
_OFFICIAL_PROFILE_CACHE = {}


def _normalize_template_name(name: str) -> str:
    """
    Normalize a device template name so it is safe to use as an Elasticsearch
    index name component (e.g. a data stream namespace).

    Rules applied in order:
      1. Strip surrounding whitespace.
      2. Lowercase.
      3. Replace any run of whitespace with a single underscore.
      4. Replace characters that are illegal in ES index names
         (*, :, /, \\, ?, ", <, >, |, ,, #, space) with underscores.
      5. Collapse consecutive underscores/hyphens into one underscore.
      6. Strip any leading characters that ES forbids at position 0: -, _, +, .
      7. Truncate to 255 bytes (UTF-8).
      8. Fall back to 'unknown_template' if the result is empty.

    Returns:
        A normalized string safe for use as an ES index name / namespace.
    """
    if not name:
        return "unknown_template"

    slug = name.strip()
    slug = slug.lower()
    slug = re.sub(r'\s+', '_', slug)
    # Replace ES-illegal punctuation with underscores
    slug = re.sub(r'[*:/\\?"<>|,#]', '_', slug)
    # Collapse runs of underscores or hyphens into a single underscore
    slug = re.sub(r'[-_]{2,}', '_', slug)
    # Strip leading forbidden characters (-, _, +, .)
    slug = slug.lstrip('-_+.')
    # Truncate to 255 bytes
    encoded = slug.encode('utf-8')
    if len(encoded) > 255:
        slug = encoded[:255].decode('utf-8', errors='ignore')

    return slug or "unknown_template"


def _deduplicate_normalizers(normalizers):
    """
    Remove duplicate normalizers based on their content.
    Two normalizers are considered duplicates if they have the same operation, target, and params.
    
    Args:
        normalizers: List of normalizer configurations
        
    Returns:
        List of unique normalizers
    """
    if not normalizers:
        return []
    
    seen = []
    unique = []
    
    for normalizer in normalizers:
        # Create a hashable representation of the normalizer
        normalizer_key = (
            normalizer.get('operation'),
            str(normalizer.get('target', {})),
            str(normalizer.get('params', {}))
        )
        
        if normalizer_key not in seen:
            seen.append(normalizer_key)
            unique.append(normalizer)
    
    return unique

def _generate_input(input_data, profile_cache=None, template_filter=None):
    """
    Generate SNMP input components grouped by:
    1. Device template (all devices with same template in one input)
    2. Credential (devices with different credentials need separate inputs)

    Each input is enriched with ECS fields from the device template:
    - [host][type] from template.type
    - [observer][vendor] from template.vendor
    - [observer][os][full] from template.product-template.model

    Args:
        input_data: Dict containing network and device information
        profile_cache: Optional dict to cache loaded profile data
        template_filter: Optional device template ID to filter devices by

    Returns: (input_components, oid_mappings, all_normalizers)
    """
    input_components = []
    network_id = input_data['network'].id

    # Collect all OID mappings (key-value pairs) for filter generation
    oid_mappings = {
        'get': {},
        'walk': {},
        'table': {}
    }
    
    # Collect all normalizers from all device groups
    all_normalizers = []

    global_input_config = {
        "ecs_compatibility": "disabled",
        "oid_mapping_format": "dotted_string"
    }

    # Process v1/v2c devices
    if input_data['devices']['v1_v2c']:
        # Group v1/v2c devices by device template + credential
        v1_v2c_groups = {}

        for device_name, device in input_data['devices']['v1_v2c'].items():
            # Get device template (use None if not assigned)
            template_id = device.device_template.id if device.device_template else None
            
            # Skip devices that don't match the template filter
            if template_filter is not None and template_id != template_filter:
                continue
            
            profile_ids, merged_oids, normalizers = _get_device_profiles(device, profile_cache)
            credential_id = device.credential.id if device.credential else None
            
            # Use (template_id, credential_id) as grouping key
            group_key = (template_id, credential_id)

            if group_key not in v1_v2c_groups:
                v1_v2c_groups[group_key] = {
                    'devices': [],
                    'oids': merged_oids,
                    'normalizers': normalizers,
                    'template': device.device_template,
                    'credential': device.credential
                }
            else:
                # Merge normalizers from additional devices in the same group
                if normalizers:
                    v1_v2c_groups[group_key]['normalizers'].extend(normalizers)

            v1_v2c_groups[group_key]['devices'].append(device)

        # Create an input for each template+credential group
        for group_idx, (group_key, group_data) in enumerate(v1_v2c_groups.items()):
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
                template = group_data['template']
                interval_value = getattr(input_data['network'], 'interval', 30) or 30
                logger.info(
                    f"Network {input_data['network'].name} interval: {interval_value} (type: {type(interval_value)})")
                
                config = {
                    "hosts": hosts,
                    "interval": interval_value
                } | global_input_config

                # Add ECS field enrichment from device template
                add_fields = {}
                
                # Use SNMP plugin's built-in metadata field for host IP
                add_fields["[host][hostname]"] = "%{[@metadata][host_address]}"
                
                if template:
                    # [host][device_template] — normalized slug, safe for use as an ES namespace
                    add_fields["[host][device_template]"] = _normalize_template_name(template.name)

                    # [host][type] from template.type
                    if template.type:
                        add_fields["[host][type]"] = template.type
                    
                    # [observer][vendor] from template.vendor
                    if template.vendor:
                        add_fields["[observer][vendor]"] = template.vendor
                    
                    # [observer][os][full] from product-model
                    os_full_parts = []
                    if template.product:
                        os_full_parts.append(template.product)
                    if template.model:
                        os_full_parts.append(template.model)
                    if os_full_parts:
                        add_fields["[observer][os][full]"] = "-".join(os_full_parts)
                
                if add_fields:
                    config["add_field"] = add_fields

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
                
                # Collect normalizers from this group (deduplicated)
                if 'normalizers' in group_data and group_data['normalizers']:
                    # Deduplicate normalizers within this group first
                    unique_group_normalizers = _deduplicate_normalizers(group_data['normalizers'])
                    all_normalizers.extend(unique_group_normalizers)

                input_components.append({
                    "id": f"input_snmp_v1_v2c_{network_id}_group_{group_idx}",
                    "type": "input",
                    "plugin": "snmp",
                    "config": config
                })

    # Process v3 devices
    if input_data['devices']['v3']:
        # Group v3 devices by device template + credential
        v3_groups = {}

        for device_name, device in input_data['devices']['v3'].items():
            # Get device template (use None if not assigned)
            template_id = device.device_template.id if device.device_template else None
            
            # Skip devices that don't match the template filter
            if template_filter is not None and template_id != template_filter:
                continue
            
            profile_ids, merged_oids, normalizers = _get_device_profiles(device, profile_cache)
            credential_id = device.credential.id if device.credential else None

            # Use (template_id, credential_id) as grouping key
            group_key = (template_id, credential_id)

            if group_key not in v3_groups:
                v3_groups[group_key] = {
                    'devices': [],
                    'oids': merged_oids,
                    'normalizers': normalizers,
                    'template': device.device_template,
                    'credential': device.credential
                }
            else:
                # Merge normalizers from additional devices in the same group
                if normalizers:
                    v3_groups[group_key]['normalizers'].extend(normalizers)

            v3_groups[group_key]['devices'].append(device)

        # Create an input for each template+credential group
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
                template = group_data['template']
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

                # Add ECS field enrichment from device template
                add_fields = {}
                
                # Use SNMP plugin's built-in metadata field for host IP
                add_fields["[host][hostname]"] = "%{[@metadata][host_address]}"
                
                if template:
                    # [host][device_template] — normalized slug, safe for use as an ES namespace
                    add_fields["[host][device_template]"] = _normalize_template_name(template.name)

                    # [host][type] from template.type
                    if template.type:
                        add_fields["[host][type]"] = template.type
                    
                    # [observer][vendor] from template.vendor
                    if template.vendor:
                        add_fields["[observer][vendor]"] = template.vendor
                    
                    # [observer][os][full] from product-model
                    os_full_parts = []
                    if template.product:
                        os_full_parts.append(template.product)
                    if template.model:
                        os_full_parts.append(template.model)
                    if os_full_parts:
                        add_fields["[observer][os][full]"] = "-".join(os_full_parts)
                
                if add_fields:
                    config["add_field"] = add_fields

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
                
                # Collect normalizers from this group (deduplicated)
                if 'normalizers' in group_data and group_data['normalizers']:
                    # Deduplicate normalizers within this group first
                    unique_group_normalizers = _deduplicate_normalizers(group_data['normalizers'])
                    all_normalizers.extend(unique_group_normalizers)

                input_components.append({
                    "id": f"input_snmp_v3_{network_id}_group_{group_idx}",
                    "type": "input",
                    "plugin": "snmp",
                    "config": config
                })

    return input_components, oid_mappings, all_normalizers



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
    Adds event.category: discovery field to distinguish from regular metrics.

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
                    "[event][category]": "discovery"
                }
            }
        }
    ]

    return filter_components


def _generate_filters(oid_mappings, network, normalizers=None):
    """
    Generate filter components based on OID mappings from profiles.

    Args:
        oid_mappings: Dictionary with 'get', 'walk', 'table' keys containing OID key-value pairs
        network: Network object for accessing network name and other properties
        normalizers: List of normalizer configurations from profiles

    Returns:
        List of filter components
    """
    # Build rename mappings for get OIDs
    get_renames = {value: _format_field_name(key) for key, value in oid_mappings['get'].items()}

    # Build rename mappings for table columns using proper bracket notation.
    # Dotted table/column names are expanded: component.fan -> [component][fan]
    table_renames = {}
    for table_name, table_data in oid_mappings['table'].items():
        if isinstance(table_data, dict) and 'columns' in table_data:
            columns = table_data['columns']
            if isinstance(columns, dict):
                for column_name, oid in columns.items():
                    table_bracket = _format_field_name(table_name)
                    column_bracket = _format_field_name(column_name)
                    from_field = f"{table_bracket}[{oid}]"
                    to_field = f"{table_bracket}{column_bracket}"
                    table_renames[from_field] = to_field

    filter_components = [
        {
            "id": "filter_mutate_1",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "rename": get_renames
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

    # Apply normalizers from profiles
    if normalizers:
        get_normalizers = [n for n in normalizers if n.get('target', {}).get('scope') == 'get']
        normalizer_filters = _apply_normalizers(get_normalizers)
        filter_components.extend(normalizer_filters)

    # Generate table-split filters
    filter_components.extend(_generate_table_split_filters(oid_mappings))

    # Apply table-scope normalizers AFTER table splitters so they run on the
    # already-split row events (which have columns as top-level fields).
    if normalizers:
        table_normalizers = [n for n in normalizers if n.get('target', {}).get('scope') == 'table']
        table_normalizer_filters = _apply_normalizers(table_normalizers)
        filter_components.extend(table_normalizer_filters)

    return filter_components


def _generate_output(input_data, network_db_object, snmp_type="polling", device_template=None):
    """
    Generate Elasticsearch output configuration with data stream settings.

    Args:
        input_data: Dict containing network and device information
        network_db_object: Network model instance
        snmp_type: Type of SNMP operation - "discovery", "traps", or "polling" (default)
        device_template: Optional DeviceTemplate instance. When provided and
            network_db_object.namespace_from_device_template is True, the
            normalized template name is used as the data stream namespace.

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

    # Resolve namespace: use normalized template name when the flag is set and
    # a concrete template is available; fall back to the network's fixed value.
    if (snmp_type == "polling"
            and getattr(network_db_object, 'namespace_from_device_template', False)
            and device_template is not None):
        namespace = _normalize_template_name(device_template.name)
    else:
        namespace = network_db_object.namespace

    config = {
        "data_stream": True,
        "data_stream_type": data_stream_type,
        "data_stream_namespace": namespace,
        "data_stream_dataset": data_stream_dataset
    }

    # Add connection details based on what's available
    if connection.cloud_id:
        config["cloud_id"] = connection.cloud_id
    elif connection.host:
        # Add port to host if available
        host_with_port = f"{connection.host}:{connection.port}" if connection.port else connection.host
        config["hosts"] = [host_with_port]

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


def _get_device_profiles(device, profile_cache=None):
    """
    Get all profiles for a device and return merged OID data and normalizers.
    Returns a tuple: (profile_ids_tuple, merged_oids_dict, normalizers_list)

    Args:
        device: Device object with prefetched device_template and its profiles
        profile_cache: Optional dict to cache loaded profile data
    """

    if profile_cache is None:
        profile_cache = _OFFICIAL_PROFILE_CACHE

    # Get all profiles from the device's template (should already be prefetched)
    if device.device_template:
        profiles = list(device.device_template.profiles.all())
        logger.debug(f"Device '{device.name}' using template '{device.device_template.name}' with {len(profiles)} profiles")
    else:
        # No template assigned - device has no profiles
        profiles = []
        logger.debug(f"Device '{device.name}' has no template assigned")

    if not profiles:
        return (tuple(), {'get': {}, 'walk': {}, 'table': {}}, [])

    # Create a tuple of profile IDs for grouping (sorted for consistency)
    profile_ids = tuple(sorted([p.id for p in profiles]))

    # Merge OIDs from all profiles
    merged_oids = {
        'get': {},
        'walk': {},
        'table': {}
    }
    
    # Collect all normalizers from all profiles
    all_normalizers = []

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
        
        # Collect normalizers from this profile
        if 'normalizers' in profile_data and isinstance(profile_data['normalizers'], list):
            all_normalizers.extend(profile_data['normalizers'])

    return (profile_ids, merged_oids, all_normalizers)



def _load_system_profile_oids():
    """
    Load the System profile OIDs for discovery.
    Returns a dictionary with 'get', 'walk', 'table' keys.
    """
    system_profile_path = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles', 'generic_system.json')

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

    # No dots and not in bracket notation, wrap in brackets
    return f'[{field_name}]'


def _ruby_table_nested_entry(table_name, value_expr):
    """
    Generate a Ruby hash key-value entry for a (possibly dot-separated) table name.
    Dot-separated names produce nested Ruby hashes.

    Examples:
        "ifTable",      "row" -> '"ifTable" => row'
        "component.fan","row" -> '"component" => { "fan" => row }'
    """
    parts = table_name.split('.')

    def build(parts, val):
        if len(parts) == 1:
            return f'"{parts[0]}" => {val}'
        return f'"{parts[0]}" => {{ {build(parts[1:], val)} }}'

    return build(parts, value_expr)


def _ruby_row_rename_statements(columns):
    """
    Generate Ruby statements that rename OID keys to column names inside a row Hash.
    Dot-separated column names are expanded into nested hashes.

    Each parent path is initialized with ||= {} only once, regardless of how many
    columns share that parent.

    Args:
        columns: Dict of {column_name: oid}

    Returns:
        Multi-line string of 4-space-indented Ruby statements
    """
    statements = []
    initialized_paths = set()
    for field_name, oid in columns.items():
        parts = field_name.split('.')
        if len(parts) == 1:
            statements.append(f'    row["{field_name}"] = row.delete("{oid}")')
        else:
            # Emit ||= {} for each parent level only the first time it's seen
            for i in range(1, len(parts)):
                path = ''.join(f'["{p}"]' for p in parts[:i])
                if path not in initialized_paths:
                    statements.append(f'    row{path} ||= {{}}')
                    initialized_paths.add(path)
            full_path = ''.join(f'["{p}"]' for p in parts)
            statements.append(f'    row{full_path} = row.delete("{oid}")')
    return '\n'.join(statements)


def _generate_table_split_filters(oid_mappings):
    """
    Generate Ruby filter components that split SNMP table data into per-row events.

    For each table in oid_mappings, emits a ruby filter that iterates over the
    array of row hashes produced by the SNMP input plugin, renames OID keys to
    their human-readable column names (expanding dotted names into nested hashes),
    creates a new LogStash::Event per row carrying the original event metadata,
    and removes the raw table field from the original event.

    Args:
        oid_mappings: Dictionary with 'get', 'walk', 'table' keys containing OID
                      key-value pairs (only 'table' is used here)

    Returns:
        List of ruby filter component dicts, one per table that has columns defined
    """
    special_filters = []

    # Generate dynamic table splitters for all tables in oid_mappings
    for table_name, table_data in oid_mappings.get('table', {}).items():
        if isinstance(table_data, dict) and 'columns' in table_data:
            columns = table_data.get('columns', {})
            if isinstance(columns, dict) and columns:
                # Literal field path for event.get / event.remove.
                # The SNMP plugin stores table data under the table name as a single
                # literal field key (dots included), so "network.neighbor" is stored at
                # the field "[network.neighbor]", NOT the nested path "[network][neighbor]".
                table_field_path = f"[{table_name}]"

                # Ruby statements that rename OID keys to column names inside each row.
                # Dotted column names are expanded into nested Ruby hashes.
                rename_statements = _ruby_row_rename_statements(columns)

                # Nested bracket path for new_event.set — dots become separate bracket
                # pairs so Logstash merges into existing hashes rather than overwriting.
                # "network.neighbor" -> "[network][neighbor]"
                # Using event.set instead of hash literals avoids duplicate-key collisions
                # when the table top-level key matches a standard field (e.g. "network").
                table_set_path = _format_field_name(table_name)

                # Build the Ruby code for this table
                ruby_code = (
                    f"rows = event.get(\"{table_field_path}\")\n"
                    f"if rows.is_a?(Array)\n"
                    f"  host_name = event.get(\"[host][name]\")\n"
                    f"  host_hostname = event.get(\"[host][hostname]\")\n"
                    f"  host_type = event.get(\"[host][type]\")\n"
                    f"  host_device_template = event.get(\"[host][device_template]\")\n"
                    f"  observer_vendor = event.get(\"[observer][vendor]\")\n"
                    f"  observer_os_full = event.get(\"[observer][os][full]\")\n"
                    f"  network_name = event.get(\"[network][name]\")\n"
                    f"  timestamp = event.get(\"@timestamp\")\n"
                    f"  rows.each do |row|\n"
                    f"    next unless row.is_a?(Hash)\n"
                    f"{rename_statements}\n"
                    f"    new_event = LogStash::Event.new({{\n"
                    f"      \"@timestamp\" => timestamp,\n"
                    f"      \"host\" => {{ \"name\" => host_name, \"hostname\" => host_hostname, \"type\" => host_type }},\n"
                    f"      \"observer\" => {{ \"vendor\" => observer_vendor, \"os\" => {{ \"full\" => observer_os_full }} }},\n"
                    f"      \"metricset\" => {{ \"module\" => \"snmp\" }},\n"
                    f"      \"event\" => {{ \"category\" => \"{table_name.lower()}\" }}\n"
                    f"    }})\n"
                    f"    new_event.set(\"[network][name]\", network_name)\n"
                    f"    new_event.set(\"[host][device_template]\", host_device_template) if host_device_template\n"
                    f"    new_event.set(\"{table_set_path}\", row)\n"
                    f"    new_event_block.call(new_event)\n"
                    f"  end\n"
                    f"  event.remove(\"{table_field_path}\")\n"
                    f"  event.set(\"[event][category]\", \"metrics\")\n"
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
