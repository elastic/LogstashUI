from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from SNMP.models import Credential, Network
from django.core.exceptions import ValidationError
import json


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
        
        return HttpResponse("Credential created successfully!", status=200)
        
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
        
        return HttpResponse("Network created successfully!", status=200)
        
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
