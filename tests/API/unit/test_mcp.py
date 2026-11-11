"""Tests for API/mcp — the MCP JSON-RPC endpoint and its tool registry."""

import json
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from API import urls as api_urls
from API.guides import GUIDES, read_guide
from API.mcp.dispatch import validate_arguments
from API.mcp.tools import (
    ASK_TO_BUILD_PIPELINE, EXCLUDED_ROUTES, PROTECTED_HINT, REDACTED, STATUS_HINTS, TOOLS, TOOLS_BY_NAME,
    TOOLSETS, ToolArgumentError, _find_next_steps, concrete_tools,
)
from API.mcp.views import _INSTRUCTIONS
from Management.models import UserProfile
from PipelineManager.models import ApiKey, EnrollmentToken, Pipeline, Policy

MCP_URL = '/api/mcp'


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_auth(test_user):
    _token, raw = ApiKey.issue_for_user(test_user, name='mcp-admin')
    return {'HTTP_AUTHORIZATION': f'ApiKey {raw}'}


@pytest.fixture
def readonly_auth(db):
    user = User.objects.create_user(username='mcp-reader', password='R3ad0nly!Pass')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    _token, raw = ApiKey.issue_for_user(user, name='mcp-reader')
    return {'HTTP_AUTHORIZATION': f'ApiKey {raw}'}


@pytest.fixture
def policy(db):
    return Policy.objects.create(
        name='mcp-policy',
        policy_type=Policy.PolicyType.PACKAGED,
        is_system=False,
        logstash_yml='# yml',
        jvm_options='-Xms512m',
        log4j2_properties='# log4j2',
    )


def _rpc(client, method, params=None, auth=None, url=MCP_URL, msg_id=1, **extra):
    message = {'jsonrpc': '2.0', 'id': msg_id, 'method': method}
    if params is not None:
        message['params'] = params
    return client.post(url, data=json.dumps(message), content_type='application/json',
                       **(auth or {}), **extra)


def _call(client, auth, name, arguments=None, url=MCP_URL):
    response = _rpc(client, 'tools/call', {'name': name, 'arguments': arguments or {}},
                    auth=auth, url=url)
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# Transport and protocol
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTransport:

    def test_get_is_405(self, client, admin_auth):
        response = client.get(MCP_URL, **admin_auth)
        assert response.status_code == 405
        assert response['Allow'] == 'POST'

    def test_trailing_slash_route_works(self, client, admin_auth):
        assert _rpc(client, 'ping', auth=admin_auth, url='/api/mcp/').json()['result'] == {}

    def test_no_auth_is_401(self, client, db):
        assert _rpc(client, 'ping').status_code == 401

    def test_invalid_token_is_401(self, client, db):
        response = _rpc(client, 'ping', auth={'HTTP_AUTHORIZATION': 'ApiKey lsui_abc_nope'})
        assert response.status_code == 401

    def test_bearer_scheme_authenticates(self, client, test_user):
        _token, raw = ApiKey.issue_for_user(test_user, name='bearer')
        response = _rpc(client, 'ping', auth={'HTTP_AUTHORIZATION': f'Bearer {raw}'})
        assert response.status_code == 200

    def test_foreign_origin_rejected(self, client, admin_auth):
        response = _rpc(client, 'ping', auth=admin_auth, HTTP_ORIGIN='https://evil.example')
        assert response.status_code == 403

    def test_same_origin_allowed(self, client, admin_auth):
        response = _rpc(client, 'ping', auth=admin_auth, HTTP_ORIGIN='http://testserver')
        assert response.status_code == 200

    def test_non_json_content_type_is_415(self, client, admin_auth):
        response = client.post(MCP_URL, data='{}', content_type='text/plain', **admin_auth)
        assert response.status_code == 415

    def test_parse_error(self, client, admin_auth):
        response = client.post(MCP_URL, data='{not json', content_type='application/json',
                               **admin_auth)
        assert response.status_code == 400
        assert response.json()['error']['code'] == -32700

    def test_batch_rejected(self, client, admin_auth):
        response = client.post(MCP_URL, data='[]', content_type='application/json', **admin_auth)
        assert response.json()['error']['code'] == -32600

    def test_notification_is_202(self, client, admin_auth):
        body = json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        response = client.post(MCP_URL, data=body, content_type='application/json', **admin_auth)
        assert response.status_code == 202
        assert response.content == b''

    def test_unknown_method(self, client, admin_auth):
        assert _rpc(client, 'completion/complete', auth=admin_auth).json()['error']['code'] == -32601


@pytest.mark.django_db
class TestInitialize:

    def test_echoes_supported_version(self, client, admin_auth):
        result = _rpc(client, 'initialize', {'protocolVersion': '2025-03-26'},
                      auth=admin_auth).json()['result']
        assert result['protocolVersion'] == '2025-03-26'
        assert result['capabilities'] == {'tools': {'listChanged': False}}
        assert result['serverInfo']['name'] == 'LogstashUI'

    def test_unsupported_version_falls_back_to_latest(self, client, admin_auth):
        result = _rpc(client, 'initialize', {'protocolVersion': '1999-01-01'},
                      auth=admin_auth).json()['result']
        assert result['protocolVersion'] == '2025-06-18'

    def test_instructions_stay_short(self, client, admin_auth):
        result = _rpc(client, 'initialize', {}, auth=admin_auth).json()['result']
        assert len(result['instructions']) <= 1700

    @pytest.mark.parametrize('phrase', [
        'Centralized Pipeline Management',
        'neither is an Elasticsearch ingest pipeline',
        'confirm with the user',
        'policies_diff',
        'snmp_deploy_diff',
        'next_steps',
        "Don't switch to the REST API, the database, the web UI, or config files",
        'guides_get(topic)',
        'Responses are compact by default',
        'locate it with pipelines_find',
    ])
    def test_instructions_cover_key_rules(self, client, admin_auth, phrase):
        result = _rpc(client, 'initialize', {}, auth=admin_auth).json()['result']
        assert phrase in result['instructions']


