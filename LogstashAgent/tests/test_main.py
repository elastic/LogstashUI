#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for logstashagent.main (YAML helpers, pipeline HTTP API, write_file)."""

import base64
import os
from unittest.mock import mock_open, patch

import pytest
import yaml

from logstashagent import main


class TestLoadPipelinesYml:
    """Test _load_pipelines_yml() with various file states"""

    def test_empty_file(self, mock_pipelines_yml):
        """Test loading an empty file returns empty list"""
        open(mock_pipelines_yml, "w").close()

        result = main._load_pipelines_yml()
        assert result == []

    def test_comment_only_file(self, mock_pipelines_yml):
        """Test loading a file with only comments returns empty list"""
        with open(mock_pipelines_yml, "w") as f:
            f.write("# This is a comment\n")
            f.write("# Another comment\n")
            f.write("  # Indented comment\n")

        result = main._load_pipelines_yml()
        assert result == []

    def test_valid_yaml(self, mock_pipelines_yml):
        """Test loading valid YAML returns parsed data"""
        pipelines = [
            {
                "pipeline.id": "test-pipeline",
                "path.config": "/etc/logstash/conf.d/test.conf",
                "pipeline.workers": 2,
            }
        ]

        with open(mock_pipelines_yml, "w") as f:
            yaml.dump(pipelines, f)

        result = main._load_pipelines_yml()
        assert result == pipelines
        assert len(result) == 1
        assert result[0]["pipeline.id"] == "test-pipeline"

    def test_corrupted_yaml(self, mock_pipelines_yml):
        """Test loading corrupted YAML returns empty list and logs error"""
        with open(mock_pipelines_yml, "w") as f:
            f.write("invalid: yaml: content:\n")
            f.write("  - broken\n")
            f.write("  unclosed: [\n")

        result = main._load_pipelines_yml()
        assert result == []

    def test_nonexistent_file(self, temp_dir):
        """Test loading nonexistent file returns empty list"""
        yml_path = os.path.join(temp_dir, "nonexistent.yml")

        with patch.object(main, "PIPELINES_YML_PATH", yml_path):
            result = main._load_pipelines_yml()
            assert result == []


class TestSavePipelinesYml:
    """Test _save_pipelines_yml() atomic write behavior"""

    def test_atomic_write_succeeds(self, mock_pipelines_yml):
        """Test successful atomic write; static simulate-* pipelines are always first."""
        pipelines = [
            {
                "pipeline.id": "test-pipeline",
                "path.config": "/etc/logstash/conf.d/test.conf",
            }
        ]

        main._save_pipelines_yml(pipelines)

        assert os.path.exists(mock_pipelines_yml)

        with open(mock_pipelines_yml, "r") as f:
            loaded = yaml.safe_load(f)

        ids = [p["pipeline.id"] for p in loaded]
        assert ids[:2] == ["simulate-start", "simulate-end"]
        test_entry = next(p for p in loaded if p["pipeline.id"] == "test-pipeline")
        assert test_entry["path.config"] == "/etc/logstash/conf.d/test.conf"

        temp_file = f"{mock_pipelines_yml}.tmp"
        assert not os.path.exists(temp_file)

    def test_temp_file_cleanup_on_failure(self, mock_pipelines_yml):
        """Test that temp file is cleaned up when write fails"""
        pipelines = [{"pipeline.id": "test"}]
        temp_file = f"{mock_pipelines_yml}.tmp"

        with patch("os.replace", side_effect=OSError("Simulated failure")):
            with pytest.raises(OSError):
                main._save_pipelines_yml(pipelines)

        assert not os.path.exists(temp_file)

    def test_multiple_writes_atomic(self, mock_pipelines_yml):
        """Test multiple writes don't leave temp files"""
        for i in range(3):
            pipelines = [{"pipeline.id": f"pipeline-{i}"}]
            main._save_pipelines_yml(pipelines)

        assert os.path.exists(mock_pipelines_yml)
        assert not os.path.exists(f"{mock_pipelines_yml}.tmp")

        with open(mock_pipelines_yml, "r") as f:
            loaded = yaml.safe_load(f)
        assert [p["pipeline.id"] for p in loaded[:2]] == [
            "simulate-start",
            "simulate-end",
        ]
        assert loaded[2]["pipeline.id"] == "pipeline-2"


