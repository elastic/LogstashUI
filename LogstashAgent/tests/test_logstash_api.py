#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for logstashagent.logstash_api."""

from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from logstashagent import logstash_api
from logstashagent.logstash_api import (
    LogstashAPI,
    LogstashAPIError,
    PipelineNotFoundError,
    get_running_pipelines,
    is_pipeline_loaded,
    wait_for_pipeline,
)


@pytest.fixture(autouse=True)
def reset_shared_http_client():
    """Avoid cross-test pollution of the module-level pooled client."""
    logstash_api._shared_client = None
    yield
    logstash_api._shared_client = None


@pytest.fixture
def mock_http():
    """Patch only ``httpx.Client`` so ``httpx.HTTPError`` in except clauses stays real."""
    client = MagicMock()
    with patch("logstashagent.logstash_api.httpx.Client", return_value=client):
        yield client


@pytest.fixture
def api(mock_http):
    return LogstashAPI(use_shared_client=False, timeout=5.0)


def _ok_json(data):
    r = Mock()
    r.status_code = 200
    r.json.return_value = data
    r.raise_for_status = Mock()
    return r


class TestLogstashAPIInitialization:
    def test_default_base_url_and_dedicated_client(self):
        mock_client = MagicMock()
        with patch(
            "logstashagent.logstash_api.httpx.Client", return_value=mock_client
        ) as ctor:
            api = LogstashAPI(use_shared_client=False, timeout=5.0)

        assert api.base_url == "http://localhost:9600"
        assert api.timeout == 5.0
        assert api._owns_client is True
        ctor.assert_called_once_with(timeout=5.0)

    def test_shared_client_uses_connection_limits(self):
        mock_client = MagicMock()
        with patch(
            "logstashagent.logstash_api.httpx.Client", return_value=mock_client
        ) as ctor:
            logstash_api._shared_client = None
            api = LogstashAPI(use_shared_client=True, timeout=7.0)

        assert api.client is mock_client
        assert api._owns_client is False
        ctor.assert_called_with(
            timeout=7.0,
            limits=httpx.Limits(
                max_connections=10, max_keepalive_connections=5
            ),
        )

    def test_context_manager_closes_owned_client(self, mock_http):
        with LogstashAPI(use_shared_client=False) as api:
            assert api._owns_client is True
        mock_http.close.assert_called_once()

    def test_close_only_when_owning_client(self, mock_http):
        api = LogstashAPI(use_shared_client=False)
        api.close()
        mock_http.close.assert_called_once()

    def test_close_skipped_for_shared_client(self):
        shared = MagicMock()
        with patch("logstashagent.logstash_api.httpx.Client", return_value=shared):
            logstash_api._shared_client = None
            api = LogstashAPI(use_shared_client=True)
            api.close()
        shared.close.assert_not_called()


class TestGetNodeAndHealth:
    def test_get_node_info(self, api, mock_http):
        mock_http.get.return_value = _ok_json({"version": "8.x"})
        assert api.get_node_info() == {"version": "8.x"}
        mock_http.get.assert_called_with("http://localhost:9600/")

    def test_get_health_report(self, api, mock_http):
        mock_http.get.return_value = _ok_json({"status": "green"})
        assert api.get_health_report() == {"status": "green"}
        mock_http.get.assert_called_with("http://localhost:9600/_node/health_report")

    def test_get_node_stats(self, api, mock_http):
        mock_http.get.return_value = _ok_json({"jvm": {}})
        assert api.get_node_stats() == {"jvm": {}}
        mock_http.get.assert_called_with("http://localhost:9600/_node/stats")


class TestGetRunningPipelinesFromHealth:
    def test_returns_indicator_keys(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "indicators": {
                    "pipelines": {
                        "indicators": {"main": {}, "beats": {}},
                    }
                }
            }
        )
        assert set(api.get_running_pipelines_from_health()) == {"main", "beats"}

    def test_fallback_on_404(self, api, mock_http):
        err = LogstashAPIError("Failed to get health report: 404 Not Found")
        with patch.object(api, "get_health_report", side_effect=err):
            with patch.object(api, "list_pipelines", return_value=["a", "b"]):
                assert api.get_running_pipelines_from_health() == ["a", "b"]


