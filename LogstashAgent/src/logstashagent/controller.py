#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import time
import logging
import requests
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from . import agent_state
from . import encryption
from .ls_keystore_utils import LogstashKeystore
from .ls_keystore_utils.exceptions import (
    LogstashKeystoreException,
    IncorrectPassword,
    LogstashKeystoreModified
)

logger = logging.getLogger(__name__)


def update_logstash_yml(settings_path, content):
    """
    Update logstash.yml file with new content.
    
    Args:
        settings_path: Path to Logstash settings directory
        content: New content for logstash.yml
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logstash_yml_path = settings_path + 'logstash.yml'
        logger.info(f"Updating logstash.yml at {logstash_yml_path}")
        
        with open(logstash_yml_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info("Successfully updated logstash.yml")
        return True
    except Exception as e:
        logger.error(f"Failed to update logstash.yml: {e}")
        return False


def update_jvm_options(settings_path, content):
    """
    Update jvm.options file with new content.
    
    Args:
        settings_path: Path to Logstash settings directory
        content: New content for jvm.options
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        jvm_options_path = settings_path + 'jvm.options'
        logger.info(f"Updating jvm.options at {jvm_options_path}")
        
        with open(jvm_options_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info("Successfully updated jvm.options")
        return True
    except Exception as e:
        logger.error(f"Failed to update jvm.options: {e}")
        return False


def update_log4j2_properties(settings_path, content):
    """
    Update log4j2.properties file with new content.
    
    Args:
        settings_path: Path to Logstash settings directory
        content: New content for log4j2.properties
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        log4j2_properties_path = settings_path + 'log4j2.properties'
        logger.info(f"Updating log4j2.properties at {log4j2_properties_path}")
        
        with open(log4j2_properties_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info("Successfully updated log4j2.properties")
        return True
    except Exception as e:
        logger.error(f"Failed to update log4j2.properties: {e}")
        return False


def update_keystore(settings_path, keystore_changes):
    """
    Update the Logstash keystore with set/delete operations.
    
    Args:
        settings_path: Path to Logstash settings directory
        keystore_changes: Dictionary with 'set' and 'delete' keys
            - 'set': Dictionary of {key_name: key_value} to add/update
            - 'delete': List of key names to remove
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info(f"Starting keystore update at {settings_path}")
        logger.debug(f"Keystore changes requested: {keystore_changes}")
        
        # Get keystore password from agent state
        # Use empty string "" for passwordless keystores (PKCS12 standard)
        state = agent_state.get_state()
        keystore_password = state.get('keystore_password', '')
        
        # Log password configuration status
        if not keystore_password:
            logger.info("Keystore password: NOT CONFIGURED (using empty string for passwordless keystore)")
            keystore_password = ""  # PKCS12 standard for passwordless
        else:
            logger.info("Keystore password: CONFIGURED (using provided password)")
        
        # Normalize path separators
        if settings_path:
            settings_path = settings_path.replace('\\', '/')
        if not settings_path.endswith('/'):
            settings_path = settings_path + '/'
        
        logger.debug(f"Normalized settings path: {settings_path}")
        
        # Extract set and delete operations
        keys_to_set = keystore_changes.get('set', {})
        keys_to_delete = keystore_changes.get('delete', [])
        
        logger.info(f"Operations summary: {len(keys_to_set)} keys to set, {len(keys_to_delete)} keys to delete")
        
        if not keys_to_set and not keys_to_delete:
            logger.info("No keystore changes to apply - skipping keystore operations")
            return False
        
        # Load the keystore, recreating it if the password is wrong or it doesn't exist
        logger.info("Attempting to load existing keystore...")
        try:
            ks = LogstashKeystore.load(
                path_settings=settings_path,
                password=keystore_password
            )
            logger.info("Successfully loaded existing keystore")
            logger.debug(f"Keystore contains {len(ks.keys)} existing keys")
        except IncorrectPassword:
            logger.warning("Incorrect keystore password - deleting incompatible keystore and recreating")
            from pathlib import Path
            keystore_file = Path(settings_path) / 'logstash.keystore'
            try:
                keystore_file.unlink(missing_ok=True)
                logger.info("Deleted incompatible keystore file")
            except Exception as del_e:
                logger.warning(f"Could not delete keystore file: {del_e}")
            try:
                ks = LogstashKeystore.create(
                    path_settings=settings_path,
                    password=keystore_password
                )
                logger.info("Recreated keystore with current stored password")
            except Exception as create_error:
                logger.error(f"Failed to recreate keystore: {create_error}")
                return False
        except LogstashKeystoreException as e:
            logger.warning(f"Failed to load keystore: {e}")
            try:
                logger.info("Keystore does not exist - creating new keystore...")
                ks = LogstashKeystore.create(
                    path_settings=settings_path,
                    password=keystore_password
                )
                logger.info("Successfully created new keystore")
            except Exception as create_error:
                logger.error(f"Failed to create keystore: {create_error}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error loading keystore: {e}")
            return False
        
        # Perform delete operations first
        if keys_to_delete:
            logger.info(f"Processing DELETE operations for {len(keys_to_delete)} key(s): {keys_to_delete}")
            try:
                # Filter out keys that don't exist
                existing_keys = ks.keys
                logger.debug(f"Current keystore keys: {existing_keys}")
                keys_to_actually_delete = [k for k in keys_to_delete if k.upper() in existing_keys]
                
                if keys_to_actually_delete:
                    logger.info(f"Deleting keys: {keys_to_actually_delete}")
                    ks.remove_key(keys_to_actually_delete)
                    logger.info(f"Successfully deleted {len(keys_to_actually_delete)} key(s) from keystore")
                    for key in keys_to_actually_delete:
                        logger.debug(f"  - Deleted key: {key}")
                else:
                    logger.info("No keys to delete - all specified keys don't exist in keystore")
                    for key in keys_to_delete:
                        logger.debug(f"  - Key not found: {key}")
            except LogstashKeystoreModified as e:
                logger.error(f"Keystore was modified externally during delete operation: {e}")
                logger.error("Cannot proceed - keystore state has changed")
                return False
            except Exception as e:
                logger.error(f"Failed to delete keys: {e}")
                logger.exception("Delete operation exception details:")
                return False
        
        # Perform set operations
        if keys_to_set:
            logger.info(f"Processing SET operations for {len(keys_to_set)} key(s): {list(keys_to_set.keys())}")
            
            # Decrypt keystore values using API key from agent state
            state = agent_state.get_state()
            api_key_decrypted = state.get('api_key')
            
            if not api_key_decrypted:
                logger.error("No API key found in agent state - cannot decrypt keystore values")
                return False
            
            try:
                # Decrypt all keystore values using the API key
                decrypted_keys = {}
                for key_name, encrypted_value in keys_to_set.items():
                    try:
                        # Decrypt the value (format: "api_key:actual_value")
                        decrypted_combined = encryption.decrypt_credential(encrypted_value)
                        
                        # Verify API key prefix and extract actual value
                        if not decrypted_combined.startswith(f"{api_key_decrypted}:"):
                            logger.error(f"API key mismatch for keystore value {key_name} - this value was encrypted for a different agent")
                            return False
                        
                        # Extract the actual keystore value after the API key prefix
                        actual_value = decrypted_combined[len(api_key_decrypted) + 1:]
                        decrypted_keys[key_name] = actual_value
                        logger.debug(f"  - Decrypted key: {key_name}")
                    except Exception as e:
                        logger.error(f"Failed to decrypt keystore value for {key_name}: {e}")
                        return False
                
                # Use decrypted keys instead of encrypted ones
                keys_to_set = decrypted_keys
                logger.info(f"Successfully decrypted {len(keys_to_set)} keystore value(s)")
                
            except Exception as e:
                logger.error(f"Failed to decrypt keystore values: {e}")
                logger.exception("Decryption exception details:")
                return False
            
            try:
                # Log each key being set (without values for security)
                for key_name in keys_to_set.keys():
                    logger.debug(f"  - Setting key: {key_name}")
                
                ks.add_key(keys_to_set)
                logger.info(f"Successfully set {len(keys_to_set)} key(s) in keystore")
                
                # Verify keys were set
                for key_name in keys_to_set.keys():
                    if key_name.upper() in ks.keys:
                        logger.debug(f"  - Verified key exists: {key_name}")
                    else:
                        logger.warning(f"  - Key verification failed: {key_name}")
            except LogstashKeystoreModified as e:
                logger.error(f"Keystore was modified externally during set operation: {e}")
                logger.error("Cannot proceed - keystore state has changed")
                return False
            except Exception as e:
                logger.error(f"Failed to set keys: {e}")
                logger.exception("Set operation exception details:")
                return False
        
        # Update keystore state with hashes
        logger.info("Updating agent state with new keystore hashes...")
        new_keystore_state = {}
        try:
            all_keys = ks.keys
            logger.debug(f"Reading {len(all_keys)} keys from keystore for state update")
            
            for key_name in all_keys:
                key_value = ks.get_key(key_name)
                if key_value is not None:
                    # Hash the key_name + key_value for change detection
                    hash_input = f"{key_name}{key_value}"
                    key_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
                    new_keystore_state[key_name] = key_hash
                    logger.debug(f"  - Computed hash for key: {key_name}")
                else:
                    logger.warning(f"  - Key {key_name} returned None value")
            
            # Update agent state with new keystore hashes
            agent_state.update_state('keystore', new_keystore_state)
            logger.info(f"Successfully updated agent state with {len(new_keystore_state)} keystore key hash(es)")
        except Exception as e:
            logger.error(f"Failed to update keystore state: {e}")
            logger.exception("State update exception details:")
            logger.warning("Keystore was updated successfully, but state update failed")
            # Don't return False here - the keystore was updated successfully
        
        logger.info("Keystore update completed successfully")
        logger.info(f"Final keystore contains {len(ks.keys)} key(s)")
        return True
        
    except Exception as e:
        logger.error(f"Unexpected error in update_keystore: {e}")
        logger.exception("Keystore update exception details:")
        return False


def build_pipelines_state(settings_path):
    """
    Scans {settings_path}/conf.d/*.conf and {settings_path}/pipelines.yml to build
    the current pipelines state dict from agent state (stored pipeline_hash values).

    Returns:
        dict: {pipeline_name: {config_hash: str, settings: {...}}}
              config_hash is the server's pipeline_hash stored after the last apply.
    """
    try:
        import os
        import yaml

        if settings_path:
            settings_path = settings_path.replace('\\', '/')
        if not settings_path.endswith('/'):
            settings_path = settings_path + '/'

        conf_d_path = settings_path + 'conf.d/'

        # Start from persisted state so config_hash values are the server's pipeline_hash
        state = agent_state.get_state()
        persisted_pipelines = state.get('pipelines', {})

        if not os.path.isdir(conf_d_path):
            logger.debug(f"conf.d directory not found at {conf_d_path}, returning empty pipelines state")
            return {}

        conf_files = [f for f in os.listdir(conf_d_path) if f.endswith('.conf')]
        if not conf_files:
            logger.debug("No .conf files found in conf.d")
            return {}

        # Parse pipelines.yml for per-pipeline settings
        pipelines_yml_path = settings_path + 'pipelines.yml'
        pipeline_settings_map = {}
        try:
            with open(pipelines_yml_path, 'r', encoding='utf-8') as f:
                pipeline_list = yaml.safe_load(f)
            if isinstance(pipeline_list, list):
                for entry in pipeline_list:
                    pid = entry.get('pipeline.id')
                    if pid:
                        pipeline_settings_map[pid] = {
                            'pipeline_workers': entry.get('pipeline.workers', 1),
                            'pipeline_batch_size': entry.get('pipeline.batch.size', 128),
                            'pipeline_batch_delay': entry.get('pipeline.batch.delay', 50),
                            'queue_type': entry.get('queue.type', 'memory'),
                            'queue_max_bytes': entry.get('queue.max_bytes', '1gb'),
                            'queue_checkpoint_writes': entry.get('queue.checkpoint.writes', 1024),
                        }
        except FileNotFoundError:
            logger.debug(f"pipelines.yml not found at {pipelines_yml_path}")
        except Exception as e:
            logger.warning(f"Failed to parse pipelines.yml: {e}")

        pipelines_state = {}
        for conf_file in conf_files:
            pipeline_name = conf_file[:-5]  # strip .conf
            # Use the stored server pipeline_hash as config_hash for stable comparison
            stored = persisted_pipelines.get(pipeline_name, {})
            config_hash = stored.get('config_hash', '')
            settings = pipeline_settings_map.get(pipeline_name, stored.get('settings', {}))
            pipelines_state[pipeline_name] = {
                'config_hash': config_hash,
                'settings': settings,
            }

        logger.debug(f"Built pipelines state: {list(pipelines_state.keys())}")
        return pipelines_state

    except Exception as e:
        logger.error(f"Failed to build pipelines state: {e}")
        return {}


def update_pipelines(settings_path, pipeline_changes):
    """
    Apply pipeline set/delete directives from the server.

    - Writes {settings_path}/conf.d/{name}.conf for each entry in 'set'
    - Deletes {settings_path}/conf.d/{name}.conf for each entry in 'delete'
    - Rewrites {settings_path}/pipelines.yml from current conf.d state
    - Updates agent state with new pipelines dict (using server pipeline_hash values)

    Args:
        settings_path: Path to Logstash settings directory
        pipeline_changes: {'set': {name: {lscl, pipeline_hash, settings}}, 'delete': [name, ...]}

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import os
        import yaml

        if settings_path:
            settings_path = settings_path.replace('\\', '/')
        if not settings_path.endswith('/'):
            settings_path = settings_path + '/'

        conf_d_path = settings_path + 'conf.d/'
        pipelines_yml_path = settings_path + 'pipelines.yml'

        pipelines_to_set = pipeline_changes.get('set', {})
        pipelines_to_delete = pipeline_changes.get('delete', [])

        logger.info(f"Pipeline update: {len(pipelines_to_set)} to set, {len(pipelines_to_delete)} to delete")

        if not pipelines_to_set and not pipelines_to_delete:
            logger.info("No pipeline changes to apply")
            return False

        # Ensure conf.d directory exists
        os.makedirs(conf_d_path, exist_ok=True)

        # Process deletes
        for pipeline_name in pipelines_to_delete:
            conf_path = conf_d_path + pipeline_name + '.conf'
            try:
                if os.path.isfile(conf_path):
                    os.remove(conf_path)
                    logger.info(f"Deleted pipeline config: {conf_path}")
                else:
                    logger.debug(f"Pipeline config not found (already gone): {conf_path}")
            except Exception as e:
                logger.error(f"Failed to delete pipeline config {conf_path}: {e}")
                return False

        # Process sets
        for pipeline_name, pipeline_data in pipelines_to_set.items():
            lscl_content = pipeline_data.get('lscl', '')
            conf_path = conf_d_path + pipeline_name + '.conf'
            try:
                with open(conf_path, 'w', encoding='utf-8') as f:
                    f.write(lscl_content)
                logger.info(f"Wrote pipeline config: {conf_path}")
            except Exception as e:
                logger.error(f"Failed to write pipeline config {conf_path}: {e}")
                return False

        # Build current state from conf.d (all .conf files now present)
        try:
            conf_files = [f for f in os.listdir(conf_d_path) if f.endswith('.conf')]
        except Exception as e:
            logger.error(f"Failed to list conf.d directory: {e}")
            return False

        # Load existing agent state for settings of pipelines we didn't just receive
        existing_state = agent_state.get_state()
        existing_pipelines = existing_state.get('pipelines', {})

        # Build pipelines.yml entries and new agent state
        yml_entries = []
        new_pipelines_state = {}

        for conf_file in sorted(conf_files):
            pipeline_name = conf_file[:-5]  # strip .conf

            # Get settings: prefer freshly received, fall back to existing state
            if pipeline_name in pipelines_to_set:
                settings = pipelines_to_set[pipeline_name].get('settings', {})
                config_hash = pipelines_to_set[pipeline_name].get('pipeline_hash', '')
            else:
                existing = existing_pipelines.get(pipeline_name, {})
                settings = existing.get('settings', {})
                config_hash = existing.get('config_hash', '')

            workers = settings.get('pipeline_workers', 1)
            batch_size = settings.get('pipeline_batch_size', 128)
            batch_delay = settings.get('pipeline_batch_delay', 50)
            queue_type = settings.get('queue_type', 'memory')
            queue_max_bytes = settings.get('queue_max_bytes', '1gb')
            checkpoint_writes = settings.get('queue_checkpoint_writes', 1024)

            yml_entry = {
                'pipeline.id': pipeline_name,
                'path.config': f"{conf_d_path}{pipeline_name}.conf",
                'pipeline.workers': workers,
                'pipeline.batch.size': batch_size,
                'pipeline.batch.delay': batch_delay,
                'queue.type': queue_type,
                'queue.max_bytes': queue_max_bytes,
                'queue.checkpoint.writes': checkpoint_writes,
            }
            yml_entries.append(yml_entry)

            new_pipelines_state[pipeline_name] = {
                'config_hash': config_hash,
                'settings': {
                    'pipeline_workers': workers,
                    'pipeline_batch_size': batch_size,
                    'pipeline_batch_delay': batch_delay,
                    'queue_type': queue_type,
                    'queue_max_bytes': queue_max_bytes,
                    'queue_checkpoint_writes': checkpoint_writes,
                }
            }

        # Write pipelines.yml
        try:
            with open(pipelines_yml_path, 'w', encoding='utf-8') as f:
                yaml.dump(yml_entries, f, default_flow_style=False, allow_unicode=True)
            logger.info(f"Rewrote pipelines.yml with {len(yml_entries)} pipeline(s)")
        except Exception as e:
            logger.error(f"Failed to write pipelines.yml: {e}")
            return False

        # Update agent state
        agent_state.update_state('pipelines', new_pipelines_state)
        logger.info(f"Updated agent pipelines state with {len(new_pipelines_state)} pipeline(s)")

        return True

    except Exception as e:
        logger.error(f"Unexpected error in update_pipelines: {e}")
        logger.exception("update_pipelines exception details:")
        return False


def restart_logstash():
    """
    Restart the Logstash service.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info("Restarting Logstash service...")
        
        # Try systemctl first (most common on Linux)
        try:
            result = subprocess.run(
                ['systemctl', 'restart', 'logstash'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info("Logstash service restarted successfully via systemctl")
                return True
            else:
                logger.warning(f"systemctl restart failed: {result.stderr}")
        except FileNotFoundError:
            logger.debug("systemctl not found, trying service command")
        
        # Try service command as fallback
        try:
            result = subprocess.run(
                ['service', 'logstash', 'restart'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info("Logstash service restarted successfully via service command")
                return True
            else:
                logger.warning(f"service restart failed: {result.stderr}")
        except FileNotFoundError:
            logger.debug("service command not found")
        
        logger.error("Failed to restart Logstash - no suitable service manager found")
        return False
        
    except subprocess.TimeoutExpired:
        logger.error("Logstash restart timed out after 30 seconds")
        return False
    except Exception as e:
        logger.error(f"Failed to restart Logstash service: {e}")
        return False


def get_config_changes(server_settings_path=None, server_logs_path=None, server_binary_path=None):
    """
    Check for configuration changes by reading local config files and comparing hashes with server.
    Reads logstash.yml, jvm.options, and log4j2.properties from settings_path and computes SHA256 hashes.
    
    Args:
        server_settings_path: Optional settings path from server (used if paths changed)
        server_logs_path: Optional logs path from server (used if paths changed)
        server_binary_path: Optional binary path from server (used if paths changed)
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
        binary_path = server_binary_path if server_binary_path else state.get('binary_path')
        
        # Normalize path separators for cross-platform compatibility
        # Convert Windows backslashes to forward slashes (works on both Windows and Linux)
        if settings_path:
            settings_path = settings_path.replace('\\', '/')
        if logs_path:
            logs_path = logs_path.replace('\\', '/')
        if binary_path:
            binary_path = binary_path.replace('\\', '/')
        
        if not all([logstash_ui_url, api_key, connection_id, settings_path]):
            logger.error("Missing required data for config change detection")
            return None
        
        # Ensure settings_path ends with forward slash for consistent concatenation
        if not settings_path.endswith('/'):
            settings_path = settings_path + '/'
        
        logger.info(f"Checking for config files at: {settings_path}")
        
        # Read and hash config files
        config_hashes = {}
        
        # Track if any files existed initially (to determine if we should restart Logstash)
        files_existed = False
        
        # Read logstash.yml
        logstash_yml_path = settings_path + 'logstash.yml'
        try:
            with open(logstash_yml_path, 'r', encoding='utf-8') as f:
                logstash_yml_content = f.read()
                config_hashes['logstash_yml_hash'] = hashlib.sha256(logstash_yml_content.encode('utf-8')).hexdigest()
                files_existed = True
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
                files_existed = True
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
                files_existed = True
        except FileNotFoundError:
            logger.warning(f"log4j2.properties not found at {log4j2_properties_path}")
            config_hashes['log4j2_properties_hash'] = ''
        except Exception as e:
            logger.error(f"Error reading log4j2.properties: {e}")
            config_hashes['log4j2_properties_hash'] = ''
        
        # If no files existed, error out immediately
        logger.info(f"files_existed flag: {files_existed}")
        if not files_existed:
            logger.error(f"Provided file path of {settings_path} was not found. Do you have Logstash installed and is this the correct settings path?")
            return None
        
        logger.info(f"Files found, proceeding to check with server")
        
        # Get keystore state from agent state
        keystore_state = state.get('keystore', {})
        logger.debug(f"Current keystore state: {keystore_state}")

        # Get pipelines state
        pipelines_state = build_pipelines_state(settings_path)
        logger.debug(f"Current pipelines state: {list(pipelines_state.keys())}")

        # Prepare request data
        request_data = {
            'connection_id': connection_id,
            'logstash_yml_hash': config_hashes['logstash_yml_hash'],
            'jvm_options_hash': config_hashes['jvm_options_hash'],
            'log4j2_properties_hash': config_hashes['log4j2_properties_hash'],
            'settings_path': settings_path,
            'logs_path': logs_path,
            'binary_path': binary_path,
            'keystore': keystore_state,
            'keystore_password_hash': state.get('keystore_password_hash', ''),
            'pipelines': pipelines_state,
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
            
            # Debug: Log what server returned
            logger.debug(f"Server response - changes: {changes}")
            logger.debug(f"files_existed flag: {files_existed}")
            
            # Fail-fast rollout: each step must succeed before proceeding.
            # On any failure, stop immediately — no restart, no revision increment.
            # requires_restart is only set for changes that need a full Logstash restart
            # (logstash.yml, jvm.options, log4j2.properties, keystore).
            # Pipeline changes are applied dynamically and do not require a restart.
            files_updated = False
            requires_restart = False
            failed_operations = []
            rollout_aborted = False

            # Update logstash.yml if changed
            logstash_yml_content = changes.get('logstash_yml')
            if logstash_yml_content and logstash_yml_content != False:
                logger.info("Configuration change found for logstash.yml")
                if update_logstash_yml(settings_path, logstash_yml_content):
                    files_updated = True
                    requires_restart = True
                else:
                    logger.error("Failed to update logstash.yml - aborting rollout")
                    failed_operations.append('logstash.yml write failed')
                    rollout_aborted = True

            # Update jvm.options if changed
            if not rollout_aborted:
                jvm_options_content = changes.get('jvm_options')
                if jvm_options_content and jvm_options_content != False:
                    logger.info("Configuration change found for jvm.options")
                    if update_jvm_options(settings_path, jvm_options_content):
                        files_updated = True
                        requires_restart = True
                    else:
                        logger.error("Failed to update jvm.options - aborting rollout")
                        failed_operations.append('jvm.options write failed')
                        rollout_aborted = True

            # Update log4j2.properties if changed
            if not rollout_aborted:
                log4j2_properties_content = changes.get('log4j2_properties')
                if log4j2_properties_content and log4j2_properties_content != False:
                    logger.info("Configuration change found for log4j2.properties")
                    if update_log4j2_properties(settings_path, log4j2_properties_content):
                        files_updated = True
                        requires_restart = True
                    else:
                        logger.error("Failed to update log4j2.properties - aborting rollout")
                        failed_operations.append('log4j2.properties write failed')
                        rollout_aborted = True

            # Check for path changes (informational only - can't update these automatically)
            if changes.get('settings_path') and changes.get('settings_path') != False:
                logger.info(f"Configuration change found for settings_path: {changes.get('settings_path')}")
            if changes.get('logs_path') and changes.get('logs_path') != False:
                logger.info(f"Configuration change found for logs_path: {changes.get('logs_path')}")

            # Handle keystore password change (must run BEFORE keystore key changes)
            if not rollout_aborted:
                keystore_password_response = changes.get('keystore_password')
                if keystore_password_response and keystore_password_response != False:
                    logger.info("Keystore password change detected - will always recreate keystore")
                    actual_password = ''
                    new_hash = ''
                    try:
                        decrypted_combined = encryption.decrypt_credential(keystore_password_response)
                        if not decrypted_combined.startswith(f"{api_key}:"):
                            raise ValueError("API key prefix mismatch in decrypted keystore password")
                        actual_password = decrypted_combined[len(api_key) + 1:]
                        new_hash = hashlib.sha256(actual_password.encode('utf-8')).hexdigest()
                        logger.info("Successfully decrypted new keystore password")
                    except Exception as decrypt_error:
                        # Non-fatal: log and record the failure but continue the rollout.
                        # The server will keep detecting the hash mismatch and retry on
                        # every subsequent sync until the encryption key issue resolves.
                        logger.error(f"Failed to decrypt keystore password from server: {decrypt_error}")
                        logger.warning("Proceeding with keystore recreation using empty password - will self-correct on next sync")
                        failed_operations.append(f'keystore_password decrypt failed: {decrypt_error}')

                    # Always delete and recreate the keystore regardless of whether
                    # decryption succeeded. Uses the decrypted password if available,
                    # otherwise an empty password so key deltas can still be applied.
                    from pathlib import Path
                    keystore_file = Path(settings_path) / 'logstash.keystore'
                    try:
                        keystore_file.unlink(missing_ok=True)
                        logger.info("Deleted existing keystore file")
                    except Exception as del_e:
                        logger.warning(f"Could not delete keystore file: {del_e}")

                    try:
                        LogstashKeystore.create(path_settings=settings_path, password=actual_password)
                        logger.info("Created new keystore%s", " with updated password" if actual_password else " with empty password (decrypt failed)")
                        agent_state.update_state('keystore_password', actual_password)
                        agent_state.update_state('keystore_password_hash', new_hash)
                        state = agent_state.get_state()
                        files_updated = True
                        requires_restart = True
                    except Exception as create_error:
                        logger.error(f"Failed to create keystore: {create_error}")
                        logger.exception("Keystore creation exception details:")
                        failed_operations.append(f'keystore creation failed: {create_error}')
                        rollout_aborted = True

            # Handle keystore changes
            if not rollout_aborted:
                keystore_changes = changes.get('keystore')
                if keystore_changes and keystore_changes != False:
                    logger.info("Keystore changes detected")
                    if update_keystore(settings_path, keystore_changes):
                        files_updated = True
                        requires_restart = True
                    else:
                        logger.error("Failed to update keystore - aborting rollout")
                        failed_operations.append('keystore update failed')
                        rollout_aborted = True

            # Handle pipeline changes (no restart needed — Logstash reloads pipelines dynamically)
            if not rollout_aborted:
                pipeline_changes = changes.get('pipelines')
                if pipeline_changes and pipeline_changes != False:
                    logger.info("Pipeline changes detected")
                    if update_pipelines(settings_path, pipeline_changes):
                        files_updated = True
                    else:
                        logger.error("Failed to update pipelines - aborting rollout")
                        failed_operations.append('pipelines update failed')
                        rollout_aborted = True

            if rollout_aborted:
                logger.error(f"Rollout aborted due to failures: {failed_operations}")
            elif files_updated:
                # All updates succeeded — restart if needed and increment revision
                if requires_restart:
                    if files_existed:
                        logger.info("Configuration files updated, restarting Logstash service...")
                        if restart_logstash():
                            logger.info("Logstash restart completed successfully")
                        else:
                            logger.error("Logstash restart failed - manual intervention may be required")
                            failed_operations.append('logstash restart failed')
                    else:
                        logger.info("Configuration files created - Logstash restart skipped (files didn't exist previously)")
                else:
                    logger.info("Pipeline-only changes applied - Logstash restart not required")

                # Update agent's revision number to match server after successful changes
                if not failed_operations:
                    server_revision = result.get('current_revision')
                    if server_revision is not None:
                        agent_state.update_state('revision_number', server_revision)
                        logger.info(f"Updated agent revision number to {server_revision}")
            else:
                logger.info("No configuration file changes detected")

            # Persist policy apply result to state (fires regardless of whether files changed)
            server_revision = result.get('current_revision')
            apply_success = len(failed_operations) == 0
            agent_state.update_state('last_policy_apply', {
                'success': apply_success,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'revision': server_revision,
                'failed_operations': failed_operations,
            })
            logger.info(f"Saved last_policy_apply: success={apply_success}, failed={failed_operations}")

            return result
        else:
            logger.warning(f"Config changes check returned success=false: {result.get('message', 'Unknown error')}")
            return result
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to check config changes with logstashui: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during config changes check: {e}")
        return None


def get_logstash_api_status(api_port=9600):
    """
    Query the Logstash node info API at http://localhost:{api_port}/.

    Returns:
        dict with keys: accessible, status, version, host, error
    """
    from .logstash_api import LogstashAPI
    base_url = f"http://localhost:{api_port}"
    try:
        api = LogstashAPI(base_url=base_url)
        data = api.get_node_info()
        return {
            'accessible': True,
            'status': data.get('status', 'unknown'),
            'version': data.get('version'),
            'host': data.get('host'),
            'error': None,
        }
    except Exception as e:
        logger.warning(f"Logstash API not accessible at {base_url}: {e}")
        return {
            'accessible': False,
            'status': 'unknown',
            'version': None,
            'host': None,
            'error': str(e)[:200],
        }


def get_logstash_health_report(api_port=9600):
    """
    Query the Logstash /_health_report endpoint.

    The raw Logstash response is stripped down to only the fields the UI needs
    (status, symptom, diagnosis, nested indicators) before being sent to
    LogstashUI. This avoids shipping large/unpredictable sub-objects (impacts,
    details, flow metrics) that could contain non-JSON-serializable values and
    silently break the check-in POST.

    All interpretation of the indicator tree stays on the LogstashUI side.

    Returns:
        dict with keys: accessible, status, symptom, indicators, error
    """
    from .logstash_api import LogstashAPI
    base_url = f"http://localhost:{api_port}"

    def strip_indicators(indicators_dict):
        """
        Recursively keep only the fields the UI renders:
        status, symptom, diagnosis (cause + action only), and nested indicators.
        Everything else (impacts, details, flow, help_url, ids, …) is dropped.
        """
        result = {}
        for name, ind in (indicators_dict or {}).items():
            result[name] = {
                'status': ind.get('status'),
                'symptom': ind.get('symptom'),
                'diagnosis': [
                    {'cause': d.get('cause'), 'action': d.get('action')}
                    for d in ind.get('diagnosis', [])
                ],
                'indicators': strip_indicators(ind.get('indicators', {})),
            }
        return result

    try:
        api = LogstashAPI(base_url=base_url)
        data = api.get_instance_health()
        indicators = strip_indicators(data.get('indicators', {}))
        logger.debug(f"Health report: status={data.get('status')}, indicators={list(indicators.keys())}")
        return {
            'accessible': True,
            'status': data.get('status', 'unknown'),
            'symptom': data.get('symptom'),
            'indicators': indicators,
            'error': None,
        }
    except Exception as e:
        logger.warning(f"Logstash health report not accessible at {base_url}: {e}")
        return {
            'accessible': False,
            'status': 'unknown',
            'symptom': None,
            'indicators': {},
            'error': str(e)[:200],
        }


def get_logstash_node_stats(api_port=9600):
    """
    Query the Logstash /_node/stats endpoint and return condensed node-level
    statistics. Pipeline-level detail is intentionally excluded.

    Returns:
        dict with keys: accessible, jvm, process, events, pipeline, reloads, error
    """
    from .logstash_api import LogstashAPI
    base_url = f"http://localhost:{api_port}"
    try:
        api = LogstashAPI(base_url=base_url)
        data = api.get_node_stats()

        jvm      = data.get('jvm', {})
        mem      = jvm.get('mem', {})
        gc       = jvm.get('gc', {}).get('collectors', {})
        process  = data.get('process', {})
        cpu      = process.get('cpu', {})
        events   = data.get('events', {})
        pipeline = data.get('pipeline', {})
        reloads  = data.get('reloads', {})

        return {
            'accessible': True,
            'jvm': {
                'heap_used_percent':        mem.get('heap_used_percent'),
                'uptime_in_millis':         jvm.get('uptime_in_millis'),
                'gc_old_collection_count':  gc.get('old', {}).get('collection_count'),
                'gc_young_collection_count': gc.get('young', {}).get('collection_count'),
            },
            'process': {
                'cpu_percent':           cpu.get('percent'),
                'open_file_descriptors': process.get('open_file_descriptors'),
            },
            'events': {
                'in':       events.get('in', 0),
                'filtered': events.get('filtered', 0),
                'out':      events.get('out', 0),
            },
            'pipeline': {
                'workers':    pipeline.get('workers'),
                'batch_size': pipeline.get('batch_size'),
            },
            'reloads': {
                'successes': reloads.get('successes', 0),
                'failures':  reloads.get('failures', 0),
            },
            'error': None,
        }
    except Exception as e:
        logger.warning(f"Logstash node stats not accessible at {base_url}: {e}")
        return {
            'accessible': False,
            'error': str(e)[:200],
        }


def check_in():
    """
    Send check-in to logstashui with current agent state
    
    Returns:
        dict: Response from logstashui or None if check-in fails
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
        
        # Get paths from state
        settings_path = state.get('settings_path', '')
        logs_path = state.get('logs_path', '')
        binary_path = state.get('binary_path', '')
        
        # Normalize path separators for cross-platform compatibility
        if settings_path:
            settings_path = settings_path.replace('\\', '/')
        if logs_path:
            logs_path = logs_path.replace('\\', '/')
        if binary_path:
            binary_path = binary_path.replace('\\', '/')
        
        # Check if paths exist and capture detailed error information
        import os
        from datetime import datetime
        problems = []
        
        def check_path(path, path_name):
            """Check if path exists and is accessible, return status and capture problems"""
            if not path:
                problems.append(f"{path_name} is not configured")
                return False
            
            if not os.path.exists(path):
                problems.append(f"{path_name} does not exist: {path}")
                return False
            
            # Check if we can read the path
            try:
                if os.path.isdir(path):
                    os.listdir(path)
                else:
                    with open(path, 'r') as f:
                        pass
            except PermissionError:
                problems.append(f"{path_name} exists but permission denied: {path}")
                return False
            except Exception as e:
                problems.append(f"{path_name} exists but error accessing: {path} ({str(e)})")
                return False
            
            return True
        
        def check_file_exists(directory, filename):
            """Check if a specific file exists in a directory"""
            if not directory or not os.path.exists(directory):
                return False
            file_path = os.path.join(directory, filename)
            return os.path.isfile(file_path)
        
        def check_executable_exists(directory, executable_name):
            """Check if an executable exists in a directory (with or without bin/ subdirectory)"""
            if not directory or not os.path.exists(directory):
                return False
            
            # Check in bin/ subdirectory first
            bin_path = os.path.join(directory, 'bin', executable_name)
            if os.path.isfile(bin_path):
                return True
            
            # Check directly in the directory
            direct_path = os.path.join(directory, executable_name)
            return os.path.isfile(direct_path)
        
        def get_log_file_info(logs_path, log_filename):
            """Get information about a log file including last modified time"""
            if not logs_path or not os.path.exists(logs_path):
                return None
            
            log_file_path = os.path.join(logs_path, log_filename)
            if not os.path.isfile(log_file_path):
                return None
            
            try:
                stat_info = os.stat(log_file_path)
                last_modified = datetime.fromtimestamp(stat_info.st_mtime)
                return {
                    'exists': True,
                    'last_modified': last_modified.isoformat(),
                    'size_bytes': stat_info.st_size
                }
            except Exception as e:
                problems.append(f"Error reading log file {log_filename}: {str(e)}")
                return None
        
        # Basic path validation
        settings_path_valid = check_path(settings_path, 'Settings path')
        logs_path_valid = check_path(logs_path, 'Logs path')
        binary_path_valid = check_path(binary_path, 'Binary path')
        
        # Check for specific config files in settings_path
        config_files = {
            'logstash_yml': check_file_exists(settings_path, 'logstash.yml'),
            'jvm_options': check_file_exists(settings_path, 'jvm.options'),
            'log4j2_properties': check_file_exists(settings_path, 'log4j2.properties'),
            'logstash_keystore': check_file_exists(settings_path, 'logstash.keystore')
        }
        
        # Add problems for missing config files
        if settings_path_valid:
            if not config_files['logstash_yml']:
                problems.append(f"logstash.yml not found in {settings_path}")
            if not config_files['jvm_options']:
                problems.append(f"jvm.options not found in {settings_path}")
            if not config_files['log4j2_properties']:
                problems.append(f"log4j2.properties not found in {settings_path}")
            if not config_files['logstash_keystore']:
                problems.append(f"logstash.keystore not found in {settings_path}")
        
        # Check for binaries in binary_path
        binaries = {
            'logstash': check_executable_exists(binary_path, 'logstash'),
            'logstash_keystore': check_executable_exists(binary_path, 'logstash-keystore')
        }
        
        # Add problems for missing binaries
        if binary_path_valid:
            if not binaries['logstash']:
                problems.append(f"logstash binary not found in {binary_path} or {binary_path}/bin")
            if not binaries['logstash_keystore']:
                problems.append(f"logstash-keystore binary not found in {binary_path} or {binary_path}/bin")
        
        # Check for log file
        log_info = get_log_file_info(logs_path, 'logstash-json.log')
        if logs_path_valid and not log_info:
            problems.append(f"logstash-json.log not found in {logs_path}")
        
        status_blob = {
            'settings_path_found': settings_path_valid,
            'logs_path_found': logs_path_valid,
            'binary_path_found': binary_path_valid,
            'config_files': config_files,
            'binaries': binaries,
            'log_file': log_info,
            'problems': '\n'.join(problems) if problems else None,
            'agent_version': state.get('agent_version', '0.0.0+unknown')
        }

        api_port = state.get('api_port', 9600)
        status_blob['logstash_api'] = get_logstash_api_status(api_port)
        status_blob['health_report'] = get_logstash_health_report(api_port)
        status_blob['node_stats'] = get_logstash_node_stats(api_port)
        status_blob['last_policy_apply'] = state.get('last_policy_apply')

        logger.debug(f"Path validation status: {status_blob}")
        
        # Prepare check-in data
        check_in_data = {
            'connection_id': connection_id,
            'revision_number': state.get('revision_number', 0),
            'status_blob': status_blob
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
                server_binary_path = result.get('binary_path')
                get_config_changes(server_settings_path, server_logs_path, server_binary_path)
            
            return result
        else:
            logger.warning(f"Check-in returned success=false: {result.get('message', 'Unknown error')}")
            return result
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to check in with logstashui: {e}")
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
    logger.info(f"logstashui URL: {state.get('logstash_ui_url')}")
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
