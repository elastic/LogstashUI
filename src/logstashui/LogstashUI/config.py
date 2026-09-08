#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Environment-backed runtime configuration (no YAML)."""

import os
import logging

logger = logging.getLogger(__name__)

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")


def _split_csv_hosts(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def merge_allowed_hosts(
    allowed: str | None = None,
    host_ips: str | None = None,
    pod_ip: str | None = None,
) -> list[str]:
    """Build Django ALLOWED_HOSTS, plus pod/host IPs used as kube-probe Host headers.

    ``ALLOWED_HOSTS=*`` stays a single wildcard. Otherwise ``LOGSTASHUI_HOST_IPS``
    and ``POD_IP`` are appended (Kubernetes Downward API / compose host IPs).

    Args:
        allowed: Comma-separated hosts; env ``ALLOWED_HOSTS`` when omitted.
        host_ips: Extra IPs; env ``LOGSTASHUI_HOST_IPS`` when omitted.
        pod_ip: Pod IP; env ``POD_IP`` when omitted.

    Returns:
        Host list. ``["*"]`` if allowed is empty or a lone wildcard.
    """
    if allowed is None:
        allowed = os.environ.get("ALLOWED_HOSTS", "*")
    hosts = _split_csv_hosts(allowed)
    if not hosts:
        hosts = ["*"]
    if hosts == ["*"]:
        return hosts
    extras = _split_csv_hosts(
        host_ips if host_ips is not None else os.environ.get("LOGSTASHUI_HOST_IPS", "")
    )
    extra_pod = pod_ip if pod_ip is not None else os.environ.get("POD_IP", "")
    extras.extend(_split_csv_hosts(extra_pod))
    for host in extras:
        if host not in hosts:
            hosts.append(host)
    return hosts


def env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable.

    True: ``1``, ``true``, ``yes``, ``on``. False: ``0``, ``false``, ``no``,
    ``off``. Unset, blank-after-strip, or any other value yields ``default``.

    Args:
        name: Environment variable to read.
        default: Value when unset or unrecognized.

    Examples:
        os.environ["LOGSTASHUI_NO_AUTH"] = "true"
        env_bool("LOGSTASHUI_NO_AUTH", False)
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    text = raw.strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


def load_config() -> dict:
    """Load runtime knobs from environment variables.

    YAML (``LOGSTASHUI_CONFIG`` / ``logstashui.yml``) is not read. Use env,
    systemd ``EnvironmentFile``, or a Kubernetes ConfigMap.

    Returns:
        Dict with ``no_auth``, ``agent`` (ui_url, include_ca_fingerprint), and
        ``paths`` placeholders (data/logs filled later from ``paths``).
    """
    ui_url = (os.environ.get("LOGSTASHUI_AGENT_UI_URL") or "").strip().rstrip("/")
    config = {
        "no_auth": {
            "enabled": env_bool("LOGSTASHUI_NO_AUTH", False),
        },
        "agent": {
            "ui_url": ui_url,
            "include_ca_fingerprint": env_bool(
                "LOGSTASHUI_INCLUDE_CA_FINGERPRINT", True
            ),
        },
        "paths": {
            "data": None,
            "logs": None,
        },
    }
    logger.info(
        "Loaded configuration from environment "
        "(LOGSTASHUI_NO_AUTH=%s, LOGSTASHUI_AGENT_UI_URL=%s)",
        config["no_auth"]["enabled"],
        ui_url or "(unset)",
    )
    return config


CONFIG = load_config()
