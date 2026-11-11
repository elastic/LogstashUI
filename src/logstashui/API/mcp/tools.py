"""Declarative MCP tool registry mapped onto REST API routes.

Each :class:`Tool` names the URL pattern and HTTP method it dispatches to;
:mod:`API.mcp.dispatch` builds the request. Arguments are flat: path
parameters, query parameters, and body fields share one ``inputSchema``.
A tool with ``variants`` covers several routes and picks one from the
arguments it gets, so agent and CPM pipelines share one set of tools.

Examples:
    >>> from API.mcp.tools import select_tools
    >>> tools = select_tools(['policies'])
    >>> tools['policies_get'].url_name
    'api-policies-detail'
"""

from dataclasses import dataclass, field

from API.guides import GUIDES

TOOLSETS = ('guides', 'connections', 'pipelines', 'policies', 'snmp')

#: Toolsets that no longer exist. Old client URLs may still name them, so
#: they are ignored instead of rejected.
RETIRED_TOOLSETS = ('security',)

#: Routes deliberately not exposed over MCP, as ``(url_name, method)``.
#: Bootstrap is an unauthenticated setup flow; user and API key management
#: stays out of model reach; enrollment-token creation returns a raw secret
#: that would land in the model's transcript. The pipelines deploy route does
#: the same as ``policies_deploy``, and one tool per destructive action is
#: less for a model to confuse. ``security/me`` only reports the key's role,
#: and tools/list already hides what that role can't call.
EXCLUDED_ROUTES = frozenset({
    ('api-pipeline-deploy', 'POST'),
    ('api-security-me', 'GET'),
    ('api-security-bootstrap', 'GET'),
    ('api-security-bootstrap', 'POST'),
    ('api-security-user-list', 'GET'),
    ('api-security-user-list', 'POST'),
    ('api-security-user-detail', 'GET'),
    ('api-security-user-detail', 'PUT'),
    ('api-security-user-detail', 'DELETE'),
    ('api-security-key-list', 'GET'),
    ('api-security-key-list', 'POST'),
    ('api-security-key-revoke', 'POST'),
    ('api-security-key-detail', 'DELETE'),
    ('api-policies-tokens', 'POST'),
})

REDACTED = '[redacted]'

#: 422 hints for connection writes: Elasticsearch rejected the connectivity test.
_CONNECTION_TEST_FAILED = ('The Elasticsearch connectivity test failed (error has the reason). '
                           'Check the host, credentials, and certificate settings with the user; '
                           'do not retry with guessed values.')

#: Default ``hint`` added to error responses, by HTTP status.
STATUS_HINTS = {
    400: 'Fix the arguments named in the error and retry. If a value is unclear, ask the user '
         'instead of guessing.',
    401: 'The MCP API key is missing or invalid. Tell the user; do not look for another key.',
    403: "This API key's role cannot do this. Tell the user; do not try another route.",
    404: 'Not found. List the resource to get the exact ID or name, and confirm with the user '
         'if more than one could match.',
    408: 'Timed out. Retry once; if it times out again, report it to the user and stop.',
    409: 'Conflicts with an existing object, usually one with the same name. Ask the user for '
         'another name or which object to change.',
    502: 'An upstream system (Elasticsearch or a LogstashAgent) failed. Report the error to '
         'the user; connections_test can check a connection.',
}

#: Hint for errors with ``code: protected``: official and system objects no role can change.
PROTECTED_HINT = ('This object ships with LogstashUI and is read-only for every role. Do not '
                  'retry or try another route; offer to create a custom copy under a new name.')


class ToolArgumentError(ValueError):
    """Raised when tool arguments cannot be mapped onto the REST route."""


@dataclass(frozen=True)
class Variant:
    """One concrete tool behind a tool with ``variants``.

    Attributes:
        keys: Arguments that select this variant; any one of them present picks it.
        usage: How errors tell the caller to pick it, e.g. ``'pipeline_id (agent pipeline)'``.
        label: Plural name for errors about arguments it doesn't take.
        tool: The :class:`Tool` that runs.
        drop: Arguments removed before dispatch because this variant doesn't use them.
    """

    keys: tuple
    usage: str
    label: str
    tool: 'Tool'
    drop: tuple = ()


