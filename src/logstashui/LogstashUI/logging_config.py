#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Resolve Python logging levels from environment variables."""

from __future__ import annotations

import os

_ALLOWED = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def resolve_log_level(name: str, *, default: str = "INFO") -> str:
    raw = (os.environ.get(name) or "").strip().upper()
    if not raw:
        return default
    if raw == "WARN":
        raw = "WARNING"
    if raw not in _ALLOWED:
        raise RuntimeError(
            f"{name}={raw!r} is invalid. Allowed: {', '.join(_ALLOWED)} (WARN is accepted as WARNING)."
        )
    return raw


def resolve_django_log_levels() -> tuple[str, str]:
    """Return (django logger level, django.request level).

    Unset: django=INFO, django.request=ERROR.
    When LOGSTASHUI_DJANGO_LOG_LEVEL or DJANGO_LOG_LEVEL is set, both loggers
    use that value (prefixed env wins).
    """
    if (os.environ.get("LOGSTASHUI_DJANGO_LOG_LEVEL") or "").strip():
        level = resolve_log_level("LOGSTASHUI_DJANGO_LOG_LEVEL", default="INFO")
        return level, level
    if (os.environ.get("DJANGO_LOG_LEVEL") or "").strip():
        level = resolve_log_level("DJANGO_LOG_LEVEL", default="INFO")
        return level, level
    return "INFO", "ERROR"
