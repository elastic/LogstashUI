"""
Comprehensive tests for LogstashAgent

Tests cover:
- YAML file operations (_load_pipelines_yml, _save_pipelines_yml)
- Pipeline CRUD operations (put_pipeline, get_pipeline, delete_pipeline)
- Slot allocation and eviction (allocate_slot, evict_expired_slots)
- File upload endpoint (write_file)
- Log analysis (find_related_logs)
- Pipeline ID sanitization
"""

import pytest
import os
import json
import yaml
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, mock_open
from fastapi.testclient import TestClient
import base64

# Import modules to test
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main
import slots
import log_analyzer


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
    with patch.object(main, 'PIPELINES_YML_PATH', yml_path):
        yield yml_path


@pytest.fixture
def mock_dirs(temp_dir):
    """Mock all directory paths"""
    pipelines_dir = os.path.join(temp_dir, "conf.d")
    metadata_dir = os.path.join(temp_dir, "metadata")
    yml_path = os.path.join(temp_dir, "pipelines.yml")
    
    os.makedirs(pipelines_dir, exist_ok=True)
    os.makedirs(metadata_dir, exist_ok=True)
    
    with patch.object(main, 'PIPELINES_DIR', pipelines_dir), \
         patch.object(main, 'METADATA_DIR', metadata_dir), \
         patch.object(main, 'PIPELINES_YML_PATH', yml_path):
        yield {
            'pipelines_dir': pipelines_dir,
            'metadata_dir': metadata_dir,
            'yml_path': yml_path
        }


# ============================================================================
# 6a. _load_pipelines_yml() Tests
# ============================================================================

class TestLoadPipelinesYml:
    """Test _load_pipelines_yml() with various file states"""
    
    def test_empty_file(self, mock_pipelines_yml):
        """Test loading an empty file returns empty list"""
        # Create empty file
        open(mock_pipelines_yml, 'w').close()
        
        result = main._load_pipelines_yml()
        assert result == []
    
    def test_comment_only_file(self, mock_pipelines_yml):
        """Test loading a file with only comments returns empty list"""
        with open(mock_pipelines_yml, 'w') as f:
            f.write("# This is a comment\n")
            f.write("# Another comment\n")
            f.write("  # Indented comment\n")
        
        result = main._load_pipelines_yml()
        assert result == []
    
    def test_valid_yaml(self, mock_pipelines_yml):
        """Test loading valid YAML returns parsed data"""
        pipelines = [
            {
                'pipeline.id': 'test-pipeline',
                'path.config': '/etc/logstash/conf.d/test.conf',
                'pipeline.workers': 2
            }
        ]
        
        with open(mock_pipelines_yml, 'w') as f:
            yaml.dump(pipelines, f)
        
        result = main._load_pipelines_yml()
        assert result == pipelines
        assert len(result) == 1
        assert result[0]['pipeline.id'] == 'test-pipeline'
    
    def test_corrupted_yaml(self, mock_pipelines_yml):
        """Test loading corrupted YAML returns empty list and logs error"""
        with open(mock_pipelines_yml, 'w') as f:
            f.write("invalid: yaml: content:\n")
            f.write("  - broken\n")
            f.write("  unclosed: [\n")
        
        result = main._load_pipelines_yml()
        assert result == []
    
    def test_nonexistent_file(self, temp_dir):
        """Test loading nonexistent file returns empty list"""
        yml_path = os.path.join(temp_dir, "nonexistent.yml")
        
        with patch.object(main, 'PIPELINES_YML_PATH', yml_path):
            result = main._load_pipelines_yml()
            assert result == []


# ============================================================================
# 6b. _save_pipelines_yml() Tests
# ============================================================================

