#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Helpers for packaged / managed / simulate / embedded agent roles."""

from __future__ import annotations

from django.db.models import Max, Q

from PipelineManager.models import Connection, Policy

# Port scheme: packaged as-is; simulate-N / managed-N = policy base + N (N >= 1)
PACKAGED_AGENT_API_PORT = 9550
PACKAGED_LOGSTASH_API_PORT = 9600
EMBEDDED_AGENT_API_PORT = 9500
EMBEDDED_LOGSTASH_API_PORT = 9560
SIMULATE_AGENT_API_BASE = 9500
SIMULATE_LOGSTASH_API_BASE = 9560
MANAGED_AGENT_API_BASE = 9550
MANAGED_LOGSTASH_API_BASE = 9700
AGENT_OPT_ROOT = "/opt/logstash-agent"
SIMULATE_ROOT = AGENT_OPT_ROOT
MANAGED_ROOT = AGENT_OPT_ROOT
# Legacy path (pre-rename); rewrite on read
_LEGACY_OPT_ROOT = "/opt/LogstashAgent"


def normalize_agent_opt_path(path: str | None) -> str:
    """Map /opt/LogstashAgent/... → /opt/logstash-agent/... (and leave other paths alone)."""
    if not path:
        return ""
    p = str(path)
    if p.startswith(_LEGACY_OPT_ROOT):
        return AGENT_OPT_ROOT + p[len(_LEGACY_OPT_ROOT) :]
    return p.replace(_LEGACY_OPT_ROOT, AGENT_OPT_ROOT)


def normalize_policy_type(policy_type: str | None) -> str:
    """Map legacy DEFAULT → PACKAGED; uppercase."""
    pt = (policy_type or Policy.PolicyType.PACKAGED).upper()
    if pt == "DEFAULT":
        return Policy.PolicyType.PACKAGED
    return pt


def next_simulate_instance_id() -> int:
    """Allocate next free global simulate instance id (1-based)."""
    used = set(
        Connection.objects.filter(
            connection_type=Connection.ConnectionType.AGENT,
            instance_id__isnull=False,
            policy__policy_type=Policy.PolicyType.SIMULATE,
        ).values_list("instance_id", flat=True)
    )
    n = 1
    while n in used:
        n += 1
    return n


def next_managed_instance_id() -> int:
    """Allocate next free managed instance id (1-based), separate from simulate."""
    used = set(
        Connection.objects.filter(
            connection_type=Connection.ConnectionType.AGENT,
            instance_id__isnull=False,
            policy__policy_type=Policy.PolicyType.MANAGED,
        ).values_list("instance_id", flat=True)
    )
    # Also scan path-like agent_ids if any
    n = 1
    while n in used:
        n += 1
    return n


def simulate_paths(instance_id: int) -> dict:
    root = f"{SIMULATE_ROOT}/simulate-{instance_id}"
    return {
        "settings_path": f"{root}/settings",
        "config_path": f"{root}/config",
        "logs_path": f"{root}/logs",
        "data_path": f"{root}/data",
        "keystore_env_file": f"{root}/env",
        "path_root": root,
        "deployment_id": f"simulate-{instance_id}",
    }


def managed_paths(instance_id: int) -> dict:
    root = f"{MANAGED_ROOT}/managed-{instance_id}"
    return {
        "settings_path": f"{root}/settings",
        "config_path": f"{root}/config",
        "logs_path": f"{root}/logs",
        "data_path": f"{root}/data",
        "keystore_env_file": f"{root}/env",
        "path_root": root,
        "deployment_id": f"managed-{instance_id}",
    }


def simulate_ports(instance_id: int, policy: Policy | None = None) -> tuple[int, int]:
    agent_base = SIMULATE_AGENT_API_BASE
    ls_base = SIMULATE_LOGSTASH_API_BASE
    if policy is not None:
        if policy.agent_api_port:
            agent_base = int(policy.agent_api_port)
        if policy.logstash_api_port:
            ls_base = int(policy.logstash_api_port)
    return (agent_base + instance_id, ls_base + instance_id)


