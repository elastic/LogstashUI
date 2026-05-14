#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings
from .models import Device, DeviceTemplate, Profile
import json
import os
import traceback

# Import PySNMP asyncio API
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UsmUserData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    next_cmd,
    usmHMACMD5AuthProtocol,
    usmHMACSHAAuthProtocol,
    usmDESPrivProtocol,
    usm3DESEDEPrivProtocol,
    usmAesCfb128Protocol,
    usmAesCfb192Protocol,
    usmAesCfb256Protocol,
)
import asyncio


def _format_snmp_value(value):
    """
    Format SNMP value - convert binary values to hex for MAC/IP addresses
    """
    value_str = str(value)
    
    # Count printable vs non-printable characters
    printable_count = sum(1 for c in value_str if 32 <= ord(c) <= 126 or c in '\r\n\t')
    total_count = len(value_str)
    
    # If mostly printable (>70%), treat as text
    if total_count == 0 or printable_count / total_count > 0.7:
        return value_str
    
    # Check if it looks like a MAC address (6 bytes) or IP address (4 bytes)
    if total_count in [4, 6, 16]:  # IPv4, MAC, or IPv6
        try:
            hex_str = ':'.join(f'{ord(c):02x}' for c in value_str)
            return hex_str
        except:
            return value_str
    
    # For other binary data, convert to hex
    if any(ord(c) < 32 or ord(c) > 126 for c in value_str if c not in '\r\n\t'):
        try:
            hex_str = ':'.join(f'{ord(c):02x}' for c in value_str)
            return hex_str
        except:
            return value_str
    
    return value_str


def _load_profile_data(profile):
    """
    Load profile data from JSON file (for official profiles) or database (for custom profiles)
    
    Args:
        profile: Profile object
        
    Returns:
        dict: Profile data containing get, walk, and table OIDs
    """
    if profile.profile_data.get('is_official_placeholder'):
        profile_name = profile.name.replace('.json', '')
        official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
        profile_path = os.path.join(official_profiles_dir, f"{profile_name}.json")
        
        try:
            with open(profile_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading official profile {profile_name}: {e}")
            return {'get': {}, 'walk': {}, 'table': {}}
    else:
        return profile.profile_data


def _merge_profile_oids(profiles):
    """
    Merge OIDs from multiple profiles
    
    Args:
        profiles: List of Profile objects
        
    Returns:
        dict: Merged OIDs with structure {'get': {}, 'walk': {}, 'table': {}}
    """
    merged = {
        'get': {},
        'walk': {},
        'table': {}
    }
    
    for profile in profiles:
        profile_data = _load_profile_data(profile)
        
        if 'get' in profile_data:
            merged['get'].update(profile_data['get'])
        if 'walk' in profile_data:
            merged['walk'].update(profile_data['walk'])
        if 'table' in profile_data:
            merged['table'].update(profile_data['table'])
    
    return merged


def _create_auth_data(credential):
    """
    Create PySNMP authentication data based on credential type
    
    Args:
        credential: Credential object
        
    Returns:
        CommunityData or UsmUserData object
    """
    if credential.version in ['1', '2c']:
        # SNMPv1/v2c - use community string
        community = credential.get_community()
        if not community:
            raise ValueError(f"Credential '{credential.name}' has no community string")
        return CommunityData(community, mpModel=0 if credential.version == '1' else 1)
    
    elif credential.version == '3':
        # SNMPv3 - use USM
        if not credential.security_name:
            raise ValueError(f"Credential '{credential.name}' has no security name")
        
        if credential.security_level == 'noAuthNoPriv':
            return UsmUserData(credential.security_name)
        
        elif credential.security_level == 'authNoPriv':
            if not credential.auth_protocol or not credential.auth_pass:
                raise ValueError(f"Credential '{credential.name}' requires auth protocol and password for authNoPriv")
            
            auth_protocol = usmHMACMD5AuthProtocol if credential.auth_protocol == 'md5' else usmHMACSHAAuthProtocol
            return UsmUserData(
                credential.security_name,
                authKey=credential.get_auth_pass(),
                authProtocol=auth_protocol
            )
        
        elif credential.security_level == 'authPriv':
            if not credential.auth_protocol or not credential.auth_pass:
                raise ValueError(f"Credential '{credential.name}' requires auth protocol and password for authPriv")
            if not credential.priv_protocol or not credential.priv_pass:
                raise ValueError(f"Credential '{credential.name}' requires privacy protocol and password for authPriv")
            
            auth_protocol = usmHMACMD5AuthProtocol if credential.auth_protocol == 'md5' else usmHMACSHAAuthProtocol
            priv_protocol_map = {
                'des': usmDESPrivProtocol,
                '3des': usm3DESEDEPrivProtocol,
                'aes': usmAesCfb128Protocol,
                'aes128': usmAesCfb128Protocol,
                'aes192': usmAesCfb192Protocol,
                'aes256': usmAesCfb256Protocol,
            }
            priv_protocol = priv_protocol_map.get(credential.priv_protocol, usmDESPrivProtocol)
            
            return UsmUserData(
                credential.security_name,
                authKey=credential.get_auth_pass(),
                authProtocol=auth_protocol,
                privKey=credential.get_priv_pass(),
                privProtocol=priv_protocol
            )
    
    raise ValueError(f"Unknown SNMP version: {credential.version}")


async def _perform_snmp_get_async(device, credential, oids):
    """Perform SNMP GET operations (async)"""
    results = {}
    
    if not oids:
        return results
    
    try:
        auth_data = _create_auth_data(credential)
    except Exception as e:
        return {'error': f'Failed to create authentication data: {str(e)}'}
    
    transport = await UdpTransportTarget.create((device.ip_address, device.port))
    snmp_engine = SnmpEngine()  # Reuse the same engine
    
    for field_name, oid_string in oids.items():
        try:
            errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
                snmp_engine,
                auth_data,
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(oid_string))
            )
            
            if errorIndication:
                results[field_name] = {'error': str(errorIndication)}
            elif errorStatus:
                results[field_name] = {'error': f'{errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex) - 1][0] or "?"}'}
            else:
                for varBind in varBinds:
                    results[field_name] = _format_snmp_value(varBind[1])
        except Exception as e:
            results[field_name] = {'error': str(e)}
    
    return results

