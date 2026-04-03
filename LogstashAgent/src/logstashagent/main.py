#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import warnings
# Suppress FastAPI deprecation warnings before importing FastAPI
warnings.filterwarnings("ignore", category=DeprecationWarning)

import sys

# Check early whether we're in a non-simulation mode (--run or --enroll).
# slots starts background threads on import, so we skip it in these modes.
_SKIP_SIMULATION_IMPORTS = '--run' in sys.argv or '--enroll' in sys.argv

from fastapi import FastAPI, HTTPException, Path as FastAPIPath, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import os
import yaml
import json
import glob
import logging
import re
from logstashagent import agent_state, enrollment, log_analyzer, logstash_supervisor, controller
if not _SKIP_SIMULATION_IMPORTS:
    from logstashagent import slots
from logstashagent.logstash_api import LogstashAPI
import requests
import time
import base64
import asyncio
import atexit
from collections import deque
import threading
from pathlib import Path
from logging.handlers import RotatingFileHandler
import argparse
import uvicorn
from importlib.metadata import version, PackageNotFoundError

# Configure logging with file output
# Create data/logs directory if it doesn't exist
LOGS_DIR = Path(__file__).parent / 'data' / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s %(name)s %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        # Console handler
        logging.StreamHandler(),
        # File handler with rotation
        RotatingFileHandler(
            LOGS_DIR / 'logstashagent.log',
            maxBytes=1024 * 1024 * 10,  # 10 MB
            backupCount=5,
        )
    ]
)
logger = logging.getLogger(__name__)

# Reduce httpx logging noise - only show warnings and errors
logging.getLogger("httpx").setLevel(logging.WARNING)

logger.info(f"logstashagent logging initialized - logs directory: {LOGS_DIR}")

# Get agent version from pyproject.toml
def _get_version():
    """Get version from installed package metadata or pyproject.toml"""
    try:
        return version("LogstashAgent")
    except PackageNotFoundError:
        try:
            import tomllib
            # Navigate to LogstashAgent root directory (2 levels up from main.py)
            agent_root = Path(__file__).resolve().parent.parent.parent
            pyproject_path = agent_root / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "rb") as f:
                    pyproject_data = tomllib.load(f)
                    return pyproject_data.get("project", {}).get("version", "0.0.0+unknown")
        except Exception:
            pass
        return "0.0.0+unknown"

AGENT_VERSION = _get_version()

# Initialize agent state (generates agent_id on first run)
AGENT_ID = agent_state.get_or_create_agent_id()

# Save version to agent state
agent_state.update_state('agent_version', AGENT_VERSION)
logger.info(f"LogstashAgent version: {AGENT_VERSION}")

# Load agent configuration
# Check for config in current directory first (native mode)
def get_config_path() -> str:
    """Get the path to logstashagent.yml - only used for native/host mode"""
    local_path = os.path.join(os.path.dirname(__file__), "config/logstashagent.yml")
    return local_path

CONFIG_PATH = get_config_path()

def load_agent_config() -> dict:
    """Load logstashagent.yml configuration, with fallback to logstashui.yml or logstashui.example.yml if mounted"""
    # First, try to load from mounted logstashui.yml (preferred), then logstashui.example.yml
    # Check /app first (docker-compose mounts), then /etc (legacy)
    config_paths = [
        "/app/logstashui.yml",
        "/app/logstashui.example.yml",
        "/etc/logstashui.yml",
        "/etc/logstashui.example.yml"
    ]
    
    for logstashui_config_path in config_paths:
        if os.path.exists(logstashui_config_path):
            try:
                with open(logstashui_config_path, 'r') as f:
                    full_config = yaml.safe_load(f)
                    # logstash_agent is nested under simulation section
                    if full_config and 'simulation' in full_config:
                        simulation_config = full_config['simulation']
                        if 'logstash_agent' in simulation_config:
                            agent_config = simulation_config['logstash_agent'].copy()
                            # Add simulation mode from parent config
                            if 'mode' in simulation_config:
                                agent_config['simulation_mode'] = simulation_config['mode']
                            if 'mode' not in agent_config:
                                agent_config['mode'] = 'simulation'
                            
                            # FORCE embedded mode to use container paths (ignore config file paths)
                            if agent_config.get('simulation_mode') == 'embedded':
                                agent_config['logstash_binary'] = '/usr/share/logstash/bin/logstash'
                                agent_config['logstash_settings'] = '/etc/logstash'
                                agent_config['logstash_log_path'] = '/var/log/logstash'
                            
                            # Only log simulation_mode details when in simulation mode
                            mode = agent_config.get('mode', 'simulation')
                            if mode == 'simulation':
                                sim_mode = agent_config.get('simulation_mode', 'embedded')
                                if sim_mode == 'embedded':
                                    logger.info(f"Loaded agent config from {logstashui_config_path}: simulation_mode=embedded (forced Linux paths)")
                                else:
                                    logger.info(f"Loaded agent config from {logstashui_config_path}: simulation_mode={sim_mode}")
                            else:
                                logger.info(f"Loaded agent config from {logstashui_config_path}")
                            return agent_config
            except Exception as e:
                logger.warning(f"Failed to load config from {logstashui_config_path}: {e}, trying next path")
    
    # Fallback to logstashagent.yml
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f)
            mode = config.get('mode', 'simulation')
            if mode == 'simulation':
                logger.info(f"Loaded agent config from {CONFIG_PATH}: simulation_mode={config.get('simulation_mode', 'embedded')}")
            else:
                logger.info(f"Loaded agent config from {CONFIG_PATH}")
            return config
    except FileNotFoundError:
        logger.warning(f"Config file {CONFIG_PATH} not found, using embedded mode defaults")
        return {
            'mode': 'simulation',
            'simulation_mode': 'embedded',
            'logstash_binary': '/usr/share/logstash/bin/logstash',
            'logstash_settings': '/etc/logstash/'
        }
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        raise

# Global config
AGENT_CONFIG = load_agent_config()

app = FastAPI(title="logstashagent API", version="0.0.1")

# Request queue for simulation requests during Logstash restarts
_simulation_queue: deque = deque(maxlen=100)  # Max 100 queued requests
_queue_lock = threading.Lock()
_queue_processor_task: Optional[asyncio.Task] = None