# ---------------------------------------------------------------------------
# tools/list and toolsets
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestToolsList:

    def test_lists_every_tool(self, client, admin_auth):
        tools = _rpc(client, 'tools/list', auth=admin_auth).json()['result']['tools']
        assert [t['name'] for t in tools] == [t.name for t in TOOLS]
        for tool in tools:
            assert tool['inputSchema']['type'] == 'object'
            assert tool['description']

    def test_read_tools_are_annotated_read_only(self, client, admin_auth):
        tools = _rpc(client, 'tools/list', auth=admin_auth).json()['result']['tools']
        by_name = {t['name']: t for t in tools}
        assert by_name['pipelines_get']['annotations'] == {'readOnlyHint': True}
        assert by_name['pipelines_delete']['annotations']['destructiveHint'] is True
        assert by_name['policies_deploy']['annotations']['destructiveHint'] is True
        assert by_name['pipelines_create']['annotations']['destructiveHint'] is False

    def test_toolsets_filter_list(self, client, admin_auth):
        tools = _rpc(client, 'tools/list', auth=admin_auth,
                     url=f'{MCP_URL}?toolsets=snmp,guides').json()['result']['tools']
        assert tools
        assert {TOOLS_BY_NAME[t['name']].toolset for t in tools} == {'snmp', 'guides'}

    def test_retired_toolset_is_ignored(self, client, admin_auth):
        body = _rpc(client, 'tools/list', auth=admin_auth,
                    url=f'{MCP_URL}?toolsets=snmp,security').json()
        assert {TOOLS_BY_NAME[t['name']].toolset for t in body['result']['tools']} == {'snmp'}
        only_retired = _rpc(client, 'tools/list', auth=admin_auth,
                            url=f'{MCP_URL}?toolsets=security').json()['result']['tools']
        assert len(only_retired) == len(TOOLS)

    def test_readonly_key_lists_only_tools_it_can_use(self, client, readonly_auth):
        names = {t['name'] for t in _rpc(client, 'tools/list', auth=readonly_auth)
                 .json()['result']['tools']}
        assert names == {t.name for t in TOOLS if not t.admin_only}
        assert 'pipelines_get' in names and 'pipelines_simulate' not in names

    def test_toolsets_filter_call(self, client, admin_auth):
        body = _call(client, admin_auth, 'connections_list', url=f'{MCP_URL}?toolsets=snmp')
        assert body['error']['code'] == -32602

    def test_unknown_toolset_errors(self, client, admin_auth):
        body = _rpc(client, 'tools/list', auth=admin_auth,
                    url=f'{MCP_URL}?toolsets=pipelines,bogus').json()
        assert body['error']['code'] == -32602
        assert 'bogus' in body['error']['message']


