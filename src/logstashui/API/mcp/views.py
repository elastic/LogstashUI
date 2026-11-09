"""Stateless MCP Streamable HTTP endpoint at ``/api/mcp``.

Each POST carries one JSON-RPC message and gets one ``application/json``
reply. No SSE stream and no ``Mcp-Session-Id``: the transport spec allows
both to be omitted, which keeps this compatible with gunicorn + gevent.

Examples:
    curl -X POST https://logstashui.example.com/api/mcp \\
      -H "Authorization: ApiKey $KEY" -H "Content-Type: application/json" \\
      -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
"""

import json
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from API.guides import GUIDES
from API.mcp.dispatch import ToolArgumentError, call_tool, validate_arguments
from API.mcp.tools import STATUS_HINTS, TOOLSETS, parse_toolsets, select_tools

logger = logging.getLogger(__name__)

SUPPORTED_PROTOCOL_VERSIONS = ('2025-06-18', '2025-03-26')

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

_INSTRUCTIONS = (
    'LogstashUI is the control plane for Logstash: it authors, simulates, and deploys Logstash '
    'pipelines (LSCL), manages LogstashAgent nodes through policies, and runs SNMP monitoring.\n'
    '\n'
    'Vocabulary: an agent pipeline lives in a policy and goes live only when the policy is '
    'deployed (policies_deploy). A CPM pipeline is stored in Elasticsearch through Centralized '
    'Pipeline Management and is live as soon as it is written. Both are Logstash pipelines; '
    'neither is an Elasticsearch ingest pipeline. The pipelines_* tools handle both: pass the '
    'pipeline_id or connection_id + name that pipelines_find returns.\n'
    '\n'
    'Guides (guides_get(topic)): '
    + ', '.join(GUIDES) + '. Read concepts before your first change and the guide for a task '
    'before starting it.\n'
    '\n'
    'How to work:\n'
    '- Read before you write, and write only when the user asked for a change.\n'
    '- When the user names a pipeline, locate it with pipelines_find and follow its next_steps. '
    'Never substitute config you wrote for a pipeline the user named.\n'
    "- If a name or ID doesn't match exactly, list the candidates and confirm with the user "
    'before acting.\n'
    '- Before policies_deploy or snmp_deploy_apply, show the user policies_diff or '
    'snmp_deploy_diff and wait for confirmation.\n'
    '- Follow next_steps on results and hint on errors.\n'
    '- Responses are compact by default. Ask for more (simulate detail=full, include_lscl, '
    'include_config) only when you need it.\n'
    '\n'
    "Use only these tools. If a tool fails or can't do what is needed, report what happened "
    "and stop. Don't switch to the REST API, the database, the web UI, or config files unless "
    'the user explicitly asks for that.\n'
    '\n'
    "Tools this API key's role can't use are not listed."
)


