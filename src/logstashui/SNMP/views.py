#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse

from .models import Credential, Network, Device, Profile, DeviceTemplate
from PipelineManager.forms import ConnectionForm
from .overview import get_discovered_devices_count, get_template_data_categories, get_high_resource_usage

import datetime
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


def GenerateTemplateAndProfiles(request):
    """
    Orchestrate SNMP AI template/profile generation.

    1. Splits the raw walk into 5 000-line chunks.
    2. Bulk-indexes the chunks into a timestamped ES index.
    3. Invokes the ``snmp-profile-author`` Agent Builder agent with the index
       name as context and streams its response back to the browser via SSE.

    POST body (JSON):
        connection_id – int, required
        kibana_url    – str, optional (URL-based connections only)
        walk_text     – str, required (raw SNMP walk output)

    Response: text/event-stream — each event is a JSON object:
        {"phase": "indexing",      "message": "..."}
        {"phase": "indexing_done", "message": "..."}
        {"phase": "invoking",      "message": "..."}
        {"phase": "agent_chunk",   "data":    <raw chunk dict from Kibana>}
        {"phase": "done"}
        {"phase": "error",         "message": "..."}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, Exception):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    connection_id = data.get('connection_id')
    kibana_url    = data.get('kibana_url') or None
    walk_text     = data.get('walk_text', '')
    inference_id  = data.get('inference_id') or None

    if not connection_id:
        return JsonResponse({'error': 'connection_id is required'}, status=400)
    if not walk_text.strip():
        return JsonResponse({'error': 'walk_text is required'}, status=400)

    def _sse(payload):
        return f"data: {json.dumps(payload)}\n\n"

    def _stream():
        from Common.elastic_utils import bulk_index_documents
        from Common.ai.agent_builder import AgentBuilder

        if not inference_id:
            yield _sse({"phase": "error", "message": "No inference model selected."})
            return

        # ── 1. Chunk the walk into 5 000-line documents ───────────────────────
        lines      = walk_text.splitlines()
        chunk_size = 5000
        chunks     = [
            {"message": "\n".join(lines[i:i + chunk_size])}
            for i in range(0, len(lines), chunk_size)
        ]

        ts         = datetime.datetime.utcnow().strftime('%Y%m%dt%H%M%Sz')
        index_name = f"snmp-template_generation-{ts}"

        yield _sse({
            "phase":   "indexing",
            "message": f"Indexing walk data into Elasticsearch ({len(chunks)} chunk(s) → {index_name})…",
        })

        # ── 2. Bulk index ─────────────────────────────────────────────────────
        try:
            bulk_index_documents(int(connection_id), index_name, chunks)
        except Exception as exc:
            yield _sse({"phase": "error", "message": f"Indexing failed: {exc}"})
            return

        yield _sse({"phase": "indexing_done"})

        # ── 3. Build the agent prompt ─────────────────────────────────────────
        user_message = (
            f"I have indexed a raw SNMP walk into Elasticsearch index `{index_name}`. "
            f"The walk is split into {len(chunks)} document(s) of up to 5,000 lines each, "
            f"stored in the `message` field. "
            f"Please analyse the OIDs present and generate a LogstashUI device template "
            f"with the appropriate profiles. Consult the SNMP Catalog knowledge in your "
            f"instructions to reuse any existing OIDs and profiles, then produce JSON for "
            f"any new profiles required."
        )

        # Build configuration_overrides: agent instructions + full catalog appended.
        # Skills can't be linked to agents via the API, so we inject the catalog here.
        _base = os.path.dirname(os.path.abspath(__file__))
        _agent_json = os.path.join(_base, 'assets', 'device_template_generation', 'agents', 'snmp-profile-author.json')
        _catalog_md = os.path.join(_base, 'data', 'template_profile_context.md')
        try:
            with open(_agent_json, 'r', encoding='utf-8') as fh:
                _agent_def = json.load(fh)
            _base_instructions = _agent_def.get('configuration', {}).get('instructions', '')
        except Exception:
            _base_instructions = ''
        try:
            with open(_catalog_md, 'r', encoding='utf-8') as fh:
                _catalog = fh.read()
        except Exception:
            _catalog = ''

        _full_instructions = _base_instructions
        if _catalog:
            _full_instructions += f"\n\n---\n\n## SNMP Catalog\n\n{_catalog}"

        configuration_overrides = {"instructions": _full_instructions} if _full_instructions else None

        yield _sse({
            "phase":   "invoking",
            "message": f"Invoking SNMP Profile Author ({inference_id})…",
        })

        # ── 4. Stream agent response ──────────────────────────────────────────
        try:
            builder = AgentBuilder(
                connection_id=int(connection_id),
                kibana_url_override=kibana_url,
            )
            kibana_base = builder._kibana_url
            for chunk in builder.invoke_agent(
                'snmp-profile-author', user_message,
                inference_id=inference_id,
                configuration_overrides=configuration_overrides,
            ):
                err = chunk.get('error')
                if err:
                    msg = err if isinstance(err, str) else json.dumps(err)
                    yield _sse({"phase": "error", "message": msg})
                    return

                event_type = chunk.get('event')
                # Agent Builder wraps the actual payload one level deep:
                # SSE data line parses to {"data": {<actual content>}}
                outer_data = chunk.get('data') or {}
                data       = outer_data.get('data') if isinstance(outer_data.get('data'), dict) else outer_data

                if event_type == 'conversation_id_set':
                    conv_id = data.get('conversation_id', '')
                    if conv_id:
                        conv_url = (
                            f"{kibana_base}/app/agent_builder/agents"
                            f"/snmp-profile-author/conversations/{conv_id}"
                        )
                        yield _sse({"phase": "conversation_link", "url": conv_url, "conversation_id": conv_id})

                elif event_type == 'conversation_created':
                    title = data.get('title', '')
                    if title:
                        yield _sse({"phase": "conversation_title", "title": title})

                elif event_type == 'reasoning':
                    reasoning_text = data.get('reasoning', '')
                    if reasoning_text and not data.get('transient', False):
                        yield _sse({"phase": "reasoning", "message": reasoning_text})

                elif event_type == 'message_chunk':
                    text = data.get('text_chunk', '')
                    if text:
                        yield _sse({"phase": "agent_chunk", "data": {"text": text}})

                elif event_type == 'tool_call':
                    tool_id = data.get('tool_id', 'unknown')
                    yield _sse({"phase": "tool_call", "message": f"Calling tool: {tool_id}…"})

                elif event_type == 'tool_result':
                    yield _sse({"phase": "tool_done"})

                elif event_type in ('message_complete', 'round_complete', 'thinking_complete'):
                    pass  # Redundant / very large — content already built from message_chunk events

        except Exception as exc:
            yield _sse({"phase": "error", "message": f"Agent invocation failed: {exc}"})
            return

        yield _sse({"phase": "done"})

    response = StreamingHttpResponse(_stream(), content_type='text/event-stream')
    response['X-Accel-Buffering'] = 'no'
    response['Cache-Control']     = 'no-cache'
    return response


_SNMP_TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'snmp_template.json')


def _load_snmp_template():
    with open(_SNMP_TEMPLATE_PATH, 'r', encoding='utf-8') as fh:
        return json.load(fh)


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

