#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import time
import logging
import requests
import json
import hashlib
import os
from . import agent_state

logger = logging.getLogger(__name__)


def get_config_changes(server_settings_path=None, server_logs_path=None):
    """
    Check for configuration changes by reading local config files and comparing hashes with server.
    Reads logstash.yml, jvm.options, and log4j2.properties from settings_path and computes SHA256 hashes.
    
    Args:
        server_settings_path: Optional settings path from server (used if paths changed)
        server_logs_path: Optional logs path from server (used if paths changed)
    """
    try:
        # Load agent state
        state = agent_state.get_state()
        
        # Get required fields
        logstash_ui_url = state.get('logstash_ui_url')
        api_key = state.get('api_key')
        connection_id = state.get('connection_id')
        
        # Use server-provided paths if available, otherwise fall back to state
        # This allows the agent to check new paths even if state hasn't been updated yet
        settings_path = server_settings_path if server_settings_path else state.get('settings_path')
        logs_path = server_logs_path if server_logs_path else state.get('logs_path')
        
        # Normalize path separators for cross-platform compatibility
        # Convert Windows backslashes to forward slashes (works on both Windows and Linux)
        if settings_path:
            settings_path = settings_path.replace('\\', '/')
        if logs_path:
            logs_path = logs_path.replace('\\', '/')
        
        if not all([logstash_ui_url, api_key, connection_id, settings_path]):
            logger.error("Missing required data for config change detection")
            return None
        
        # Read and hash config files
        config_hashes = {}
        
        # Ensure settings_path ends with forward slash for consistent concatenation
        if not settings_path.endswith('/'):
            settings_path = settings_path + '/'
        
        # Read logstash.yml
        logstash_yml_path = settings_path + 'logstash.yml'
        try:
            with open(logstash_yml_path, 'r', encoding='utf-8') as f:
                logstash_yml_content = f.read()
                config_hashes['logstash_yml_hash'] = hashlib.sha256(logstash_yml_content.encode('utf-8')).hexdigest()
        except FileNotFoundError:
            logger.warning(f"logstash.yml not found at {logstash_yml_path}")
            config_hashes['logstash_yml_hash'] = ''
        except Exception as e:
            logger.error(f"Error reading logstash.yml: {e}")
            config_hashes['logstash_yml_hash'] = ''
        
        # Read jvm.options
        jvm_options_path = settings_path + 'jvm.options'
        try:
            with open(jvm_options_path, 'r', encoding='utf-8') as f:
                jvm_options_content = f.read()
                config_hashes['jvm_options_hash'] = hashlib.sha256(jvm_options_content.encode('utf-8')).hexdigest()
        except FileNotFoundError:
            logger.warning(f"jvm.options not found at {jvm_options_path}")
            config_hashes['jvm_options_hash'] = ''
        except Exception as e:
            logger.error(f"Error reading jvm.options: {e}")
            config_hashes['jvm_options_hash'] = ''
        
        # Read log4j2.properties
        log4j2_properties_path = settings_path + 'log4j2.properties'
        try:
            with open(log4j2_properties_path, 'r', encoding='utf-8') as f:
                log4j2_properties_content = f.read()
                config_hashes['log4j2_properties_hash'] = hashlib.sha256(log4j2_properties_content.encode('utf-8')).hexdigest()
        except FileNotFoundError:
            logger.warning(f"log4j2.properties not found at {log4j2_properties_path}")
            config_hashes['log4j2_properties_hash'] = ''
        except Exception as e:
            logger.error(f"Error reading log4j2.properties: {e}")
            config_hashes['log4j2_properties_hash'] = ''
        
        # Prepare request data
        request_data = {
            'connection_id': connection_id,
            'logstash_yml_hash': config_hashes['logstash_yml_hash'],
            'jvm_options_hash': config_hashes['jvm_options_hash'],
            'log4j2_properties_hash': config_hashes['log4j2_properties_hash'],
            'settings_path': settings_path,
            'logs_path': logs_path
        }
        
        # Send request to server
        config_changes_url = f"{logstash_ui_url}/ConnectionManager/GetConfigChanges/"
        headers = {
            'Authorization': f'ApiKey {api_key}',
            'Content-Type': 'application/json'
        }
        
        logger.debug(f"Checking config changes with {config_changes_url}")
        
        response = requests.post(
            config_changes_url,
            json=request_data,
            headers=headers,
            timeout=30,
            verify=False
        )
        
        if response.status_code >= 400:
            logger.error(f"Config changes check failed with status {response.status_code}")
            logger.error(f"Response: {response.text}")
            return None
        
        # Try to parse JSON response
        try:
            result = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from server")
            logger.error(f"Status code: {response.status_code}")
            logger.error(f"Response headers: {dict(response.headers)}")
            logger.error(f"Response body: {response.text[:500]}")
            raise
        
        if result.get('success'):
            changes = result.get('changes', {})
            
            # Announce which configs need updating
            if changes.get('logstash_yml_changed'):
                logger.info("Configuration change found for logstash.yml")
            if changes.get('jvm_options_changed'):
                logger.info("Configuration change found for jvm.options")
            if changes.get('log4j2_properties_changed'):
                logger.info("Configuration change found for log4j2.properties")
            if changes.get('settings_path_changed'):
                logger.info("Configuration change found for settings_path")
            if changes.get('logs_path_changed'):
                logger.info("Configuration change found for logs_path")
            
            if not any(changes.values()):
                logger.info("No configuration file changes detected")
            
            return result
        else:
            logger.warning(f"Config changes check returned success=false: {result.get('message', 'Unknown error')}")
            return result
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to check config changes with LogstashUI: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during config changes check: {e}")
        return None