class TestSavePipelinesYml:
    """Test _save_pipelines_yml() atomic write behavior"""
    
    def test_atomic_write_succeeds(self, mock_pipelines_yml):
        """Test successful atomic write"""
        pipelines = [
            {
                'pipeline.id': 'test-pipeline',
                'path.config': '/etc/logstash/conf.d/test.conf'
            }
        ]
        
        main._save_pipelines_yml(pipelines)
        
        # Verify file was written
        assert os.path.exists(mock_pipelines_yml)
        
        # Verify content is correct
        with open(mock_pipelines_yml, 'r') as f:
            loaded = yaml.safe_load(f)
        
        assert loaded == pipelines
        
        # Verify temp file was cleaned up
        temp_file = f"{mock_pipelines_yml}.tmp"
        assert not os.path.exists(temp_file)
    
    def test_temp_file_cleanup_on_failure(self, mock_pipelines_yml):
        """Test that temp file is cleaned up when write fails"""
        pipelines = [{'pipeline.id': 'test'}]
        temp_file = f"{mock_pipelines_yml}.tmp"
        
        # Mock os.replace to raise an exception
        with patch('os.replace', side_effect=OSError("Simulated failure")):
            with pytest.raises(OSError):
                main._save_pipelines_yml(pipelines)
        
        # Verify temp file was cleaned up
        assert not os.path.exists(temp_file)
    
    def test_multiple_writes_atomic(self, mock_pipelines_yml):
        """Test multiple writes don't leave temp files"""
        for i in range(3):
            pipelines = [{'pipeline.id': f'pipeline-{i}'}]
            main._save_pipelines_yml(pipelines)
        
        # Verify only the final file exists, no temp files
        assert os.path.exists(mock_pipelines_yml)
        assert not os.path.exists(f"{mock_pipelines_yml}.tmp")
        
        # Verify final content
        with open(mock_pipelines_yml, 'r') as f:
            loaded = yaml.safe_load(f)
        assert loaded[0]['pipeline.id'] == 'pipeline-2'


# ============================================================================
# 6c. put_pipeline / get_pipeline / delete_pipeline - Full CRUD
# ============================================================================

class TestPipelineCRUD:
    """Test full CRUD cycle for pipelines"""
    
    def test_full_crud_roundtrip(self, client, mock_dirs):
        """Test create, read, update, delete pipeline"""
        pipeline_id = "test-crud-pipeline"
        
        # CREATE - Put a new pipeline
        create_body = {
            "pipeline": "input { stdin {} } filter { mutate { add_field => { \"test\" => \"value\" } } } output { stdout {} }",
            "description": "Test CRUD pipeline",
            "username": "test-user",
            "pipeline_settings": {
                "pipeline.workers": 2,
                "pipeline.batch.size": 125
            }
        }
        
        response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=create_body)
        assert response.status_code == 200
        assert response.json()["acknowledged"] == True
        
        # Verify config file was created
        config_path = os.path.join(mock_dirs['pipelines_dir'], f"{pipeline_id}.conf")
        assert os.path.exists(config_path)
        
        # Verify metadata file was created
        metadata_path = os.path.join(mock_dirs['metadata_dir'], f"{pipeline_id}.json")
        assert os.path.exists(metadata_path)
        
        # READ - Get the pipeline
        response = client.get(f"/_logstash/pipeline/{pipeline_id}")
        assert response.status_code == 200
        data = response.json()
        
        assert pipeline_id in data
        assert data[pipeline_id]["description"] == "Test CRUD pipeline"
        assert data[pipeline_id]["username"] == "test-user"
        assert data[pipeline_id]["pipeline"] == create_body["pipeline"]
        assert data[pipeline_id]["pipeline_settings"]["pipeline.workers"] == 2
        
        # UPDATE - Modify the pipeline
        update_body = {
            "pipeline": "input { stdin {} } output { stdout { codec => json } }",
            "description": "Updated CRUD pipeline",
            "username": "updated-user",
            "pipeline_settings": {
                "pipeline.workers": 4
            }
        }
        
        response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=update_body)
        assert response.status_code == 200
        
        # Verify update
        response = client.get(f"/_logstash/pipeline/{pipeline_id}")
        assert response.status_code == 200
        data = response.json()
        
        assert data[pipeline_id]["description"] == "Updated CRUD pipeline"
        assert data[pipeline_id]["username"] == "updated-user"
        assert data[pipeline_id]["pipeline_settings"]["pipeline.workers"] == 4
        
        # DELETE - Remove the pipeline
        response = client.delete(f"/_logstash/pipeline/{pipeline_id}")
        assert response.status_code == 200
        assert response.json()["acknowledged"] == True
        
        # Verify files were deleted
        assert not os.path.exists(config_path)
        assert not os.path.exists(metadata_path)
        
        # Verify pipeline no longer exists
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
        response = client.put("/_logstash/pipeline/test", json={"description": "Missing pipeline"})
        assert response.status_code == 400
        assert "Missing 'pipeline' field" in response.json()["detail"]