# ---------------------------------------------------------------------------
# tools/call
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestToolsCall:

    def test_unknown_tool(self, client, admin_auth):
        assert _call(client, admin_auth, 'nope')['error']['code'] == -32602

    def test_missing_required_argument(self, client, admin_auth):
        result = _call(client, admin_auth, 'pipelines_get')['result']
        assert result['isError'] is True
        assert 'pipeline_id' in result['structuredContent']['error']

    def test_non_integer_path_argument(self, client, admin_auth):
        result = _call(client, admin_auth, 'pipelines_get', {'pipeline_id': 'abc'})['result']
        assert result['isError'] is True

    def test_unexpected_argument_on_bodyless_tool(self, client, admin_auth):
        result = _call(client, admin_auth, 'connections_list', {'bogus': 1})['result']
        assert result['isError'] is True

    def test_list_response_returns_text_only(self, client, admin_auth, test_connection):
        result = _call(client, admin_auth, 'connections_list')['result']
        assert result['isError'] is False
        assert 'structuredContent' not in result
        assert json.loads(result['content'][0]['text'])[0]['name'] == 'Test Connection'

    def test_not_found_is_tool_error(self, client, admin_auth):
        result = _call(client, admin_auth, 'connections_get', {'connection_id': 999999})['result']
        assert result['isError'] is True

    def test_pipeline_crud_round_trip(self, client, admin_auth, policy):
        created = _call(client, admin_auth, 'pipelines_create', {
            'policy_id': policy.id, 'name': 'mcp-pipe',
            'lscl': 'input { stdin {} } output { stdout {} }',
        })['result']
        assert created['isError'] is False, created
        pipeline_id = created['structuredContent']['id']

        updated = _call(client, admin_auth, 'pipelines_update',
                        {'pipeline_id': pipeline_id, 'description': 'via mcp'})['result']
        assert updated['isError'] is False, updated
        assert Pipeline.objects.get(pk=pipeline_id).description == 'via mcp'

        listed = _call(client, admin_auth, 'pipelines_list', {'policy_id': policy.id})['result']
        assert [p['name'] for p in listed['structuredContent']['pipelines']] == ['mcp-pipe']

        deleted = _call(client, admin_auth, 'pipelines_delete',
                        {'pipeline_id': pipeline_id})['result']
        assert deleted['isError'] is False
        assert not Pipeline.objects.filter(pk=pipeline_id).exists()

    def test_centralized_pipeline_get_uses_logstash_pipeline_api(self, client, admin_auth, test_connection):
        with patch('API.pipelines_views.get_elastic_connection') as mock_get_es:
            mock_es = mock_get_es.return_value
            mock_es.logstash.get_pipeline.return_value = {'cpm-pipe': {'pipeline': 'input {}'}}
            result = _call(client, admin_auth, 'pipelines_get',
                           {'connection_id': test_connection.id, 'name': 'cpm-pipe'})['result']
        assert result['isError'] is False, result
        assert result['structuredContent']['pipeline']['lscl'] == 'input {}'
        mock_es.logstash.get_pipeline.assert_called_once_with(id='cpm-pipe')
        mock_es.ingest.get_pipeline.assert_not_called()

    def test_readonly_key_cannot_write(self, client, readonly_auth, policy):
        result = _call(client, readonly_auth, 'pipelines_create', {
            'policy_id': policy.id, 'name': 'x', 'lscl': 'input { stdin {} }',
        })['result']
        assert result['isError'] is True
        assert not Pipeline.objects.filter(name='x').exists()

    def test_readonly_key_can_read(self, client, readonly_auth):
        result = _call(client, readonly_auth, 'snmp_deploy_status')['result']
        assert result['isError'] is False

    def test_snmp_credential_create_and_get(self, client, admin_auth):
        created = _call(client, admin_auth, 'snmp_credentials_create', {
            'name': 'mcp-cred', 'version': '2c', 'community': 's3cret',
        })['result']
        assert created['isError'] is False, created
        cred = _call(client, admin_auth, 'snmp_credentials_get',
                     {'credential_id': created['structuredContent']['id']})['result']
        assert cred['structuredContent']['credential']['community'] == '***'

    def test_argument_error_has_hint(self, client, admin_auth):
        result = _call(client, admin_auth, 'pipelines_get')['result']
        assert result['structuredContent']['hint'] == STATUS_HINTS[400]

    def test_not_found_uses_tool_hint(self, client, admin_auth):
        result = _call(client, admin_auth, 'pipelines_get', {'pipeline_id': 999999})['result']
        assert result['isError'] is True
        assert 'pipelines_find' in result['structuredContent']['hint']

    def test_not_found_falls_back_to_status_hint(self, client, admin_auth):
        result = _call(client, admin_auth, 'policies_get', {'policy_id': 999999})['result']
        assert result['structuredContent']['hint'] == STATUS_HINTS[404]

    def test_readonly_write_has_403_hint(self, client, readonly_auth, policy):
        result = _call(client, readonly_auth, 'pipelines_create', {
            'policy_id': policy.id, 'name': 'x', 'lscl': 'input { stdin {} }',
        })['result']
        assert result['structuredContent']['hint'] == STATUS_HINTS[403]

    def test_protected_object_has_protected_hint(self, client, admin_auth):
        system = Policy.objects.create(name='mcp-system', policy_type=Policy.PolicyType.PACKAGED,
                                       is_system=True)
        result = _call(client, admin_auth, 'policies_delete', {'policy_id': system.id})['result']
        assert result['isError'] is True
        assert result['structuredContent']['code'] == 'protected'
        assert result['structuredContent']['hint'] == PROTECTED_HINT

    def test_policies_diff_defaults_to_summary(self, client, admin_auth, policy):
        result = _call(client, admin_auth, 'policies_diff', {'policy_id': policy.id})['result']
        content = result['structuredContent']
        assert 'current' not in content
        assert set(content['changes']) >= {'config_files', 'pipelines', 'keystore'}
        full = _call(client, admin_auth, 'policies_diff',
                     {'policy_id': policy.id, 'detail': 'full'})['result']['structuredContent']
        assert full['pending_changes'] == content['pending_changes']
        assert 'current' in full

    def test_name_conflict_has_409_hint(self, client, admin_auth, policy):
        result = _call(client, admin_auth, 'policies_create',
                       {'name': policy.name, 'policy_type': 'PACKAGED'})['result']
        assert 'already exists' in result['structuredContent']['error']
        assert result['structuredContent']['hint'] == STATUS_HINTS[409]

    @pytest.mark.parametrize('tool, arguments, expected', [
        ('connections_create', {'name': 'mcp-bad-conn', 'connection_type': 'CENTRALIZED',
                                'connection_mode': 'url', 'auth_type': 'basic',
                                'host': 'https://bad.example.com', 'username': 'elastic',
                                'password': 'changeme'}, 'Nothing was saved'),
        ('connections_update', {'name': 'renamed', 'host': 'https://new-es.example.com',
                                'port': 9200}, 'rolled back'),
        ('connections_test', {}, 'connections_update'),
    ])
    @patch('API.connections_views.manager_views.test_connectivity',
           return_value=(False, 'Connection timed out'))
    def test_connectivity_failure_has_422_hint(self, _mock, client, admin_auth, test_connection,
                                               tool, arguments, expected):
        if tool != 'connections_create':
            arguments = {'connection_id': test_connection.id, **arguments}
        result = _call(client, admin_auth, tool, arguments)['result']
        assert result['isError'] is True
        assert result['structuredContent']['error'] == 'Connection timed out'
        hint = result['structuredContent']['hint']
        assert 'connectivity test failed' in hint and expected in hint

    def test_agent_pipeline_write_reports_not_live(self, client, admin_auth, policy):
        created = _call(client, admin_auth, 'pipelines_create', {
            'policy_id': policy.id, 'name': 'mcp-next', 'lscl': 'input { stdin {} }',
        })['result']
        assert 'policies_deploy' in created['structuredContent']['next_steps']

    def test_read_success_has_no_guidance(self, client, admin_auth, policy):
        result = _call(client, admin_auth, 'policies_get', {'policy_id': policy.id})['result']
        assert 'next_steps' not in result['structuredContent']
        assert 'hint' not in result['structuredContent']

    def test_cpm_not_found_points_to_find(self, client, admin_auth, test_connection):
        with patch('API.pipelines_views.get_elastic_connection') as mock_get_es:
            mock_get_es.return_value.logstash.get_pipeline.side_effect = Exception('404 not found')
            result = _call(client, admin_auth, 'pipelines_get',
                           {'connection_id': test_connection.id, 'name': 'asa-fixed'})['result']
        assert result['isError'] is True
        assert 'pipelines_find' in result['structuredContent']['hint']

    def test_cpm_create_goes_to_elasticsearch_and_reports_live(self, client, admin_auth,
                                                              test_connection, policy):
        with patch('API.pipelines_views.get_elastic_connection') as mock_get_es:
            result = _call(client, admin_auth, 'pipelines_create', {
                'connection_id': test_connection.id, 'name': 'cpm-new', 'lscl': 'input {}',
            })['result']
        assert result['isError'] is False, result
        assert result['structuredContent']['next_steps'].startswith('Live now')
        mock_get_es.return_value.logstash.put_pipeline.assert_called_once()
        assert not Pipeline.objects.filter(name='cpm-new').exists()

    @pytest.mark.parametrize('arguments, expected', [
        ({}, 'Pass pipeline_id (agent pipeline) or connection_id + name (CPM pipeline).'),
        ({'pipeline_id': 1, 'connection_id': 2, 'name': 'x'}, 'not both'),
    ])
    def test_pipeline_source_must_be_one_of_two(self, client, admin_auth, arguments, expected):
        result = _call(client, admin_auth, 'pipelines_delete', arguments)['result']
        assert result['isError'] is True
        assert expected in result['structuredContent']['error']

    def test_argument_for_the_other_pipeline_kind_is_named(self, client, admin_auth, policy):
        result = _call(client, admin_auth, 'pipelines_list',
                       {'policy_id': policy.id, 'include_lscl': True})['result']
        assert result['structuredContent']['error'] == 'include_lscl: not used for agent pipelines.'

    def test_echoed_defaults_and_cpm_name_are_tolerated(self, client, admin_auth, policy):
        pipeline = Pipeline.objects.create(policy=policy, name='asa', lscl='input {}')
        listed = _call(client, admin_auth, 'pipelines_list',
                       {'policy_id': policy.id, 'include_lscl': False})['result']
        assert listed['isError'] is False, listed
        updated = _call(client, admin_auth, 'pipelines_update', {
            'pipeline_id': pipeline.id, 'name': 'asa', 'description': 'kept name'})['result']
        assert updated['isError'] is False, updated
        pipeline.refresh_from_db()
        assert (pipeline.name, pipeline.description) == ('asa', 'kept name')

    def test_enrollment_tokens_are_redacted(self, client, admin_auth, policy):
        EnrollmentToken.objects.create(policy=policy, name='default', token='tok-secret')
        result = _call(client, admin_auth, 'policies_tokens_list', {'policy_id': policy.id})['result']
        token = result['structuredContent']['tokens'][0]
        assert token['name'] == 'default'
        assert token['raw_token'] == REDACTED
        assert token['encoded_token'] == REDACTED
        assert 'tok-secret' not in result['content'][0]['text']


