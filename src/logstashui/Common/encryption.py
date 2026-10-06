#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Fernet helpers for stored credentials and the Django ``SECRET_KEY``.

Keys resolve from env, then ``DATA_DIR``, then a newly generated file.
"""

import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
import secrets
import logging

logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    from LogstashUI.paths import resolve_data_dir
    return resolve_data_dir()


def get_encryption_key():
    """Return the Fernet key used to encrypt stored credentials.

    Resolution order:

    1. Environment variable ``CREDENTIAL_KEY``
    2. File ``DATA_DIR/.secret_key``
    3. Generate a new key and write that file (mode ``0o600``)

    Returns:
        The key as bytes.

    Raises:
        RuntimeError: If the key cannot be loaded or generated.
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
        
        # Check for key file in the configured data directory
        key_file = _data_dir() / '.secret_key'
        
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
    """Encrypt a credential string with the persisted Fernet key.

    Empty values are returned unchanged.

    Args:
        plaintext: Credential to encrypt.

    Returns:
        Base64-encoded ciphertext, or the original empty value.

    Raises:
        ValueError: If ``plaintext`` is not a string.
        RuntimeError: If key load or encryption fails.

    Examples:
        stored = encrypt_credential("s3cret")
        decrypt_credential(stored) == "s3cret"
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
    """Decrypt a credential previously produced by ``encrypt_credential``.

    Empty values are returned unchanged.

    Args:
        encrypted_text: Base64-encoded ciphertext.

    Returns:
        Plaintext credential, or the original empty value.

    Raises:
        ValueError: If the value is not a string, or the token/key is wrong.
        RuntimeError: If key load or decryption fails.
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


def get_django_secret_key():
    """Return a persisted Django ``SECRET_KEY`` for this data directory.

    Resolution order:

    1. Environment variable ``SECRET_KEY``
    2. File ``DATA_DIR/.django_secret_key``
    3. Generate 50 random characters and write that file (mode ``0o600``)

    Each deployment keeps a unique key across container restarts via the
    data-dir volume.

    Returns:
        Secret string (50 characters when generated here).

    Raises:
        RuntimeError: If the key cannot be loaded or generated.
    """
    try:
        # Check for environment variable first
        env_key = os.environ.get('SECRET_KEY')
        if env_key:
            if len(env_key) < 50:
                logger.warning(f"SECRET_KEY from environment is short ({len(env_key)} chars), recommended minimum is 50")
            return env_key
        
        # Check for key file in the configured data directory
        key_file = _data_dir() / '.django_secret_key'
        
        if key_file.exists():
            try:
                with open(key_file, 'r') as f:
                    key = f.read().strip()
                if not key:
                    logger.error(f"Django secret key file is empty: {key_file}")
                    raise RuntimeError("Django secret key file is empty")
                return key
            except PermissionError:
                logger.error(f"Permission denied reading Django secret key file: {key_file}")
                raise RuntimeError(f"Cannot read Django secret key: Permission denied")
            except Exception as e:
                logger.error(f"Error reading Django secret key from {key_file}: {e}")
                raise RuntimeError(f"Cannot read Django secret key: {e}")
        
        # Generate new key (same method Django uses)
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        key = ''.join(secrets.choice(chars) for _ in range(50))
        
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
            logger.error(f"Permission denied creating Django secret key file: {key_file}")
            raise RuntimeError(f"Cannot create Django secret key file: Permission denied")
        except Exception as e:
            logger.error(f"Error creating Django secret key file: {e}")
            raise RuntimeError(f"Cannot create Django secret key file: {e}")
        
        # Save key to file
        try:
            with open(key_file, 'w') as f:
                f.write(key)
            logger.info(f"Generated new Django secret key and saved to {key_file}")
        except PermissionError:
            logger.error(f"Permission denied writing to Django secret key file: {key_file}")
            raise RuntimeError(f"Cannot write Django secret key: Permission denied")
        except Exception as e:
            logger.error(f"Error writing Django secret key: {e}")
            raise RuntimeError(f"Cannot write Django secret key: {e}")
        
        return key
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_django_secret_key: {e}")
        raise RuntimeError(f"Failed to get Django secret key: {e}")
