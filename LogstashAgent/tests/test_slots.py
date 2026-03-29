#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for logstashagent.slots."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from logstashagent import slots


@pytest.fixture(autouse=True)
def clear_slots():
    slots.clear_all_slots()
    yield
    slots.clear_all_slots()


def _pipelines(filter_config: str, index: int = 1, output_config: str = "ignored-output"):
    return [{"filter_config": filter_config, "index": index, "output_config": output_config}]


class TestPipelineHash:
    def test_hash_ignores_output_config(self):
        p1 = _pipelines("filter { mutate { add_tag => ['a'] } }", output_config="stdout {}")
        p2 = _pipelines("filter { mutate { add_tag => ['a'] } }", output_config="null {}")
        assert slots._compute_pipeline_hash(p1) == slots._compute_pipeline_hash(p2)

    def test_hash_changes_with_filter_config_or_index(self):
        base = _pipelines("filter { mutate { add_tag => ['a'] } }", index=1)
        changed_filter = _pipelines("filter { mutate { add_tag => ['b'] } }", index=1)
        changed_index = _pipelines("filter { mutate { add_tag => ['a'] } }", index=2)
        assert slots._compute_pipeline_hash(base) != slots._compute_pipeline_hash(changed_filter)
        assert slots._compute_pipeline_hash(base) != slots._compute_pipeline_hash(changed_index)


class TestAllocateSlot:
    def test_allocates_new_slot(self):
        slot_id = slots.allocate_slot("pipeline-a", _pipelines("filter { drop {} }"))
        state = slots.get_slot_state()
        assert slot_id == 1
        assert state[slot_id]["pipeline_name"] == "pipeline-a"

    def test_reuses_slot_for_same_hash_and_keeps_created_at(self):
        pipelines = _pipelines("filter { drop {} }")
        slot_1 = slots.allocate_slot("pipeline-a", pipelines)
        created_at_1 = slots.get_slot_state()[slot_1]["created_at"]
        last_accessed_1 = slots.get_slot_state()[slot_1]["last_accessed"]

        slot_2 = slots.allocate_slot("pipeline-b", pipelines)
        state = slots.get_slot_state()[slot_2]

        assert slot_1 == slot_2
        assert state["created_at"] == created_at_1
        assert state["last_accessed"] >= last_accessed_1
        assert len(slots.get_slot_state()) == 1

    def test_different_hash_gets_different_slot(self):
        slot_1 = slots.allocate_slot("pipeline-a", _pipelines("filter { drop {} }"))
        slot_2 = slots.allocate_slot("pipeline-b", _pipelines("filter { mutate { add_tag => ['x'] } }"))
        assert slot_1 != slot_2
        assert len(slots.get_slot_state()) == 2

    def test_evicts_oldest_slot_when_full_and_cleans_old_slot(self):
        first_slot = None
        for i in range(slots.NUM_SLOTS):
            slot_id = slots.allocate_slot(f"pipeline-{i}", _pipelines(f"filter {{ mutate {{ add_tag => ['{i}'] }} }}"))
            if i == 0:
                first_slot = slot_id

        old_snapshot = slots.get_slot_state()[first_slot].copy()
        with patch.object(slots, "_delete_slot_pipelines") as cleanup:
            new_slot = slots.allocate_slot("new-pipeline", _pipelines("filter { json {} }"))

        assert new_slot == first_slot
        cleanup.assert_called_once_with(first_slot, old_snapshot)
        assert len(slots.get_slot_state()) == slots.NUM_SLOTS
        assert slots.get_slot_state()[new_slot]["pipeline_name"] == "new-pipeline"


class TestSlotLifecycle:
    def test_release_slot(self):
        slot_id = slots.allocate_slot("pipeline-a", _pipelines("filter { drop {} }"))
        assert slots.release_slot(slot_id) is True
        assert slots.release_slot(slot_id) is False
        assert slot_id not in slots.get_slot_state()


class TestEvictExpiredSlots:
    def test_evicts_old_and_invalid_slots(self):
        old_slot = slots.allocate_slot("old", _pipelines("filter { drop {} }"))
        bad_ts_slot = slots.allocate_slot("bad-ts", _pipelines("filter { json {} }"))
        active_slot = slots.allocate_slot("active", _pipelines("filter { mutate { add_tag => ['ok'] } }"))

        old_time = datetime.now(timezone.utc) - timedelta(seconds=slots.SLOT_TTL_SECONDS + 10)
        with slots._slots_lock:
            slots._slots[old_slot]["last_accessed"] = old_time.isoformat()
            slots._slots[bad_ts_slot]["last_accessed"] = "not-a-timestamp"

        with patch.object(slots, "_delete_slot_pipelines") as cleanup:
            evicted = slots.evict_expired_slots()

        assert set(evicted) == {old_slot, bad_ts_slot}
        assert active_slot in slots.get_slot_state()
        assert cleanup.call_count == 2

    def test_does_not_evict_recent_slot(self):
        slots.allocate_slot("recent", _pipelines("filter { drop {} }"))
        with patch.object(slots, "_delete_slot_pipelines") as cleanup:
            evicted = slots.evict_expired_slots()
        assert evicted == []
        cleanup.assert_not_called()