# ---------------------------------------------------------------------------
# Registry drift guard
# ---------------------------------------------------------------------------

_PROBE_METHODS = ('GET', 'POST', 'PUT', 'DELETE')


def _api_routes():
    for pattern in api_urls.urlpatterns:
        if pattern.name and pattern.name != 'api-mcp':
            yield pattern


class TestRegistry:

    def test_tool_names_are_unique_and_grouped(self):
        assert len(TOOLS_BY_NAME) == len(TOOLS)
        for tool in TOOLS:
            assert tool.toolset in TOOLSETS
            assert tool.name.startswith(f'{tool.toolset}_')

    def test_excluded_routes_are_not_exposed(self):
        exposed = {(t.url_name, t.method) for t in concrete_tools()}
        assert not exposed & EXCLUDED_ROUTES

    def test_pipeline_tools_cover_agent_and_cpm_routes(self):
        for name in ('pipelines_list', 'pipelines_get', 'pipelines_create', 'pipelines_update',
                     'pipelines_delete'):
            tool = TOOLS_BY_NAME[name]
            routes = [v.tool.url_name for v in tool.variants]
            assert len(routes) == 2 and any('centralized' in r for r in routes), name
            assert all(v.tool.method == tool.method for v in tool.variants), name

    def test_variant_arguments_are_advertised(self):
        """Every argument a variant takes must be in the schema clients see."""
        for tool in TOOLS:
            advertised = set(tool.input_schema()['properties'])
            for variant in tool.variants:
                taken = set(variant.tool.input_schema()['properties'])
                assert taken <= advertised, (tool.name, taken - advertised)

    def test_resolve_rejects_non_object_arguments_later(self):
        tool, args = TOOLS_BY_NAME['pipelines_get'].resolve('nope')
        assert tool is TOOLS_BY_NAME['pipelines_get'] and args == 'nope'
        with pytest.raises(ToolArgumentError):
            validate_arguments(tool, args)

    def test_write_tools_state_admin_only(self):
        for tool in TOOLS:
            if tool.method != 'GET' and not tool.read_only:
                assert 'Admin only.' in tool.description, tool.name

    @pytest.mark.parametrize('name', ['connections_test', 'pipelines_simulate', 'snmp_deploy_diff'])
    def test_side_effect_free_posts_are_read_only(self, name):
        assert TOOLS_BY_NAME[name].annotations() == {'readOnlyHint': True}

    @pytest.mark.parametrize('name, preview', [
        ('policies_deploy', 'policies_diff'),
        ('snmp_deploy_apply', 'snmp_deploy_diff'),
    ])
    def test_deploy_tools_require_preview_and_confirmation(self, name, preview):
        description = TOOLS_BY_NAME[name].description
        assert preview in description
        assert 'confirm' in description

    def test_every_destructive_deploy_is_covered(self):
        deploys = {t.name for t in TOOLS if t.destructive}
        assert deploys == {'policies_deploy', 'snmp_deploy_apply'}

    def test_hints_are_error_statuses(self):
        for tool in TOOLS:
            assert all(400 <= status < 600 for status in tool.hints), tool.name

    def test_guidance_only_names_real_tools(self):
        """Tool names mentioned in hints and next_steps must exist."""
        import re
        tools = TOOLS + concrete_tools()
        texts = [t.next_steps for t in tools] + [h for t in tools for h in t.hints.values()]
        texts += list(STATUS_HINTS.values())
        mentioned = {m for text in texts for m in re.findall(r'\b[a-z]+_[a-z_]+\b', text)}
        assert mentioned - set(TOOLS_BY_NAME) - {'policy_id', 'connection_id', 'next_steps'} == set()

    def test_every_tool_reverses(self):
        for tool in concrete_tools():
            kwargs = {name: (1 if s['type'] == 'integer' else 'x')
                      for name, s in tool.path_params.items()}
            assert reverse(tool.url_name, kwargs=kwargs).startswith('/api/')

    def test_every_route_has_a_tool_or_exclusion(self):
        covered = {t.url_name for t in concrete_tools()} | {name for name, _ in EXCLUDED_ROUTES}
        missing = [p.name for p in _api_routes() if p.name not in covered]
        assert not missing, f'API routes without MCP tools: {missing}'

    @pytest.mark.django_db
    def test_uncovered_methods_are_not_supported(self, client, admin_auth, test_user,
                                                 test_connection):
        """Any method a route accepts must be a tool or an explicit exclusion."""
        covered = {(t.url_name, t.method) for t in concrete_tools()} | EXCLUDED_ROUTES
        # Some views look up the object before checking the method.
        ids = {'connection_id': test_connection.id, 'user_id': test_user.id}
        for pattern in _api_routes():
            kwargs = {name: (ids.get(name, 999999)
                             if conv.__class__.__name__ == 'IntConverter' else 'nope')
                      for name, conv in pattern.pattern.converters.items()}
            url = reverse(pattern.name, kwargs=kwargs)
            for method in _PROBE_METHODS:
                if (pattern.name, method) in covered:
                    continue
                response = client.generic(method, url, '{}', content_type='application/json',
                                          **admin_auth)
                assert response.status_code == 405, (
                    f'{method} {url} returned {response.status_code}: add an MCP tool for it '
                    f'or list it in EXCLUDED_ROUTES'
                )