@app.on_event("startup")
async def startup_event():
    """Start Logstash under supervision when FastAPI starts"""
    global _queue_processor_task
    logger.info("FastAPI startup - initializing Logstash supervisor")
    logstash_supervisor.start_supervised_logstash(config=AGENT_CONFIG)
    # Wait for Logstash to initialize
    await asyncio.sleep(5)
    logger.info("Logstash supervision started")
    
    # Start queue processor
    _queue_processor_task = asyncio.create_task(_process_simulation_queue())
    logger.info("Simulation queue processor started")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown Logstash supervisor when FastAPI stops"""
    global _queue_processor_task
    logger.info("FastAPI shutdown - stopping queue processor")
    if _queue_processor_task:
        _queue_processor_task.cancel()
        try:
            await _queue_processor_task
        except asyncio.CancelledError:
            pass
    logger.info("FastAPI shutdown - stopping Logstash supervisor")
    logstash_supervisor.shutdown_supervisor()

# Also register atexit handler for clean shutdown
atexit.register(logstash_supervisor.shutdown_supervisor)

# Configuration paths - dynamically set based on mode
def get_logstash_paths():
    """Get Logstash paths based on configuration (Docker vs native)"""
    logstash_settings = AGENT_CONFIG.get('logstash_settings', '/etc/logstash/')
    
    # Ensure settings path ends with /
    if not logstash_settings.endswith('/') and not logstash_settings.endswith('\\'):
        logstash_settings += '/'
    
    # Normalize to forward slashes for consistency
    logstash_settings = logstash_settings.replace('\\', '/')
    
    return {
        'pipelines_yml': f"{logstash_settings}pipelines.yml",
        'conf_d': f"{logstash_settings}conf.d",
        'metadata': f"{logstash_settings}pipeline-metadata"
    }

LOGSTASH_PATHS = get_logstash_paths()
PIPELINES_YML_PATH = LOGSTASH_PATHS['pipelines_yml']
PIPELINES_DIR = LOGSTASH_PATHS['conf_d']
METADATA_DIR = LOGSTASH_PATHS['metadata']

# Ensure directories exist
os.makedirs(PIPELINES_DIR, exist_ok=True)
os.makedirs(METADATA_DIR, exist_ok=True)


def _validate_pipeline_id(pipeline_id: str) -> None:
    """
    Validate pipeline_id to prevent path traversal attacks.

    Args:
        pipeline_id: The pipeline ID to validate

    Raises:
        HTTPException: If pipeline_id contains unsafe characters
    """
    # Allow only alphanumeric, hyphens, underscores, and dots
    # This prevents path traversal with ../ or absolute paths
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', pipeline_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pipeline_id: must contain only alphanumeric characters, hyphens, underscores, and dots"
        )

    # Additional check: prevent .. sequences even if they pass regex
    if '..' in pipeline_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid pipeline_id: cannot contain '..' sequences"
        )

    # Prevent starting with dot (hidden files) or hyphen
    if pipeline_id.startswith('.') or pipeline_id.startswith('-'):
        raise HTTPException(
            status_code=400,
            detail="Invalid pipeline_id: cannot start with '.' or '-'"
        )


def _load_pipelines_yml() -> list:
    """Load the pipelines.yml file"""
    if not os.path.exists(PIPELINES_YML_PATH):
        return []

    try:
        with open(PIPELINES_YML_PATH, 'r') as f:
            content = f.read()
            # Handle empty or comment-only files
            if not content.strip() or all(line.strip().startswith('#') for line in content.split('\n') if line.strip()):
                return []
            pipelines = yaml.safe_load(content)
            return pipelines if pipelines else []
    except Exception as e:
        logger.error(f"Error loading pipelines.yml: {e}")
        return []


def _save_pipelines_yml(pipelines: list):
    """Save the pipelines.yml file atomically, ensuring static pipelines are preserved"""
    # Get logstash settings path from config
    logstash_settings = AGENT_CONFIG.get('logstash_settings', '/etc/logstash/')
    
    # Detect OS and handle path separators appropriately
    is_windows = os.name == 'nt'
    
    if is_windows:
        # Windows: Ensure path ends with backslash, then escape for YAML
        if not logstash_settings.endswith('/') and not logstash_settings.endswith('\\'):
            logstash_settings += '\\'
        # YAML requires backslashes to be escaped, so C:\path becomes C:\\path
        yaml_path = logstash_settings.replace('\\', '\\\\')
        path_sep = '\\\\'
    else:
        # Linux/Docker: Use forward slashes (no escaping needed)
        if not logstash_settings.endswith('/'):
            logstash_settings += '/'
        yaml_path = logstash_settings
        path_sep = '/'
    
    # Define static pipelines that must always be present
    # Static pipeline .conf files are in config/config/ subdirectory
    static_pipelines = [
        {
            'pipeline.id': 'simulate-start',
            'pipeline.workers': 1,
            'path.config': f'{yaml_path}config{path_sep}simulate_start.conf'
        },
        {
            'pipeline.id': 'simulate-end',
            'pipeline.workers': 1,
            'path.config': f'{yaml_path}config{path_sep}simulate_end.conf'
        }
    ]
    
    # Remove any existing static pipeline entries from the input list
    static_ids = {'simulate-start', 'simulate-end'}
    dynamic_pipelines = [p for p in pipelines if p.get('pipeline.id') not in static_ids]
    
    # Combine static pipelines (first) with dynamic pipelines
    final_pipelines = static_pipelines + dynamic_pipelines
    
    temp_path = f"{PIPELINES_YML_PATH}.tmp"
    try:
        with open(temp_path, 'w') as f:
            yaml.dump(final_pipelines, f, default_flow_style=False, sort_keys=False)
        os.replace(temp_path, PIPELINES_YML_PATH)
        logger.debug(f"Saved pipelines.yml with {len(static_pipelines)} static + {len(dynamic_pipelines)} dynamic pipelines")
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e


def delete_pipeline_internal(pipeline_id: str) -> bool:
    """
    Delete a pipeline directly without going through the HTTP API.
    This is used by slots.py to avoid HTTP overhead during cleanup.

    Args:
        pipeline_id: The pipeline ID to delete

    Returns:
        True if deleted successfully, False if not found or error occurred
    """
    try:
        _validate_pipeline_id(pipeline_id)

        # Load existing pipelines
        pipelines = _load_pipelines_yml()

        # Find and remove the pipeline
        pipeline_found = False
        config_path = None
        new_pipelines = []

        for pipeline in pipelines:
            if pipeline.get('pipeline.id') == pipeline_id:
                pipeline_found = True
                config_path = pipeline.get('path.config')
            else:
                new_pipelines.append(pipeline)

        if not pipeline_found:
            return False

        # Delete pipeline config file
        if config_path and os.path.exists(config_path):
            try:
                os.remove(config_path)
            except Exception as e:
                logger.error(f"Failed to delete pipeline config {config_path}: {e}")
                return False

        # Delete metadata file
        metadata_path = os.path.join(METADATA_DIR, f"{pipeline_id}.json")
        if os.path.exists(metadata_path):
            try:
                os.remove(metadata_path)
            except Exception:
                pass  # Non-critical if metadata deletion fails

        # Save updated pipelines.yml
        try:
            _save_pipelines_yml(new_pipelines)
        except Exception as e:
            logger.error(f"Failed to update pipelines.yml: {e}")
            return False

        return True
    except Exception as e:
        logger.error(f"Error deleting pipeline {pipeline_id}: {e}")
        return False


def _load_pipeline_config(pipeline_id: str) -> Optional[str]:
    """Load the pipeline configuration file(s) - supports wildcards"""
    pipelines = _load_pipelines_yml()

    for pipeline in pipelines:
        if pipeline.get('pipeline.id') == pipeline_id:
            config_path = pipeline.get('path.config')
            if not config_path:
                continue

            # Check if path contains wildcards
            if '*' in config_path or '?' in config_path:
                # Expand wildcards and read all matching files
                matching_files = sorted(glob.glob(config_path))
                if not matching_files:
                    return None

                # Concatenate all matching files
                config_parts = []
                for file_path in matching_files:
                    try:
                        with open(file_path, 'r') as f:
                            config_parts.append(f.read())
                    except Exception as e:
                        logger.error(f"Error reading {file_path}: {e}")
                        continue

                return '\n'.join(config_parts) if config_parts else None
            else:
                # Single file path
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        return f.read()
    return None


def _load_pipeline_metadata(pipeline_id: str) -> Dict[str, Any]:
    """Load pipeline metadata (description, settings, etc.)"""
    _validate_pipeline_id(pipeline_id)
    metadata_path = os.path.join(METADATA_DIR, f"{pipeline_id}.json")

    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading metadata for pipeline '{pipeline_id}': {e}")

    # Return default metadata if file doesn't exist or failed to load
    return {
        "description": "",
        "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        "pipeline_metadata": {
            "type": "logstash_pipeline",
            "version": 1
        },
        "username": "logstashagent",
        "pipeline_settings": {
            "pipeline.workers": 1,
            "pipeline.batch.size": 125,
            "pipeline.batch.delay": 50,
            "queue.type": "memory",
            "queue.max_bytes": "1gb",
            "queue.checkpoint.writes": 1024
        }
    }


def _save_pipeline_metadata(pipeline_id: str, metadata: Dict[str, Any]):
    """Save pipeline metadata"""
    _validate_pipeline_id(pipeline_id)
    metadata_path = os.path.join(METADATA_DIR, f"{pipeline_id}.json")
    temp_path = f"{metadata_path}.tmp"

    try:
        with open(temp_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        os.replace(temp_path, metadata_path)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e


def _get_pipeline_settings_from_yml(pipeline_id: str) -> Dict[str, Any]:
    """Extract pipeline settings from pipelines.yml"""
    _validate_pipeline_id(pipeline_id)
    pipelines = _load_pipelines_yml()
    settings = {}

    for pipeline in pipelines:
        if pipeline.get('pipeline.id') == pipeline_id:
            # Extract all pipeline.* and queue.* settings
            for key, value in pipeline.items():
                if key.startswith('pipeline.') or key.startswith('queue.'):
                    settings[key] = value
            break

    return settings


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "name": "logstashagent",
        "version": AGENT_VERSION,
        "status": "running",
        "logstash_version": "9.3.0"
    }


async def _process_simulation_queue():
    """
    Background task that processes queued simulation requests when Logstash becomes healthy.
    """
    logger.info("Queue processor started")
    last_healthy_time = None
    
    while True:
        try:
            await asyncio.sleep(2)  # Check every 2 seconds
            
            supervisor = logstash_supervisor.get_supervisor()
            if not supervisor or not supervisor.is_healthy:
                last_healthy_time = None
                continue
            
            # Track when Logstash became healthy
            if last_healthy_time is None:
                last_healthy_time = time.time()
                logger.info("Logstash became healthy, waiting 10s for full initialization before processing queue")
                continue
            
            # Wait at least 10 seconds after Logstash becomes healthy before processing
            time_since_healthy = time.time() - last_healthy_time
            if time_since_healthy < 10:
                continue
            
            # Verify Logstash port 9449 is actually ready before processing queue
            try:
                test_response = requests.get("http://127.0.0.1:9449", timeout=2)
            except Exception:
                logger.debug("Logstash port 9449 not ready yet, waiting...")
                continue
            
            # Process all queued requests
            while True:
                queued_item = None
                with _queue_lock:
                    if _simulation_queue:
                        queued_item = _simulation_queue.popleft()
                    else:
                        break
                
                if queued_item:
                    log_data = queued_item['log_data']
                    slot_config = queued_item.get('slot_config')
                    
                    logger.info(f"Processing queued simulation: slot={log_data.get('slot')}, run_id={log_data.get('run_id')}")
                    
                    # Restore slot configuration if needed
                    if slot_config:
                        slot_id = slot_config['slot_id']
                        pipeline_name = slot_config['pipeline_name']
                        pipelines = slot_config['pipelines']
                        
                        # Re-allocate slot (will reuse if hash matches)
                        try:
                            # Check if slot already exists
                            existing_slots = slots.get_slot_state()
                            slot_exists = slot_id in existing_slots
                            
                            if not slot_exists:
                                # Allocate slot and create pipelines
                                slots.allocate_slot(pipeline_name, pipelines)
                                await _create_slot_pipelines(slot_id, pipelines)
                                logger.info(f"Restored slot {slot_id} configuration")
                            else:
                                logger.info(f"Slot {slot_id} already exists, skipping restoration")
                        except Exception as e:
                            logger.error(f"Failed to restore slot {slot_id}: {e}")
                            continue
                    
                    # Forward the simulation request with retries
                    max_retries = 3
                    success = False
                    for attempt in range(max_retries):
                        try:
                            timeout = 2 + attempt  # 2s, 3s, 4s
                            response = requests.post(
                                "http://127.0.0.1:9449",
                                json=log_data,
                                timeout=timeout
                            )
                            response.raise_for_status()
                            logger.info(f"Queued simulation processed successfully: slot={log_data.get('slot')}")
                            success = True
                            break
                        except Exception as e:
                            if attempt < max_retries - 1:
                                logger.warning(f"Queued simulation attempt {attempt + 1} failed, retrying: {e}")
                                await asyncio.sleep(1)
                            else:
                                logger.error(f"Failed to process queued simulation after {max_retries} attempts: {e}")
                    
                    if not success:
                        # Re-queue the failed item at the front for retry later
                        with _queue_lock:
                            _simulation_queue.appendleft(queued_item)
                        logger.warning("Re-queued failed simulation for retry later")
                        break  # Stop processing queue, will retry on next iteration
                        
        except asyncio.CancelledError:
            logger.info("Queue processor cancelled")
            break
        except Exception as e:
            logger.error(f"Error in queue processor: {e}", exc_info=True)
            await asyncio.sleep(5)


@app.get("/_logstash/health")
async def logstash_health():
    """
    Check if Logstash is healthy and ready to accept simulation requests.
    Returns health status from supervisor.
    """
    supervisor = logstash_supervisor.get_supervisor()
    with _queue_lock:
        queue_size = len(_simulation_queue)
    
    if supervisor:
        return JSONResponse(
            status_code=200 if supervisor.is_healthy else 503,
            content={
                "healthy": supervisor.is_healthy,
                "restarting": supervisor.is_restarting,
                "restart_count": supervisor.restart_count,
                "queued_requests": queue_size
            }
        )
    return JSONResponse(
        status_code=503,
        content={"healthy": False, "restarting": False, "restart_count": 0, "queued_requests": queue_size}
    )


@app.post("/_logstash/simulate")
async def simulate_log(request: Request):
    """
    Proxy endpoint for simulation log input.
    Accepts HTTPS requests from logstashui and forwards them to the local HTTP port 9449.
    
    Queues requests when Logstash is unhealthy and processes them when it recovers.
    """
    try:
        # Get the JSON body from the request
        log_data = await request.json()
        slot_id = log_data.get('slot')
        
        # Check if Logstash is healthy
        supervisor = logstash_supervisor.get_supervisor()
        is_healthy = supervisor and supervisor.is_healthy
        
        if not is_healthy:
            # Queue the request with slot configuration for restoration
            slot_config = None
            if slot_id:
                # Get current slot configuration to restore later
                slot_state = slots.get_slot_state()
                if slot_id in slot_state:
                    slot_data = slot_state[slot_id]
                    slot_config = {
                        'slot_id': slot_id,
                        'pipeline_name': slot_data.get('pipeline_name'),
                        'pipelines': slot_data.get('pipelines')
                    }
            
            with _queue_lock:
                _simulation_queue.append({
                    'log_data': log_data,
                    'slot_config': slot_config,
                    'queued_at': time.time()
                })
                queue_size = len(_simulation_queue)
            
            logger.warning(f"Logstash unhealthy - queued simulation request (queue size: {queue_size})")
            return JSONResponse(
                status_code=202,
                content={
                    "status": "queued",
                    "message": "Logstash is restarting, request queued for processing",
                    "queue_position": queue_size
                }
            )
        
        # Logstash is healthy - forward immediately with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                timeout = 1 + attempt  # 1s, 2s, 3s - aggressive timeouts to detect hung Logstash
                logger.debug(f"Simulation attempt {attempt + 1}/{max_retries}, timeout={timeout}s")
                
                # Forward to local Logstash HTTP input on port 9449
                response = requests.post(
                    "http://127.0.0.1:9449",
                    json=log_data,
                    timeout=timeout
                )
                response.raise_for_status()
                
                logger.info(
                    f"Forwarded simulation log to Logstash: slot={slot_id}, run_id={log_data.get('run_id')}")
                
                return JSONResponse(
                    status_code=200,
                    content={"status": "success", "message": "Log forwarded to Logstash"}
                )
                
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Simulation timeout on attempt {attempt + 1}, retrying...")
                    await asyncio.sleep(1)
                    continue
                else:
                    # All retries failed - Logstash is likely stunned/OOM
                    logger.error(f"Simulation failed after {max_retries} attempts due to timeout - triggering restart")
                    
                    # Queue the request for retry after restart
                    slot_config = None
                    if slot_id:
                        slot_state = slots.get_slot_state()
                        if slot_id in slot_state:
                            slot_data = slot_state[slot_id]
                            slot_config = {
                                'slot_id': slot_id,
                                'pipeline_name': slot_data.get('pipeline_name'),
                                'pipelines': slot_data.get('pipelines')
                            }
                    
                    with _queue_lock:
                        _simulation_queue.append({
                            'log_data': log_data,
                            'slot_config': slot_config,
                            'queued_at': time.time()
                        })
                        queue_size = len(_simulation_queue)
                    
                    # Trigger restart
                    logstash_supervisor.trigger_restart("Simulation POST failed - Logstash stunned/OOM")
                    
                    logger.warning(f"Queued failed simulation for retry after restart (queue size: {queue_size})")
                    return JSONResponse(
                        status_code=202,
                        content={
                            "status": "queued",
                            "message": "Logstash unresponsive, triggering restart and queuing request",
                            "queue_position": queue_size
                        }
                    )
                    
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Simulation request failed on attempt {attempt + 1}, retrying: {e}")
                    await asyncio.sleep(1)
                    continue
                else:
                    # All retries failed - Logstash is likely stunned/OOM
                    logger.error(f"Simulation failed after {max_retries} attempts: {e} - triggering restart")
                    
                    # Queue the request for retry after restart
                    slot_config = None
                    if slot_id:
                        slot_state = slots.get_slot_state()
                        if slot_id in slot_state:
                            slot_data = slot_state[slot_id]
                            slot_config = {
                                'slot_id': slot_id,
                                'pipeline_name': slot_data.get('pipeline_name'),
                                'pipelines': slot_data.get('pipelines')
                            }
                    
                    with _queue_lock:
                        _simulation_queue.append({
                            'log_data': log_data,
                            'slot_config': slot_config,
                            'queued_at': time.time()
                        })
                        queue_size = len(_simulation_queue)
                    
                    # Trigger restart
                    logstash_supervisor.trigger_restart(f"Simulation POST failed: {str(e)}")
                    
                    logger.warning(f"Queued failed simulation for retry after restart (queue size: {queue_size})")
                    return JSONResponse(
                        status_code=202,
                        content={
                            "status": "queued",
                            "message": "Logstash unresponsive, triggering restart and queuing request",
                            "queue_position": queue_size
                        }
                    )
                    
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to forward log to Logstash: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to forward log to Logstash: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error in simulate_log endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing simulation log: {str(e)}"
        )


@app.get("/_logstash/pipeline")
async def list_pipelines():
    """List all pipelines (mimics Elasticsearch API)"""
    pipelines = _load_pipelines_yml()
    result = {}

    for pipeline in pipelines:
        pipeline_id = pipeline.get('pipeline.id')
        if pipeline_id:
            # Load pipeline config
            config = _load_pipeline_config(pipeline_id)
            if config is None:
                continue

            # Load metadata
            metadata = _load_pipeline_metadata(pipeline_id)

            # Get settings from pipelines.yml
            yml_settings = _get_pipeline_settings_from_yml(pipeline_id)

            # Merge settings (yml takes precedence)
            pipeline_settings = metadata.get('pipeline_settings', {})
            pipeline_settings.update(yml_settings)

            result[pipeline_id] = {
                "description": metadata.get('description', ''),
                "last_modified": metadata.get('last_modified'),
                "pipeline_metadata": metadata.get('pipeline_metadata', {
                    "type": "logstash_pipeline",
                    "version": 1
                }),
                "username": metadata.get('username', 'logstashagent'),
                "pipeline": config,
                "pipeline_settings": pipeline_settings
            }

    return result


@app.get("/_logstash/pipeline/{pipeline_id}")
async def get_pipeline(pipeline_id: str = FastAPIPath(..., description="Pipeline ID")):
    """Get a specific pipeline (mimics Elasticsearch API)"""
    _validate_pipeline_id(pipeline_id)

    # Load pipeline config
    config = _load_pipeline_config(pipeline_id)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")

    # Load metadata
    metadata = _load_pipeline_metadata(pipeline_id)

    # Get settings from pipelines.yml
    yml_settings = _get_pipeline_settings_from_yml(pipeline_id)

    # Merge settings (yml takes precedence)
    pipeline_settings = metadata.get('pipeline_settings', {})
    pipeline_settings.update(yml_settings)

    result = {
        pipeline_id: {
            "description": metadata.get('description', ''),
            "last_modified": metadata.get('last_modified'),
            "pipeline_metadata": metadata.get('pipeline_metadata', {
                "type": "logstash_pipeline",
                "version": 1
            }),
            "username": metadata.get('username', 'logstashagent'),
            "pipeline": config,
            "pipeline_settings": pipeline_settings
        }
    }

    return result


@app.put("/_logstash/pipeline/{pipeline_id}")
async def put_pipeline(pipeline_id: str, body: Dict[str, Any]):
    """Create or update a pipeline (mimics Elasticsearch API)"""
    _validate_pipeline_id(pipeline_id)

    pipeline_config = body.get('pipeline')
    if not pipeline_config:
        raise HTTPException(status_code=400, detail="Missing 'pipeline' field in request body")

    # Prepare pipeline settings for pipelines.yml
    pipeline_settings = body.get('pipeline_settings', {})

    # Load existing pipelines
    pipelines = _load_pipelines_yml()

    # Check if pipeline exists
    pipeline_exists = False
    for i, pipeline in enumerate(pipelines):
        if pipeline.get('pipeline.id') == pipeline_id:
            pipeline_exists = True
            # Update existing pipeline entry
            config_path = pipeline.get('path.config', f"{PIPELINES_DIR}/{pipeline_id}.conf")
            pipelines[i] = {
                'pipeline.id': pipeline_id,
                'path.config': config_path,
                **{k: v for k, v in pipeline_settings.items() if k.startswith('pipeline.') or k.startswith('queue.')}
            }
            break

    if not pipeline_exists:
        # Add new pipeline entry
        # Handle path separators based on OS
        if os.name == 'nt':
            # Windows: Convert to backslashes and escape for YAML
            config_path = f"{PIPELINES_DIR}/{pipeline_id}.conf".replace('/', '\\').replace('\\', '\\\\')
        else:
            # Linux/Docker: Use forward slashes (no escaping needed)
            config_path = f"{PIPELINES_DIR}/{pipeline_id}.conf"
        new_pipeline = {
            'pipeline.id': pipeline_id,
            'path.config': config_path,
            **{k: v for k, v in pipeline_settings.items() if k.startswith('pipeline.') or k.startswith('queue.')}
        }
        pipelines.append(new_pipeline)

    # Save pipeline configuration file
    config_path = f"{PIPELINES_DIR}/{pipeline_id}.conf"
    temp_config_path = f"{config_path}.tmp"
    try:
        with open(temp_config_path, 'w') as f:
            f.write(pipeline_config)
        os.replace(temp_config_path, config_path)
    except Exception as e:
        if os.path.exists(temp_config_path):
            os.remove(temp_config_path)
        raise HTTPException(status_code=500, detail=f"Failed to write pipeline config: {str(e)}")

    # Save pipelines.yml
    try:
        _save_pipelines_yml(pipelines)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update pipelines.yml: {str(e)}")

    # Save metadata
    metadata = {
        "description": body.get('description', ''),
        "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        "pipeline_metadata": body.get('pipeline_metadata', {
            "type": "logstash_pipeline",
            "version": 1
        }),
        "username": body.get('username', 'logstashagent'),
        "pipeline_settings": pipeline_settings
    }

    try:
        _save_pipeline_metadata(pipeline_id, metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save metadata: {str(e)}")

    return {"acknowledged": True}


@app.delete("/_logstash/pipeline/{pipeline_id}")
async def delete_pipeline(pipeline_id: str = FastAPIPath(..., description="Pipeline ID")):
    """Delete a pipeline (mimics Elasticsearch API)"""
    _validate_pipeline_id(pipeline_id)

    # Load existing pipelines
    pipelines = _load_pipelines_yml()

    # Find and remove the pipeline
    pipeline_found = False
    config_path = None
    new_pipelines = []

    for pipeline in pipelines:
        if pipeline.get('pipeline.id') == pipeline_id:
            pipeline_found = True
            config_path = pipeline.get('path.config')
        else:
            new_pipelines.append(pipeline)

    if not pipeline_found:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")

    # Delete pipeline config file
    if config_path and os.path.exists(config_path):
        try:
            os.remove(config_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete pipeline config: {str(e)}")

    # Delete metadata file
    metadata_path = os.path.join(METADATA_DIR, f"{pipeline_id}.json")
    if os.path.exists(metadata_path):
        try:
            os.remove(metadata_path)
        except Exception:
            pass  # Non-critical if metadata deletion fails

    # Save updated pipelines.yml
    try:
        _save_pipelines_yml(new_pipelines)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update pipelines.yml: {str(e)}")

    return {"acknowledged": True}


@app.post("/_logstash/slots/allocate")
async def allocate_simulation_slot(body: Dict[str, Any]):
    """
    Allocate a slot for simulation pipelines.

    Request body:
    {
        "pipeline_name": "name of the pipeline being simulated",
        "pipelines": [
            {"config": "filter config 1", "index": 1},
            {"config": "filter config 2", "index": 2},
            ...
        ]
    }

    Returns:
    {
        "slot_id": 1-10,
        "reused": true/false (whether an existing slot was reused)
    }
    """
    pipeline_name = body.get('pipeline_name')
    pipelines = body.get('pipelines', [])

    if not pipeline_name:
        raise HTTPException(status_code=400, detail="Missing 'pipeline_name' field")

    if not pipelines:
        raise HTTPException(status_code=400, detail="Missing 'pipelines' field or empty pipeline list")

    # Check if a slot with this exact configuration already exists
    content_hash = slots._compute_pipeline_hash(pipelines)
    existing_slots = slots.get_slot_state()
    slot_existed_before = any(
        slot_data.get('content_hash') == content_hash
        for slot_data in existing_slots.values()
    )

    # Allocate or reuse slot (allocate_slot handles hash checking internally)
    slot_id = slots.allocate_slot(pipeline_name, pipelines)

    if slot_id is None:
        raise HTTPException(status_code=500, detail="Failed to allocate slot")

    # If the slot existed before with the same hash, it's reused
    reused = slot_existed_before

    logger.info(f"Slot {slot_id} - reused: {reused}, hash: {content_hash[:8]}...")

    # Check if pipelines actually exist when reusing a slot
    # They may have been deleted during previous failure cleanup or eviction
    pipelines_exist = False
    if reused:
        # Check if the first pipeline exists in Logstash using API
        first_pipeline_name = f"slot{slot_id}-filter1"
        try:
            with LogstashAPI(timeout=3.0) as api:
                all_pipelines = api.list_pipelines()
                pipelines_exist = first_pipeline_name in all_pipelines
                logger.info(f"Slot {slot_id} reused - pipelines exist: {pipelines_exist}")
        except Exception as e:
            logger.warning(f"Failed to check pipeline existence via API: {e}. Assuming pipelines don't exist.")
            pipelines_exist = False

    # Create pipelines if they don't exist (new slot or reused slot with deleted pipelines)
    if not reused or not pipelines_exist:
        try:
            await _create_slot_pipelines(slot_id, pipelines)
        except HTTPException as e:
            # Release the slot if pipeline creation fails
            slots.release_slot(slot_id)
            # Re-raise HTTPException as-is to preserve detail structure (may contain slot_id dict)
            raise
        except Exception as e:
            # Release the slot if pipeline creation fails
            slots.release_slot(slot_id)
            # For non-HTTP exceptions, include slot_id in detail for error tracking
            raise HTTPException(
                status_code=500,
                detail={
                    "message": f"Failed to create slot pipelines: {str(e)}",
                    "slot_id": slot_id
                }
            )

    logger.info(f"Returning HTTP response for slot {slot_id}")
    return {
        "slot_id": slot_id,
        "reused": reused,
        "pipeline_count": len(pipelines)
    }


async def _create_slot_pipelines(slot_id: int, pipelines: List[Dict[str, Any]]):
    """
    Create the filter pipelines for a specific slot.

    Args:
        slot_id: Slot ID (1-10)
        pipelines: List of pipeline configurations
    """
    for pipeline_data in pipelines:
        idx = pipeline_data.get('index', 1)
        filter_config = pipeline_data.get('filter_config', '')

        if not filter_config:
            continue

        # Determine next filter address
        if idx < len(pipelines):
            next_filter_id = f"slot{slot_id}-filter{idx + 1}"
        else:
            next_filter_id = "filter-final"

        # Generate pipeline config with both pipeline and HTTP outputs
        pipeline_config = f"""input {{
  pipeline {{ address => "slot{slot_id}-filter{idx}" }}
}}

