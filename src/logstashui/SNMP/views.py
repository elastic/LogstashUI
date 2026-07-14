#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse

from .models import Credential, Network, Device, Profile, DeviceTemplate
from PipelineManager.forms import ConnectionForm
from .overview import get_discovered_devices_count, get_template_data_categories, get_high_resource_usage
from Common.decorators import require_admin_role

import os
import json


# Create your views here.
def Networks(request):
    from PipelineManager.models import Connection
    networks = Network.objects.select_related('connection').all()
    form = ConnectionForm()
    devices = Device.objects.all().select_related('credential', 'network', 'device_template')
    templates = DeviceTemplate.objects.all().order_by('-official', 'name')
    credentials = Credential.objects.all().order_by('name')
    connections = Connection.objects.filter(
        connection_type=Connection.ConnectionType.CENTRALIZED
    ).values('id', 'name', 'cloud_id')
    return render(request, 'Networks.html', {
        'networks': networks,
        'form': form,
        'devices': devices,
        'templates': templates,
        'credentials': credentials,
        'connections': connections,
    })

def Onboarding(request):
    from PipelineManager.models import Connection
    connections   = Connection.objects.all().values('id', 'name', 'cloud_id')
    credentials   = Credential.objects.all().order_by('name')
    networks      = Network.objects.all().order_by('name')
    templates     = DeviceTemplate.objects.exclude(name='default').order_by('-official', 'name')
    devices       = Device.objects.all().select_related('credential', 'network', 'device_template')
    from PipelineManager.forms import ConnectionForm
    form = ConnectionForm()
    return render(request, 'Onboarding.html', {
        'connections':  connections,
        'credentials':  credentials,
        'networks':     networks,
        'templates':    templates,
        'devices':      devices,
        'device_count': devices.count(),
        'form':         form,
    })