def _perform_snmp_get(device, credential, oids):
    """Synchronous wrapper - runs async code in a thread"""
    import threading
    result = [None]  # Use list to allow modification in nested function
    exception = [None]
    
    def run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result[0] = loop.run_until_complete(_perform_snmp_get_async(device, credential, oids))
            # Cancel all pending tasks before closing
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=20)  # 20 second timeout
    
    if thread.is_alive():
        # Thread is still running - timeout occurred
        return {'error': 'SNMP GET operation timed out - device may be unreachable'}
    
    if exception[0]:
        return {'error': str(exception[0])}
    
    return result[0] if result[0] is not None else {'error': 'No response from device'}


async def _perform_snmp_walk_async(device, credential, oids):
    """Perform SNMP WALK operations (async)"""
    results = {}
    
    if not oids:
        return results
    
    try:
        auth_data = _create_auth_data(credential)
    except Exception as e:
        return {'error': f'Failed to create authentication data: {str(e)}'}
    
    transport = await UdpTransportTarget.create((device.ip_address, device.port))
    snmp_engine = SnmpEngine()  # Reuse the same engine
    
    for field_name, oid_string in oids.items():
        try:
            walk_results = []
            current_oid = oid_string
            max_iterations = 100  # Safety limit
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                errorIndication, errorStatus, errorIndex, varBinds = await next_cmd(
                    snmp_engine,
                    auth_data,
                    transport,
                    ContextData(),
                    ObjectType(ObjectIdentity(current_oid)),
                    lexicographic_mode=False
                )
                
                if errorIndication:
                    results[field_name] = {'error': str(errorIndication)}
                    break
                elif errorStatus:
                    results[field_name] = {'error': f'{errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex) - 1][0] or "?"}'}
                    break
                elif not varBinds:
                    break
                
                varBind = varBinds[0]  # next_cmd returns one result
                next_oid = str(varBind[0])
                
                # Check if we've moved beyond this OID prefix
                if not next_oid.startswith(oid_string + '.'):
                    break
                
                walk_results.append({
                    'oid': next_oid,
                    'value': _format_snmp_value(varBind[1])
                })
                
                # Update OID for next iteration
                current_oid = next_oid
            
            if field_name not in results:
                results[field_name] = walk_results
        except Exception as e:
            results[field_name] = {'error': str(e)}
    
    return results

