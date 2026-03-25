import json
import time
import logging
import traceback
import tempfile
import os

from django.http import JsonResponse, HttpResponse
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from Common.decorators import require_admin_role
from Common.encryption import decrypt_credential

from .models import Device, Credential, Profile

logger = logging.getLogger(__name__)


# ============================================================================
# Credential endpoints
# ============================================================================

def GetCredentials(request):
    """Get all network credentials (no secrets)"""
    try:
        credentials = Credential.objects.all().values(
            'id', 'name', 'protocol', 'auth_type', 'description',
            'username', 'api_key_header', 'verify_ssl', 'created_at'
        )
        return JsonResponse(list(credentials), safe=False, status=200)
    except Exception as e:
        logger.exception("Error fetching credentials")
        return HttpResponse(f"Error fetching credentials: {str(e)}", status=500)


def GetCredential(request, credential_id):
    """Get a single credential for editing (no secret values)"""
    try:
        cred = Credential.objects.get(pk=credential_id)
        data = {
            'id': cred.id,
            'name': cred.name,
            'description': cred.description,
            'protocol': cred.protocol,
            'auth_type': cred.auth_type,
            'username': cred.username,
            'api_key_header': cred.api_key_header,
            'verify_ssl': cred.verify_ssl,
        }
        return JsonResponse(data, status=200)
    except Credential.DoesNotExist:
        return HttpResponse("Credential not found", status=404)
    except Exception as e:
        logger.exception("Error fetching credential %s", credential_id)
        return HttpResponse(f"Error fetching credential: {str(e)}", status=500)


@require_admin_role
def AddCredential(request):
    """Add a new network credential"""
    try:
        cred = Credential(
            name=request.POST.get('name', '').strip(),
            description=request.POST.get('description', '').strip(),
            protocol=request.POST.get('protocol', 'restconf'),
            auth_type=request.POST.get('auth_type', 'basic'),
            username=request.POST.get('username', '').strip(),
            api_key_header=request.POST.get('api_key_header', 'X-API-Key').strip(),
            verify_ssl=request.POST.get('verify_ssl', 'true').lower() == 'true',
        )

        password = request.POST.get('password', '').strip()
        if password:
            cred.password = password

        token = request.POST.get('token', '').strip()
        if token:
            cred.token = token

        cred.save()
        return JsonResponse({'id': cred.id, 'message': 'Credential created successfully!'}, status=200)

    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        logger.exception("Error creating credential")
        return HttpResponse(f"Error creating credential: {str(e)}", status=500)


@require_admin_role
def UpdateCredential(request, credential_id):
    """Update an existing network credential"""
    try:
        cred = Credential.objects.get(pk=credential_id)

        cred.name = request.POST.get('name', cred.name).strip()
        cred.description = request.POST.get('description', cred.description).strip()
        cred.protocol = request.POST.get('protocol', cred.protocol)
        cred.auth_type = request.POST.get('auth_type', cred.auth_type)
        cred.username = request.POST.get('username', cred.username).strip()
        cred.api_key_header = request.POST.get('api_key_header', cred.api_key_header).strip()
        cred.verify_ssl = request.POST.get('verify_ssl', 'true').lower() == 'true'

        # Only update secrets if provided (not empty)
        password = request.POST.get('password', '').strip()
        if password:
            cred.password = password

        token = request.POST.get('token', '').strip()
        if token:
            cred.token = token

        cred.save()
        return JsonResponse({'id': cred.id, 'message': 'Credential updated successfully!'}, status=200)

    except Credential.DoesNotExist:
        return HttpResponse("Credential not found", status=404)
    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        logger.exception("Error updating credential %s", credential_id)
        return HttpResponse(f"Error updating credential: {str(e)}", status=500)


@require_admin_role
def DeleteCredential(request, credential_id):
    """Delete a network credential"""
    try:
        cred = Credential.objects.get(pk=credential_id)
        cred.delete()
        return JsonResponse({'message': 'Credential deleted successfully!'}, status=200)
    except Credential.DoesNotExist:
        return HttpResponse("Credential not found", status=404)
    except Exception as e:
        logger.exception("Error deleting credential %s", credential_id)
        return HttpResponse(f"Error deleting credential: {str(e)}", status=500)


