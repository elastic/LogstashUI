#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Logstash / agent version display and VERSION binary-path helpers."""

from __future__ import annotations

from packaging.version import InvalidVersion, Version

SYSTEM_BINARY_PATH = "/usr/share/logstash/bin"
DEFAULT_DOWNLOAD_DIR = "/opt/logstash-agent/logstash-versions"


def derive_version_binary_path(download_dir: str | None, version: str | None) -> str | None:
    ver = (version or "").strip()
    if not ver:
        return None
    root = (download_dir or DEFAULT_DOWNLOAD_DIR).rstrip("/") or DEFAULT_DOWNLOAD_DIR
    return f"{root}/logstash-{ver}/bin"


def is_derived_version_binary_path(path: str | None, download_dir: str | None) -> bool:
    p = (path or "").rstrip("/")
    if not p:
        return False
    root = (download_dir or DEFAULT_DOWNLOAD_DIR).rstrip("/") or DEFAULT_DOWNLOAD_DIR
    prefix = f"{root}/logstash-"
    suffix = "/bin"
    if not (p.startswith(prefix) and p.endswith(suffix)):
        return False
    mid = p[len(prefix) : -len(suffix)]
    return bool(mid) and "/" not in mid


def resolve_running_logstash_version(
    *,
    logstash_version_resolved: str | None = None,
    status_blob: dict | None = None,
) -> str | None:
    """Best available answer to "which Logstash is running on that host?".

    The status blob is the current check-in and the column is history, so the
    blob leads. Preferring the column stranded the display: it is only ever
    written on a truthy value and never cleared, so one recorded version
    shadowed every later one and the pill froze for the life of the row.

    The column still backs the blob up, which is what keeps the last known
    version on screen while Logstash is stopped or its API is unreachable.
    ``logstash_version`` is last because elsewhere it means the policy-*desired*
    version rather than the running one.
    """
    blob = status_blob if isinstance(status_blob, dict) else {}
    api = blob.get("logstash_api")
    if isinstance(api, dict):
        ver = str(api.get("version") or "").strip()
        if ver:
            return ver
    ver = str(blob.get("logstash_version_resolved") or "").strip()
    if ver:
        return ver
    resolved = (logstash_version_resolved or "").strip()
    if resolved:
        return resolved
    ver = str(blob.get("logstash_version") or "").strip()
    if ver:
        return ver
    return None


def agent_version_relation(current: str | None, preferred: str | None) -> str:
    try:
        cur = Version(str(current or "").strip())
        pref = Version(str(preferred or "").strip())
    except InvalidVersion:
        return "unknown"
    if cur < pref:
        return "older"
    if cur > pref:
        return "newer"
    return "equal"


def resolve_persisted_binary_path(
    *,
    source: str | None,
    version: str | None,
    download_dir: str | None,
    binary_path: str | None,
) -> str:
    current = (binary_path or "").strip() or SYSTEM_BINARY_PATH
    src = (source or "SYSTEM").upper()
    derived = derive_version_binary_path(download_dir, version)
    if src == "VERSION":
        if derived and (
            not (binary_path or "").strip()
            or current.rstrip("/") == SYSTEM_BINARY_PATH.rstrip("/")
            or is_derived_version_binary_path(current, download_dir)
        ):
            return derived
        return current
    if is_derived_version_binary_path(current, download_dir):
        return SYSTEM_BINARY_PATH
    return current
