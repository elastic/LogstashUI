#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for logstashagent.controller."""

import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from logstashagent import controller
from logstashagent.ls_keystore_utils.exceptions import (
    IncorrectPassword,
    LogstashKeystoreException,
    LogstashKeystoreModified,
)


class TestUpdateLogstashYml:
    def test_writes_file_and_returns_true(self, temp_dir):
        base = temp_dir.replace("\\", "/")
        if not base.endswith("/"):
            base = base + "/"
        content = "pipeline:\n  workers: 2\n"

        assert controller.update_logstash_yml(base, content) is True

        written = Path(base) / "logstash.yml"
        assert written.read_text(encoding="utf-8") == content

    def test_returns_false_on_error(self, temp_dir):
        base = temp_dir.replace("\\", "/") + "/"
        with patch("builtins.open", side_effect=OSError("denied")):
            assert controller.update_logstash_yml(base, "x") is False


class TestUpdateJvmOptions:
    def test_writes_file_and_returns_true(self, temp_dir):
        base = temp_dir.replace("\\", "/") + "/"
        content = "-Xmx1g\n"

        assert controller.update_jvm_options(base, content) is True

        assert (Path(base) / "jvm.options").read_text(encoding="utf-8") == content

    def test_returns_false_on_error(self, temp_dir):
        base = temp_dir.replace("\\", "/") + "/"
        with patch("builtins.open", side_effect=OSError("denied")):
            assert controller.update_jvm_options(base, "x") is False


class TestUpdateLog4j2Properties:
    def test_writes_file_and_returns_true(self, temp_dir):
        base = temp_dir.replace("\\", "/") + "/"
        content = "rootLogger.level = info\n"

        assert controller.update_log4j2_properties(base, content) is True

        assert (Path(base) / "log4j2.properties").read_text(encoding="utf-8") == content

    def test_returns_false_on_error(self, temp_dir):
        base = temp_dir.replace("\\", "/") + "/"
        with patch("builtins.open", side_effect=OSError("denied")):
            assert controller.update_log4j2_properties(base, "x") is False


class TestUpdateKeystore:
    def test_no_ops_returns_false(self):
        with patch.object(controller.agent_state, "get_state", return_value={}):
            assert controller.update_keystore("/cfg/", {"set": {}, "delete": []}) is False

    @patch.object(controller.LogstashKeystore, "load")
    def test_incorrect_password_returns_false(self, mock_load):
        mock_load.side_effect = IncorrectPassword("wrong")
        with patch.object(controller.agent_state, "get_state", return_value={}):
            assert (
                controller.update_keystore(
                    "/cfg/", {"set": {"K": "v"}, "delete": []}
                )
                is False
            )

    @patch.object(controller.LogstashKeystore, "create")
    @patch.object(controller.LogstashKeystore, "load")
    def test_creates_keystore_when_load_fails_with_logstash_exception(
        self, mock_load, mock_create
    ):
        mock_load.side_effect = LogstashKeystoreException("no file")
        ks = MagicMock()
        ks.keys = ["MYKEY"]
        ks.get_key.return_value = "secret"
        mock_create.return_value = ks

        with patch.object(controller.agent_state, "get_state", return_value={}):
            with patch.object(controller.agent_state, "update_state") as update_state:
                ok = controller.update_keystore(
                    "/cfg", {"set": {"mykey": "secret"}, "delete": []}
                )

        assert ok is True
        mock_create.assert_called_once()
        ks.add_key.assert_called_once_with({"mykey": "secret"})
        expected_hash = hashlib.sha256(b"MYKEYsecret").hexdigest()
        update_state.assert_called_once()
        call_kw = update_state.call_args
        assert call_kw[0][0] == "keystore"
        assert call_kw[0][1] == {"MYKEY": expected_hash}

    @patch.object(controller.LogstashKeystore, "load")
    def test_deletes_then_sets(self, mock_load):
        ks = MagicMock()
        ks.keys = ["OLD", "OTHER"]
        mock_load.return_value = ks

        with patch.object(controller.agent_state, "get_state", return_value={}):
            with patch.object(controller.agent_state, "update_state"):
                controller.update_keystore(
                    "/cfg/",
                    {"set": {"new": "1"}, "delete": ["old", "missing"]},
                )

        ks.remove_key.assert_called_once_with(["old"])
        ks.add_key.assert_called_once_with({"new": "1"})

    @patch.object(controller.LogstashKeystore, "load")
    def test_logstash_modified_on_delete_returns_false(self, mock_load):
        ks = MagicMock()
        ks.keys = ["K"]
        mock_load.return_value = ks
        ks.remove_key.side_effect = LogstashKeystoreModified(["k"], 1.0)

        with patch.object(controller.agent_state, "get_state", return_value={}):
            assert (
                controller.update_keystore("/cfg/", {"set": {}, "delete": ["k"]})
                is False
            )

    @patch.object(controller.LogstashKeystore, "load")
    def test_create_failure_returns_false(self, mock_load):
        mock_load.side_effect = LogstashKeystoreException("missing")
        with patch.object(
            controller.LogstashKeystore,
            "create",
            side_effect=RuntimeError("cannot create"),
        ):
            with patch.object(controller.agent_state, "get_state", return_value={}):
                assert (
                    controller.update_keystore(
                        "/cfg/", {"set": {"a": "b"}, "delete": []}
                    )
                    is False
                )


