#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

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
from logstash_api import LogstashAPI, PipelineNotFoundError

# Configure logging
logger = logging.getLogger(__name__)

# Number of simulation slots available
NUM_SLOTS = 6

# Slot TTL in seconds (2 minutes)
SLOT_TTL_SECONDS = 120

# Global slot state - thread-safe
_slots_lock = Lock()
_slots: Dict[int, Dict[str, Any]] = {}


def _compute_pipeline_hash(pipelines: List[Dict[str, Any]]) -> str:
    """
    Compute a hash of the pipeline list to detect changes.

    Only hashes fields that actually affect the created pipeline:
    - filter_config: The filter configuration content
    - index: The pipeline index/order

    Args:
        pipelines: List of pipeline configurations

    Returns:
        SHA256 hash string
    """
    # Extract only the fields that affect the actual pipeline
    # (output_config is sent by UI but ignored by agent, so exclude it from hash)
    normalized_pipelines = []
    for pipeline in pipelines:
        filter_config = pipeline.get('filter_config', '')
        normalized_pipelines.append({
            'filter_config': filter_config,
            'index': pipeline.get('index', 1)
        })

    # Convert to JSON string with sorted keys for consistent hashing
    pipeline_str = json.dumps(normalized_pipelines, sort_keys=True)
    computed_hash = hashlib.sha256(pipeline_str.encode()).hexdigest()

    # Debug: Write full filter_config to temp file for comparison
    # if normalized_pipelines:
    #     import tempfile
    #     filter_config = normalized_pipelines[0]['filter_config']
    #     debug_file = os.path.join(tempfile.gettempdir(), f"filter_config_{computed_hash[:8]}.txt")
    #     try:
    #         with open(debug_file, 'w', encoding='utf-8') as f:
    #             f.write(filter_config)
    #         logger.info(f"Hash {computed_hash[:8]}: Wrote filter_config to {debug_file} ({len(filter_config)} bytes)")
    #     except Exception as e:
    #         logger.error(f"Failed to write debug file: {e}")
    
    return computed_hash


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

    logger.info(f"allocate_slot: Looking for hash {content_hash[:8]}... in {len(_slots)} existing slots")

    with _slots_lock:
        # Check if we already have a slot with this exact configuration
        for slot_id, slot_data in _slots.items():
            existing_hash = slot_data.get('content_hash', '')
            logger.debug(f"  Slot {slot_id} hash: {existing_hash[:8]}...")
            if existing_hash == content_hash:
                # Update last_accessed to prevent TTL eviction
                # DO NOT update created_at - keep original creation time to prevent race conditions
                # with eviction logic during active simulations
                now = datetime.now(timezone.utc)
                slot_data['last_accessed'] = now.isoformat()
                logger.info(f"+ Reusing slot {slot_id} with matching hash")
                return slot_id
            else:
                # Debug: Compare configs to see what's different
                if pipelines and slot_data.get('pipelines'):
                    new_config = pipelines[0].get('filter_config', '')
                    old_config = slot_data['pipelines'][0].get('filter_config', '')
                    if len(new_config) == len(old_config):
                        # Same length but different hash - find first difference
                        for i, (c1, c2) in enumerate(zip(new_config, old_config)):
                            if c1 != c2:
                                start = max(0, i - 50)
                                end = min(len(new_config), i + 50)
                                logger.warning(f"Hash mismatch at position {i}:")
                                logger.warning(f"  Old (slot {slot_id}): ...{old_config[start:end]}...")
                                logger.warning(f"  New: ...{new_config[start:end]}...")
                                break

        # Find an empty slot
        logger.info(f"No matching hash found, allocating new slot")
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
                logger.info(f"+ Allocated new empty slot {slot_id}")
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

    return oldest_slot_id


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