# ---------------------------------------------------------------------------
# Guides
# ---------------------------------------------------------------------------

def _mentioned_tool_names(text):
    """Tool-like names in ``text``; ``snmp_deploy_*`` style prefixes end in ``_``."""
    import re
    prefixes = '|'.join(TOOLSETS)
    return set(re.findall(rf'\b(?:{prefixes})_[a-z_]+', text))


def _is_real_tool(name):
    if name.endswith('_'):
        return any(tool.startswith(name) for tool in TOOLS_BY_NAME)
    return name in TOOLS_BY_NAME


@pytest.mark.django_db
class TestGuides:

    def test_guides_tools(self, client, admin_auth):
        listed = _call(client, admin_auth, 'guides_list')['result']['structuredContent']
        assert [g['topic'] for g in listed['guides']] == list(GUIDES)
        got = _call(client, admin_auth, 'guides_get', {'topic': 'deploy'})['result']
        assert got['structuredContent']['content'] == read_guide('deploy')

    def test_guides_get_unknown_topic_is_tool_error(self, client, admin_auth):
        result = _call(client, admin_auth, 'guides_get', {'topic': 'nope'})['result']
        assert result['isError'] is True
        assert 'Valid topics' in result['structuredContent']['error']

    def test_readonly_key_can_read_guides(self, client, readonly_auth):
        result = _call(client, readonly_auth, 'guides_get', {'topic': 'concepts'})['result']
        assert result['isError'] is False

    def test_every_guide_file_exists(self):
        for topic in GUIDES:
            assert read_guide(topic).startswith('# '), topic

    def test_missing_guide_file_is_404_not_500(self, client, admin_auth, tmp_path):
        with patch('API.guides.GUIDES_DIR', tmp_path):
            result = _call(client, admin_auth, 'guides_get', {'topic': 'concepts'})['result']
        assert result['isError'] is True
        assert 'not installed' in result['structuredContent']['error']

    def test_admin_only_label_matches_readonly_access(self, client, readonly_auth):
        """'Admin only.' in a description must mean exactly that a readonly key gets 403."""
        mismatched = []
        for tool in TOOLS:
            schema = (tool.variants[0].tool if tool.variants else tool).input_schema()
            args = {name: (999999 if schema['properties'][name]['type'] == 'integer' else 'x')
                    for name in schema['required']}
            with patch('API.pipelines_views.get_elastic_connection'), \
                    patch('API.pipelines_views._check_centralized_connection_exists', return_value=None):
                result = _call(client, readonly_auth, tool.name, args)
            payload = json.loads(result['result']['content'][0]['text'])
            forbidden = isinstance(payload, dict) and payload.get('hint') == STATUS_HINTS[403]
            if forbidden != ('Admin only.' in tool.description):
                mismatched.append(tool.name)
        assert not mismatched, ', '.join(mismatched)

    def test_guides_only_name_real_tools(self):
        mentioned = set().union(*(_mentioned_tool_names(read_guide(t)) for t in GUIDES))
        assert mentioned
        assert {n for n in mentioned if not _is_real_tool(n)} == set()


