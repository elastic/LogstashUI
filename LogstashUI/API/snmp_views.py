from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from SNMP.models import Credential, Network
from django.core.exceptions import ValidationError
import json


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
        
        return HttpResponse("Credential updated successfully!", status=200)
        
    except Credential.DoesNotExist:
        return HttpResponse("Credential not found", status=404)
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
        discovery_enabled = request.POST.get('discovery_enabled', 'true') == 'true'
        
        # Create network object
        network = Network(
            name=name,
            network_range=network_range,
            logstash_name=logstash_name,
            discovery_enabled=discovery_enabled
        )
        
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
        
        # Save (this will trigger validation)
        network.save()
        
        return HttpResponse("Network updated successfully!", status=200)
        
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
        queryset = Device.objects.select_related('credential', 'network')
        
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
            devices.append({
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'credential_id': device.credential.id if device.credential else None,
                'credential_name': device.credential.name if device.credential else None,
                'network_id': device.network.id if device.network else None,
                'network_name': device.network.name if device.network else None,
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
        from SNMP.models import Device
        
        # Extract form data
        name = request.POST.get('name')
        ip_address = request.POST.get('ip_address')
        credential_id = request.POST.get('credential')
        network_id = request.POST.get('network')
        
        # Create device object
        device = Device(
            name=name,
            ip_address=ip_address
        )
        
        # Set optional foreign keys
        if credential_id:
            device.credential_id = credential_id
        if network_id:
            device.network_id = network_id
        
        # Save (this will trigger validation)
        device.save()
        
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
        from SNMP.models import Device
        
        device = Device.objects.get(pk=device_id)
        
        # Update fields
        device.name = request.POST.get('name', device.name)
        device.ip_address = request.POST.get('ip_address', device.ip_address)
        
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
        
        data = {
            'id': device.id,
            'name': device.name,
            'ip_address': device.ip_address,
            'credential': device.credential_id if device.credential else None,
            'network': device.network_id if device.network else None,
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