class TestEvictFailedSlots:
    def _age_slot(self, slot_id: int, age_seconds: int = 60):
        ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        with slots._slots_lock:
            slots._slots[slot_id]["created_at"] = ts.isoformat()

    def test_does_not_evict_new_slot_before_min_age(self):
        slot_id = slots.allocate_slot("new-slot", _pipelines("filter { drop {} }"))

        mock_api = MagicMock()
        mock_api.__enter__.return_value = mock_api
        mock_api.__exit__.return_value = False
        mock_api.list_pipelines.return_value = []

        with patch("logstashagent.slots.LogstashAPI", return_value=mock_api):
            evicted = slots.evict_failed_slots()

        assert evicted == []
        assert slot_id in slots.get_slot_state()

    def test_evicts_when_pipeline_missing_after_min_age(self):
        slot_id = slots.allocate_slot("missing", _pipelines("filter { drop {} }"))
        self._age_slot(slot_id)

        mock_api = MagicMock()
        mock_api.__enter__.return_value = mock_api
        mock_api.__exit__.return_value = False
        mock_api.list_pipelines.return_value = []

        with patch("logstashagent.slots.LogstashAPI", return_value=mock_api):
            with patch.object(slots, "_delete_slot_pipelines") as cleanup:
                evicted = slots.evict_failed_slots()

        assert evicted == [slot_id]
        cleanup.assert_called_once()
        assert len(slots.get_slot_state()) == 0

    def test_evicts_when_pipeline_state_failed(self):
        slot_id = slots.allocate_slot("failed", _pipelines("filter { drop {} }"))
        self._age_slot(slot_id)

        pipeline_name = f"slot{slot_id}-filter1"
        mock_api = MagicMock()
        mock_api.__enter__.return_value = mock_api
        mock_api.__exit__.return_value = False
        mock_api.list_pipelines.return_value = [pipeline_name]
        mock_api.detect_pipeline_state.return_value = "failed"

        with patch("logstashagent.slots.LogstashAPI", return_value=mock_api):
            with patch.object(slots, "_delete_slot_pipelines"):
                evicted = slots.evict_failed_slots()

        assert evicted == [slot_id]
        assert len(slots.get_slot_state()) == 0

    def test_falls_back_when_api_raises(self):
        with patch("logstashagent.slots.LogstashAPI", side_effect=Exception("api down")):
            with patch("logstashagent.slots._evict_failed_slots_fallback", return_value=[2]) as fallback:
                assert slots.evict_failed_slots() == [2]
                fallback.assert_called_once()


class TestVerifySlotPipelinesLoaded:
    def test_returns_true_when_running(self):
        mock_api = MagicMock()
        mock_api.__enter__.return_value = mock_api
        mock_api.__exit__.return_value = False
        mock_api.get_pipeline_stats.return_value = {
            "pipelines": {
                "slot1-filter1": {"reloads": {"failures": 0, "successes": 1}}
            }
        }
        mock_api.detect_pipeline_state.return_value = "running"

        with patch("logstashagent.slots.LogstashAPI", return_value=mock_api):
            result = asyncio.run(
                slots.verify_slot_pipelines_loaded(
                    slot_id=1, expected_count=1, max_wait_seconds=0.2, poll_interval=0
                )
            )

        assert result is True
        mock_api.detect_pipeline_state.assert_called_once_with("slot1-filter1")

    def test_returns_false_on_new_reload_failures(self):
        mock_api = MagicMock()
        mock_api.__enter__.return_value = mock_api
        mock_api.__exit__.return_value = False
        mock_api.get_pipeline_stats.side_effect = [
            {"pipelines": {"slot1-filter1": {"reloads": {"failures": 0, "successes": 0}}}},
            {"pipelines": {"slot1-filter1": {"reloads": {"failures": 1, "successes": 0}}}},
        ]
        mock_api.detect_pipeline_state.return_value = "not_found"

        with patch("logstashagent.slots.LogstashAPI", return_value=mock_api):
            result = asyncio.run(
                slots.verify_slot_pipelines_loaded(
                    slot_id=1, expected_count=1, max_wait_seconds=0.5, poll_interval=0
                )
            )

        assert result is False

    def test_falls_back_when_api_unavailable(self):
        with patch("logstashagent.slots.LogstashAPI", side_effect=Exception("api down")):
            with patch(
                "logstashagent.slots._verify_slot_pipelines_loaded_fallback",
                return_value=True,
            ) as fallback:
                result = asyncio.run(
                    slots.verify_slot_pipelines_loaded(
                        slot_id=3, expected_count=2, max_wait_seconds=0.1, poll_interval=0
                    )
                )

        assert result is True
        fallback.assert_called_once_with(3, 2)