class TestRestartLogstash:
    @patch.object(controller.subprocess, "run")
    def test_systemctl_success_returns_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        assert controller.restart_logstash() is True

        mock_run.assert_called_with(
            ["systemctl", "restart", "logstash"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    @patch.object(controller.subprocess, "run")
    def test_falls_back_to_service_command(self, mock_run):
        mock_run.side_effect = [
            FileNotFoundError(),
            MagicMock(returncode=0, stderr=""),
        ]

        assert controller.restart_logstash() is True

        assert mock_run.call_args_list[1][0][0] == [
            "service",
            "logstash",
            "restart",
        ]

    @patch.object(controller.subprocess, "run")
    def test_returns_false_when_no_manager_succeeds(self, mock_run):
        mock_run.side_effect = [
            FileNotFoundError(),
            FileNotFoundError(),
        ]

        assert controller.restart_logstash() is False

    @patch.object(controller.subprocess, "run")
    def test_timeout_returns_false(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        assert controller.restart_logstash() is False


class TestGetConfigChanges:
    def test_missing_required_state_returns_none(self):
        with patch.object(
            controller.agent_state,
            "get_state",
            return_value={"logstash_ui_url": "http://x"},
        ):
            assert controller.get_config_changes() is None

    def test_no_config_files_found_returns_none(self, temp_dir):
        base = Path(temp_dir) / "empty_settings"
        base.mkdir()
        settings = str(base).replace("\\", "/") + "/"
        state = {
            "logstash_ui_url": "http://localhost:8000",
            "api_key": "key",
            "connection_id": "conn-1",
            "settings_path": settings,
        }
        with patch.object(controller.agent_state, "get_state", return_value=state):
            assert controller.get_config_changes() is None

    def test_posts_hashes_and_returns_result(self, temp_dir):
        settings = Path(temp_dir) / "ls_settings"
        settings.mkdir()
        yml = settings / "logstash.yml"
        yml.write_text("http.host: 0.0.0.0\n", encoding="utf-8")

        base = str(settings).replace("\\", "/") + "/"
        state = {
            "logstash_ui_url": "http://localhost:8000",
            "api_key": "secret-key",
            "connection_id": "conn-1",
            "settings_path": base,
            "keystore": {"FOO": "hash1"},
        }

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": True, "changes": {}}

        with patch.object(controller.agent_state, "get_state", return_value=state):
            with patch.object(controller.requests, "post", return_value=resp) as post:
                out = controller.get_config_changes()

        assert out["success"] is True
        post.assert_called_once()
        url, kwargs = post.call_args[0][0], post.call_args[1]
        assert url.endswith("/ConnectionManager/GetConfigChanges/")
        assert kwargs["json"]["connection_id"] == "conn-1"
        assert kwargs["json"]["keystore"] == {"FOO": "hash1"}
        assert kwargs["headers"]["Authorization"] == "ApiKey secret-key"
        assert kwargs["verify"] is False

    def test_http_error_returns_none(self, temp_dir):
        settings = Path(temp_dir) / "s"
        settings.mkdir()
        (settings / "logstash.yml").write_text("a", encoding="utf-8")
        base = str(settings).replace("\\", "/") + "/"
        state = {
            "logstash_ui_url": "http://localhost:8000",
            "api_key": "k",
            "connection_id": "c",
            "settings_path": base,
        }
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "err"

        with patch.object(controller.agent_state, "get_state", return_value=state):
            with patch.object(controller.requests, "post", return_value=resp):
                assert controller.get_config_changes() is None

    def test_invalid_json_returns_none(self, temp_dir):
        """JSON decode errors are caught by the outer handler and become None."""
        settings = Path(temp_dir) / "s2"
        settings.mkdir()
        (settings / "logstash.yml").write_text("a", encoding="utf-8")
        base = str(settings).replace("\\", "/") + "/"
        state = {
            "logstash_ui_url": "http://localhost:8000",
            "api_key": "k",
            "connection_id": "c",
            "settings_path": base,
        }
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        resp.headers = {}
        resp.text = "not-json"

        with patch.object(controller.agent_state, "get_state", return_value=state):
            with patch.object(controller.requests, "post", return_value=resp):
                assert controller.get_config_changes() is None

    def test_applies_changes_and_restarts(self, temp_dir):
        settings = Path(temp_dir) / "s3"
        settings.mkdir()
        (settings / "logstash.yml").write_text("old", encoding="utf-8")
        base = str(settings).replace("\\", "/") + "/"

        state = {
            "logstash_ui_url": "http://localhost:8000",
            "api_key": "k",
            "connection_id": "c",
            "settings_path": base,
        }
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "success": True,
            "changes": {"logstash_yml": "new-content"},
            "current_revision": 7,
        }

        with patch.object(controller.agent_state, "get_state", return_value=state):
            with patch.object(controller.agent_state, "update_state") as upd:
                with patch.object(
                    controller, "update_logstash_yml", return_value=True
                ) as mock_ylm:
                    with patch.object(
                        controller, "restart_logstash", return_value=True
                    ) as mock_restart:
                        with patch.object(controller.requests, "post", return_value=resp):
                            out = controller.get_config_changes()

        assert out["success"] is True
        mock_ylm.assert_called_once_with(base, "new-content")
        mock_restart.assert_called_once()
        upd.assert_called_with("revision_number", 7)


class TestCheckIn:
    def test_not_enrolled_returns_none(self):
        with patch.object(controller.agent_state, "get_state", return_value={}):
            assert controller.check_in() is None

    def test_missing_fields_returns_none(self):
        with patch.object(
            controller.agent_state,
            "get_state",
            return_value={"enrolled": True, "logstash_ui_url": "http://x"},
        ):
            assert controller.check_in() is None

    def test_success_same_revision(self):
        state = {
            "enrolled": True,
            "logstash_ui_url": "http://localhost:8000",
            "api_key": "k",
            "connection_id": "c",
            "revision_number": 5,
        }
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "success": True,
            "current_revision_number": 5,
        }

        with patch.object(controller.agent_state, "get_state", return_value=state):
            with patch.object(controller, "get_config_changes") as gcc:
                with patch.object(controller.requests, "post", return_value=resp):
                    out = controller.check_in()

        assert out["success"] is True
        gcc.assert_not_called()

    def test_success_new_revision_triggers_get_config_changes(self):
        state = {
            "enrolled": True,
            "logstash_ui_url": "http://localhost:8000",
            "api_key": "k",
            "connection_id": "c",
            "revision_number": 1,
        }
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "success": True,
            "current_revision_number": 2,
            "settings_path": "/a/",
            "logs_path": "/l/",
            "binary_path": "/b/",
        }

        with patch.object(controller.agent_state, "get_state", return_value=state):
            with patch.object(controller, "get_config_changes") as gcc:
                with patch.object(controller.requests, "post", return_value=resp):
                    controller.check_in()

        gcc.assert_called_once_with("/a/", "/l/", "/b/")

    def test_request_failure_returns_none(self):
        state = {
            "enrolled": True,
            "logstash_ui_url": "http://localhost:8000",
            "api_key": "k",
            "connection_id": "c",
        }
        with patch.object(controller.agent_state, "get_state", return_value=state):
            with patch.object(
                controller.requests,
                "post",
                side_effect=requests.exceptions.ConnectionError("down"),
            ):
                assert controller.check_in() is None

    def test_success_false_returns_result(self):
        state = {
            "enrolled": True,
            "logstash_ui_url": "http://localhost:8000",
            "api_key": "k",
            "connection_id": "c",
        }
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"success": False, "message": "no"}

        with patch.object(controller.agent_state, "get_state", return_value=state):
            with patch.object(controller.requests, "post", return_value=resp):
                out = controller.check_in()

        assert out["success"] is False


class TestRunController:
    def test_not_enrolled_returns_without_loop(self):
        with patch.object(controller.agent_state, "get_state", return_value={}):
            with patch.object(controller.time, "sleep") as sleep:
                controller.run_controller()
        sleep.assert_not_called()

    def test_loop_until_keyboard_interrupt(self):
        state = {
            "enrolled": True,
            "agent_id": "aid",
            "connection_id": "cid",
            "logstash_ui_url": "http://x",
            "policy_id": "p",
        }
        with patch.object(controller.agent_state, "get_state", return_value=state):
            with patch.object(controller, "check_in", return_value={"success": True}):
                with patch.object(
                    controller.time,
                    "sleep",
                    side_effect=KeyboardInterrupt,
                ):
                    controller.run_controller()