def _perform_snmp_walk(device, credential, oids):
    """Synchronous wrapper - runs async code in a thread"""
    import threading
    result = [None]
    exception = [None]
    
    def run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result[0] = loop.run_until_complete(_perform_snmp_walk_async(device, credential, oids))
            # Cancel all pending tasks before closing
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=20)  # 20 second timeout
    
    if thread.is_alive():
        return {'error': 'SNMP WALK operation timed out - device may be unreachable'}
    
    if exception[0]:
        return {'error': str(exception[0])}
    
    return result[0] if result[0] is not None else {'error': 'No response from device'}

async def _perform_snmp_table_async(device, credential, tables):
    """Perform SNMP table operations (async)"""
    results = {}
    
    if not tables:
        return results
    
    try:
        auth_data = _create_auth_data(credential)
    except Exception as e:
        return {'error': f'Failed to create authentication data: {str(e)}'}
    
    transport = await UdpTransportTarget.create((device.ip_address, device.port))
    snmp_engine = SnmpEngine()  # Reuse the same engine
    
    for table_name, table_config in tables.items():
        try:
            if isinstance(table_config, dict) and 'columns' in table_config:
                columns = table_config['columns']
                
                table_rows = {}
                
                for column_name, column_oid in columns.items():
                    current_oid = column_oid
                    max_iterations = 100  # Safety limit
                    iteration = 0
                    
                    while iteration < max_iterations:
                        iteration += 1
                        errorIndication, errorStatus, errorIndex, varBinds = await next_cmd(
                            snmp_engine,
                            auth_data,
                            transport,
                            ContextData(),
                            ObjectType(ObjectIdentity(current_oid)),
                            lexicographic_mode=False
                        )
                        
                        if errorIndication or errorStatus or not varBinds:
                            break
                        
                        varBind = varBinds[0]  # next_cmd returns one result
                        next_oid = str(varBind[0])
                        
                        # Check if we've moved beyond this column's OID prefix
                        if not next_oid.startswith(column_oid + '.'):
                            break
                        
                        # Extract row index from OID
                        oid_parts = next_oid.split('.')
                        column_parts = column_oid.split('.')
                        row_index = '.'.join(oid_parts[len(column_parts):])
                        
                        if row_index:
                            if row_index not in table_rows:
                                table_rows[row_index] = {}
                            table_rows[row_index][column_name] = _format_snmp_value(varBind[1])
                        
                        # Update OID for next iteration
                        current_oid = next_oid
                
                results[table_name] = list(table_rows.values())
        except Exception as e:
            results[table_name] = {'error': str(e)}
    
    return results

def _perform_snmp_table(device, credential, tables):
    """Synchronous wrapper - runs async code in a thread"""
    import threading
    result = [None]
    exception = [None]
    
    def run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result[0] = loop.run_until_complete(_perform_snmp_table_async(device, credential, tables))
            # Cancel all pending tasks before closing
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=40)  # 40 second timeout for tables
    
    if thread.is_alive():
        return {'error': 'SNMP TABLE operation timed out - device may be unreachable'}
    
    if exception[0]:
        return {'error': str(exception[0])}
    
    return result[0] if result[0] is not None else {'error': 'No response from device'}


