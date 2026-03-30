#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Exceptions for Logstash keystore management."""

from typing import Optional


class LogstashKeystoreException(Exception):
    """Base exception for Logstash keystore operations.

    This exception serves as the root for all keystore-related errors,
    allowing for broad exception handling.
    """

    def __repr__(self):
        return f"{self.__class__.__name__}()"


class KeystoreBinaryException(LogstashKeystoreException):
    """Exception raised when the keystore binary is not found or fails.

    This exception is raised when operations require the logstash-keystore
    binary but it cannot be located or executed successfully.
    """

    def __repr__(self):
        return f"{self.__class__.__name__}()"


class LogstashKeystoreModified(LogstashKeystoreException):
    """Exception raised when keystore is modified externally.

    This exception is raised when the keystore timestamp indicates external
    modifications, and value mismatches are detected.
    """

    def __init__(self, modified_keys: list[str], discovered_timestamp: Optional[float]):
        """Initialize the exception.

        Args:
            modified_keys: List of keys that were modified externally.
            discovered_timestamp: The timestamp found on the keystore file, or None
                if not found.
        """
        self.modified_keys = modified_keys
        self.discovered_timestamp = discovered_timestamp
        super().__init__(
            f"Keystore modified externally. Modified keys: {modified_keys}, "
            f"timestamp: {discovered_timestamp}"
        )

    def __repr__(self):
        return (
            f"{self.__class__.__name__}("
            f"modified_keys={self.modified_keys!r}, "
            f"discovered_timestamp={self.discovered_timestamp!r})"
        )


class IncorrectPassword(LogstashKeystoreException):
    """Exception raised when keystore password is incorrect.

    This exception is raised when the keystore cannot be decrypted with the
    provided password, typically detected when keys exist but values cannot
    be read.
    """

    def __repr__(self):
        return f"{self.__class__.__name__}()"
