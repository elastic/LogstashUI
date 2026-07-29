#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Helpers for default / simulate / embedded agent roles."""

from __future__ import annotations

from django.db.models import Max

from PipelineManager.models import Connection, Policy

# Port scheme (plan): embedded fixed; simulate-N = base + N
EMBEDDED_AGENT_API_PORT = 9500
EMBEDDED_LOGSTASH_API_PORT = 9560
SIMULATE_AGENT_API_BASE = 9500
SIMULATE_LOGSTASH_API_BASE = 9560
SIMULATE_ROOT = "/opt/LogstashAgent"


def next_simulate_instance_id() -> int:
    """Allocate next free global simulate instance id (1-based)."""
    used = set(
        Connection.objects.filter(
            connection_type=Connection.ConnectionType.AGENT,
            instance_id__isnull=False,
        ).values_list("instance_id", flat=True)
    )
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
    }


def simulate_ports(instance_id: int) -> tuple[int, int]:
    return (
        SIMULATE_AGENT_API_BASE + instance_id,
        SIMULATE_LOGSTASH_API_BASE + instance_id,
    )


def materialize_simulate_logstash_yml(template: str, logstash_api_port: int) -> str:
    """Ensure api.http.port matches the instance port."""
    lines = []
    port_set = False
    for line in (template or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("api.http.port:") or stripped.startswith("http.port:"):
            lines.append(f"api.http.port: {logstash_api_port}")
            port_set = True
        else:
            lines.append(line)
    if not port_set:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"api.http.port: {logstash_api_port}")
    return "\n".join(lines) + ("\n" if lines else "")


def build_policy_config(policy: Policy, *, instance_id: int | None = None) -> dict:
    """
    Build enrollment / apply policy_config payload.

    For SIMULATE, instance_id is required and paths/ports are instance-specific.
    """
    if policy.policy_type == Policy.PolicyType.EMBEDDED:
        return {
            "policy_type": policy.policy_type,
            "settings_path": policy.settings_path,
            "logs_path": policy.logs_path,
            "binary_path": policy.binary_path,
            "data_path": policy.data_path or "",
            "agent_api_port": EMBEDDED_AGENT_API_PORT,
            "logstash_api_port": EMBEDDED_LOGSTASH_API_PORT,
            "keystore_env_file": policy.keystore_env_file or "",
            "logstash_source": policy.logstash_source,
            "logstash_version": policy.logstash_version or "",
            "logstash_download_dir": policy.logstash_download_dir or "",
            "logstash_yml": materialize_simulate_logstash_yml(
                policy.logstash_yml, EMBEDDED_LOGSTASH_API_PORT
            ),
            "jvm_options": policy.jvm_options,
            "log4j2_properties": policy.log4j2_properties,
        }

    if policy.policy_type == Policy.PolicyType.SIMULATE:
        if not instance_id:
            raise ValueError("instance_id required for SIMULATE policy_config")
        paths = simulate_paths(instance_id)
        agent_port, ls_port = simulate_ports(instance_id)
        yml = materialize_simulate_logstash_yml(policy.logstash_yml, ls_port)
        return {
            "policy_type": policy.policy_type,
            "instance_id": instance_id,
            "settings_path": paths["settings_path"],
            "config_path": paths["config_path"],
            "logs_path": paths["logs_path"],
            "data_path": paths["data_path"],
            "binary_path": policy.binary_path,
            "agent_api_port": agent_port,
            "logstash_api_port": ls_port,
            "keystore_env_file": paths["keystore_env_file"],
            "logstash_source": policy.logstash_source,
            "logstash_version": policy.logstash_version or "",
            "logstash_download_dir": policy.logstash_download_dir
            or f"{SIMULATE_ROOT}/logstash-versions",
            "logstash_unit": f"ls-simulate@{instance_id}",
            "agent_unit": f"lsagent-simulate@{instance_id}",
            "logstash_yml": yml,
            "jvm_options": policy.jvm_options,
            "log4j2_properties": policy.log4j2_properties,
        }

    # DEFAULT
    return {
        "policy_type": policy.policy_type,
        "settings_path": policy.settings_path,
        "logs_path": policy.logs_path,
        "binary_path": policy.binary_path,
        "data_path": policy.data_path or "",
        "agent_api_port": policy.agent_api_port,
        "logstash_api_port": policy.logstash_api_port,
        "keystore_env_file": policy.keystore_env_file or "/etc/default/logstash",
        "logstash_source": policy.logstash_source,
        "logstash_version": policy.logstash_version or "",
        "logstash_download_dir": policy.logstash_download_dir or "",
        "logstash_yml": policy.logstash_yml,
        "jvm_options": policy.jvm_options,
        "log4j2_properties": policy.log4j2_properties,
    }


def list_simulation_targets(active_only: bool = True):
    """
    Return list of dicts describing simulate-capable connections for the editor.
    """
    qs = Connection.objects.filter(
        connection_type=Connection.ConnectionType.AGENT,
        policy__policy_type__in=[
            Policy.PolicyType.SIMULATE,
            Policy.PolicyType.EMBEDDED,
        ],
    ).select_related("policy")
    if active_only:
        qs = qs.filter(is_active=True)

    targets = []
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
            label = f"embedded · {version or 'docker'}"
            agent_port = conn.agent_api_port or EMBEDDED_AGENT_API_PORT
        else:
            n = conn.instance_id or "?"
            ver_label = version or "system"
            label = f"simulate-{n} · Logstash {ver_label}"
            agent_port = conn.agent_api_port
            if agent_port is None and conn.instance_id:
                agent_port = SIMULATE_AGENT_API_BASE + conn.instance_id

        host = conn.host or "127.0.0.1"
        # Prefer http for agent FastAPI (matches current host mode)
        base_url = f"http://{host}:{agent_port}" if agent_port else None

        targets.append(
            {
                "connection_id": conn.id,
                "name": conn.name,
                "label": label,
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
        )
    return targets


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