class TestGetPipelineStats:
    def test_get_all_pipeline_stats_success(self, api, mock_http):
        body = {
            "pipelines": {
                "pipeline1": {"events": {"in": 100}},
                "pipeline2": {"events": {"in": 200}},
            }
        }
        mock_http.get.return_value = _ok_json(body)

        assert api.get_all_pipeline_stats() == body
        mock_http.get.assert_called_once_with(
            "http://localhost:9600/_node/stats/pipelines"
        )

    def test_get_all_pipeline_stats_http_error(self, api, mock_http):
        mock_http.get.side_effect = httpx.HTTPError("Connection failed")

        with pytest.raises(LogstashAPIError, match="Failed to get pipeline stats"):
            api.get_all_pipeline_stats()

    def test_get_pipeline_stats_success(self, api, mock_http):
        body = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 100, "out": 95},
                    "reloads": {"successes": 1, "failures": 0},
                }
            }
        }
        mock_http.get.return_value = _ok_json(body)

        assert api.get_pipeline_stats("test-pipeline") == body
        mock_http.get.assert_called_once_with(
            "http://localhost:9600/_node/stats/pipelines/test-pipeline"
        )

    def test_get_pipeline_stats_not_found_status(self, api, mock_http):
        r = Mock()
        r.status_code = 404
        mock_http.get.return_value = r

        with pytest.raises(PipelineNotFoundError, match="nonexistent"):
            api.get_pipeline_stats("nonexistent")


class TestDetectPipelineState:
    def test_running(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {"in": 100, "out": 95},
                        "reloads": {"successes": 1, "failures": 0},
                    }
                }
            }
        )
        assert api.detect_pipeline_state("test-pipeline") == "running"

    def test_idle(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {"in": 0, "out": 0},
                        "reloads": {"successes": 1, "failures": 0},
                    }
                }
            }
        )
        assert api.detect_pipeline_state("test-pipeline") == "idle"

    def test_idle_with_historical_failures(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {"in": 0, "out": 0},
                        "reloads": {"successes": 1, "failures": 3},
                    }
                }
            }
        )
        assert api.detect_pipeline_state("test-pipeline") == "idle"

    def test_idle_only_failures_no_events_in_key_still_idle(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {"in": 0, "out": 0},
                        "reloads": {"successes": 0, "failures": 3},
                    }
                }
            }
        )
        assert api.detect_pipeline_state("test-pipeline") == "idle"

    def test_not_found_404(self, api, mock_http):
        r = Mock()
        r.status_code = 404
        mock_http.get.return_value = r
        assert api.detect_pipeline_state("nonexistent") == "not_found"

    def test_idle_empty_reloads_dict(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {"in": 0, "out": 0},
                        "reloads": {},
                    }
                }
            }
        )
        assert api.detect_pipeline_state("test-pipeline") == "idle"

    def test_api_error_returns_not_found(self, api, mock_http):
        mock_http.get.side_effect = httpx.HTTPError("down")
        assert api.detect_pipeline_state("test-pipeline") == "not_found"


class TestListPipelines:
    def test_success(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {"pipelines": {"p1": {}, "p2": {}, "p3": {}}}
        )
        names = api.list_pipelines()
        assert len(names) == 3
        assert set(names) == {"p1", "p2", "p3"}

    def test_empty(self, api, mock_http):
        mock_http.get.return_value = _ok_json({"pipelines": {}})
        assert api.list_pipelines() == []

    def test_error(self, api, mock_http):
        mock_http.get.side_effect = httpx.HTTPError("Connection failed")
        with pytest.raises(LogstashAPIError):
            api.list_pipelines()


class TestIsPipelineRunning:
    def test_true_with_events(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {"in": 100, "out": 95},
                        "reloads": {"successes": 1},
                    }
                }
            }
        )
        assert api.is_pipeline_running("test-pipeline") is True

    def test_true_with_reload_only(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {"in": 0, "out": 0},
                        "reloads": {"successes": 1},
                    }
                }
            }
        )
        assert api.is_pipeline_running("test-pipeline") is True

    def test_false_when_not_found(self, api, mock_http):
        r = Mock()
        r.status_code = 404
        mock_http.get.return_value = r
        assert api.is_pipeline_running("nonexistent") is False


