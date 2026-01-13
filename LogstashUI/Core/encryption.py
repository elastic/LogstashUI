import os
from pathlib import Path
from cryptography.fernet import Fernet


def get_encryption_key():
    """
    Get or generate the encryption key for credential storage.
    
    Priority:
    1. Environment variable CREDENTIAL_KEY
    2. Key file in data/.secret_key
    3. Generate new key and save to data/.secret_key
    
    Returns:
        bytes: The encryption key
    """
    # Check for environment variable first
    env_key = os.environ.get('CREDENTIAL_KEY')
    if env_key:
        return env_key.encode()
    
    # Check for key file in data directory
    base_dir = Path(__file__).resolve().parent.parent
    key_file = base_dir / 'data' / '.secret_key'
    
    if key_file.exists():
        with open(key_file, 'rb') as f:
            return f.read()
    
    # Generate new key
    key = Fernet.generate_key()
    
    # Ensure data directory exists
    key_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Save key to file
    with open(key_file, 'wb') as f:
        f.write(key)
    
    return key


def encrypt_credential(plaintext):
    """
    Encrypt a credential string.
    
    Args:
        plaintext (str): The plaintext credential to encrypt
        
    Returns:
        str: Base64-encoded encrypted credential
    """
    if not plaintext:
        return plaintext
    
    key = get_encryption_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(plaintext.encode())
    return encrypted.decode()


def decrypt_credential(encrypted_text):
    """
    Decrypt a credential string.
    
    Args:
        encrypted_text (str): The encrypted credential
        
    Returns:
        str: Decrypted plaintext credential
    """
    if not encrypted_text:
        return encrypted_text
    
    key = get_encryption_key()
    fernet = Fernet(key)
    decrypted = fernet.decrypt(encrypted_text.encode())
    return decrypted.decode()