class TestPipelineCRUD:
    """Test full CRUD cycle for pipelines"""

    def test_full_crud_roundtrip(self, client, mock_dirs):
        """Test create, read, update, delete pipeline"""
        pipeline_id = "test-crud-pipeline"

        create_body = {
            "pipeline": 'input { stdin {} } filter { mutate { add_field => { "test" => "value" } } } output { stdout {} }',
            "description": "Test CRUD pipeline",
            "username": "test-user",
            "pipeline_settings": {
                "pipeline.workers": 2,
                "pipeline.batch.size": 125,
            },
        }

        response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=create_body)
        assert response.status_code == 200
        assert response.json()["acknowledged"] is True

        config_path = os.path.join(mock_dirs["pipelines_dir"], f"{pipeline_id}.conf")
        assert os.path.exists(config_path)

        metadata_path = os.path.join(mock_dirs["metadata_dir"], f"{pipeline_id}.json")
        assert os.path.exists(metadata_path)

        response = client.get(f"/_logstash/pipeline/{pipeline_id}")
        assert response.status_code == 200
        data = response.json()

        assert pipeline_id in data
        assert data[pipeline_id]["description"] == "Test CRUD pipeline"
        assert data[pipeline_id]["username"] == "test-user"
        assert data[pipeline_id]["pipeline"] == create_body["pipeline"]
        assert data[pipeline_id]["pipeline_settings"]["pipeline.workers"] == 2

        update_body = {
            "pipeline": "input { stdin {} } output { stdout { codec => json } }",
            "description": "Updated CRUD pipeline",
            "username": "updated-user",
            "pipeline_settings": {
                "pipeline.workers": 4,
            },
        }

        response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=update_body)
        assert response.status_code == 200

        response = client.get(f"/_logstash/pipeline/{pipeline_id}")
        assert response.status_code == 200
        data = response.json()

        assert data[pipeline_id]["description"] == "Updated CRUD pipeline"
        assert data[pipeline_id]["username"] == "updated-user"
        assert data[pipeline_id]["pipeline_settings"]["pipeline.workers"] == 4

        response = client.delete(f"/_logstash/pipeline/{pipeline_id}")
        assert response.status_code == 200
        assert response.json()["acknowledged"] is True

        assert not os.path.exists(config_path)
        assert not os.path.exists(metadata_path)

        response = client.get(f"/_logstash/pipeline/{pipeline_id}")
        assert response.status_code == 404

    def test_get_nonexistent_pipeline(self, client, mock_dirs):
        """Test getting a pipeline that doesn't exist"""
        response = client.get("/_logstash/pipeline/nonexistent")
        assert response.status_code == 404

    def test_delete_nonexistent_pipeline(self, client, mock_dirs):
        """Test deleting a pipeline that doesn't exist"""
        response = client.delete("/_logstash/pipeline/nonexistent")
        assert response.status_code == 404

    def test_put_pipeline_missing_config(self, client, mock_dirs):
        """Test putting a pipeline without required 'pipeline' field"""
        response = client.put(
            "/_logstash/pipeline/test", json={"description": "Missing pipeline"}
        )
        assert response.status_code == 400
        assert "Missing 'pipeline' field" in response.json()["detail"]