@dataclass(frozen=True)
class Tool:
    """One MCP tool backed by one REST route + method.

    Attributes:
        name: MCP tool name, ``<toolset>_<action>``.
        toolset: Group used by the ``?toolsets=`` filter.
        url_name: Django URL name in ``API/urls.py``.
        method: HTTP method to dispatch with.
        description: Text shown to the model.
        path_params: Schemas for URL kwargs, keyed by kwarg name.
        query_params: Schemas for query-string parameters.
        body: Schemas for JSON body fields (POST/PUT only).
        required: Argument names that must be present.
        destructive: Mark a non-DELETE write as destructive (deploys, revokes).
        read_only: Mark a non-GET call that changes nothing (tests, previews,
            simulations) as read-only.
        redact: Response keys replaced with ``[redacted]`` at any depth.
        next_steps: Added to successful object responses as ``next_steps``.
        guidance: ``callable(payload) -> str`` that writes ``next_steps``
            from a successful response, for tools whose right next step
            depends on what they returned. Takes precedence over
            ``next_steps``.
        hints: ``{status_code: text}`` added to error responses as ``hint``;
            overrides :data:`STATUS_HINTS` for this tool.
        defaults: Argument values used when the caller omits them. Lets MCP
            ask for compact responses while REST keeps its full default.
        aliases: ``{alias: argument}`` names accepted in place of an argument
            and renamed before dispatch. Not advertised in ``inputSchema``.
            A tool with exactly one path parameter also accepts ``id``.
        variants: :class:`Variant` tools this one dispatches to. Its own
            schema is what clients see; :meth:`resolve` picks the variant.
    """

    name: str
    toolset: str
    url_name: str
    method: str
    description: str
    path_params: dict = field(default_factory=dict)
    query_params: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    required: tuple = ()
    destructive: bool = False
    read_only: bool = False
    redact: frozenset = frozenset()
    next_steps: str = ''
    guidance: object = None
    hints: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)
    aliases: dict = field(default_factory=dict)
    variants: tuple = ()

    @property
    def admin_only(self):
        """Whether only admin-role keys can call it; tests keep this in step with the views."""
        return 'Admin only.' in self.description

    def resolve(self, arguments):
        """Pick the tool that runs for these arguments.

        Args:
            arguments: Raw ``arguments`` object from ``tools/call``.

        Returns:
            tuple: ``(tool, arguments)``. A tool without variants returns
            itself and the arguments unchanged.

        Raises:
            ToolArgumentError: If no variant's keys are present, several are,
                or the chosen variant doesn't take an argument that was sent.

        Examples:
            >>> tool, args = TOOLS_BY_NAME['pipelines_get'].resolve({'pipeline_id': 4})
            >>> tool.url_name, args
            ('api-pipeline-detail', {'pipeline_id': 4})
        """
        if not self.variants or not isinstance(arguments, dict):
            return self, arguments
        chosen = [v for v in self.variants
                  if any(arguments.get(key) not in (None, '') for key in v.keys)]
        options = ' or '.join(v.usage for v in self.variants)
        if len(chosen) != 1:
            raise ToolArgumentError(f'Pass {options}' + (', not both.' if chosen else '.'))
        variant = chosen[0]
        own = set(variant.tool.input_schema()['properties'])
        # Clients may echo schema defaults or send nulls for arguments the variant doesn't take.
        arguments = {k: v for k, v in arguments.items() if k not in variant.drop
                     and (k in own or (v is not None and v != self.defaults.get(k)))}
        if not variant.tool.body:
            extra = sorted(set(arguments) - own - set(variant.tool.argument_aliases()))
            if extra:
                raise ToolArgumentError(f"{', '.join(extra)}: not used for {variant.label}.")
        return variant.tool, arguments

    def argument_aliases(self):
        """Return every accepted alias, including the implicit ``id``.

        Examples:
            >>> TOOLS_BY_NAME['snmp_networks_get'].argument_aliases()
            {'id': 'network_id'}
        """
        aliases = dict(self.aliases)
        if len(self.path_params) == 1:
            aliases.setdefault('id', next(iter(self.path_params)))
        return aliases

    def input_schema(self):
        """Return the JSON Schema for this tool's flat argument object."""
        properties = {**self.path_params, **self.query_params, **self.body}
        for name, value in self.defaults.items():
            properties[name] = {**properties[name], 'default': value}
        return {
            'type': 'object',
            'properties': properties,
            'required': list(dict.fromkeys((*self.path_params, *self.required))),
            # Views own field validation; unknown body keys pass through to them.
            'additionalProperties': bool(self.body),
        }

    def annotations(self):
        """Return MCP tool annotations so clients can auto-approve reads."""
        if self.method == 'GET' or self.read_only:
            return {'readOnlyHint': True}
        return {
            'readOnlyHint': False,
            'destructiveHint': self.method == 'DELETE' or self.destructive,
            'idempotentHint': self.method in ('PUT', 'DELETE'),
        }

    def to_mcp(self):
        """Return the ``tools/list`` entry for this tool."""
        return {
            'name': self.name,
            'description': self.description,
            'inputSchema': self.input_schema(),
            'annotations': self.annotations(),
        }


def _str(description='', enum=None):
    schema = {'type': 'string', 'description': description}
    if enum:
        schema['enum'] = list(enum)
    return schema


def _int(description=''):
    return {'type': 'integer', 'description': description}


def _bool(description=''):
    return {'type': 'boolean', 'description': description}


def _obj(description=''):
    return {'type': 'object', 'description': description}


def _arr(description='', items=None):
    return {'type': 'array', 'description': description, 'items': items or {}}


def _nullable_int(description=''):
    return {'type': ['integer', 'null'], 'description': description}


# ---------------------------------------------------------------------------
# Shared field sets
# ---------------------------------------------------------------------------

_CONNECTION_FIELDS = {
    'name': _str('Unique connection name.'),
    'connection_type': _str('Connection type.', ['CENTRALIZED', 'AGENT']),
    'connection_mode': _str('How to reach Elasticsearch.', ['url', 'cloud']),
    'auth_type': _str('Elasticsearch auth method: basic or api_key.'),
    'host': _str('Elasticsearch URL without the port, e.g. https://es.example.com; put the '
                 'port in port.'),
    'cloud_id': _str('Elastic Cloud ID.'),
    'cloud_url': _str('Full cluster URL for Cloud deployments.'),
    'port': _int('9200 for URL mode, 443 for Cloud.'),
    'username': _str('Basic-auth username.'),
    'password': _str('Basic-auth password. Omit on update to keep the stored value.'),
    'api_key': _str('Elasticsearch API key. Omit on update to keep the stored value.'),
    'allow_self_signed_certs': _bool('Skip TLS verification for Elasticsearch/Kibana calls.'),
}

_PIPELINE_SETTINGS = {
    'description': _str('Pipeline description.'),
    'pipeline_workers': _int('pipeline.workers (default 1).'),
    'pipeline_batch_size': _int('pipeline.batch.size (default 128).'),
    'pipeline_batch_delay': _int('pipeline.batch.delay in ms (default 50).'),
    'queue_type': _str('queue.type.', ['memory', 'persisted']),
    'queue_max_bytes': _str('queue.max_bytes, e.g. "1gb".'),
    'queue_checkpoint_writes': _int('queue.checkpoint.writes (default 1024).'),
}

