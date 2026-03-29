#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
import secrets
import logging

logger = logging.getLogger(__name__)

def get_encryption_key():
    """
    Get or generate the encryption key for credential storage.
    
    Priority:
    1. Environment variable CREDENTIAL_KEY
    2. Key file in data/.secret_key
    3. Generate new key and save to data/.secret_key
    
    Returns:
        bytes: The encryption key
        
    Raises:
        RuntimeError: If key cannot be loaded or generated
    """
    try:
        # Check for environment variable first
        env_key = os.environ.get('CREDENTIAL_KEY')
        if env_key:
            # Validate the key format
            try:
                Fernet(env_key.encode())
                return env_key.encode()
            except Exception as e:
                logger.error(f"Invalid CREDENTIAL_KEY in environment: {e}")
                raise RuntimeError(f"Invalid CREDENTIAL_KEY format: {e}")
        
        # Check for key file in package-local data directory
        base_dir = Path(__file__).resolve().parent
        key_file = base_dir / 'data' / '.secret_key'
        
        if key_file.exists():
            try:
                with open(key_file, 'rb') as f:
                    key = f.read()
                # Validate the key
                Fernet(key)
                return key
            except PermissionError:
                logger.error(f"Permission denied reading encryption key file: {key_file}")
                raise RuntimeError(f"Cannot read encryption key file: Permission denied")
            except Exception as e:
                logger.error(f"Error reading or validating encryption key from {key_file}: {e}")
                raise RuntimeError(f"Invalid encryption key in file: {e}")
        
        # Generate new key
        key = Fernet.generate_key()
        
        # Ensure data directory exists
        try:
            key_file.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.error(f"Permission denied creating directory: {key_file.parent}")
            raise RuntimeError(f"Cannot create data directory: Permission denied")
        except Exception as e:
            logger.error(f"Error creating data directory: {e}")
            raise RuntimeError(f"Cannot create data directory: {e}")

        # Set file permissions before writing
        try:
            key_file.touch(mode=0o600, exist_ok=True)
        except PermissionError:
            logger.error(f"Permission denied creating key file: {key_file}")
            raise RuntimeError(f"Cannot create encryption key file: Permission denied")
        except Exception as e:
            logger.error(f"Error creating key file: {e}")
            raise RuntimeError(f"Cannot create encryption key file: {e}")

        # Save key to file
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
            logger.info(f"Generated new encryption key and saved to {key_file}")
        except PermissionError:
            logger.error(f"Permission denied writing to key file: {key_file}")
            raise RuntimeError(f"Cannot write encryption key: Permission denied")
        except Exception as e:
            logger.error(f"Error writing encryption key: {e}")
            raise RuntimeError(f"Cannot write encryption key: {e}")
        
        return key
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_encryption_key: {e}")
        raise RuntimeError(f"Failed to get encryption key: {e}")


def encrypt_credential(plaintext):
    """
    Encrypt a credential string.
    
    Args:
        plaintext (str): The plaintext credential to encrypt
        
    Returns:
        str: Base64-encoded encrypted credential, or None if encryption fails
        
    Raises:
        ValueError: If plaintext is not a string
        RuntimeError: If encryption fails
    """
    if not plaintext:
        return plaintext
    
    if not isinstance(plaintext, str):
        raise ValueError(f"plaintext must be a string, got {type(plaintext).__name__}")
    
    try:
        key = get_encryption_key()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(plaintext.encode())
        return encrypted.decode()
    except RuntimeError:
        # Re-raise key loading errors
        raise
    except Exception as e:
        logger.error(f"Error encrypting credential: {e}")
        raise RuntimeError(f"Encryption failed: {e}")


def decrypt_credential(encrypted_text):
    """
    Decrypt a credential string.
    
    Args:
        encrypted_text (str): The encrypted credential
        
    Returns:
        str: Decrypted plaintext credential, or None if decryption fails
        
    Raises:
        ValueError: If encrypted_text is not a string or is invalid
        RuntimeError: If decryption fails
    """
    if not encrypted_text:
        return encrypted_text
    
    if not isinstance(encrypted_text, str):
        raise ValueError(f"encrypted_text must be a string, got {type(encrypted_text).__name__}")
    
    try:
        key = get_encryption_key()
        fernet = Fernet(key)
        decrypted = fernet.decrypt(encrypted_text.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.error("Failed to decrypt credential: Invalid token or wrong encryption key")
        raise ValueError("Cannot decrypt credential: Invalid token or wrong encryption key")
    except RuntimeError:
        # Re-raise key loading errors
        raise
    except Exception as e:
        logger.error(f"Error decrypting credential: {e}")
        raise RuntimeError(f"Decryption failed: {e}")
