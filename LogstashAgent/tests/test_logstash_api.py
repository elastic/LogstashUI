"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

"""
Comprehensive tests for Logstash API SDK

Tests cover:
- LogstashAPI class initialization and context management
- Pipeline stats retrieval (all pipelines and specific pipeline)
- Pipeline state detection (running, idle, failed, not_found)
- Pipeline listing and existence checks
- Event count retrieval
- Error handling and edge cases
- Reload failure detection
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import httpx

# Import modules to test
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from logstash_api import (
    LogstashAPI,
    LogstashAPIError,
    PipelineNotFoundError
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_httpx_client():
    """Mock httpx.Client for testing"""
    with patch('logstash_api.httpx.Client') as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def api_instance(mock_httpx_client):
    """Create a LogstashAPI instance with mocked client"""
    return LogstashAPI()


# ============================================================================
# LogstashAPI Initialization Tests
# ============================================================================

class TestLogstashAPIInitialization:
    """Test LogstashAPI initialization and context management"""
    
    def test_default_initialization(self):
        """Test initialization with default parameters"""
        with patch('logstash_api.httpx.Client') as mock_client:
            api = LogstashAPI()
            
            assert api.base_url == "http://localhost:9600"
            assert api.timeout == 5.0
            mock_client.assert_called_once_with(timeout=5.0)
    
    def test_custom_initialization(self):
        """Test initialization with custom parameters"""
        with patch('logstash_api.httpx.Client') as mock_client:
            api = LogstashAPI(base_url="http://custom:9700", timeout=10.0)
            
            assert api.base_url == "http://custom:9700"
            assert api.timeout == 10.0
            mock_client.assert_called_once_with(timeout=10.0)
    
    def test_context_manager(self, mock_httpx_client):
        """Test context manager closes client properly"""
        with LogstashAPI() as api:
            assert api is not None
        
        mock_httpx_client.close.assert_called_once()
    
    def test_manual_close(self, mock_httpx_client):
        """Test manual close method"""
        api = LogstashAPI()
        api.close()
        
        mock_httpx_client.close.assert_called_once()


# ============================================================================
# Pipeline Stats Retrieval Tests
# ============================================================================

class TestGetPipelineStats:
    """Test pipeline statistics retrieval"""
    
    def test_get_all_pipeline_stats_success(self, api_instance, mock_httpx_client):
        """Test successful retrieval of all pipeline stats"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "pipeline1": {"events": {"in": 100}},
                "pipeline2": {"events": {"in": 200}}
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        result = api_instance.get_all_pipeline_stats()
        
        assert "pipelines" in result
        assert len(result["pipelines"]) == 2
        mock_httpx_client.get.assert_called_once_with("http://localhost:9600/_node/stats/pipelines")
    
    def test_get_all_pipeline_stats_http_error(self, api_instance, mock_httpx_client):
        """Test handling of HTTP errors when getting all stats"""
        mock_httpx_client.get.side_effect = httpx.HTTPError("Connection failed")
        
        with pytest.raises(LogstashAPIError) as exc_info:
            api_instance.get_all_pipeline_stats()
        
        assert "Failed to get pipeline stats" in str(exc_info.value)
    
    def test_get_pipeline_stats_success(self, api_instance, mock_httpx_client):
        """Test successful retrieval of specific pipeline stats"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 100, "out": 95},
                    "reloads": {"successes": 1, "failures": 0}
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        result = api_instance.get_pipeline_stats("test-pipeline")
        
        assert "pipelines" in result
        assert "test-pipeline" in result["pipelines"]
        mock_httpx_client.get.assert_called_once_with(
            "http://localhost:9600/_node/stats/pipelines/test-pipeline"
        )
    
    def test_get_pipeline_stats_not_found(self, api_instance, mock_httpx_client):
        """Test handling of 404 when pipeline doesn't exist"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_httpx_client.get.return_value = mock_response
        
        with pytest.raises(PipelineNotFoundError) as exc_info:
            api_instance.get_pipeline_stats("nonexistent")
        
        assert "nonexistent" in str(exc_info.value)


# ============================================================================
# Pipeline State Detection Tests
# ============================================================================

class TestDetectPipelineState:
    """Test pipeline state detection logic"""
    
    def test_detect_running_state(self, api_instance, mock_httpx_client):
        """Test detection of running pipeline (has processed events)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 100, "out": 95},
                    "reloads": {"successes": 1, "failures": 0}
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        assert state == "running"
    
    def test_detect_idle_state_with_successes(self, api_instance, mock_httpx_client):
        """Test detection of idle pipeline (loaded but no events yet)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 0, "out": 0},
                    "reloads": {"successes": 1, "failures": 0}
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        assert state == "idle"
    
    def test_detect_idle_state_with_historical_failures(self, api_instance, mock_httpx_client):
        """Test that pipeline with successes is idle even with historical failures"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 0, "out": 0},
                    "reloads": {"successes": 1, "failures": 3}  # Historical failures
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        # Should be idle because it has at least one success
        assert state == "idle"
    
    def test_detect_failed_state(self, api_instance, mock_httpx_client):
        """Test detection of failed pipeline (only failures, no successes)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 0, "out": 0},
                    "reloads": {"successes": 0, "failures": 3}
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        assert state == "idle"
    
    def test_detect_not_found_state(self, api_instance, mock_httpx_client):
        """Test detection when pipeline doesn't exist"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("nonexistent")
        
        assert state == "not_found"
    
    def test_detect_idle_state_no_reload_data(self, api_instance, mock_httpx_client):
        """Test detection of newly created pipeline with no reload data yet"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 0, "out": 0},
                    "reloads": {}  # No reload data yet
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        # Should be idle (newly created, no failures)
        assert state == "idle"
    
    def test_detect_state_api_error(self, api_instance, mock_httpx_client):
        """Test handling of API errors during state detection"""
        mock_httpx_client.get.side_effect = httpx.HTTPError("Connection failed")
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        # Should return not_found on error
        assert state == "not_found"


