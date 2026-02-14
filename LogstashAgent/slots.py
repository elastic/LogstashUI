import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from threading import Lock

# Number of simulation slots available
NUM_SLOTS = 10

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