# ---------------------------------------------------------------------------
# Finding pipelines by name
# ---------------------------------------------------------------------------

_CPM_MATCH = {'type': 'cpm', 'name': 'asa-new', 'connection_id': 2, 'connection_name': 'Homelab'}
_AGENT_MATCH = {'type': 'agent', 'name': 'asa-new', 'pipeline_id': 9, 'policy_id': 1,
                'policy_name': 'Default', 'managed_by': 'user'}
_DOWN = {'connection_id': 3, 'connection_name': 'Lab', 'error': 'timed out'}


class TestFindGuidance:

    def test_single_match_names_the_simulate_arguments(self):
        cpm = _find_next_steps({'matches': [_CPM_MATCH]})
        assert "connection_id=2 and name='asa-new'" in cpm
        assert 'pipeline_id=9' in _find_next_steps({'matches': [_AGENT_MATCH]})
        assert 'described' not in cpm

    def test_single_match_with_similar_warns_about_keywords(self):
        steps = _find_next_steps({'matches': [_CPM_MATCH], 'similar': [_AGENT_MATCH]})
        assert "name='asa-new'" in steps
        assert 'described the pipeline' in steps and 'ask which' in steps

    def test_several_matches_asks_which(self):
        assert 'ask which' in _find_next_steps({'matches': [_CPM_MATCH, _AGENT_MATCH]})

    def test_unreachable_connection_never_offers_to_build(self):
        steps = _find_next_steps({'matches': [], 'similar': [], 'unreachable': [_DOWN]})
        assert 'Lab could not be searched' in steps
        assert ASK_TO_BUILD_PIPELINE not in steps

    def test_similar_names_are_offered_before_building(self):
        steps = _find_next_steps({'matches': [], 'similar': [_CPM_MATCH], 'unreachable': []})
        assert steps.index('similar pipelines') < steps.index(ASK_TO_BUILD_PIPELINE)
        assert 'do not pick one yourself' in steps

    def test_no_match_asks_the_exact_question(self):
        steps = _find_next_steps({'matches': [], 'similar': [], 'unreachable': []})
        assert f'"{ASK_TO_BUILD_PIPELINE}"' in steps

    def test_question_has_one_home_in_code_and_the_guide_quotes_it(self):
        assert f'> {ASK_TO_BUILD_PIPELINE}' in read_guide('simulation')
        assert ASK_TO_BUILD_PIPELINE not in _INSTRUCTIONS
        assert not [t.name for t in TOOLS if ASK_TO_BUILD_PIPELINE in json.dumps(t.to_mcp())]


@pytest.mark.django_db
class TestFindTool:

    def test_mcp_result_carries_next_steps_rest_does_not(
        self, client, admin_auth, authenticated_client, test_connection
    ):
        with patch('API.pipelines_views.get_elastic_connection') as mock_get_es:
            mock_get_es.return_value.options.return_value.logstash.get_pipeline.return_value = {
                'asa-new': {},
            }
            mcp = _call(client, admin_auth, 'pipelines_find', {'name': 'asa-new'})['result']
            rest = authenticated_client.get('/api/pipelines/find/?name=asa-new').json()

        found = mcp['structuredContent']
        assert found['matches'][0]['connection_id'] == test_connection.id
        assert f'connection_id={test_connection.id}' in found['next_steps']
        assert 'next_steps' not in rest

    def test_name_is_required(self, client, admin_auth):
        result = _call(client, admin_auth, 'pipelines_find', {})['result']
        assert result['isError'] is True
        assert 'name' in result['structuredContent']['error']


# ---------------------------------------------------------------------------
# Compact defaults
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCompactDefaults:

    def test_defaults_are_in_schema(self):
        schema = TOOLS_BY_NAME['pipelines_simulate'].input_schema()
        assert schema['properties']['detail']['default'] == 'steps'

    def test_simulate_defaults_to_steps(self):
        args = validate_arguments(TOOLS_BY_NAME['pipelines_simulate'], {'event': 'x'})
        assert args == {'event': 'x', 'detail': 'steps'}
        args = validate_arguments(TOOLS_BY_NAME['pipelines_simulate'], {'detail': 'full'})
        assert args['detail'] == 'full'

    def test_policies_list_omits_config_unless_asked(self, client, admin_auth, policy):
        def first(arguments):
            body = _call(client, admin_auth, 'policies_list', arguments)['result']
            return next(p for p in body['structuredContent']['policies'] if p['id'] == policy.id)
        assert 'logstash_yml' not in first({})
        assert first({'include_config': True})['logstash_yml'] == '# yml'

    def test_policies_get_omits_config_unless_asked(self, client, admin_auth, policy):
        def get(arguments):
            body = _call(client, admin_auth, 'policies_get', {'policy_id': policy.id, **arguments})
            return body['result']['structuredContent']['policy']
        compact = get({})
        assert compact['name'] == policy.name
        assert not {'logstash_yml', 'jvm_options', 'log4j2_properties'} & set(compact)
        assert get({'include_config': True})['logstash_yml'] == '# yml'

    def test_cpm_list_omits_lscl_unless_asked(self, client, admin_auth, test_connection):
        with patch('API.pipelines_views.get_elastic_connection') as mock_get_es:
            mock_get_es.return_value.logstash.get_pipeline.return_value = {
                'cpm-pipe': {'pipeline': 'input {}'},
            }
            compact = _call(client, admin_auth, 'pipelines_list',
                            {'connection_id': test_connection.id})['result']
            full = _call(client, admin_auth, 'pipelines_list',
                         {'connection_id': test_connection.id, 'include_lscl': True})['result']
        assert 'lscl' not in compact['structuredContent']['pipelines'][0]
        assert full['structuredContent']['pipelines'][0]['lscl'] == 'input {}'


