#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Shared pytest fixtures for LogstashAgent tests."""

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, PropertyMock

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from logstashagent import main
from logstashagent import logstash_supervisor


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


# ---------------------------------------------------------------------------
# Supervisor-related shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def supervisor_config_embedded():
    """Sample supervisor configuration for embedded (Docker) mode"""
    return {
        "mode": "simulation",
        "simulation_mode": "embedded",
        "logstash_binary": "/usr/share/logstash/bin/logstash",
        "logstash_settings": "/etc/logstash/",
        "logstash_log_path": "/var/log/logstash",
    }


@pytest.fixture
def supervisor_config_host(temp_dir):
    """Sample supervisor configuration for host mode"""
    binary_path = os.path.join(temp_dir, "bin", "logstash")
    settings_path = os.path.join(temp_dir, "settings")
    log_path = os.path.join(temp_dir, "logs")
    os.makedirs(os.path.dirname(binary_path), exist_ok=True)
    os.makedirs(settings_path, exist_ok=True)
    os.makedirs(log_path, exist_ok=True)
    # Create a dummy binary so FileNotFoundError isn't raised
    with open(binary_path, "w") as f:
        f.write("#!/bin/bash\n")
    return {
        "mode": "simulation",
        "simulation_mode": "host",
        "logstash_binary": binary_path,
        "logstash_settings": settings_path,
        "logstash_log_path": log_path,
    }


@pytest.fixture
def mock_logstash_process():
    """Mock subprocess.Popen for Logstash process.

    Returns a MagicMock that behaves like a running process.
    Configure poll(), returncode, pid, etc. in individual tests as needed.
    """
    proc = MagicMock()
    proc.pid = 12345
    proc.poll.return_value = None  # Process is running
    proc.returncode = None
    proc.wait.return_value = 0
    proc.communicate.return_value = (b"", b"")
    return proc


@pytest.fixture
def mock_logstash_api():
    """Mock LogstashAPI responses for health/stats.

    Returns a MagicMock configured as a context manager that provides
    default healthy API responses. Override specific return values in tests.
    """
    api = MagicMock()
    api.__enter__ = MagicMock(return_value=api)
    api.__exit__ = MagicMock(return_value=False)

    # Default: healthy Logstash with 4GB heap, 50% usage
    api.get_node_stats.return_value = {
        "jvm": {
            "mem": {
                "heap_used_in_bytes": 2 * 1024 ** 3,       # 2 GB
                "heap_max_in_bytes": 4 * 1024 ** 3,         # 4 GB
            }
        }
    }

    # Default: no pipelines running
    api.get_running_pipelines_from_health.return_value = []
    api.get_health_report.return_value = {"indicators": {"pipelines": {"indicators": {}}}}
    return api


@pytest.fixture
def reset_supervisor_global():
    """Reset the module-level _supervisor singleton before and after each test."""
    logstash_supervisor._supervisor = None
    yield
    logstash_supervisor._supervisor = None


@pytest.fixture
def supervisor_instance(supervisor_config_embedded, reset_supervisor_global):
    """Create a LogstashSupervisor with embedded config and clean global state."""
    sup = logstash_supervisor.LogstashSupervisor(config=supervisor_config_embedded)
    yield sup
    # Ensure monitoring thread is stopped
    sup.should_run = False
    if sup.monitor_thread and sup.monitor_thread.is_alive():
        sup.monitor_thread.join(timeout=2)


@pytest.fixture(autouse=True)
def reset_controller_globals():
    """Reset controller module globals to prevent test pollution."""
    from logstashagent import controller
    controller._log_watcher = None
    yield
    controller._log_watcher = None


@pytest.fixture(autouse=True)
def mock_unix_functions():
    """Mock Unix-only OS functions on Windows for cross-platform testing."""
    import sys
    import signal
    if sys.platform == 'win32':
        with patch('os.setsid', create=True), \
             patch('os.killpg', create=True), \
             patch('os.getpgid', create=True, return_value=12345), \
             patch.object(signal, 'SIGKILL', 9, create=True), \
             patch.object(signal, 'SIGTERM', 15, create=True):
            yield
    else:
        yield
