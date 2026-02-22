import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from threading import Lock, Thread
import time
import yaml
import os
import log_analyzer
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s [Slots] %(levelname)s: %(message)s'))
logger.addHandler(handler)

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
    old_slot_data_to_cleanup = None
    slot_id_to_cleanup = None
    
    with _slots_lock:
        # Check if we already have a slot with this exact configuration
        for slot_id, slot_data in _slots.items():
            if slot_data.get('content_hash') == content_hash:
                # Update timestamps to reset log filtering for each new simulation
                now = datetime.now(timezone.utc)
                slot_data['last_accessed'] = now.isoformat()
                slot_data['created_at'] = now.isoformat()
                slot_data['created_at_millis'] = int(now.timestamp() * 1000)
                return slot_id
        
        # Find an empty slot
        for slot_id in range(1, NUM_SLOTS + 1):
            if slot_id not in _slots:
                now = datetime.now(timezone.utc)
                _slots[slot_id] = {
                    'content_hash': content_hash,
                    'created_at': now.isoformat(),
                    'created_at_millis': int(now.timestamp() * 1000),
                    'last_accessed': now.isoformat(),
                    'pipeline_name': pipeline_name,
                    'pipelines': pipelines
                }
                return slot_id
        
        # No empty slots - evict the oldest one (by created_at)
        oldest_slot_id = min(
            _slots.keys(),
            key=lambda sid: _slots[sid]['created_at']
        )
        
        # Save old slot data before overwriting so we can clean up its pipelines
        old_slot_data_to_cleanup = _slots[oldest_slot_id].copy()
        slot_id_to_cleanup = oldest_slot_id
        
        now = datetime.now(timezone.utc)
        _slots[oldest_slot_id] = {
            'content_hash': content_hash,
            'created_at': now.isoformat(),
            'created_at_millis': int(now.timestamp() * 1000),
            'last_accessed': now.isoformat(),
            'pipeline_name': pipeline_name,
            'pipelines': pipelines
        }
    
    # Delete old pipelines OUTSIDE the lock to avoid blocking other allocations
    if old_slot_data_to_cleanup is not None:
        logger.info(f"Evicting slot {slot_id_to_cleanup}, cleaning up old pipelines")
        _delete_slot_pipelines(slot_id_to_cleanup, old_slot_data_to_cleanup)
    
    return oldest_slot_id if old_slot_data_to_cleanup else slot_id


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


def evict_failed_slots() -> List[int]:
    """
    Evict slots whose pipelines have failed to load (FailedAction errors).
    
    This checks the Logstash logs for "Failed to execute action" errors
    and automatically evicts those slots since they won't be usable anyway.
    
    Returns:
        List of evicted slot IDs
    """
    evicted_slots = []
    
    with _slots_lock:
        slots_to_evict = []
        
        for slot_id, slot_data in _slots.items():
            pipelines = slot_data.get('pipelines', [])
            
            # Check each pipeline in the slot for failures
            for idx in range(1, len(pipelines) + 1):
                pipeline_name = f"slot{slot_id}-filter{idx}"
                
                try:
                    # Check if this pipeline is running (which also checks for FailedAction errors)
                    is_running = log_analyzer.is_pipeline_running(pipeline_name)
                    
                    if not is_running:
                        # Pipeline is not running - check if it's due to a FailedAction error
                        # by looking at the running_pipelines status
                        pipeline_status = log_analyzer.get_running_pipelines()
                        
                        if pipeline_status:
                            running_pipelines = pipeline_status.get('running_pipelines', [])
                            
                            # If the pipeline was expected but isn't running, it likely failed
                            # The get_running_pipelines already filters out FailedAction pipelines
                            if pipeline_name not in running_pipelines:
                                logger.info(f"Pipeline {pipeline_name} failed to load - marking slot {slot_id} for eviction")
                                slots_to_evict.append((slot_id, slot_data))
                                break  # No need to check other pipelines in this slot
                
                except Exception as e:
                    logger.error(f"Error checking pipeline {pipeline_name} status: {e}")
        
        # Evict the failed slots
        for slot_id, slot_data in slots_to_evict:
            del _slots[slot_id]
            evicted_slots.append(slot_id)
    
    # Delete Logstash pipelines for evicted slots (outside the lock)
    for slot_id, slot_data in slots_to_evict:
        _delete_slot_pipelines(slot_id, slot_data)
    
    return evicted_slots