# ---------------------------------------------------------------------------
# Argument aliases
# ---------------------------------------------------------------------------

class TestAliases:

    def test_id_maps_to_the_only_path_param(self):
        for name in ('snmp_credentials_get', 'snmp_templates_delete', 'snmp_networks_update',
                     'snmp_profiles_get', 'policies_get'):
            tool = TOOLS_BY_NAME[name]
            target = next(iter(tool.path_params))
            assert validate_arguments(tool, {'id': '5'})[target] == 5

    def test_query_maps_to_name_for_find(self):
        args = validate_arguments(TOOLS_BY_NAME['pipelines_find'], {'query': 'asa'})
        assert args == {'name': 'asa'}

    def test_conflicting_alias_is_rejected(self):
        from API.mcp.dispatch import ToolArgumentError
        with pytest.raises(ToolArgumentError, match='network_id'):
            validate_arguments(TOOLS_BY_NAME['snmp_networks_get'], {'id': 1, 'network_id': 2})

    def test_matching_alias_is_accepted(self):
        args = validate_arguments(TOOLS_BY_NAME['snmp_networks_get'], {'id': 2, 'network_id': 2})
        assert args == {'network_id': 2}

    def test_no_id_alias_with_two_path_params(self):
        assert 'id' not in TOOLS_BY_NAME['policies_tokens_get'].argument_aliases()

    def test_aliases_are_not_advertised(self):
        for tool in TOOLS:
            properties = tool.input_schema()['properties']
            assert not set(tool.aliases) & set(properties), tool.name

    @pytest.mark.django_db
    def test_alias_works_end_to_end(self, client, admin_auth, policy):
        body = _call(client, admin_auth, 'policies_get', {'id': policy.id})['result']
        assert body.get('isError') is not True
        assert policy.name in json.dumps(body['structuredContent'])


# ---------------------------------------------------------------------------
# SNMP deploy diff
# ---------------------------------------------------------------------------

_PLAN = {
    'success': True,
    'has_changes': True,
    'blocking_errors': [],
    'connections': [{'id': 1, 'name': 'es'}],
    'networks': [
        {'network_name': 'lab', 'pipeline_name': 'snmp-lab-discovery', 'action': 'update',
         'pipeline_type': 'discovery', 'current': 'input {}\nfilter { a }\n',
         'new': 'input { snmp { community => "LSCL-SECRET" } }\nfilter { b }\n'
                'output { elasticsearch { api_key => \'LSCL-KEY\' password => "${ES_PW}" } }\n',
         'destination_type': 'cpm', 'destination_name': 'es',
         'manual_keystore_keys': ['snmp_es_1_api_key'],
         'manual_keystore_values': {'snmp_es_1_api_key': 'TOP-SECRET'}},
        {'network_name': 'lab', 'pipeline_name': 'snmp-lab-default-polling', 'action': 'create',
         'pipeline_type': 'polling', 'current': '', 'new': 'input {}\n'},
        {'network_name': 'Keystore', 'pipeline_name': 'Keystore: p', 'action': 'update',
         'pipeline_type': 'keystore', 'current': '', 'new': 'k'},
    ],
}


def _fake_diff(_request):
    from django.http import JsonResponse
    return JsonResponse(_PLAN)


@pytest.mark.parametrize('lscl,expected', [
    ('community => "public"', 'community => "[redacted]"'),
    ('"community" => "public"', '"community" => "[redacted]"'),
    ("auth_pass => 'line1\n\tline2' next => \"ok\"", "auth_pass => '[redacted]' next => \"ok\""),
    ('community => ["a", \'b\']', 'community => ["[redacted]", \'[redacted]\']'),
    ('community => ["${snmp_1_v2}"]', 'community => ["${snmp_1_v2}"]'),
    ('password => "a\\"b" host => "h"', 'password => "[redacted]" host => "h"'),
    ('api_key => "${ES_KEY}tail"', 'api_key => "[redacted]"'),
    ('ssl_keystore_password => "x"', 'ssl_keystore_password => "[redacted]"'),
    ('host => "community"', 'host => "community"'),
])
def test_mask_secrets(lscl, expected):
    from API.snmp_views import _mask_secrets
    assert _mask_secrets(lscl) == expected


