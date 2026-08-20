#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from pathlib import Path

from LogstashUI.paths import (
    PROJECT_ROOT,
    maybe_migrate_legacy_data,
    resolve_data_dir,
    resolve_logs_dir,
)


def test_env_data_dir_wins(tmp_path, monkeypatch):
    dest = tmp_path / "from-env"
    dest.mkdir()
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", str(dest))
    monkeypatch.delenv("LOGSTASHUI_LOGS_DIR", raising=False)
    assert resolve_data_dir(migrate_legacy=False) == dest
    assert resolve_logs_dir(dest) == dest / "logs"


def test_env_logs_dir_wins(tmp_path, monkeypatch):
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    data.mkdir()
    logs.mkdir()
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", str(data))
    monkeypatch.setenv("LOGSTASHUI_LOGS_DIR", str(logs))
    assert resolve_logs_dir() == logs


def test_relative_env_path_is_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOGSTASHUI_DATA_DIR", "relative-data")
    resolved = resolve_data_dir(migrate_legacy=False)
    assert resolved.is_absolute()
    assert resolved == (tmp_path / "relative-data").resolve()


def test_migrate_legacy_copies_sqlite(tmp_path):
    legacy = tmp_path / "legacy"
    dest = tmp_path / "dest"
    legacy.mkdir()
    (legacy / "db.sqlite3").write_bytes(b"sqlite")
    (legacy / "tls").mkdir()
    (legacy / "tls" / "product-ca.crt").write_text("ca")
    # Point LEGACY_DATA_DIR by copying into maybe_migrate with patched constant
    from LogstashUI import paths as paths_mod

    original = paths_mod.LEGACY_DATA_DIR
    try:
        paths_mod.LEGACY_DATA_DIR = legacy
        maybe_migrate_legacy_data(dest)
        assert (dest / "db.sqlite3").read_bytes() == b"sqlite"
        assert (dest / "tls" / "product-ca.crt").read_text() == "ca"
        maybe_migrate_legacy_data(dest)  # idempotent
        assert (dest / "db.sqlite3").read_bytes() == b"sqlite"
    finally:
        paths_mod.LEGACY_DATA_DIR = original


def test_pytest_default_is_legacy_not_checkout_bind():
    # Under pytest, default must not be <repo>/logstashui_data
    resolved = resolve_data_dir(migrate_legacy=False)
    assert resolved != PROJECT_ROOT / "logstashui_data"
    assert resolved.name == "data"


def test_native_default_is_cwd_logstashui_data(tmp_path, monkeypatch):
    """Installed / CLI default is $(pwd)/logstashui_data, not site-packages."""
    from LogstashUI import paths as paths_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOGSTASHUI_DATA_DIR", raising=False)
    monkeypatch.setattr(paths_mod, "_is_pytest", lambda: False)
    resolved = paths_mod.resolve_data_dir(migrate_legacy=False)
    assert resolved == (tmp_path / "logstashui_data").resolve()
