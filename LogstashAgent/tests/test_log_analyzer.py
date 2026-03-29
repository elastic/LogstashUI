#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for logstashagent.log_analyzer."""

import json
from unittest.mock import patch

from logstashagent import log_analyzer


def _line(obj: dict) -> str:
    return json.dumps(obj) + "\n"


class TestReadJsonLogs:
    """Tests for _read_json_logs using a temporary log directory."""

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert (
            log_analyzer._read_json_logs(log_dir=str(tmp_path), max_lines=10) == []
        )

    def test_reads_ndjson_lines_sequential(self, tmp_path):
        f = tmp_path / "logstash-json.log"
        f.write_text(
            _line({"a": 1})
            + "not json\n"
            + _line({"b": 2}),
            encoding="utf-8",
        )

        out = log_analyzer._read_json_logs(
            log_dir=str(tmp_path),
            pattern="logstash-json*.log",
            max_lines=None,
            reverse=False,
        )

        assert out == [{"a": 1}, {"b": 2}]

    def test_respects_max_lines_sequential(self, tmp_path):
        f = tmp_path / "logstash-json.log"
        f.write_text(
            "".join(_line({"n": i}) for i in range(5)),
            encoding="utf-8",
        )

        out = log_analyzer._read_json_logs(
            log_dir=str(tmp_path),
            pattern="logstash-json*.log",
            max_lines=2,
            reverse=False,
        )

        assert len(out) == 2
        assert out[0] == {"n": 0}
        assert out[1] == {"n": 1}

    def test_reverse_with_max_lines_reads_recent_first(self, tmp_path):
        f = tmp_path / "logstash-json.log"
        f.write_text(
            "".join(_line({"idx": i, "timeMillis": 1000 + i}) for i in range(5)),
            encoding="utf-8",
        )

        out = log_analyzer._read_json_logs(
            log_dir=str(tmp_path),
            pattern="logstash-json*.log",
            max_lines=3,
            reverse=True,
        )

        assert len(out) == 3
        # Newest lines last in file; reversed tail should surface highest idx first
        assert out[0]["idx"] >= out[-1]["idx"]

    def test_globs_multiple_files(self, tmp_path):
        (tmp_path / "logstash-json.log").write_text(_line({"file": 1}), encoding="utf-8")
        (tmp_path / "logstash-json-2.log").write_text(
            _line({"file": 2}), encoding="utf-8"
        )

        out = log_analyzer._read_json_logs(
            log_dir=str(tmp_path),
            pattern="logstash-json*.log",
            max_lines=None,
            reverse=False,
        )

        assert len(out) == 2


class TestGetRunningPipelines:
    def test_returns_none_when_no_status_entries(self):
        with patch.object(log_analyzer, "_read_json_logs", return_value=[{"x": 1}]):
            assert log_analyzer.get_running_pipelines(log_dir="/tmp") is None

    def test_picks_latest_by_timestamp(self):
        logs = [
            {
                "timeMillis": 100,
                "logEvent": {
                    "running_pipelines": ["old"],
                    "non_running_pipelines": [],
                    "count": 1,
                },
            },
            {
                "timeMillis": 200,
                "level": "INFO",
                "logEvent": {
                    "running_pipelines": ["new"],
                    "non_running_pipelines": [],
                    "count": 1,
                    "message": "status",
                },
            },
        ]
        with patch.object(log_analyzer, "_read_json_logs", return_value=logs):
            out = log_analyzer.get_running_pipelines(log_dir="/tmp")

        assert out is not None
        assert out["timestamp"] == 200
        assert out["running_pipelines"] == ["new"]
        assert out["count"] == 1
        assert "raw_event" not in out

    def test_removes_running_pipelines_with_failed_action(self):
        ts = 500
        logs = [
            {
                "timeMillis": ts,
                "level": "INFO",
                "logEvent": {
                    "running_pipelines": ["good", "bad"],
                    "non_running_pipelines": [],
                    "count": 2,
                },
            },
            {
                "timeMillis": ts + 10,
                "level": "ERROR",
                "logEvent": {
                    "action_type": "FailedAction",
                    "id": "bad",
                },
            },
        ]
        with patch.object(log_analyzer, "_read_json_logs", return_value=logs):
            out = log_analyzer.get_running_pipelines(log_dir="/tmp")

        assert out["running_pipelines"] == ["good"]


