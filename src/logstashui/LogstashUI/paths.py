#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Resolve runtime data / logs directories (no Django import).

Precedence: LOGSTASHUI_DATA_DIR / LOGSTASHUI_LOGS_DIR → logstashui.yml
``paths.data`` / ``paths.logs`` → default.

Default data root is ``<project_root>/logstashui_data`` (outside src/).
Pytest keeps using ``<BASE_DIR>/data`` so test runs do not touch a checkout
bind-mount. Docker always sets LOGSTASHUI_DATA_DIR=/var/lib/logstashui.
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
    return PROJECT_ROOT / "logstashui_data"


def _yaml_paths() -> dict:
    try:
        from .config import CONFIG
    except Exception:
        return {}
    paths = (CONFIG or {}).get("paths") or {}
    return paths if isinstance(paths, dict) else {}


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
        chosen = _coerce_path(_yaml_paths().get("data"), relative_to=PROJECT_ROOT)
    if chosen is None:
        chosen = _default_data_dir()

    if migrate_legacy and not _is_pytest():
        maybe_migrate_legacy_data(chosen)

    return chosen


def resolve_logs_dir(data_dir: Optional[Path] = None) -> Path:
    env = os.environ.get("LOGSTASHUI_LOGS_DIR")
    chosen = _coerce_path(env, relative_to=Path.cwd())
    if chosen is None:
        chosen = _coerce_path(_yaml_paths().get("logs"), relative_to=PROJECT_ROOT)
    if chosen is None:
        root = data_dir if data_dir is not None else resolve_data_dir()
        chosen = root / "logs"
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
