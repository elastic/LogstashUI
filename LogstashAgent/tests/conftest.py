#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Shared pytest fixtures for LogstashAgent tests."""

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from logstashagent import main


@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(main.app)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_pipelines_yml(temp_dir):
    """Mock pipelines.yml path"""
    yml_path = os.path.join(temp_dir, "pipelines.yml")
    with patch.object(main, "PIPELINES_YML_PATH", yml_path):
        yield yml_path


@pytest.fixture
def mock_dirs(temp_dir):
    """Mock all directory paths"""
    pipelines_dir = os.path.join(temp_dir, "conf.d")
    metadata_dir = os.path.join(temp_dir, "metadata")
    yml_path = os.path.join(temp_dir, "pipelines.yml")

    os.makedirs(pipelines_dir, exist_ok=True)
    os.makedirs(metadata_dir, exist_ok=True)

    with patch.object(main, "PIPELINES_DIR", pipelines_dir), patch.object(
        main, "METADATA_DIR", metadata_dir
    ), patch.object(main, "PIPELINES_YML_PATH", yml_path):
        yield {
            "pipelines_dir": pipelines_dir,
            "metadata_dir": metadata_dir,
            "yml_path": yml_path,
        }
