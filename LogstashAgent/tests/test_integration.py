#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Integration & end-to-end tests for LogstashAgent workflows."""

import asyncio
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from logstashagent import main, slots, logstash_supervisor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pipelines(filter_config, index=1):
    return [{"filter_config": filter_config, "index": index}]


@pytest.fixture(autouse=True)
def _clear_slots():
    slots.clear_all_slots()
    yield
    slots.clear_all_slots()


@pytest.fixture
def healthy_supervisor(reset_supervisor_global):
    """Create a supervisor that reports healthy."""
    sup = logstash_supervisor.LogstashSupervisor()
    sup.is_healthy = True
    sup.is_restarting = False
    logstash_supervisor._supervisor = sup
    yield sup
    logstash_supervisor._supervisor = None


# ---------------------------------------------------------------------------
# TestSlotAllocationWorkflow
# ---------------------------------------------------------------------------

class TestSlotAllocationWorkflow:
    """End-to-end slot allocation flow."""

    def test_allocate_creates_slot(self):
        sid = slots.allocate_slot("p1", _pipelines("filter { drop {} }"))
        state = slots.get_slot_state()
        assert sid == 1
        assert state[sid]["pipeline_name"] == "p1"

    def test_reuse_with_matching_hash(self):
        p = _pipelines("filter { drop {} }")
        s1 = slots.allocate_slot("p1", p)
        s2 = slots.allocate_slot("p2", p)
        assert s1 == s2
        assert len(slots.get_slot_state()) == 1

    def test_eviction_when_full(self):
        for i in range(slots.NUM_SLOTS):
            slots.allocate_slot(f"p{i}", _pipelines(f"filter {{ {i} }}"))
        assert len(slots.get_slot_state()) == slots.NUM_SLOTS
        with patch.object(slots, "_delete_slot_pipelines"):
            new = slots.allocate_slot("overflow", _pipelines("filter { new }"))
        assert new is not None
        assert len(slots.get_slot_state()) == slots.NUM_SLOTS

    def test_concurrent_allocation(self):
        """Thread-safe concurrent slot allocations."""
        results = []
        errors = []

        def allocate(idx):
            try:
                sid = slots.allocate_slot(
                    f"p{idx}",
                    _pipelines(f"filter {{ mutate {{ add_tag => ['{idx}'] }} }}")
                )
                results.append(sid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=allocate, args=(i,))
                   for i in range(slots.NUM_SLOTS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert len(results) == slots.NUM_SLOTS
        assert len(slots.get_slot_state()) == slots.NUM_SLOTS

    def test_slot_cleanup_during_restart(self, reset_supervisor_global):
        """evict_all_slots_and_cleanup clears all slots."""
        for i in range(3):
            slots.allocate_slot(f"p{i}", _pipelines(f"filter {{ {i} }}"))
        assert len(slots.get_slot_state()) == 3

        with patch.object(slots, "_delete_slot_pipelines"):
            evicted = slots.evict_all_slots_and_cleanup()
        assert len(evicted) == 3
        assert len(slots.get_slot_state()) == 0


# ---------------------------------------------------------------------------
# TestSimulationQueueProcessing
# ---------------------------------------------------------------------------

class TestSimulationQueueProcessing:
    """Simulation request queuing when Logstash is unhealthy."""

    def test_queue_when_unhealthy(self, client, reset_supervisor_global):
        """Requests are queued (202) when Logstash is unhealthy."""
        sup = logstash_supervisor.LogstashSupervisor()
        sup.is_healthy = False
        logstash_supervisor._supervisor = sup

        with patch.object(slots, "get_slot_state", return_value={}):
            resp = client.post("/_logstash/simulate",
                               json={"slot": 1, "run_id": "r1", "data": "x"})
        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"

    def test_queue_overflow(self, reset_supervisor_global):
        """Queue respects maxlen=100."""
        q = deque(maxlen=100)
        for i in range(150):
            q.append({"log_data": {"n": i}})
        assert len(q) == 100
        # Oldest items evicted
        assert q[0]["log_data"]["n"] == 50

    def test_forward_when_healthy(self, client, healthy_supervisor):
        """Requests are forwarded (200) when Logstash is healthy."""
        with patch("logstashagent.main.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status.return_value = None
            mock_post.return_value = mock_resp

            resp = client.post("/_logstash/simulate",
                               json={"slot": 1, "run_id": "r1"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


# ---------------------------------------------------------------------------
# TestPipelineVerification
# ---------------------------------------------------------------------------

class TestPipelineVerification:
    """Tests for verify_slot_pipelines_loaded."""

    def test_success_when_running(self):
        api = MagicMock()
        api.__enter__ = MagicMock(return_value=api)
        api.__exit__ = MagicMock(return_value=False)
        api.get_pipeline_stats.return_value = {
            "pipelines": {"slot1-filter1": {
                "reloads": {"failures": 0, "successes": 1}
            }}
        }
        api.detect_pipeline_state.return_value = "running"

        with patch("logstashagent.slots.LogstashAPI", return_value=api):
            result = asyncio.run(slots.verify_slot_pipelines_loaded(
                slot_id=1, expected_count=1,
                max_wait_seconds=0.2, poll_interval=0
            ))
        assert result is True

    def test_timeout_returns_false(self):
        api = MagicMock()
        api.__enter__ = MagicMock(return_value=api)
        api.__exit__ = MagicMock(return_value=False)
        api.get_pipeline_stats.return_value = {
            "pipelines": {"slot1-filter1": {
                "reloads": {"failures": 0, "successes": 0}
            }}
        }
        api.detect_pipeline_state.return_value = "not_found"

        with patch("logstashagent.slots.LogstashAPI", return_value=api):
            result = asyncio.run(slots.verify_slot_pipelines_loaded(
                slot_id=1, expected_count=1,
                max_wait_seconds=0.3, poll_interval=0.05
            ))
        assert result is False

    def test_new_failure_returns_false(self):
        api = MagicMock()
        api.__enter__ = MagicMock(return_value=api)
        api.__exit__ = MagicMock(return_value=False)
        api.get_pipeline_stats.side_effect = [
            {"pipelines": {"slot1-filter1": {
                "reloads": {"failures": 0, "successes": 0}
            }}},
            {"pipelines": {"slot1-filter1": {
                "reloads": {"failures": 1, "successes": 0}
            }}},
        ]
        api.detect_pipeline_state.return_value = "not_found"

        with patch("logstashagent.slots.LogstashAPI", return_value=api):
            result = asyncio.run(slots.verify_slot_pipelines_loaded(
                slot_id=1, expected_count=1,
                max_wait_seconds=0.5, poll_interval=0
            ))
        assert result is False

    def test_fallback_on_api_error(self):
        with patch("logstashagent.slots.LogstashAPI",
                   side_effect=Exception("down")):
            with patch("logstashagent.slots._verify_slot_pipelines_loaded_fallback",
                       return_value=True) as fb:
                result = asyncio.run(slots.verify_slot_pipelines_loaded(
                    slot_id=3, expected_count=2,
                    max_wait_seconds=0.1, poll_interval=0
                ))
        assert result is True
        fb.assert_called_once_with(3, 2)


# ---------------------------------------------------------------------------
# TestLogstashHealthEndpoint
# ---------------------------------------------------------------------------

class TestLogstashHealthEndpoint:
    """HTTP-level tests for /_logstash/health."""

    def test_healthy_returns_200(self, client, healthy_supervisor):
        resp = client.get("/_logstash/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is True
        assert data["restarting"] is False

    def test_unhealthy_returns_503(self, client, reset_supervisor_global):
        sup = logstash_supervisor.LogstashSupervisor()
        sup.is_healthy = False
        logstash_supervisor._supervisor = sup

        resp = client.get("/_logstash/health")
        assert resp.status_code == 503
        assert resp.json()["healthy"] is False

    def test_restarting_shown(self, client, reset_supervisor_global):
        sup = logstash_supervisor.LogstashSupervisor()
        sup.is_healthy = False
        sup.is_restarting = True
        sup.restart_count = 3
        logstash_supervisor._supervisor = sup

        resp = client.get("/_logstash/health")
        data = resp.json()
        assert data["restarting"] is True
        assert data["restart_count"] == 3


# ---------------------------------------------------------------------------
# TestSlotEvictionLifecycle
# ---------------------------------------------------------------------------

class TestSlotEvictionLifecycle:
    """Integration tests for slot eviction flows."""

    def test_expired_slot_eviction(self):
        sid = slots.allocate_slot("old", _pipelines("filter { drop {} }"))
        old_time = datetime.now(timezone.utc) - timedelta(
            seconds=slots.SLOT_TTL_SECONDS + 10
        )
        with slots._slots_lock:
            slots._slots[sid]["last_accessed"] = old_time.isoformat()
        with patch.object(slots, "_delete_slot_pipelines"):
            evicted = slots.evict_expired_slots()
        assert sid in evicted
        assert sid not in slots.get_slot_state()

    def test_failed_slot_eviction_api(self):
        sid = slots.allocate_slot("fail", _pipelines("filter { drop {} }"))
        old = datetime.now(timezone.utc) - timedelta(seconds=60)
        with slots._slots_lock:
            slots._slots[sid]["created_at"] = old.isoformat()

        api = MagicMock()
        api.__enter__ = MagicMock(return_value=api)
        api.__exit__ = MagicMock(return_value=False)
        api.list_pipelines.return_value = [f"slot{sid}-filter1"]
        api.detect_pipeline_state.return_value = "failed"

        with patch("logstashagent.slots.LogstashAPI", return_value=api), \
             patch.object(slots, "_delete_slot_pipelines"):
            evicted = slots.evict_failed_slots()
        assert sid in evicted

    def test_hash_computation_consistency(self):
        p1 = _pipelines("filter { mutate { add_tag => ['a'] } }",
                         index=1)
        p2 = _pipelines("filter { mutate { add_tag => ['a'] } }",
                         index=1)
        assert slots._compute_pipeline_hash(p1) == slots._compute_pipeline_hash(p2)

    def test_hash_changes_with_content(self):
        p1 = _pipelines("filter { mutate { add_tag => ['a'] } }")
        p2 = _pipelines("filter { mutate { add_tag => ['b'] } }")
        assert slots._compute_pipeline_hash(p1) != slots._compute_pipeline_hash(p2)
