#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for logstashagent.enrollment."""

import base64
import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from logstashagent import enrollment


def _encoded_token(payload: dict) -> str:
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


class TestGetHostname:
    def test_returns_socket_hostname(self):
        with patch.object(enrollment.socket, "gethostname", return_value="my-box"):
            assert enrollment.get_hostname() == "my-box"

    def test_unknown_host_on_error(self):
        with patch.object(
            enrollment.socket,
            "gethostname",
            side_effect=OSError("no name"),
        ):
            assert enrollment.get_hostname() == "unknown-host"


class TestDecodeEnrollmentToken:
    def test_decodes_valid_payload(self):
        payload = {"enrollment_token": "secret-inner", "extra": 1}
        encoded = _encoded_token(payload)

        out = enrollment.decode_enrollment_token(encoded)

        assert out == payload

    def test_missing_enrollment_token_raises(self):
        encoded = _encoded_token({"other": "x"})

        with pytest.raises(ValueError, match="Failed to decode enrollment token"):
            enrollment.decode_enrollment_token(encoded)

    def test_invalid_base64_raises(self):
        with pytest.raises(ValueError, match="Failed to decode enrollment token"):
            enrollment.decode_enrollment_token("@@@not-base64!!!")

    def test_invalid_json_raises(self):
        raw = base64.b64encode(b"not-json").decode("ascii")

        with pytest.raises(ValueError, match="Failed to decode enrollment token"):
            enrollment.decode_enrollment_token(raw)


class TestEnrollAgent:
    def test_posts_and_returns_result(self):
        token_payload = {"enrollment_token": "inner"}
        encoded = _encoded_token(token_payload)
        response = MagicMock()
        response.status_code = 200
        response.headers = {}
        response.text = "{}"
        result_body = {
            "success": True,
            "api_key": "ak",
            "policy_id": 9,
            "connection_id": 42,
            "policy_config": {},
        }
        response.json.return_value = result_body

        with patch.object(enrollment, "get_hostname", return_value="host-1"):
            with patch.object(enrollment.requests, "post", return_value=response) as post:
                out = enrollment.enroll_agent(
                    encoded, "https://ui.example.com", "agent-uuid"
                )

        assert out == result_body
        post.assert_called_once()
        args, kwargs = post.call_args
        assert args[0] == "https://ui.example.com/ConnectionManager/Enroll/"
        assert kwargs["json"] == {
            "enrollment_token": encoded,
            "host": "host-1",
            "agent_id": "agent-uuid",
        }
        assert kwargs["timeout"] == 30
        assert kwargs["verify"] is False

    def test_success_false_raises(self):
        encoded = _encoded_token({"enrollment_token": "x"})
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {"success": False, "error": "nope"}

        with patch.object(enrollment, "get_hostname", return_value="h"):
            with patch.object(enrollment.requests, "post", return_value=response):
                with pytest.raises(Exception, match="Enrollment failed: nope"):
                    enrollment.enroll_agent(encoded, "http://localhost", "aid")

    def test_non_json_response_raises(self):
        encoded = _encoded_token({"enrollment_token": "x"})
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.text = "<html>not json</html>"
        response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)

        with patch.object(enrollment, "get_hostname", return_value="h"):
            with patch.object(enrollment.requests, "post", return_value=response):
                with pytest.raises(Exception, match="Server returned non-JSON response"):
                    enrollment.enroll_agent(encoded, "http://localhost:8000", "aid")

    def test_request_exception_wrapped(self):
        encoded = _encoded_token({"enrollment_token": "x"})
        with patch.object(enrollment, "get_hostname", return_value="h"):
            with patch.object(
                enrollment.requests,
                "post",
                side_effect=requests.exceptions.ConnectionError("refused"),
            ):
                with pytest.raises(Exception, match="Failed to connect to logstashui"):
                    enrollment.enroll_agent(encoded, "http://down", "aid")


class TestComputeHash:
    def test_sha256_hex(self):
        assert enrollment.compute_hash("hello") == hashlib.sha256(
            b"hello"
        ).hexdigest()


class TestSaveEnrollmentConfig:
    def test_updates_agent_state(self):
        policy = {"settings_path": "/etc/logstash", "logs_path": "/var/log"}

        with patch.object(enrollment.agent_state, "update_state") as upd:
            enrollment.save_enrollment_config(
                api_key="key",
                logstash_ui_url="http://ui",
                policy_id=3,
                connection_id=7,
                policy_config=policy,
            )

        calls = [c[0] for c in upd.call_args_list]
        assert calls == [
            ("enrolled", True),
            ("logstash_ui_url", "http://ui"),
            ("api_key", "key"),
            ("policy_id", 3),
            ("connection_id", 7),
            ("settings_path", "/etc/logstash"),
            ("logs_path", "/var/log"),
            ("revision_number", 0),
        ]

    def test_propagates_update_state_failure(self):
        with patch.object(
            enrollment.agent_state,
            "update_state",
            side_effect=OSError("disk full"),
        ):
            with pytest.raises(Exception, match="Failed to save enrollment configuration"):
                enrollment.save_enrollment_config(
                    "k",
                    "http://x",
                    1,
                    2,
                    {},
                )


class TestPerformEnrollment:
    def test_full_flow(self):
        encoded = _encoded_token({"enrollment_token": "t"})
        enroll_result = {
            "success": True,
            "api_key": "long-api-key-value",
            "policy_id": 1,
            "connection_id": 2,
            "policy_config": {"settings_path": "/s", "logs_path": "/l"},
        }

        with patch.object(enrollment, "enroll_agent", return_value=enroll_result):
            with patch.object(enrollment, "save_enrollment_config") as save:
                out = enrollment.perform_enrollment(
                    encoded, "https://example.com", "agent-1"
                )

        assert out == enroll_result
        save.assert_called_once_with(
            api_key="long-api-key-value",
            logstash_ui_url="https://example.com",
            policy_id=1,
            connection_id=2,
            policy_config={"settings_path": "/s", "logs_path": "/l"},
        )

    def test_re_raises_on_enroll_failure(self):
        encoded = _encoded_token({"enrollment_token": "t"})

        with patch.object(
            enrollment,
            "enroll_agent",
            side_effect=Exception("network"),
        ):
            with pytest.raises(Exception, match="network"):
                enrollment.perform_enrollment(encoded, "http://x", "aid")
