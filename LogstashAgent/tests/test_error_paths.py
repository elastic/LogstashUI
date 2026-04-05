#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Error path and edge case tests for LogstashAgent."""

import json
import os
import shutil
import tempfile
import threading
import time
from unittest.mock import patch, MagicMock, mock_open

import pytest
import yaml

from logstashagent import main, slots, logstash_supervisor, agent_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pipelines(fc, index=1):
    return [{"filter_config": fc, "index": index}]


@pytest.fixture(autouse=True)
def _clear_slots():
    slots.clear_all_slots()
    yield
    slots.clear_all_slots()


# ---------------------------------------------------------------------------
# TestFileSystemErrors
# ---------------------------------------------------------------------------

class TestFileSystemErrors:
    """File system error handling."""

    def test_load_pipelines_yml_corrupt_yaml(self, temp_dir):
        yml = os.path.join(temp_dir, "pipelines.yml")
        with open(yml, "w") as f:
            f.write("invalid: yaml: [\n")
        with patch.object(main, "PIPELINES_YML_PATH", yml):
            assert main._load_pipelines_yml() == []

    def test_load_pipelines_yml_nonexistent(self, temp_dir):
        yml = os.path.join(temp_dir, "nonexistent.yml")
        with patch.object(main, "PIPELINES_YML_PATH", yml):
            assert main._load_pipelines_yml() == []

    def test_save_pipelines_yml_atomic_cleanup(self, temp_dir):
        yml = os.path.join(temp_dir, "pipelines.yml")
        tmp = yml + ".tmp"
        with patch.object(main, "PIPELINES_YML_PATH", yml):
            with patch("os.replace", side_effect=OSError("disk full")):
                with pytest.raises(OSError):
                    main._save_pipelines_yml([{"pipeline.id": "t"}])
        assert not os.path.exists(tmp)

    def test_save_pipeline_metadata_atomic(self, temp_dir):
        md_dir = os.path.join(temp_dir, "metadata")
        os.makedirs(md_dir, exist_ok=True)
        with patch.object(main, "METADATA_DIR", md_dir):
            main._save_pipeline_metadata("test-pipe", {
                "description": "d", "last_modified": "now"
            })
            path = os.path.join(md_dir, "test-pipe.json")
            assert os.path.exists(path)
            assert not os.path.exists(path + ".tmp")

    def test_save_pipeline_metadata_failure_cleanup(self, temp_dir):
        md_dir = os.path.join(temp_dir, "metadata")
        os.makedirs(md_dir, exist_ok=True)
        with patch.object(main, "METADATA_DIR", md_dir):
            with patch("os.replace", side_effect=OSError("fail")):
                with pytest.raises(OSError):
                    main._save_pipeline_metadata("test-pipe", {"d": 1})
        tmp = os.path.join(md_dir, "test-pipe.json.tmp")
        assert not os.path.exists(tmp)

    def test_delete_pipeline_internal_missing(self, temp_dir):
        yml = os.path.join(temp_dir, "pipelines.yml")
        with open(yml, "w") as f:
            yaml.dump([], f)
        with patch.object(main, "PIPELINES_YML_PATH", yml):
            assert main.delete_pipeline_internal("nonexistent") is False

    def test_load_pipeline_metadata_corrupt(self, temp_dir):
        md_dir = os.path.join(temp_dir, "metadata")
        os.makedirs(md_dir, exist_ok=True)
        md_path = os.path.join(md_dir, "bad.json")
        with open(md_path, "w") as f:
            f.write("{corrupt json")
        with patch.object(main, "METADATA_DIR", md_dir):
            result = main._load_pipeline_metadata("bad")
        assert "description" in result  # Falls back to defaults


# ---------------------------------------------------------------------------
# TestConcurrentOperations
# ---------------------------------------------------------------------------

