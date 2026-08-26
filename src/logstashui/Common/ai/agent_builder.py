#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Centralised helper for managing Elastic Agent Builder resources
(tools, skills, agents) via the Elastic Agent Builder REST API.

API reference: https://www.elastic.co/docs/explore-analyze/ai-features/agent-builder/kibana-api

Typical usage
─────────────
    from Common.assets.agent_builder import AgentBuilder, RESOURCE_TOOL, RESOURCE_SKILL, RESOURCE_AGENT

    builder = AgentBuilder(connection_id=42)
    # or, for URL-based connections:
    builder = AgentBuilder(connection_id=42, kibana_url_override="https://my-kibana:5601")

    results = builder.check_resources(
        tools  = MY_TOOL_DEFINITIONS,
        skills = MY_SKILL_DEFINITIONS,
        agents = MY_AGENT_DEFINITIONS,
    )
    # results['tools'][0] == {'id': '...', 'display_name': '...', 'status': 'missing'|'matches'|'differs', ...}

    ok, data = builder.create_resource(RESOURCE_TOOL, MY_TOOL_DEFINITIONS[0])
    ok, data = builder.update_resource(RESOURCE_TOOL, 'my-tool-id', MY_TOOL_DEFINITIONS[0])
"""

import json
import logging
import os

import requests

logger = logging.getLogger(__name__)


# ── Directory loader ───────────────────────────────────────────────────────────

def load_resources_from_directory(base_dir):
    """
    Load Agent Builder resource definitions from a directory that follows the
    standard layout::

        <base_dir>/
            tools/   *.json
            skills/  *.json
            agents/  *.json

    Each JSON file must contain a single resource definition object with at
    minimum an ``id`` field.  Keys whose names start with ``_`` (e.g.
    ``_comment``) are stripped before returning so that internal annotations
    in the files do not get sent to Kibana.

    Returns
    ───────
    ``(tools, skills, agents)`` — three lists of dicts, each ready to pass to
    :py:meth:`AgentBuilder.check_resources`.
    """
    result = {RESOURCE_TOOL: [], RESOURCE_SKILL: [], RESOURCE_AGENT: []}

    for resource_type, subdir in [
        (RESOURCE_TOOL,  'tools'),
        (RESOURCE_SKILL, 'skills'),
        (RESOURCE_AGENT, 'agents'),
    ]:
        folder = os.path.join(base_dir, subdir)
        if not os.path.isdir(folder):
            continue

        for filename in sorted(os.listdir(folder)):
            if not filename.endswith('.json'):
                continue

            filepath = os.path.join(folder, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as fh:
                    raw = json.load(fh)

                # _content_from_file: load a sibling file's text into the `content` field.
                # The path is resolved relative to the JSON file's own directory.
                if '_content_from_file' in raw:
                    content_path = os.path.join(os.path.dirname(filepath), raw['_content_from_file'])
                    try:
                        with open(content_path, 'r', encoding='utf-8') as cf:
                            raw['content'] = cf.read()
                    except Exception as ce:
                        logger.warning("_content_from_file for %s failed: %s", filepath, ce)

                # Strip internal annotation keys (e.g. _comment, _content_from_file)
                definition = {k: v for k, v in raw.items() if not k.startswith('_')}

                if 'id' not in definition:
                    logger.warning("Skipping %s — no 'id' field", filepath)
                    continue

                result[resource_type].append(definition)
                logger.debug("Loaded %s resource: %s", resource_type, definition['id'])

            except Exception as exc:
                logger.error("Failed to load %s: %s", filepath, exc)

    return result[RESOURCE_TOOL], result[RESOURCE_SKILL], result[RESOURCE_AGENT]


# ── Status constants ───────────────────────────────────────────────────────────

STATUS_MISSING = 'missing'   # resource does not exist in Kibana
STATUS_MATCHES = 'matches'   # exists and content matches our definition
STATUS_DIFFERS = 'differs'   # exists but content differs from our definition
STATUS_ERROR   = 'error'     # an API error occurred for this resource


# ── Resource type constants ────────────────────────────────────────────────────

RESOURCE_TOOL  = 'tool'
RESOURCE_SKILL = 'skill'
RESOURCE_AGENT = 'agent'


# ── Kibana API paths ───────────────────────────────────────────────────────────

_PATHS = {
    RESOURCE_TOOL:  '/api/agent_builder/tools',
    RESOURCE_SKILL: '/api/agent_builder/skills',
    RESOURCE_AGENT: '/api/agent_builder/agents',
}


# ── Comparison keys ────────────────────────────────────────────────────────────
# Only these fields are compared when deciding whether a resource is "different".
# Server-side metadata (id, created_at, updated_at, …) is intentionally excluded.

_COMPARE_KEYS = {
    RESOURCE_TOOL:  ['type', 'description', 'configuration', 'tags'],
    RESOURCE_SKILL: ['name', 'description', 'content', 'tool_ids', 'referenced_content'],
    RESOURCE_AGENT: ['name', 'description', 'configuration', 'labels'],
}

# ── Field-strip keys ───────────────────────────────────────────────────────────
# Kibana rejects unknown fields with HTTP 400 "Additional properties are not
# allowed".  We strip offending keys before sending rather than requiring every
# definition file to omit them manually.
#
# POST (create) – fields not accepted by the Kibana create endpoint:
#   agents: 'type', 'visibility' are not part of the agent schema
#
# PUT (update) – fields not accepted by the Kibana update endpoint:
#   all types: 'id' belongs in the URL, not the body
#   tools:     'type' is immutable after creation
#   agents:    'type', 'visibility' are not part of the agent update schema

_POST_STRIP_KEYS = {
    RESOURCE_TOOL:  set(),
    RESOURCE_SKILL: set(),
    RESOURCE_AGENT: {'type', 'visibility'},
}

_PUT_STRIP_KEYS = {
    RESOURCE_TOOL:  {'id', 'type'},
    RESOURCE_SKILL: {'id'},
    RESOURCE_AGENT: {'id', 'type', 'visibility'},
}


class AgentBuilder:
    """
    Client for the Elastic Elastic Agent Builder API.

    Instantiation
    ─────────────
    - ``connection_id``: LogstashUI DB Connection pk.  The Kibana URL and
      auth credentials are derived automatically from the Connection record.
    - ``kibana_url_override``: Used as the Kibana origin after
      ``normalize_kibana_url`` (``.es.`` hosts become ``.kb.``, paths stripped).
      If omitted, the origin is derived from the Connection via
      ``get_kibana_url``.

    At least one of ``connection_id`` or ``kibana_url_override`` must be
    provided.
    """

    # Connect timeout is short so a wrong host (ES instead of Kibana) fails
    # fast. Read timeout is longer because the SNMP catalog skill payload is
    # ~100 KB. Streaming converse uses a separate 300s read timeout.
    _CONNECT_TIMEOUT = 5
    _READ_TIMEOUT = 20
    _PROBE_READ_TIMEOUT = 8
    _INVOKE_READ_TIMEOUT = 300

    def __init__(self, connection_id=None, kibana_url_override=None):
        from Common.elastic_utils import _get_creds, get_kibana_url, normalize_kibana_url

        if connection_id is None and kibana_url_override is None:
            raise ValueError(
                "Supply at least connection_id or kibana_url_override"
            )

        self._creds = _get_creds(connection_id) if connection_id else {}
        self._connection_id = connection_id

        raw_url = (kibana_url_override or '').strip()
        if not raw_url:
            raw_url = get_kibana_url(connection_id)
        self._kibana_url = normalize_kibana_url(raw_url).rstrip('/')
        logger.info("AgentBuilder Kibana origin: %s", self._kibana_url)

        # Build reusable headers.  Writes also need kbn-xsrf (added per-call).
        self._read_headers = {
            'Content-Type': 'application/json',
        }
        if 'api_key' in self._creds:
            self._read_headers['Authorization'] = f"ApiKey {self._creds['api_key']}"

        self._write_headers = {**self._read_headers, 'kbn-xsrf': 'true'}
        self._auth = self._creds.get('http_auth')  # (username, password) or None

        self._session = requests.Session()
        self._session.verify = False
        self._session.auth = self._auth
        self._session.headers.update(self._read_headers)

    # ── Private HTTP helpers ───────────────────────────────────────────────────

    def _timeout(self, read=None):
        return (self._CONNECT_TIMEOUT, self._READ_TIMEOUT if read is None else read)

    def _request(self, method, path, **kwargs):
        url = f"{self._kibana_url}{path}"
        timeout = kwargs.pop('timeout', None) or self._timeout()
        headers = kwargs.pop('headers', None)
        req_kwargs = dict(timeout=timeout, allow_redirects=False, **kwargs)
        if headers is not None:
            req_kwargs['headers'] = headers
        return self._session.request(method, url, **req_kwargs)

    def _get(self, path, timeout=None):
        return self._request('GET', path, timeout=timeout)

    def _post(self, path, body, timeout=None):
        return self._request('POST', path, json=body, headers=self._write_headers,
                             timeout=timeout)

    def _put(self, path, body, timeout=None):
        return self._request('PUT', path, json=body, headers=self._write_headers,
                             timeout=timeout)

    def _delete(self, path, timeout=None):
        return self._request('DELETE', path, headers=self._write_headers,
                             timeout=timeout)

    def _unreachable_message(self, exc):
        hint = (
            f"Could not reach Agent Builder at {self._kibana_url}. "
            "Confirm this is a Kibana URL (*.kb.*), not the Elasticsearch endpoint."
        )
        return f"{hint} ({exc})"

    def _probe_api(self):
        """
        Cheap reachability check against the skills collection.

        Hitting Elasticsearch (or a dead host) returns quickly with
        api_available=False instead of waiting on per-resource GET timeouts
        for the large SNMP catalog skill.
        """
        try:
            resp = self._get(
                _PATHS[RESOURCE_SKILL],
                timeout=self._timeout(self._PROBE_READ_TIMEOUT),
            )
        except requests.exceptions.RequestException as exc:
            return False, self._unreachable_message(exc)

        if resp.status_code == 404:
            return False, (
                "Elastic Agent Builder API not available. "
                "Ensure Kibana ≥ 9.2 and Agent Builder is enabled."
            )
        if resp.status_code in (401, 403):
            return False, (
                f"Authentication failed against {self._kibana_url} "
                f"(HTTP {resp.status_code}). Check the connection API key."
            )
        if resp.status_code >= 400:
            snippet = (resp.text or '')[:300]
            return False, (
                f"Agent Builder probe failed against {self._kibana_url} "
                f"(HTTP {resp.status_code}): {snippet}"
            )
        if 300 <= resp.status_code < 400:
            return False, (
                f"Unexpected redirect from {self._kibana_url} "
                f"(HTTP {resp.status_code}). Is this a Kibana URL?"
            )
        return True, None

    # ── Private: fetch by ID ───────────────────────────────────────────────────

    def _fetch_one(self, resource_type, resource_id):
        """
        Fetch a single resource by ID.

        Returns
        ───────
        (resource_dict, None)   – resource found
        (None, None)            – 404, resource simply doesn't exist
        (None, error_str)       – unexpected HTTP error
        """
        path = f"{_PATHS[resource_type]}/{resource_id}"
        try:
            resp = self._get(path)
        except requests.exceptions.RequestException as exc:
            return None, self._unreachable_message(exc)

        if resp.status_code == 404:
            return None, None

        if not (200 <= resp.status_code < 300):
            snippet = (resp.text or '')[:300]
            return None, f"HTTP {resp.status_code}: {snippet}"

        try:
            return resp.json(), None
        except ValueError:
            return None, (
                f"HTTP {resp.status_code}: non-JSON response from "
                f"{self._kibana_url}{path}"
            )

    # ── Private: comparison ────────────────────────────────────────────────────

    @staticmethod
    def _differs(desired, current, resource_type):
        """Return True if any comparable field differs between desired and current."""
        for key in _COMPARE_KEYS.get(resource_type, []):
            if desired.get(key) != current.get(key):
                return True
        return False

    @staticmethod
    def _diff_fields(desired, current, resource_type):
        """Return list of field names that differ between desired and current."""
        return [
            k for k in _COMPARE_KEYS.get(resource_type, [])
            if desired.get(k) != current.get(k)
        ]

    # ── Public: check ──────────────────────────────────────────────────────────

    def check_resources(self, tools=None, skills=None, agents=None):
        """
        Compare desired definitions against what currently exists in Kibana.

        Parameters
        ──────────
        tools   – list of tool definition dicts  (each must have an ``id`` key)
        skills  – list of skill definition dicts (each must have an ``id`` key)
        agents  – list of agent definition dicts (each must have an ``id`` key)

        Returns
        ───────
        {
            'api_available': bool,
            'error': str | None,       # top-level error (e.g. API not found)
            'tools':  [ ResourceResult, … ],
            'skills': [ ResourceResult, … ],
            'agents': [ ResourceResult, … ],
        }

        ResourceResult:
        {
            'id':           str,
            'display_name': str,
            'status':       'missing' | 'matches' | 'differs' | 'error',
            'differences':  [ field_name, … ],   # non-empty only when status=='differs'
            'error':        str | None,
        }
        """
        results = {
            'api_available': True,
            'error': None,
            'tools':  [],
            'skills': [],
            'agents': [],
        }

        available, probe_err = self._probe_api()
        if not available:
            results['api_available'] = False
            results['error'] = probe_err
            return results

        resource_groups = [
            (RESOURCE_TOOL,  tools  or []),
            (RESOURCE_SKILL, skills or []),
            (RESOURCE_AGENT, agents or []),
        ]

        for resource_type, desired_list in resource_groups:
            plural_key = f"{resource_type}s"

            for desired in desired_list:
                rid = desired.get('id')
                display = desired.get('name') or rid

                current, err = self._fetch_one(resource_type, rid)

                if err:
                    results[plural_key].append({
                        'id': rid,
                        'display_name': display,
                        'status': STATUS_ERROR,
                        'differences': [],
                        'error': err,
                    })
                    continue

                if current is None:
                    status      = STATUS_MISSING
                    differences = []
                elif self._differs(desired, current, resource_type):
                    status      = STATUS_DIFFERS
                    differences = self._diff_fields(desired, current, resource_type)
                else:
                    status      = STATUS_MATCHES
                    differences = []

                results[plural_key].append({
                    'id':           rid,
                    'display_name': display,
                    'status':       status,
                    'differences':  differences,
                    'error':        None,
                })

        return results

    # ── Public: create / update / delete ──────────────────────────────────────

    def create_resource(self, resource_type, definition):
        """
        POST a new resource to Kibana.

        Returns (True, response_dict) on success, (False, error_str) on failure.
        """
        strip = _POST_STRIP_KEYS.get(resource_type, set())
        body  = {k: v for k, v in definition.items() if k not in strip}
        try:
            resp  = self._post(_PATHS[resource_type], body)
        except requests.exceptions.RequestException as exc:
            return False, self._unreachable_message(exc)
        if 200 <= resp.status_code < 300:
            return True, resp.json()
        return False, f"HTTP {resp.status_code}: {resp.text[:400]}"

    def update_resource(self, resource_type, resource_id, definition):
        """
        PUT (overwrite) an existing resource in Kibana.

        The ``id`` field is part of the URL path for PUT requests and must not
        be included in the request body — Kibana rejects it with a 400.

        Returns (True, response_dict) on success, (False, error_str) on failure.
        """
        path      = f"{_PATHS[resource_type]}/{resource_id}"
        strip     = _PUT_STRIP_KEYS.get(resource_type, {'id'})
        body      = {k: v for k, v in definition.items() if k not in strip}
        try:
            resp = self._put(path, body)
        except requests.exceptions.RequestException as exc:
            return False, self._unreachable_message(exc)
        if 200 <= resp.status_code < 300:
            return True, resp.json()
        return False, f"HTTP {resp.status_code}: {resp.text[:400]}"

    def delete_resource(self, resource_type, resource_id):
        """
        DELETE a resource from Kibana.

        Returns (True, {}) on success, (False, error_str) on failure.
        """
        path = f"{_PATHS[resource_type]}/{resource_id}"
        try:
            resp = self._delete(path)
        except requests.exceptions.RequestException as exc:
            return False, self._unreachable_message(exc)
        if 200 <= resp.status_code < 300:
            try:
                return True, resp.json()
            except Exception:
                return True, {}
        return False, f"HTTP {resp.status_code}: {resp.text[:400]}"

    def invoke_agent(self, agent_id, message, stream=True, conversation_id=None, inference_id=None, configuration_overrides=None):
        """
        Send a user message to an Agent Builder agent via the converse API.

        Sync  (stream=False): POST /api/agent_builder/converse
        Async (stream=True):  POST /api/agent_builder/converse/async  ← preferred

        Parameters
        ──────────
        agent_id        – the ``id`` of the agent (must already exist in Kibana)
        message         – plain-text user message (``input`` field)
        stream          – use the async/streaming endpoint (default: True)
        conversation_id – optional; pass to continue an existing conversation
        inference_id    – reserved for future use; not currently sent to Kibana

        Streaming mode (stream=True)
        ────────────────────────────
        Yields dicts parsed from each ``data:`` SSE line.  Unparseable lines
        are yielded as ``{'raw': <line>}``.  Errors yield ``{'error': <msg>}``.

        Non-streaming mode (stream=False)
        ──────────────────────────────────
        Returns ``(True, response_dict)`` on success or
        ``(False, error_str)`` on failure.
        """
        if stream:
            path = '/api/agent_builder/converse/async'
        else:
            path = '/api/agent_builder/converse'

        url  = f"{self._kibana_url}{path}"
        body = {"input": message, "agent_id": agent_id}
        if conversation_id:
            body["conversation_id"] = conversation_id
        if inference_id:
            body["inference_id"] = inference_id
        if configuration_overrides:
            body["configuration_overrides"] = configuration_overrides

        headers = {**self._write_headers}
        logger.debug("invoke_agent → POST %s (agent=%s, inference_id=%s)", url, agent_id, inference_id)

        if stream:
            headers['Accept'] = 'text/event-stream'
            try:
                resp = self._session.post(
                    url, json=body, headers=headers,
                    timeout=self._timeout(self._INVOKE_READ_TIMEOUT),
                    allow_redirects=False, stream=True,
                )
                if not (200 <= resp.status_code < 300):
                    logger.error("invoke_agent %s → HTTP %s: %s", url, resp.status_code, resp.text[:500])
                    yield {'error': f"HTTP {resp.status_code} — URL: {url} — {resp.text[:300]}"}
                    return

                # SSE events have both an `event:` type line and a `data:` payload line.
                # Buffer the event type so we can attach it to the parsed data dict.
                current_event = None
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        current_event = None  # blank line = SSE event separator
                        continue
                    line = raw_line.decode('utf-8') if isinstance(raw_line, bytes) else raw_line
                    logger.debug("agent_builder SSE raw: %s", line[:300])
                    if line.startswith('event: '):
                        current_event = line[7:].strip()
                        continue
                    if line.startswith('data: '):
                        payload = line[6:]
                        if not payload or payload == '[DONE]':
                            continue
                        try:
                            yield {'event': current_event, 'data': json.loads(payload)}
                        except json.JSONDecodeError:
                            yield {'event': current_event, 'raw': payload}
            except Exception as exc:
                yield {'error': str(exc)}
        else:
            resp = self._session.post(
                url, json=body, headers=headers,
                timeout=self._timeout(self._INVOKE_READ_TIMEOUT),
                allow_redirects=False,
            )
            if 200 <= resp.status_code < 300:
                return True, resp.json()
            return False, f"HTTP {resp.status_code}: {resp.text[:400]}"

    def apply_all_resources(self, tools=None, skills=None, agents=None):
        """
        Create or overwrite every supplied resource in Kibana.

        Resources are applied in dependency order: tools first, then skills,
        then agents.  Each resource is PUT if it already exists or POST if it
        does not.  Errors for individual resources are collected rather than
        aborting the whole run.

        Returns
        ───────
        {
            'success': bool,           # True only if every resource applied cleanly
            'results': [
                {
                    'type':    str,
                    'id':      str,
                    'action':  'created' | 'updated',
                    'success': bool,
                    'error':   str | None,
                },
                …
            ],
        }
        """
        available, probe_err = self._probe_api()
        if not available:
            return {'success': False, 'results': [], 'error': probe_err}

        results = []
        all_ok  = True

        for resource_type, resource_list in [
            (RESOURCE_TOOL,  tools  or []),
            (RESOURCE_SKILL, skills or []),
            (RESOURCE_AGENT, agents or []),
        ]:
            for definition in resource_list:
                rid = definition.get('id')

                # Check whether it already exists to decide create vs update
                existing, err = self._fetch_one(resource_type, rid)
                if err:
                    results.append({
                        'type':    resource_type,
                        'id':      rid,
                        'action':  'unknown',
                        'success': False,
                        'error':   err,
                    })
                    all_ok = False
                    continue

                if existing is None:
                    ok, data = self.create_resource(resource_type, definition)
                    action = 'created'
                else:
                    ok, data = self.update_resource(resource_type, rid, definition)
                    action = 'updated'

                results.append({
                    'type':    resource_type,
                    'id':      rid,
                    'action':  action,
                    'success': ok,
                    'error':   None if ok else data,
                })
                if not ok:
                    all_ok = False

        return {'success': all_ok, 'results': results}