# ============================================================================
# 6d. allocate_slot() Tests
# ============================================================================

class TestAllocateSlot:
    """Test slot allocation, reuse, and eviction"""
    
    def setup_method(self):
        """Clear slots before each test"""
        slots.clear_all_slots()
    
    def teardown_method(self):
        """Clear slots after each test"""
        slots.clear_all_slots()
    
    def test_fresh_slot_allocation(self):
        """Test allocating a fresh slot"""
        pipelines = [
            {"config": "input { stdin {} } output { stdout {} }"}
        ]
        
        slot_id = slots.allocate_slot("test-pipeline", pipelines)
        
        assert slot_id is not None
        assert 1 <= slot_id <= slots.NUM_SLOTS
        
        # Verify slot data
        slot_data = slots.get_slot_state()
        assert slot_id in slot_data
        assert slot_data[slot_id]['pipeline_name'] == "test-pipeline"
        assert slot_data[slot_id]['pipelines'] == pipelines
    
    def test_hash_match_reuse(self):
        """Test that identical pipeline configs reuse the same slot"""
        pipelines = [
            {"config": "input { stdin {} } output { stdout {} }"}
        ]
        
        # Allocate first time
        slot_id_1 = slots.allocate_slot("test-pipeline-1", pipelines)
        
        # Allocate with same config (different name)
        slot_id_2 = slots.allocate_slot("test-pipeline-2", pipelines)
        
        # Should reuse the same slot
        assert slot_id_1 == slot_id_2
        
        # Verify only one slot is allocated
        slot_state = slots.get_slot_state()
        assert len(slot_state) == 1
    
    def test_eviction_when_all_slots_full(self):
        """Test eviction of oldest slot when all 10 slots are full"""
        # Fill all 10 slots with different configs
        allocated_slots = []
        
        for i in range(slots.NUM_SLOTS):
            pipelines = [{"config": f"input {{ generator {{ count => {i} }} }} output {{ stdout {{}} }}"}]
            slot_id = slots.allocate_slot(f"pipeline-{i}", pipelines)
            allocated_slots.append(slot_id)
        
        # Verify all slots are full
        assert len(slots.get_slot_state()) == slots.NUM_SLOTS
        
        # Record the first slot's ID (should be evicted)
        first_slot_id = allocated_slots[0]
        
        # Allocate one more with a new config (should evict oldest)
        new_pipelines = [{"config": "input { stdin {} } output { null {} }"}]
        
        with patch.object(main, 'delete_pipeline_internal', return_value=True):
            new_slot_id = slots.allocate_slot("new-pipeline", new_pipelines)
        
        # Should still have 10 slots
        assert len(slots.get_slot_state()) == slots.NUM_SLOTS
        
        # The new slot should have reused the oldest slot's ID
        assert new_slot_id == first_slot_id
        
        # Verify the new pipeline is in the slot
        slot_data = slots.get_slot_state()[new_slot_id]
        assert slot_data['pipeline_name'] == "new-pipeline"
    
    def test_different_configs_get_different_slots(self):
        """Test that different pipeline configs get different slots"""
        pipelines_1 = [{"config": "input { stdin {} }"}]
        pipelines_2 = [{"config": "input { generator {} }"}]
        
        slot_id_1 = slots.allocate_slot("pipeline-1", pipelines_1)
        slot_id_2 = slots.allocate_slot("pipeline-2", pipelines_2)
        
        assert slot_id_1 != slot_id_2
        assert len(slots.get_slot_state()) == 2


