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
    def test_live_api_version_beats_stale_column(self):
        """The blob is this check-in; the column is history.

        Preferring the column froze the LS pill: the column is only written on
        a truthy value and never cleared, so the first version ever recorded
        shadowed every later one.
        """
        assert resolve_running_logstash_version(
            logstash_version_resolved="8.0.0",
            status_blob={"logstash_api": {"version": "9.4.3"}},
        ) == "9.4.3"

    def test_blob_resolved_beats_column(self):
        assert resolve_running_logstash_version(
            logstash_version_resolved="8.0.0",
            status_blob={"logstash_version_resolved": "9.4.3"},
        ) == "9.4.3"

    def test_api_version_beats_blob_resolved(self):
        assert resolve_running_logstash_version(
            status_blob={
                "logstash_api": {"version": "9.4.3"},
                "logstash_version_resolved": "9.1.0",
            }
        ) == "9.4.3"

    def test_column_used_when_blob_reports_no_version(self):
        """Logstash stopped or its API unreachable: keep the last known version."""
        assert resolve_running_logstash_version(
            logstash_version_resolved="9.4.3",
            status_blob={"logstash_api": {"accessible": False}},
        ) == "9.4.3"

    def test_column_used_when_blob_absent(self):
        assert resolve_running_logstash_version(
            logstash_version_resolved="9.4.3"
        ) == "9.4.3"

    def test_desired_version_is_last_resort(self):
        """`logstash_version` is the policy-desired version, not the running one."""
        assert resolve_running_logstash_version(
            status_blob={"logstash_version": "8.15.0"}
        ) == "8.15.0"
        assert resolve_running_logstash_version(
            logstash_version_resolved="9.4.3",
            status_blob={"logstash_version": "8.15.0"},
        ) == "9.4.3"

    def test_missing_returns_none(self):
        assert resolve_running_logstash_version() is None
        assert resolve_running_logstash_version(status_blob={}) is None


class TestAgentVersionRelation:
    def test_older_equal_newer(self):
        assert agent_version_relation("0.5.1", "0.5.2") == "older"
        assert agent_version_relation("0.5.2", "0.5.2") == "equal"
        assert agent_version_relation("0.5.3", "0.5.2") == "newer"

    def test_prerelease_newer_than_preferred(self):
        assert agent_version_relation("0.5.3.dev0", "0.5.2") == "newer"

    def test_garbage_unknown(self):
        assert agent_version_relation("not-a-version", "0.5.2") == "unknown"
        assert agent_version_relation("", "0.5.2") == "unknown"
        assert agent_version_relation(None, "0.5.2") == "unknown"


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