def managed_ports(instance_id: int, policy: Policy | None = None) -> tuple[int, int]:
    agent_base = MANAGED_AGENT_API_BASE
    ls_base = MANAGED_LOGSTASH_API_BASE
    if policy is not None:
        if policy.agent_api_port:
            agent_base = int(policy.agent_api_port)
        if policy.logstash_api_port:
            ls_base = int(policy.logstash_api_port)
    return (agent_base + instance_id, ls_base + instance_id)


def apply_managed_path_bundle(policy: Policy, instance_id: int | None = None) -> None:
    """
    Write managed path scheme onto a Policy (used when cloning Packaged → Managed).

    When instance_id is None, stores template placeholders (enroll allocates N).
    When set, stores concrete managed-N paths (tests / display).
    """
    if instance_id is None:
        root = f"{MANAGED_ROOT}/managed-{{instance_id}}"
        policy.settings_path = f"{root}/settings"
        policy.logs_path = f"{root}/logs"
        policy.data_path = f"{root}/data"
        policy.keystore_env_file = f"{root}/env"
        policy.agent_api_port = MANAGED_AGENT_API_BASE
        policy.logstash_api_port = MANAGED_LOGSTASH_API_BASE
    else:
        paths = managed_paths(instance_id)
        agent_port, ls_port = managed_ports(instance_id)
        policy.settings_path = paths["settings_path"]
        policy.logs_path = paths["logs_path"]
        policy.data_path = paths["data_path"]
        policy.keystore_env_file = paths["keystore_env_file"]
        policy.agent_api_port = agent_port
        policy.logstash_api_port = ls_port
    if not policy.logstash_download_dir or "LogstashAgent" in (policy.logstash_download_dir or ""):
        policy.logstash_download_dir = f"{AGENT_OPT_ROOT}/logstash-versions"
    if not policy.binary_path:
        policy.binary_path = "/usr/share/logstash/bin"


def apply_simulate_path_bundle(policy: Policy, instance_id: int | None = None) -> None:
    """
    Write simulate path scheme onto a Policy (used when creating a SIMULATE policy).

    When instance_id is None, stores template placeholders (enroll allocates N).
    When set, stores concrete simulate-N paths (tests / display).
    """
    if instance_id is None:
        root = f"{SIMULATE_ROOT}/simulate-{{instance_id}}"
        policy.settings_path = f"{root}/settings"
        policy.logs_path = f"{root}/logs"
        policy.data_path = f"{root}/data"
        policy.keystore_env_file = f"{root}/env"
        policy.agent_api_port = SIMULATE_AGENT_API_BASE
        policy.logstash_api_port = SIMULATE_LOGSTASH_API_BASE
    else:
        paths = simulate_paths(instance_id)
        agent_port, ls_port = simulate_ports(instance_id)
        policy.settings_path = paths["settings_path"]
        policy.logs_path = paths["logs_path"]
        policy.data_path = paths["data_path"]
        policy.keystore_env_file = paths["keystore_env_file"]
        policy.agent_api_port = agent_port
        policy.logstash_api_port = ls_port
    if not policy.logstash_download_dir or "LogstashAgent" in (policy.logstash_download_dir or ""):
        policy.logstash_download_dir = f"{AGENT_OPT_ROOT}/logstash-versions"
    if not policy.binary_path:
        policy.binary_path = "/usr/share/logstash/bin"


def uses_packaged_default_paths(policy: Policy) -> bool:
    """True when settings/logs still look like distro Packaged defaults (or empty)."""
    settings = (policy.settings_path or "").rstrip("/")
    logs = (policy.logs_path or "").rstrip("/")
    return settings in ("", "/etc/logstash") and logs in ("", "/var/log/logstash")


CREATABLE_POLICY_TYPES = frozenset(
    {
        Policy.PolicyType.PACKAGED,
        Policy.PolicyType.MANAGED,
        Policy.PolicyType.SIMULATE,
    }
)


def parse_creatable_policy_type(raw) -> tuple[str | None, str | None]:
    """
    Return (policy_type, error). Empty/missing defaults to PACKAGED.
    EMBEDDED, DEFAULT, and unknown values are rejected.
    """
    if raw is None or str(raw).strip() == "":
        return Policy.PolicyType.PACKAGED, None
    pt = str(raw).strip().upper()
    if pt == "DEFAULT":
        return None, "policy_type DEFAULT is not allowed; use PACKAGED"
    if pt == Policy.PolicyType.EMBEDDED:
        return None, "Cannot create Embedded Policy"
    if pt not in CREATABLE_POLICY_TYPES:
        return None, f"Invalid policy_type '{raw}'"
    return pt, None


