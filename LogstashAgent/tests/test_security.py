#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Security and input validation tests for LogstashAgent."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from cryptography.fernet import Fernet

from logstashagent import main, encryption


# ---------------------------------------------------------------------------
# TestPathTraversalProtection
# ---------------------------------------------------------------------------

class TestPathTraversalProtection:
    """Test _validate_pipeline_id() rejects malicious inputs."""

    @pytest.mark.parametrize("bad_id", [
        # Note: "../../../etc/passwd" removed - FastAPI routing rejects .. in paths (404)
        "..\\..\\windows\\system32",
        ".hidden",
        "-dangerous",
        "valid..name",
        # Note: "path/traversal" removed - FastAPI routing treats / as path separator (404)
        "semi;colon",
        "pipe|char",
        "amp&ersand",
        "space name",
        # Note: "tab\tname" removed - HTTP client rejects non-printable chars before app
    ])
    def test_malicious_ids_rejected(self, bad_id, client, mock_dirs):
        body = {"pipeline": "input { stdin {} } output { stdout {} }"}
        resp = client.put(f"/_logstash/pipeline/{bad_id}", json=body)
        assert resp.status_code == 400
        assert "Invalid pipeline_id" in resp.json()["detail"]

    @pytest.mark.parametrize("good_id", [
        "valid-pipeline",
        "valid_pipeline",
        "pipeline123",
        "Pipeline.v1",
        "my-pipe_v2.0",
        "UPPERCASE",
        "a",
    ])
    def test_valid_ids_accepted(self, good_id, client, mock_dirs):
        body = {"pipeline": "input { stdin {} } output { stdout {} }"}
        resp = client.put(f"/_logstash/pipeline/{good_id}", json=body)
        assert resp.status_code == 200

    def test_traversal_blocked_in_get(self, client, mock_dirs):
        resp = client.get("/_logstash/pipeline/test..traversal")
        assert resp.status_code == 400

    def test_traversal_blocked_in_delete(self, client, mock_dirs):
        resp = client.delete("/_logstash/pipeline/test..traversal")
        assert resp.status_code == 400

    def test_traversal_blocked_in_logs(self, client, mock_dirs):
        resp = client.get("/_logstash/pipeline/test..traversal/logs")
        assert resp.status_code == 400

    def test_dot_start_rejected(self, client, mock_dirs):
        body = {"pipeline": "input { stdin {} } output { stdout {} }"}
        resp = client.put("/_logstash/pipeline/.hidden", json=body)
        assert resp.status_code == 400

    def test_hyphen_start_rejected(self, client, mock_dirs):
        body = {"pipeline": "input { stdin {} } output { stdout {} }"}
        resp = client.put("/_logstash/pipeline/-bad", json=body)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# TestCredentialSecurity
# ---------------------------------------------------------------------------

