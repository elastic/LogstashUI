"""Subprocess utilities for Logstash keystore operations."""

import glob
import os
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, overload
from .decorators import path_exists, pathify
from .exceptions import KeystoreBinaryException, LogstashKeystoreException
from .settings import PATTERNS
from .utils import executable_file

logger = logging.getLogger(__name__)


@overload
def run_keystore_cli(
    keystore_bin: str,
    path_settings: str,
    args: List[str],
    password: Optional[str] = None,
    input_text: Optional[str] = None,
) -> str: ...
@overload
def run_keystore_cli(
    keystore_bin: Path,
    path_settings: Path,
    args: List[str],
    password: Optional[str] = None,
    input_text: Optional[str] = None,
) -> str: ...


@pathify("keystore_bin", "path_settings")
@path_exists("keystore_bin", kind="is_file")
@path_exists("path_settings", kind="is_dir")
def run_keystore_cli(
    keystore_bin: Path,
    path_settings: Path,
    args: List[str],
    password: Optional[str] = None,
    input_text: Optional[str] = None,
) -> str:
    """Run a logstash-keystore command.

    Args:
        keystore_bin: Path to the logstash-keystore binary.
        path_settings: Path to the Logstash config directory.
        args: Arguments to pass to the logstash-keystore command.
        password: Password for the keystore.
        input_text: Input text to send to stdin.

    Returns:
        The stdout output from the command.

    Raises:
        LogstashKeystoreException: If the command fails.
    """

    cmd = [str(keystore_bin), "--path.settings", str(path_settings)] + args
    env = os.environ.copy()
    if password:
        env["LOGSTASH_KEYSTORE_PASS"] = password
        logger.debug(
            "Populating LOGSTASH_KEYSTORE_PASS environment variable with "
            "provided password"
        )
    logger.info("Running logstash-keystore command: %s", " ".join(cmd))
    env_logstash = {k: v for k, v in env.items() if k.startswith("LOGSTASH")}
    logger.debug("Environment variables: %s", env_logstash)
    logger.debug("cmd: %s", cmd)
    result = subprocess.run(
        cmd, capture_output=True, text=True, input=input_text, env=env, check=False
    )
    logger.debug("Command return code: %d", result.returncode)
    logger.debug("Command stdout: %s", result.stdout)
    logger.debug("Command stderr: %s", result.stderr)
    if result.returncode != 0:
        logger.error(
            "logstash-keystore command failed: %s\n%s", " ".join(cmd), result.stderr
        )
        raise LogstashKeystoreException(
            f"Command failed: {' '.join(cmd)}\n{result.stderr}"
        )
    return result.stdout


@overload
def create_keystore(
    keystore_bin: str, path_settings: str, password: Optional[str] = None
) -> bool: ...
@overload
def create_keystore(
    keystore_bin: Path, path_settings: Path, password: Optional[str] = None
) -> bool: ...


@pathify("keystore_bin", "path_settings")
@path_exists("keystore_bin", kind="is_file")
@path_exists("path_settings", kind="is_dir")
def create_keystore(
    keystore_bin: Path, path_settings: Path, password: Optional[str] = None
) -> bool:
    """Create a new keystore.

    Args:
        keystore_bin: Path to the logstash-keystore binary.
        path_settings: Path to the Logstash config directory.
        password: Password for the keystore.

    Returns:
        True if successful.

    Raises:
        FileExistsError: If the keystore already exists.
    """
    logger.debug("keystore_bin: %s, path_settings: %s", keystore_bin, path_settings)
    keystore_path = path_settings / "logstash.keystore"
    path_settings.mkdir(parents=True, exist_ok=True)
    if keystore_path.exists():
        raise FileExistsError(f"Keystore already exists: {keystore_path}")
    run_keystore_cli(keystore_bin, path_settings, ["create"], password)
    return True


def find_keystore_binary() -> Path:
    """Find the logstash-keystore binary.

    Checks the values in PATTERNS in order (see settings.py).

    If not found, uses 'which' command.
    If still not found, raises KeystoreBinaryException.

    Returns:
        str: Path to the logstash-keystore binary.

    Raises:
        KeystoreBinaryException: If the binary is not found or not executable.

    Example:
        >>> find_keystore_binary()  # doctest: +SKIP
        '/usr/share/logstash/bin/logstash-keystore'
    """
    # Crawl known patterns to find a valid logstash-keystore binary
    for pattern in PATTERNS:
        paths = glob.glob(pattern)
        for path in paths:
            try:
                result = executable_file(path)
                if result:
                    logger.debug(f"Found executable logstash-keystore at {path}")
                    return Path(path)  # path is valid and executable
            except FileNotFoundError:
                continue

    # Try using which as a last-ditch attempt to find logstash-keystore in PATH
    try:
        result = subprocess.run(
            ["which", "logstash-keystore"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            candidate = result.stdout.strip()
            logger.debug(f"Found logstash-keystore via which: {candidate}")
            result = executable_file(candidate)
            if result:
                return Path(candidate)
    except (OSError, subprocess.SubprocessError):
        logger.error("Error occurred while trying to find logstash-keystore with which")

    raise KeystoreBinaryException(
        "logstash-keystore binary not found, or not executable. "
        "Please install Logstash or specify the path."
    )