def materialize_simulate_logstash_yml(
    template: str,
    logstash_api_port: int,
    *,
    instance_id: int | None = None,
) -> str:
    """
    Ensure Logstash API port matches the instance and expand ``{instance_id}``.

    Policy editor stores nested YAML (``api: { http: { port: N } }``). Older
    seeds use flat ``api.http.port:``. Both must be rewritten; a naive flat-only
    replace left nested ``port: 9560`` in place while agent expected 9560+N.
    """
    text = template or ""
    if instance_id is not None:
        text = text.replace("{instance_id}", str(instance_id))
    port = int(logstash_api_port)

    # Structured rewrite (preferred for nested UI editor output)
    try:
        import yaml

        data = yaml.safe_load(text)
        if isinstance(data, dict):
            api = data.get("api")
            if not isinstance(api, dict):
                api = {}
                data["api"] = api
            http = api.get("http")
            if not isinstance(http, dict):
                http = {}
                api["http"] = http
            http["port"] = port
            if "host" not in http:
                http["host"] = "0.0.0.0"
            # Keep flat keys in sync when present (or historically used)
            if "api.http.port" in data:
                data["api.http.port"] = port
            if "http.port" in data:
                data["http.port"] = port
            out = yaml.safe_dump(
                data,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
            return out if out.endswith("\n") else out + "\n"
    except Exception:
        pass

    # Line-based fallback for non-YAML or parse failures
    lines: list[str] = []
    port_set = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("api.http.port:") or stripped.startswith("http.port:"):
            lines.append(f"api.http.port: {port}")
            port_set = True
        else:
            lines.append(line)
    if not port_set:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"api.http.port: {port}")
    return "\n".join(lines) + ("\n" if lines else "")


