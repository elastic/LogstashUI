#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""``LOGSTASHUI_INSECURE_HTTP`` helpers.

Env-only — safe before ``django.setup()``. When enabled, UI and agent
connections are plain HTTP; product CA and UI certificates are not generated;
``LOGSTASHUI_TLS`` is overridden.
"""

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
    """Return whether ``LOGSTASHUI_INSECURE_HTTP`` is enabled.

    Examples:
        os.environ["LOGSTASHUI_INSECURE_HTTP"] = "true"
        insecure_http()
    """
    return env_bool("LOGSTASHUI_INSECURE_HTTP", False)


def force_http_url(url: str | None, enabled: bool | None = None) -> str | None:
    """Rewrite an ``https://`` URL to ``http://`` when insecure HTTP is on.

    Other schemes and empty values are left unchanged.

    Args:
        url: Absolute URL or None.
        enabled: Override; ``insecure_http()`` when omitted.

    Returns:
        Rewritten URL, the original value, or None.

    Examples:
        force_http_url("https://ui.example:8443", enabled=True)
    """
    if enabled is None:
        enabled = insecure_http()
    if not enabled or not url:
        return url
    if url[:8].lower() == "https://":
        return "http://" + url[8:]
    return url


def tls_enabled(tls_env: str | None = None, insecure: bool | None = None) -> bool:
    """Return whether the UI should terminate TLS.

    Insecure HTTP always wins (returns False). Otherwise ``LOGSTASHUI_TLS``
    is true unless it is ``0`` / ``false`` / ``no`` / ``off``.

    Args:
        tls_env: Raw ``LOGSTASHUI_TLS`` value; env is read when omitted.
        insecure: Override for ``insecure_http()``.
    """
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
    """Rewrite ``https://`` entries in a CSRF/origin list to ``http://``.

    Args:
        origins: Origin URLs.
        enabled: Passed to ``force_http_url``; ``insecure_http()`` when omitted.

    Returns:
        New list with the same length as ``origins``.
    """
    return [force_http_url(o, enabled=enabled) or o for o in origins]


def secure_cookies(*, debug: bool, insecure: bool) -> bool:
    """Return whether session/CSRF cookies should be marked Secure.

    True only when not in DEBUG and not in insecure HTTP.

    Args:
        debug: Django DEBUG.
        insecure: ``LOGSTASHUI_INSECURE_HTTP`` (or equivalent).
    """
    return (not debug) and (not insecure)


def warn_if_enabled(log: logging.Logger | None = None) -> None:
    """Log ``INSECURE_HTTP_WARNING`` when insecure HTTP is enabled.

    Args:
        log: Logger to use; this module's logger when omitted.
    """
    if insecure_http():
        (log or logger).warning(INSECURE_HTTP_WARNING)
