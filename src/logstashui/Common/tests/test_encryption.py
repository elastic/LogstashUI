#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, Mock
from cryptography.fernet import Fernet, InvalidToken

from Common.encryption import (
    get_encryption_key,
    encrypt_credential,
    decrypt_credential,
    get_django_secret_key
)


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory for testing"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def mock_base_dir(temp_data_dir, monkeypatch):
    """Mock the base directory to use temp directory"""
    def mock_resolve():
        class MockPath:
            def __init__(self):
                self.parent = temp_data_dir.parent
        return MockPath()
    
    with patch('Common.encryption.py.Path') as mock_path:
        mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
        yield temp_data_dir


class TestGetEncryptionKey:
    """Test get_encryption_key function"""

    def test_key_from_environment_variable(self, monkeypatch, temp_data_dir):
        """Test loading key from CREDENTIAL_KEY environment variable"""
        valid_key = Fernet.generate_key()
        monkeypatch.setenv('CREDENTIAL_KEY', valid_key.decode())
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_encryption_key()
        
        assert key == valid_key
        assert isinstance(key, bytes)

    def test_invalid_key_in_environment_variable(self, monkeypatch, temp_data_dir):
        """Test that invalid CREDENTIAL_KEY raises RuntimeError"""
        monkeypatch.setenv('CREDENTIAL_KEY', 'invalid-key-format')
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            with pytest.raises(RuntimeError, match="Invalid CREDENTIAL_KEY format"):
                get_encryption_key()

    def test_key_from_file(self, temp_data_dir):
        """Test loading key from file"""
        key_file = temp_data_dir / ".secret_key"
        valid_key = Fernet.generate_key()
        key_file.write_bytes(valid_key)
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_encryption_key()
        
        assert key == valid_key

    def test_invalid_key_in_file(self, temp_data_dir):
        """Test that invalid key in file raises RuntimeError"""
        key_file = temp_data_dir / ".secret_key"
        key_file.write_bytes(b'invalid-key-data')
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            with pytest.raises(RuntimeError, match="Invalid encryption.py key in file"):
                get_encryption_key()

    def test_generate_new_key_and_persist(self, temp_data_dir):
        """Test generating new key and persisting to file"""
        key_file = temp_data_dir / ".secret_key"
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_encryption_key()
        
        # Verify key was generated
        assert isinstance(key, bytes)
        assert len(key) > 0
        
        # Verify key was saved to file
        assert key_file.exists()
        saved_key = key_file.read_bytes()
        assert saved_key == key
        
        # Verify key is valid Fernet key
        fernet = Fernet(key)
        assert fernet is not None

    def test_permission_error_reading_key_file(self, temp_data_dir):
        """Test handling of permission errors when reading key file"""
        key_file = temp_data_dir / ".secret_key"
        key_file.write_bytes(Fernet.generate_key())
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            with patch('builtins.open', side_effect=PermissionError("Access denied")):
                with pytest.raises(RuntimeError, match="Cannot read encryption.py key file: Permission denied"):
                    get_encryption_key()