def build_policy_config(policy: Policy, *, instance_id: int | None = None) -> dict:
    """
    Build enrollment / apply policy_config payload.

    For SIMULATE and MANAGED, instance_id is required and paths/ports are instance-specific.
    """
    ptype = normalize_policy_type(policy.policy_type)

    if ptype == Policy.PolicyType.EMBEDDED:
        return {
            "policy_type": Policy.PolicyType.EMBEDDED,
            "deployment_id": "embedded",
            "settings_path": policy.settings_path,
            "logs_path": policy.logs_path,
            "binary_path": policy.binary_path,
            "data_path": policy.data_path or "",
            "agent_api_port": EMBEDDED_AGENT_API_PORT,
            "logstash_api_port": EMBEDDED_LOGSTASH_API_PORT,
            "keystore_env_file": policy.keystore_env_file or "",
            "logstash_source": policy.logstash_source,
            "logstash_version": policy.logstash_version or "",
            "logstash_download_dir": normalize_agent_opt_path(
                policy.logstash_download_dir or f"{AGENT_OPT_ROOT}/logstash-versions"
            ),
            "logstash_yml": materialize_simulate_logstash_yml(
                policy.logstash_yml, EMBEDDED_LOGSTASH_API_PORT, instance_id=None
            ),
            "jvm_options": policy.jvm_options,
            "log4j2_properties": policy.log4j2_properties,
        }

    if ptype == Policy.PolicyType.SIMULATE:
        if not instance_id:
            raise ValueError("instance_id required for SIMULATE policy_config")
        paths = simulate_paths(instance_id)
        agent_port, ls_port = simulate_ports(instance_id, policy)
        yml = materialize_simulate_logstash_yml(
            policy.logstash_yml, ls_port, instance_id=instance_id
        )
        download_dir = normalize_agent_opt_path(
            policy.logstash_download_dir or f"{AGENT_OPT_ROOT}/logstash-versions"
        )
        if not download_dir:
            download_dir = f"{AGENT_OPT_ROOT}/logstash-versions"
        return {
            "policy_type": Policy.PolicyType.SIMULATE,
            "instance_id": instance_id,
            "deployment_id": paths["deployment_id"],
            "settings_path": paths["settings_path"],
            "config_path": paths["config_path"],
            "logs_path": paths["logs_path"],
            "data_path": paths["data_path"],
            "binary_path": normalize_agent_opt_path(policy.binary_path) or policy.binary_path,
            "agent_api_port": agent_port,
            "logstash_api_port": ls_port,
            "keystore_env_file": paths["keystore_env_file"],
            "logstash_source": policy.logstash_source,
            "logstash_version": policy.logstash_version or "",
            "logstash_download_dir": download_dir,
            "logstash_unit": f"ls-simulate@{instance_id}",
            "agent_unit": f"lsagent-simulate@{instance_id}",
            "logstash_yml": yml,
            "jvm_options": policy.jvm_options,
            "log4j2_properties": policy.log4j2_properties,
        }

    if ptype == Policy.PolicyType.MANAGED:
        if not instance_id:
            raise ValueError("instance_id required for MANAGED policy_config")
        paths = managed_paths(instance_id)
        agent_port, ls_port = managed_ports(instance_id, policy)
        yml = materialize_simulate_logstash_yml(
            policy.logstash_yml, ls_port, instance_id=instance_id
        )
        download_dir = normalize_agent_opt_path(
            policy.logstash_download_dir or f"{AGENT_OPT_ROOT}/logstash-versions"
        )
        return {
            "policy_type": Policy.PolicyType.MANAGED,
            "instance_id": instance_id,
            "deployment_id": paths["deployment_id"],
            "settings_path": paths["settings_path"],
            "config_path": paths["config_path"],
            "logs_path": paths["logs_path"],
            "data_path": paths["data_path"],
            "binary_path": policy.binary_path or "/usr/share/logstash/bin",
            "agent_api_port": agent_port,
            "logstash_api_port": ls_port,
            "keystore_env_file": paths["keystore_env_file"],
            "logstash_source": policy.logstash_source,
            "logstash_version": policy.logstash_version or "",
            "logstash_download_dir": download_dir or f"{AGENT_OPT_ROOT}/logstash-versions",
            "logstash_unit": f"logstash-managed@{instance_id}",
            "agent_unit": f"logstash-agent@{instance_id}",
            "path_root": paths["path_root"],
            "logstash_yml": yml,
            "jvm_options": policy.jvm_options,
            "log4j2_properties": policy.log4j2_properties,
        }

    # PACKAGED (and legacy DEFAULT)
    return {
        "policy_type": Policy.PolicyType.PACKAGED,
        "deployment_id": "package",
        "settings_path": policy.settings_path,
        "logs_path": policy.logs_path,
        "binary_path": policy.binary_path,
        "data_path": policy.data_path or "",
        "agent_api_port": policy.agent_api_port or PACKAGED_AGENT_API_PORT,
        "logstash_api_port": policy.logstash_api_port or PACKAGED_LOGSTASH_API_PORT,
        "keystore_env_file": policy.keystore_env_file or "/etc/default/logstash",
        "logstash_source": policy.logstash_source or "SYSTEM",
        "logstash_version": policy.logstash_version or "",
        "logstash_download_dir": normalize_agent_opt_path(policy.logstash_download_dir or ""),
        "logstash_unit": "logstash",
        "agent_unit": "logstash-agent",
        "logstash_yml": policy.logstash_yml,
        "jvm_options": policy.jvm_options,
        "log4j2_properties": policy.log4j2_properties,
    }


def embedded_agent_base_url() -> str:
    """URL the UI uses to reach the docker/local embedded agent FastAPI."""
    try:
        from django.conf import settings

        return (getattr(settings, "LOGSTASH_AGENT_URL", None) or "https://127.0.0.1:9500").rstrip(
            "/"
        )
    except Exception:
        return "https://127.0.0.1:9500"


def probe_embedded_agent_online(timeout: float = 2.0) -> bool:
    """
    Live probe of the embedded agent (no enrollment/check-in).

    Embedded agents never POST CheckIn, so Connection.last_check_in stays empty
    unless we touch it after a successful probe.
    """
    import logging

    logger = logging.getLogger(__name__)
    url = embedded_agent_base_url()
    try:
        import requests
        from Common.product_ca import agent_requests_verify

        resp = requests.get(url + "/", timeout=timeout, verify=agent_requests_verify())
        if resp.status_code < 400:
            return True
        logger.debug("Embedded agent probe %s -> %s", url, resp.status_code)
        return False
    except Exception as exc:
        logger.debug("Embedded agent probe failed (%s): %s", url, exc)
        return False


