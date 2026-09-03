#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from PipelineManager.agent_versions import (
    SYSTEM_BINARY_PATH,
    agent_version_relation,
    derive_version_binary_path,
    is_derived_version_binary_path,
    resolve_persisted_binary_path,
    resolve_running_logstash_version,
)


class TestDeriveVersionBinaryPath:
    def test_default_dir(self):
        assert derive_version_binary_path(None, "9.4.3") == (
            "/opt/logstash-agent/logstash-versions/logstash-9.4.3/bin"
        )

    def test_custom_dir_strips_slash(self):
        assert derive_version_binary_path("/opt/ls/vers/", "8.17.1") == (
            "/opt/ls/vers/logstash-8.17.1/bin"
        )

    def test_empty_version_returns_none(self):
        assert derive_version_binary_path("/opt/ls", "") is None
        assert derive_version_binary_path("/opt/ls", None) is None
        assert derive_version_binary_path("/opt/ls", "  ") is None

    def test_is_derived_true(self):
        path = derive_version_binary_path(None, "9.4.3")
        assert is_derived_version_binary_path(path, None) is True
        assert is_derived_version_binary_path(path + "/", None) is True

    def test_is_derived_false_for_system(self):
        assert is_derived_version_binary_path(SYSTEM_BINARY_PATH, None) is False
        assert is_derived_version_binary_path("/opt/custom/bin", None) is False


class TestResolveRunningLogstashVersion:
    def test_prefers_column(self):
        assert resolve_running_logstash_version(
            logstash_version_resolved="9.4.3",
            status_blob={"logstash_api": {"version": "8.0.0"}},
        ) == "9.4.3"

    def test_falls_back_to_api_version(self):
        assert resolve_running_logstash_version(
            logstash_version_resolved="",
            status_blob={"logstash_api": {"version": "9.1.0"}},
        ) == "9.1.0"

    def test_falls_back_to_blob_keys(self):
        assert resolve_running_logstash_version(
            status_blob={"logstash_version": "8.15.0"}
        ) == "8.15.0"

    def test_missing_returns_none(self):
        assert resolve_running_logstash_version() is None
        assert resolve_running_logstash_version(status_blob={}) is None


class TestAgentVersionRelation:
    def test_older_equal_newer(self):
        assert agent_version_relation("0.5.0", "0.5.1") == "older"
        assert agent_version_relation("0.5.1", "0.5.1") == "equal"
        assert agent_version_relation("0.5.2", "0.5.1") == "newer"

    def test_prerelease_newer_than_preferred(self):
        assert agent_version_relation("0.5.2.dev0", "0.5.1") == "newer"

    def test_garbage_unknown(self):
        assert agent_version_relation("not-a-version", "0.5.1") == "unknown"
        assert agent_version_relation("", "0.5.1") == "unknown"
        assert agent_version_relation(None, "0.5.1") == "unknown"


class TestResolvePersistedBinaryPath:
    def test_version_autofills_system_default(self):
        assert resolve_persisted_binary_path(
            source="VERSION",
            version="9.4.3",
            download_dir="/opt/logstash-agent/logstash-versions",
            binary_path="/usr/share/logstash/bin",
        ) == "/opt/logstash-agent/logstash-versions/logstash-9.4.3/bin"

    def test_version_updates_previous_derived_path(self):
        old = "/opt/logstash-agent/logstash-versions/logstash-9.4.3/bin"
        assert resolve_persisted_binary_path(
            source="VERSION",
            version="9.5.0",
            download_dir="/opt/logstash-agent/logstash-versions",
            binary_path=old,
        ) == "/opt/logstash-agent/logstash-versions/logstash-9.5.0/bin"

    def test_version_keeps_custom_path(self):
        assert resolve_persisted_binary_path(
            source="VERSION",
            version="9.4.3",
            download_dir="/opt/logstash-agent/logstash-versions",
            binary_path="/opt/my/logstash/bin",
        ) == "/opt/my/logstash/bin"

    def test_version_empty_pin_does_not_rewrite(self):
        assert resolve_persisted_binary_path(
            source="VERSION",
            version="",
            download_dir="/opt/logstash-agent/logstash-versions",
            binary_path="/usr/share/logstash/bin",
        ) == "/usr/share/logstash/bin"

    def test_system_restores_when_path_was_derived(self):
        derived = "/opt/logstash-agent/logstash-versions/logstash-9.4.3/bin"
        assert resolve_persisted_binary_path(
            source="SYSTEM",
            version="9.4.3",
            download_dir="/opt/logstash-agent/logstash-versions",
            binary_path=derived,
        ) == SYSTEM_BINARY_PATH

    def test_system_keeps_custom_path(self):
        assert resolve_persisted_binary_path(
            source="SYSTEM",
            version="9.4.3",
            download_dir="/opt/logstash-agent/logstash-versions",
            binary_path="/opt/my/bin",
        ) == "/opt/my/bin"