@require_admin_role
def CheckDeviceType(request):
    """
    Lightweight SNMP probe: GET sysDescr (1.3.6.1.2.1.1.1.0) from an arbitrary
    host using a stored credential, then run suggest_device_template() to find
    the best matching template.

    POST body (JSON): { host, port (optional, default 161), credential_id }

    Returns:
        {
            success: bool,
            sys_descr: str,
            matched_template: {id, name, vendor, description, matching_rules} | null,
            error: str  (only on failure)
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data          = json.loads(request.body)
        host          = (data.get('host') or '').strip()
        port          = int(data.get('port') or 161)
        credential_id = data.get('credential_id')

        if not host:
            return JsonResponse({'success': False, 'error': 'host is required'}, status=400)
        if not credential_id:
            return JsonResponse({'success': False, 'error': 'credential_id is required'}, status=400)

        credential = Credential.objects.get(pk=credential_id)
    except Credential.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Credential not found'}, status=404)
    except (json.JSONDecodeError, Exception) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    # ── Perform a single-OID SNMP GET for sysDescr ────────────────────────────
    sys_descr = _snmp_get_sys_descr(host, port, credential)
    if sys_descr is None:
        return JsonResponse({
            'success': False,
            'error': f'Could not reach {host}:{port} — check the address and credential, '
                     'and ensure the device is accessible from LogstashUI.',
        })

    # ── Match against templates ────────────────────────────────────────────────
    from .snmp_crud import suggest_device_template
    matched_ids = suggest_device_template(sys_descr)

    matched_template = None
    if matched_ids:
        tpl = DeviceTemplate.objects.filter(pk=matched_ids[0]).first()
        if tpl:
            matched_template = {
                'id':            tpl.id,
                'name':          tpl.name,
                'vendor':        tpl.vendor,
                'description':   tpl.description,
                'matching_rules': tpl.matching_rules,
                'profile_names': list(tpl.profiles.values_list('name', flat=True)),
            }

    return JsonResponse({
        'success':          True,
        'sys_descr':        sys_descr,
        'matched_template': matched_template,
    })


def _snmp_get_sys_descr(host, port, credential):
    """
    Do a single SNMP GET for sysDescr.0 and return the string value, or None on failure.
    Runs in a background thread so the async loop is isolated.
    Timeout: 8 seconds (generous enough for slow devices, fast enough to feel responsive).
    """
    import asyncio
    import threading
    from pysnmp.hlapi.v3arch.asyncio import (
        SnmpEngine, CommunityData, UsmUserData, UdpTransportTarget,
        ContextData, ObjectType, ObjectIdentity, get_cmd,
        usmHMACMD5AuthProtocol, usmHMACSHAAuthProtocol,
        usmDESPrivProtocol, usm3DESEDEPrivProtocol,
        usmAesCfb128Protocol, usmAesCfb192Protocol, usmAesCfb256Protocol,
    )

    SYS_DESCR_OID = '1.3.6.1.2.1.1.1.0'

    def _build_auth(cred):
        if cred.version in ('1', '2c'):
            community = cred.get_community()
            if not community:
                raise ValueError('No community string')
            return CommunityData(community, mpModel=0 if cred.version == '1' else 1)
        # SNMPv3
        if cred.security_level == 'noAuthNoPriv':
            return UsmUserData(cred.security_name)
        proto_map = {
            'md5': usmHMACMD5AuthProtocol,
            'sha': usmHMACSHAAuthProtocol,
        }
        auth_proto = proto_map.get((cred.auth_protocol or '').lower(), usmHMACSHAAuthProtocol)
        if cred.security_level == 'authNoPriv':
            return UsmUserData(cred.security_name, authKey=cred.get_auth_pass(), authProtocol=auth_proto)
        priv_map = {
            'des': usmDESPrivProtocol, '3des': usm3DESEDEPrivProtocol,
            'aes': usmAesCfb128Protocol, 'aes128': usmAesCfb128Protocol,
            'aes192': usmAesCfb192Protocol, 'aes256': usmAesCfb256Protocol,
        }
        priv_proto = priv_map.get((cred.priv_protocol or '').lower(), usmDESPrivProtocol)
        return UsmUserData(cred.security_name, authKey=cred.get_auth_pass(),
                           authProtocol=auth_proto, privKey=cred.get_priv_pass(),
                           privProtocol=priv_proto)

    async def _fetch():
        auth  = _build_auth(credential)
        xport = await UdpTransportTarget.create((host, port), timeout=5, retries=1)
        errInd, errStatus, _, varBinds = await get_cmd(
            SnmpEngine(), auth, xport, ContextData(),
            ObjectType(ObjectIdentity(SYS_DESCR_OID))
        )
        if errInd or errStatus:
            return None
        return str(varBinds[0][1]) if varBinds else None

    result    = [None]
    exception = [None]

    def _run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result[0] = loop.run_until_complete(_fetch())
            loop.close()
        except Exception as exc:
            exception[0] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=10)
    if t.is_alive() or exception[0]:
        return None
    return result[0]

def Devices(request):
    from PipelineManager.models import Connection
    devices = Device.objects.all().select_related('credential', 'network', 'device_template')
    templates = DeviceTemplate.objects.all().order_by('-official', 'name')
    credentials = Credential.objects.all().order_by('name')
    form = ConnectionForm()
    connections = Connection.objects.filter(
        connection_type=Connection.ConnectionType.CENTRALIZED
    ).values('id', 'name', 'cloud_id')
    return render(request, 'Devices.html', {'devices': devices, 'templates': templates, 'credentials': credentials, 'form': form, 'connections': connections})

def DeviceTemplates(request):
    from django.db.models import Count
    from PipelineManager.models import Connection
    
    # Load all device templates from database (includes synced official templates)
    device_templates = []
    for template in DeviceTemplate.objects.annotate(device_count=Count('devices')).prefetch_related('profiles').order_by('-official', 'name'):
        # Create a friendly display name from the template name
        display_name = template.name.replace('_', ' ').title()
        
        # Count the number of profiles associated with this template
        profile_count = template.profiles.count()
        
        device_templates.append({
            'name': template.name,
            'display_name': display_name,
            'official': template.official,
            'description': template.description,
            'vendor': template.vendor,
            'model': template.model,
            'product': template.product,
            'device_count': template.device_count,
            'profile_count': profile_count,
            'id': template.id
        })
    
    # Load official profiles from JSON files (for Profiles tab)
    official_profiles = []
    official_profiles_dir = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
    
    if os.path.exists(official_profiles_dir):
        for filename in os.listdir(official_profiles_dir):
            if filename.endswith('.json'):
                profile_name = filename[:-5]  # Remove .json extension
                # Convert filename to display name (e.g., cisco_ios -> Cisco Ios)
                display_name = profile_name.replace('_', ' ').title()
                
                # Load the JSON file to get description, vendor, and product
                profile_path = os.path.join(official_profiles_dir, filename)
                description = ''
                vendor = ''
                product = ''
                try:
                    with open(profile_path, 'r') as f:
                        profile_data = json.load(f)
                        description = profile_data.get('description', '')
                        vendor = profile_data.get('vendor', '')
                        product = profile_data.get('product', '')
                except Exception:
                    profile_data = {}  # If we can't load the file, just use empty dict
                
                # Count how many device templates use this profile
                template_count = DeviceTemplate.objects.filter(profiles__name=profile_name).count()
                
                official_profiles.append({
                    'name': profile_name,
                    'display_name': display_name,
                    'is_official': True,
                    'description': description,
                    'vendor': vendor,
                    'product': product,
                    'profile_data': json.dumps(profile_data),
                    'template_count': template_count
                })
    
    # Load user profiles from database (exclude placeholders)
    user_profiles = []
    for profile in Profile.objects.all():
        # Skip placeholder profiles (those with is_official_placeholder flag)
        if profile.profile_data.get('is_official_placeholder'):
            continue
        
        # Count how many device templates use this profile
        template_count = DeviceTemplate.objects.filter(profiles__id=profile.id).count()
        
        user_profiles.append({
            'name': profile.name,
            'display_name': profile.name.replace('_', ' ').title(),
            'is_official': False,
            'description': profile.description,
            'vendor': profile.vendor,
            'product': profile.product,
            'profile_data': json.dumps(profile.profile_data),
            'template_count': template_count
        })
    
    # Combine and sort profiles alphabetically
    all_profiles = official_profiles + user_profiles
    all_profiles.sort(key=lambda x: x['display_name'])
    
    connections = Connection.objects.filter(
        connection_type=Connection.ConnectionType.CENTRALIZED
    ).values('id', 'name', 'cloud_id')

    devices = Device.objects.all().select_related('credential', 'network', 'device_template')
    snmp_test_templates = DeviceTemplate.objects.all().order_by('-official', 'name')
    snmp_test_credentials = Credential.objects.all().order_by('name')
    return render(request, 'DeviceTemplates.html', {
        'device_templates': device_templates,
        'profiles': all_profiles,
        'connections': connections,
        'devices': devices,
        'templates': snmp_test_templates,
        'credentials': snmp_test_credentials,
    })

def Credentials(request):
    from django.db.models import Count
    from PipelineManager.models import Connection
    credentials = Credential.objects.annotate(device_count=Count('devices')).order_by('name')
    devices = Device.objects.all().select_related('credential', 'network', 'device_template')
    templates = DeviceTemplate.objects.all().order_by('-official', 'name')
    connections = Connection.objects.filter(
        connection_type=Connection.ConnectionType.CENTRALIZED
    ).values('id', 'name', 'cloud_id')
    return render(request, 'Credentials.html', {
        'credentials': credentials,
        'devices': devices,
        'templates': templates,
        'connections': connections,
    })

def Overview(request):
    """SNMP Overview page with metrics and statistics"""
    return render(request, 'Overview.html')

def GetOverviewMetrics(request):
    """API endpoint to get overview metrics"""
    try:
        # Get total devices from database
        total_devices = Device.objects.count()
        
        # Get discovered devices count from Elasticsearch
        discovered_result = get_discovered_devices_count()
        
        # Get template data coverage
        template_coverage_result = get_template_data_categories()

        # Get high resource usage
        high_usage_result = get_high_resource_usage()
        
        # Combine errors from all queries
        all_errors = []
        if discovered_result.get('errors'):
            all_errors.extend(discovered_result.get('errors'))
        if template_coverage_result.get('errors'):
            all_errors.extend(template_coverage_result.get('errors'))
        if high_usage_result.get('errors'):
            all_errors.extend(high_usage_result.get('errors'))
        
        return JsonResponse({
            'success': True,
            'metrics': {
                'total_devices': total_devices,
                'discovered_devices': discovered_result.get('count', 0)
            },
            'data_quality': {
                'templates': template_coverage_result.get('templates', [])
            },
            'high_usage': {
                'high_cpu': high_usage_result.get('high_cpu', []),
                'high_memory': high_usage_result.get('high_memory', [])
            },
            'errors': all_errors if all_errors else None
        }, status=200)
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_admin_role
def CheckAgentBuilderResources(request):
    """
    Check whether the SNMP AI template generation resources (tools, skills, agents)
    exist in Kibana and whether they match our expected definitions.

    POST body (JSON):
        connection_id  – int, required
        kibana_url     – str, optional override for URL-based connections

    Returns JSON matching the shape from AgentBuilder.check_resources().
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    connection_id  = data.get('connection_id')
    kibana_url     = data.get('kibana_url') or None

    if not connection_id:
        return JsonResponse({'error': 'connection_id is required'}, status=400)

    try:
        from Common.ai.agent_builder import AgentBuilder, load_resources_from_directory

        _assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'device_template_generation')
        tools, skills, agents = load_resources_from_directory(_assets_dir)

        builder = AgentBuilder(
            connection_id=int(connection_id),
            kibana_url_override=kibana_url,
        )
        results = builder.check_resources(
            tools=tools,
            skills=skills,
            agents=agents,
        )
        return JsonResponse(results)

    except Exception as e:
        return JsonResponse({'error': str(e), 'api_available': False}, status=500)


