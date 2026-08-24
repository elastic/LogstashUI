#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Database settings helper.

SQLite is the only implemented engine. PostgreSQL and MySQL are anticipated
via ``LOGSTASHUI_DB_ENGINE`` but not wired in this release.
"""

from __future__ import annotations

import os
from pathlib import Path


def build_databases(data_dir: Path) -> dict:
    engine = (os.environ.get("LOGSTASHUI_DB_ENGINE") or "sqlite").strip().lower()
    if engine in ("", "sqlite", "sqlite3"):
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": Path(data_dir) / "db.sqlite3",
            }
        }
    raise RuntimeError(
        f"LOGSTASHUI_DB_ENGINE={engine!r} is not implemented. "
        "Supported: sqlite. PostgreSQL and MySQL are planned; keep a PVC on "
        "LOGSTASHUI_DATA_DIR even after those engines land (TLS and secrets)."
    )
