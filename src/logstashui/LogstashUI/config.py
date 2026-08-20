#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import os
import logging

logger = logging.getLogger(__name__)

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")


def env_bool(name: str, default: bool = False) -> bool:
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
