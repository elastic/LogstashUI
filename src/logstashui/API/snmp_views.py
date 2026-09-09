#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""REST API views for SNMP device management.

Endpoints
---------
GET    /api/snmp/devices/           device_list     (any authenticated user)
POST   /api/snmp/devices/           device_list     (admin)
GET    /api/snmp/devices/{id}/      device_detail   (any authenticated user)
PUT    /api/snmp/devices/{id}/      device_detail   (admin)
DELETE /api/snmp/devices/{id}/      device_detail   (admin)

List query parameters
---------------------
page        int, default 1
page_size   int, default 25
search      str — case-insensitive match on name, ip_address, or hostname
network     int — filter by network id
sort_by     name | -name | ip_address | -ip_address | hostname | -hostname |
            created_at | -created_at  (default: -created_at)
"""

import json
import logging

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from SNMP.models import Device, SNMPDeploymentState

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
        'latitude': str(device.latitude) if device.latitude is not None else None,
        'longitude': str(device.longitude) if device.longitude is not None else None,
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
    device.latitude = round(float(lat), 6) if lat is not None else None
    device.longitude = round(float(lon), 6) if lon is not None else None

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
