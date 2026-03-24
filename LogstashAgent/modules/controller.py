#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import time
import logging
import requests
import json
from . import agent_state

logger = logging.getLogger(__name__)


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
            'settings_path': state.get('settings_path'),
            'logs_path': state.get('logs_path'),
            'logstash_yml_hash': state.get('logstash_yml_hash'),
            'jvm_options_hash': state.get('jvm_options_hash'),
            'log4j2_properties_hash': state.get('log4j2_properties_hash')
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