@require_admin_role
def InstallAgentBuilderPackage(request):
    """
    Create or overwrite ALL Agent Builder resources for SNMP AI template
    generation in Kibana (tools → skills → agents order).

    POST body (JSON):
        connection_id – int, required
        kibana_url    – str, optional override for URL-based connections

    Returns:
        { success: bool, results: [ { type, id, action, success, error? } ] }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    connection_id = data.get('connection_id')
    kibana_url    = data.get('kibana_url') or None

    if not connection_id:
        return JsonResponse({'error': 'connection_id is required'}, status=400)

    try:
        from Common.ai.agent_builder import AgentBuilder, load_resources_from_directory

        _assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'device_template_generation')
        tools, skills, agents = load_resources_from_directory(_assets_dir)

        builder = AgentBuilder(
            connection_id=int(connection_id),
            kibana_url_override=kibana_url,
        )
        result = builder.apply_all_resources(
            tools=tools,
            skills=skills,
            agents=agents,
        )
        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_admin_role
def GenerateTemplateAndProfiles(request):
    """
    Orchestrate SNMP AI template/profile generation.

    Thin view wrapper — all stream logic lives in ``ai_template_generation.py``.

    POST body (JSON):
        connection_id – int, required
        kibana_url    – str, optional (URL-based connections only)
        walk_text     – str, required (raw SNMP walk output)
        inference_id  – str, required

    Response: text/event-stream  (see ``ai_template_generation.stream_template_generation``)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    connection_id = body.get('connection_id')
    kibana_url    = body.get('kibana_url') or None
    walk_text     = body.get('walk_text', '')
    inference_id  = body.get('inference_id') or None

    if not connection_id:
        return JsonResponse({'error': 'connection_id is required'}, status=400)
    if not walk_text.strip():
        return JsonResponse({'error': 'walk_text is required'}, status=400)

    from .ai_template_generation import stream_template_generation

    response = StreamingHttpResponse(
        stream_template_generation(connection_id, kibana_url, walk_text, inference_id),
        content_type='text/event-stream',
    )
    response['X-Accel-Buffering'] = 'no'
    response['Cache-Control']     = 'no-cache'
    return response