filter {{
{filter_config}
}}

output {{
  pipeline {{ send_to => "simulate-end" }}
}}
"""

        # Create the pipeline
        pipeline_name = f"slot{slot_id}-filter{idx}"
        pipeline_body = {
            "pipeline": pipeline_config,
            "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "pipeline_metadata": {
                "version": 1,
                "type": "logstash_pipeline"
            },
            "username": "logstashagent",
            "pipeline_settings": {
                "pipeline.workers": 1
            }
        }

        # Use the existing put_pipeline logic
        await put_pipeline(pipeline_name, pipeline_body)

    # Verify all slot pipelines loaded successfully
    # Uses adaptive timing based on pipeline count (default: 20 retries, 2s delay)
    verify_start = time.time()
    verification_success = await slots.verify_slot_pipelines_loaded(
        slot_id,
        len(pipelines)
    )
    verify_end = time.time()
    logger.info(f"Verification completed in {verify_end - verify_start:.2f}s")

    if not verification_success:
        # Delete the failed pipelines from Logstash to prevent log pollution
        logger.warning(f"Verification failed for slot {slot_id}, cleaning up pipelines")
        for idx in range(1, len(pipelines) + 1):
            pipeline_name = f"slot{slot_id}-filter{idx}"
            try:
                await delete_pipeline(pipeline_name)
                logger.info(f"Deleted failed pipeline {pipeline_name}")
            except Exception as cleanup_error:
                logger.error(f"Error deleting failed pipeline {pipeline_name}: {cleanup_error}")

        # Wait for pipelines to actually disappear from Logstash API
        # This prevents stale failure state when slot is reused
        import asyncio
        logger.info(f"Waiting for slot {slot_id} pipelines to be removed from Logstash...")
        max_wait = 5.0
        start_wait = time.time()
        while time.time() - start_wait < max_wait:
            try:
                with LogstashAPI(timeout=3.0) as api:
                    all_pipelines = api.list_pipelines()
                    slot_pipelines_still_exist = any(
                        f"slot{slot_id}-filter{idx}" in all_pipelines
                        for idx in range(1, len(pipelines) + 1)
                    )
                    if not slot_pipelines_still_exist:
                        logger.info(f"Slot {slot_id} pipelines successfully removed from Logstash")
                        break
            except Exception as e:
                logger.warning(f"Error checking pipeline removal: {e}")
            await asyncio.sleep(0.5)

        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Slot {slot_id} pipelines created but failed to load in Logstash. Check logs for errors.",
                "slot_id": slot_id
            }
        )


@app.get("/_logstash/slots")
async def get_slots():
    """Get the current state of all slots."""
    return slots.get_slot_state()


@app.delete("/_logstash/slots/{slot_id}")
async def release_slot(slot_id: int = FastAPIPath(..., description="Slot ID", ge=1, le=10)):
    """Release a specific slot."""
    success = slots.release_slot(slot_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Slot {slot_id} not found")

    return {"acknowledged": True, "slot_id": slot_id}


@app.get("/_logstash/pipeline/{pipeline_id}/logs")
async def get_pipeline_logs(
        pipeline_id: str = FastAPIPath(..., description="Pipeline ID"),
        max_entries: int = Query(50, description="Maximum number of log entries to return", ge=1, le=500),
        min_level: str = Query("WARN", description="Minimum log level (DEBUG, INFO, WARN, ERROR)"),
        min_timestamp: int = Query(None,
                                   description="Minimum timestamp in milliseconds. Only logs at or after this time will be included.")
):
    """
    Get log entries related to a specific pipeline.

    This endpoint searches Logstash JSON logs for entries related to the given pipeline,
    including errors, warnings, and other diagnostic information.

    Args:
        pipeline_id: The pipeline ID to search for (e.g., "slot4-filter1")
        max_entries: Maximum number of log entries to return (default: 50, max: 500)
        min_level: Minimum log level to include (default: WARN)
        min_timestamp: Optional minimum timestamp in milliseconds. Only logs at or after this time will be included.

    Returns:
        JSON response with:
        - pipeline_id: The pipeline ID searched
        - log_count: Number of log entries found
        - logs: List of log entries with full context
    """
    _validate_pipeline_id(pipeline_id)

    try:
        # Fetch logs using log_analyzer
        logs = log_analyzer.find_related_logs(
            pipeline_id=pipeline_id,
            max_entries=max_entries,
            min_level=min_level.upper(),
            min_timestamp=min_timestamp
        )

        return {
            "pipeline_id": pipeline_id,
            "log_count": len(logs),
            "logs": logs
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching logs for pipeline {pipeline_id}: {str(e)}"
        )


@app.get("/_logstash/pipelines/status")
async def get_pipelines_status():
    """
    Get the current status of all running pipelines from Logstash API.

    Returns:
        - running_pipelines: List of pipeline IDs currently loaded in Logstash
        - count: Total count of pipelines
        - timestamp: When this status was retrieved
        - states: Dictionary mapping pipeline names to their states (running/idle/failed/unknown)
    """
    try:
        with LogstashAPI(timeout=5.0) as api:
            # Get all pipelines
            all_pipelines = api.list_pipelines()

            # Get state for each pipeline
            # Use defensive error handling - if one pipeline fails, don't crash the whole endpoint
            pipeline_states = {}
            for pipeline_name in all_pipelines:
                try:
                    state = api.detect_pipeline_state(pipeline_name)
                    pipeline_states[pipeline_name] = state
                except Exception as e:
                    logger.error(f"Error detecting state for pipeline '{pipeline_name}': {e}")
                    pipeline_states[pipeline_name] = 'unknown'

            return {
                "running_pipelines": all_pipelines,
                "count": len(all_pipelines),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "states": pipeline_states
            }
    except Exception as e:
        logger.error(f"Error in get_pipelines_status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching pipeline status from Logstash API: {str(e)}"
        )


@app.post("/_logstash/write-file")
async def write_file(request: Request):
    """
    Write a file to the uploaded directory for simulation use.
    Only enabled when SIMULATION_MODE environment variable is set to true.

    Request body:
    {
        "filename": "filter_translate_10_dictionary_path.json",
        "content": "<base64 encoded file content>"
    }
    """
    # Check if simulation mode is enabled (defaults to true for development)
    # Set SIMULATION_MODE=false to explicitly disable file uploads
    simulation_mode = os.getenv("SIMULATION_MODE", "true").lower() == "true"
    if not simulation_mode:
        raise HTTPException(
            status_code=403,
            detail="File upload is only allowed in simulation mode"
        )

    try:
        body = await request.json()
        filename = body.get("filename")
        content = body.get("content")

        if not filename or not content:
            raise HTTPException(
                status_code=400,
                detail="Both 'filename' and 'content' are required"
            )

        # Create uploaded directory in /tmp if it doesn't exist
        uploaded_dir = "/tmp/uploaded"
        os.makedirs(uploaded_dir, exist_ok=True)

        # Sanitize filename to prevent path traversal
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(uploaded_dir, safe_filename)

        # Decode base64 content and write file
        logger.info(f"Received content length: {len(content)} characters")
        file_content = base64.b64decode(content)
        logger.info(f"Decoded to {len(file_content)} bytes")

        with open(file_path, 'wb') as f:
            bytes_written = f.write(file_content)
            logger.info(f"Wrote {bytes_written} bytes to {file_path}")

        logger.info(f"File written successfully: {file_path}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"File written to {file_path}",
                "path": file_path
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error writing file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error writing file: {str(e)}"
        )


@app.post("/_logstash/validate")
async def validate_logstash_config(request: Request):
    """
    Validate a Logstash pipeline configuration using logstash --config.test_and_exit.
    
    Request body:
        - pipeline_name: Name of the pipeline (used for temp file naming)
        - config: The Logstash configuration to validate
    
    Returns:
        - status: "OK" or "ERROR"
        - notifications: List of warning/deprecation messages
        - error: Error message if validation failed
    """
    import subprocess

    try:
        body = await request.json()
        pipeline_name = body.get("pipeline_name", "pipeline")
        config = body.get("config")
        
        if not config:
            raise HTTPException(
                status_code=400,
                detail="No configuration provided"
            )
        
        # Create temporary config file
        temp_file_path = f"/tmp/{pipeline_name}.conf"
        
        try:
            # Replace keystore variables without defaults to avoid validation failures
            # Pattern: ${variable_name} -> ${variable_name:test}
            # Don't replace if already has a default: ${variable_name:existing_default}
            import re
            config_with_defaults = re.sub(
                r'\$\{([^}:]+)\}',  # Match ${variable_name} without colon
                r'${\1:test}',       # Replace with ${variable_name:test}
                config
            )
            
            # Write config to temp file
            with open(temp_file_path, 'w') as f:
                f.write(config_with_defaults)
            
            logger.info(f"Validating config for pipeline '{pipeline_name}' at {temp_file_path}")
            
            # Get logstash binary path from config
            logstash_binary = AGENT_CONFIG.get('logstash_binary', '/usr/share/logstash/bin/logstash')
            logger.info(f"Using Logstash binary: {logstash_binary}")
            
            # Run logstash validation
            result = subprocess.run(
                [logstash_binary, "--config.test_and_exit", "-f", temp_file_path, "--log.format", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Parse output to extract notifications by log level
            notifications_by_level = {}
            output_lines = result.stdout.strip().split('\n')
            
            for line in output_lines:
                try:
                    log_entry = json.loads(line)
                    # Extract log entries with logEvent
                    if "logEvent" in log_entry:
                        message = log_entry["logEvent"].get("message", "")
                        logger_name = log_entry.get("loggerName", "")
                        level = log_entry.get("level", "INFO")
                        
                        # Filter out noise
                        if "Reflections took" in message or "pipelines.yml" in message:
                            continue
                        
                        # Only include relevant log levels
                        if level in ["FATAL", "ERROR", "WARN", "INFO"]:
                            # Skip generic INFO messages unless they're important
                            if level == "INFO":
                                # Filter out logstash.runner INFO logs - not useful to users
                                if logger_name == "logstash.runner":
                                    continue
                                # Only include specific INFO messages
                                if not any(keyword in message.lower() for keyword in ["deprecated", "warning", "error"]):
                                    continue
                            
                            # Initialize level list if not exists
                            if level not in notifications_by_level:
                                notifications_by_level[level] = []
                            
                            # Remove discussion forum text if present
                            cleaned_message = message.replace(
                                "If you have any questions about this, please ask it on the https://discuss.elastic.co/c/logstash discussion forum",
                                ""
                            ).strip()
                            
                            # Add entry with plugin and message
                            notifications_by_level[level].append({
                                "plugin": logger_name,
                                "message": cleaned_message
                            })
                except json.JSONDecodeError:
                    # Skip non-JSON lines (like "Configuration OK")
                    if "Configuration OK" in line:
                        logger.info("Configuration validation passed")
                    continue
            
            # Determine overall status based on log levels present
            if "FATAL" in notifications_by_level or "ERROR" in notifications_by_level:
                status = "ERROR"
            elif "WARN" in notifications_by_level:
                status = "WARN"
            elif result.returncode == 0:
                status = "OK"
            else:
                status = "ERROR"
            
            logger.info(f"Validation result for pipeline '{pipeline_name}': {status}, levels: {list(notifications_by_level.keys())}")
            
            return JSONResponse(
                status_code=200,
                content={
                    "status": status,
                    "notifications": notifications_by_level
                }
            )
        
        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                logger.debug(f"Removed temp file: {temp_file_path}")
    
    except subprocess.TimeoutExpired:
        logger.error(f"Validation timeout for pipeline '{pipeline_name}'")
        raise HTTPException(
            status_code=500,
            detail="Validation timeout - configuration took too long to validate"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating config: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error validating configuration: {str(e)}"
        )


def parse_arguments():
    """
    Parse command-line arguments for enrollment and other modes
    """
    parser = argparse.ArgumentParser(
        description='logstashagent - Control plane agent for logstashui',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Enroll agent with logstashui
  python main.py --enroll=eyJlbnJvbGxtZW50X3Rva2VuIjogInN3VGJJODZkYl9tbjBUVE12X2Rfd1hXd0Via3RETU1iUkE2elVaRkF4WXcifQ== --logstash-ui-url=http://localhost:8080
  
  # Enroll with HTTPS URL
  python main.py --enroll=TOKEN --logstash-ui-url=https://logstashui.example.com
  
  # Run in normal mode (simulation or agent mode based on config)
  python main.py
        """
    )
    
    parser.add_argument(
        '--enroll',
        type=str,
        metavar='TOKEN',
        help='Enroll this agent with logstashui using the provided base64-encoded enrollment token'
    )
    
    parser.add_argument(
        '--logstash-ui-url',
        type=str,
        metavar='URL',
        help='logstashui URL for enrollment (required with --enroll, e.g., http://localhost:8080 or https://logstashui.example.com)'
    )
    
    parser.add_argument(
        '--run',
        action='store_true',
        help='Run the agent controller (for enrolled agents in host mode)'
    )

    parser.add_argument(
        '--yes',
        action='store_true',
        help='Skip the enrollment confirmation prompt'
    )

    return parser.parse_args()


