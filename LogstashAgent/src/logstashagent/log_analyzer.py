#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Logstash Log Analyzer Library

This module provides functions to analyze Logstash JSON logs for pipeline health
monitoring and error detection during simulations.

Log files are expected to be in JSON format (one JSON object per line) located at:
/var/log/logstash/logstash-json.log and rotated files logstash-json-*.log
"""

import json
import glob
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

# Default log directory
LOG_DIR = "/var/log/logstash"
LOG_PATTERN = "logstash-json*.log"


def _read_json_logs(log_dir: str = LOG_DIR, pattern: str = LOG_PATTERN,
                    max_lines: Optional[int] = None, reverse: bool = True) -> List[Dict[str, Any]]:
    """
    Read and parse JSON log files.

    Args:
        log_dir: Directory containing log files
        pattern: Glob pattern for log files
        max_lines: Maximum number of lines to read (None for all)
        reverse: If True, read files in reverse order (newest first) and read from end of file

    Returns:
        List of parsed JSON log entries
    """
    search_path = str(Path(log_dir) / pattern)
    log_files = sorted(glob.glob(search_path))

    logger.debug(f"Searching for logs: {search_path}")
    logger.debug(f"Found {len(log_files)} log files: {log_files}")

    if not log_files:
        return []

    if reverse:
        log_files = log_files[::-1]

    logs = []
    lines_read = 0

    for log_file in log_files:
        try:
            # If reading in reverse and we have a max_lines limit, read from end of file
            if reverse and max_lines:
                # Read last N lines efficiently using tail-like approach
                with open(log_file, 'rb') as f:
                    # Seek to end
                    f.seek(0, 2)
                    file_size = f.tell()
                    
                    # Estimate bytes per line (assume ~500 bytes average)
                    estimated_bytes = (max_lines - lines_read) * 500
                    seek_pos = max(0, file_size - estimated_bytes)
                    f.seek(seek_pos)
                    
                    # Read and decode
                    content = f.read().decode('utf-8', errors='ignore')
                    file_lines = content.split('\n')
                    
                    # If we didn't start at beginning, skip first partial line
                    if seek_pos > 0:
                        file_lines = file_lines[1:]
                    
                    # Reverse to get newest first
                    file_lines.reverse()
                    
                    for line in file_lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            log_entry = json.loads(line)
                            logs.append(log_entry)
                            lines_read += 1
                            
                            if lines_read >= max_lines:
                                logger.debug(f"Read {lines_read} lines from {log_file}")
                                return logs
                        except json.JSONDecodeError:
                            continue
            else:
                # Original sequential reading for non-reverse or unlimited reads
                with open(log_file, 'r', encoding='utf-8') as f:
                    file_lines = 0
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            log_entry = json.loads(line)
                            logs.append(log_entry)
                            lines_read += 1
                            file_lines += 1

                            if max_lines and lines_read >= max_lines:
                                logger.debug(f"Read {file_lines} lines from {log_file}")
                                return logs
                        except json.JSONDecodeError as e:
                            # Skip malformed JSON lines
                            continue
                    logger.debug(f"Read {file_lines} lines from {log_file}")
        except (IOError, OSError) as e:
            logger.error(f"Error reading {log_file}: {e}")
            continue

    return logs


def get_running_pipelines(log_dir: str = LOG_DIR) -> Optional[Dict[str, Any]]:
    """
    Get the most recent pipeline status from logs.

    Searches for the last log entry with 'running_pipelines' field to determine
    which pipelines are currently running.

    Args:
        log_dir: Directory containing log files

    Returns:
        Dictionary containing:
        - running_pipelines: List of pipeline IDs that are running
        - non_running_pipelines: List of pipeline IDs that are not running
        - count: Total count of running pipelines
        - timestamp: When this status was logged

        Returns None if no pipeline status found in logs.

    Example:
        {
            "running_pipelines": ["simulate-end", "simulate-start", "slot1-filter1"],
            "non_running_pipelines": [],
            "count": 3,
            "timestamp": 1771269108232
        }
    """
    # Read recent logs (200 lines should be enough for pipeline status)
    logs = _read_json_logs(log_dir=log_dir, max_lines=200, reverse=True)

    logger.debug(f"Read {len(logs)} log entries from {log_dir}")

    # Collect ALL entries with running_pipelines and find the most recent by timestamp
    pipeline_status_entries = []

    for log_entry in logs:
        log_event = log_entry.get('logEvent', {})

        if 'running_pipelines' in log_event:
            timestamp = log_entry.get('timeMillis', 0)
            pipeline_status_entries.append({
                'running_pipelines': log_event.get('running_pipelines', []),
                'non_running_pipelines': log_event.get('non_running_pipelines', []),
                'count': log_event.get('count', 0),
                'timestamp': timestamp,
                'level': log_entry.get('level'),
                'message': log_event.get('message'),
                'raw_event': log_event
            })

    if not pipeline_status_entries:
        logger.warning(f"No running_pipelines found in {len(logs)} log entries")
        return None

    # Sort by timestamp descending (most recent first) and take the first one
    pipeline_status_entries.sort(key=lambda x: x['timestamp'], reverse=True)
    result = pipeline_status_entries[0]

    # Debug: show the raw log entry
    logger.debug(f"Found {len(pipeline_status_entries)} pipeline status entries")
    logger.debug(f"Most recent timestamp: {result['timestamp']}")
    logger.debug(f"Raw logEvent: {json.dumps(result['raw_event'], indent=2)}")

    # Remove raw_event from result before returning
    del result['raw_event']
    
    # Check for FailedAction errors that occurred after this status timestamp
    # and remove those pipelines from the running list
    status_timestamp = result['timestamp']
    failed_pipelines = set()
    
    for log_entry in logs:
        log_timestamp = log_entry.get('timeMillis', 0)
        
        # Only check logs newer than or equal to the status timestamp
        if log_timestamp < status_timestamp:
            continue
            
        if log_entry.get('level') == 'ERROR':
            log_event = log_entry.get('logEvent', {})
            action_type = log_event.get('action_type', '')
            
            if 'FailedAction' in action_type:
                pipeline_id = log_event.get('id')
                if pipeline_id:
                    failed_pipelines.add(pipeline_id)
                    logger.debug(f"Found FailedAction for pipeline {pipeline_id} at timestamp {log_timestamp}")
    
    # Remove failed pipelines from running_pipelines list
    if failed_pipelines:
        original_running = result['running_pipelines'][:]
        result['running_pipelines'] = [p for p in result['running_pipelines'] if p not in failed_pipelines]
        logger.warning(f"Removed {len(failed_pipelines)} failed pipelines from running list: {failed_pipelines}")
        logger.debug(f"Running pipelines before: {original_running}")
        logger.debug(f"Running pipelines after: {result['running_pipelines']}")

    logger.debug(f"Found running_pipelines: {result['running_pipelines']}")
    return result


def find_related_logs(pipeline_id: str, log_dir: str = LOG_DIR,
                      max_entries: int = 100,
                      min_level: str = "WARN",
                      min_timestamp: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Find all log entries related to a specific pipeline.

    Searches logs for entries that mention the given pipeline_id, typically
    used to find errors, warnings, and other issues related to a pipeline.

    Args:
        pipeline_id: The pipeline ID to search for (e.g., "slot4-filter1")
        log_dir: Directory containing log files
        max_entries: Maximum number of log entries to return
        min_level: Minimum log level to include (DEBUG, INFO, WARN, ERROR)
        min_timestamp: Optional minimum timestamp in milliseconds. Only logs at or after this time will be included.

    Returns:
        List of log entries related to the pipeline, sorted by timestamp (newest first).
        Each entry includes the full log structure with fields like:
        - level: Log level (WARN, ERROR, etc.)
        - loggerName: Logger that produced the message
        - timeMillis: Timestamp in milliseconds
        - thread: Thread name (often contains pipeline info)
        - pipeline.id: Pipeline ID (if present)
        - plugin.id: Plugin ID (if present)
        - logEvent: The actual log event data including message and event details

    Example:
        [
            {
                "level": "WARN",
                "loggerName": "org.logstash.dissect.Dissector",
                "timeMillis": 1771269132430,
                "thread": "[slot4-filter1]>worker0",
                "pipeline.id": "slot4-filter1",
                "logEvent": {
                    "message": "Dissector mapping, field found in event but it was empty",
                    "field": "url.original",
                    "event": {...}
                }
            }
        ]
    """
    # Define log level hierarchy
    level_priority = {
        'DEBUG': 0,
        'INFO': 1,
        'WARN': 2,
        'ERROR': 3,
        'FATAL': 4
    }

    min_priority = level_priority.get(min_level.upper(), 0)

    # Read recent logs (search more lines for pipeline-specific logs)
    logs = _read_json_logs(log_dir=log_dir, max_lines=5000, reverse=True)

    related_logs = []

    for log_entry in logs:
        # Filter by timestamp if min_timestamp is provided
        if min_timestamp is not None:
            log_timestamp = log_entry.get('timeMillis', 0)
            if log_timestamp < min_timestamp:
                continue  # Skip logs older than the minimum timestamp
        
        # Check if this log entry is related to the pipeline
        is_related = False

        # Check pipeline.id field
        if log_entry.get('pipeline.id') == pipeline_id:
            is_related = True

        # Check thread name (often contains pipeline ID like "[slot4-filter1]>worker0")
        thread = log_entry.get('thread', '')
        if pipeline_id in thread:
            is_related = True

        # Check logEvent for pipeline references
        log_event = log_entry.get('logEvent', {})
        if isinstance(log_event, dict):
            # Check if event data contains run_id or slot info that matches
            event_data = log_event.get('event', {})
            if isinstance(event_data, dict):
                # Check snapshots for pipeline references
                snapshots = event_data.get('snapshots', {})
                if isinstance(snapshots, dict) and any(pipeline_id in str(v) for v in snapshots.values()):
                    is_related = True

        if is_related:
            # Check log level
            entry_level = log_entry.get('level', 'INFO').upper()
            entry_priority = level_priority.get(entry_level, 0)

            if entry_priority >= min_priority:
                related_logs.append(log_entry)

                if len(related_logs) >= max_entries:
                    break

    return related_logs


