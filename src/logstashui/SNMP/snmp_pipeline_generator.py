#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Generate Logstash SNMP pipeline fragments (input, filter, output).

Agent mode never embeds secrets: LSCL uses `${KEY}` references and LogstashUI
provisions matching keystore entries on the agent policy. Centralized mode
follows `credential_mode` (KEYSTORE vs PLAINTEXT).

Keystore names:
    snmp_{cred_id}_v1 / snmp_{cred_id}_v2
    snmp_{cred_id}_v3_auth / snmp_{cred_id}_v3_priv
    snmp_es_{conn_id}_api_key / snmp_es_{conn_id}_user / snmp_es_{conn_id}_password
"""

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


# ============================================================================
# Agent-mode keystore helpers
#
# In Agent (LogstashAgent) mode, secrets are never embedded in the generated
# pipeline. Instead the pipeline references Logstash keystore keys (${KEY}) and
# LogstashUI provisions the matching keystore entries on the agent's policy.
# The naming convention (agreed for SNMP) is:
#   SNMP device credentials:
#     snmp_{cred_id}_v1        (v1 community)
#     snmp_{cred_id}_v2        (v2c community)
#     snmp_{cred_id}_v3_auth   (v3 auth password)
#     snmp_{cred_id}_v3_priv   (v3 priv password)
#   Elasticsearch output connection credentials:
#     snmp_es_{conn_id}_api_key
#     snmp_es_{conn_id}_user
#     snmp_es_{conn_id}_password
# ============================================================================


def _uses_keystore(network):
    """Return True when credentials should be `${KEY}` references, not inline secrets.

    Agent mode always uses the keystore. Centralized mode uses KEYSTORE (operator
    runs `logstash-keystore`) or PLAINTEXT (embed secrets in LSCL).
    """
    if getattr(network, 'deployment_mode', 'CENTRALIZED') == 'AGENT':
        return True
    return getattr(network, 'credential_mode', 'KEYSTORE') == 'KEYSTORE'


def _community_key_name(credential):
    """Return the keystore key for a v1/v2c community string (`snmp_{id}_v1` or `_v2`)."""
    suffix = 'v1' if credential.version == '1' else 'v2'
    return f"snmp_{credential.id}_{suffix}"


def _auth_pass_key_name(credential):
    """Return the keystore key for a v3 auth password (`snmp_{id}_v3_auth`)."""
    return f"snmp_{credential.id}_v3_auth"


def _priv_pass_key_name(credential):
    """Return the keystore key for a v3 privacy password (`snmp_{id}_v3_priv`)."""
    return f"snmp_{credential.id}_v3_priv"


def _es_api_key_name(connection):
    """Return the keystore key for an ES API key (`snmp_es_{id}_api_key`)."""
    return f"snmp_es_{connection.id}_api_key"


def _es_user_key_name(connection):
    """Return the keystore key for an ES username (`snmp_es_{id}_user`)."""
    return f"snmp_es_{connection.id}_user"


def _es_password_key_name(connection):
    """Return the keystore key for an ES password (`snmp_es_{id}_password`)."""
    return f"snmp_es_{connection.id}_password"


def _ref(key_name):
    """Format a keystore key name as a Logstash `${KEY}` reference."""
    return "${" + key_name + "}"


def snmp_credential_keystore_entries(credential):
    """Return `{key_name: plaintext}` for secrets actually set on the credential.

    Used by Agent deploy to provision keystore rows.

    Args:
        credential: Credential row, or None.

    Returns:
        Dict of keystore names to decrypted values.
    """
    entries = {}
    if credential is None:
        return entries

    if credential.version == '1':
        community = credential.get_community()
        if community:
            entries[_community_key_name(credential)] = community
    elif credential.version == '2c':
        community = credential.get_community()
        if community:
            entries[_community_key_name(credential)] = community
    elif credential.version == '3':
        if credential.security_level in ['authNoPriv', 'authPriv']:
            auth = credential.get_auth_pass()
            if auth:
                entries[_auth_pass_key_name(credential)] = auth
        if credential.security_level == 'authPriv':
            priv = credential.get_priv_pass()
            if priv:
                entries[_priv_pass_key_name(credential)] = priv
    return entries


def es_connection_keystore_entries(connection):
    """Return `{key_name: plaintext}` for an ES connection's secrets.

    Prefers API key auth; otherwise username/password. Used by Agent deploy for
    pipeline output credentials.

    Args:
        connection: Elasticsearch Connection row, or None.

    Returns:
        Dict of keystore names to decrypted values.
    """
    entries = {}
    if connection is None:
        return entries

    if connection.api_key:
        api_key = connection.get_api_key()
        if api_key:
            entries[_es_api_key_name(connection)] = api_key
    elif connection.username and connection.password:
        entries[_es_user_key_name(connection)] = connection.username
        password = connection.get_password()
        if password:
            entries[_es_password_key_name(connection)] = password
    return entries


def snmp_credential_keystore_key_names(credential):
    """Return keystore key names for a credential without decrypting secrets.

    Names come from id/version/security_level and non-empty encrypted columns.
    Mirrors `snmp_credential_keystore_entries` for check-in scoping.
    """
    names = set()
    if credential is None:
        return names

    if credential.version in ('1', '2c'):
        if credential.community:
            names.add(_community_key_name(credential))
    elif credential.version == '3':
        if credential.security_level in ('authNoPriv', 'authPriv') and credential.auth_pass:
            names.add(_auth_pass_key_name(credential))
        if credential.security_level == 'authPriv' and credential.priv_pass:
            names.add(_priv_pass_key_name(credential))
    return names


def es_connection_keystore_key_names(connection):
    """Return ES keystore key names without decrypting.

    Mirrors `es_connection_keystore_entries` using encrypted columns directly.
    """
    names = set()
    if connection is None:
        return names

    if connection.api_key:
        names.add(_es_api_key_name(connection))
    elif connection.username and connection.password:
        names.add(_es_user_key_name(connection))
        names.add(_es_password_key_name(connection))
    return names


def _normalize_template_name(name: str) -> str:
    """Make a template name safe as an Elasticsearch index/namespace component.

    Strips, lowercases, replaces illegal punctuation, collapses separators, drops
    leading `-_+.`, truncates to 255 bytes, and falls back to `unknown_template`.

    Args:
        name: Raw device template name.

    Returns:
        Normalized slug safe for an ES index name or data-stream namespace.
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
    """Drop normalizers that share operation, target, and params.

    Args:
        normalizers: Normalizer config dicts.

    Returns:
        List of unique normalizers.
    """
    if not normalizers:
        return []
    
    seen = set()
    unique = []

    for normalizer in normalizers:
        normalizer_key = (
            normalizer.get('operation'),
            str(normalizer.get('target', {})),
            str(normalizer.get('params', {}))
        )

        if normalizer_key not in seen:
            seen.add(normalizer_key)
            unique.append(normalizer)
    
    return unique

