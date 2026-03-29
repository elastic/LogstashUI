#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for logstashagent.agent_state (state file, agent id, encryption hooks)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from logstashagent import agent_state


def test_default_state_dir_is_package_local():
    expected = Path(agent_state.__file__).resolve().parent / "data"
    assert agent_state.STATE_DIR.resolve() == expected


@pytest.fixture
def isolated_state(temp_dir):
    """Use a temp directory for STATE_DIR / STATE_FILE instead of package data."""
    state_dir = Path(temp_dir) / "data"
    state_file = state_dir / "state.json"
    with patch.object(agent_state, "STATE_DIR", state_dir), patch.object(
        agent_state, "STATE_FILE", state_file
    ):
        yield {"state_dir": state_dir, "state_file": state_file}


class TestGetOrCreateAgentId:
    """Tests for get_or_create_agent_id()."""

    def test_creates_new_id_and_persists(self, isolated_state):
        fixed = "11111111-2222-3333-4444-555555555555"

        with patch.object(agent_state.uuid, "uuid4", return_value=MagicMock(__str__=lambda _: fixed)):
            result = agent_state.get_or_create_agent_id()

        assert result == fixed
        f = isolated_state["state_file"]
        assert f.exists()
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data == {"agent_id": fixed}

    def test_returns_existing_agent_id(self, isolated_state):
        existing = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        f = isolated_state["state_file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"agent_id": existing}), encoding="utf-8")

        result = agent_state.get_or_create_agent_id()

        assert result == existing
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["agent_id"] == existing

    def test_regenerates_when_file_has_no_agent_id(self, isolated_state):
        f = isolated_state["state_file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"other": "value"}), encoding="utf-8")
        fixed = "99999999-aaaa-bbbb-cccc-dddddddddddd"

        with patch.object(agent_state.uuid, "uuid4", return_value=MagicMock(__str__=lambda _: fixed)):
            result = agent_state.get_or_create_agent_id()

        assert result == fixed
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["agent_id"] == fixed

    def test_regenerates_on_invalid_json(self, isolated_state):
        f = isolated_state["state_file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("not json {", encoding="utf-8")
        fixed = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"

        with patch.object(agent_state.uuid, "uuid4", return_value=MagicMock(__str__=lambda _: fixed)):
            result = agent_state.get_or_create_agent_id()

        assert result == fixed
        assert json.loads(f.read_text(encoding="utf-8"))["agent_id"] == fixed

    def test_returns_new_id_even_if_save_fails(self, isolated_state):
        fixed = "cccccccc-dddd-eeee-ffff-000000000000"

        with patch.object(agent_state.uuid, "uuid4", return_value=MagicMock(__str__=lambda _: fixed)):
            with patch("builtins.open", mock_open()) as m:
                m.side_effect = OSError("write failed")
                result = agent_state.get_or_create_agent_id()

        assert result == fixed


class TestGetState:
    """Tests for get_state()."""

    def test_returns_empty_dict_when_no_file(self, isolated_state):
        assert agent_state.get_state() == {}

    def test_loads_plain_state(self, isolated_state):
        f = isolated_state["state_file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"foo": "bar", "n": 1}), encoding="utf-8")

        assert agent_state.get_state() == {"foo": "bar", "n": 1}

    def test_decrypts_api_key_when_present(self, isolated_state):
        f = isolated_state["state_file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"api_key": "blob"}), encoding="utf-8")

        with patch.object(
            agent_state.encryption,
            "decrypt_credential",
            return_value="decrypted-secret",
        ) as dec:
            state = agent_state.get_state()

        dec.assert_called_once_with("blob")
        assert state["api_key"] == "decrypted-secret"

    def test_keeps_ciphertext_when_decrypt_fails(self, isolated_state):
        f = isolated_state["state_file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"api_key": "bad-blob"}), encoding="utf-8")

        with patch.object(
            agent_state.encryption,
            "decrypt_credential",
            side_effect=ValueError("bad token"),
        ):
            state = agent_state.get_state()

        assert state["api_key"] == "bad-blob"

    def test_skips_decrypt_for_empty_api_key(self, isolated_state):
        f = isolated_state["state_file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"api_key": ""}), encoding="utf-8")

        with patch.object(
            agent_state.encryption,
            "decrypt_credential",
        ) as dec:
            state = agent_state.get_state()

        dec.assert_not_called()
        assert state["api_key"] == ""

    def test_returns_empty_dict_on_invalid_json(self, isolated_state):
        f = isolated_state["state_file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{", encoding="utf-8")

        assert agent_state.get_state() == {}


class TestUpdateState:
    """Tests for update_state()."""

    def test_writes_new_key(self, isolated_state):
        agent_state.update_state("hello", "world")

        data = json.loads(isolated_state["state_file"].read_text(encoding="utf-8"))
        assert data["hello"] == "world"

    def test_merges_with_existing_state(self, isolated_state):
        f = isolated_state["state_file"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"a": 1}), encoding="utf-8")

        agent_state.update_state("b", 2)

        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["a"] == 1
        assert data["b"] == 2

    def test_encrypts_api_key_before_save(self, isolated_state):
        with patch.object(
            agent_state.encryption,
            "encrypt_credential",
            return_value="ENC_STORED",
        ) as enc:
            agent_state.update_state("api_key", "plain-secret")

        enc.assert_called_once_with("plain-secret")
        data = json.loads(isolated_state["state_file"].read_text(encoding="utf-8"))
        assert data["api_key"] == "ENC_STORED"

    def test_skips_encrypt_for_empty_api_key(self, isolated_state):
        with patch.object(
            agent_state.encryption,
            "encrypt_credential",
        ) as enc:
            agent_state.update_state("api_key", "")

        enc.assert_not_called()
        data = json.loads(isolated_state["state_file"].read_text(encoding="utf-8"))
        assert data["api_key"] == ""

    def test_saves_unencrypted_api_key_when_encrypt_fails(self, isolated_state):
        with patch.object(
            agent_state.encryption,
            "encrypt_credential",
            side_effect=RuntimeError("no key"),
        ):
            agent_state.update_state("api_key", "fallback-plain")

        data = json.loads(isolated_state["state_file"].read_text(encoding="utf-8"))
        assert data["api_key"] == "fallback-plain"