# ============================================================================
# Device endpoints
# ============================================================================

def GetDevices(request):
    """Get paginated network devices with search, filter, and sort"""
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 25))
        search = request.GET.get('search', '').strip()
        vendor_filter = request.GET.get('vendor', '').strip()
        sort_by = request.GET.get('sort_by', '-created_at')

        queryset = Device.objects.select_related('credential', 'profile')

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(hostname__icontains=search)
            )

        if vendor_filter:
            queryset = queryset.filter(vendor=vendor_filter)

        valid_sort_fields = ['name', '-name', 'hostname', '-hostname', 'created_at', '-created_at', 'last_status']
        if sort_by in valid_sort_fields:
            queryset = queryset.order_by(sort_by)

        offset = (page - 1) * page_size
        devices_page = list(queryset[offset:offset + page_size + 1])
        has_next = len(devices_page) > page_size
        if has_next:
            devices_page = devices_page[:page_size]

        total_count = queryset.count()
        total_pages = max(1, (total_count + page_size - 1) // page_size)

        devices = []
        for device in devices_page:
            devices.append({
                'id': device.id,
                'name': device.name,
                'hostname': device.hostname,
                'vendor': device.vendor,
                'vendor_display': device.get_vendor_display(),
                'rest_port': device.rest_port,
                'netconf_port': device.netconf_port,
                'use_restconf': device.use_restconf,
                'use_netconf': device.use_netconf,
                'credential_id': device.credential_id,
                'credential_name': device.credential.name if device.credential else None,
                'profile_id': device.profile_id,
                'profile_name': device.profile.name if device.profile else None,
                'last_status': device.last_status,
                'last_checked': device.last_checked.isoformat() if device.last_checked else None,
                'last_status_message': device.last_status_message,
                'created_at': device.created_at.isoformat(),
            })

        return JsonResponse({
            'devices': devices,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
            'has_next': has_next,
            'has_previous': page > 1,
        }, status=200)

    except Exception as e:
        logger.exception("Error fetching devices")
        return HttpResponse(f"Error fetching devices: {str(e)}", status=500)


def GetDevice(request, device_id):
    """Get a single device for editing"""
    try:
        device = Device.objects.select_related('credential', 'profile').get(pk=device_id)
        data = {
            'id': device.id,
            'name': device.name,
            'description': device.description,
            'vendor': device.vendor,
            'hostname': device.hostname,
            'rest_port': device.rest_port,
            'netconf_port': device.netconf_port,
            'use_restconf': device.use_restconf,
            'use_netconf': device.use_netconf,
            'credential_id': device.credential_id,
            'profile_id': device.profile_id,
        }
        return JsonResponse(data, status=200)
    except Device.DoesNotExist:
        return HttpResponse("Device not found", status=404)
    except Exception as e:
        logger.exception("Error fetching device %s", device_id)
        return HttpResponse(f"Error fetching device: {str(e)}", status=500)


@require_admin_role
def AddDevice(request):
    """Add a new network device"""
    try:
        credential_id = request.POST.get('credential_id') or None
        profile_id = request.POST.get('profile_id') or None

        device = Device(
            name=request.POST.get('name', '').strip(),
            description=request.POST.get('description', '').strip(),
            vendor=request.POST.get('vendor', 'generic'),
            hostname=request.POST.get('hostname', '').strip(),
            rest_port=int(request.POST.get('rest_port', 443)),
            netconf_port=int(request.POST.get('netconf_port', 830)),
            use_restconf=request.POST.get('use_restconf', 'true').lower() == 'true',
            use_netconf=request.POST.get('use_netconf', 'false').lower() == 'true',
            credential_id=credential_id,
            profile_id=profile_id,
        )
        device.save()
        return JsonResponse({'id': device.id, 'message': 'Device created successfully!'}, status=200)

    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        logger.exception("Error creating device")
        return HttpResponse(f"Error creating device: {str(e)}", status=500)


@require_admin_role
def UpdateDevice(request, device_id):
    """Update an existing network device"""
    try:
        device = Device.objects.get(pk=device_id)

        credential_id = request.POST.get('credential_id') or None
        profile_id = request.POST.get('profile_id') or None

        device.name = request.POST.get('name', device.name).strip()
        device.description = request.POST.get('description', device.description).strip()
        device.vendor = request.POST.get('vendor', device.vendor)
        device.hostname = request.POST.get('hostname', device.hostname).strip()
        device.rest_port = int(request.POST.get('rest_port', device.rest_port))
        device.netconf_port = int(request.POST.get('netconf_port', device.netconf_port))
        device.use_restconf = request.POST.get('use_restconf', 'true').lower() == 'true'
        device.use_netconf = request.POST.get('use_netconf', 'false').lower() == 'true'
        device.credential_id = credential_id
        device.profile_id = profile_id

        device.save()
        return JsonResponse({'id': device.id, 'message': 'Device updated successfully!'}, status=200)

    except Device.DoesNotExist:
        return HttpResponse("Device not found", status=404)
    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        logger.exception("Error updating device %s", device_id)
        return HttpResponse(f"Error updating device: {str(e)}", status=500)


@require_admin_role
def DeleteDevice(request, device_id):
    """Delete a network device"""
    try:
        device = Device.objects.get(pk=device_id)
        device.delete()
        return JsonResponse({'message': 'Device deleted successfully!'}, status=200)
    except Device.DoesNotExist:
        return HttpResponse("Device not found", status=404)
    except Exception as e:
        logger.exception("Error deleting device %s", device_id)
        return HttpResponse(f"Error deleting device: {str(e)}", status=500)


def TestDeviceConnection(request, device_id):
    """
    Attempt a live connection test to the device.
    For RESTCONF: HTTP GET to the capabilities endpoint.
    For NETCONF: SSH hello exchange via ncclient.
    Updates device.last_status and last_status_message.
    """
    try:
        device = Device.objects.select_related('credential').get(pk=device_id)
    except Device.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Device not found'}, status=404)

    cred = device.credential
    start = time.time()
    status = 'unknown'
    message = ''

    try:
        if device.use_restconf and cred:
            import requests as req
            import urllib3

            auth_type = cred.auth_type
            verify = cred.verify_ssl

            if not verify:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            scheme = 'https'
            url = f"{scheme}://{device.hostname}:{device.rest_port}/restconf/data/ietf-yang-library:modules-state"

            headers = {'Accept': 'application/yang-data+json'}
            auth = None

            if auth_type == 'basic':
                auth = (cred.username, cred.get_password() or '')
            elif auth_type in ('token', 'api_key'):
                header_name = cred.api_key_header if auth_type == 'api_key' else 'Authorization'
                token_val = cred.get_token() or ''
                headers[header_name] = f'Bearer {token_val}' if auth_type == 'token' else token_val

            response = req.get(url, headers=headers, auth=auth, verify=verify, timeout=10)
            elapsed_ms = int((time.time() - start) * 1000)

            if response.status_code < 500:
                status = 'reachable'
                message = f"HTTP {response.status_code} in {elapsed_ms}ms"
            else:
                status = 'unreachable'
                message = f"HTTP {response.status_code} in {elapsed_ms}ms"

        elif device.use_netconf and cred:
            try:
                from ncclient import manager as nc_manager

                connect_params = {
                    'host': device.hostname,
                    'port': device.netconf_port,
                    'username': cred.username,
                    'password': cred.get_password() or '',
                    'timeout': 10,
                    'hostkey_verify': False,
                    'look_for_keys': False,
                    'allow_agent': False,
                }

                with nc_manager.connect(**connect_params) as m:
                    elapsed_ms = int((time.time() - start) * 1000)
                    status = 'reachable'
                    message = f"NETCONF hello exchanged in {elapsed_ms}ms"

            except ImportError:
                status = 'error'
                message = "ncclient not installed. Add 'ncclient' to requirements.txt."
        else:
            status = 'error'
            message = "No protocol configured or no credential assigned."

    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        status = 'unreachable'
        message = f"{type(e).__name__}: {str(e)} (after {elapsed_ms}ms)"
        logger.warning("Connection test failed for device %s: %s", device_id, str(e))

    # Persist result
    device.last_status = status
    device.last_checked = timezone.now()
    device.last_status_message = message
    # Use update() to skip full_clean on this status-only write
    Device.objects.filter(pk=device_id).update(
        last_status=status,
        last_checked=device.last_checked,
        last_status_message=message,
    )

    return JsonResponse({
        'status': status,
        'message': message,
        'elapsed_ms': int((time.time() - start) * 1000),
    }, status=200)


# ============================================================================
# Profile endpoints
# ============================================================================

def GetProfiles(request):
    """Get all network config profiles"""
    try:
        profiles = Profile.objects.all().values(
            'id', 'name', 'description', 'vendor', 'type', 'created_at'
        )
        return JsonResponse(list(profiles), safe=False, status=200)
    except Exception as e:
        logger.exception("Error fetching profiles")
        return HttpResponse(f"Error fetching profiles: {str(e)}", status=500)


def GetProfile(request, profile_name):
    """Get a single profile"""
    try:
        profile = Profile.objects.get(name=profile_name)
        data = {
            'id': profile.id,
            'name': profile.name,
            'description': profile.description,
            'vendor': profile.vendor,
            'type': profile.type,
            'profile_data': profile.profile_data,
        }
        return JsonResponse(data, status=200)
    except Profile.DoesNotExist:
        return HttpResponse("Profile not found", status=404)
    except Exception as e:
        logger.exception("Error fetching profile %s", profile_name)
        return HttpResponse(f"Error fetching profile: {str(e)}", status=500)


@require_admin_role
def AddProfile(request):
    """Add a new network config profile"""
    try:
        profile_data_raw = request.POST.get('profile_data', '{}')
        try:
            profile_data = json.loads(profile_data_raw)
        except json.JSONDecodeError:
            return HttpResponse("profile_data must be valid JSON", status=400)

        profile = Profile(
            name=request.POST.get('name', '').strip(),
            description=request.POST.get('description', '').strip(),
            vendor=request.POST.get('vendor', '').strip(),
            type=request.POST.get('type', '').strip(),
            profile_data=profile_data,
        )
        profile.save()
        return JsonResponse({'id': profile.id, 'message': 'Profile created successfully!'}, status=200)

    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        logger.exception("Error creating profile")
        return HttpResponse(f"Error creating profile: {str(e)}", status=500)


@require_admin_role
def UpdateProfile(request, profile_name):
    """Update an existing profile"""
    try:
        profile = Profile.objects.get(name=profile_name)

        profile_data_raw = request.POST.get('profile_data', '')
        if profile_data_raw:
            try:
                profile.profile_data = json.loads(profile_data_raw)
            except json.JSONDecodeError:
                return HttpResponse("profile_data must be valid JSON", status=400)

        profile.name = request.POST.get('name', profile.name).strip()
        profile.description = request.POST.get('description', profile.description).strip()
        profile.vendor = request.POST.get('vendor', profile.vendor).strip()
        profile.type = request.POST.get('type', profile.type).strip()

        profile.save()
        return JsonResponse({'id': profile.id, 'message': 'Profile updated successfully!'}, status=200)

    except Profile.DoesNotExist:
        return HttpResponse("Profile not found", status=404)
    except ValidationError as e:
        error_msg = str(e)
        if hasattr(e, 'message_dict'):
            error_msg = '<br>'.join([f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()])
        return HttpResponse(error_msg, status=400)
    except Exception as e:
        logger.exception("Error updating profile %s", profile_name)
        return HttpResponse(f"Error updating profile: {str(e)}", status=500)


@require_admin_role
def DeleteProfile(request, profile_name):
    """Delete a profile"""
    try:
        profile = Profile.objects.get(name=profile_name)
        profile.delete()
        return JsonResponse({'message': 'Profile deleted successfully!'}, status=200)
    except Profile.DoesNotExist:
        return HttpResponse("Profile not found", status=404)
    except Exception as e:
        logger.exception("Error deleting profile %s", profile_name)
        return HttpResponse(f"Error deleting profile: {str(e)}", status=500)
