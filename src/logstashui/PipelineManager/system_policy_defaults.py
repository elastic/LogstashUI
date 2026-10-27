#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Requirements-compliant ``logstash.yml`` defaults for system agent policies.

Pure helpers (no model imports) so the data migration, ``add_policy``, and tests
can share them. The requirement checks mirror ``checkConfigNotifications`` in
``static/js/agent_policies.js`` (the policy editor's "Requirements" tile).
"""

import re

import yaml

# Base Logstash API port written into the seeded yml per policy type. Managed
# and Simulate use these as bases; enroll overrides the port per instance.
LOGSTASH_API_PORTS = {"PACKAGED": 9600, "MANAGED": 9700, "SIMULATE": 9560}

# Seeded values that the original (pre-0031) Managed/Simulate seeds wrote as
# flat dotted keys. Used to recognise a policy yml nobody has edited.
_ORIGINAL_FLAT_SEED_KEYS = {
    "config.reload.automatic": True,
    "config.reload.interval": "2s",
    "xpack.management.enabled": False,
    "api.http.host": "0.0.0.0",
}

_HEADER = "# Policy default logstash.yml (LogstashAgent requirements satisfied)\n"

# Repo license header that pre-commit adds to data/default_logstash.yml. It must
# not be copied into customer policies.
_LICENSE_HEADER_LINES = (
    "#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one",
    "#or more contributor license agreements. Licensed under the Elastic License;",
    "#you may not use this file except in compliance with the Elastic License.",
)


def strip_license_header(text: str) -> str:
    """Remove the repo license header (and the blank line after it) from the top.

    Args:
        text: File contents, possibly starting with the license header.

    Returns:
        ``text`` without the header; unchanged when the header is absent.

    Examples:
        >>> strip_license_header("\\n".join(_LICENSE_HEADER_LINES) + "\\n\\nlog.level: info\\n")
        'log.level: info\\n'
        >>> strip_license_header("log.level: info\\n")
        'log.level: info\\n'
    """
    lines = (text or "").splitlines(keepends=True)
    head = [line.rstrip("\r\n") for line in lines[: len(_LICENSE_HEADER_LINES)]]
    if tuple(head) != _LICENSE_HEADER_LINES:
        return text
    rest = lines[len(_LICENSE_HEADER_LINES):]
    if rest and not rest[0].strip():
        rest = rest[1:]
    return "".join(rest)


def build_required_logstash_yml(policy_type: str, logs_path: str) -> str:
    """Build a ``logstash.yml`` that satisfies every policy requirement.

    Args:
        policy_type: ``PACKAGED``, ``MANAGED``, or ``SIMULATE`` (``DEFAULT`` is
            treated as ``PACKAGED``).
        logs_path: The policy ``logs_path``; written to ``path.logs``. May contain
            an ``{instance_id}`` placeholder.

    Returns:
        Nested YAML text (the shape the policy editor itself emits).

    Examples:
        >>> yml = build_required_logstash_yml("PACKAGED", "/var/log/logstash")
        >>> unmet_requirements(yml, "/var/log/logstash")
        []
    """
    ptype = "PACKAGED" if policy_type in ("DEFAULT", "PACKAGED") else policy_type
    packaged = ptype == "PACKAGED"
    config = {
        "log": {"level": "info", "format": "json"},
        "path": {"logs": logs_path},
        "config": {"reload": {"automatic": True, "interval": "10s" if packaged else "2s"}},
        "api": {
            "enabled": True,
            "http": {
                "host": "127.0.0.1" if packaged else "0.0.0.0",
                "port": LOGSTASH_API_PORTS.get(ptype, 9600),
            },
        },
        "xpack": {"management": {"enabled": False}},
    }
    return _HEADER + yaml.safe_dump(config, default_flow_style=False, sort_keys=False)


def _get(config: dict, dotted: str):
    """Read ``a.b.c`` from flat-dotted or nested config (same as the editor)."""
    if dotted in config:
        return config[dotted]
    current = config
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def unmet_requirements(yml: str, logs_path: str) -> list[str]:
    """List the policy requirements a ``logstash.yml`` does not meet.

    Mirrors ``checkConfigNotifications`` in ``agent_policies.js``.

    Args:
        yml: ``logstash.yml`` text.
        logs_path: The policy ``logs_path`` that ``path.logs`` must equal.

    Returns:
        Names of unmet requirements; empty when the yml is compliant.

    Examples:
        >>> unmet_requirements("", "/var/log/logstash")[:2]
        ['log.level', 'log.format']
    """
    try:
        config = yaml.safe_load(yml or "")
    except yaml.YAMLError:
        config = None
    if not isinstance(config, dict):
        config = {}

    unmet = []
    if _get(config, "log.level") != "info":
        unmet.append("log.level")
    if _get(config, "log.format") != "json":
        unmet.append("log.format")
    # Like the editor: a missing path.logs counts as a mismatch when logs_path is set.
    if logs_path and _get(config, "path.logs") != logs_path:
        unmet.append("path.logs")
    if _get(config, "config.reload.automatic") is not True:
        unmet.append("config.reload.automatic")
    if not str(_get(config, "config.reload.interval") or "").strip():
        unmet.append("config.reload.interval")
    if _get(config, "api.enabled") is False:
        unmet.append("api.enabled")
    if not str(_get(config, "api.http.host") or "").strip():
        unmet.append("api.http.host")
    if not str(_get(config, "api.http.port") or "").strip():
        unmet.append("api.http.port")
    return unmet


def set_path_logs(yml: str, logs_path: str) -> str:
    """Point the ``path.logs`` entry at ``logs_path``.

    Handles a flat ``path.logs:`` key and a ``logs:`` child of a top-level
    ``path:`` block (in any child order). Text is edited line by line so
    comments survive. Returns the input unchanged when there is no entry.

    Args:
        yml: ``logstash.yml`` text.
        logs_path: Value for ``path.logs``.

    Examples:
        >>> set_path_logs("path:\\n  data: /d\\n  logs: /var/log/logstash\\n", "/opt/x/logs")
        'path:\\n  data: /d\\n  logs: /opt/x/logs\\n'
        >>> set_path_logs("path.logs: /a\\n", "/b")
        'path.logs: /b\\n'
    """
    lines = (yml or "").splitlines(keepends=True)
    child_indent = None
    in_path = False
    for i, line in enumerate(lines):
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        if re.match(r"^path\.logs:", body):
            lines[i] = f"path.logs: {logs_path}{ending}"
            return "".join(lines)
        if re.match(r"^path:[ \t]*(#.*)?$", body):
            in_path, child_indent = True, None
            continue
        if not in_path or not body.strip() or body.lstrip().startswith("#"):
            continue
        indent = len(body) - len(body.lstrip())
        if indent == 0:
            in_path = False
            continue
        if child_indent is None:
            child_indent = indent
        match = re.match(r"^([ \t]+)logs:", body)
        if match and indent == child_indent:
            lines[i] = f"{match.group(1)}logs: {logs_path}{ending}"
            return "".join(lines)
    return yml


def retarget_path_logs(yml: str, old_logs_path: str, new_logs_path: str) -> str:
    """Move ``path.logs`` to ``new_logs_path`` only if it pointed at the old path.

    Used when a policy's path scheme is rewritten (Packaged to Managed clone,
    new Managed/Simulate policy) so a yml that tracked the old logs path keeps
    tracking it, while a deliberately different ``path.logs`` is left alone.

    Args:
        yml: ``logstash.yml`` text.
        old_logs_path: The policy ``logs_path`` before the rewrite.
        new_logs_path: The policy ``logs_path`` after the rewrite.

    Examples:
        >>> retarget_path_logs("path:\\n  logs: /a\\n", "/a", "/b")
        'path:\\n  logs: /b\\n'
        >>> retarget_path_logs("path:\\n  logs: /custom\\n", "/a", "/b")
        'path:\\n  logs: /custom\\n'
    """
    try:
        config = yaml.safe_load(yml or "")
    except yaml.YAMLError:
        return yml
    if not isinstance(config, dict):
        return yml
    current = _get(config, "path.logs")
    if current is None or str(current).rstrip("/") != (old_logs_path or "").rstrip("/"):
        return yml
    return set_path_logs(yml, new_logs_path)


def is_untouched_seed(yml: str, policy_type: str) -> bool:
    """True when a system policy's yml is still its original, unedited seed.

    The original seeds were either comment-only (Packaged) or a handful of flat
    keys with fixed values (Managed/Simulate).

    Args:
        yml: Current ``logstash.yml`` text.
        policy_type: ``PACKAGED``, ``MANAGED``, or ``SIMULATE``.

    Examples:
        >>> is_untouched_seed("# only comments\\n", "PACKAGED")
        True
        >>> is_untouched_seed("log:\\n  level: debug\\n", "PACKAGED")
        False
    """
    try:
        config = yaml.safe_load(yml or "")
    except yaml.YAMLError:
        return False
    if config is None:
        return True
    if not isinstance(config, dict):
        return False
    expected = dict(_ORIGINAL_FLAT_SEED_KEYS)
    base_port = LOGSTASH_API_PORTS.get(policy_type)
    expected["api.http.port"] = base_port
    return all(key in expected and expected[key] == value for key, value in config.items())


def build_snapshot(policy, pipelines, keystore) -> dict:
    """Build a revision snapshot with the same shape as a UI/API deploy.

    Args:
        policy: Policy (or historical-model) instance.
        pipelines: List of user pipeline dicts (``name``, ``description``,
            ``lscl``, ``no_input``, ``non_reloadable``).
        keystore: List of user keystore dicts (``key_name``, ``key_value``).
    """
    return {
        "logstash_yml": policy.logstash_yml,
        "jvm_options": policy.jvm_options,
        "log4j2_properties": policy.log4j2_properties,
        "settings_path": policy.settings_path,
        "logs_path": policy.logs_path,
        "binary_path": policy.binary_path,
        "pipelines": pipelines,
        "keystore": keystore,
        "keystore_password_hash": policy.keystore_password_hash,
    }
