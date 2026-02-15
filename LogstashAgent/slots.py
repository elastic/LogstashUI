import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from threading import Lock, Thread
import time
import yaml
import os

# Number of simulation slots available
NUM_SLOTS = 10

# Slot TTL in seconds (5 minutes)
SLOT_TTL_SECONDS = 300

# Global slot state - thread-safe
_slots_lock = Lock()
_slots: Dict[int, Dict[str, Any]] = {}


def _compute_pipeline_hash(pipelines: List[Dict[str, Any]]) -> str:
    """
    Compute a hash of the pipeline list to detect changes.
    
    Args:
        pipelines: List of pipeline configurations
        
    Returns:
        SHA256 hash string
    """
    # Convert to JSON string with sorted keys for consistent hashing
    pipeline_str = json.dumps(pipelines, sort_keys=True)
    return hashlib.sha256(pipeline_str.encode()).hexdigest()


def get_slot_state() -> Dict[int, Dict[str, Any]]:
    """
    Get a copy of the current slot state.
    
    Returns:
        Dictionary mapping slot IDs to their state
    """
    with _slots_lock:
        return _slots.copy()


def allocate_slot(pipeline_name: str, pipelines: List[Dict[str, Any]]) -> Optional[int]:
    """
    Allocate a slot for the given pipeline configuration.
    
    If a slot already exists with the same content hash, reuse it.
    Otherwise, find an empty slot or evict the oldest one.
    
    Args:
        pipeline_name: Name of the pipeline
        pipelines: List of pipeline configurations
        
    Returns:
        Slot ID (1-10) or None if allocation failed
    """
    content_hash = _compute_pipeline_hash(pipelines)
    
    with _slots_lock:
        # Check if we already have a slot with this exact configuration
        for slot_id, slot_data in _slots.items():
            if slot_data.get('content_hash') == content_hash:
                # Update the timestamp to keep it fresh
                slot_data['last_accessed'] = datetime.now(timezone.utc).isoformat()
                return slot_id
        
        # Find an empty slot
        for slot_id in range(1, NUM_SLOTS + 1):
            if slot_id not in _slots:
                _slots[slot_id] = {
                    'content_hash': content_hash,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'last_accessed': datetime.now(timezone.utc).isoformat(),
                    'pipeline_name': pipeline_name,
                    'pipelines': pipelines
                }
                return slot_id
        
        # No empty slots - evict the oldest one (by created_at)
        oldest_slot_id = min(
            _slots.keys(),
            key=lambda sid: _slots[sid]['created_at']
        )
        
        _slots[oldest_slot_id] = {
            'content_hash': content_hash,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_accessed': datetime.now(timezone.utc).isoformat(),
            'pipeline_name': pipeline_name,
            'pipelines': pipelines
        }
        
        return oldest_slot_id


def get_slot(slot_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the data for a specific slot.
    
    Args:
        slot_id: Slot ID (1-10)
        
    Returns:
        Slot data or None if slot doesn't exist
    """
    with _slots_lock:
        slot_data = _slots.get(slot_id)
        if slot_data:
            # Update last accessed time
            slot_data['last_accessed'] = datetime.now(timezone.utc).isoformat()
        return slot_data.copy() if slot_data else None


def release_slot(slot_id: int) -> bool:
    """
    Release a slot, making it available for reuse.
    
    Args:
        slot_id: Slot ID (1-10)
        
    Returns:
        True if slot was released, False if it didn't exist
    """
    with _slots_lock:
        if slot_id in _slots:
            del _slots[slot_id]
            return True
        return False


def clear_all_slots():
    """Clear all slots - useful for testing or reset."""
    with _slots_lock:
        _slots.clear()


def evict_expired_slots() -> List[int]:
    """
    Evict slots that haven't been accessed within the TTL period.
    
    Returns:
        List of evicted slot IDs
    """
    evicted_slots = []
    current_time = datetime.now(timezone.utc)
    
    with _slots_lock:
        slots_to_evict = []
        
        for slot_id, slot_data in _slots.items():
            last_accessed_str = slot_data.get('last_accessed')
            if last_accessed_str:
                try:
                    last_accessed = datetime.fromisoformat(last_accessed_str.replace('Z', '+00:00'))
                    time_since_access = (current_time - last_accessed).total_seconds()
                    
                    if time_since_access > SLOT_TTL_SECONDS:
                        slots_to_evict.append((slot_id, slot_data))
                except (ValueError, AttributeError):
                    # If we can't parse the timestamp, evict the slot to be safe
                    slots_to_evict.append((slot_id, slot_data))
        
        # Evict the expired slots
        for slot_id, slot_data in slots_to_evict:
            del _slots[slot_id]
            evicted_slots.append(slot_id)
    
    # Delete Logstash pipelines for evicted slots (outside the lock)
    for slot_id, slot_data in slots_to_evict:
        _delete_slot_pipelines(slot_id, slot_data)
    
    return evicted_slots


def _delete_slot_pipelines(slot_id: int, slot_data: Dict[str, Any]):
    """
    Delete all Logstash pipelines associated with a slot.
    
    Args:
        slot_id: Slot ID
        slot_data: Slot data containing pipeline information
    """
    import requests
    
    try:
        pipelines = slot_data.get('pipelines', [])
        logstash_url = "http://localhost:9600"
        
        # Delete each filter pipeline
        for idx in range(1, len(pipelines) + 1):
            pipeline_name = f"slot{slot_id}-filter{idx}"
            try:
                response = requests.delete(f"{logstash_url}/_logstash/pipeline/{pipeline_name}")
                if response.status_code in [200, 404]:
                    # 200 = deleted, 404 = already gone
                    pass
                else:
                    print(f"[Slots] Warning: Failed to delete pipeline {pipeline_name}: {response.status_code}")
            except Exception as e:
                print(f"[Slots] Error deleting pipeline {pipeline_name}: {e}")
        
        print(f"[Slots] Deleted {len(pipelines)} pipelines for slot {slot_id}")
    except Exception as e:
        print(f"[Slots] Error cleaning up pipelines for slot {slot_id}: {e}")


def _background_cleanup_worker():
    """
    Background worker thread that periodically evicts expired slots.
    Runs every 60 seconds.
    """
    while True:
        try:
            time.sleep(60)  # Check every minute
            evicted_slots = evict_expired_slots()
            if evicted_slots:
                print(f"[Slots] Background cleanup evicted expired slots: {evicted_slots}")
        except Exception as e:
            print(f"[Slots] Error during background cleanup: {e}")


def _load_config() -> Dict[str, Any]:
    """
    Load configuration from logstashagent.yml.
    
    Returns:
        Dictionary with configuration settings
    """
    config_path = os.path.join(os.path.dirname(__file__), 'logstashagent.yml')
    
    if not os.path.exists(config_path):
        print(f"[Slots] Config file not found at {config_path}, using defaults")
        return {}
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except Exception as e:
        print(f"[Slots] Error loading config: {e}, using defaults")
        return {}


# Conditionally start the background cleanup thread based on config
_config = _load_config()
_mode = _config.get('mode', '').lower()

if _mode == 'simulation':
    _cleanup_thread = Thread(target=_background_cleanup_worker, daemon=True, name="SlotCleanupThread")
    _cleanup_thread.start()
    print("[Slots] Started background cleanup thread (mode: simulation)")
else:
    print(f"[Slots] Background cleanup thread NOT started (mode: {_mode or 'not set'})")