def evict_all_slots_and_cleanup():
    """
    Evict all slots and clean up all pipeline files from conf.d.
    This should be called before Logstash restart to prevent mismatch
    between slots state and Logstash's loaded pipelines.
    
    Returns:
        List of evicted slot IDs
    """
    logger.info("Evicting all slots and cleaning up conf.d folder for Logstash restart")
    evicted_slots = []
    
    with _slots_lock:
        # Get all current slots before clearing
        slots_to_cleanup = list(_slots.items())
        
        # Clear the slots dictionary
        _slots.clear()
        evicted_slots = [slot_id for slot_id, _ in slots_to_cleanup]
    
    # Delete all pipeline files outside the lock
    for slot_id, slot_data in slots_to_cleanup:
        try:
            _delete_slot_pipelines(slot_id, slot_data)
        except Exception as e:
            logger.error(f"Error cleaning up slot {slot_id} during evict_all: {e}")
    
    # Also clean up any orphaned pipeline files in conf.d
    try:
        import main
        conf_d_path = main.PIPELINES_DIR
        if os.path.exists(conf_d_path):
            orphaned_files = []
            for filename in os.listdir(conf_d_path):
                if filename.startswith('slot') and filename.endswith('.conf'):
                    file_path = os.path.join(conf_d_path, filename)
                    try:
                        os.remove(file_path)
                        orphaned_files.append(filename)
                        logger.debug(f"Removed orphaned pipeline file: {filename}")
                    except Exception as e:
                        logger.error(f"Error removing orphaned file {filename}: {e}")
            
            if orphaned_files:
                logger.info(f"Cleaned up {len(orphaned_files)} orphaned pipeline files from conf.d")
    except Exception as e:
        logger.error(f"Error cleaning up orphaned files: {e}")
    
    logger.info(f"Evicted all {len(evicted_slots)} slots and cleaned up conf.d folder")
    return evicted_slots


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
    Evict slots whose pipelines have failed to load or are not running.

    Uses the Logstash API to directly query pipeline state instead of parsing logs.
    This is more reliable and faster than log-based detection.

    Returns:
        List of evicted slot IDs
    """
    evicted_slots = []
    current_time = datetime.now(timezone.utc)

    # Minimum age before evicting a slot (prevents race condition with pipeline creation)
    # Pipelines need time to load - don't evict slots that were just created
    MIN_SLOT_AGE_SECONDS = 30

    try:
        with LogstashAPI(timeout=5.0) as api:
            # Get all currently loaded pipelines from Logstash
            all_pipelines = api.list_pipelines()

            with _slots_lock:
                slots_to_evict = []

                for slot_id, slot_data in _slots.items():
                    # Check slot age - don't evict newly created slots
                    created_at_str = slot_data.get('created_at')
                    if created_at_str:
                        try:
                            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                            slot_age = (current_time - created_at).total_seconds()

                            if slot_age < MIN_SLOT_AGE_SECONDS:
                                logger.debug(f"Slot {slot_id} is only {slot_age:.1f}s old - skipping eviction check")
                                continue
                        except (ValueError, AttributeError) as e:
                            logger.warning(f"Could not parse created_at for slot {slot_id}: {e}")
                            # Continue with eviction check if we can't parse timestamp

                    pipelines = slot_data.get('pipelines', [])

                    # Check if any pipeline in this slot is missing, failed, or not running
                    for idx in range(1, len(pipelines) + 1):
                        pipeline_name = f"slot{slot_id}-filter{idx}"

                        # Check if pipeline exists in Logstash
                        if pipeline_name not in all_pipelines:
                            logger.warning(
                                f"Slot {slot_id} pipeline {pipeline_name} not found in Logstash - marking for eviction")
                            slots_to_evict.append((slot_id, slot_data))
                            break

                        # Check pipeline state
                        state = api.detect_pipeline_state(pipeline_name)
                        if state == 'not_found':
                            logger.warning(
                                f"Slot {slot_id} pipeline {pipeline_name} state is 'not_found' - marking for eviction")
                            slots_to_evict.append((slot_id, slot_data))
                            break
                        elif state == 'failed':
                            logger.warning(
                                f"Slot {slot_id} pipeline {pipeline_name} has failed (reload failures) - marking for eviction")
                            slots_to_evict.append((slot_id, slot_data))
                            break

                # Evict the failed slots
                for slot_id, slot_data in slots_to_evict:
                    del _slots[slot_id]
                    evicted_slots.append(slot_id)

            # Delete Logstash pipelines for evicted slots (outside the lock)
            for slot_id, slot_data in slots_to_evict:
                _delete_slot_pipelines(slot_id, slot_data)

            if evicted_slots:
                logger.info(f"Evicted {len(evicted_slots)} failed slots: {evicted_slots}")

    except Exception as e:
        logger.error(f"Error during API-based slot eviction: {e}")
        # Fall back to log-based detection if API fails
        logger.warning("Falling back to log-based detection")
        return _evict_failed_slots_fallback()

    return evicted_slots


def _evict_failed_slots_fallback() -> List[int]:
    """
    Fallback to log-based eviction if API is unavailable.
    This is the old implementation kept as a safety net.
    """
    evicted_slots = []

    try:
        logs = log_analyzer._read_json_logs(max_lines=1000, reverse=True)
    except Exception as e:
        logger.error(f"Error reading logs for failed slot detection: {e}")
        return evicted_slots

    failed_pipeline_ids = set()

    for log_entry in logs:
        if log_entry.get('level') == 'ERROR':
            log_event = log_entry.get('logEvent', {})
            action_type = log_event.get('action_type', '')
            if 'FailedAction' in action_type:
                pipeline_id = log_event.get('id')
                if pipeline_id and pipeline_id.startswith('slot'):
                    failed_pipeline_ids.add(pipeline_id)

    if not failed_pipeline_ids:
        return evicted_slots

    with _slots_lock:
        slots_to_evict = []
        for slot_id, slot_data in _slots.items():
            pipelines = slot_data.get('pipelines', [])
            for idx in range(1, len(pipelines) + 1):
                pipeline_name = f"slot{slot_id}-filter{idx}"
                if pipeline_name in failed_pipeline_ids:
                    slots_to_evict.append((slot_id, slot_data))
                    break

        for slot_id, slot_data in slots_to_evict:
            del _slots[slot_id]
            evicted_slots.append(slot_id)

    for slot_id, slot_data in slots_to_evict:
        _delete_slot_pipelines(slot_id, slot_data)

    return evicted_slots


async def verify_slot_pipelines_loaded(slot_id: int, expected_count: int, max_wait_seconds: float = 20.0,
                                       poll_interval: float = 1.0) -> bool:
    """
    Verify that all pipelines for a slot have been successfully loaded by Logstash.

    Uses continuous polling of the Logstash API to detect pipeline state changes immediately.
    This provides instant feedback when pipelines fail or succeed.

    Args:
        slot_id: Slot ID (1-10)
        expected_count: Number of pipelines expected for this slot
        max_wait_seconds: Maximum time to wait for pipelines to load (default: 20 seconds)
        poll_interval: How often to poll the API in seconds (default: 0.2 seconds for fast feedback)

    Returns:
        True if all slot pipelines are running, False otherwise
    """
    import asyncio
    import time

    logger.info(
        f"Verifying slot {slot_id} pipelines (polling every {poll_interval}s, max wait: {max_wait_seconds}s)...")
    start_time = time.time()
    attempt = 0
    
    # Track when we first see each pipeline to detect initialization vs. actual failures
    first_seen = {}
    
    # Grace period for pipelines to appear in Logstash API (config reload detection time)
    # Logstash config.reload.automatic is typically 1-3 seconds
    GRACE_PERIOD_SECONDS = 5.0

    # Track baseline reload counters for each pipeline to detect NEW failures
    # Logstash reload counters are cumulative and persist across pipeline deletions
    baseline_reload_counters = {}
    
    try:
        with LogstashAPI(timeout=5.0) as api:
            while True:
                attempt += 1
                elapsed = time.time() - start_time

                try:
                    # Check if all slot pipelines are loaded
                    slot_pipelines = [f"slot{slot_id}-filter{i}" for i in range(1, expected_count + 1)]
                    not_found_pipelines = []
                    failed_pipelines = []
                    loaded_pipelines = []

                    for pipeline_name in slot_pipelines:
                        # Get detailed pipeline stats to check reload counters
                        try:
                            stats = api.get_pipeline_stats(pipeline_name)
                            pipeline_data = stats.get('pipelines', {}).get(pipeline_name, {})
                            reloads = pipeline_data.get('reloads', {})
                            current_failures = reloads.get('failures', 0)
                            current_successes = reloads.get('successes', 0)
                            
                            # Set baseline on first check of this pipeline
                            if pipeline_name not in baseline_reload_counters:
                                baseline_reload_counters[pipeline_name] = {
                                    'failures': current_failures,
                                    'successes': current_successes
                                }
                                logger.debug(f"Pipeline {pipeline_name} - baseline: failures={current_failures}, successes={current_successes}")
                            
                            # Calculate NEW failures/successes since baseline
                            baseline = baseline_reload_counters[pipeline_name]
                            new_failures = current_failures - baseline['failures']
                            new_successes = current_successes - baseline['successes']
                            
                            # Check if there are NEW failures (not historical ones)
                            if new_failures > 0 and new_failures >= new_successes:
                                failed_pipelines.append(pipeline_name)
                                logger.error(f"Pipeline {pipeline_name} has NEW failures (new_failures={new_failures}, new_successes={new_successes}, baseline_failures={baseline['failures']})")
                                continue
                                
                        except Exception as e:
                            logger.debug(f"Could not get detailed stats for {pipeline_name}: {e}")
                        
                        # Use standard state detection
                        state = api.detect_pipeline_state(pipeline_name)
                        
                        # Track when we first see this pipeline
                        if pipeline_name not in first_seen and state != 'not_found':
                            first_seen[pipeline_name] = time.time()

                        if state == 'not_found':
                            not_found_pipelines.append(pipeline_name)
                        elif state == 'idle':
                            # Pipeline exists and loaded successfully - but check if it's truly ready
                            # Logstash can report a pipeline as 'idle' while it's still initializing
                            # (events structure exists but pipeline isn't accepting events yet)
                            # Wait at least 2 seconds after first seeing the pipeline to ensure it's started
                            if pipeline_name in first_seen:
                                time_since_first_seen = time.time() - first_seen[pipeline_name]
                                if time_since_first_seen >= 2.0:
                                    loaded_pipelines.append(pipeline_name)
                                    logger.debug(f"Pipeline {pipeline_name} is idle (loaded successfully, stable for {time_since_first_seen:.1f}s)")
                                else:
                                    # Pipeline just appeared, wait a bit longer to ensure it's truly ready
                                    logger.debug(f"Pipeline {pipeline_name} is idle but only seen for {time_since_first_seen:.1f}s, waiting for stability")
                                    not_found_pipelines.append(pipeline_name)
                            else:
                                # First time seeing this pipeline as idle, wait for next check
                                logger.debug(f"Pipeline {pipeline_name} is idle (first detection, waiting for stability)")
                                not_found_pipelines.append(pipeline_name)
                        elif state == 'running':
                            # Pipeline is actively processing - it's definitely ready!
                            loaded_pipelines.append(pipeline_name)
                            logger.debug(f"Pipeline {pipeline_name} is running")

                    # Check for failed pipelines first - FAIL IMMEDIATELY for fast feedback
                    if failed_pipelines:
                        logger.error(f"✗ Pipelines failed to load (NEW failures detected): {failed_pipelines}")
                        return False

                    # All pipelines found and loaded (either idle or running) - SUCCESS IMMEDIATELY
                    if len(loaded_pipelines) == expected_count:
                        logger.info(
                            f"+ All {expected_count} pipelines for slot {slot_id} are loaded (took {elapsed:.2f}s, {attempt} checks)")
                        return True

                    # Check if we've exceeded max wait time
                    if elapsed >= max_wait_seconds:
                        logger.error(
                            f"✗ Pipelines still not loaded after {elapsed:.2f}s ({attempt} checks): not_found={not_found_pipelines}, loaded={len(loaded_pipelines)}/{expected_count}")
                        return False

                    # Some pipelines are still not found - wait and retry
                    if elapsed > 5.0:
                        # Log at INFO level if taking longer than 5 seconds to help debug slow loads
                        logger.info(
                            f"Check {attempt} ({elapsed:.2f}s): Waiting for pipelines - loaded: {len(loaded_pipelines)}/{expected_count}, not_found: {not_found_pipelines}")
                    else:
                        logger.debug(f"Check {attempt} ({elapsed:.2f}s): Loaded {len(loaded_pipelines)}/{expected_count}, waiting for: {not_found_pipelines}")
                    await asyncio.sleep(poll_interval)

                except Exception as e:
                    logger.error(f"Error checking pipeline status (check {attempt}, {elapsed:.2f}s): {e}")
                    # On error, wait and retry (unless we've exceeded max wait time)
                    if elapsed >= max_wait_seconds:
                        logger.error(f"✗ Failed to verify pipelines after {elapsed:.2f}s due to errors")
                        return False
                    await asyncio.sleep(poll_interval)

    except Exception as e:
        logger.error(f"Failed to verify slot {slot_id} pipelines via API: {e}")
        # Fallback to log-based verification
        logger.warning("Falling back to log-based verification")
        return await _verify_slot_pipelines_loaded_fallback(slot_id, expected_count)


async def _verify_slot_pipelines_loaded_fallback(slot_id: int, expected_count: int, max_retries: int = 3,
                                                 retry_delay: float = 1.0) -> bool:
    """
    Fallback to log-based verification if API is unavailable.
    This is the old implementation kept as a safety net.
    """
    import asyncio

    for attempt in range(max_retries):
        try:
            pipeline_status = log_analyzer.get_running_pipelines()

            if not pipeline_status:
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: No pipeline status found in logs yet")
                await asyncio.sleep(retry_delay)
                continue

            running_pipelines = pipeline_status.get('running_pipelines', [])
            slot_pipelines = [f"slot{slot_id}-filter{i}" for i in range(1, expected_count + 1)]
            missing_pipelines = [p for p in slot_pipelines if p not in running_pipelines]

            if not missing_pipelines:
                logger.info(f"+ All {expected_count} pipelines for slot {slot_id} are running (fallback)")
                return True

            logger.warning(f"Attempt {attempt + 1}/{max_retries}: Waiting for pipelines: {missing_pipelines}")
            await asyncio.sleep(retry_delay)

        except Exception as e:
            logger.error(f"Error checking pipeline status (attempt {attempt + 1}/{max_retries}): {e}")
            await asyncio.sleep(retry_delay)

    logger.error(f"X Failed to verify slot {slot_id} pipelines after {max_retries} attempts")
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
    Runs every 15 seconds to quickly catch and clean up failed pipelines.
    """
    while True:
        try:
            time.sleep(60)

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
        logger.warning(f"[Slots] Config file not found at {config_path}, using defaults")
        return {}

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except Exception as e:
        logger.error(f"[Slots] Error loading config: {e}, using defaults")
        return {}


# Conditionally start the background cleanup thread based on config
_config = _load_config()
_mode = _config.get('mode', '').lower()

if _mode == 'simulation':
    _cleanup_thread = Thread(target=_background_cleanup_worker, daemon=True, name="SlotCleanupThread")
    _cleanup_thread.start()
    logger.info("[Slots] Started background cleanup thread (mode: simulation)")
else:
    logger.warning(f"[Slots] Background cleanup thread NOT started (mode: {_mode or 'not set'})")
