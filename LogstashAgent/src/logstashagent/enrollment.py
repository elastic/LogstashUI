#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import requests
import json
import base64
import logging
import socket
import hashlib
from LogstashAgent.src.logstashagent import agent_state

logger = logging.getLogger(__name__)


def get_hostname():
    """Get the hostname of the current machine"""
    try:
        return socket.gethostname()
    except Exception as e:
        logger.warning(f"Failed to get hostname: {e}, using 'unknown-host'")
        return "unknown-host"


def decode_enrollment_token(encoded_token: str) -> dict:
    """
    Decode the base64-encoded enrollment token
    
    Args:
        encoded_token: Base64-encoded JSON token
        
    Returns:
        dict: Decoded token payload containing enrollment_token
        
    Raises:
        ValueError: If token is invalid or cannot be decoded
    """
    try:
        decoded_json = base64.b64decode(encoded_token.encode('utf-8')).decode('utf-8')
        token_payload = json.loads(decoded_json)
        
        if 'enrollment_token' not in token_payload:
            raise ValueError("Invalid token payload: missing enrollment_token")
            
        return token_payload
    except Exception as e:
        raise ValueError(f"Failed to decode enrollment token: {str(e)}")


def enroll_agent(encoded_token: str, logstash_ui_url: str, agent_id: str) -> dict:
    """
    Enroll the agent with LogstashUI
    
    Args:
        encoded_token: Base64-encoded enrollment token
        logstash_ui_url: LogstashUI URL (from --logstash-ui-url)
        agent_id: Unique agent ID for this instance
        
    Returns:
        dict: Enrollment response containing api_key, policy_id, connection_id
        
    Raises:
        Exception: If enrollment fails
    """
    # Validate the enrollment token by decoding it
    token_payload = decode_enrollment_token(encoded_token)
    
    # Use provided URL
    ui_url = logstash_ui_url
    
    # Get hostname
    hostname = get_hostname()
    
    logger.info(f"Enrolling agent with LogstashUI at {ui_url}")
    logger.info(f"Hostname: {hostname}")
    logger.info(f"Agent ID: {agent_id}")
    
    # Prepare enrollment request - send the base64-encoded token, not the decoded one
    enrollment_url = f"{ui_url}/ConnectionManager/Enroll/"
    enrollment_data = {
        "enrollment_token": encoded_token,
        "host": hostname,
        "agent_id": agent_id
    }
    
    try:
        # Send enrollment request
        response = requests.post(
            enrollment_url,
            json=enrollment_data,
            timeout=30,
            verify=False  # Allow self-signed certificates
        )
        
        # Log response details for debugging
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response headers: {response.headers}")
        
        # Check for error status codes before raising
        if response.status_code >= 400:
            logger.error(f"Server returned error status {response.status_code}")
            logger.error(f"Response body: {response.text}")
        
        response.raise_for_status()
        
        # Try to parse JSON response
        try:
            result = response.json()
        except json.JSONDecodeError as e:
            logger.error(f"Server returned non-JSON response. Status: {response.status_code}")
            logger.error(f"Response text: {response.text[:500]}")  # First 500 chars
            raise Exception(f"Server returned non-JSON response (status {response.status_code}). Check that the enrollment endpoint exists at {enrollment_url}")
        
        if not result.get('success'):
            error_msg = result.get('error', 'Unknown error')
            raise Exception(f"Enrollment failed: {error_msg}")
        
        logger.info("Agent enrolled successfully!")
        logger.info(f"Connection ID: {result.get('connection_id')}")
        logger.info(f"Policy ID: {result.get('policy_id')}")
        
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to LogstashUI: {e}")
        raise Exception(f"Failed to connect to LogstashUI at {ui_url}: {str(e)}")


def compute_hash(content: str) -> str:
    """
    Compute SHA256 hash of a string
    
    Args:
        content: String content to hash
        
    Returns:
        str: Hexadecimal hash string
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def save_enrollment_config(api_key: str, logstash_ui_url: str, policy_id: int, connection_id: int, policy_config: dict):
    """
    Save enrollment configuration to state.json
    
    Args:
        api_key: API key returned from enrollment
        logstash_ui_url: LogstashUI URL
        policy_id: Policy ID assigned to this agent
        connection_id: Connection ID created for this agent
        policy_config: Policy configuration containing paths and config files
    """
    try:
        # Save enrollment data to state.json
        agent_state.update_state('enrolled', True)
        agent_state.update_state('logstash_ui_url', logstash_ui_url)
        agent_state.update_state('api_key', api_key)
        agent_state.update_state('policy_id', policy_id)
        agent_state.update_state('connection_id', connection_id)
        
        # Save paths
        agent_state.update_state('settings_path', policy_config.get('settings_path'))
        agent_state.update_state('logs_path', policy_config.get('logs_path'))
        
        # Set initial revision number to 0 (agent has no configuration yet)
        agent_state.update_state('revision_number', 0)
        
        logger.info(f"Enrollment configuration saved to state.json")
        logger.info(f"Settings path: {policy_config.get('settings_path')}")
        logger.info(f"Logs path: {policy_config.get('logs_path')}")
        logger.info(f"Revision number set to 0 (no configuration deployed yet)")
        logger.info(f"Agent is now enrolled and managed by LogstashUI at {logstash_ui_url}")
        
    except Exception as e:
        logger.error(f"Failed to save enrollment configuration: {e}")
        raise Exception(f"Failed to save enrollment configuration: {str(e)}")


def perform_enrollment(encoded_token: str, logstash_ui_url: str, agent_id: str):
    """
    Perform the complete enrollment process
    
    Args:
        encoded_token: Base64-encoded enrollment token
        logstash_ui_url: LogstashUI URL (required)
        agent_id: Unique agent ID for this instance
    """
    try:
        # Use the provided UI URL
        ui_url = logstash_ui_url
        
        # Enroll the agent
        result = enroll_agent(encoded_token, ui_url, agent_id)
        
        # Save enrollment configuration
        save_enrollment_config(
            api_key=result['api_key'],
            logstash_ui_url=ui_url,
            policy_id=result['policy_id'],
            connection_id=result['connection_id'],
            policy_config=result.get('policy_config', {})
        )
        
        logger.info("=" * 60)
        logger.info("ENROLLMENT SUCCESSFUL!")
        logger.info("=" * 60)
        logger.info(f"LogstashUI URL: {ui_url}")
        logger.info(f"Connection ID: {result['connection_id']}")
        logger.info(f"Policy ID: {result['policy_id']}")
        logger.info(f"API Key: {result['api_key'][:10]}...")
        logger.info("=" * 60)
        logger.info("Configuration saved to state.json")
        logger.info("You can now start the agent in normal mode")
        logger.info("=" * 60)
        
        return result
        
    except Exception as e:
        logger.error(f"Enrollment failed: {e}")
        raise
