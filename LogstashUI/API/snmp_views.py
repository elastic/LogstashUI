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
    """Get the pipeline name for a network based on its logstash_name"""
    try:
        network = Network.objects.get(pk=network_id)
        
        # Generate pipeline name: snmp-{logstash_name}-*
        pipeline_name = f"snmp-{network.logstash_name}-*"
        
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

def _generate_input(input_data):
    input_components = []

    hosts = []
    for device_name, device in input_data['devices']['v1_v2c'].items():
        credential = device.credential
        hosts.append(
            {
                "host": f"udp:{device.ip_address}/{device.port}",
                "community": credential.get_community(),
                "version": credential.version
            }
        )

    if hosts:
        input_components.append(
            {
                "id": f"input_snmp_v1_v2c_{input_data['network'].id}",
                "type": "input",
                "plugin": "snmp",
                "config": {
                    "hosts": hosts
                }
            }
        )

    hosts = []
    for device_name, device in input_data['devices']['v3'].items():
        credential = device.credential
        hosts.append(
            {
                "host": f"udp:{device.ip_address}/{device.port}",
                "version": credential.version
            }
        )

    if hosts:
        # Get credential from first device for v3 auth settings (all v3 devices should share same credential)
        first_device = list(input_data['devices']['v3'].values())[0]
        credential = first_device.credential
        
        config = {
            "hosts": hosts,
            "security_name": credential.security_name
        }
        
        # Add auth settings based on security level
        if credential.security_level in ['authNoPriv', 'authPriv']:
            config["auth_protocol"] = credential.auth_protocol
            config["auth_pass"] = credential.get_auth_pass()
        
        if credential.security_level == 'authPriv':
            config["priv_protocol"] = credential.priv_protocol
            config["priv_pass"] = credential.get_priv_pass()
        
        config["security_level"] = credential.security_level
        
        input_components.append(
            {
                "id": f"input_snmp_v3_{input_data['network'].id}",
                "type": "input",
                "plugin": "snmp",
                "config": config
            }
        )
    
    return input_components

def _generate_output(input_data, network_db_object):
    output_components = []
    
    # Get the connection from the network
    connection = network_db_object.connection
    
    if not connection:
        return output_components
    
    config = {
        "index": f"snmp-{network_db_object.name.lower().replace(' ', '-')}-%{{+YYYY.MM.dd}}"
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

def CommitConfiguration(request):
    print("Next up")
    return JsonResponse({
        'success': True,
        'message': f'Configuration updated!'
    })

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
            'name': profile_name,
            'profile_data': profile_data,
            'description': ''
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
            'profile_data': profile.profile_data,
            'description': profile.description
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
