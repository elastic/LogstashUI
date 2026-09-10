#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""REST API views for SNMP resources.

Devices
-------
GET    /api/snmp/devices/           device_list     (any authenticated user)
POST   /api/snmp/devices/           device_list     (admin)
GET    /api/snmp/devices/{id}/      device_detail   (any authenticated user)
PUT    /api/snmp/devices/{id}/      device_detail   (admin)
DELETE /api/snmp/devices/{id}/      device_detail   (admin)

Credentials
-----------
GET    /api/snmp/credentials/         credential_list    (any authenticated user)
POST   /api/snmp/credentials/         credential_list    (admin)
GET    /api/snmp/credentials/{id}/    credential_detail  (any authenticated user)
PUT    /api/snmp/credentials/{id}/    credential_detail  (admin)
DELETE /api/snmp/credentials/{id}/    credential_detail  (admin)

Networks
--------
GET    /api/snmp/networks/            network_list    (any authenticated user)
POST   /api/snmp/networks/            network_list    (admin)
GET    /api/snmp/networks/{id}/       network_detail  (any authenticated user)
PUT    /api/snmp/networks/{id}/       network_detail  (admin)
DELETE /api/snmp/networks/{id}/       network_detail  (admin)

Profiles (OID device profiles)
-------------------------------
GET    /api/snmp/profiles/            profile_list    (any authenticated user)
POST   /api/snmp/profiles/            profile_list    (admin)
GET    /api/snmp/profiles/{id}/       profile_detail  (any authenticated user)
PUT    /api/snmp/profiles/{id}/       profile_detail  (admin)
DELETE /api/snmp/profiles/{id}/       profile_detail  (admin)