# ============================================================================
# 6e. evict_expired_slots() Tests
# ============================================================================

class TestEvictExpiredSlots:
    """Test slot eviction based on TTL"""
    
    def setup_method(self):
        """Clear slots before each test"""
        slots.clear_all_slots()
    
    def teardown_method(self):
        """Clear slots after each test"""
        slots.clear_all_slots()
    
    def test_evict_expired_slots_with_old_timestamps(self):
        """Test eviction of slots with expired TTL"""
        # Allocate a slot
        pipelines = [{"config": "input { stdin {} }"}]
        slot_id = slots.allocate_slot("test-pipeline", pipelines)
        
        # Manually inject an old timestamp (beyond TTL)
        old_time = datetime.now(timezone.utc) - timedelta(seconds=slots.SLOT_TTL_SECONDS + 60)
        
        with slots._slots_lock:
            slots._slots[slot_id]['last_accessed'] = old_time.isoformat()
            slots._slots[slot_id]['created_at'] = old_time.isoformat()
        
        # Mock delete_pipeline_internal to avoid actual deletion
        with patch.object(main, 'delete_pipeline_internal', return_value=True):
            evicted = slots.evict_expired_slots()
        
        # Verify the slot was evicted
        assert slot_id in evicted
        assert len(slots.get_slot_state()) == 0
    
    def test_no_eviction_for_recent_slots(self):
        """Test that recently accessed slots are not evicted"""
        # Allocate a slot
        pipelines = [{"config": "input { stdin {} }"}]
        slot_id = slots.allocate_slot("test-pipeline", pipelines)
        
        # Evict expired slots
        evicted = slots.evict_expired_slots()
        
        # Verify no slots were evicted
        assert len(evicted) == 0
        assert len(slots.get_slot_state()) == 1
    
    def test_mixed_expired_and_active_slots(self):
        """Test eviction with mix of expired and active slots"""
        # Allocate multiple slots
        slot_ids = []
        for i in range(3):
            pipelines = [{"config": f"input {{ generator {{ count => {i} }} }}"}]
            slot_id = slots.allocate_slot(f"pipeline-{i}", pipelines)
            slot_ids.append(slot_id)
        
        # Make first two slots expired
        old_time = datetime.now(timezone.utc) - timedelta(seconds=slots.SLOT_TTL_SECONDS + 60)
        
        with slots._slots_lock:
            for slot_id in slot_ids[:2]:
                slots._slots[slot_id]['last_accessed'] = old_time.isoformat()
        
        # Evict expired slots
        with patch.object(main, 'delete_pipeline_internal', return_value=True):
            evicted = slots.evict_expired_slots()
        
        # Verify only the first two were evicted
        assert len(evicted) == 2
        assert slot_ids[0] in evicted
        assert slot_ids[1] in evicted
        assert slot_ids[2] not in evicted
        
        # Verify one slot remains
        assert len(slots.get_slot_state()) == 1
    
    def test_evict_slot_with_invalid_timestamp(self):
        """Test that slots with unparseable timestamps are evicted"""
        # Allocate a slot
        pipelines = [{"config": "input { stdin {} }"}]
        slot_id = slots.allocate_slot("test-pipeline", pipelines)
        
        # Inject invalid timestamp
        with slots._slots_lock:
            slots._slots[slot_id]['last_accessed'] = "invalid-timestamp"
        
        # Evict expired slots
        with patch.object(main, 'delete_pipeline_internal', return_value=True):
            evicted = slots.evict_expired_slots()
        
        # Verify the slot was evicted due to invalid timestamp
        assert slot_id in evicted
        assert len(slots.get_slot_state()) == 0


