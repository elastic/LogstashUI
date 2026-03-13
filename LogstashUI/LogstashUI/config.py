#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import os
import yaml
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "simulation": {
        "mode": "embedded",
        "host": {
            "logstash_binary": "/usr/share/logstash/bin/logstash",
            "logstash_settings": "/etc/logstash"
        }
    }
}


def deep_merge(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries. Override values take precedence.
    
    Args:
        base: Base dictionary with default values
        override: Dictionary with override values
    
    Returns:
        Merged dictionary
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = deep_merge(result[key], value)
        else:
            # Override the value
            result[key] = value
    
    return result


def load_config() -> dict:
    """
    Load LogstashUI configuration from YAML file specified in LOGSTASHUI_CONFIG env var.
    Falls back to DEFAULT_CONFIG if env var is not set or file doesn't exist.
    
    Returns:
        Configuration dictionary
    """
    config = DEFAULT_CONFIG.copy()
    
    config_path = os.environ.get('LOGSTASHUI_CONFIG')
    
    if not config_path:
        logger.info("LOGSTASHUI_CONFIG environment variable not set, using default configuration")
        return config
    
    config_file = Path(config_path)
    
    if not config_file.exists():
        logger.warning(f"Config file not found at {config_path}, using default configuration")
        return config
    
    try:
        with open(config_file, 'r') as f:
            yaml_config = yaml.safe_load(f)
        
        if yaml_config:
            config = deep_merge(DEFAULT_CONFIG, yaml_config)
            logger.info(f"Loaded configuration from {config_path}")
        else:
            logger.warning(f"Config file at {config_path} is empty, using default configuration")
    
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML config file {config_path}: {e}")
        logger.warning("Using default configuration due to YAML parsing error")
    except Exception as e:
        logger.error(f"Error loading config file {config_path}: {e}")
        logger.warning("Using default configuration due to loading error")
    
    return config


# Load configuration once at module import
CONFIG = load_config()