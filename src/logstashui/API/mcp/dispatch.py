"""Execute an MCP tool by calling its REST API view in-process.

The caller's authenticated user and API token are carried onto a synthetic
request, so the view's own ``api_require_auth`` / ``api_require_admin`` checks
decide what the caller may do.
"""

import json
from urllib.parse import urlencode

from django.test import RequestFactory
from django.urls import NoReverseMatch, resolve, reverse

from API.mcp.tools import PROTECTED_HINT, REDACTED, STATUS_HINTS, ToolArgumentError

#: META keys copied from the MCP request so ``build_absolute_uri`` and
#: ``SECURE_PROXY_SSL_HEADER`` behave as they would for a direct REST call.
_FORWARDED_META = (
    'HTTP_HOST', 'SERVER_NAME', 'SERVER_PORT', 'REMOTE_ADDR', 'wsgi.url_scheme',
    'HTTP_X_FORWARDED_PROTO', 'HTTP_X_FORWARDED_HOST', 'HTTP_X_FORWARDED_FOR',
)


def validate_arguments(tool, arguments):
    """Check required arguments and coerce path parameters.

    Args:
        tool: The :class:`~API.mcp.tools.Tool` being called, already
            resolved to its variant with :meth:`~API.mcp.tools.Tool.resolve`.
        arguments: Raw ``arguments`` object from ``tools/call``.

    Returns:
        A new dict with aliases renamed, the tool's ``defaults`` filled in,
        and integer path parameters coerced from numeric strings.

    Raises:
        ToolArgumentError: If arguments are not an object, an alias conflicts
            with its argument, a required argument is missing, or a path
            parameter has the wrong type.

    Examples:
        >>> from API.mcp.tools import TOOLS_BY_NAME
        >>> validate_arguments(TOOLS_BY_NAME['snmp_networks_get'], {'network_id': '7'})
        {'network_id': 7}
        >>> validate_arguments(TOOLS_BY_NAME['snmp_networks_get'], {'id': 7})
        {'network_id': 7}
    """
    if not isinstance(arguments, dict):
        raise ToolArgumentError('arguments must be an object.')
    arguments = dict(arguments)
    for alias, target in tool.argument_aliases().items():
        if alias not in arguments or alias == target:
            continue
        value = arguments.pop(alias)
        if target in arguments and arguments[target] != value:
            raise ToolArgumentError(f'{alias} and {target} name the same argument; send only {target}.')
        arguments[target] = value
    args = {**tool.defaults, **arguments}

    missing = [name for name in tool.input_schema()['required'] if args.get(name) in (None, '')]
    if missing:
        raise ToolArgumentError(f"Missing required argument(s): {', '.join(missing)}.")

    for name, schema in tool.path_params.items():
        value = args[name]
        if schema['type'] == 'integer':
            if isinstance(value, str) and value.isdigit():
                value = int(value)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ToolArgumentError(f'{name} must be an integer.')
        elif not isinstance(value, str):
            raise ToolArgumentError(f'{name} must be a string.')
        args[name] = value

    if not tool.body:
        unexpected = set(args) - set(tool.path_params) - set(tool.query_params)
        if unexpected:
            raise ToolArgumentError(f"Unexpected argument(s): {', '.join(sorted(unexpected))}.")
    return args


def call_tool(request, tool, arguments):
    """Dispatch ``tool`` to its REST view as the requesting user.

    Args:
        request: The incoming MCP ``HttpRequest`` (already authenticated).
        tool: The :class:`~API.mcp.tools.Tool` to run.
        arguments: Arguments already passed through :func:`validate_arguments`.

    Returns:
        ``(status_code, payload)`` where ``payload`` is the decoded JSON body
        with the tool's ``redact`` keys replaced.

    Raises:
        ToolArgumentError: If the path parameters do not fit the URL pattern.
    """
    args = dict(arguments)
    kwargs = {name: args.pop(name) for name in tool.path_params}
    query = {name: args.pop(name) for name in tool.query_params if name in args}

    try:
        path = reverse(tool.url_name, kwargs=kwargs)
    except NoReverseMatch as exc:
        raise ToolArgumentError(f'Invalid path argument(s): {kwargs}.') from exc
    if query:
        path = f'{path}?{urlencode(query)}'

    body = json.dumps(args) if tool.method in ('POST', 'PUT') else ''
    extra = {key: request.META[key] for key in _FORWARDED_META if key in request.META}
    sub_request = RequestFactory().generic(
        tool.method, path, body, content_type='application/json', **extra
    )
    sub_request.user = request.user
    sub_request._api_token = getattr(request, '_api_token', None)
    if hasattr(request, 'session'):
        sub_request.session = request.session

    match = resolve(sub_request.path_info)
    response = match.func(sub_request, *match.args, **match.kwargs)
    payload = _redact(_decode(response), tool.redact)
    return response.status_code, add_guidance(tool, response.status_code, payload)


def add_guidance(tool, status, payload):
    """Attach ``next_steps`` (success) or a ``hint`` (error) to ``payload``.

    Errors with ``code: protected`` always get :data:`PROTECTED_HINT`, so a
    write to an official object isn't mistaken for a name conflict.

    On success, ``next_steps`` comes from the tool's ``guidance`` callable when
    it has one, otherwise from its fixed ``next_steps``. Only object payloads
    are annotated; list responses pass through unchanged. The REST API never
    calls this, so its responses stay plain data.

    Args:
        tool: The :class:`~API.mcp.tools.Tool` that ran.
        status: HTTP status code of the REST response.
        payload: Decoded (and redacted) response body.

    Returns:
        The payload, copied and annotated when there is guidance to add.

    Examples:
        >>> from API.mcp.tools import TOOLS_BY_NAME
        >>> add_guidance(TOOLS_BY_NAME['snmp_networks_get'], 404, {'error': 'nope'})['hint']
        'SNMP network not found. Use snmp_networks_list to find the ID.'
    """
    if not isinstance(payload, dict):
        return payload
    if status >= 400:
        if payload.get('code') == 'protected':
            hint = PROTECTED_HINT
        else:
            hint = tool.hints.get(status) or STATUS_HINTS.get(status)
        return {**payload, 'hint': hint} if hint and 'hint' not in payload else payload
    next_steps = tool.guidance(payload) if tool.guidance else tool.next_steps
    if next_steps and 'next_steps' not in payload:
        return {**payload, 'next_steps': next_steps}
    return payload


def _decode(response):
    content = response.content.decode('utf-8', errors='replace')
    if 'application/json' in response.get('Content-Type', ''):
        try:
            return json.loads(content)
        except ValueError:
            pass
    return {'success': response.status_code < 400, 'message': content}


def _redact(value, keys):
    if not keys:
        return value
    if isinstance(value, dict):
        return {k: (REDACTED if k in keys and v else _redact(v, keys)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, keys) for v in value]
    return value
