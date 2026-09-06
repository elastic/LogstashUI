#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Resolve Python logging levels from environment variables."""

from __future__ import annotations

import logging.handlers
import os
import sys

_ALLOWED = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class WindowsSafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler that handles Windows file-locking during rotation gracefully.

    On Windows, os.rename() raises PermissionError (WinError 32) when another
    thread still holds the log file open at the moment rotation is triggered.
    Python's logging machinery re-raises this from emit(), producing a flood of
    '--- Logging error ---' lines that can crash a running instance.

    This subclass overrides rotate() to catch PermissionError and skip the
    current rotation cycle instead of propagating the error. The file continues
    to be written to, and the next emit() that triggers shouldRollover() will
    attempt rotation again.
    """

    def rotate(self, source: str, dest: str) -> None:
        try:
            super().rotate(source, dest)
        except PermissionError:
            # Another thread holds the file open; skip this rotation cycle.
            # The next shouldRollover check will retry.
            pass


# Resolved at import time so settings.py can reference it as a dotted class
# path string. On Windows we use the safe subclass above; on POSIX platforms
# os.rename() is atomic on open files so the stock handler is fine.
ROTATING_FILE_HANDLER_CLASS = (
    "LogstashUI.logging_config.WindowsSafeRotatingFileHandler"
    if sys.platform == "win32"
    else "logging.handlers.RotatingFileHandler"
)


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
