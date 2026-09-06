#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""LOGSTASHUI_INSECURE_HTTP helpers. Env-only — safe before django.setup()."""

from __future__ import annotations

import logging
import os

from LogstashUI.config import env_bool

logger = logging.getLogger(__name__)

INSECURE_HTTP_WARNING = (
    "LOGSTASHUI_INSECURE_HTTP=true: UI and agent connections are plain HTTP. "
    "Product CA and UI certificates will not be generated. "
    "Automatic TLS is the supported path. LOGSTASHUI_TLS is overridden."
)

_FALSE = ("0", "false", "no", "off")


def insecure_http() -> bool:
    return env_bool("LOGSTASHUI_INSECURE_HTTP", False)


def force_http_url(url: str | None, enabled: bool | None = None) -> str | None:
    if enabled is None:
        enabled = insecure_http()
    if not enabled or not url:
        return url
    if url[:8].lower() == "https://":
        return "http://" + url[8:]
    return url


def tls_enabled(tls_env: str | None = None, insecure: bool | None = None) -> bool:
    if insecure is None:
        insecure = insecure_http()
    if insecure:
        return False
    if tls_env is None:
        tls_env = os.environ.get("LOGSTASHUI_TLS", "true")
    return (tls_env or "true").strip().lower() not in _FALSE


def force_http_origins(
    origins: list[str], enabled: bool | None = None
) -> list[str]:
    return [force_http_url(o, enabled=enabled) or o for o in origins]


def secure_cookies(*, debug: bool, insecure: bool) -> bool:
    return (not debug) and (not insecure)


def warn_if_enabled(log: logging.Logger | None = None) -> None:
    if insecure_http():
        (log or logger).warning(INSECURE_HTTP_WARNING)