class TestIsPipelineRunning:
    def test_true_when_in_running_list(self):
        with patch.object(
            log_analyzer,
            "get_running_pipelines",
            return_value={"running_pipelines": ["a", "b"]},
        ):
            assert log_analyzer.is_pipeline_running("b") is True

    def test_false_when_status_missing(self):
        with patch.object(log_analyzer, "get_running_pipelines", return_value=None):
            assert log_analyzer.is_pipeline_running("x") is False

    def test_false_when_not_in_list(self):
        with patch.object(
            log_analyzer,
            "get_running_pipelines",
            return_value={"running_pipelines": ["a"]},
        ):
            assert log_analyzer.is_pipeline_running("z") is False


class TestFindRelatedLogs:
    """Test log analysis with mocked log data"""

    def test_find_logs_for_pipeline(self):
        """Test finding logs related to a specific pipeline"""
        mock_logs = [
            {
                "level": "ERROR",
                "pipeline.id": "test-pipeline",
                "logEvent": {
                    "message": "Pipeline error occurred",
                },
                "timeMillis": 1704110400000,
            },
            {
                "level": "WARN",
                "pipeline.id": "test-pipeline",
                "logEvent": {
                    "message": "Pipeline warning",
                },
                "timeMillis": 1704110460000,
            },
            {
                "level": "INFO",
                "pipeline.id": "other-pipeline",
                "logEvent": {
                    "message": "Other pipeline info",
                },
                "timeMillis": 1704110520000,
            },
        ]

        with patch.object(log_analyzer, "_read_json_logs", return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="WARN",
            )

        assert len(logs) == 2
        assert all(log["pipeline.id"] == "test-pipeline" for log in logs)

    def test_match_by_thread_name(self):
        mock_logs = [
            {
                "level": "ERROR",
                "thread": "[slot1-filter1]>worker0",
                "timeMillis": 1,
            }
        ]
        with patch.object(log_analyzer, "_read_json_logs", return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                "slot1-filter1",
                max_entries=10,
                min_level="WARN",
            )
        assert len(logs) == 1

    def test_match_by_snapshot_reference(self):
        mock_logs = [
            {
                "level": "ERROR",
                "timeMillis": 1,
                "logEvent": {
                    "event": {
                        "snapshots": {"s1": "pipeline slot2-filter99 state"},
                    }
                },
            }
        ]
        with patch.object(log_analyzer, "_read_json_logs", return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                "slot2-filter99",
                max_entries=10,
                min_level="WARN",
            )
        assert len(logs) == 1

    def test_find_logs_with_min_level_filter(self):
        """Test log filtering by minimum level"""
        mock_logs = [
            {
                "level": "ERROR",
                "pipeline.id": "test-pipeline",
                "timeMillis": 1704110400000,
            },
            {
                "level": "WARN",
                "pipeline.id": "test-pipeline",
                "timeMillis": 1704110460000,
            },
            {
                "level": "INFO",
                "pipeline.id": "test-pipeline",
                "timeMillis": 1704110520000,
            },
            {
                "level": "DEBUG",
                "pipeline.id": "test-pipeline",
                "timeMillis": 1704110580000,
            },
        ]

        with patch.object(log_analyzer, "_read_json_logs", return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="ERROR",
            )

        assert len(logs) == 1
        assert logs[0]["level"] == "ERROR"

    def test_find_logs_with_timestamp_filter(self):
        """Test log filtering by minimum timestamp"""
        base_time = 1704110400000
        mock_logs = [
            {"level": "ERROR", "pipeline.id": "test-pipeline", "timeMillis": base_time},
            {
                "level": "ERROR",
                "pipeline.id": "test-pipeline",
                "timeMillis": base_time + 300000,
            },
            {
                "level": "ERROR",
                "pipeline.id": "test-pipeline",
                "timeMillis": base_time + 600000,
            },
        ]

        min_timestamp = base_time + 300000

        with patch.object(log_analyzer, "_read_json_logs", return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="DEBUG",
                min_timestamp=min_timestamp,
            )

        assert len(logs) == 2

    def test_find_logs_max_entries_limit(self):
        """Test that max_entries limit is respected"""
        mock_logs = [
            {
                "level": "ERROR",
                "pipeline.id": "test-pipeline",
                "timeMillis": 1704110400000 + (i * 1000),
            }
            for i in range(100)
        ]

        with patch.object(log_analyzer, "_read_json_logs", return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="DEBUG",
            )

        assert len(logs) == 10

    def test_find_logs_no_matches(self):
        """Test when no logs match the criteria"""
        mock_logs = [
            {
                "level": "INFO",
                "pipeline.id": "other-pipeline",
                "timeMillis": 1704110400000,
            }
        ]

        with patch.object(log_analyzer, "_read_json_logs", return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="WARN",
            )

        assert len(logs) == 0
