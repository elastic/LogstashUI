#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from pathlib import Path

import pytest

from LogstashUI.database import build_databases


def test_build_databases_sqlite_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGSTASHUI_DB_ENGINE", raising=False)
    db = build_databases(tmp_path)
    assert db["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert db["default"]["NAME"] == tmp_path / "db.sqlite3"


def test_build_databases_rejects_unimplemented_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGSTASHUI_DB_ENGINE", "postgresql")
    with pytest.raises(RuntimeError, match="not implemented"):
        build_databases(tmp_path)
    monkeypatch.setenv("LOGSTASHUI_DB_ENGINE", "mysql")
    with pytest.raises(RuntimeError, match="not implemented"):
        build_databases(Path(tmp_path))