def ensure_embedded_connection(*, probe: bool = True) -> Connection | None:
    """
    Ensure a pseudo Connection exists for the system Embedded Policy so the
    editor picker can list docker/local embedded agent without enrollment.

    Host/port derived from settings.LOGSTASH_AGENT_URL when possible.

    When probe=True (default), performs a live HTTP probe and updates
    last_check_in/status_blob so Connection Manager and is_embedded_discovered
    reflect current online state. Page-render paths that only need the sticky
    row to exist should pass probe=False; the background thread started by
    refresh_embedded_connection_async keeps the DB warm.
    """
    try:
        from datetime import datetime, timezone
        from urllib.parse import urlparse
    except Exception:
        return None

    try:
        policy = Policy.objects.filter(
            policy_type=Policy.PolicyType.EMBEDDED, is_system=True
        ).first()
        if not policy:
            policy = Policy.objects.filter(name="Embedded Policy").first()
        if not policy:
            return None

        agent_url = embedded_agent_base_url()
        parsed = urlparse(agent_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or EMBEDDED_AGENT_API_PORT
        online = probe_embedded_agent_online() if probe else False
        now = datetime.now(timezone.utc)

        conn = Connection.objects.filter(
            policy=policy,
            connection_type=Connection.ConnectionType.AGENT,
            agent_id="embedded-local",
        ).first()
        update_fields = {
            "name": "embedded",
            "host": host,
            "agent_api_port": port,
            "logstash_api_port": EMBEDDED_LOGSTASH_API_PORT,
            "is_active": True,
            "policy": policy,
        }
        if online:
            # Synthetic check-in so list/SSE treat embedded like a live agent
            update_fields["last_check_in"] = now
            update_fields["status_blob"] = {
                "embedded": True,
                "mode": "embedded",
                "agent_url": agent_url,
                "probed_at": now.isoformat(),
                "online": True,
            }
        elif probe:
            # Probe ran but failed — mark offline so the Sim picker can hide
            # undiscovered embedded. Don't wipe last_check_in on transient fail.
            update_fields["status_blob"] = {
                "embedded": True,
                "mode": "embedded",
                "agent_url": agent_url,
                "probed_at": now.isoformat(),
                "online": False,
            }
        # else probe=False: don't touch status_blob or last_check_in at all;
        # leave whatever the last async probe wrote.

        if conn:
            Connection.objects.filter(pk=conn.pk).update(**update_fields)
            conn.refresh_from_db()
            return conn

        conn = Connection(
            name="embedded",
            connection_type=Connection.ConnectionType.AGENT,
            host=host,
            agent_id="embedded-local",
            is_active=True,
            policy=policy,
            agent_api_port=port,
            logstash_api_port=EMBEDDED_LOGSTASH_API_PORT,
            last_check_in=now if online else None,
            status_blob=update_fields.get("status_blob") or {"embedded": True, "online": online},
        )
        conn.save()
        return conn
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Could not ensure embedded simulation connection: %s", exc
        )
        return None


def refresh_embedded_connection_async() -> None:
    """Probe the embedded agent and update last_check_in without blocking the caller."""
    try:
        import threading

        threading.Thread(target=ensure_embedded_connection, daemon=True).start()
    except Exception:
        pass


def is_embedded_discovered(conn) -> bool:
    """True when the docker/local embedded agent has been successfully probed."""
    if conn is None:
        return False
    if isinstance(conn, dict):
        blob = conn.get("status_blob") or {}
        last_check_in = conn.get("last_check_in")
    else:
        blob = getattr(conn, "status_blob", None) or {}
        last_check_in = getattr(conn, "last_check_in", None)
    if blob.get("online") is True:
        return True
    if not last_check_in:
        return False
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    ts = last_check_in
    if getattr(ts, "tzinfo", None) is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() < 600