class TestGetPipelineEventCounts:
    def test_success(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {
                            "in": 1000,
                            "filtered": 950,
                            "out": 900,
                            "duration_in_millis": 5000,
                            "queue_push_duration_in_millis": 100,
                        }
                    }
                }
            }
        )
        counts = api.get_pipeline_event_counts("test-pipeline")
        assert counts["in"] == 1000
        assert counts["filtered"] == 950
        assert counts["out"] == 900
        assert counts["duration_in_millis"] == 5000
        assert counts["queue_push_duration_in_millis"] == 100

    def test_not_found(self, api, mock_http):
        r = Mock()
        r.status_code = 404
        mock_http.get.return_value = r
        with pytest.raises(PipelineNotFoundError):
            api.get_pipeline_event_counts("nonexistent")


class TestWaitForPipelineActivity:
    def test_detects_increase(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "p": {
                        "events": {"in": 5, "out": 5},
                    }
                }
            }
        )
        assert api.wait_for_pipeline_activity("p", initial_event_count=0, timeout=1.0) is True

    def test_timeout(self, api, mock_http):
        body = {
            "pipelines": {
                "p": {
                    "events": {"in": 1, "out": 1},
                }
            }
        }
        mock_http.get.return_value = _ok_json(body)
        with patch("logstashagent.logstash_api.time.time", side_effect=[0.0, 0.005, 0.02]):
            with patch("logstashagent.logstash_api.time.sleep"):
                assert (
                    api.wait_for_pipeline_activity(
                        "p", initial_event_count=1, timeout=0.01
                    )
                    is False
                )


class TestGetPipelineUptime:
    def test_seconds_from_duration(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "p": {
                        "events": {"duration_in_millis": 5000},
                    }
                }
            }
        )
        assert api.get_pipeline_uptime("p") == 5.0

    def test_none_when_zero(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "p": {
                        "events": {"duration_in_millis": 0},
                    }
                }
            }
        )
        assert api.get_pipeline_uptime("p") is None


class TestHasPipelineAttemptedLoad:
    def test_true_when_counters_nonzero(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "p": {"reloads": {"successes": 0, "failures": 1}},
                }
            }
        )
        assert api.has_pipeline_attempted_load("p") is True

    def test_false_when_zero(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "p": {"reloads": {"successes": 0, "failures": 0}},
                }
            }
        )
        assert api.has_pipeline_attempted_load("p") is False


class TestEdgeCases:
    def test_empty_pipeline_data(self, api, mock_http):
        mock_http.get.return_value = _ok_json({"pipelines": {"test-pipeline": {}}})
        assert api.detect_pipeline_state("test-pipeline") == "not_found"

    def test_missing_events_field(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {"reloads": {"successes": 1, "failures": 0}},
                }
            }
        )
        assert api.detect_pipeline_state("test-pipeline") == "not_found"

    def test_missing_reloads_field(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {"events": {"in": 0, "out": 0}},
                }
            }
        )
        assert api.detect_pipeline_state("test-pipeline") == "not_found"

    def test_null_reloads(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {"in": 0, "out": 0},
                        "reloads": None,
                    }
                }
            }
        )
        assert api.detect_pipeline_state("test-pipeline") == "not_found"

    def test_reloads_not_dict_returns_failed(self, api, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "test-pipeline": {
                        "events": {"in": 0, "out": 0},
                        "reloads": "bad",
                    }
                }
            }
        )
        assert api.detect_pipeline_state("test-pipeline") == "failed"


class TestModuleHelpers:
    def test_is_pipeline_loaded(self, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "x": {"events": {"in": 1}, "reloads": {}},
                }
            }
        )
        assert is_pipeline_loaded("x", timeout=3.0) is True

    def test_get_running_pipelines_helper(self, mock_http):
        mock_http.get.return_value = _ok_json(
            {"pipelines": {"a": {}, "b": {}}}
        )
        assert set(get_running_pipelines(timeout=3.0)) == {"a", "b"}

    def test_wait_for_pipeline_helper(self, mock_http):
        mock_http.get.return_value = _ok_json(
            {
                "pipelines": {
                    "p": {"events": {"in": 1}, "reloads": {}},
                }
            }
        )
        with patch("logstashagent.logstash_api.time.time", return_value=0.0):
            assert wait_for_pipeline("p", max_wait=0.01, timeout=3.0) is True