@pytest.mark.django_db
class TestSnmpDeployDiff:

    def _mcp(self, client, admin_auth, arguments=None):
        with patch('SNMP.snmp_crud.GetDeployDiff', _fake_diff):
            return _call(client, admin_auth, 'snmp_deploy_diff', arguments)['result']

    def test_mcp_defaults_to_summary(self, client, admin_auth):
        body = self._mcp(client, admin_auth)['structuredContent']
        assert body['counts'] == {'create': 1, 'update': 1, 'delete': 0,
                                  'keystore_updates': 1, 'errors': 0}
        assert [row['pipeline_name'] for row in body['networks']] == [
            'snmp-lab-discovery', 'snmp-lab-default-polling', 'Keystore: p']
        assert not any('current' in row or 'new' in row for row in body['networks'])

    def test_changes_returns_unified_diff_for_selected_pipelines(self, client, admin_auth):
        body = self._mcp(client, admin_auth, {
            'detail': 'changes', 'pipelines': ['snmp-lab-discovery']})['structuredContent']
        assert len(body['networks']) == 1
        assert '-filter { a }' in body['networks'][0]['diff']
        assert '+filter { b }' in body['networks'][0]['diff']
        assert body['counts']['create'] == 1

    def test_secrets_are_redacted_over_mcp(self, client, admin_auth):
        for detail in ('summary', 'changes', 'full'):
            result = self._mcp(client, admin_auth, {'detail': detail})
            assert 'TOP-SECRET' not in json.dumps(result), detail

    def test_config_secrets_are_masked_at_every_detail(self, client, admin_auth, authenticated_client):
        for detail in ('changes', 'full'):
            text = json.dumps(self._mcp(client, admin_auth, {'detail': detail}))
            assert 'LSCL-SECRET' not in text and 'LSCL-KEY' not in text, detail
            assert '${ES_PW}' in text, detail
        with patch('SNMP.snmp_crud.GetDeployDiff', _fake_diff):
            rest = json.dumps(authenticated_client.post('/api/snmp/deploy/diff/').json())
        assert 'LSCL-SECRET' not in rest and 'LSCL-KEY' not in rest

    def test_trap_and_multiline_secrets_are_masked(self, client, admin_auth, authenticated_client):
        from django.http import JsonResponse
        trap = {'network_name': 'lab', 'pipeline_name': 'snmp-lab-trap', 'action': 'update',
                'pipeline_type': 'trap', 'current': '',
                'new': 'input { snmptrap { community => ["TRAP-SECRET"] } }\n'
                       'input { snmp { "community" => "QUOTED-SECRET" auth_pass => \'LINE-1\n\tLINE-2\' } }\n'}
        plan = {**_PLAN, 'networks': [trap]}
        with patch('SNMP.snmp_crud.GetDeployDiff', lambda _request: JsonResponse(plan)):
            texts = [json.dumps(_call(client, admin_auth, 'snmp_deploy_diff', {'detail': d})['result'])
                     for d in ('changes', 'full')]
            texts.append(json.dumps(authenticated_client.post('/api/snmp/deploy/diff/').json()))
        for text in texts:
            for secret in ('TRAP-SECRET', 'QUOTED-SECRET', 'LINE-1', 'LINE-2'):
                assert secret not in text

    def test_rest_default_returns_full_entries(self, authenticated_client):
        with patch('SNMP.snmp_crud.GetDeployDiff', _fake_diff):
            body = authenticated_client.post('/api/snmp/deploy/diff/').json()
        assert [e['pipeline_name'] for e in body['networks']] == [e['pipeline_name'] for e in _PLAN['networks']]
        assert body['networks'][0]['current'] == _PLAN['networks'][0]['current']
        assert body['counts']['create'] == 1

    def test_bad_detail_is_400(self, authenticated_client):
        response = authenticated_client.post('/api/snmp/deploy/diff/', data={'detail': 'all'},
                                             content_type='application/json')
        assert response.status_code == 400

    def test_plan_with_changes_asks_for_confirmation(self, client, admin_auth):
        steps = self._mcp(client, admin_auth)['structuredContent']['next_steps']
        assert 'only after they confirm' in steps

    def test_empty_plan_says_nothing_to_deploy(self, client, admin_auth):
        from django.http import JsonResponse
        empty = {**_PLAN, 'has_changes': False, 'networks': []}
        with patch('SNMP.snmp_crud.GetDeployDiff', lambda _request: JsonResponse(empty)):
            body = _call(client, admin_auth, 'snmp_deploy_diff')['result']['structuredContent']
        assert body['next_steps'].startswith('Nothing to deploy')
        assert 'confirm' not in body['next_steps']


# ---------------------------------------------------------------------------
# Recently changed pipelines
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecentPipelines:

    def test_sorts_agent_and_cpm_newest_first(self, client, admin_auth, policy, test_connection):
        Pipeline.objects.create(policy=policy, name='agent-pipe', lscl='input {}')
        with patch('API.pipelines_views.get_elastic_connection') as mock_get_es:
            mock_get_es.return_value.options.return_value.logstash.get_pipeline.return_value = {
                'cpm-future': {'last_modified': '2999-01-01T00:00:00.000Z'},
                'cpm-old': {'last_modified': '2001-01-01T00:00:00.000Z'},
            }
            body = _call(client, admin_auth, 'pipelines_recent', {})['result']['structuredContent']
            since = _call(client, admin_auth, 'pipelines_recent',
                          {'since': '2002-01-01'})['result']['structuredContent']
        assert [p['name'] for p in body['pipelines']] == ['cpm-future', 'agent-pipe', 'cpm-old']
        assert [p['name'] for p in since['pipelines']] == ['cpm-future', 'agent-pipe']

    def test_bad_since_is_400(self, authenticated_client):
        response = authenticated_client.get('/api/pipelines/recent/?since=yesterday')
        assert response.status_code == 400