# Keywords in logEvent.message that indicate a graceful Logstash shutdown
_SHUTDOWN_KEYWORDS = [
    "logstash shutdown completed",
    "stopping all pipelines",
    "pipeline terminated",
    "shutting down",
]

# Minimum milliseconds between consecutive running_pipelines entries before
# we consider the gap a possible crash-restart (no explicit down entry logged)
_CRASH_GAP_THRESHOLD_MS = 5000


def _check_for_shutdown_message(logs: List[Dict[str, Any]], near_timestamp: int,
                                 window_ms: int = 10000) -> bool:
    """
    Return True if any log entry within window_ms of near_timestamp contains a
    known Logstash shutdown message keyword.
    """
    lo = near_timestamp - window_ms
    hi = near_timestamp + window_ms
    for entry in logs:
        ts = entry.get('timeMillis', 0)
        if not (lo <= ts <= hi):
            continue
        message = entry.get('logEvent', {}).get('message', '')
        if isinstance(message, str):
            msg_lower = message.lower()
            if any(kw in msg_lower for kw in _SHUTDOWN_KEYWORDS):
                return True
    return False


def _extract_cause_hint(logs: List[Dict[str, Any]], shutdown_timestamp: int,
                        window_ms: int = 10000) -> str:
    """
    Inspect logs near shutdown_timestamp for clues about what caused the restart.

    Returns a short string like "FailedAction", "OOM", "graceful shutdown", or "unknown".
    """
    lo = shutdown_timestamp - window_ms
    hi = shutdown_timestamp + window_ms

    for entry in logs:
        ts = entry.get('timeMillis', 0)
        if not (lo <= ts <= hi):
            continue

        log_event = entry.get('logEvent', {})

        # FailedAction errors from existing detection logic
        if entry.get('level') == 'ERROR':
            action_type = log_event.get('action_type', '')
            if 'FailedAction' in action_type:
                return 'FailedAction'

        # OOM indicators in message
        message = log_event.get('message', '')
        if isinstance(message, str):
            msg_lower = message.lower()
            if 'out of memory' in msg_lower or 'outofmemory' in msg_lower:
                return 'OOM'
            if any(kw in msg_lower for kw in _SHUTDOWN_KEYWORDS):
                return 'graceful shutdown'

    return 'unknown'


