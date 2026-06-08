#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.conf import settings
import os
import ipaddress
import logging
import json

logger = logging.getLogger(__name__)

# Import Device model for discovery IP address filtering
from .models import Device

# Cache for official profile data to avoid repeated file I/O
_OFFICIAL_PROFILE_CACHE = {}

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
    Get all profiles for a device and return merged OID data.
    Returns a tuple: (profile_ids_tuple, merged_oids_dict)

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
                    f"      \"event\" => {{ \"category\" => \"{table_name.lower()}\" }}\n"
                    f"    }})\n"
                    f"    new_event_block.call(new_event)\n"
                    f"  end\n"
                    f"  event.remove(\"[{table_name}]\")\n"
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