def is_embedded_connection(conn) -> bool:
    """True for the docker/local pseudo agent (dict or model)."""
    if conn is None:
        return False
    if isinstance(conn, dict):
        if conn.get("agent_id") == "embedded-local":
            return True
        pt = conn.get("policy__policy_type") or conn.get("policy_type")
        return pt == Policy.PolicyType.EMBEDDED or pt == "EMBEDDED"
    if getattr(conn, "agent_id", None) == "embedded-local":
        return True
    policy = getattr(conn, "policy", None)
    if policy is not None and getattr(policy, "policy_type", None) == Policy.PolicyType.EMBEDDED:
        return True
    return False


def list_simulation_targets(active_only: bool = True, *, ensure_embedded: bool = True):
    """
    Return list of dicts describing simulate-capable connections for the editor.
    """
    if ensure_embedded:
        ensure_embedded_connection(probe=False)

    qs = Connection.objects.filter(
        connection_type=Connection.ConnectionType.AGENT,
        policy__policy_type__in=[
            Policy.PolicyType.SIMULATE,
            Policy.PolicyType.EMBEDDED,
        ],
    ).select_related("policy")
    if active_only:
        qs = qs.filter(is_active=True)

    simulate_targets = []
    embedded_targets = []
    for conn in qs.order_by("instance_id", "name"):
        policy = conn.policy
        if not policy:
            continue
        version = (
            conn.logstash_version_resolved
            or (policy.logstash_version if policy.logstash_source == Policy.LogstashSource.VERSION else "")
            or ("system" if policy.policy_type == Policy.PolicyType.SIMULATE else "")
        )
        if policy.policy_type == Policy.PolicyType.EMBEDDED:
            # Picker only — and only after a successful live probe
            if not is_embedded_discovered(conn):
                continue
            # Closed select: terse; detail on hover / open option list
            label = "embedded"
            ver_label = version or "docker"
            agent_port = conn.agent_api_port or EMBEDDED_AGENT_API_PORT
            # Prefer settings URL (https://logstashagent:9500) for embedded
            try:
                from django.conf import settings

                base_url = getattr(settings, "LOGSTASH_AGENT_URL", None)
            except Exception:
                base_url = None
            if not base_url:
                host = conn.host or "127.0.0.1"
                base_url = f"https://{host}:{agent_port}"
            host = conn.host or "127.0.0.1"
            detail = f"embedded · {host} · Logstash {ver_label}"
        else:
            n = conn.instance_id or "?"
            ver_label = version or "system"
            host = conn.host or "127.0.0.1"
            label = f"simulate-{n}"
            detail = f"simulate-{n} · {host} · Logstash {ver_label}"
            agent_port = conn.agent_api_port
            if agent_port is None and conn.instance_id:
                agent_port = SIMULATE_AGENT_API_BASE + conn.instance_id
            base_url = f"https://{host}:{agent_port}" if agent_port else None

        row = {
            "connection_id": conn.id,
            "name": conn.name,
            "label": label,
            "detail": detail,
            "policy_type": policy.policy_type,
            "policy_name": policy.name,
            "instance_id": conn.instance_id,
            "agent_api_port": agent_port,
            "logstash_api_port": conn.logstash_api_port,
            "logstash_version": version or None,
            "logstash_source": policy.logstash_source,
            "host": host,
            "base_url": base_url,
            "last_selected_at": conn.last_selected_at.isoformat()
            if conn.last_selected_at
            else None,
        }
        if policy.policy_type == Policy.PolicyType.EMBEDDED:
            embedded_targets.append(row)
        else:
            simulate_targets.append(row)
    # Dedicated simulate-N first; embedded last when discovered
    return simulate_targets + embedded_targets


def resolve_simulation_target(connection_id=None, session=None):
    """
    Pick a simulation target connection.

    - Explicit connection_id wins
    - Single target auto-selected
    - Multiple: session sticky id, else first
    Returns (target_dict | None, error_message | None)
    """
    targets = list_simulation_targets()
    if not targets:
        return None, "No simulation agents available. Enroll a simulate agent or start embedded mode."

    if connection_id is not None:
        for t in targets:
            if t["connection_id"] == int(connection_id):
                return t, None
        return None, f"Simulation agent connection_id={connection_id} not found or inactive"

    if len(targets) == 1:
        return targets[0], None

    sticky = None
    if session is not None:
        sticky = session.get("sim_connection_id")
    if sticky is not None:
        for t in targets:
            if t["connection_id"] == int(sticky):
                return t, None

    return targets[0], None