def detect_restart_events(
    log_dir: str = LOG_DIR,
    since_timestamp: Optional[int] = None,
    max_events: int = 10,
    max_lines: int = 500
) -> List[Dict[str, Any]]:
    """
    Detect Logstash restart events by analysing running_pipelines log transitions.

    Reads up to max_lines from the *end* of the log files (efficient tail-style read),
    then processes entries chronologically to find:
      - Graceful restarts: running_pipelines goes non-empty → empty, then back
      - Crash restarts: a gap > 5 seconds between consecutive non-empty entries
        with no explicit "down" entry in between
      - Pipeline reload loops: a single pipeline disappears and reappears ≥ 3 times
        within 60 seconds (Logstash-internal, process may not restart)

    Args:
        log_dir: Directory containing Logstash JSON log files.
        since_timestamp: Optional lower bound (timeMillis). Events whose
            shutdown_timestamp is older than this are excluded.
        max_events: Maximum number of events to return.
        max_lines: How many lines to read from the end of log files.
            Increase for longer lookback. Default 500 is sufficient for the
            "is it currently restarting?" question without reading the whole file.

    Returns:
        List of restart event dicts, newest first:
        {
            "type": "graceful" | "crash" | "pipeline_loop",
            "shutdown_timestamp": int,       # timeMillis of detected shutdown
            "startup_timestamp": int | None, # timeMillis of detected startup (None if still down)
            "is_complete": bool,
            "duration_ms": int | None,
            "cause_hint": str,               # "graceful shutdown", "FailedAction", "OOM",
                                             #  "gap_detected", "unknown"
        }
    """
    # Read from end of file — avoid re-reading the whole log on every call
    raw_logs = _read_json_logs(log_dir=log_dir, max_lines=max_lines, reverse=True)
    # Reverse to chronological order for transition analysis
    raw_logs.reverse()

    if not raw_logs:
        return []

    # ------------------------------------------------------------------
    # 1. Extract pipeline-status entries in chronological order
    # ------------------------------------------------------------------
    status_entries: List[Dict[str, Any]] = []
    for entry in raw_logs:
        log_event = entry.get('logEvent', {})
        if 'running_pipelines' in log_event:
            ts = entry.get('timeMillis', 0)
            if since_timestamp is not None and ts < since_timestamp:
                continue
            status_entries.append({
                'running_pipelines': log_event.get('running_pipelines', []),
                'count': log_event.get('count', 0),
                'timestamp': ts,
            })

    if not status_entries:
        logger.debug("detect_restart_events: no running_pipelines entries found")
        return []

    # ------------------------------------------------------------------
    # 2. State-machine walk to find restart transitions
    # ------------------------------------------------------------------
    events: List[Dict[str, Any]] = []
    open_event: Optional[Dict[str, Any]] = None  # a shutdown seen, startup not yet

    prev = status_entries[0]
    prev_is_up = prev['count'] > 0 or len(prev['running_pipelines']) > 0

    for status in status_entries[1:]:
        ts = status['timestamp']
        is_up = status['count'] > 0 or len(status['running_pipelines']) > 0
        prev_ts = prev['timestamp']

        if prev_is_up and not is_up:
            # Transition: UP → DOWN  →  shutdown began
            restart_type = 'graceful' if _check_for_shutdown_message(raw_logs, ts) else 'crash'
            cause = _extract_cause_hint(raw_logs, ts)
            open_event = {
                'type': restart_type,
                'shutdown_timestamp': ts,
                'startup_timestamp': None,
                'is_complete': False,
                'duration_ms': None,
                'cause_hint': cause,
            }
            logger.debug(f"detect_restart_events: shutdown at {ts} type={restart_type}")

        elif not prev_is_up and is_up:
            # Transition: DOWN → UP  →  startup complete
            if open_event is not None:
                open_event['startup_timestamp'] = ts
                open_event['is_complete'] = True
                open_event['duration_ms'] = ts - open_event['shutdown_timestamp']
                events.append(open_event)
                logger.debug(f"detect_restart_events: startup at {ts}, duration={open_event['duration_ms']}ms")
                open_event = None
            else:
                # Startup with no preceding explicit down — first entry was already down
                logger.debug(f"detect_restart_events: startup at {ts} with no preceding shutdown entry")

        elif prev_is_up and is_up:
            # Both UP — check for a suspiciously large gap (crash with no down entry logged)
            gap = ts - prev_ts
            if gap > _CRASH_GAP_THRESHOLD_MS:
                events.append({
                    'type': 'crash',
                    'shutdown_timestamp': prev_ts,
                    'startup_timestamp': ts,
                    'is_complete': True,
                    'duration_ms': gap,
                    'cause_hint': 'gap_detected',
                })
                logger.debug(f"detect_restart_events: gap-based crash at {prev_ts} gap={gap}ms")

        prev = status
        prev_is_up = is_up

    # If we still have an open event, Logstash hasn't come back up yet
    if open_event is not None:
        events.append(open_event)
        logger.debug("detect_restart_events: open (incomplete) restart event — Logstash still down")

    # ------------------------------------------------------------------
    # 3. Pipeline reload loop detection
    # ------------------------------------------------------------------
    LOOP_WINDOW_MS = 60_000
    LOOP_MIN_CYCLES = 3

    # Track per-pipeline appearance/disappearance counts within rolling windows
    pipeline_events: Dict[str, List[int]] = {}  # pipeline_id → list of appearance timestamps
    for status in status_entries:
        ts = status['timestamp']
        for pid in status['running_pipelines']:
            pipeline_events.setdefault(pid, []).append(ts)

    for pid, appearances in pipeline_events.items():
        if len(appearances) < LOOP_MIN_CYCLES:
            continue
        # Slide over appearances and look for LOOP_MIN_CYCLES within LOOP_WINDOW_MS
        for i in range(len(appearances) - LOOP_MIN_CYCLES + 1):
            window_start = appearances[i]
            window_end = appearances[i + LOOP_MIN_CYCLES - 1]
            if (window_end - window_start) <= LOOP_WINDOW_MS:
                # Check that the pipeline also *disappeared* inside this window
                # by verifying it was absent from at least one status entry between appearances
                window_statuses = [s for s in status_entries
                                   if window_start <= s['timestamp'] <= window_end]
                absent = any(pid not in s['running_pipelines'] for s in window_statuses)
                if absent:
                    events.append({
                        'type': 'pipeline_loop',
                        'shutdown_timestamp': window_start,
                        'startup_timestamp': window_end,
                        'is_complete': True,
                        'duration_ms': window_end - window_start,
                        'cause_hint': f'pipeline {pid} reloading repeatedly',
                    })
                    logger.warning(
                        f"detect_restart_events: pipeline_loop for {pid} "
                        f"({LOOP_MIN_CYCLES}+ cycles in {window_end - window_start}ms)"
                    )
                    break  # one loop event per pipeline is enough

    # ------------------------------------------------------------------
    # 4. Return newest-first, capped at max_events
    # ------------------------------------------------------------------
    events.sort(key=lambda e: e['shutdown_timestamp'], reverse=True)
    return events[:max_events]


def is_logstash_restarting(log_dir: str = LOG_DIR) -> bool:
    """
    Return True if Logstash appears to be mid-restart right now.

    Uses a short lookback (500 lines from end of log) so it is cheap to call
    repeatedly (e.g. from a health-check loop or UI polling endpoint).

    Returns:
        True if the most recent restart event is incomplete (shutdown seen,
        startup not yet observed in logs). False otherwise.
    """
    events = detect_restart_events(log_dir=log_dir, max_events=1, max_lines=500)
    if not events:
        return False
    latest = events[0]
    return not latest['is_complete']


def is_pipeline_running(pipeline_id: str, log_dir: str = LOG_DIR) -> bool:
    """
    Check if a specific pipeline is currently running.
    
    Args:
        pipeline_id: The pipeline ID to check
        log_dir: Directory containing log files
    
    Returns:
        True if the pipeline is in the running_pipelines list, False otherwise
    """
    status = get_running_pipelines(log_dir=log_dir)
    
    if not status:
        return False
    
    return pipeline_id in status.get('running_pipelines', [])