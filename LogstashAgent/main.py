from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import os
import yaml
import json
import glob
import logging
import logging.handlers
from pathlib import Path as PathLib
import slots
import log_analyzer
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s %(name)s %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="LogstashAgent API", version="0.0.1")

# Configuration paths
PIPELINES_YML_PATH = "/etc/logstash/pipelines.yml"
PIPELINES_DIR = "/etc/logstash/conf.d"
METADATA_DIR = "/etc/logstash/pipeline-metadata"

# Ensure directories exist
os.makedirs(PIPELINES_DIR, exist_ok=True)
os.makedirs(METADATA_DIR, exist_ok=True)


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
        print(f"Error loading pipelines.yml: {e}")
        return []


def _save_pipelines_yml(pipelines: list):
    """Save the pipelines.yml file atomically"""
    temp_path = f"{PIPELINES_YML_PATH}.tmp"
    try:
        with open(temp_path, 'w') as f:
            yaml.dump(pipelines, f, default_flow_style=False, sort_keys=False)
        os.replace(temp_path, PIPELINES_YML_PATH)
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
                        print(f"Error reading {file_path}: {e}")
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
    metadata_path = os.path.join(METADATA_DIR, f"{pipeline_id}.json")
    
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            return json.load(f)
    
    # Return default metadata if file doesn't exist
    return {
        "description": "",
        "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
        "pipeline_metadata": {
            "type": "logstash_pipeline",
            "version": 1
        },
        "username": "LogstashAgent",
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
        "name": "LogstashAgent",
        "version": "0.0.1",
        "status": "running",
        "logstash_version": "9.3.0"
    }


@app.post("/_logstash/simulate")
async def simulate_log(request: Request):
    """
    Proxy endpoint for simulation log input.
    Accepts HTTPS requests from LogstashUI and forwards them to the local HTTP port 8082.
    
    This allows LogstashUI to send simulation logs over HTTPS (via nginx) while
    Logstash's HTTP input plugin only accepts HTTP on localhost.
    """
    try:
        # Get the JSON body from the request
        log_data = await request.json()
        
        # Forward to local Logstash HTTP input on port 8082
        response = requests.post(
            "http://127.0.0.1:8082",
            json=log_data,
            timeout=10
        )
        response.raise_for_status()
        
        logger.info(f"Forwarded simulation log to Logstash: slot={log_data.get('slot')}, run_id={log_data.get('run_id')}")
        
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Log forwarded to Logstash"}
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
                "username": metadata.get('username', 'LogstashAgent'),
                "pipeline": config,
                "pipeline_settings": pipeline_settings
            }
    
    return result


@app.get("/_logstash/pipeline/{pipeline_id}")
async def get_pipeline(pipeline_id: str = Path(..., description="Pipeline ID")):
    """Get a specific pipeline (mimics Elasticsearch API)"""
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
            "username": metadata.get('username', 'LogstashAgent'),
            "pipeline": config,
            "pipeline_settings": pipeline_settings
        }
    }
    
    return result


@app.put("/_logstash/pipeline/{pipeline_id}")
async def put_pipeline(pipeline_id: str, body: Dict[str, Any]):
    """Create or update a pipeline (mimics Elasticsearch API)"""
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
        "username": body.get('username', 'LogstashAgent'),
        "pipeline_settings": pipeline_settings
    }
    
    try:
        _save_pipeline_metadata(pipeline_id, metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save metadata: {str(e)}")
    
    return {"acknowledged": True}


@app.delete("/_logstash/pipeline/{pipeline_id}")
async def delete_pipeline(pipeline_id: str = Path(..., description="Pipeline ID")):
    """Delete a pipeline (mimics Elasticsearch API)"""
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
        # Check if the first pipeline exists in Logstash
        first_pipeline_name = f"slot{slot_id}-filter1"
        pipeline_status = log_analyzer.get_running_pipelines()
        if pipeline_status:
            running_pipelines = pipeline_status.get('running_pipelines', [])
            pipelines_exist = first_pipeline_name in running_pipelines
            logger.info(f"Slot {slot_id} reused - pipelines exist: {pipelines_exist}")
    
    # Create pipelines if they don't exist (new slot or reused slot with deleted pipelines)
    if not reused or not pipelines_exist:
        try:
            await _create_slot_pipelines(slot_id, pipelines)
        except Exception as e:
            # Release the slot if pipeline creation fails
            slots.release_slot(slot_id)
            raise HTTPException(status_code=500, detail=f"Failed to create slot pipelines: {str(e)}")
    
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
            "username": "LogstashAgent",
            "pipeline_settings": {
                "pipeline.workers": 1
            }
        }
        
        # Use the existing put_pipeline logic
        await put_pipeline(pipeline_name, pipeline_body)
    
    # Verify all slot pipelines loaded successfully
    # Use longer retry window when system is under load
    verification_success = await slots.verify_slot_pipelines_loaded(
        slot_id, 
        len(pipelines),
        max_retries=10,  # Increased from default 5
        retry_delay=2.0   # Increased from default 1.0
    )
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
async def release_slot(slot_id: int = Path(..., description="Slot ID", ge=1, le=10)):
    """Release a specific slot."""
    success = slots.release_slot(slot_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Slot {slot_id} not found")
    
    return {"acknowledged": True, "slot_id": slot_id}


@app.get("/_logstash/pipeline/{pipeline_id}/logs")
async def get_pipeline_logs(
    pipeline_id: str = Path(..., description="Pipeline ID"),
    max_entries: int = Query(50, description="Maximum number of log entries to return", ge=1, le=500),
    min_level: str = Query("WARN", description="Minimum log level (DEBUG, INFO, WARN, ERROR)"),
    min_timestamp: int = Query(None, description="Minimum timestamp in milliseconds. Only logs at or after this time will be included.")
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
    Get the current status of all running pipelines from Logstash logs.
    
    Returns:
        JSON response with:
        - running_pipelines: List of pipeline IDs currently running
        - non_running_pipelines: List of pipeline IDs not running
        - count: Total count of running pipelines
        - timestamp: When this status was logged
    """
    try:
        status = log_analyzer.get_running_pipelines()
        
        if not status:
            raise HTTPException(
                status_code=404,
                detail="No pipeline status found in logs. Logstash may not be running or logs not available."
            )
        
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching pipeline status: {str(e)}"
        )