class TestConcurrentOperations:
    """Thread safety and concurrent access tests."""

    def test_concurrent_slot_allocations(self):
        results = []
        errors = []

        def worker(i):
            try:
                sid = slots.allocate_slot(
                    f"p{i}",
                    _pipelines(f"filter {{ x{i} }}")
                )
                results.append(sid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(slots.NUM_SLOTS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert len(set(results)) == slots.NUM_SLOTS

    def test_concurrent_slot_release(self):
        sids = []
        for i in range(4):
            sids.append(
                slots.allocate_slot(f"p{i}", _pipelines(f"filter {{ {i} }}"))
            )

        results = []
        def release(sid):
            results.append(slots.release_slot(sid))

        threads = [threading.Thread(target=release, args=(s,)) for s in sids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert all(results)
        assert len(slots.get_slot_state()) == 0

    def test_concurrent_get_slot_state(self):
        """Reading slot state concurrently is safe."""
        for i in range(3):
            slots.allocate_slot(f"p{i}", _pipelines(f"filter {{ {i} }}"))

        results = []
        def reader():
            results.append(len(slots.get_slot_state()))

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert all(r == 3 for r in results)


# ---------------------------------------------------------------------------
# TestConfigEdgeCases
# ---------------------------------------------------------------------------

class TestConfigEdgeCases:
    """Configuration edge case handling."""

    def test_path_normalization_forward_slash(self):
        sup = logstash_supervisor.LogstashSupervisor(
            config={"logstash_settings": "/etc/logstash"}
        )
        assert sup.logstash_settings == "/etc/logstash/"

    def test_empty_config(self):
        sup = logstash_supervisor.LogstashSupervisor(config={})
        assert sup.simulation_mode_type == "embedded"
        assert sup.logstash_binary == "/usr/share/logstash/bin/logstash"

    def test_none_config(self):
        sup = logstash_supervisor.LogstashSupervisor(config=None)
        assert sup.simulation_mode_type == "embedded"

    def test_save_pipelines_preserves_static(self, temp_dir):
        yml = os.path.join(temp_dir, "pipelines.yml")
        with patch.object(main, "PIPELINES_YML_PATH", yml):
            main._save_pipelines_yml([
                {"pipeline.id": "dynamic-1",
                 "path.config": "/x.conf"}
            ])
            with open(yml) as f:
                data = yaml.safe_load(f)
        ids = [p["pipeline.id"] for p in data]
        assert ids[:2] == ["simulate-start", "simulate-end"]
        assert "dynamic-1" in ids

    def test_load_empty_yml(self, temp_dir):
        yml = os.path.join(temp_dir, "pipelines.yml")
        with open(yml, "w") as f:
            f.write("")
        with patch.object(main, "PIPELINES_YML_PATH", yml):
            assert main._load_pipelines_yml() == []

    def test_load_comment_only_yml(self, temp_dir):
        yml = os.path.join(temp_dir, "pipelines.yml")
        with open(yml, "w") as f:
            f.write("# only comments\n# more\n")
        with patch.object(main, "PIPELINES_YML_PATH", yml):
            assert main._load_pipelines_yml() == []


# ---------------------------------------------------------------------------
# TestNetworkFailures
# ---------------------------------------------------------------------------

class TestNetworkFailures:
    """Network error simulation."""

    def test_simulate_forward_failure_triggers_restart(
        self, client, reset_supervisor_global
    ):
        """All retries exhausted triggers restart and queues request."""
        sup = logstash_supervisor.LogstashSupervisor()
        sup.is_healthy = True
        logstash_supervisor._supervisor = sup

        import requests as req_lib
        with patch("logstashagent.main.requests.post",
                   side_effect=req_lib.exceptions.Timeout("timeout")), \
             patch.object(logstash_supervisor, "trigger_restart") as mr:
            resp = client.post("/_logstash/simulate",
                               json={"slot": 1, "run_id": "r1"})
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        mr.assert_called_once()

    def test_simulate_connection_error(self, client, reset_supervisor_global):
        """Connection errors are retried and eventually handled."""
        sup = logstash_supervisor.LogstashSupervisor()
        sup.is_healthy = True
        logstash_supervisor._supervisor = sup

        import requests as req_lib
        with patch("logstashagent.main.requests.post",
                   side_effect=req_lib.exceptions.ConnectionError("refused")), \
             patch.object(logstash_supervisor, "trigger_restart"):
            resp = client.post("/_logstash/simulate",
                               json={"slot": 1, "run_id": "r1"})
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# TestSupervisorErrorRecovery
# ---------------------------------------------------------------------------

class TestSupervisorErrorRecovery:
    """Supervisor error recovery scenarios."""

    @patch("logstashagent.logstash_supervisor.time.sleep")
    def test_restart_during_active_monitoring(self, _sleep,
                                               supervisor_instance):
        """Restart during monitoring loop doesn't deadlock."""
        with patch.object(supervisor_instance, "stop_logstash"), \
             patch.object(supervisor_instance, "start_logstash"), \
             patch("logstashagent.slots") as ms:
            ms.evict_all_slots_and_cleanup.return_value = []
            supervisor_instance.restart_logstash("test")
        assert supervisor_instance.restart_count == 1
        assert supervisor_instance.is_restarting is False

    def test_supervisor_multiple_restarts(self, supervisor_instance):
        """Multiple restarts increment counter correctly."""
        for i in range(5):
            with patch.object(supervisor_instance, "stop_logstash"), \
                 patch.object(supervisor_instance, "start_logstash"), \
                 patch("logstashagent.logstash_supervisor.time.sleep"), \
                 patch("logstashagent.slots") as ms:
                ms.evict_all_slots_and_cleanup.return_value = []
                supervisor_instance.restart_logstash(f"test-{i}")
        assert supervisor_instance.restart_count == 5