_POLICY_FIELDS = {
    'name': _str('Unique policy name.'),
    'policy_type': _str('Policy type; immutable after creation.', ['PACKAGED', 'MANAGED', 'SIMULATE']),
    'settings_path': _str('Logstash settings dir (default /etc/logstash/).'),
    'logs_path': _str('Logstash logs dir (default /var/log/logstash).'),
    'binary_path': _str('Logstash bin dir (default /usr/share/logstash/bin).'),
    'data_path': _str('Logstash data dir.'),
    'keystore_env_file': _str('Keystore env file (default /etc/default/logstash).'),
    'agent_api_port': _int('LogstashAgent API port.'),
    'logstash_api_port': _int('Logstash API port.'),
    'logstash_source': _str('Where the Logstash binary comes from.', ['SYSTEM', 'VERSION']),
    'logstash_version': _str('Logstash version; required when logstash_source is VERSION.'),
    'logstash_download_dir': _str('Directory for downloaded Logstash versions.'),
    'logstash_via_ui': _bool('Download Logstash through LogstashUI.'),
    'logstash_yml': _str('Full logstash.yml contents.'),
    'jvm_options': _str('Full jvm.options contents.'),
    'log4j2_properties': _str('Full log4j2.properties contents.'),
}

_DEVICE_FIELDS = {
    'name': _str('Unique device name.'),
    'ip_address': _str('Device IP. One of ip_address or hostname is required on create.'),
    'hostname': _str('Device hostname.'),
    'port': _int('SNMP port (default 161).'),
    'retries': _int('Retries (default 2).'),
    'timeout': _int('Timeout in ms (default 1000).'),
    'credential': _nullable_int('SNMP credential ID; null clears it.'),
    'network': _nullable_int('SNMP network ID; null clears it.'),
    'device_template': _nullable_int('Device template ID; null clears it.'),
    'site': _str('Site label.'),
    'building': _str('Building label.'),
    'room': _str('Room label.'),
    'latitude': {'type': ['number', 'null'], 'description': 'Decimal degrees.'},
    'longitude': {'type': ['number', 'null'], 'description': 'Decimal degrees.'},
    'metadata': _obj('Arbitrary JSON metadata.'),
}

_CREDENTIAL_FIELDS = {
    'name': _str('Unique credential name.'),
    'description': _str('Description.'),
    'version': _str('SNMP version.', ['1', '2c', '3']),
    'community': _str('v1/v2c community string. Empty or omitted on update keeps it.'),
    'security_name': _str('SNMPv3 username.'),
    'security_level': _str('SNMPv3 security level.', ['noAuthNoPriv', 'authNoPriv', 'authPriv']),
    'auth_protocol': _str('SNMPv3 auth protocol, e.g. sha, md5, hmac192sha256.'),
    'auth_pass': _str('SNMPv3 auth password. Empty or omitted on update keeps it.'),
    'priv_protocol': _str('SNMPv3 privacy protocol, e.g. aes, des, aes256.'),
    'priv_pass': _str('SNMPv3 privacy password. Empty or omitted on update keeps it.'),
}

_NETWORK_FIELDS = {
    'name': _str('Unique network name.'),
    'network_range': _str('CIDR range; prefix must be /20 or longer.'),
    'deployment_mode': _str('Where polling runs.', ['CENTRALIZED', 'AGENT']),
    'credential_mode': _str('How credentials reach Logstash.', ['KEYSTORE', 'PLAINTEXT']),
    'connection': _nullable_int('Elasticsearch connection ID (centralized polling).'),
    'agent_connection': _nullable_int('Agent connection ID (agent-mode polling).'),
    'discovery_credential': _nullable_int('Credential ID used for discovery.'),
    'credential': _nullable_int('Credential ID used for trap ingestion.'),
    'discovery_enabled': _bool('Run discovery (default true).'),
    'traps_enabled': _bool('Ingest traps (default false).'),
    'interval': _int('Poll interval in seconds (default 30).'),
    'namespace': _str('Data-stream namespace (default "default").'),
    'namespace_from_device_template': _bool('Derive namespace from device template name.'),
    'ssl_certificate_authorities': _str('Comma-separated CA paths on the Logstash host.'),
}

_PROFILE_FIELDS = {
    'name': _str('Unique profile name. Names ending in .json are reserved for official profiles.'),
    'vendor': _str('Vendor.'),
    'product': _str('Product.'),
    'description': _str('Description.'),
    'profile_data': _obj('OIDs to poll, keyed by ECS-style field name: {"get": {"field": "oid"}, '
                         '"walk": {"field": "oid"}, "table": {"table.name": {"columns": '
                         '{"column": "oid"}}}}. get for scalar OIDs ending in .0, walk for a flat '
                         'subtree, table for per-row data. See guides_get("snmp").'),
    'normalizers': _arr('Unit conversions and derived fields: {"operation": "multiply", '
                        '"translate", "average", "sum", or "ratio", "target": {"scope": "get" or '
                        '"table", ...}, "params": {...}}. Unknown operations or params are '
                        'rejected with 400. See guides_get("snmp") for the params of each.'),
}

_TEMPLATE_FIELDS = {
    'name': _str('Unique template name.'),
    'vendor': _str('Vendor.'),
    'model': _str('Model label.'),
    'product': _str('Product label.'),
    'type': _str('Device type label, e.g. switch.'),
    'description': _str('Description.'),
    'matching_rules': _arr('sysDescr substrings used for auto-classification.', {'type': 'string'}),
    'profiles': _arr('Profile IDs to attach; replaces the existing list on update.', {'type': 'integer'}),
}