_SNMP_TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'snmp_template.json')


def _load_snmp_template():
    with open(_SNMP_TEMPLATE_PATH, 'r', encoding='utf-8') as fh:
        return json.load(fh)


@require_admin_role
def CheckSNMPIndexTemplate(request):
    """
    Check whether the SNMP index template is installed and up to date on each
    of the supplied Elasticsearch connections.

    POST body (JSON):
        connection_ids – [int, ...], required

    Returns:
        {
            "results": [
                {
                    "connection_id": int,
                    "connection_name": str,
                    "status": "not_installed" | "installed" | "installed_but_outdated" | "error",
                    "differences": [str],
                    "error": str | null
                }
            ]
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    connection_ids = data.get('connection_ids', [])
    if not connection_ids:
        return JsonResponse({'error': 'connection_ids is required'}, status=400)

    from Common.elastic_utils import check_index_template
    from PipelineManager.models import Connection

    try:
        template_definition = _load_snmp_template()
    except Exception as e:
        return JsonResponse({'error': f'Failed to load SNMP template: {e}'}, status=500)

    template_name = template_definition.get('_meta', {}).get('template_name', 'metrics-snmp.polling')

    results = []
    for conn_id in connection_ids:
        try:
            conn = Connection.objects.get(id=int(conn_id))
            result = check_index_template(int(conn_id), template_name, template_definition)
            results.append({
                'connection_id': conn_id,
                'connection_name': conn.name,
                **result,
            })
        except Connection.DoesNotExist:
            results.append({
                'connection_id': conn_id,
                'connection_name': f'Connection {conn_id}',
                'status': 'error',
                'differences': [],
                'error': f'Connection {conn_id} not found',
            })
        except Exception as e:
            results.append({
                'connection_id': conn_id,
                'connection_name': f'Connection {conn_id}',
                'status': 'error',
                'differences': [],
                'error': str(e),
            })

    return JsonResponse({'results': results})


@require_admin_role
def InstallSNMPIndexTemplate(request):
    """
    Install or update the SNMP index template on each of the supplied
    Elasticsearch connections.

    POST body (JSON):
        connection_ids – [int, ...], required

    Returns:
        {
            "success": bool,
            "results": [
                { "connection_id": int, "connection_name": str, "success": bool, "error": str? }
            ]
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    connection_ids = data.get('connection_ids', [])
    if not connection_ids:
        return JsonResponse({'error': 'connection_ids is required'}, status=400)

    from Common.elastic_utils import create_index_template
    from PipelineManager.models import Connection

    try:
        template_definition = _load_snmp_template()
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Failed to load SNMP template: {e}'}, status=500)

    template_name = template_definition.get('_meta', {}).get('template_name', 'metrics-snmp.polling')

    overall_success = True
    results = []
    for conn_id in connection_ids:
        try:
            conn = Connection.objects.get(id=int(conn_id))
            create_index_template(int(conn_id), template_name, template_definition)
            results.append({
                'connection_id': conn_id,
                'connection_name': conn.name,
                'success': True,
            })
        except Connection.DoesNotExist:
            overall_success = False
            results.append({
                'connection_id': conn_id,
                'connection_name': f'Connection {conn_id}',
                'success': False,
                'error': f'Connection {conn_id} not found',
            })
        except Exception as e:
            overall_success = False
            results.append({
                'connection_id': conn_id,
                'connection_name': f'Connection {conn_id}',
                'success': False,
                'error': str(e),
            })

    return JsonResponse({'success': overall_success, 'results': results})


@require_admin_role
def ImportAIGeneratedDefinitions(request):
    """
    Persist the profiles and device template produced by GenerateTemplateAndProfiles.

    POST body (JSON):
        profiles        – list of profile dicts (may be empty)
        device_template – device template dict

    Each item in `profiles` must have at minimum a non-empty `name`.
    The `device_template` must have `name` and a `profiles` list (all profile
    names the template should reference, both new and existing catalog ones).

    Per-item actions:
        created  – new record inserted
        updated  – existing user-owned record overwritten in place
        skipped  – record already exists as official (official_key set) and
                   cannot be overwritten; still linked to the template

    Returns:
        {
            "success": bool,
            "profiles": [{"name", "action", "id", "reason?"}],
            "template": {"name", "action", "id", "reason?"},
            "errors": ["..."]
        }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    raw_profiles = data.get('profiles', [])
    raw_template = data.get('device_template')

    # ── Top-level shape validation ─────────────────────────────────────────────
    errors = []

    if not isinstance(raw_profiles, list):
        return JsonResponse({'error': '`profiles` must be a list'}, status=400)
    if not isinstance(raw_template, dict):
        return JsonResponse({'error': '`device_template` must be an object'}, status=400)

    template_name = (raw_template.get('name') or '').strip()
    if not template_name:
        return JsonResponse({'error': '`device_template.name` is required'}, status=400)

    template_profile_names = raw_template.get('profiles', [])
    if not isinstance(template_profile_names, list):
        return JsonResponse({'error': '`device_template.profiles` must be a list'}, status=400)

    # ── Validate each profile ──────────────────────────────────────────────────
    def _validate_profile(p, idx):
        errs = []
        if not isinstance(p, dict):
            errs.append(f'Profile[{idx}] is not an object')
            return errs
        name = (p.get('name') or '').strip()
        if not name:
            errs.append(f'Profile[{idx}] missing required field: name')
        for section in ('get', 'walk', 'table'):
            if section in p and not isinstance(p[section], dict):
                errs.append(f'Profile[{idx}] ({name or "?"}): `{section}` must be an object')
        return errs

    for i, prof in enumerate(raw_profiles):
        errors.extend(_validate_profile(prof, i))

    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=422)

    # ── Import profiles ────────────────────────────────────────────────────────
    from django.core.exceptions import ValidationError as DjangoValidationError

    profile_results = []
    name_to_id = {}  # track created/updated profile IDs for template linking

    for prof in raw_profiles:
        p_name  = prof['name'].strip()
        p_data  = {k: prof[k] for k in ('get', 'walk', 'table', 'normalizers') if k in prof}
        if 'get'        not in p_data: p_data['get']        = {}
        if 'walk'       not in p_data: p_data['walk']       = {}
        if 'table'      not in p_data: p_data['table']      = {}
        if 'normalizers' not in p_data: p_data['normalizers'] = []

        existing = Profile.objects.filter(name=p_name).first()

        if existing and existing.official_key:
            profile_results.append({
                'name':   p_name,
                'action': 'skipped',
                'id':     existing.id,
                'reason': 'Official profile — cannot overwrite',
            })
            name_to_id[p_name] = existing.id
            continue

        action = 'updated' if existing else 'created'
        profile = existing or Profile(name=p_name)
        profile.description = (prof.get('description') or '').strip()
        profile.vendor      = (prof.get('vendor') or 'Any').strip()
        profile.product     = (prof.get('product') or '').strip()
        profile.profile_data = p_data
        profile.normalizers  = p_data.pop('normalizers', [])
        profile.profile_data = {k: p_data[k] for k in ('get', 'walk', 'table') if k in p_data}

        try:
            profile.save()
            profile_results.append({'name': p_name, 'action': action, 'id': profile.id})
            name_to_id[p_name] = profile.id
        except (DjangoValidationError, Exception) as exc:
            errors.append(f'Profile "{p_name}": {exc}')
            profile_results.append({'name': p_name, 'action': 'error', 'reason': str(exc)})

    # ── Import device template ─────────────────────────────────────────────────
    template_result = {}

    existing_tpl = DeviceTemplate.objects.filter(name=template_name).first()

    if existing_tpl and existing_tpl.official:
        template_result = {
            'name':   template_name,
            'action': 'skipped',
            'id':     existing_tpl.id,
            'reason': 'Official template — cannot overwrite',
        }
        template = existing_tpl
    else:
        action = 'updated' if existing_tpl else 'created'
        template = existing_tpl or DeviceTemplate(name=template_name, official=False)
        template.description    = (raw_template.get('description') or '').strip()
        template.vendor         = (raw_template.get('vendor') or 'Any').strip()
        template.product        = (raw_template.get('product') or '').strip()
        template.model          = (raw_template.get('model') or '').strip()
        template.matching_rules = raw_template.get('matching_rules', [])

        try:
            template.save()

            # Resolve ALL profile names the template should reference:
            # first the ones we just created/updated, then look up the rest by name.
            linked_ids = set()
            for pname in template_profile_names:
                if pname in name_to_id:
                    linked_ids.add(name_to_id[pname])
                else:
                    db_prof = Profile.objects.filter(name=pname).first()
                    if not db_prof:
                        # Try the official name with .json suffix
                        db_prof = Profile.objects.filter(name=f'{pname}.json').first()
                    if db_prof:
                        linked_ids.add(db_prof.id)
                    else:
                        errors.append(
                            f'Template profile "{pname}" not found in database — '
                            'install official data first or create the profile manually'
                        )

            template.profiles.set(linked_ids)

            from .models import SNMPDeploymentState
            SNMPDeploymentState.mark_config_changed()

            template_result = {'name': template_name, 'action': action, 'id': template.id}

        except (DjangoValidationError, Exception) as exc:
            errors.append(f'Template "{template_name}": {exc}')
            template_result = {'name': template_name, 'action': 'error', 'reason': str(exc)}

    overall_success = not any(r.get('action') == 'error' for r in profile_results) \
                      and template_result.get('action') != 'error'

    return JsonResponse({
        'success':  overall_success,
        'profiles': profile_results,
        'template': template_result,
        'errors':   errors,
    })

