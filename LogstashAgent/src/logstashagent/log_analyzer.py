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
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

# Default log directory
LOG_DIR = "/var/log/logstash"
LOG_PATTERN = "logstash-json*.log"

# Agent log directory (relative to this file's location — main.py writes here)
AGENT_LOG_DIR = Path(__file__).parent / "data" / "logs"
AGENT_LOG_PATTERN = "logstashagent*.log"

# Regex patterns for agent log lines
# Format: [LEVEL] YYYY-MM-DD HH:MM:SS module funcname: message
_AGENT_LOG_LINE_RE = re.compile(
    r'^\[(?P<level>\w+)\]\s+'
    r'(?P<datetime>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+'
    r'(?P<module>\S+)\s+(?P<func>\S+):\s+(?P<message>.+)$'
)
# Specific messages we care about
_AGENT_RESTART_RE = re.compile(r'Restarting Logstash \(restart #(\d+)\): (.+)')
_AGENT_STARTED_RE = re.compile(r'Logstash started with PID (\d+)')
_AGENT_DIED_RE    = re.compile(r'Logstash process died \(exit code: (.+)\)')


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


def _read_agent_logs(agent_log_dir: Path = AGENT_LOG_DIR,
                     max_lines: int = 500,
                     since_timestamp: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Read the agent's own rotating log file and return parsed entries for
    restart-relevant messages (restart initiated, process died, started).

    Reads from the end of the file (newest-first), then reverses to chronological
    order so callers always get entries oldest-first.

    Returns list of dicts with keys:
        level, datetime_str, module, func, message, timestamp_ms,
        event_type ("restart_initiated"|"process_died"|"started"),
        restart_count (int, for restart_initiated),
        reason (str, for restart_initiated / process_died),
        pid (int, for started)
    """
    search_path = str(agent_log_dir / AGENT_LOG_PATTERN)
    log_files = sorted(glob.glob(search_path), reverse=True)  # newest file first

    if not log_files:
        logger.debug(f"No agent log files found at {search_path}")
        return []

    entries: List[Dict[str, Any]] = []
    lines_read = 0

    for log_file in log_files:
        try:
            with open(log_file, 'rb') as f:
                f.seek(0, 2)
                file_size = f.tell()
                estimated_bytes = (max_lines - lines_read) * 200
                seek_pos = max(0, file_size - estimated_bytes)
                f.seek(seek_pos)
                content = f.read().decode('utf-8', errors='ignore')
                file_lines = content.split('\n')
                if seek_pos > 0:
                    file_lines = file_lines[1:]
                file_lines.reverse()  # newest first

            for raw_line in file_lines:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                m = _AGENT_LOG_LINE_RE.match(raw_line)
                if not m:
                    continue

                try:
                    dt = datetime.strptime(m.group('datetime'), '%Y-%m-%d %H:%M:%S')
                    ts_ms = int(dt.timestamp() * 1000)
                except ValueError:
                    continue

                if since_timestamp is not None and ts_ms < since_timestamp:
                    continue

                message = m.group('message')

                # Only keep lines relevant to restart detection
                event_type = None
                extra: Dict[str, Any] = {}

                rm = _AGENT_RESTART_RE.search(message)
                if rm:
                    event_type = 'restart_initiated'
                    extra['restart_count'] = int(rm.group(1))
                    extra['reason'] = rm.group(2).strip()

                elif _AGENT_DIED_RE.search(message):
                    dm = _AGENT_DIED_RE.search(message)
                    event_type = 'process_died'
                    extra['reason'] = f"exit code: {dm.group(1)}"

                elif _AGENT_STARTED_RE.search(message):
                    sm = _AGENT_STARTED_RE.search(message)
                    event_type = 'started'
                    extra['pid'] = int(sm.group(1))

                if event_type is None:
                    continue

                entries.append({
                    'level': m.group('level'),
                    'datetime_str': m.group('datetime'),
                    'module': m.group('module'),
                    'func': m.group('func'),
                    'message': message,
                    'timestamp_ms': ts_ms,
                    'event_type': event_type,
                    **extra,
                })
                lines_read += 1
                if lines_read >= max_lines:
                    break

        except (IOError, OSError) as e:
            logger.error(f"Error reading agent log {log_file}: {e}")
            continue

        if lines_read >= max_lines:
            break

    # Return in chronological order (oldest first)
    entries.reverse()
    return entries


def _find_logstash_lifecycle_events(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Scan already-read Logstash JSON log entries for explicit shutdown and startup
    messages emitted by Logstash itself.

    Uses the module-level _SHUTDOWN_KEYWORDS and _STARTUP_KEYWORDS lists.
    Matched case-insensitively as substrings of logEvent.message.

    Returns list of dicts (chronological order):
        {"event_type": "shutdown"|"startup", "timestamp": int, "message": str}
    """
    events: List[Dict[str, Any]] = []

    for entry in logs:
        ts = entry.get('timeMillis', 0)
        message = entry.get('logEvent', {}).get('message', '')
        if not isinstance(message, str) or not message:
            continue
        msg_lower = message.lower()

        if any(kw in msg_lower for kw in _SHUTDOWN_KEYWORDS):
            events.append({'event_type': 'shutdown', 'timestamp': ts, 'message': message})
        elif any(kw in msg_lower for kw in _STARTUP_KEYWORDS):
            events.append({'event_type': 'startup', 'timestamp': ts, 'message': message})

    # Sort chronologically
    events.sort(key=lambda e: e['timestamp'])
    return events


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


# Process-level shutdown keywords — only messages emitted by the Logstash
# process itself as it exits. Pipeline-level messages ("Pipeline terminated",
# "Stopping all pipelines") are intentionally excluded: they fire on config
# reloads and pipeline restarts within a running process, which would create
# false shutdown signals and break restart pairing logic.
_SHUTDOWN_KEYWORDS = [
    "logstash shut down",   # "Logstash shut down."  — process has fully exited
    "shutting down",        # "SIGTERM received. Shutting down." — process is exiting
]

# Process-level startup keywords — only messages that are emitted exactly
# once per Logstash process startup. Pipeline-level messages ("Pipelines
# running", "Pipeline started") are excluded because they also fire on config
# reloads within a running process, creating false startup signals.
# The running_pipelines metric transitions (Source C in detect_restart_events)
# handle pipeline-level state changes separately.
_STARTUP_KEYWORDS = [
    "successfully started logstash",  # "Successfully started Logstash API endpoint"
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
    agent_log_dir: Path = AGENT_LOG_DIR,
    since_timestamp: Optional[int] = None,
    max_events: int = 10,
    max_lines: int = 500
) -> List[Dict[str, Any]]:
    """
    Detect Logstash restart events from three complementary signal sources:

      1. Agent logs (``data/logs/logstashagent.log``) — direct evidence of
         agent-initiated restarts with the reason string and restart count.
         These are the most authoritative for restarts the agent kicked off.

      2. Logstash JSON log lifecycle messages — explicit "Shutting down" /
         "Logstash started" messages emitted by Logstash itself. These cover
         external restarts (systemd, manual ``systemctl restart``) that the
         agent did not initiate.

      3. ``running_pipelines`` metric transitions — periodic status entries
         going non-empty→empty and back. Used as a fallback signal and for
         gap-based crash detection when neither explicit message source fires.

    Reads up to max_lines from the *end* of each log file (efficient tail-style
    read), so repeated calls stay cheap.

    Args:
        log_dir: Directory containing Logstash JSON log files.
        agent_log_dir: Directory containing the agent's own rotating log files.
        since_timestamp: Optional lower bound (timeMillis). Events older than
            this are excluded.
        max_events: Maximum number of events to return.
        max_lines: Lines to tail from each log file. 500 is sufficient for
            "is it currently restarting?"; increase for longer history.

    Returns:
        List of restart event dicts, newest-first:
        {
            "type": "graceful" | "crash" | "pipeline_loop",
            "shutdown_timestamp": int,
            "startup_timestamp": int | None,
            "is_complete": bool,
            "duration_ms": int | None,
            "cause_hint": str,   # e.g. "agent: Process crash (exit code: 1)",
                                 #       "graceful shutdown", "OOM",
                                 #       "FailedAction", "gap_detected", "unknown"
        }
    """
    # ------------------------------------------------------------------
    # Read log sources (tail-only, chronological order for processing)
    # ------------------------------------------------------------------
    raw_logs = _read_json_logs(log_dir=log_dir, max_lines=max_lines, reverse=True)
    raw_logs.reverse()  # chronological order

    agent_entries = _read_agent_logs(
        agent_log_dir=agent_log_dir,
        max_lines=max_lines,
        since_timestamp=since_timestamp,
    )

    # ------------------------------------------------------------------
    # 1. Collect shutdown signals from all sources
    #    Each signal: {"timestamp": int, "source": str, "cause_hint": str}
    # ------------------------------------------------------------------
    DEDUP_WINDOW_MS = 10_000  # signals within 10s of each other = same event

    shutdown_signals: List[Dict[str, Any]] = []
    startup_signals:  List[Dict[str, Any]] = []

    # Source A: explicit Logstash lifecycle messages in JSON logs
    lifecycle = _find_logstash_lifecycle_events(raw_logs)
    for ev in lifecycle:
        if ev['event_type'] == 'shutdown':
            shutdown_signals.append({
                'timestamp': ev['timestamp'],
                'source': 'logstash_message',
                'cause_hint': 'graceful shutdown',
            })
        else:
            startup_signals.append({
                'timestamp': ev['timestamp'],
                'source': 'logstash_message',
            })

    # Source B: agent log entries
    for ae in agent_entries:
        if ae['event_type'] == 'restart_initiated':
            shutdown_signals.append({
                'timestamp': ae['timestamp_ms'],
                'source': 'agent_log',
                'cause_hint': f"agent: {ae.get('reason', 'unknown')}",
                'restart_count': ae.get('restart_count'),
            })
        elif ae['event_type'] == 'process_died':
            shutdown_signals.append({
                'timestamp': ae['timestamp_ms'],
                'source': 'agent_log',
                'cause_hint': f"agent: {ae.get('reason', 'process died')}",
            })
        elif ae['event_type'] == 'started':
            startup_signals.append({
                'timestamp': ae['timestamp_ms'],
                'source': 'agent_log',
                'pid': ae.get('pid'),
            })

    # Source C: running_pipelines metric transitions
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

    if status_entries:
        prev = status_entries[0]
        prev_is_up = prev['count'] > 0 or bool(prev['running_pipelines'])
        for status in status_entries[1:]:
            ts = status['timestamp']
            is_up = status['count'] > 0 or bool(status['running_pipelines'])
            prev_ts = prev['timestamp']

            if prev_is_up and not is_up:
                # running_pipelines went to 0
                shutdown_signals.append({
                    'timestamp': ts,
                    'source': 'pipeline_metric',
                    'cause_hint': _extract_cause_hint(raw_logs, ts),
                })
            elif not prev_is_up and is_up:
                # running_pipelines came back
                startup_signals.append({
                    'timestamp': ts,
                    'source': 'pipeline_metric',
                })
            elif prev_is_up and is_up:
                # Both up — check for gap indicating a crash with no down entry logged
                gap = ts - prev_ts
                if gap > _CRASH_GAP_THRESHOLD_MS:
                    shutdown_signals.append({
                        'timestamp': prev_ts,
                        'source': 'pipeline_metric_gap',
                        'cause_hint': 'gap_detected',
                    })
                    startup_signals.append({
                        'timestamp': ts,
                        'source': 'pipeline_metric_gap',
                    })

            prev = status
            prev_is_up = is_up

    # ------------------------------------------------------------------
    # 2. Deduplicate signals within DEDUP_WINDOW_MS of each other
    # ------------------------------------------------------------------
    def _dedup(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not signals:
            return []
        signals_sorted = sorted(signals, key=lambda s: s['timestamp'])
        merged: List[Dict[str, Any]] = [signals_sorted[0]]
        for sig in signals_sorted[1:]:
            if sig['timestamp'] - merged[-1]['timestamp'] <= DEDUP_WINDOW_MS:
                # Keep the more informative signal (prefer agent_log > logstash_message > metric)
                priority = {'agent_log': 0, 'logstash_message': 1,
                            'pipeline_metric': 2, 'pipeline_metric_gap': 3}
                existing_pri = priority.get(merged[-1].get('source', ''), 9)
                new_pri      = priority.get(sig.get('source', ''), 9)
                if new_pri < existing_pri:
                    merged[-1] = sig
            else:
                merged.append(sig)
        return merged

    shutdown_signals = _dedup(shutdown_signals)
    startup_signals  = _dedup(startup_signals)

    logger.debug(
        f"detect_restart_events: {len(shutdown_signals)} shutdown signals, "
        f"{len(startup_signals)} startup signals after dedup"
    )

    # ------------------------------------------------------------------
    # 3. Pair each shutdown with the next startup after it
    # ------------------------------------------------------------------
    events: List[Dict[str, Any]] = []
    startup_idx = 0

    for sd in shutdown_signals:
        if since_timestamp is not None and sd['timestamp'] < since_timestamp:
            continue

        # Find first startup signal after this shutdown
        su = None
        while startup_idx < len(startup_signals):
            if startup_signals[startup_idx]['timestamp'] > sd['timestamp']:
                su = startup_signals[startup_idx]
                startup_idx += 1
                break
            startup_idx += 1

        # Classify type: if agent says it was graceful, trust it; else infer from message
        cause_hint = sd.get('cause_hint', 'unknown')
        if sd.get('source') == 'agent_log':
            restart_type = 'graceful' if 'graceful' in cause_hint.lower() else 'crash'
        elif sd.get('source') == 'pipeline_metric_gap':
            restart_type = 'crash'
        elif _check_for_shutdown_message(raw_logs, sd['timestamp']):
            restart_type = 'graceful'
        else:
            restart_type = 'crash'

        event: Dict[str, Any] = {
            'type': restart_type,
            'shutdown_timestamp': sd['timestamp'],
            'startup_timestamp': su['timestamp'] if su else None,
            'is_complete': su is not None,
            'duration_ms': (su['timestamp'] - sd['timestamp']) if su else None,
            'cause_hint': cause_hint,
        }
        if sd.get('restart_count') is not None:
            event['restart_count'] = sd['restart_count']
        if su and su.get('pid'):
            event['pid'] = su['pid']

        events.append(event)
        logger.debug(
            f"detect_restart_events: restart at {sd['timestamp']} "
            f"type={restart_type} source={sd.get('source')} complete={event['is_complete']}"
        )

    # ------------------------------------------------------------------
    # 4. Pipeline reload loop detection (running_pipelines based)
    # ------------------------------------------------------------------
    if status_entries:
        LOOP_WINDOW_MS = 60_000
        LOOP_MIN_CYCLES = 3

        pipeline_appearances: Dict[str, List[int]] = {}
        for status in status_entries:
            for pid in status['running_pipelines']:
                pipeline_appearances.setdefault(pid, []).append(status['timestamp'])

        for pid, appearances in pipeline_appearances.items():
            if len(appearances) < LOOP_MIN_CYCLES:
                continue
            for i in range(len(appearances) - LOOP_MIN_CYCLES + 1):
                window_start = appearances[i]
                window_end   = appearances[i + LOOP_MIN_CYCLES - 1]
                if (window_end - window_start) > LOOP_WINDOW_MS:
                    continue
                window_statuses = [s for s in status_entries
                                   if window_start <= s['timestamp'] <= window_end]
                if any(pid not in s['running_pipelines'] for s in window_statuses):
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
                    break

    # ------------------------------------------------------------------
    # 5. Return newest-first, capped at max_events
    # ------------------------------------------------------------------
    events.sort(key=lambda e: e['shutdown_timestamp'], reverse=True)
    return events[:max_events]


def is_logstash_restarting(log_dir: str = LOG_DIR,
                           agent_log_dir: Path = AGENT_LOG_DIR) -> bool:
    """
    Return True if Logstash appears to be mid-restart right now.

    Checks both the agent log and Logstash JSON logs (500 lines from end of
    each file), so it is cheap to call repeatedly from a health-check loop or
    UI polling endpoint.

    Returns:
        True if the most recent restart event is incomplete (shutdown seen,
        startup not yet observed). False otherwise.
    """
    events = detect_restart_events(
        log_dir=log_dir,
        agent_log_dir=agent_log_dir,
        max_events=1,
        max_lines=500,
    )
    if not events:
        return False
    return not events[0]['is_complete']


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