_SEARCH = {'search': _str('Case-insensitive search.')}
_OFFICIAL = {'official': _str('Filter by official status.', ['true', 'false'])}


def _crud(toolset, resource, list_url, detail_url, id_param, fields, *,
          label, list_query=None, create_required=(), read_note='', write_note='',
          write_next_steps=''):
    """Build list/create/get/update/delete tools for a standard REST resource."""
    path = {id_param: _int(f'{label} ID.')}
    not_found = {404: f'{label} not found. Use {toolset}_{resource}_list to find the ID.'}
    return [
        Tool(f'{toolset}_{resource}_list', toolset, list_url, 'GET',
             f'List {label}s.{read_note}', query_params=list_query or {}),
        Tool(f'{toolset}_{resource}_create', toolset, list_url, 'POST',
             f'Create a {label}. Admin only.{write_note}', body=fields, required=create_required,
             next_steps=write_next_steps),
        Tool(f'{toolset}_{resource}_get', toolset, detail_url, 'GET',
             f'Get one {label} by ID.{read_note}', path_params=path, hints=not_found),
        Tool(f'{toolset}_{resource}_update', toolset, detail_url, 'PUT',
             f'Update a {label}; send only fields to change. Admin only.{write_note}',
             path_params=path, body=fields, next_steps=write_next_steps, hints=not_found),
        Tool(f'{toolset}_{resource}_delete', toolset, detail_url, 'DELETE',
             f'Delete a {label}. Admin only.{write_note}', path_params=path,
             next_steps=write_next_steps, hints=not_found),
    ]


_SNMP_DEPLOY_NOTE = (
    ' Flags SNMP config as changed; nothing is pushed until snmp_deploy_diff and '
    'snmp_deploy_apply.'
)
_SNMP_NEXT_STEPS = (
    'Not pushed yet. When the user is done editing, run snmp_deploy_diff, show them the plan, '
    'and run snmp_deploy_apply only after they confirm.'
)
_AGENT_PIPELINE_NEXT_STEPS = (
    'Not live yet: agents run the last deployed revision. To go live, show the user '
    'policies_diff(policy_id) and run policies_deploy only after they confirm.'
)
_CPM_NEXT_STEPS = (
    'Live now: Logstash nodes using CPM on this connection pick up the change without a '
    'deploy step.'
)
_CPM_NOT_FOUND = {
    404: 'CPM pipeline not found. Use pipelines_find(name) to locate it on any connection.',
}
_AGENT_PIPELINE_NOT_FOUND = {
    404: 'Pipeline not found. Use pipelines_find(name) to get the ID.',
}
_PIPELINE_REF = {
    'pipeline_id': _int('Agent pipeline ID, from pipelines_find.'),
    'connection_id': _int('CENTRALIZED connection ID holding the CPM pipeline, from '
                          'pipelines_find; use with name.'),
    'name': _str('CPM pipeline name; use with connection_id.'),
}
_CPM_PATH = {'connection_id': _int(), 'name': _str()}

#: Asked when a pipeline the user wants simulated exists nowhere. The
#: ``simulation`` guide quotes it; a test keeps the two identical.
ASK_TO_BUILD_PIPELINE = (
    "This pipeline doesn't exist on any of your connections. Would you like for me to build "
    "one to simulate with? I won't save it until you tell me to, though."
)


def _find_next_steps(result):
    """Turn a ``pipelines_find`` result into the agent's next step.

    Args:
        result: The find response: ``matches``, ``similar``, ``unreachable``.

    Returns:
        str: What to do with this result.

    Examples:
        >>> _find_next_steps({'matches': [{'type': 'agent', 'pipeline_id': 4}]})
        'Found one match. Pass pipeline_id=4 to pipelines_simulate or pipelines_get.'
    """
    matches = result.get('matches') or []
    unreachable = result.get('unreachable') or []
    if len(matches) == 1:
        match = matches[0]
        if match['type'] == 'cpm':
            steps = (f"Found one match. Pass connection_id={match['connection_id']} and "
                     f"name={match['name']!r} to pipelines_simulate or pipelines_get.")
        else:
            steps = (f"Found one match. Pass pipeline_id={match['pipeline_id']} to "
                     'pipelines_simulate or pipelines_get.')
        if result.get('similar'):
            steps += (' If the user described the pipeline instead of naming it, this name only '
                      'matched your keyword: show them it and the similar pipelines (name, where '
                      'it is, last_modified) and ask which to use.')
        return steps
    if matches:
        return 'Several pipelines have this name. Show the user where each one is and ask which.'
    if unreachable:
        names = ', '.join(c['connection_name'] for c in unreachable)
        return (f'No match on the connections that answered, but {names} could not be searched. '
                'Tell the user it may be there and ask how to proceed. Do not build a '
                'replacement yet.')
    if result.get('similar'):
        return ('No exact match. Show the user the similar pipelines (name, where it is, '
                'last_modified) and ask which they meant; do not pick one yourself. If none and '
                f'they asked to simulate, ask exactly: "{ASK_TO_BUILD_PIPELINE}"')
    return (f'No pipeline has this name anywhere. If the user asked to simulate, ask exactly: '
            f'"{ASK_TO_BUILD_PIPELINE}" Write and simulate your own config (lscl) only after '
            'they say yes, and save it only if they ask.')


def _snmp_plan_next_steps(plan):
    """Turn an ``snmp_deploy_diff`` plan into the agent's next step.

    Args:
        plan: The deploy plan response; ``has_changes`` says whether anything would change.

    Returns:
        str: What to do with this plan.

    Examples:
        >>> _snmp_plan_next_steps({'has_changes': False})
        'Nothing to deploy: the SNMP pipelines already match the configuration. Do not run snmp_deploy_apply.'
    """
    if not plan.get('has_changes'):
        return ('Nothing to deploy: the SNMP pipelines already match the configuration. '
                'Do not run snmp_deploy_apply.')
    return ('Show this plan to the user. Run snmp_deploy_apply only after they confirm; '
            'if more than 60 seconds pass, run snmp_deploy_diff again first.')


