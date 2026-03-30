#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Utilities for Logstash keystore management.
"""

import base64
import logging
import os
import random
import shutil
from pathlib import Path
from typing import Optional, Union, overload
from .decorators import path_exists, pathify
from .exceptions import LogstashKeystoreException
from .settings import CANDIDATES, ALTERNATE_LS_PATHS

logger = logging.getLogger(__name__)


def ascii_bytes_to_chars(bytes_data: bytes) -> str:
    """Converts bytes from ascii encoded text to a string.

    Args:
        bytes_data (bytes): The bytes data to convert.

    Returns:
        str: The string representation.

    Example:
        >>> ascii_bytes_to_chars(b'hello')
        'hello'
    """
    return "".join(chr(b) for b in bytes_data)


def ascii_chars_to_bytes(chars: str) -> bytes:
    """Converts characters from ascii encoded text to bytes.

    Args:
        chars (str): The string to convert.

    Returns:
        bytes: The bytes representation.

    Example:
        >>> ascii_chars_to_bytes('hello')
        b'hello'
    """
    return bytes(ord(c) for c in chars)


def clear_bytes(data: bytearray) -> None:
    """Clears the byte array by setting all to 0.

    Args:
        data (bytearray): The bytearray to clear.

    Example:
        >>> data = bytearray(b'hello')
        >>> clear_bytes(data)
        >>> data
        bytearray(b'\\x00\\x00\\x00\\x00\\x00')
    """
    for i, _ in enumerate(data):
        data[i] = 0


def base64_encode(data: bytes) -> bytes:
    """Base64 encode the given bytes, then clear the original.

    Args:
        data (bytes): The bytes to encode.

    Returns:
        bytes: The base64 encoded bytes.

    Example:
        >>> base64_encode(b'hello')
        b'aGVsbG8='
    """
    encoded = base64.b64encode(data)
    clear_bytes(bytearray(data))
    return encoded


def deobfuscate(obfuscated: str) -> str:
    """De-obfuscates a string

    This is only called when the password is needed in plain text form, such as when
    calling the keystore binary, and the password is longer than
    settings.PASSWORD_OBFUSCATED_LENGTH), because Logstash assumes a password longer
    than that must be obfuscated.

    Args:
        obfuscated (str): The obfuscated string.

    Returns:
        str: The de-obfuscated string.

    Raises:
        ValueError: If the obfuscated data length is invalid.

    Example:
        >>> deobfuscate(obfuscate("abc123xyz"))
        'abc123xyz'
    """
    bytes_data = ascii_chars_to_bytes(obfuscated)
    if len(bytes_data) % 2 != 0:
        raise ValueError("Invalid obfuscated data length")
    length = len(bytes_data)
    half = length // 2
    xor_part = bytes_data[:half]
    random_part = bytes_data[half:]
    deobfuscated = bytearray(half)
    for i in range(half):
        deobfuscated[i] = xor_part[i] ^ random_part[i]
    return ascii_bytes_to_chars(deobfuscated)


# Not currently used outside of testing
def obfuscate(value: str) -> str:
    """Obfuscates a Logstash Keystore main password string.

    Args:
        value (str): The plain string.

    Returns:
        str: The obfuscated string.

    Example:
        >>> obfuscate("abc123xyz")  # doctest: +SKIP
        '...'
    """
    bytes_data = ascii_chars_to_bytes(value)
    length = len(bytes_data)
    random_bytes = bytearray(length)
    for i in range(length):
        random_bytes[i] = random.randint(0, 255)
    obfuscated = bytearray(length * 2)
    for i in range(length):
        obfuscated[i] = bytes_data[i] ^ random_bytes[i]
    obfuscated[length:] = random_bytes
    result = ascii_bytes_to_chars(obfuscated)
    clear_bytes(obfuscated)
    return result


def executable_file(binary_path: str) -> bool:
    """Verify that the logstash-keystore binary is executable.

    This uses these decorators because the calling function is going from a list
    of possible paths which are all strings.

    Args:
        binary_path (str): Path to the binary.

    Returns:
        bool: True if the binary is executable, False otherwise.

    Raises:
        FileNotFoundError if the @path_exists docorator determines that the file
            does not exist or is not a file.

    Example:
        >>> executable_file('/usr/bin/ls')
        True
    """
    result = os.access(binary_path, os.X_OK)
    if not result:
        logger.debug("%s is not executable", binary_path)
    return result


def find_path_settings(binary_path: Optional[Path] = None) -> Path:
    """Find or validate the path.settings directory.

    If path_settings is provided, validates it exists, is a directory, and is writable.
    If not provided, attempts to find a suitable directory:
    - /etc/logstash
    - /usr/share/logstash/config
    - Whatever is added to settings.ALTERNATE_LS_PATHS that matches binary_path
      - Homebrew's /opt/homebrew/etc/logstash

    Args:
        binary_path (Optional[Path]): Path to the keystore binary detection.

    Returns:
        str: The path to the config directory.

    Raises:
        LogstashKeystoreException: If no valid path is found.

    Example:
        >>> find_path_settings()  # doctest: +SKIP
        '/etc/logstash'
    """
    candidates = CANDIDATES.copy()
    name = binary_path.name if binary_path else ""
    for alt_path, alt_cfg in ALTERNATE_LS_PATHS.items():
        if binary_path and alt_path in name:
            candidates.append(alt_cfg)

    for path in candidates:
        p = Path(path)
        if p.exists() and p.is_dir() and os.access(p, os.W_OK):
            logger.debug(f"Using --path.settings {path}")
            return p

    raise LogstashKeystoreException(
        "No valid path.settings directory found. Please specify --path.settings."
    )


# The overload decorator is here to provide type hints allowing for both str and
# Path inputs, while the pathify decorator handles the conversion and validation
@overload
def file_exists(filename: str) -> bool: ...
@overload
def file_exists(filename: Path) -> bool: ...


# The file_exists function is used where the path_exists decorator cannot be used
# directly, such as in backup_keystore where we want to check if the backup file
# was created successfully after copying, and we don't want to raise an exception
# if it doesn't exist beforehand.
@pathify("filename")
@path_exists("filename", kind="is_file")
def file_exists(filename: Path) -> bool:
    """Check if a named file exists and is a file.

    Args:
        filename: The file path to check.
    Returns:
        bool: True if the file exists, False otherwise.
    Raises:
        FileNotFoundError: If the file does not exist or is not a file (raised
            by the path_exists decorator).
    """
    return filename.exists()


# The overload decorator is here to provide type hints allowing for both str and
# Path inputs, while the pathify decorator handles the conversion and validation
@overload
def backup_keystore(source: str, dest: str) -> bool: ...
@overload
def backup_keystore(source: Path, dest: Path) -> bool: ...


@pathify("source", "dest")  # Ensure both paths are Path objects
@path_exists("source", kind="is_file")  # Ensure keystore exists and is a file
def backup_keystore(source: Path, dest: Path) -> bool:
    """Backup the keystore file to a specified path.

    Args:
        source: Path to the source keystore file.
        dest: Path to the backup file.

    Returns:
        True if successful, False if keystore does not exist.

    Example:
        >>> backup_keystore(
        ... '/path/to/keystore', '/path/to/backup')  # doctest: +SKIP
        True
    """
    # Ensure the destination directory exists before copying
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    try:
        file_exists(dest)
    except FileNotFoundError as e:
        logger.error("Failed to create backup file: %s, Exception: %s", dest, e)
        raise e
    logger.info("Backed up keystore from %s to %s", source, dest)
    return True


# The overload decorator is here to provide type hints allowing for both str and
# Path inputs, while the pathify decorator handles the conversion and validation
@overload
def read_file_bytes(filepath: str) -> bytes: ...
@overload
def read_file_bytes(filepath: Path) -> bytes: ...


@pathify("filename")
@path_exists("filename", kind="is_file")
def read_file_bytes(filename: Path) -> bytes:
    """Read file contents as bytes.

    Args:
        filename: Pathlib.Path object representing the file.

    Returns:
        The bytes content of the file.

    Raises:
        FileNotFoundError: If the file does not exist.

    Example:
        >>> read_file_bytes(Path('/path/to/file'))  # doctest: +SKIP
        b'...'
    """
    with open(filename, "rb") as f:
        _ = f.read()
    return _


def now_path(filename: Union[str, Path, None]) -> Optional[Path]:
    """Ensure filename is a Path object.

    Args:
        filename: The file path to ensure is a Path object.

    Returns:
        The original filename Path object.

    Example:
        >>> now_path(Path('/tmp/some/dir/file.txt'))  # doctest: +SKIP
        PosixPath('/tmp/some/dir/file.txt')
    """
    if isinstance(filename, str):
        return Path(filename)
    return filename