async def verify_slot_pipelines_loaded(slot_id: int, expected_count: int, max_retries: int = 5, retry_delay: float = 1.0) -> bool:
    """
    Verify that all pipelines for a slot have been successfully loaded by Logstash.
    
    Uses log_analyzer.get_running_pipelines() to check the Logstash logs for
    confirmation that the slot's pipelines are running.
    
    Args:
        slot_id: Slot ID (1-10)
        expected_count: Number of pipelines expected for this slot
        max_retries: Maximum number of times to check before giving up
        retry_delay: Seconds to wait between retries
        
    Returns:
        True if all slot pipelines are running, False otherwise
    """
    import asyncio
    
    # Give pipelines an initial grace period to initialize before checking
    logger.info(f"Waiting 3 seconds for slot {slot_id} pipelines to initialize...")
    await asyncio.sleep(3.0)
    
    for attempt in range(max_retries):
        try:
            # Get current running pipelines from logs
            pipeline_status = log_analyzer.get_running_pipelines()
            
            if not pipeline_status:
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: No pipeline status found in logs yet")
                await asyncio.sleep(retry_delay)
                continue
            
            running_pipelines = pipeline_status.get('running_pipelines', [])
            
            # Check if all slot pipelines are present
            slot_pipelines = [f"slot{slot_id}-filter{i}" for i in range(1, expected_count + 1)]
            missing_pipelines = [p for p in slot_pipelines if p not in running_pipelines]
            
            if not missing_pipelines:
                logger.info(f"✓ All {expected_count} pipelines for slot {slot_id} are running")
                return True
            
            # Early failure detection: Check if any missing pipelines have FailedAction errors
            # This allows us to fail fast instead of waiting the full retry period
            if attempt >= 3:  # Give pipelines at least 3 attempts (6+ seconds) before checking for failures
                logs = log_analyzer._read_json_logs(max_lines=500, reverse=True)
                failed_pipelines = set()
                
                for log_entry in logs:
                    if log_entry.get('level') == 'ERROR':
                        log_event = log_entry.get('logEvent', {})
                        action_type = log_event.get('action_type', '')
                        
                        if 'FailedAction' in action_type:
                            pipeline_id = log_event.get('id')
                            if pipeline_id in missing_pipelines:
                                failed_pipelines.add(pipeline_id)
                
                if failed_pipelines:
                    logger.error(f"✗ Detected FailedAction errors for pipelines: {failed_pipelines}")
                    logger.error(f"Failing fast instead of waiting full retry period")
                    return False
            
            logger.warning(f"Attempt {attempt + 1}/{max_retries}: Waiting for pipelines: {missing_pipelines}")
            await asyncio.sleep(retry_delay)
        
        except Exception as e:
            logger.error(f"Error checking pipeline status (attempt {attempt + 1}/{max_retries}): {e}")
            await asyncio.sleep(retry_delay)
    
    logger.error(f"✗ Failed to verify slot {slot_id} pipelines after {max_retries} attempts")
    return False


def _delete_slot_pipelines(slot_id: int, slot_data: Dict[str, Any]):
    """
    Delete all Logstash pipelines associated with a slot.
    
    Args:
        slot_id: Slot ID
        slot_data: Slot data containing pipeline information
    """
    # Import here to avoid circular dependency
    import main
    
    try:
        pipelines = slot_data.get('pipelines', [])
        
        # Delete each filter pipeline directly (no HTTP overhead)
        deleted_count = 0
        for idx in range(1, len(pipelines) + 1):
            pipeline_name = f"slot{slot_id}-filter{idx}"
            try:
                success = main.delete_pipeline_internal(pipeline_name)
                if success:
                    deleted_count += 1
                    logger.info(f"Deleted pipeline {pipeline_name}")
                else:
                    logger.warning(f"Pipeline {pipeline_name} not found or already deleted")
            except Exception as e:
                logger.error(f"Error deleting pipeline {pipeline_name}: {e}")
        
        logger.info(f"Deleted {deleted_count}/{len(pipelines)} pipelines for slot {slot_id}")
    except Exception as e:
        logger.error(f"Error cleaning up pipelines for slot {slot_id}: {e}")


def _background_cleanup_worker():
    """
    Background worker thread that periodically evicts expired and failed slots.
    Runs every 60 seconds.
    """
    while True:
        try:
            time.sleep(60)  # Check every minute
            
            # Evict slots that have exceeded TTL
            expired_slots = evict_expired_slots()
            if expired_slots:
                logger.info(f"Background cleanup evicted expired slots: {expired_slots}")
            
            # Evict slots with failed pipelines
            failed_slots = evict_failed_slots()
            if failed_slots:
                logger.info(f"Background cleanup evicted failed slots: {failed_slots}")
                
        except Exception as e:
            logger.error(f"Error during background cleanup: {e}")


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