# ============================================================================
# 6f. write_file endpoint Tests
# ============================================================================

class TestWriteFileEndpoint:
    """Test file upload endpoint with various scenarios"""
    
    def test_simulation_mode_off_returns_403(self, client):
        """Test that file upload is forbidden when simulation mode is off"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "false"}):
            body = {
                "filename": "test.txt",
                "content": base64.b64encode(b"test content").decode()
            }
            
            response = client.post("/_logstash/write-file", json=body)
            assert response.status_code == 403
            assert "simulation mode" in response.json()["detail"].lower()
    
    def test_missing_filename_returns_400(self, client):
        """Test that missing filename returns 400"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "true"}):
            body = {
                "content": base64.b64encode(b"test content").decode()
            }
            
            response = client.post("/_logstash/write-file", json=body)
            assert response.status_code == 400
            assert "required" in response.json()["detail"].lower()
    
    def test_missing_content_returns_400(self, client):
        """Test that missing content returns 400"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "true"}):
            body = {
                "filename": "test.txt"
            }
            
            response = client.post("/_logstash/write-file", json=body)
            assert response.status_code == 400
            assert "required" in response.json()["detail"].lower()
    
    def test_path_traversal_sanitized(self, client, temp_dir):
        """Test that path traversal attempts are sanitized"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "true"}):
            # Mock the uploaded directory
            uploaded_dir = os.path.join(temp_dir, "uploaded")
            
            with patch('os.makedirs'), \
                 patch('builtins.open', mock_open()) as mock_file:
                
                # Attempt path traversal
                body = {
                    "filename": "../../../etc/passwd",
                    "content": base64.b64encode(b"malicious content").decode()
                }
                
                response = client.post("/_logstash/write-file", json=body)
                assert response.status_code == 200
                
                # Verify the file was written with sanitized name (basename only)
                # The open call should use only "passwd", not the full path
                call_args = mock_file.call_args[0][0]
                assert "etc" not in call_args
                assert call_args.endswith("passwd")
    
    def test_valid_upload(self, client, temp_dir):
        """Test successful file upload"""
        with patch.dict(os.environ, {"SIMULATION_MODE": "true"}):
            uploaded_dir = os.path.join(temp_dir, "uploaded")
            os.makedirs(uploaded_dir, exist_ok=True)
            
            # Mock the uploaded directory path
            with patch('os.makedirs'), \
                 patch('os.path.join', return_value=os.path.join(uploaded_dir, "test.json")):
                
                test_content = b'{"key": "value"}'
                body = {
                    "filename": "test.json",
                    "content": base64.b64encode(test_content).decode()
                }
                
                response = client.post("/_logstash/write-file", json=body)
                assert response.status_code == 200
                
                result = response.json()
                assert result["status"] == "success"
                assert "test.json" in result["path"]


# ============================================================================
# 6g. find_related_logs() Tests
# ============================================================================