# ============================================================================
# Pipeline Listing Tests
# ============================================================================

class TestListPipelines:
    """Test pipeline listing functionality"""
    
    def test_list_pipelines_success(self, api_instance, mock_httpx_client):
        """Test successful listing of all pipelines"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "pipeline1": {},
                "pipeline2": {},
                "pipeline3": {}
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        pipelines = api_instance.list_pipelines()
        
        assert len(pipelines) == 3
        assert "pipeline1" in pipelines
        assert "pipeline2" in pipelines
        assert "pipeline3" in pipelines
    
    def test_list_pipelines_empty(self, api_instance, mock_httpx_client):
        """Test listing when no pipelines exist"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"pipelines": {}}
        mock_httpx_client.get.return_value = mock_response
        
        pipelines = api_instance.list_pipelines()
        
        assert pipelines == []
    
    def test_list_pipelines_error(self, api_instance, mock_httpx_client):
        """Test handling of errors when listing pipelines"""
        mock_httpx_client.get.side_effect = httpx.HTTPError("Connection failed")
        
        with pytest.raises(LogstashAPIError):
            api_instance.list_pipelines()


# ============================================================================
# Pipeline Running Check Tests
# ============================================================================

class TestIsPipelineRunning:
    """Test pipeline running status checks"""
    
    def test_is_running_with_events(self, api_instance, mock_httpx_client):
        """Test pipeline is running when it has processed events"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 100, "out": 95},
                    "reloads": {"successes": 1}
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        is_running = api_instance.is_pipeline_running("test-pipeline")
        
        assert is_running == True
    
    def test_is_running_with_reload_data(self, api_instance, mock_httpx_client):
        """Test pipeline is running when it has reload data (even without events)"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 0, "out": 0},
                    "reloads": {"successes": 1}
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        is_running = api_instance.is_pipeline_running("test-pipeline")
        
        assert is_running == True
    
    def test_is_not_running_when_not_found(self, api_instance, mock_httpx_client):
        """Test pipeline is not running when it doesn't exist"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_httpx_client.get.return_value = mock_response
        
        is_running = api_instance.is_pipeline_running("nonexistent")
        
        assert is_running == False


# ============================================================================
# Event Counts Tests
# ============================================================================

class TestGetPipelineEventCounts:
    """Test event count retrieval"""
    
    def test_get_event_counts_success(self, api_instance, mock_httpx_client):
        """Test successful retrieval of event counts"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {
                        "in": 1000,
                        "filtered": 950,
                        "out": 900,
                        "duration_in_millis": 5000,
                        "queue_push_duration_in_millis": 100
                    }
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        counts = api_instance.get_pipeline_event_counts("test-pipeline")
        
        assert counts["in"] == 1000
        assert counts["filtered"] == 950
        assert counts["out"] == 900
        assert counts["duration_in_millis"] == 5000
        assert counts["queue_push_duration_in_millis"] == 100
    
    def test_get_event_counts_not_found(self, api_instance, mock_httpx_client):
        """Test event counts when pipeline doesn't exist"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_httpx_client.get.return_value = mock_response
        
        with pytest.raises(PipelineNotFoundError):
            api_instance.get_pipeline_event_counts("nonexistent")


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================

class TestEdgeCasesAndErrors:
    """Test edge cases and error handling"""
    
    def test_empty_pipeline_data(self, api_instance, mock_httpx_client):
        """Test handling of empty pipeline data in response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {}
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        # Empty pipeline data means pipeline is still registering/initializing
        assert state == "not_found"
    
    def test_missing_events_field(self, api_instance, mock_httpx_client):
        """Test handling when events field is missing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "reloads": {"successes": 1, "failures": 0}
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        # Missing events structure means pipeline hasn't fully initialized yet
        assert state == "not_found"
    
    def test_missing_reloads_field(self, api_instance, mock_httpx_client):
        """Test handling when reloads field is missing"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 0, "out": 0}
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        # Missing reloads structure means pipeline is still registering
        assert state == "not_found"
    
    def test_null_reloads_field(self, api_instance, mock_httpx_client):
        """Test handling when reloads field is null"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "pipelines": {
                "test-pipeline": {
                    "events": {"in": 0, "out": 0},
                    "reloads": None
                }
            }
        }
        mock_httpx_client.get.return_value = mock_response
        
        state = api_instance.detect_pipeline_state("test-pipeline")
        
        # Null reloads field means pipeline is still registering
        assert state == "not_found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