@csrf_exempt
def mcp_endpoint(request):
    """Handle one MCP JSON-RPC message.

    Args:
        request: POST with a single JSON-RPC 2.0 object. Optional
            ``?toolsets=a,b`` limits which tools are listed and callable.
            Admin-only tools are left out of ``tools/list`` for other roles;
            calling one still returns the view's 403.

    Returns:
        ``JsonResponse`` with the JSON-RPC reply, ``202`` for notifications,
        or an HTTP error for transport-level failures (405, 403, 401, 415).
    """
    if request.method != 'POST':
        response = JsonResponse(
            {'error': 'MCP endpoint accepts POST only; this server does not offer an SSE stream.'},
            status=405,
        )
        response['Allow'] = 'POST'
        return response

    if not _origin_allowed(request):
        return JsonResponse({'error': 'Origin not allowed.'}, status=403)

    if not request.user.is_authenticated:
        return JsonResponse(
            {'error': 'Authentication required. Provide Authorization: ApiKey <token>.'},
            status=401,
        )

    if 'application/json' not in (request.content_type or ''):
        return JsonResponse({'error': 'Content-Type must be application/json.'}, status=415)

    try:
        message = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return _error(None, PARSE_ERROR, 'Parse error: body is not valid JSON.')

    if isinstance(message, list):
        return _error(None, INVALID_REQUEST, 'Batch requests are not supported.')
    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' \
            or not isinstance(message.get('method'), str):
        return _error(message.get('id') if isinstance(message, dict) else None,
                      INVALID_REQUEST, 'Invalid JSON-RPC 2.0 request.')

    if 'id' not in message:
        # Notifications (e.g. notifications/initialized) need no reply.
        return HttpResponse(status=202)

    msg_id = message['id']
    method = message['method']
    params = message.get('params') or {}
    if not isinstance(params, dict):
        return _error(msg_id, INVALID_PARAMS, 'params must be an object.')

    toolsets, unknown = parse_toolsets(request.GET.get('toolsets'))
    if unknown:
        return _error(
            msg_id, INVALID_PARAMS,
            f"Unknown toolset(s): {', '.join(unknown)}. Valid toolsets: {', '.join(TOOLSETS)}.",
        )
    tools = select_tools(toolsets)

    if method == 'initialize':
        return _result(msg_id, _initialize(params))
    if method == 'ping':
        return _result(msg_id, {})
    if method == 'tools/list':
        is_admin = getattr(getattr(request.user, 'profile', None), 'role', None) == 'admin'
        listed = [tool.to_mcp() for tool in tools.values() if is_admin or not tool.admin_only]
        return _result(msg_id, {'tools': listed})
    if method == 'tools/call':
        return _tools_call(request, msg_id, params, tools)
    return _error(msg_id, METHOD_NOT_FOUND, f'Method not found: {method}')


def _initialize(params):
    requested = params.get('protocolVersion')
    version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
    return {
        'protocolVersion': version,
        'capabilities': {'tools': {'listChanged': False}},
        'serverInfo': {'name': 'LogstashUI', 'version': getattr(settings, '__VERSION__', '')},
        'instructions': _INSTRUCTIONS,
    }


def _tools_call(request, msg_id, params, tools):
    name = params.get('name')
    tool = tools.get(name)
    if tool is None:
        return _error(msg_id, INVALID_PARAMS, f'Unknown tool: {name}')

    try:
        tool, arguments = tool.resolve(params.get('arguments') or {})
        arguments = validate_arguments(tool, arguments)
        status, payload = call_tool(request, tool, arguments)
    except ToolArgumentError as exc:
        return _result(msg_id, _tool_result(
            {'success': False, 'error': str(exc), 'hint': STATUS_HINTS[400]}, is_error=True,
        ))
    except Exception:
        logger.exception("MCP: tool %s failed for user %s", name, request.user.username)
        return _result(msg_id, _tool_result(
            {'success': False, 'error': 'An internal error occurred. Check server logs.'},
            is_error=True,
        ))

    logger.info(
        "MCP: user '%s' called %s -> %s", request.user.username, name, status,
    )
    return _result(msg_id, _tool_result(payload, is_error=status >= 400))


def _tool_result(payload, is_error):
    result = {
        'content': [{'type': 'text', 'text': json.dumps(payload, indent=2, default=str)}],
        'isError': is_error,
    }
    if isinstance(payload, dict):
        result['structuredContent'] = payload
    return result


def _origin_allowed(request):
    """Reject cross-origin browser requests (DNS-rebinding guard from the MCP spec).

    Non-browser MCP clients send no ``Origin`` and are always allowed.
    """
    origin = request.headers.get('Origin')
    if not origin:
        return True
    if urlsplit(origin).netloc == request.get_host():
        return True
    return origin in getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])


def _result(msg_id, result):
    return JsonResponse({'jsonrpc': '2.0', 'id': msg_id, 'result': result})


def _error(msg_id, code, message):
    status = 400 if code in (PARSE_ERROR, INVALID_REQUEST) else 200
    return JsonResponse(
        {'jsonrpc': '2.0', 'id': msg_id, 'error': {'code': code, 'message': message}},
        status=status,
    )
