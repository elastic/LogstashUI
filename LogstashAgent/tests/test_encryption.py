#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for logstashagent.encryption (Fernet credential storage)."""

import pytest
from unittest.mock import patch

from cryptography.fernet import Fernet

from logstashagent.encryption import (
    decrypt_credential,
    encrypt_credential,
    get_encryption_key,
)


@pytest.fixture
def temp_data_dir(tmp_path):
    """Temporary ``data/`` directory where ``.secret_key`` is written."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def no_env_credential_key(monkeypatch):
    """Ensure file-based key resolution is used when tests expect it."""
    monkeypatch.delenv("CREDENTIAL_KEY", raising=False)


class TestGetEncryptionKey:
    """Tests for get_encryption_key."""

    def test_key_from_environment_variable(self, monkeypatch, temp_data_dir):
        valid_key = Fernet.generate_key()
        monkeypatch.setenv("CREDENTIAL_KEY", valid_key.decode())

        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_encryption_key()

        assert key == valid_key
        assert isinstance(key, bytes)

    def test_invalid_key_in_environment_variable(self, monkeypatch, temp_data_dir):
        monkeypatch.setenv("CREDENTIAL_KEY", "invalid-key-format")

        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            with pytest.raises(RuntimeError, match="Invalid CREDENTIAL_KEY format"):
                get_encryption_key()

    def test_key_from_file(self, no_env_credential_key, temp_data_dir):
        key_file = temp_data_dir / ".secret_key"
        valid_key = Fernet.generate_key()
        key_file.write_bytes(valid_key)

        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_encryption_key()

        assert key == valid_key

    def test_invalid_key_in_file(self, no_env_credential_key, temp_data_dir):
        key_file = temp_data_dir / ".secret_key"
        key_file.write_bytes(b"invalid-key-data")

        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            with pytest.raises(RuntimeError, match="Invalid encryption key in file"):
                get_encryption_key()

    def test_generate_new_key_and_persist(self, no_env_credential_key, temp_data_dir):
        key_file = temp_data_dir / ".secret_key"

        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_encryption_key()

        assert isinstance(key, bytes)
        assert len(key) > 0
        assert key_file.exists()
        assert key_file.read_bytes() == key
        assert Fernet(key) is not None

    def test_permission_error_reading_key_file(self, no_env_credential_key, temp_data_dir):
        key_file = temp_data_dir / ".secret_key"
        key_file.write_bytes(Fernet.generate_key())

        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            with patch("builtins.open", side_effect=PermissionError("Access denied")):
                with pytest.raises(
                    RuntimeError,
                    match="Cannot read encryption key file: Permission denied",
                ):
                    get_encryption_key()


class TestEncryptDecryptCredential:
    """Tests for encrypt_credential and decrypt_credential."""

    def test_encrypt_decrypt_round_trip(self, no_env_credential_key, temp_data_dir):
        plaintext = "my-secret-password"

        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent

            encrypted = encrypt_credential(plaintext)
            assert encrypted != plaintext
            assert isinstance(encrypted, str)

            decrypted = decrypt_credential(encrypted)
            assert decrypted == plaintext

    def test_encrypt_empty_string_passthrough(self):
        assert encrypt_credential("") == ""
        assert encrypt_credential(None) is None

    def test_decrypt_empty_string_passthrough(self):
        assert decrypt_credential("") == ""
        assert decrypt_credential(None) is None

    def test_encrypt_non_string_raises_error(self):
        with pytest.raises(ValueError, match="plaintext must be a string"):
            encrypt_credential(123)

        with pytest.raises(ValueError, match="plaintext must be a string"):
            encrypt_credential(["list"])

    def test_decrypt_non_string_raises_error(self):
        with pytest.raises(ValueError, match="encrypted_text must be a string"):
            decrypt_credential(123)

        with pytest.raises(ValueError, match="encrypted_text must be a string"):
            decrypt_credential(["list"])

    def test_decrypt_invalid_token(self, no_env_credential_key, temp_data_dir):
        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent

            with pytest.raises(
                ValueError,
                match="Cannot decrypt credential: Invalid token or wrong encryption key",
            ):
                decrypt_credential("invalid-encrypted-data")

    def test_decrypt_with_wrong_key(self, no_env_credential_key, temp_data_dir):
        key1 = Fernet.generate_key()
        fernet1 = Fernet(key1)
        encrypted = fernet1.encrypt(b"secret").decode()

        key_file = temp_data_dir / ".secret_key"
        key_file.write_bytes(Fernet.generate_key())

        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent

            with pytest.raises(
                ValueError,
                match="Cannot decrypt credential: Invalid token or wrong encryption key",
            ):
                decrypt_credential(encrypted)

    def test_encrypt_unicode_characters(self, no_env_credential_key, temp_data_dir):
        plaintext = "🔒 Secret with émojis and spëcial çhars 中文"

        with patch("logstashagent.encryption.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent

            encrypted = encrypt_credential(plaintext)
            decrypted = decrypt_credential(encrypted)
            assert decrypted == plaintext