Device Templates
----------------
GET    /api/snmp/templates/           template_list    (any authenticated user)
POST   /api/snmp/templates/           template_list    (admin)
GET    /api/snmp/templates/{id}/      template_detail  (any authenticated user)
PUT    /api/snmp/templates/{id}/      template_detail  (admin)
DELETE /api/snmp/templates/{id}/      template_detail  (admin)
"""

import json
import logging
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from SNMP.models import Credential, Device, DeviceTemplate, Network, Profile, SNMPDeploymentState
from Common.elastic_utils import get_elastic_connection
from Common.formatters import _sanitize_pipeline_name_component
from Common.validators import validate_namespace

from API.auth import api_require_auth, api_require_admin, parse_request_body

logger = logging.getLogger(__name__)

_VALID_SORT_FIELDS = frozenset([
    'name', '-name',
    'ip_address', '-ip_address',
    'hostname', '-hostname',
    'created_at', '-created_at',
])


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _device_list_data(device):
    """Serialize a Device for the list response (no metadata/location coords)."""
    return {
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
        'site': device.site,
        'building': device.building,
        'room': device.room,
        'created_at': device.created_at.isoformat(),
    }


def _device_detail_data(device):
    """Serialize a Device for a single-item response (full fields)."""
    return {
        'id': device.id,
        'name': device.name,
        'ip_address': device.ip_address,
        'hostname': device.hostname,
        'port': device.port,
        'retries': device.retries,
        'timeout': device.timeout,
        'credential_id': device.credential_id,
        'network_id': device.network_id,
        'device_template_id': device.device_template_id,
        'site': device.site,
        'building': device.building,
        'room': device.room,
        'latitude': float(device.latitude) if device.latitude is not None else None,
        'longitude': float(device.longitude) if device.longitude is not None else None,
        'metadata': device.metadata,
        'created_at': device.created_at.isoformat(),
        'updated_at': device.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Request parsing helpers
# ---------------------------------------------------------------------------

def _parse_device_fields(data, device):
    """Apply a parsed JSON body onto a Device instance.

    Mutates ``device`` in place. Raises ``ValueError`` for bad numeric inputs.

    Args:
        data: dict from ``parse_request_body``.
        device: ``Device`` instance to update (may be unsaved).
    """
    if 'name' in data:
        device.name = (data['name'] or '').strip() or device.name

    device.ip_address = data.get('ip_address') or None
    device.hostname = data.get('hostname') or None

    if 'port' in data and data['port'] is not None:
        device.port = int(data['port'])
    if 'retries' in data and data['retries'] is not None:
        device.retries = int(data['retries'])
    if 'timeout' in data and data['timeout'] is not None:
        device.timeout = int(data['timeout'])

    # FK ids — explicit None clears the relationship
    if 'credential' in data:
        device.credential_id = data['credential']
    if 'network' in data:
        device.network_id = data['network']
    if 'device_template' in data:
        device.device_template_id = data['device_template']

    # Location
    if 'site' in data:
        device.site = data['site'] or None
    if 'building' in data:
        device.building = data['building'] or None
    if 'room' in data:
        device.room = data['room'] or None

    lat = data.get('latitude')
    lon = data.get('longitude')
    try:
        device.latitude = Decimal(str(round(float(lat), 6))) if lat is not None else None
        device.longitude = Decimal(str(round(float(lon), 6))) if lon is not None else None
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f'Invalid lat/lon value: {exc}') from exc

    # Metadata
    raw_meta = data.get('metadata')
    if raw_meta is not None:
        if isinstance(raw_meta, str):
            try:
                device.metadata = json.loads(raw_meta)
            except (json.JSONDecodeError, ValueError):
                device.metadata = {}
        elif isinstance(raw_meta, dict):
            device.metadata = raw_meta
        else:
            device.metadata = {}


# ---------------------------------------------------------------------------
# /api/snmp/devices/  — list + create
# ---------------------------------------------------------------------------

@csrf_exempt
def device_list(request):
    """List all SNMP devices or create a new one.

    GET  /api/snmp/devices/
        Paginated, filterable list. Any authenticated user.

    POST /api/snmp/devices/
        Create a device from a JSON body. Admin only.
        Calls ``SNMPDeploymentState.mark_config_changed()`` on success.
    """
    if request.method == 'GET':
        return _list_devices(request)
    if request.method == 'POST':
        return _create_device(request)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _list_devices(request):
    page = max(1, int(request.GET.get('page', 1)))
    page_size = max(1, min(200, int(request.GET.get('page_size', 25))))
    search = request.GET.get('search', '').strip()
    network_filter = request.GET.get('network', '').strip()
    sort_by = request.GET.get('sort_by', '-created_at')

    if sort_by not in _VALID_SORT_FIELDS:
        sort_by = '-created_at'

    qs = Device.objects.select_related('credential', 'network', 'device_template').only(
        'id', 'name', 'ip_address', 'hostname', 'port', 'retries', 'timeout', 'created_at',
        'site', 'building', 'room',
        'credential__id', 'credential__name',
        'network__id', 'network__name', 'network__deployment_mode',
        'device_template__id', 'device_template__name',
    )

    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(ip_address__icontains=search) |
            Q(hostname__icontains=search)
        )
    if network_filter:
        qs = qs.filter(network_id=network_filter)

    qs = qs.order_by(sort_by)

    total = qs.count()
    offset = (page - 1) * page_size
    page_qs = list(qs[offset:offset + page_size + 1])
    has_next = len(page_qs) > page_size
    devices_page = page_qs[:page_size]
    total_pages = max(1, (total + page_size - 1) // page_size)

    return JsonResponse({
        'devices': [_device_list_data(d) for d in devices_page],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'has_next': has_next,
        'has_previous': page > 1,
    })


@api_require_admin
def _create_device(request):
    data = parse_request_body(request)

    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'name is required.'}, status=400)

    device = Device(
        port=161,
        retries=2,
        timeout=1000,
        metadata={},
    )
    device.name = name

    try:
        _parse_device_fields(data, device)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': f'Invalid numeric field: {exc}'}, status=400)

    try:
        device.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except IntegrityError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=409)
    except Exception as exc:
        logger.error("API create device: %s", exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    SNMPDeploymentState.mark_config_changed()
    logger.info("API: device '%s' (ID: %s) created by %s.", name, device.id, request.user.username)
    return JsonResponse({
        'success': True,
        'id': device.id,
        'message': 'Device created successfully.',
    }, status=201)


# ---------------------------------------------------------------------------
# /api/snmp/devices/{id}/  — read, update, delete
# ---------------------------------------------------------------------------

@csrf_exempt
def device_detail(request, device_id):
    """Read, update, or delete a single SNMP device.

    GET    /api/snmp/devices/{id}/   any authenticated user
    PUT    /api/snmp/devices/{id}/   admin only
    DELETE /api/snmp/devices/{id}/   admin only
    """
    if request.method == 'GET':
        return _get_device(request, device_id)
    if request.method == 'PUT':
        return _update_device(request, device_id)
    if request.method == 'DELETE':
        return _delete_device(request, device_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _get_device(request, device_id):
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device not found.'}, status=404)
    return JsonResponse({'success': True, 'device': _device_detail_data(device)})


@api_require_admin
def _update_device(request, device_id):
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device not found.'}, status=404)

    data = parse_request_body(request)

    try:
        _parse_device_fields(data, device)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': f'Invalid numeric field: {exc}'}, status=400)

    try:
        device.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except IntegrityError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=409)
    except Exception as exc:
        logger.error("API update device %s: %s", device_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    SNMPDeploymentState.mark_config_changed()
    logger.info("API: device %s updated by %s.", device_id, request.user.username)
    return JsonResponse({
        'success': True,
        'id': device.id,
        'message': 'Device updated successfully.',
    })


@api_require_admin
def _delete_device(request, device_id):
    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device not found.'}, status=404)

    name = device.name
    device.delete()
    SNMPDeploymentState.mark_config_changed()
    logger.warning("API: device '%s' (ID: %s) deleted by %s.", name, device_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Device '{name}' deleted."})


# ===========================================================================
# CREDENTIALS
# ===========================================================================

def _credential_safe_data(cred):
    """Return a credential dict with secrets masked."""
    data = {
        'id': cred.id,
        'name': cred.name,
        'description': cred.description,
        'version': cred.version,
        'created_at': cred.created_at.isoformat(),
        'updated_at': cred.updated_at.isoformat(),
    }
    if cred.version in ('1', '2c'):
        data['has_community'] = bool(cred.community)
        data['community'] = '***' if cred.community else ''
    else:
        data['security_name'] = cred.security_name or ''
        data['security_level'] = cred.security_level or ''
        data['auth_protocol'] = cred.auth_protocol or ''
        data['priv_protocol'] = cred.priv_protocol or ''
        data['has_auth_pass'] = bool(cred.auth_pass)
        data['has_priv_pass'] = bool(cred.priv_pass)
        data['auth_pass'] = '***' if cred.auth_pass else ''
        data['priv_pass'] = '***' if cred.priv_pass else ''
    return data


def _apply_credential_fields(data, cred, is_update=False):
    """Apply JSON body fields to a Credential instance.

    For updates, empty strings for secret fields keep the existing encrypted value.
    """
    if 'name' in data:
        cred.name = (data['name'] or '').strip()
    if 'description' in data:
        cred.description = data.get('description', '') or ''
    if 'version' in data:
        cred.version = data['version']

    version = cred.version
    # Always clear version-specific fields before re-applying (mirrors UI behaviour)
    cred.community = ''
    cred.security_name = ''
    cred.security_level = ''
    cred.auth_protocol = ''
    cred.priv_protocol = ''
    if not is_update:
        cred.auth_pass = ''
        cred.priv_pass = ''

    if version in ('1', '2c'):
        cred.community = data.get('community', 'public') or 'public'
    elif version == '3':
        cred.security_name = data.get('security_name', '') or ''
        cred.security_level = data.get('security_level', '') or ''
        if cred.security_level in ('authNoPriv', 'authPriv'):
            cred.auth_protocol = data.get('auth_protocol', '') or ''
            ap = data.get('auth_pass', '')
            if ap:  # empty string on update = keep existing
                cred.auth_pass = ap
        if cred.security_level == 'authPriv':
            cred.priv_protocol = data.get('priv_protocol', '') or ''
            pp = data.get('priv_pass', '')
            if pp:
                cred.priv_pass = pp


@csrf_exempt
def credential_list(request):
    """List all credentials or create a new one."""
    if request.method == 'GET':
        return _list_credentials(request)
    if request.method == 'POST':
        return _create_credential(request)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _list_credentials(request):
    from django.db.models import Count
    qs = Credential.objects.annotate(device_count=Count('devices')).order_by('name')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))

    version_filter = request.GET.get('version', '').strip()
    if version_filter:
        qs = qs.filter(version=version_filter)

    items = []
    for cred in qs:
        items.append({
            'id': cred.id,
            'name': cred.name,
            'description': cred.description,
            'version': cred.version,
            'security_level': cred.security_level or None,
            'device_count': cred.device_count,
            'created_at': cred.created_at.isoformat(),
        })
    return JsonResponse({'credentials': items, 'total': len(items)})


@api_require_admin
def _create_credential(request):
    data = parse_request_body(request)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'name is required.'}, status=400)
    version = (data.get('version') or '').strip()
    if version not in ('1', '2c', '3'):
        return JsonResponse({'success': False, 'error': "version must be '1', '2c', or '3'."}, status=400)

    cred = Credential(name=name, version=version)
    _apply_credential_fields(data, cred, is_update=False)
    try:
        cred.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except Exception as exc:
        logger.error("API create credential: %s", exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    SNMPDeploymentState.mark_config_changed()
    logger.info("API: credential '%s' (id=%s) created by %s.", name, cred.id, request.user.username)
    return JsonResponse({'success': True, 'id': cred.id, 'message': 'Credential created successfully.'}, status=201)


@csrf_exempt
def credential_detail(request, credential_id):
    """Read, update, or delete a single credential."""
    if request.method == 'GET':
        return _get_credential(request, credential_id)
    if request.method == 'PUT':
        return _update_credential(request, credential_id)
    if request.method == 'DELETE':
        return _delete_credential(request, credential_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _get_credential(request, credential_id):
    try:
        cred = Credential.objects.get(pk=credential_id)
    except Credential.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Credential not found.'}, status=404)
    return JsonResponse({'success': True, 'credential': _credential_safe_data(cred)})


@api_require_admin
def _update_credential(request, credential_id):
    try:
        cred = Credential.objects.get(pk=credential_id)
    except Credential.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Credential not found.'}, status=404)

    data = parse_request_body(request)
    _apply_credential_fields(data, cred, is_update=True)
    try:
        cred.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except Exception as exc:
        logger.error("API update credential %s: %s", credential_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    SNMPDeploymentState.mark_config_changed()
    logger.info("API: credential %s updated by %s.", credential_id, request.user.username)
    return JsonResponse({'success': True, 'id': cred.id, 'message': 'Credential updated successfully.'})


@api_require_admin
def _delete_credential(request, credential_id):
    try:
        cred = Credential.objects.get(pk=credential_id)
    except Credential.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Credential not found.'}, status=404)
    name = cred.name
    cred.delete()
    SNMPDeploymentState.mark_config_changed()
    logger.warning("API: credential '%s' (id=%s) deleted by %s.", name, credential_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Credential '{name}' deleted."})


# ===========================================================================
# NETWORKS
# ===========================================================================

def _network_data(net, device_count=None):
    return {
        'id': net.id,
        'name': net.name,
        'network_range': net.network_range,
        'deployment_mode': net.deployment_mode,
        'credential_mode': net.credential_mode,
        'connection_id': net.connection_id,
        'connection_name': net.connection.name if net.connection else None,
        'agent_connection_id': net.agent_connection_id,
        'agent_connection_name': net.agent_connection.name if net.agent_connection else None,
        'discovery_credential_id': net.discovery_credential_id,
        'credential_id': net.credential_id,
        'discovery_enabled': net.discovery_enabled,
        'traps_enabled': net.traps_enabled,
        'interval': net.interval,
        'namespace': net.namespace,
        'namespace_from_device_template': net.namespace_from_device_template,
        'device_count': device_count,
        'created_at': net.created_at.isoformat(),
        'updated_at': net.updated_at.isoformat(),
    }


def _validate_network_cidr(network_range):
    """Return (ok, error_str). Rejects prefixes larger than /20."""
    import ipaddress as _ip
    try:
        net = _ip.ip_network(network_range or '', strict=False)
        if net.prefixlen < 20:
            return False, (
                f'Network range {network_range} is too large. '
                'Networks larger than /20 are not supported. '
                'Please break it into smaller subnets (/20 or smaller).'
            )
    except ValueError:
        pass  # Model clean() will reject invalid CIDR
    return True, None


def _apply_network_fields(data, net):
    """Apply JSON body onto a Network instance (create or update)."""
    if 'name' in data:
        net.name = (data['name'] or '').strip()
    if 'network_range' in data:
        net.network_range = data['network_range'] or net.network_range
    if 'deployment_mode' in data:
        net.deployment_mode = data['deployment_mode'] or 'CENTRALIZED'
    if 'credential_mode' in data:
        net.credential_mode = data['credential_mode'] or 'KEYSTORE'
    if 'discovery_enabled' in data:
        net.discovery_enabled = bool(data['discovery_enabled'])
    if 'traps_enabled' in data:
        net.traps_enabled = bool(data['traps_enabled'])
    if 'interval' in data and data['interval'] is not None:
        net.interval = int(data['interval'])
    if 'namespace' in data:
        net.namespace = data['namespace'] or 'default'
    if 'namespace_from_device_template' in data:
        net.namespace_from_device_template = bool(data['namespace_from_device_template'])

    # FK fields — explicit None/null clears the relationship
    for attr, field in (
        ('connection', 'connection_id'),
        ('agent_connection', 'agent_connection_id'),
        ('discovery_credential', 'discovery_credential_id'),
        ('credential', 'credential_id'),
    ):
        if attr in data:
            setattr(net, field, data[attr])  # None clears, int id sets


@csrf_exempt
def network_list(request):
    """List all networks or create a new one."""
    if request.method == 'GET':
        return _list_networks(request)
    if request.method == 'POST':
        return _create_network(request)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _list_networks(request):
    from django.db.models import Count
    qs = Network.objects.select_related('connection', 'agent_connection').annotate(
        device_count=Count('devices')
    ).order_by('name')

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(network_range__icontains=search))

    return JsonResponse({
        'networks': [_network_data(n, n.device_count) for n in qs],
        'total': qs.count(),
    })


@api_require_admin
def _create_network(request):
    data = parse_request_body(request)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'name is required.'}, status=400)

    network_range = data.get('network_range', '')
    ok, err = _validate_network_cidr(network_range)
    if not ok:
        return JsonResponse({'success': False, 'error': err}, status=400)

    namespace = data.get('namespace', 'default') or 'default'
    use_template_ns = bool(data.get('namespace_from_device_template', False))
    if not use_template_ns:
        ns_valid, ns_error = validate_namespace(namespace)
        if not ns_valid:
            return JsonResponse({'success': False, 'error': ns_error}, status=400)

    net = Network(
        name=name,
        network_range=network_range,
        discovery_enabled=bool(data.get('discovery_enabled', True)),
        traps_enabled=bool(data.get('traps_enabled', False)),
        interval=int(data.get('interval', 30) or 30),
        namespace=namespace,
        namespace_from_device_template=use_template_ns,
        deployment_mode=data.get('deployment_mode', 'CENTRALIZED') or 'CENTRALIZED',
        credential_mode=data.get('credential_mode', 'KEYSTORE') or 'KEYSTORE',
    )
    for attr, field in (
        ('connection', 'connection_id'),
        ('agent_connection', 'agent_connection_id'),
        ('discovery_credential', 'discovery_credential_id'),
        ('credential', 'credential_id'),
    ):
        if data.get(attr) is not None:
            setattr(net, field, data[attr])

    try:
        net.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except Exception as exc:
        logger.error("API create network: %s", exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    SNMPDeploymentState.mark_config_changed()
    logger.info("API: network '%s' (id=%s) created by %s.", name, net.id, request.user.username)
    return JsonResponse({'success': True, 'id': net.id, 'message': 'Network created successfully.'}, status=201)


@csrf_exempt
def network_detail(request, network_id):
    """Read, update, or delete a single network."""
    if request.method == 'GET':
        return _get_network(request, network_id)
    if request.method == 'PUT':
        return _update_network(request, network_id)
    if request.method == 'DELETE':
        return _delete_network(request, network_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _get_network(request, network_id):
    try:
        net = Network.objects.select_related('connection', 'agent_connection').get(pk=network_id)
    except Network.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Network not found.'}, status=404)
    from django.db.models import Count
    device_count = net.devices.count()
    return JsonResponse({'success': True, 'network': _network_data(net, device_count)})


@api_require_admin
def _update_network(request, network_id):
    try:
        net = Network.objects.select_related('connection', 'agent_connection').get(pk=network_id)
    except Network.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Network not found.'}, status=404)

    data = parse_request_body(request)
    _apply_network_fields(data, net)

    network_range = net.network_range
    ok, err = _validate_network_cidr(network_range)
    if not ok:
        return JsonResponse({'success': False, 'error': err}, status=400)

    if not net.namespace_from_device_template:
        ns_valid, ns_error = validate_namespace(net.namespace)
        if not ns_valid:
            return JsonResponse({'success': False, 'error': ns_error}, status=400)

    try:
        net.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except Exception as exc:
        logger.error("API update network %s: %s", network_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    SNMPDeploymentState.mark_config_changed()
    logger.info("API: network %s updated by %s.", network_id, request.user.username)
    return JsonResponse({'success': True, 'id': net.id, 'message': 'Network updated successfully.'})


@api_require_admin
def _delete_network(request, network_id):
    try:
        net = Network.objects.get(pk=network_id)
    except Network.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Network not found.'}, status=404)

    name = net.name
    pipeline_name = f"snmp-{_sanitize_pipeline_name_component(name)}-polling"
    trap_pipeline_name = f"snmp-{_sanitize_pipeline_name_component(name)}-traps"
    pipeline_deleted = trap_deleted = False
    pipeline_error = None

    if net.connection:
        try:
            es = get_elastic_connection(net.connection.id)
            for pid, flag_attr in ((pipeline_name, 'pipeline_deleted'), (trap_pipeline_name, 'trap_deleted')):
                try:
                    existing = es.logstash.get_pipeline(id=pid)
                    if pid in existing:
                        es.logstash.delete_pipeline(id=pid)
                        if flag_attr == 'pipeline_deleted':
                            pipeline_deleted = True
                        else:
                            trap_deleted = True
                except Exception:
                    pass
        except Exception as exc:
            pipeline_error = str(exc)

    net.delete()
    SNMPDeploymentState.mark_config_changed()
    logger.warning("API: network '%s' (id=%s) deleted by %s.", name, network_id, request.user.username)

    deleted_items = []
    if pipeline_deleted:
        deleted_items.append(f'pipeline "{pipeline_name}"')
    if trap_deleted:
        deleted_items.append(f'trap pipeline "{trap_pipeline_name}"')

    if deleted_items:
        msg = f"Network and {', '.join(deleted_items)} deleted successfully."
    elif pipeline_error:
        msg = f"Network deleted. Pipeline cleanup failed: {pipeline_error}"
    else:
        msg = f"Network '{name}' deleted."

    return JsonResponse({'success': True, 'message': msg})


# ===========================================================================
# PROFILES
# ===========================================================================

def _profile_list_data(p):
    return {
        'id': p.id,
        'name': p.name,
        'vendor': p.vendor or '',
        'product': p.product or '',
        'description': p.description or '',
        'is_official': p.name.endswith('.json'),
        'created_at': p.created_at.isoformat(),
    }


def _profile_detail_data(p):
    return {
        'id': p.id,
        'name': p.name,
        'vendor': p.vendor or '',
        'product': p.product or '',
        'description': p.description or '',
        'is_official': p.name.endswith('.json'),
        'profile_data': p.profile_data or {},
        'normalizers': p.normalizers or [],
        'created_at': p.created_at.isoformat(),
        'updated_at': p.updated_at.isoformat(),
    }


@csrf_exempt
def profile_list(request):
    """List all profiles or create a new one."""
    if request.method == 'GET':
        return _list_profiles(request)
    if request.method == 'POST':
        return _create_profile(request)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _list_profiles(request):
    qs = Profile.objects.all().order_by('name')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(vendor__icontains=search))
    official_filter = request.GET.get('official', '').strip().lower()
    if official_filter == 'true':
        qs = [p for p in qs if p.name.endswith('.json')]
    elif official_filter == 'false':
        qs = [p for p in qs if not p.name.endswith('.json')]

    items = [_profile_list_data(p) for p in qs]
    return JsonResponse({'profiles': items, 'total': len(items)})


@api_require_admin
def _create_profile(request):
    data = parse_request_body(request)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'name is required.'}, status=400)
    vendor = (data.get('vendor') or '').strip()
    if not vendor:
        return JsonResponse({'success': False, 'error': 'vendor is required.'}, status=400)

    if Profile.objects.filter(name=name).exists():
        return JsonResponse({'success': False, 'error': 'A profile with this name already exists.'}, status=400)

    profile = Profile(
        name=name,
        description=data.get('description', '') or '',
        vendor=vendor,
        product=data.get('product', '') or '',
        profile_data=data.get('profile_data', {}) or {},
        normalizers=data.get('normalizers', []) or [],
    )
    try:
        profile.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except Exception as exc:
        logger.error("API create profile: %s", exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    SNMPDeploymentState.mark_config_changed()
    logger.info("API: profile '%s' (id=%s) created by %s.", name, profile.id, request.user.username)
    return JsonResponse({'success': True, 'id': profile.id, 'message': 'Profile created successfully.'}, status=201)


@csrf_exempt
def profile_detail(request, profile_id):
    """Read, update, or delete a single profile."""
    if request.method == 'GET':
        return _get_profile(request, profile_id)
    if request.method == 'PUT':
        return _update_profile(request, profile_id)
    if request.method == 'DELETE':
        return _delete_profile(request, profile_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _get_profile(request, profile_id):
    try:
        p = Profile.objects.get(pk=profile_id)
    except Profile.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Profile not found.'}, status=404)
    return JsonResponse({'success': True, 'profile': _profile_detail_data(p)})


@api_require_admin
def _update_profile(request, profile_id):
    try:
        p = Profile.objects.get(pk=profile_id)
    except Profile.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Profile not found.'}, status=404)

    data = parse_request_body(request)

    new_name = (data.get('name') or p.name).strip()
    if new_name != p.name and Profile.objects.filter(name=new_name).exists():
        return JsonResponse({'success': False, 'error': 'A profile with this name already exists.'}, status=400)
    p.name = new_name
    if 'description' in data:
        p.description = data['description'] or ''
    if 'vendor' in data:
        p.vendor = data['vendor'] or ''
    if 'product' in data:
        p.product = data['product'] or ''
    if 'profile_data' in data:
        p.profile_data = data['profile_data'] or {}
    if 'normalizers' in data:
        p.normalizers = data['normalizers'] or []

    try:
        p.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except Exception as exc:
        logger.error("API update profile %s: %s", profile_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    SNMPDeploymentState.mark_config_changed()
    logger.info("API: profile %s updated by %s.", profile_id, request.user.username)
    return JsonResponse({'success': True, 'id': p.id, 'message': 'Profile updated successfully.'})


@api_require_admin
def _delete_profile(request, profile_id):
    try:
        p = Profile.objects.get(pk=profile_id)
    except Profile.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Profile not found.'}, status=404)

    # Bug 3 fix: protect ALL official profiles (name ends in .json), not just
    # the two that were hard-coded before.
    if p.name.endswith('.json'):
        return JsonResponse(
            {'success': False, 'error': 'Official profiles cannot be deleted.'},
            status=403,
        )

    name = p.name
    p.delete()
    SNMPDeploymentState.mark_config_changed()
    logger.warning("API: profile '%s' (id=%s) deleted by %s.", name, profile_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Profile '{name}' deleted."})


# ===========================================================================
# DEVICE TEMPLATES
# ===========================================================================

def _template_list_data(t):
    return {
        'id': t.id,
        'name': t.name,
        'vendor': t.vendor or '',
        'model': t.model or '',
        'product': t.product or '',
        'type': t.type or '',
        'official': t.official,
        'description': t.description or '',
        'created_at': t.created_at.isoformat(),
    }


def _template_detail_data(t):
    return {
        'id': t.id,
        'name': t.name,
        'description': t.description or '',
        'vendor': t.vendor or '',
        'model': t.model or '',
        'product': t.product or '',
        'type': t.type or '',
        'official': t.official,
        'matching_rules': t.matching_rules or [],
        'profiles': [
            {'id': p.id, 'name': p.name}
            for p in t.profiles.all()
        ],
        'created_at': t.created_at.isoformat(),
        'updated_at': t.updated_at.isoformat(),
    }


def _set_template_profiles(template, profile_ids):
    """Set the M2M profiles on a template from a list of int ids.

    Returns a list of ids that were not found (skipped).
    """
    template.profiles.clear()
    skipped = []
    for pid in profile_ids:
        try:
            pid_str = str(pid)
            if pid_str.isdigit():
                p = Profile.objects.get(id=int(pid_str))
            else:
                p = Profile.objects.get(name=pid_str)
            template.profiles.add(p)
        except Profile.DoesNotExist:
            skipped.append(pid)
    return skipped


@csrf_exempt
def template_list(request):
    """List all device templates or create a new one."""
    if request.method == 'GET':
        return _list_templates(request)
    if request.method == 'POST':
        return _create_template(request)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _list_templates(request):
    qs = DeviceTemplate.objects.all().order_by('name')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(vendor__icontains=search))
    official_filter = request.GET.get('official', '').strip().lower()
    if official_filter == 'true':
        qs = qs.filter(official=True)
    elif official_filter == 'false':
        qs = qs.filter(official=False)

    items = [_template_list_data(t) for t in qs]
    return JsonResponse({'templates': items, 'total': len(items)})


@api_require_admin
def _create_template(request):
    data = parse_request_body(request)
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'name is required.'}, status=400)
    vendor = (data.get('vendor') or '').strip()
    if not vendor:
        return JsonResponse({'success': False, 'error': 'vendor is required.'}, status=400)

    matching_rules = data.get('matching_rules', []) or []
    if not isinstance(matching_rules, list):
        return JsonResponse({'success': False, 'error': 'matching_rules must be a list.'}, status=400)

    try:
        template = DeviceTemplate(
            name=name,
            description=data.get('description', '') or '',
            vendor=vendor,
            model=data.get('model', '') or '',
            product=data.get('product', '') or '',
            type=data.get('type', '') or '',
            matching_rules=matching_rules,
            official=False,
        )
        template.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except Exception as exc:
        logger.error("API create template: %s", exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    skipped = _set_template_profiles(template, data.get('profiles', []) or [])
    SNMPDeploymentState.mark_config_changed()
    logger.info("API: template '%s' (id=%s) created by %s.", name, template.id, request.user.username)

    resp = {'success': True, 'id': template.id, 'message': 'Device template created successfully.'}
    if skipped:
        resp['skipped_profiles'] = skipped
    return JsonResponse(resp, status=201)


@csrf_exempt
def template_detail(request, template_id):
    """Read, update, or delete a single device template."""
    if request.method == 'GET':
        return _get_template(request, template_id)
    if request.method == 'PUT':
        return _update_template(request, template_id)
    if request.method == 'DELETE':
        return _delete_template(request, template_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_require_auth
def _get_template(request, template_id):
    try:
        t = DeviceTemplate.objects.prefetch_related('profiles').get(pk=template_id)
    except DeviceTemplate.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device template not found.'}, status=404)
    return JsonResponse({'success': True, 'template': _template_detail_data(t)})


@api_require_admin
def _update_template(request, template_id):
    try:
        t = DeviceTemplate.objects.prefetch_related('profiles').get(pk=template_id)
    except DeviceTemplate.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device template not found.'}, status=404)

    if t.official:
        return JsonResponse({'success': False, 'error': 'Official templates cannot be modified.'}, status=403)

    data = parse_request_body(request)
    if 'name' in data and data['name']:
        t.name = data['name'].strip()
    if 'description' in data:
        t.description = data['description'] or ''
    if 'vendor' in data and data['vendor']:
        t.vendor = data['vendor'].strip()
    if 'model' in data:
        t.model = data['model'] or ''
    if 'product' in data:
        t.product = data['product'] or ''
    if 'type' in data:
        t.type = data['type'] or ''
    if 'matching_rules' in data:
        rules = data['matching_rules'] or []
        if not isinstance(rules, list):
            return JsonResponse({'success': False, 'error': 'matching_rules must be a list.'}, status=400)
        t.matching_rules = rules

    try:
        t.save()
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'message_dict') else {'error': exc.messages}
        return JsonResponse({'success': False, 'error': errors}, status=400)
    except Exception as exc:
        logger.error("API update template %s: %s", template_id, exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

    skipped = []
    if 'profiles' in data:
        skipped = _set_template_profiles(t, data['profiles'] or [])

    SNMPDeploymentState.mark_config_changed()
    logger.info("API: template %s updated by %s.", template_id, request.user.username)
    resp = {'success': True, 'id': t.id, 'message': 'Device template updated successfully.'}
    if skipped:
        resp['skipped_profiles'] = skipped
    return JsonResponse(resp)


@api_require_admin
def _delete_template(request, template_id):
    try:
        t = DeviceTemplate.objects.get(pk=template_id)
    except DeviceTemplate.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device template not found.'}, status=404)

    if t.official:
        return JsonResponse({'success': False, 'error': 'Official templates cannot be deleted.'}, status=403)

    name = t.name
    t.delete()  # DeviceTemplate.delete() reassigns devices to the default template
    SNMPDeploymentState.mark_config_changed()
    logger.warning("API: template '%s' (id=%s) deleted by %s.", name, template_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"Device template '{name}' deleted."})


# ===========================================================================
# DEPLOY
# ===========================================================================

@csrf_exempt
@api_require_auth
def deploy_status(request):
    """Check whether there are undeployed SNMP configuration changes.

    GET /api/snmp/deploy/status/
    Any authenticated user.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        has_changes = SNMPDeploymentState.has_undeployed_changes()
        return JsonResponse({'success': True, 'has_changes': has_changes})
    except Exception as exc:
        logger.error("API deploy status: %s", exc)
        return JsonResponse({'success': True, 'has_changes': True})


@csrf_exempt
@api_require_admin
def deploy_diff(request):
    """Compute and return the deployment diff (desired vs actual pipelines).

    POST /api/snmp/deploy/diff/
    Admin only. Caches the plan for 60 seconds so a subsequent
    POST /api/snmp/deploy/apply/ can reuse it without recomputing.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        from SNMP.snmp_crud import GetDeployDiff
        return GetDeployDiff(request)
    except Exception as exc:
        logger.error("API deploy diff: %s", exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@csrf_exempt
@api_require_admin
def deploy_apply(request):
    """Apply the SNMP configuration — push pipelines to ES / agent records.

    POST /api/snmp/deploy/apply/
    Admin only. Reuses the cached diff from a preceding call to
    POST /api/snmp/deploy/diff/ if available; otherwise performs a full
    reconciliation.

    Returns counts of pipelines created / updated / deleted and any errors.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        from SNMP.snmp_crud import DeployConfiguration
        return DeployConfiguration(request)
    except Exception as exc:
        logger.error("API deploy apply: %s", exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)
