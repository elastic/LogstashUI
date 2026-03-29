#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import json
import uuid
from pathlib import Path
import logging
from . import encryption

logger = logging.getLogger(__name__)

# Keys that should be encrypted when stored
ENCRYPTED_KEYS = {'api_key'}

# Path to state file
STATE_DIR = Path(__file__).parent / 'data'
STATE_FILE = STATE_DIR / 'state.json'


def get_or_create_agent_id() -> str:
    """
    Get the agent_id from state.json, or generate a new one if it doesn't exist.
    
    Returns:
        str: The unique agent ID for this instance
    """
    # Ensure data directory exists
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if state file exists
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                agent_id = state.get('agent_id')
                
                if agent_id:
                    logger.info(f"Loaded existing agent_id: {agent_id}")
                    return agent_id
                else:
                    # File exists but no agent_id, generate one
                    logger.warning("state.json exists but no agent_id found, generating new one")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to read state.json: {e}, generating new agent_id")
    
    # Generate new agent_id
    agent_id = str(uuid.uuid4())
    logger.info(f"Generated new agent_id: {agent_id}")
    
    # Save to state file
    state = {'agent_id': agent_id}
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        logger.info(f"Saved agent_id to {STATE_FILE}")
    except IOError as e:
        logger.error(f"Failed to save state.json: {e}")
    
    return agent_id


def get_state() -> dict:
    """
    Get the full state dictionary from state.json
    Automatically decrypts encrypted fields.
    
    Returns:
        dict: The state dictionary, or empty dict if file doesn't exist
    """
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                
            # Decrypt encrypted fields
            for key in ENCRYPTED_KEYS:
                if key in state and state[key]:
                    try:
                        state[key] = encryption.decrypt_credential(state[key])
                    except Exception as e:
                        logger.error(f"Failed to decrypt {key}: {e}")
                        # Keep encrypted value if decryption fails
            
            return state
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read state.json: {e}")
            return {}
    return {}


def update_state(key: str, value: any):
    """
    Update a specific key in the state file
    Automatically encrypts sensitive fields.
    
    Args:
        key: The key to update
        value: The value to set
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load existing state (this will decrypt encrypted values)
    state = get_state()
    
    # Update the key
    state[key] = value
    
    # Encrypt sensitive fields before saving
    state_to_save = state.copy()
    for encrypted_key in ENCRYPTED_KEYS:
        if encrypted_key in state_to_save and state_to_save[encrypted_key]:
            try:
                state_to_save[encrypted_key] = encryption.encrypt_credential(state_to_save[encrypted_key])
            except Exception as e:
                logger.error(f"Failed to encrypt {encrypted_key}: {e}")
                # Save unencrypted if encryption fails
    
    # Save back to file
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state_to_save, f, indent=2)
        logger.debug(f"Updated state: {key}")
    except IOError as e:
        logger.error(f"Failed to update state.json: {e}")