if __name__ == "__main__":
    """
    Main entry point for logstashagent
    
    Supports multiple modes:
    - Enrollment mode: --enroll flag to register with logstashui
    - Agent mode: mode=agent in config, checks in with logstashui
    - Simulation mode: mode=simulation in config, runs as simulation node
    - Host mode: mode=host in config, manages local Logstash instance
    """
    args = parse_arguments()
    
    # Check if we're in enrollment mode
    if args.enroll:
        logger.info("=" * 60)
        logger.info("LOGSTASH AGENT ENROLLMENT")
        logger.info("=" * 60)
        
        # Validate that logstash-ui-url is provided
        if not args.logstash_ui_url:
            logger.error("--logstash-ui-url is required when using --enroll")
            logger.error("Example: python main.py --enroll=TOKEN --logstash-ui-url=http://localhost:8080")
            sys.exit(1)

        if not args.yes:
            print("\nThis node will be enrolled into LogstashUI managed mode.")
            print("\nFuture policy applies may overwrite manual changes made directly on the host, including:")
            print("  - logstash.yml")
            print("  - jvm.options")
            print("  - log4j2.properties")
            print("  - pipelines")
            print("  - keystore contents")
            print()
            answer = input("Continue? [y/N]: ").strip().lower()
            if answer != 'y':
                print("Enrollment cancelled.")
                sys.exit(0)

        try:
            enrollment.perform_enrollment(
                encoded_token=args.enroll,
                logstash_ui_url=args.logstash_ui_url,
                agent_id=AGENT_ID
            )
            sys.exit(0)
        except Exception as e:
            logger.error(f"Enrollment failed: {e}")
            sys.exit(1)
    
    # Check if we're in run mode (controller mode for enrolled agents)
    if args.run:
        # Run the agent controller
        controller.run_controller()
        sys.exit(0)
    
    # Check the mode from config
    agent_mode = AGENT_CONFIG.get('mode', 'simulation')
    
    if agent_mode != 'simulation':
        logger.info("=" * 60)
        logger.info("LOGSTASH AGENT MODE")
        logger.info("=" * 60)
        logger.info("Agent mode is not yet fully implemented")
        logger.info("The agent will check in with logstashui and receive policies")
        logger.info("For now, starting in simulation mode...")
        logger.info("=" * 60)
        # TODO: Implement agent check-in loop
        # For now, fall through to start FastAPI server
    
    # Start FastAPI server (simulation or host mode)

    
    # Get host and port from config or use defaults
    host = AGENT_CONFIG.get('host', '0.0.0.0')
    port = AGENT_CONFIG.get('port', 9600)
    
    logger.info(f"Starting logstashagent in {agent_mode} mode on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )