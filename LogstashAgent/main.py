from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import os
import yaml
import json
import glob
from pathlib import Path as PathLib

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