class TestFindRelatedLogs:
    """Test log analysis with mocked log data"""
    
    def test_find_logs_for_pipeline(self):
        """Test finding logs related to a specific pipeline"""
        mock_logs = [
            {
                "level": "ERROR",
                "pipeline.id": "test-pipeline",
                "logEvent": {
                    "message": "Pipeline error occurred"
                },
                "timeMillis": 1704110400000
            },
            {
                "level": "WARN",
                "pipeline.id": "test-pipeline",
                "logEvent": {
                    "message": "Pipeline warning"
                },
                "timeMillis": 1704110460000
            },
            {
                "level": "INFO",
                "pipeline.id": "other-pipeline",
                "logEvent": {
                    "message": "Other pipeline info"
                },
                "timeMillis": 1704110520000
            }
        ]
        
        with patch.object(log_analyzer, '_read_json_logs', return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="WARN"
            )
        
        # Should return 2 logs (ERROR and WARN for test-pipeline)
        assert len(logs) == 2
        assert all(log['pipeline.id'] == 'test-pipeline' for log in logs)
    
    def test_find_logs_with_min_level_filter(self):
        """Test log filtering by minimum level"""
        mock_logs = [
            {"level": "ERROR", "pipeline.id": "test-pipeline", "timeMillis": 1704110400000},
            {"level": "WARN", "pipeline.id": "test-pipeline", "timeMillis": 1704110460000},
            {"level": "INFO", "pipeline.id": "test-pipeline", "timeMillis": 1704110520000},
            {"level": "DEBUG", "pipeline.id": "test-pipeline", "timeMillis": 1704110580000}
        ]
        
        with patch.object(log_analyzer, '_read_json_logs', return_value=mock_logs):
            # Filter for ERROR only
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="ERROR"
            )
        
        assert len(logs) == 1
        assert logs[0]['level'] == 'ERROR'
    
    def test_find_logs_with_timestamp_filter(self):
        """Test log filtering by minimum timestamp"""
        # Use actual millisecond timestamps
        base_time = 1704110400000  # 2024-01-01T12:00:00.000Z
        mock_logs = [
            {"level": "ERROR", "pipeline.id": "test-pipeline", "timeMillis": base_time},
            {"level": "ERROR", "pipeline.id": "test-pipeline", "timeMillis": base_time + 300000},  # +5 min
            {"level": "ERROR", "pipeline.id": "test-pipeline", "timeMillis": base_time + 600000}   # +10 min
        ]
        
        # Timestamp for +5 minutes
        min_timestamp = base_time + 300000
        
        with patch.object(log_analyzer, '_read_json_logs', return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="DEBUG",
                min_timestamp=min_timestamp
            )
        
        # Should only return logs from 12:05:00 onwards
        assert len(logs) == 2
    
    def test_find_logs_max_entries_limit(self):
        """Test that max_entries limit is respected"""
        mock_logs = [
            {"level": "ERROR", "pipeline.id": "test-pipeline", "timeMillis": 1704110400000 + (i * 1000)}
            for i in range(100)
        ]
        
        with patch.object(log_analyzer, '_read_json_logs', return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="DEBUG"
            )
        
        assert len(logs) == 10
    
    def test_find_logs_no_matches(self):
        """Test when no logs match the criteria"""
        mock_logs = [
            {"level": "INFO", "pipeline.id": "other-pipeline", "timeMillis": 1704110400000}
        ]
        
        with patch.object(log_analyzer, '_read_json_logs', return_value=mock_logs):
            logs = log_analyzer.find_related_logs(
                pipeline_id="test-pipeline",
                max_entries=10,
                min_level="WARN"
            )
        
        assert len(logs) == 0