class TestEncryptDecryptCredential:
    """Test encrypt_credential and decrypt_credential functions"""

    def test_encrypt_decrypt_round_trip(self, temp_data_dir):
        """Test that encryption.py and decryption work correctly"""
        plaintext = "my-secret-password"
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            
            encrypted = encrypt_credential(plaintext)
            assert encrypted != plaintext
            assert isinstance(encrypted, str)
            
            decrypted = decrypt_credential(encrypted)
            assert decrypted == plaintext

    def test_encrypt_empty_string_passthrough(self):
        """Test that empty string is passed through without encryption.py"""
        assert encrypt_credential("") == ""
        assert encrypt_credential(None) is None

    def test_decrypt_empty_string_passthrough(self):
        """Test that empty string is passed through without decryption"""
        assert decrypt_credential("") == ""
        assert decrypt_credential(None) is None

    def test_encrypt_non_string_raises_error(self):
        """Test that encrypting non-string raises ValueError"""
        with pytest.raises(ValueError, match="plaintext must be a string"):
            encrypt_credential(123)
        
        with pytest.raises(ValueError, match="plaintext must be a string"):
            encrypt_credential(['list'])

    def test_decrypt_non_string_raises_error(self):
        """Test that decrypting non-string raises ValueError"""
        with pytest.raises(ValueError, match="encrypted_text must be a string"):
            decrypt_credential(123)
        
        with pytest.raises(ValueError, match="encrypted_text must be a string"):
            decrypt_credential(['list'])

    def test_decrypt_invalid_token(self, temp_data_dir):
        """Test that decrypting with invalid token raises ValueError"""
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            
            with pytest.raises(ValueError, match="Cannot decrypt credential: Invalid token"):
                decrypt_credential("invalid-encrypted-data")

    def test_decrypt_with_wrong_key(self, temp_data_dir):
        """Test that decrypting with wrong key raises ValueError"""
        # Encrypt with one key
        key1 = Fernet.generate_key()
        fernet1 = Fernet(key1)
        encrypted = fernet1.encrypt(b"secret").decode()
        
        # Try to decrypt with different key
        key_file = temp_data_dir / ".secret_key"
        key2 = Fernet.generate_key()
        key_file.write_bytes(key2)
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            
            with pytest.raises(ValueError, match="Cannot decrypt credential: Invalid token"):
                decrypt_credential(encrypted)

    def test_encrypt_unicode_characters(self, temp_data_dir):
        """Test encrypting and decrypting unicode characters"""
        plaintext = "🔒 Secret with émojis and spëcial çhars 中文"
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            
            encrypted = encrypt_credential(plaintext)
            decrypted = decrypt_credential(encrypted)
            assert decrypted == plaintext


class TestGetDjangoSecretKey:
    """Test get_django_secret_key function"""

    def test_key_from_environment_variable(self, monkeypatch, temp_data_dir):
        """Test loading Django secret key from environment variable"""
        secret_key = "test-secret-key-from-environment-variable-long-enough"
        monkeypatch.setenv('SECRET_KEY', secret_key)
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_django_secret_key()
        
        assert key == secret_key

    def test_short_key_warning(self, monkeypatch, temp_data_dir, caplog):
        """Test that short SECRET_KEY generates warning"""
        short_key = "short"
        monkeypatch.setenv('SECRET_KEY', short_key)
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_django_secret_key()
        
        assert key == short_key
        assert "SECRET_KEY from environment is short" in caplog.text

    def test_key_from_file(self, temp_data_dir):
        """Test loading Django secret key from file"""
        key_file = temp_data_dir / ".django_secret_key"
        secret_key = "test-secret-key-from-file-should-be-long-enough-now"
        key_file.write_text(secret_key)
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_django_secret_key()
        
        assert key == secret_key

    def test_empty_key_file_raises_error(self, temp_data_dir):
        """Test that empty key file raises RuntimeError"""
        key_file = temp_data_dir / ".django_secret_key"
        key_file.write_text("")
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            with pytest.raises(RuntimeError, match="Django secret key file is empty"):
                get_django_secret_key()

    def test_generate_new_key_and_persist(self, temp_data_dir):
        """Test generating new Django secret key and persisting to file"""
        key_file = temp_data_dir / ".django_secret_key"
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            key = get_django_secret_key()
        
        # Verify key was generated
        assert isinstance(key, str)
        assert len(key) == 50
        
        # Verify key contains expected characters
        valid_chars = set('abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)')
        assert all(c in valid_chars for c in key)
        
        # Verify key was saved to file
        assert key_file.exists()
        saved_key = key_file.read_text().strip()
        assert saved_key == key

    def test_permission_error_reading_key_file(self, temp_data_dir):
        """Test handling of permission errors when reading Django secret key file"""
        key_file = temp_data_dir / ".django_secret_key"
        key_file.write_text("test-key")
        
        with patch('Common.encryption.py.Path') as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent = temp_data_dir.parent
            with patch('builtins.open', side_effect=PermissionError("Access denied")):
                with pytest.raises(RuntimeError, match="Cannot read Django secret key: Permission denied"):
                    get_django_secret_key()