@require_http_methods(["POST"])
def RunSNMPTest(request):
    """
    Run SNMP test against a device using a device template
    
    Expected POST data:
    {
        "device_id": int,
        "template_id": int (optional - if not provided, uses device's assigned template)
    }
    }
    """
    import time
    start_time = time.time()
    
    try:
        print("=== SNMP Test Started ===")
        data = json.loads(request.body)
        device_id = data.get('device_id')
        template_id = data.get('template_id')
        print(f"Device ID: {device_id}, Template ID: {template_id}")
        
        if not device_id:
            return JsonResponse({'success': False, 'error': 'device_id is required'}, status=400)
        
        device = Device.objects.select_related('credential', 'device_template').get(pk=device_id)
        print(f"Device found: {device.name}, Credential: {device.credential}")
        
        if not device.credential:
            return JsonResponse({'success': False, 'error': 'Device has no credential assigned'}, status=400)
        
        if template_id:
            template = DeviceTemplate.objects.prefetch_related('profiles').get(pk=template_id)
        elif device.device_template:
            template = device.device_template
        else:
            return JsonResponse({'success': False, 'error': 'No template specified and device has no assigned template'}, status=400)
        
        profiles = list(template.profiles.all())
        print(f"Template: {template.name}, Profiles: {[p.name for p in profiles]}")
        
        if not profiles:
            return JsonResponse({'success': False, 'error': 'Template has no profiles assigned'}, status=400)
        
        print("Merging profile OIDs...")
        merged_oids = _merge_profile_oids(profiles)
        print(f"Merged OIDs - GET: {len(merged_oids['get'])}, WALK: {len(merged_oids['walk'])}, TABLE: {len(merged_oids['table'])}")
        
        print("Performing SNMP operations...")
        
        # Use threading to enforce overall timeout
        import threading
        results_container = [None]
        exception_container = [None]
        
        def perform_all_operations():
            try:
                results_container[0] = {
                    'get': _perform_snmp_get(device, device.credential, merged_oids['get']),
                    'walk': _perform_snmp_walk(device, device.credential, merged_oids['walk']),
                    'table': _perform_snmp_table(device, device.credential, merged_oids['table'])
                }
            except Exception as e:
                exception_container[0] = e
        
        operation_thread = threading.Thread(target=perform_all_operations, daemon=True)
        operation_thread.start()
        operation_thread.join(timeout=60)  # Overall 60 second timeout
        
        if operation_thread.is_alive():
            # Operations took too long, return timeout error
            print("SNMP operations timed out after 60 seconds")
            return JsonResponse({
                'success': False,
                'error': 'Test timed out after 60 seconds - device may be unreachable or too slow to respond',
                'execution_time': 60.0,
                'device': {
                    'id': device.id,
                    'name': device.name,
                    'ip_address': device.ip_address,
                    'port': device.port
                },
                'template': {
                    'id': template.id,
                    'name': template.name,
                    'description': template.description,
                    'vendor': template.vendor,
                    'profiles': [{'name': p.name, 'description': p.description} for p in profiles]
                }
            })
        
        if exception_container[0]:
            raise exception_container[0]
        
        results = results_container[0]
        print("SNMP operations completed")
        
        # Check if there are any errors in the results
        has_errors = False
        error_messages = []
        has_any_success = False
        
        # Check for top-level errors
        for category in ['get', 'walk', 'table']:
            if isinstance(results[category], dict) and 'error' in results[category]:
                has_errors = True
                error_messages.append(f"{category.upper()}: {results[category]['error']}")
            elif results[category]:  # Has some data
                has_any_success = True
        
        # Check for field-level errors in get results
        if isinstance(results['get'], dict):
            for field, value in results['get'].items():
                if isinstance(value, dict) and 'error' in value:
                    has_errors = True
                else:
                    has_any_success = True
        
        # Check for field-level errors in walk results
        if isinstance(results['walk'], dict):
            for field, value in results['walk'].items():
                if isinstance(value, dict) and 'error' in value:
                    has_errors = True
                else:
                    has_any_success = True
        
        # Check for field-level errors in table results
        if isinstance(results['table'], dict):
            for table, value in results['table'].items():
                if isinstance(value, dict) and 'error' in value:
                    has_errors = True
                else:
                    has_any_success = True
        
        execution_time = time.time() - start_time
        
        # If everything failed, return error response
        if has_errors and not has_any_success:
            return JsonResponse({
                'success': False,
                'error': '; '.join(error_messages) if error_messages else 'All SNMP operations failed',
                'execution_time': round(execution_time, 2),
                'device': {
                    'id': device.id,
                    'name': device.name,
                    'ip_address': device.ip_address,
                    'port': device.port
                },
                'template': {
                    'id': template.id,
                    'name': template.name,
                    'description': template.description,
                    'vendor': template.vendor,
                    'profiles': [{'name': p.name, 'description': p.description} for p in profiles]
                }
            })
        
        response_data = {
            'success': True,  # True if we got at least some results
            'has_errors': has_errors,
            'error_summary': '; '.join(error_messages) if error_messages else None,
            'execution_time': round(execution_time, 2),
            'device': {
                'id': device.id,
                'name': device.name,
                'ip_address': device.ip_address,
                'port': device.port
            },
            'template': {
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'vendor': template.vendor,
                'profiles': [{'name': p.name, 'description': p.description} for p in profiles]
            },
            'results': results
        }
        
        print(f"Returning response - success: {response_data['success']}, has_errors: {response_data['has_errors']}")
        print(f"Response data keys: {list(response_data.keys())}")
        print("=== SNMP Test Completed ===")
        
        return JsonResponse(response_data)
        
    except Device.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device not found'}, status=404)
    except DeviceTemplate.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Template not found'}, status=404)
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"SNMP Test Error: {str(e)}")
        print(f"Traceback:\n{error_trace}")
        return JsonResponse({
            'success': False, 
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': error_trace
        }, status=500)