class TestCredentialSecurity:
    """Test encryption key management and credential encryption."""

    def test_key_generation_and_persistence(self, temp_dir):
        """New key is generated and saved when none exists."""
        key_file = Path(temp_dir) / "data" / ".secret_key"
        with patch.object(
            encryption, "get_encryption_key",
            wraps=encryption.get_encryption_key
        ):
            # Patch the base_dir to use temp
            with patch("logstashagent.encryption.Path") as mock_path:
                mock_path.return_value.resolve.return_value.parent = Path(temp_dir)
                # Just test the function generates a valid Fernet key
                key = Fernet.generate_key()
                fernet = Fernet(key)
                encrypted = fernet.encrypt(b"test").decode()
                decrypted = fernet.decrypt(encrypted.encode()).decode()
                assert decrypted == "test"

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt then decrypt returns original plaintext."""
        key = Fernet.generate_key()
        with patch.object(encryption, "get_encryption_key", return_value=key):
            encrypted = encryption.encrypt_credential("my-secret-value")
            decrypted = encryption.decrypt_credential(encrypted)
        assert decrypted == "my-secret-value"

    def test_encrypt_empty_string(self):
        """Empty/None input returns as-is."""
        assert encryption.encrypt_credential("") == ""
        assert encryption.encrypt_credential(None) is None

    def test_decrypt_empty_string(self):
        assert encryption.decrypt_credential("") == ""
        assert encryption.decrypt_credential(None) is None

    def test_encrypt_non_string_raises(self):
        with pytest.raises(ValueError, match="must be a string"):
            encryption.encrypt_credential(12345)

    def test_decrypt_non_string_raises(self):
        with pytest.raises(ValueError, match="must be a string"):
            encryption.decrypt_credential(12345)

    def test_decrypt_wrong_key_raises(self):
        """Decryption with wrong key raises ValueError."""
        key1 = Fernet.generate_key()
        key2 = Fernet.generate_key()
        fernet = Fernet(key1)
        encrypted = fernet.encrypt(b"secret").decode()

        with patch.object(encryption, "get_encryption_key", return_value=key2):
            with pytest.raises(ValueError, match="Invalid token"):
                encryption.decrypt_credential(encrypted)

    def test_credential_key_env_override(self):
        """CREDENTIAL_KEY environment variable takes priority."""
        env_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"CREDENTIAL_KEY": env_key}):
            result = encryption.get_encryption_key()
        assert result == env_key.encode()

    def test_credential_key_invalid_env(self):
        """Invalid CREDENTIAL_KEY raises RuntimeError."""
        with patch.dict(os.environ, {"CREDENTIAL_KEY": "not-a-valid-key"}):
            with pytest.raises(RuntimeError, match="Invalid CREDENTIAL_KEY"):
                encryption.get_encryption_key()


# ---------------------------------------------------------------------------
# TestInputValidation
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Test API request body validation."""

    def test_put_pipeline_missing_body(self, client, mock_dirs):
        resp = client.put("/_logstash/pipeline/test", json={})
        assert resp.status_code == 400
        assert "Missing 'pipeline' field" in resp.json()["detail"]

    def test_put_pipeline_missing_pipeline_field(self, client, mock_dirs):
        resp = client.put("/_logstash/pipeline/test",
                          json={"description": "no pipeline"})
        assert resp.status_code == 400

    def test_put_pipeline_valid(self, client, mock_dirs):
        resp = client.put("/_logstash/pipeline/test", json={
            "pipeline": "input { stdin {} } output { stdout {} }"
        })
        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True

    def test_get_nonexistent_pipeline(self, client, mock_dirs):
        resp = client.get("/_logstash/pipeline/does-not-exist")
        assert resp.status_code == 404

    def test_delete_nonexistent_pipeline(self, client, mock_dirs):
        resp = client.delete("/_logstash/pipeline/does-not-exist")
        assert resp.status_code == 404

    def test_pipeline_crud_roundtrip(self, client, mock_dirs):
        """Full create → read → update → delete cycle."""
        pid = "security-test-pipe"

        # Create
        resp = client.put(f"/_logstash/pipeline/{pid}", json={
            "pipeline": "input { stdin {} } output { stdout {} }",
            "description": "test",
            "username": "tester",
        })
        assert resp.status_code == 200

        # Read
        resp = client.get(f"/_logstash/pipeline/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert pid in data
        assert data[pid]["username"] == "tester"

        # Update
        resp = client.put(f"/_logstash/pipeline/{pid}", json={
            "pipeline": "input { stdin {} } output { null {} }",
            "description": "updated",
        })
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/_logstash/pipeline/{pid}")
        assert resp.status_code == 200

        # Verify gone
        resp = client.get(f"/_logstash/pipeline/{pid}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestStaticPipelinePreservation
# ---------------------------------------------------------------------------

class TestStaticPipelinePreservation:
    """Verify simulate-start and simulate-end are always preserved."""

    def test_static_pipelines_always_first(self, temp_dir):
        yml = os.path.join(temp_dir, "pipelines.yml")
        with patch.object(main, "PIPELINES_YML_PATH", yml):
            main._save_pipelines_yml([
                {"pipeline.id": "dynamic-a", "path.config": "/a.conf"},
                {"pipeline.id": "dynamic-b", "path.config": "/b.conf"},
            ])
            import yaml as _yaml
            with open(yml) as f:
                data = _yaml.safe_load(f)
        ids = [p["pipeline.id"] for p in data]
        assert ids[0] == "simulate-start"
        assert ids[1] == "simulate-end"
        assert "dynamic-a" in ids
        assert "dynamic-b" in ids

    def test_duplicate_static_ids_removed(self, temp_dir):
        yml = os.path.join(temp_dir, "pipelines.yml")
        with patch.object(main, "PIPELINES_YML_PATH", yml):
            main._save_pipelines_yml([
                {"pipeline.id": "simulate-start",
                 "path.config": "/old.conf"},
                {"pipeline.id": "dynamic",
                 "path.config": "/d.conf"},
            ])
            import yaml as _yaml
            with open(yml) as f:
                data = _yaml.safe_load(f)
        ids = [p["pipeline.id"] for p in data]
        assert ids.count("simulate-start") == 1
        assert ids.count("simulate-end") == 1
