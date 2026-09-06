#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Resolve runtime data / logs directories (no Django import).

Precedence: LOGSTASHUI_DATA_DIR / LOGSTASHUI_LOGS_DIR / LOGSTASHUI_LOGSTASH_DIR
→ default.

Default data root is ``$(pwd)/logstashui_data``. Pytest keeps using
``<BASE_DIR>/data`` so test runs do not touch a checkout bind-mount.
Docker/systemd always set LOGSTASHUI_DATA_DIR=/var/lib/logstashui.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

# src/logstashui/LogstashUI/paths.py → src/logstashui → src → project root
_PACKAGE_DIR = Path(__file__).resolve().parent
BASE_DIR = _PACKAGE_DIR.parent
PROJECT_ROOT = BASE_DIR.parent.parent
LEGACY_DATA_DIR = BASE_DIR / "data"


def project_root() -> Path:
    return PROJECT_ROOT


def legacy_data_dir() -> Path:
    return LEGACY_DATA_DIR


def _is_pytest() -> bool:
    return bool(os.environ.get("PYTEST_VERSION")) or "pytest" in sys.modules


def _default_data_dir() -> Path:
    if _is_pytest():
        return LEGACY_DATA_DIR
    return Path.cwd() / "logstashui_data"


def _coerce_path(raw: Optional[str], *, relative_to: Path) -> Optional[Path]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    p = Path(text).expanduser()
    if not p.is_absolute():
        p = (relative_to / p).resolve()
    return p


def resolve_data_dir(*, migrate_legacy: bool = True) -> Path:
    """Return the runtime data root (sqlite, tls, secrets, default logs)."""
    env = os.environ.get("LOGSTASHUI_DATA_DIR")
    chosen = _coerce_path(env, relative_to=Path.cwd())
    if chosen is None:
        chosen = _default_data_dir()

    if migrate_legacy and not _is_pytest():
        maybe_migrate_legacy_data(chosen)

    return chosen


def resolve_logs_dir(data_dir: Optional[Path] = None) -> Path:
    env = os.environ.get("LOGSTASHUI_LOGS_DIR")
    chosen = _coerce_path(env, relative_to=Path.cwd())
    if chosen is None:
        root = data_dir if data_dir is not None else resolve_data_dir()
        chosen = root / "logs"
    return chosen


def resolve_logstash_dir(data_dir: Optional[Path] = None) -> Path:
    """Cache root for proxied Logstash release tarballs.

    Deliberately a sibling of ``staticfiles``, never a child: STATIC_ROOT is
    served by WhiteNoise at ``/static/``, which is in LOGIN_REQUIRED_IGNORE_PATHS,
    so anything under it is an unauthenticated public download. ``collectstatic``
    also runs on every ``serve`` and would churn over half-gigabyte files.
    """
    env = os.environ.get("LOGSTASHUI_LOGSTASH_DIR")
    chosen = _coerce_path(env, relative_to=Path.cwd())
    if chosen is None:
        root = data_dir if data_dir is not None else resolve_data_dir()
        chosen = root / "logstashes"
    return chosen


def maybe_migrate_legacy_data(dest: Path) -> None:
    """Copy src/logstashui/data → dest when dest has no sqlite and legacy does."""
    try:
        dest = dest.resolve()
        legacy = LEGACY_DATA_DIR.resolve()
    except Exception:
        return
    if dest == legacy:
        return
    dest_db = dest / "db.sqlite3"
    legacy_db = legacy / "db.sqlite3"
    if dest_db.exists() or not legacy_db.exists():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in legacy.iterdir():
        target = dest / item.name
        if target.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def resolve_docs_dir() -> Path:
    """Markdown docs root (contains ``docs/`` and optionally ``CHANGELOG.md``)."""
    env = os.environ.get("LOGSTASHUI_DOCS_DIR")
    chosen = _coerce_path(env, relative_to=Path.cwd())
    if chosen is not None:
        return chosen
    checkout = PROJECT_ROOT / "docs"
    if (checkout / "docs").is_dir():
        return checkout
    packaged = BASE_DIR / "Documentation" / "content"
    return packaged


def resolve_changelog_path() -> Path:
    env = os.environ.get("LOGSTASHUI_CHANGELOG")
    chosen = _coerce_path(env, relative_to=Path.cwd())
    if chosen is not None:
        return chosen
    checkout = PROJECT_ROOT / "CHANGELOG.md"
    if checkout.is_file():
        return checkout
    return resolve_docs_dir() / "CHANGELOG.md"