TOOLS = [
    # --- Guides -----------------------------------------------------------
    Tool('guides_list', 'guides', 'api-guides-list', 'GET',
         'List how-to guides for working with LogstashUI (concepts, pipeline review, '
         'simulation, deploy, SNMP, troubleshooting).'),
    Tool('guides_get', 'guides', 'api-guides-detail', 'GET',
         'Read one how-to guide as Markdown. Read concepts before your first change, and the '
         'guide for a task before starting it, such as pipeline-review before reviewing a '
         'pipeline.',
         path_params={'topic': _str('Guide topic.', GUIDES)}),

    # --- Connections ------------------------------------------------------
    Tool('connections_list', 'connections', 'api-connections-list', 'GET',
         'List connections. CENTRALIZED connections are Elasticsearch clusters holding CPM '
         'pipelines (pipelines_list with connection_id). AGENT connections are enrolled LogstashAgent '
         'nodes; policy_id is the policy they run, and SIMULATE-policy agents run simulations. '
         'Credentials are never returned.'),
    Tool('connections_create', 'connections', 'api-connections-list', 'POST',
         'Create a connection. It is connectivity-tested first and rolled back on failure. Admin only.',
         body=_CONNECTION_FIELDS, required=('name', 'connection_type'),
         hints={422: _CONNECTION_TEST_FAILED + ' Nothing was saved.'}),
    Tool('connections_get', 'connections', 'api-connections-detail', 'GET',
         'Get one connection by ID.', path_params={'connection_id': _int('Connection ID.')}),
    Tool('connections_update', 'connections', 'api-connections-detail', 'PUT',
         'Update a connection; send only fields to change. Re-tested and rolled back on failure. Admin only.',
         path_params={'connection_id': _int('Connection ID.')}, body=_CONNECTION_FIELDS,
         hints={422: _CONNECTION_TEST_FAILED + ' The update was rolled back.'}),
    Tool('connections_delete', 'connections', 'api-connections-detail', 'DELETE',
         'Delete a connection. Admin only.', path_params={'connection_id': _int('Connection ID.')}),
    Tool('connections_test', 'connections', 'api-connections-test', 'POST',
         'Run a live connectivity check against a saved connection without changing it.',
         path_params={'connection_id': _int('Connection ID.')}, read_only=True,
         hints={404: 'Connection not found. Use connections_list to find the ID.',
                422: _CONNECTION_TEST_FAILED + ' Fix it with connections_update.'}),

    # --- Finding pipelines --------------------------------------------------
    Tool('pipelines_find', 'pipelines', 'api-pipeline-find', 'GET',
         'Find Logstash pipelines in every policy and on every CENTRALIZED connection in one '
         'call. Use this whenever the user names or describes a pipeline ("asa-new", "the ASA '
         'pipeline"), before any other pipeline tool and instead of listing policies or '
         'connections. Returns exact matches, similar names, and connections that could not be '
         'searched; next_steps says what to do with the result.',
         query_params={'name': _str('A pipeline name, part of one, or a topic keyword such as '
                                    '"asa".')},
         required=('name',),
         aliases={'query': 'name'},
         guidance=_find_next_steps),
    Tool('pipelines_recent', 'pipelines', 'api-pipeline-recent', 'GET',
         'List Logstash pipelines in every policy and on every CENTRALIZED connection, most '
         'recently modified first, in one call. Use it for "what changed lately" questions '
         'instead of listing each policy and connection. Shows when a pipeline last changed, '
         'not who changed it or what changed.',
         query_params={
             'since': _str('ISO 8601 timestamp, e.g. 2026-11-01 or 2026-11-01T09:00:00Z; only '
                           'pipelines modified at or after it.'),
             'limit': _int('Maximum pipelines to return (default 20, max 200).'),
         }),

    # --- Agent and CPM pipelines ----------------------------------------------
    # One tool per operation; the arguments pick the agent or CPM route.
    Tool('pipelines_list', 'pipelines', '', 'GET',
         'List the Logstash pipelines in one place, without their config: policy_id for a '
         "policy's agent pipelines, or connection_id for the CPM pipelines on a CENTRALIZED "
         'connection. To search every place at once, use pipelines_find or pipelines_recent.',
         query_params={
             'policy_id': _int('Policy ID (agent pipelines).'),
             'connection_id': _int('CENTRALIZED connection ID (CPM pipelines).'),
             'managed_by': _str('Agent pipelines only. Ownership filter (default user): snmp for '
                                'SNMP-generated pipelines, library for library pipelines.',
                                ['user', 'snmp', 'library']),
             'include_lscl': _bool("CPM pipelines only. Include each pipeline's full config, "
                                   'which is large; use pipelines_get for one pipeline.'),
         },
         defaults={'include_lscl': False},
         variants=(
             Variant(('policy_id',), 'policy_id (agent pipelines)', 'agent pipelines',
                     Tool('pipelines_list', 'pipelines', 'api-pipeline-list', 'GET', '',
                          query_params={'policy_id': _int(), 'managed_by': _str()},
                          required=('policy_id',),
                          hints={404: 'Policy not found. Use policies_list to find the ID.'})),
             Variant(('connection_id',), 'connection_id (CPM pipelines)', 'CPM pipelines',
                     Tool('pipelines_list', 'pipelines', 'api-centralized-pipeline-list', 'GET', '',
                          path_params={'connection_id': _int()},
                          query_params={'include_lscl': _bool()},
                          defaults={'include_lscl': False},
                          hints={404: 'Connection not found. Use connections_list and pick a '
                                      'CENTRALIZED connection.'})),
         )),
    Tool('pipelines_get', 'pipelines', '', 'GET',
         'Get one Logstash pipeline with its config (lscl) and settings. Pass pipeline_id for an '
         'agent pipeline or connection_id + name for a CPM pipeline, as pipelines_find returns '
         'them. pipelines_simulate takes the same arguments.',
         query_params=_PIPELINE_REF,
         variants=(
             Variant(('pipeline_id', 'id'), 'pipeline_id (agent pipeline)', 'agent pipelines',
                     Tool('pipelines_get', 'pipelines', 'api-pipeline-detail', 'GET', '',
                          path_params={'pipeline_id': _int()},
                          hints=_AGENT_PIPELINE_NOT_FOUND),
                     drop=('name',)),
             Variant(('connection_id',), 'connection_id + name (CPM pipeline)', 'CPM pipelines',
                     Tool('pipelines_get', 'pipelines', 'api-centralized-pipeline-detail', 'GET', '',
                          path_params=_CPM_PATH, hints=_CPM_NOT_FOUND)),
         )),
    Tool('pipelines_create', 'pipelines', '', 'POST',
         'Create a Logstash pipeline. policy_id adds an agent pipeline to a policy; it is not '
         'live until the policy is deployed. connection_id writes a CPM pipeline, which is live '
         'immediately and overwrites a CPM pipeline with the same name. Admin only.',
         body={
             'policy_id': _int('Policy ID (agent pipeline).'),
             'connection_id': _int('CENTRALIZED connection ID (CPM pipeline).'),
             'name': _str('Pipeline name, unique within the policy or connection.'),
             'lscl': _str('Full Logstash config text.'),
             **_PIPELINE_SETTINGS,
         },
         required=('name', 'lscl'),
         variants=(
             Variant(('policy_id',), 'policy_id (agent pipeline)', 'agent pipelines',
                     Tool('pipelines_create', 'pipelines', 'api-pipeline-list', 'POST', '',
                          body={'policy_id': _int(), 'name': _str(), 'lscl': _str()},
                          required=('policy_id', 'name', 'lscl'),
                          next_steps=_AGENT_PIPELINE_NEXT_STEPS)),
             Variant(('connection_id',), 'connection_id (CPM pipeline)', 'CPM pipelines',
                     Tool('pipelines_create', 'pipelines', 'api-centralized-pipeline-list', 'POST',
                          '', path_params={'connection_id': _int()},
                          body={'name': _str(), 'lscl': _str()}, required=('name', 'lscl'),
                          next_steps=_CPM_NEXT_STEPS)),
         )),
    Tool('pipelines_update', 'pipelines', '', 'PUT',
         'Update a Logstash pipeline; send only fields to change. Pass pipeline_id for an agent '
         'pipeline (not live until the policy is deployed) or connection_id + name for a CPM '
         'pipeline (live immediately; unspecified settings keep their values). Pipelines cannot '
         'be renamed here. Admin only.',
         body={**_PIPELINE_REF, 'lscl': _str('Full Logstash config text.'), **_PIPELINE_SETTINGS},
         variants=(
             Variant(('pipeline_id', 'id'), 'pipeline_id (agent pipeline)', 'agent pipelines',
                     Tool('pipelines_update', 'pipelines', 'api-pipeline-detail', 'PUT', '',
                          path_params={'pipeline_id': _int()}, body={'lscl': _str()},
                          next_steps=_AGENT_PIPELINE_NEXT_STEPS, hints=_AGENT_PIPELINE_NOT_FOUND),
                     drop=('name',)),
             Variant(('connection_id',), 'connection_id + name (CPM pipeline)', 'CPM pipelines',
                     Tool('pipelines_update', 'pipelines', 'api-centralized-pipeline-detail', 'PUT',
                          '', path_params=_CPM_PATH, body={'lscl': _str()},
                          next_steps=_CPM_NEXT_STEPS, hints=_CPM_NOT_FOUND)),
         )),
    Tool('pipelines_delete', 'pipelines', '', 'DELETE',
         'Delete a Logstash pipeline. Pass pipeline_id for an agent pipeline (agents keep '
         'running it until the policy is deployed) or connection_id + name for a CPM pipeline '
         '(Logstash nodes using CPM stop running it immediately). Admin only.',
         query_params=_PIPELINE_REF,
         variants=(
             Variant(('pipeline_id', 'id'), 'pipeline_id (agent pipeline)', 'agent pipelines',
                     Tool('pipelines_delete', 'pipelines', 'api-pipeline-detail', 'DELETE', '',
                          path_params={'pipeline_id': _int()},
                          next_steps=_AGENT_PIPELINE_NEXT_STEPS, hints=_AGENT_PIPELINE_NOT_FOUND),
                     drop=('name',)),
             Variant(('connection_id',), 'connection_id + name (CPM pipeline)', 'CPM pipelines',
                     Tool('pipelines_delete', 'pipelines', 'api-centralized-pipeline-detail',
                          'DELETE', '', path_params=_CPM_PATH,
                          next_steps=_CPM_NEXT_STEPS, hints=_CPM_NOT_FOUND)),
         )),
    Tool('pipelines_simulate', 'pipelines', 'api-pipeline-simulate', 'POST',
         "Run sample events through a pipeline's filters on a simulate agent and return what "
         'each filter did. Pass exactly one config source: connection_id + name (CPM pipeline) '
         'or pipeline_id (agent pipeline), both from pipelines_find, or lscl for config that '
         "isn't saved. Never use lscl in place of a pipeline the user named. Pass event or "
         'events. Read-only: nothing is saved or deployed. Admin only.',
         body={
             'connection_id': _int('CENTRALIZED connection ID holding the CPM pipeline; '
                                   'use with name.'),
             'name': _str('CPM pipeline name; use with connection_id.'),
             'pipeline_id': _int('Agent pipeline ID.'),
             'lscl': _str("Logstash config that isn't saved, such as a proposed fix. Input and "
                          'output blocks are ignored.'),
             'event': _str('One sample log line or JSON string.'),
             'events': _arr('Up to 100 log lines or JSON events, run on one slot in a single '
                            'call. Events run about 1.5s apart; keep a batch under about 30 to '
                            'stay within a 60s client tool timeout.',
                            {'type': ['string', 'object']}),
             'sim_connection_id': _int('Specific simulate-agent connection ID.'),
             'policy_id': _int('Policy whose keystore backs ${var} references.'),
             'timeout': _int('Seconds to wait for all events (default 30, max 180).'),
             'detail': _str('Per-event output. steps: final event plus what each filter added, '
                            'changed, or removed. final: final event only, for large batches. '
                            'full: raw snapshots, large; only when steps is not enough.',
                            ('final', 'steps', 'full')),
         },
         read_only=True,
         defaults={'detail': 'steps'},
         hints={
             404: 'Config source not found. Use pipelines_find(name) to get the exact source.',
             408: 'No results in time. Retry once with the same arguments; if it times out '
                  'again, report that the simulate agent is not returning results and stop.',
         }),

    # --- Policies -----------------------------------------------------------
    Tool('policies_list', 'policies', 'api-policies-list', 'GET',
         'List agent policies with active agent counts and deploy state. Config files '
         '(logstash.yml, jvm.options, log4j2.properties) are left out unless include_config is '
         'set. Admin only.',
         query_params={'include_config': _bool('Include config file contents.')},
         defaults={'include_config': False}),
    Tool('policies_create', 'policies', 'api-policies-list', 'POST',
         'Create an agent policy. Config files default to system defaults when omitted. Admin only.',
         body=_POLICY_FIELDS, required=('name', 'policy_type')),
    Tool('policies_get', 'policies', 'api-policies-detail', 'GET',
         'Get one agent policy by ID. Config files (logstash.yml, jvm.options, '
         'log4j2.properties) are left out unless include_config is set; set it before editing '
         'them. Admin only.',
         path_params={'policy_id': _int('Policy ID.')},
         query_params={'include_config': _bool('Include config file contents.')},
         defaults={'include_config': False}),
    Tool('policies_update', 'policies', 'api-policies-detail', 'PUT',
         'Update an agent policy; send only fields to change. Name and policy_type cannot change. '
         'Not live until the policy is deployed. Admin only.',
         path_params={'policy_id': _int('Policy ID.')},
         body={k: v for k, v in _POLICY_FIELDS.items() if k not in ('name', 'policy_type')},
         next_steps=_AGENT_PIPELINE_NEXT_STEPS),
    Tool('policies_delete', 'policies', 'api-policies-detail', 'DELETE',
         'Delete an agent policy. System policies and policies with agents cannot be deleted. Admin only.',
         path_params={'policy_id': _int('Policy ID.')}),
    Tool('policies_deploy', 'policies', 'api-policies-deploy', 'POST',
         'Deploy a policy: snapshot its pipelines, keystore, and config as a new revision that '
         'agents pick up on next check-in. Show the user policies_diff first and deploy only '
         'after they confirm. Admin only.',
         path_params={'policy_id': _int('Policy ID.')}, destructive=True),
    Tool('policies_clone', 'policies', 'api-policies-clone', 'POST',
         'Clone a policy with all its user pipelines and keystore entries. Admin only.',
         path_params={'policy_id': _int('Source policy ID.')},
         body={'new_name': _str('Unique name for the clone.')}, required=('new_name',)),
    Tool('policies_diff', 'policies', 'api-policies-diff', 'GET',
         'Compare a policy\'s live state against its last deployed revision. Returns the '
         'pending change count and the names of changed config files, paths, pipelines, and '
         'keystore keys by default; call again with detail=changes to read the diffs. '
         'Keystore values are never shown. Admin only.',
         path_params={'policy_id': _int('Policy ID.')},
         query_params={
             'detail': _str('summary: what changed, by name. changes: plus unified diffs of '
                            'changed config files and pipeline LSCL. full: both complete '
                            'snapshots, very large.', ('summary', 'changes', 'full')),
         },
         defaults={'detail': 'summary'},
         redact=frozenset({'key_value', 'keystore_password_hash'})),
    Tool('policies_tokens_list', 'policies', 'api-policies-tokens', 'GET',
         'List enrollment tokens for a policy (IDs and names; token values are redacted). Admin only.',
         path_params={'policy_id': _int('Policy ID.')},
         redact=frozenset({'raw_token', 'encoded_token', 'enroll_command'})),
    Tool('policies_tokens_get', 'policies', 'api-policies-token-detail', 'GET',
         'Get one enrollment token\'s metadata (token value is redacted). Admin only.',
         path_params={'policy_id': _int('Policy ID.'), 'token_id': _int('Token ID.')},
         redact=frozenset({'raw_token', 'encoded_token', 'enroll_command'})),
    Tool('policies_tokens_delete', 'policies', 'api-policies-token-detail', 'DELETE',
         'Delete an enrollment token. Admin only.',
         path_params={'policy_id': _int('Policy ID.'), 'token_id': _int('Token ID.')}),

    # --- SNMP -----------------------------------------------------------------
    *_crud('snmp', 'devices', 'api-snmp-device-list', 'api-snmp-device-detail', 'device_id',
           _DEVICE_FIELDS, label='SNMP device', create_required=('name',),
           write_note=_SNMP_DEPLOY_NOTE, write_next_steps=_SNMP_NEXT_STEPS,
           list_query={
               'page': _int('Page number (default 1).'),
               'page_size': _int('Page size (default 25, max 200).'),
               **_SEARCH,
               'network': _int('Filter by network ID.'),
               'sort_by': _str('Sort order.', ['name', '-name', 'ip_address', '-ip_address',
                                               'hostname', '-hostname', 'created_at', '-created_at']),
           }),
    *_crud('snmp', 'credentials', 'api-snmp-credential-list', 'api-snmp-credential-detail',
           'credential_id', _CREDENTIAL_FIELDS, label='SNMP credential',
           create_required=('name', 'version'), write_note=_SNMP_DEPLOY_NOTE,
           write_next_steps=_SNMP_NEXT_STEPS,
           read_note=' Secret values are never returned.',
           list_query={**_SEARCH, 'version': _str('SNMP version filter.', ['1', '2c', '3'])}),
    *_crud('snmp', 'networks', 'api-snmp-network-list', 'api-snmp-network-detail', 'network_id',
           _NETWORK_FIELDS, label='SNMP network', create_required=('name', 'network_range'),
           write_note=_SNMP_DEPLOY_NOTE, write_next_steps=_SNMP_NEXT_STEPS, list_query=_SEARCH),
    *_crud('snmp', 'profiles', 'api-snmp-profile-list', 'api-snmp-profile-detail', 'profile_id',
           _PROFILE_FIELDS, label='SNMP OID profile',
           create_required=('name', 'vendor', 'profile_data'), list_query={**_SEARCH, **_OFFICIAL}),
    *_crud('snmp', 'templates', 'api-snmp-template-list', 'api-snmp-template-detail', 'template_id',
           _TEMPLATE_FIELDS, label='SNMP device template', create_required=('name', 'vendor'),
           read_note=' Official templates are read-only.', list_query={**_SEARCH, **_OFFICIAL}),
    Tool('snmp_deploy_status', 'snmp', 'api-snmp-deploy-status', 'GET',
         'Check whether SNMP configuration has undeployed changes.'),
    Tool('snmp_deploy_diff', 'snmp', 'api-snmp-deploy-diff', 'POST',
         'Preview the SNMP deployment plan (pipelines to create/update/delete) and cache it for '
         '60 seconds. Changes nothing. Returns counts and one row per pipeline by default; to '
         'see what changes inside specific pipelines, call again with detail=changes and '
         'pipelines=[names]. Admin only.',
         body={
             'detail': _str('summary: counts and pipeline names. changes: plus a unified diff '
                            'per pipeline. full: raw current and new config, very large.',
                            ('summary', 'changes', 'full')),
             'pipelines': _arr('Only include these pipeline names in the rows (counts still '
                               'cover the whole plan).', {'type': 'string'}),
         },
         defaults={'detail': 'summary'},
         redact=frozenset({'manual_keystore_values'}),
         read_only=True,
         guidance=_snmp_plan_next_steps),
    Tool('snmp_deploy_apply', 'snmp', 'api-snmp-deploy-apply', 'POST',
         'Apply the SNMP deployment plan: push pipelines and keystore values. Run snmp_deploy_diff '
         'first, show the user the plan, and apply only after they confirm. Admin only.',
         destructive=True),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def concrete_tools():
    """Return every tool that maps to a route: plain tools plus each tool's variants.

    Examples:
        >>> 'api-centralized-pipeline-detail' in {t.url_name for t in concrete_tools()}
        True
    """
    return [v.tool for t in TOOLS for v in t.variants] + [t for t in TOOLS if not t.variants]


def parse_toolsets(raw):
    """Parse the ``?toolsets=`` query value.

    Args:
        raw: Comma-separated toolset names, or ``None``/empty for all.

    Returns:
        Tuple of ``(toolsets, unknown)``: the selected names (all when
        ``raw`` names none) and any names that are not in :data:`TOOLSETS`.
        :data:`RETIRED_TOOLSETS` are dropped without counting as unknown.

    Examples:
        >>> parse_toolsets('pipelines, snmp')
        (['pipelines', 'snmp'], [])
        >>> parse_toolsets('nope')
        ([], ['nope'])
        >>> parse_toolsets('snmp,security')
        (['snmp'], [])
    """
    names = [n.strip() for n in (raw or '').split(',')
             if n.strip() and n.strip() not in RETIRED_TOOLSETS]
    if not names:
        return list(TOOLSETS), []
    return [n for n in names if n in TOOLSETS], [n for n in names if n not in TOOLSETS]


def select_tools(toolsets):
    """Return ``{name: Tool}`` for tools in the given toolsets, in registry order."""
    wanted = set(toolsets)
    return {t.name: t for t in TOOLS if t.toolset in wanted}


def toolset_catalog():
    """List each toolset's tools for display in the UI.

    Returns:
        list[dict]: One ``{'name', 'tools'}`` entry per toolset, in
        :data:`TOOLSETS` order. Each tool is ``{'name', 'summary', 'writes'}``,
        where ``summary`` is the first sentence of its description.

    Examples:
        >>> catalog = toolset_catalog()
        >>> catalog[0]['name'], catalog[0]['tools'][0]['name'], catalog[0]['tools'][0]['writes']
        ('guides', 'guides_list', False)
    """
    return [
        {'name': toolset, 'tools': [
            {'name': t.name,
             'summary': t.description.split('. ')[0].rstrip('.') + '.',
             'writes': not t.annotations()['readOnlyHint']}
            for t in TOOLS if t.toolset == toolset
        ]}
        for toolset in TOOLSETS
    ]