class TestWriteFileEndpoint:
    """Test file upload endpoint with various scenarios"""

    def test_simulation_mode_off_returns_403(self, client):
        """Test that file upload is forbidden when simulation mode is off"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "false"}):
            body = {
                "filename": "test.txt",
                "content": base64.b64encode(b"test content").decode(),
            }

            response = client.post("/_logstash/write-file", json=body)
            assert response.status_code == 403
            assert "simulation mode" in response.json()["detail"].lower()

    def test_missing_filename_returns_400(self, client):
        """Test that missing filename returns 400"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "true"}):
            body = {
                "content": base64.b64encode(b"test content").decode(),
            }

            response = client.post("/_logstash/write-file", json=body)
            assert response.status_code == 400
            assert "required" in response.json()["detail"].lower()

    def test_missing_content_returns_400(self, client):
        """Test that missing content returns 400"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "true"}):
            body = {
                "filename": "test.txt",
            }

            response = client.post("/_logstash/write-file", json=body)
            assert response.status_code == 400
            assert "required" in response.json()["detail"].lower()

    def test_path_traversal_sanitized(self, client, temp_dir):
        """Test that path traversal attempts are sanitized"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "true"}):
            os.path.join(temp_dir, "uploaded")

            with patch("os.makedirs"), patch("builtins.open", mock_open()) as mock_file:
                body = {
                    "filename": "../../../etc/passwd",
                    "content": base64.b64encode(b"malicious content").decode(),
                }

                response = client.post("/_logstash/write-file", json=body)
                assert response.status_code == 200

                call_args = mock_file.call_args[0][0]
                assert "etc" not in call_args
                assert call_args.endswith("passwd")

    def test_valid_upload(self, client, temp_dir):
        """Test successful file upload"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "true"}):
            uploaded_dir = os.path.join(temp_dir, "uploaded")
            os.makedirs(uploaded_dir, exist_ok=True)

            with patch("os.makedirs"), patch(
                "os.path.join", return_value=os.path.join(uploaded_dir, "test.json")
            ):
                test_content = b'{"key": "value"}'
                body = {
                    "filename": "test.json",
                    "content": base64.b64encode(test_content).decode(),
                }

                response = client.post("/_logstash/write-file", json=body)
                assert response.status_code == 200

                result = response.json()
                assert result["status"] == "success"
                assert "test.json" in result["path"]


class TestPipelineIdSanitization:
    """Test pipeline_id validation and sanitization"""

    def test_valid_pipeline_ids_accepted(self, client, mock_dirs):
        """Test that valid pipeline IDs are accepted"""
        valid_ids = [
            "test-pipeline",
            "test_pipeline",
            "test123",
            "TEST-PIPELINE",
            "pipeline.v1",
            "my-pipeline_v2.0",
        ]

        for pipeline_id in valid_ids:
            body = {
                "pipeline": "input { stdin {} } output { stdout {} }",
            }

            response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=body)
            assert response.status_code == 200, f"Valid ID '{pipeline_id}' was rejected"

    def test_invalid_pipeline_ids_rejected(self, client, mock_dirs):
        """Test that invalid pipeline IDs are rejected"""
        invalid_ids = [
            "test pipeline",
            "test;pipeline",
            "test|pipeline",
            "test&pipeline",
            ".hidden",
            "-invalid",
            "test..pipeline",
        ]

        for pipeline_id in invalid_ids:
            body = {
                "pipeline": "input { stdin {} } output { stdout {} }",
            }

            response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=body)
            assert response.status_code == 400, f"Invalid ID '{pipeline_id}' was accepted"
            assert "Invalid pipeline_id" in response.json()["detail"]

    def test_path_traversal_blocked_in_get(self, client, mock_dirs):
        """Test path traversal is blocked in GET endpoint"""
        response = client.get("/_logstash/pipeline/test..traversal")
        assert response.status_code == 400
        assert "Invalid pipeline_id" in response.json()["detail"]

    def test_path_traversal_blocked_in_delete(self, client, mock_dirs):
        """Test path traversal is blocked in DELETE endpoint"""
        response = client.delete("/_logstash/pipeline/test..traversal")
        assert response.status_code == 400
        assert "Invalid pipeline_id" in response.json()["detail"]

    def test_path_traversal_blocked_in_logs(self, client, mock_dirs):
        """Test path traversal is blocked in logs endpoint"""
        response = client.get("/_logstash/pipeline/test..traversal/logs")
        assert response.status_code == 400
        assert "Invalid pipeline_id" in response.json()["detail"]

    def test_double_dot_sequences_rejected(self, client, mock_dirs):
        """Test that .. sequences are explicitly rejected"""
        body = {
            "pipeline": "input { stdin {} } output { stdout {} }",
        }

        response = client.put("/_logstash/pipeline/test..pipeline", json=body)
        assert response.status_code == 400
        assert ".." in response.json()["detail"]

    def test_alphanumeric_with_allowed_chars(self, client, mock_dirs):
        """Test that alphanumeric with hyphens, underscores, and dots work"""
        pipeline_id = "valid-pipeline_name.v1"
        body = {
            "pipeline": "input { stdin {} } output { stdout {} }",
        }

        response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=body)
        assert response.status_code == 200


class TestMainEdgeCases:
    """Edge cases for main HTTP surface (list pipelines)."""

    def test_list_pipelines_empty(self, client, mock_dirs):
        """Test listing pipelines when none exist"""
        response = client.get("/_logstash/pipeline")
        assert response.status_code == 200
        assert response.json() == {}

    def test_list_pipelines_with_data(self, client, mock_dirs):
        """Test listing multiple pipelines"""
        for i in range(2):
            body = {
                "pipeline": "input { stdin {} } output { stdout {} }",
                "description": f"Pipeline {i}",
            }
            client.put(f"/_logstash/pipeline/test-pipeline-{i}", json=body)

        response = client.get("/_logstash/pipeline")
        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        assert "test-pipeline-0" in data
        assert "test-pipeline-1" in data