def check_in():
    """
    Send check-in to LogstashUI with current agent state
    
    Returns:
        dict: Response from LogstashUI or None if check-in fails
    """
    try:
        # Load agent state
        state = agent_state.get_state()
        
        # Verify agent is enrolled
        if not state.get('enrolled'):
            logger.error("Agent is not enrolled. Please enroll first using --enroll")
            return None
        
        # Get required fields
        logstash_ui_url = state.get('logstash_ui_url')
        api_key = state.get('api_key')
        connection_id = state.get('connection_id')
        
        if not all([logstash_ui_url, api_key, connection_id]):
            logger.error("Missing required enrollment data. Please re-enroll the agent.")
            return None
        
        # Prepare check-in data
        check_in_data = {
            'connection_id': connection_id,
            'revision_number': state.get('revision_number', 0)
        }
        
        # Send check-in request
        check_in_url = f"{logstash_ui_url}/ConnectionManager/CheckIn/"
        headers = {
            'Authorization': f'ApiKey {api_key}',
            'Content-Type': 'application/json'
        }
        
        logger.debug(f"Sending check-in to {check_in_url}")
        
        response = requests.post(
            check_in_url,
            json=check_in_data,
            headers=headers,
            timeout=30,
            verify=False  # Allow self-signed certificates
        )
        
        # Check for error status codes
        if response.status_code >= 400:
            logger.error(f"Check-in failed with status {response.status_code}")
            logger.error(f"Response: {response.text}")
            response.raise_for_status()
        
        # Try to parse JSON response
        try:
            result = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from server")
            logger.error(f"Status code: {response.status_code}")
            logger.error(f"Response headers: {dict(response.headers)}")
            logger.error(f"Response body: {response.text[:500]}")
            raise
        
        if result.get('success'):
            logger.info("Check-in successful")
            
            # Compare revision numbers
            agent_revision = state.get('revision_number', 0)
            server_revision = result.get('current_revision_number', 0)
            
            if agent_revision == server_revision:
                logger.info(f"Agent is up-to-date (revision {agent_revision})")
            else:
                logger.warning(f"New revision detected, checking difference in config. Agent revision: {agent_revision}, Server revision: {server_revision}")
                # Get config changes from server, using server-provided paths
                # This ensures agent can check new paths even if state hasn't been updated
                server_settings_path = result.get('settings_path')
                server_logs_path = result.get('logs_path')
                get_config_changes(server_settings_path, server_logs_path)
            
            return result
        else:
            logger.warning(f"Check-in returned success=false: {result.get('message', 'Unknown error')}")
            return result
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to check in with LogstashUI: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during check-in: {e}")
        return None


def run_controller():
    """
    Main controller loop - runs indefinitely and checks in every 60 seconds
    """
    logger.info("=" * 60)
    logger.info("LOGSTASH AGENT CONTROLLER STARTED")
    logger.info("=" * 60)
    
    # Load agent state to verify enrollment
    state = agent_state.get_state()
    
    if not state.get('enrolled'):
        logger.error("Agent is not enrolled!")
        logger.error("Please enroll the agent first using:")
        logger.error("  python main.py --enroll <TOKEN> --logstash-ui-url <URL>")
        return
    
    logger.info(f"Agent ID: {state.get('agent_id')}")
    logger.info(f"Connection ID: {state.get('connection_id')}")
    logger.info(f"LogstashUI URL: {state.get('logstash_ui_url')}")
    logger.info(f"Policy ID: {state.get('policy_id')}")
    logger.info("=" * 60)
    logger.info("Starting check-in loop (every 60 seconds)")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    check_in_interval = 60  # seconds
    
    try:
        while True:
            # Perform check-in
            result = check_in()
            
            if result:
                logger.debug(f"Check-in response: {result}")
            else:
                logger.warning("Check-in failed, will retry in 60 seconds")
            
            # Wait for next check-in
            time.sleep(check_in_interval)
            
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 60)
        logger.info("Controller stopped by user")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Controller error: {e}")
        raise