# ============================================================================
# 6h. pipeline_id sanitization Tests
# ============================================================================

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
            "my-pipeline_v2.0"
        ]
        
        for pipeline_id in valid_ids:
            body = {
                "pipeline": "input { stdin {} } output { stdout {} }"
            }
            
            response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=body)
            assert response.status_code == 200, f"Valid ID '{pipeline_id}' was rejected"
    
    def test_invalid_pipeline_ids_rejected(self, client, mock_dirs):
        """Test that invalid pipeline IDs are rejected"""
        # Note: FastAPI routing handles slashes/backslashes before validation (404)
        # Test IDs that actually reach our validation code
        invalid_ids = [
            "test pipeline",           # Contains space
            "test;pipeline",           # Contains semicolon
            "test|pipeline",           # Contains pipe
            "test&pipeline",           # Contains ampersand
            ".hidden",                 # Starts with dot
            "-invalid",                # Starts with hyphen
            "test..pipeline",          # Contains double dots
        ]
        
        for pipeline_id in invalid_ids:
            body = {
                "pipeline": "input { stdin {} } output { stdout {} }"
            }
            
            response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=body)
            assert response.status_code == 400, f"Invalid ID '{pipeline_id}' was accepted"
            assert "Invalid pipeline_id" in response.json()["detail"]
    
    def test_path_traversal_blocked_in_get(self, client, mock_dirs):
        """Test path traversal is blocked in GET endpoint"""
        # FastAPI normalizes paths, so ../ in URL gets 404 from routing
        # Test with encoded path or direct invalid chars
        response = client.get("/_logstash/pipeline/test..traversal")
        assert response.status_code == 400
        assert "Invalid pipeline_id" in response.json()["detail"]
    
    def test_path_traversal_blocked_in_delete(self, client, mock_dirs):
        """Test path traversal is blocked in DELETE endpoint"""
        # FastAPI normalizes paths, test with double dots
        response = client.delete("/_logstash/pipeline/test..traversal")
        assert response.status_code == 400
        assert "Invalid pipeline_id" in response.json()["detail"]
    
    def test_path_traversal_blocked_in_logs(self, client, mock_dirs):
        """Test path traversal is blocked in logs endpoint"""
        # FastAPI normalizes paths, test with double dots
        response = client.get("/_logstash/pipeline/test..traversal/logs")
        assert response.status_code == 400
        assert "Invalid pipeline_id" in response.json()["detail"]
    
    def test_double_dot_sequences_rejected(self, client, mock_dirs):
        """Test that .. sequences are explicitly rejected"""
        body = {
            "pipeline": "input { stdin {} } output { stdout {} }"
        }
        
        response = client.put("/_logstash/pipeline/test..pipeline", json=body)
        assert response.status_code == 400
        assert ".." in response.json()["detail"]
    
    def test_alphanumeric_with_allowed_chars(self, client, mock_dirs):
        """Test that alphanumeric with hyphens, underscores, and dots work"""
        pipeline_id = "valid-pipeline_name.v1"
        body = {
            "pipeline": "input { stdin {} } output { stdout {} }"
        }
        
        response = client.put(f"/_logstash/pipeline/{pipeline_id}", json=body)
        assert response.status_code == 200


# ============================================================================
# Additional Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Additional edge case tests"""
    
    def test_list_pipelines_empty(self, client, mock_dirs):
        """Test listing pipelines when none exist"""
        response = client.get("/_logstash/pipeline")
        assert response.status_code == 200
        assert response.json() == {}
    
    def test_list_pipelines_with_data(self, client, mock_dirs):
        """Test listing multiple pipelines"""
        # Create two pipelines
        for i in range(2):
            body = {
                "pipeline": f"input {{ stdin {{}} }} output {{ stdout {{}} }}",
                "description": f"Pipeline {i}"
            }
            client.put(f"/_logstash/pipeline/test-pipeline-{i}", json=body)
        
        response = client.get("/_logstash/pipeline")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) == 2
        assert "test-pipeline-0" in data
        assert "test-pipeline-1" in data
    
    def test_slot_state_retrieval(self):
        """Test getting slot state"""
        slots.clear_all_slots()
        
        # Allocate a slot
        pipelines = [{"config": "test"}]
        slot_id = slots.allocate_slot("test", pipelines)
        
        # Get state
        state = slots.get_slot_state()
        
        assert slot_id in state
        assert state[slot_id]['pipeline_name'] == "test"
        
        slots.clear_all_slots()
    
    def test_release_slot(self):
        """Test releasing a slot"""
        slots.clear_all_slots()
        
        # Allocate a slot
        pipelines = [{"config": "test"}]
        slot_id = slots.allocate_slot("test", pipelines)
        
        # Release it
        result = slots.release_slot(slot_id)
        assert result == True
        
        # Verify it's gone
        state = slots.get_slot_state()
        assert slot_id not in state
        
        # Try releasing again
        result = slots.release_slot(slot_id)
        assert result == False
        
        slots.clear_all_slots()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
