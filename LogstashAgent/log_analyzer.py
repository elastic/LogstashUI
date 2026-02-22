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
logging.basicConfig(level=logging.DEBUG)
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
    # Read recent logs (last 1000 lines should be enough)
    logs = _read_json_logs(log_dir=log_dir, max_lines=1000, reverse=True)

    logger.info(f"Read {len(logs)} log entries from {log_dir}")

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
    logger.info(f"Found {len(pipeline_status_entries)} pipeline status entries")
    logger.info(f"Most recent timestamp: {result['timestamp']}")
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
                    logger.info(f"Found FailedAction for pipeline {pipeline_id} at timestamp {log_timestamp}")
    
    # Remove failed pipelines from running_pipelines list
    if failed_pipelines:
        original_running = result['running_pipelines'][:]
        result['running_pipelines'] = [p for p in result['running_pipelines'] if p not in failed_pipelines]
        logger.info(f"Removed {len(failed_pipelines)} failed pipelines from running list: {failed_pipelines}")
        logger.info(f"Running pipelines before: {original_running}")
        logger.info(f"Running pipelines after: {result['running_pipelines']}")

    logger.info(f"Found running_pipelines: {result['running_pipelines']}")
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


def get_pipeline_errors(pipeline_id: str, log_dir: str = LOG_DIR,
                       max_entries: int = 50,
                       min_timestamp: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get only ERROR and FATAL level logs for a specific pipeline.

    Args:
        pipeline_id: The pipeline ID to search for
        log_dir: Directory containing log files
        max_entries: Maximum number of errors to return
        min_timestamp: Optional minimum timestamp in milliseconds. Only logs at or after this time will be included.

    Returns:
        List of error log entries for the pipeline
    """
    return find_related_logs(
        pipeline_id=pipeline_id,
        log_dir=log_dir,
        max_entries=max_entries,
        min_level="ERROR",
        min_timestamp=min_timestamp
    )


def get_pipeline_warnings(pipeline_id: str, log_dir: str = LOG_DIR,
                         max_entries: int = 50,
                         min_timestamp: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get WARNING, ERROR, and FATAL level logs for a specific pipeline.

    Args:
        pipeline_id: The pipeline ID to search for
        log_dir: Directory containing log files
        max_entries: Maximum number of warnings to return
        min_timestamp: Optional minimum timestamp in milliseconds. Only logs at or after this time will be included.

    Returns:
        List of warning/error log entries for the pipeline
    """
    return find_related_logs(
        pipeline_id=pipeline_id,
        log_dir=log_dir,
        max_entries=max_entries,
        min_level="WARN",
        min_timestamp=min_timestamp
    )