def _generate_input(input_data, profile_cache=None, template_filter=None):
    """Build SNMP input plugins grouped by device template then credential.

    Each input is enriched with ECS fields from the template (`host.type`,
    `observer.vendor`, `observer.os.full`).

    Args:
        input_data: Dict with network and devices (`v1_v2c` / `v3` maps).
        profile_cache: Optional cache of loaded profile data.
        template_filter: Optional device template ID to include.

    Returns:
        Tuple `(input_components, oid_mappings, all_normalizers)`.
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
                community_value = (
                    _ref(_community_key_name(credential))
                    if _uses_keystore(input_data['network'])
                    else credential.get_community()
                )
                hosts.append({
                    "host": f"udp:{device.hostname or device.ip_address}/{device.port}",
                    "community": community_value,
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

                # Record the raw poll address permanently - the filter will also
                # copy it to [host][ip] or [host][hostname] as appropriate
                add_fields["[host][polled_address]"] = "%{[@metadata][host_address]}"

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
                    "host": f"udp:{device.hostname or device.ip_address}/{device.port}",
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
                use_keystore = _uses_keystore(input_data['network'])
                if credential.security_level in ['authNoPriv', 'authPriv']:
                    config["auth_protocol"] = credential.auth_protocol
                    config["auth_pass"] = (
                        _ref(_auth_pass_key_name(credential))
                        if use_keystore else credential.get_auth_pass()
                    )

                if credential.security_level == 'authPriv':
                    config["priv_protocol"] = credential.priv_protocol
                    config["priv_pass"] = (
                        _ref(_priv_pass_key_name(credential))
                        if use_keystore else credential.get_priv_pass()
                    )

                # Add ECS field enrichment from device template
                add_fields = {}

                # Expose the SNMP plugin's host address as a plain [host] field so
                # the downstream if/else filter can rename it to [host][ip] or [host][hostname]
                add_fields["[host][polled_address]"] = "%{[@metadata][host_address]}"

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
    """Build SNMP inputs that scan the network range using System profile OIDs.

    Existing device addresses are excluded from the scan list.

    Args:
        network: Network row.

    Returns:
        Tuple `(input_components, oid_mappings)`.
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
            host_config["community"] = (
                _ref(_community_key_name(credential))
                if _uses_keystore(network) else credential.get_community()
            )
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

        use_keystore = _uses_keystore(network)
        if credential.security_level in ['authNoPriv', 'authPriv']:
            config["auth_protocol"] = credential.auth_protocol
            config["auth_pass"] = (
                _ref(_auth_pass_key_name(credential))
                if use_keystore else credential.get_auth_pass()
            )

        if credential.security_level == 'authPriv':
            config["priv_protocol"] = credential.priv_protocol
            config["priv_pass"] = (
                _ref(_priv_pass_key_name(credential))
                if use_keystore else credential.get_priv_pass()
            )

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
    """Build discovery-pipeline filters, tagging `event.category` as discovery.

    Args:
        oid_mappings: Dict with `get`, `walk`, and `table` OID maps.
        network: Network row (name used in filters).

    Returns:
        List of filter component dicts.
    """
    # Build rename mappings for get OIDs
    get_renames = {value: _format_field_name(key) for key, value in oid_mappings['get'].items()}

    filter_components = [
        _generate_snmp_error_cleanup_filter(),
        {
            "id": "filter_mutate_discovery_1",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "rename": {
                              "host": "[host][ip]"
                          } | get_renames
            }
        },
        {
            "id": "filter_mutate_discovery_hostname",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "copy": {
                    "[host][ip]": "[host][hostname]"
                }
            }
        },
        {
            "id": "comp_1782149786510",
            "type": "filter",
            "plugin": "dns",
            "config": {
                "action": "replace",
                "reverse": ["[host][hostname]"]
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


def _generate_device_enrichment_filters(input_data):
    """Enrich poll events with per-device name, location, and metadata.

    A translate maps `[host][polled_address]` to `[@metadata][device_enrichment]`;
    a ruby filter copies present sub-keys to `[host][name]`, `[host][location]`,
    and `[host][metadata]`. The poll key matches `%{[@metadata][host_address]}`.

    Args:
        input_data: Dict whose `devices` maps hold Device rows.

    Returns:
        List of filter component dicts (possibly empty).
    """
    # Merge v1/v2c and v3 into a single address → device map.
    # Use hostname-first to match what the SNMP input's host field uses.
    all_devices = {}
    for device in (
        list(input_data['devices']['v1_v2c'].values())
        + list(input_data['devices']['v3'].values())
    ):
        address = device.hostname or device.ip_address
        if address:
            all_devices[address] = device

    filters = []

    # ── Combined enrichment translate ─────────────────────────────────────────
    # Build one dictionary entry per device containing all enrichment sub-keys
    # (name, location, metadata).  Writing to [@metadata][device_enrichment]
    # keeps the payload completely out of the [host] namespace until we
    # deliberately copy each sub-field in the ruby block below.
    enrichment_dict = {}

    for address, device in all_devices.items():
        entry = {}

        # name — always present
        if device.name:
            entry['name'] = device.name

        # location — only when at least one location field is set
        loc = {}
        if device.site:
            loc['site'] = device.site
        if device.building:
            loc['building'] = device.building
        if device.room:
            loc['room'] = device.room
        if device.latitude is not None and device.longitude is not None:
            loc['geo'] = {
                'lat': str(device.latitude),
                'lon': str(device.longitude),
            }
        if loc:
            entry['location'] = loc

        # metadata — user-supplied KV pairs; all values coerced to strings so
        # the serialiser produces valid Logstash hash syntax
        if device.metadata:
            entry['metadata'] = {str(k): str(v) for k, v in device.metadata.items()}

        if entry:
            enrichment_dict[address] = entry

    if enrichment_dict:
        filters.append({
            "id": "filter_translate_device_enrichment",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "source": "[host][polled_address]",
                "destination": "[@metadata][device_enrichment]",
                "dictionary": enrichment_dict
            }
        })

        # ── Scatter enrichment sub-fields to their final [host] destinations ──
        # mutate copy is pure-Java (no JRuby overhead) and silently skips any
        # source path that doesn't exist, so no conditional guards are needed.
        filters.append({
            "id": "filter_mutate_device_enrichment_copy",
            "type": "filter",
            "plugin": "mutate",
            "config": {
                "copy": {
                    "[@metadata][device_enrichment][name]":     "[host][name]",
                    "[@metadata][device_enrichment][location]": "[host][location]",
                    "[@metadata][device_enrichment][metadata]": "[host][metadata]",
                }
            }
        })

    return filters


def _generate_filters(oid_mappings, network, normalizers=None, input_data=None):
    """Build poll-pipeline filters from profile OID mappings and normalizers.

    Args:
        oid_mappings: Dict with `get`, `walk`, and `table` OID maps.
        network: Network row.
        normalizers: Normalizer configs from the device's profiles.
        input_data: Optional devices dict; when set, enrichment filters are appended.

    Returns:
        List of filter component dicts.
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
        _generate_snmp_error_cleanup_filter(),
        {
            "id": "condition-1782151148927",
            "type": "filter",
            "plugin": "if",
            "config": {
                "condition": r"[host][polled_address] =~ /^\d+\.\d+\.\d+\.\d+$/ or [host][polled_address] =~ /^[0-9a-fA-F]+:[0-9a-fA-F:]*$/",
                "plugins": [
                    {
                        "id": "plugin-1782151166081",
                        "type": "filter",
                        "plugin": "mutate",
                        "config": {
                            "copy": {
                                "[host][polled_address]": "[host][ip]"
                            }
                        }
                    }
                ],
                "else": {
                    "plugins": [
                        {
                            "id": "plugin-1782151183285",
                            "type": "filter",
                            "plugin": "mutate",
                            "config": {
                                "copy": {
                                    "[host][polled_address]": "[host][hostname]"
                                }
                            }
                        }
                    ]
                }
            }
        },
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
                    "[metricset][module]": "system",
                    "[tsds][category]": "metrics",
                    "[tsds][index]": "metrics"
                }
            }
        }
    ]

    # Apply normalizers from profiles
    average_normalizers = []
    if normalizers:
        get_normalizers = [n for n in normalizers if n.get('target', {}).get('scope') == 'get']
        normalizer_filters = _apply_normalizers(get_normalizers)
        filter_components.extend(normalizer_filters)
        average_normalizers = [n for n in normalizers if n.get('operation') == 'average']

    # Generate table-split filters, injecting average normalizer logic where applicable.
    filter_components.extend(_generate_table_split_filters(oid_mappings, average_normalizers))

    # Apply table-scope normalizers AFTER table splitters so they run on the
    # already-split row events (which have columns as top-level fields).
    # Average normalizers are handled inside the split block and are excluded here.
    if normalizers:
        table_normalizers = [
            n for n in normalizers
            if n.get('target', {}).get('scope') == 'table' and n.get('operation') != 'average'
        ]
        table_normalizer_filters = _apply_normalizers(table_normalizers)
        filter_components.extend(table_normalizer_filters)

    # Append per-device location and metadata enrichment translate blocks.
    if input_data is not None:
        filter_components.extend(_generate_device_enrichment_filters(input_data))

    return filter_components


def _generate_output(network_db_object, snmp_type="polling", device_template=None):
    """Build the Elasticsearch output with data-stream settings.

    Args:
        network_db_object: Network row.
        snmp_type: ``discovery``, ``traps``, or ``polling``.
        device_template: Optional template. When
            `namespace_from_device_template` is True, the normalized template name
            becomes the data-stream namespace.

    Returns:
        List of output component dicts.
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

    # Add authentication. In Agent mode, reference keystore keys instead of
    # embedding secrets; LogstashUI provisions the matching keystore entries.
    if _uses_keystore(network_db_object):
        if connection.api_key:
            config["api_key"] = _ref(_es_api_key_name(connection))
        elif connection.username and connection.password:
            config["user"] = _ref(_es_user_key_name(connection))
            config["password"] = _ref(_es_password_key_name(connection))
    else:
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
    """Load and merge a device's template profiles.

    Args:
        device: Device with prefetched `device_template.profiles`.
        profile_cache: Optional cache of loaded profile JSON.

    Returns:
        Tuple `(profile_ids_tuple, merged_oids_dict, normalizers_list)`.
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
        
        # Collect normalizers from this profile.
        # FIX (MA 2026-06-19): official profiles carry normalizers inline in profile_data (loaded
        # from disk JSON), but USER-authored profiles store them in the separate `normalizers` model
        # column -> they were being dropped from generated pipelines. Fall back to the model field.
        prof_norms = profile_data.get('normalizers')
        if not prof_norms:
            prof_norms = getattr(profile, 'normalizers', None) or []
        if isinstance(prof_norms, list):
            all_normalizers.extend(prof_norms)

    return (profile_ids, merged_oids, all_normalizers)



def _load_system_profile_oids():
    """Load System profile OIDs used by discovery.

    Returns:
        Dict with `get`, `walk`, and `table` keys.
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
    """List IPs in the network CIDR, excluding addresses already assigned to devices.

    Args:
        network: Network row with `network_range`.

    Returns:
        List of IP strings to scan.
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
    """Convert dotted field names to Logstash bracket notation.

    Names already wrapped in `[...]` are left unchanged. `system.cpu` becomes
    `[system][cpu]`.

    Args:
        field_name: Raw field name.

    Returns:
        Field name suitable for Logstash filter config.
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
    """Return a Ruby hash entry for a possibly dotted table name.

    Examples:
        _ruby_table_nested_entry("ifTable", "row")
        # '"ifTable" => row'
        _ruby_table_nested_entry("component.fan", "row")
        # '"component" => { "fan" => row }'
    """
    parts = table_name.split('.')

    def build(parts, val):
        if len(parts) == 1:
            return f'"{parts[0]}" => {val}'
        return f'"{parts[0]}" => {{ {build(parts[1:], val)} }}'

    return build(parts, value_expr)


def _ruby_row_rename_statements(columns):
    """Emit Ruby that renames OID keys to column names, expanding dotted paths.

    Parent hashes are initialized with `||= {}` once even when many columns share
    a parent.

    Args:
        columns: Mapping of column name → OID.

    Returns:
        4-space-indented Ruby statements.
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


def _ruby_row_value_expr(table_name, field):
    """Return a Ruby expression that reads a (possibly nested) renamed row column.

    `table_name='component.cpu'` and `field='component.cpu.load_pct'` yield
    `row["load_pct"]`.
    """
    prefix = table_name + '.'
    col_path = field[len(prefix):] if field.startswith(prefix) else field
    parts = [p for p in col_path.split('.') if p]
    if not parts:
        return 'nil'
    if len(parts) == 1:
        return f'row["{parts[0]}"]'
    keys = ', '.join(f'"{p}"' for p in parts)
    return f'row.dig({keys})'


_KEEP_WHEN_COLUMN_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_KEEP_WHEN_VALUE_RE = re.compile(r'^[0-9A-Za-z._-]+$')


def _ruby_keep_when_statements(table_data):
    """Emit Ruby that keeps table rows whose discriminator column matches.

    ENTITY-SENSOR-MIB mixes sensor kinds; Cisco-schema profiles split rows onto
    `component.fan` vs `component.sensor` by `entPhySensorType`. The discriminator
    is polled then dropped. Invalid tokens are ignored so profile JSON cannot
    inject Ruby.

    `table_data['keep_when']` shape: `{"column": "type", "equals": ["10"]}`.
    """
    if not isinstance(table_data, dict):
        return ''
    keep_when = table_data.get('keep_when')
    if not isinstance(keep_when, dict):
        return ''
    column = keep_when.get('column')
    if not column or not _KEEP_WHEN_COLUMN_RE.match(str(column)):
        return ''
    equals = keep_when.get('equals')
    if equals is None:
        return ''
    if not isinstance(equals, list):
        equals = [equals]
    values = [str(v) for v in equals if _KEEP_WHEN_VALUE_RE.match(str(v))]
    if not values:
        return ''
    quoted = ', '.join(f'"{v}"' for v in values)
    return (
        f'    _keep_v = row.delete("{column}")\n'
        f'    next unless [{quoted}].include?(_keep_v.to_s)'
    )


def _generate_table_split_filters(oid_mappings, average_normalizers=None):
    """Emit Ruby filters that split SNMP tables into per-row events.

    Each table becomes a ruby filter that renames OID keys, optionally applies
    `keep_when`, clones a LogStash::Event per row, and removes the raw table from
    the original event. Average normalizers accumulate inside that loop and write
    scalars onto the metrics doc after the table array is removed.

    Args:
        oid_mappings: OID maps; only `table` is used.
        average_normalizers: Optional average normalizer configs.

    Returns:
        List of ruby filter dicts, one per table with columns.
    """
    special_filters = []
    average_normalizers = average_normalizers or []

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

                # Collect average normalizers that target columns in this table.
                # Table names may be dotted (e.g. "component.cpu"), so match by checking
                # that the target field starts with the full table name followed by a dot.
                table_averages = [
                    n for n in average_normalizers
                    if n.get('target', {}).get('field', '').startswith(table_name + '.')
                ]

                # Build pre-loop accumulator declarations for each average normalizer.
                avg_pre_loop = _ruby_avg_pre_loop(table_averages)

                # Build in-loop accumulation statements (run after rename_statements).
                # Pass table_name so the column path is stripped correctly for dotted
                # table names (e.g. "component.cpu") regardless of whether the
                # normalizer stores target.table.
                avg_in_loop = _ruby_avg_in_loop(table_averages, table_name)

                # Build post-loop event.set calls (written after event.remove so the
                # raw table array is gone and the namespace is free for scalar fields).
                avg_post_loop = _ruby_avg_post_loop(table_averages)
                keep_when_statements = _ruby_keep_when_statements(table_data)

                # Build the Ruby code for this table
                ruby_code = (
                    f"rows = event.get(\"{table_field_path}\")\n"
                    f"if rows.is_a?(Array)\n"
                    f"  host_name = event.get(\"[host][name]\")\n"
                    f"  host_hostname = event.get(\"[host][hostname]\")\n"
                    f"  host_sysname = event.get(\"[host][sysname]\")\n"
                    f"  host_polled_address = event.get(\"[host][polled_address]\")\n"
                    f"  host_type = event.get(\"[host][type]\")\n"
                    f"  host_device_template = event.get(\"[host][device_template]\")\n"
                    f"  observer_vendor = event.get(\"[observer][vendor]\")\n"
                    f"  observer_os_full = event.get(\"[observer][os][full]\")\n"
                    f"  network_name = event.get(\"[network][name]\")\n"
                    f"  timestamp = event.get(\"@timestamp\")\n"
                    f"  _row_counter = 0\n"
                    + (f"{avg_pre_loop}\n" if avg_pre_loop else "")
                    + f"  rows.each do |row|\n"
                    f"    next unless row.is_a?(Hash)\n"
                    f"{rename_statements}\n"
                    + (f"{keep_when_statements}\n" if keep_when_statements else "")
                    + (f"{avg_in_loop}\n" if avg_in_loop else "")
                    + f"    new_event = LogStash::Event.new({{\n"
                    f"      \"@timestamp\" => timestamp,\n"
                    f"      \"host\" => {{ \"name\" => host_name, \"hostname\" => host_hostname, \"type\" => host_type }},\n"
                    f"      \"observer\" => {{ \"vendor\" => observer_vendor, \"os\" => {{ \"full\" => observer_os_full }} }},\n"
                    f"      \"metricset\" => {{ \"module\" => \"snmp\" }},\n"
                    f"      \"event\" => {{ \"category\" => \"{table_name.lower()}\" }}\n"
                    f"    }})\n"
                    f"    new_event.set(\"[network][name]\", network_name)\n"
                    f"    new_event.set(\"[host][device_template]\", host_device_template) if host_device_template\n"
                    f"    new_event.set(\"[host][sysname]\", host_sysname) if host_sysname\n"
                    f"    new_event.set(\"[host][polled_address]\", host_polled_address) if host_polled_address\n"
                    f"    new_event.set(\"{table_set_path}\", row)\n"
                    f"    new_event.set(\"[tsds][category]\", \"{table_name.lower()}\")\n"
                    f"    new_event.set(\"[tsds][index]\", _row_counter.to_s)\n"
                    f"    _row_counter += 1\n"
                    f"    new_event_block.call(new_event)\n"
                    f"  end\n"
                    f"  event.remove(\"{table_field_path}\")\n"
                    + (f"{avg_post_loop}\n" if avg_post_loop else "")
                    + f"  event.set(\"[event][category]\", \"metrics\")\n"
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


def _ruby_avg_pre_loop(table_averages):
    """Declare Ruby sum/count locals for average normalizers before the row loop.

    Args:
        table_averages: Average normalizer configs for this table.

    Returns:
        Indented Ruby, or empty string when there are no averages.
    """
    if not table_averages:
        return ""
    lines = []
    for normalizer in table_averages:
        var = _avg_var_name(normalizer)
        lines.append(f"  {var}_sum = 0.0")
        lines.append(f"  {var}_count = 0")
    return "\n".join(lines)


def _ruby_avg_in_loop(table_averages, table_name):
    """Accumulate average inputs inside the row loop after column rename.

    The column path is `target.field` with the `table_name` prefix stripped, so
    dotted tables such as `component.cpu` resolve to `row["load_pct"]`.

    Args:
        table_averages: Average normalizer configs for this table.
        table_name: Table key from `oid_mappings` (may contain dots).

    Returns:
        Indented Ruby, or empty string when there are no averages.
    """
    if not table_averages:
        return ""
    lines = []
    for normalizer in table_averages:
        target_field = normalizer.get('target', {}).get('field', '')
        row_expr = _ruby_row_value_expr(table_name, target_field)
        var = _avg_var_name(normalizer)
        # Float() accepts Integer 0 and numeric strings ("0") that the SNMP plugin
        # sometimes emits. is_a?(Numeric) skipped those, so the metrics doc never
        # received system.cpu.total.norm.pct even when per-core rows existed.
        # nil / non-numeric still raise and are ignored, so missing columns
        # are not counted as zero.
        lines.append(f"    _avg_v = {row_expr}")
        lines.append(f"    begin")
        lines.append(f"      {var}_sum += Float(_avg_v)")
        lines.append(f"      {var}_count += 1")
        lines.append(f"    rescue ArgumentError, TypeError")
        lines.append(f"    end")
    return "\n".join(lines)


def _ruby_avg_post_loop(table_averages):
    """Write computed averages onto the original event after the table is removed.

    Args:
        table_averages: Average normalizer configs for this table.

    Returns:
        Indented Ruby, or empty string when there are no averages.
    """
    if not table_averages:
        return ""
    lines = []
    for normalizer in table_averages:
        params = normalizer.get('params', {})
        output_field = params.get('output_field', '').strip()
        if not output_field:
            continue
        output_path = _format_field_name(output_field)
        var = _avg_var_name(normalizer)
        multiply_value = params.get('multiply_value')
        if multiply_value is not None and float(multiply_value) != 1.0:
            lines.append(f"  event.set(\"{output_path}\", ({var}_sum / {var}_count) * {multiply_value}) if {var}_count > 0")
        else:
            lines.append(f"  event.set(\"{output_path}\", {var}_sum / {var}_count) if {var}_count > 0")
    return "\n".join(lines)


def _avg_var_name(normalizer):
    """Build a safe Ruby local prefix from the normalizer output field.

    `interface.avg_in_octets` becomes `avg_interface_avg_in_octets`.
    """
    output_field = normalizer.get('params', {}).get('output_field', '').strip()
    if output_field:
        sanitized = output_field.replace('.', '_').replace('-', '_')
        return f"avg_{sanitized}"
    # Fallback using target field if output_field is somehow missing
    target_field = normalizer.get('target', {}).get('field', 'unknown').replace('.', '_')
    return f"avg_{target_field}"


def _generate_snmp_error_cleanup_filter():
    """Strip SNMP error strings so they never reach typed Elasticsearch fields.

    The input plugin emits values like ``error: no such instance currently exists
    at this OID``. Those strings would fail mapping (long/float). The helper is
    defined in `init` to avoid per-event method-redefinition warnings. Events that
    lost a field are tagged `_snmp_oid_error`.

    Returns:
        Logstash ruby filter component dict.
    """
    ruby_init = (
        "def snmp_remove_errors(obj)\n"
        "  found = false\n"
        "  case obj\n"
        "  when Hash\n"
        "    obj.keys.each do |k|\n"
        "      v = obj[k]\n"
        "      if v.is_a?(String) && v =~ /\\Aerror: (no such instance|no such object|end of mib view)/i\n"
        "        obj.delete(k)\n"
        "        found = true\n"
        "      elsif v.is_a?(Hash) || v.is_a?(Array)\n"
        "        found = true if snmp_remove_errors(v)\n"
        "      end\n"
        "    end\n"
        "  when Array\n"
        "    obj.each { |item| found = true if snmp_remove_errors(item) }\n"
        "  end\n"
        "  found\n"
        "end"
    )
    ruby_code = (
        "had_errors = false\n"
        "event.to_hash.each do |k, v|\n"
        "  next if k.start_with?(\"@\")\n"
        "  if v.is_a?(String) && v =~ /\\Aerror: (no such instance|no such object|end of mib view)/i\n"
        "    event.remove(k)\n"
        "    had_errors = true\n"
        "  elsif snmp_remove_errors(v)\n"
        "    event.set(k, v)\n"
        "    had_errors = true\n"
        "  end\n"
        "end\n"
        "event.tag(\"_snmp_oid_error\") if had_errors"
    )
    return {
        "id": "snmp_error_cleanup",
        "type": "filter",
        "plugin": "ruby",
        "config": {
            "init": ruby_init,
            "code": ruby_code
        }
    }
