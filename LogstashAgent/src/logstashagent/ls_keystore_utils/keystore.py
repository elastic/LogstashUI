"""Logstash Keystore management using logstash-keystore binary and PyJKS."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Union, overload
from .decorators import pathify
from .utils import deobfuscate, find_path_settings, backup_keystore, now_path
from .crypto import ObfuscatedValue, read_keystore, KeyEntry, generate_salt_iv
from .crypto import valid_keystore as valid_ks
from .subprocess_utils import run_keystore_cli, create_keystore, find_keystore_binary
from .exceptions import (
    IncorrectPassword,
    LogstashKeystoreException,
    LogstashKeystoreModified,
)
from .settings import PASSWORD_OBFUSCATED_LENGTH

# pylint: disable=R0902,R0913,R0917

logger = logging.getLogger(__name__)


class LogstashKeystore:
    """Logstash keystore management class.

    This class provides methods to create, load, and manipulate Logstash keystores
    using both the logstash-keystore binary for write operations and cryptographic
    parsing for read operations.
    """

    def __init__(
        self,
        path_settings: Optional[Union[str, Path]] = None,
        password: Optional[str] = None,
        exepath: Optional[Union[str, Path]] = None,
        salt_iv: Optional[bytes] = None,
        obvpassword: Optional[ObfuscatedValue] = None,
    ):
        """Initialize the LogstashKeystore instance.

        Args:
            path_settings: Path to the Logstash config directory. If not provided,
                attempts to find a suitable directory.
            password: Password for the keystore.
            exepath: Path to the binary.
            salt_iv: Optional 32-byte salt/IV for obfuscation. If not provided,
                one will be generated. Must be provided if using obvpassword.
            obvpassword: Optional ObfuscatedValue for the password. If provided, this
                will be used directly instead of the plain password. Requires that
                salt_iv is also provided to reveal the password when needed.

        Raises:
            ValueError: If obvpassword is provided without salt_iv.

        Example:
            >>> ks = LogstashKeystore('/tmp/config')  # doctest: +SKIP
        """
        self.exepath = now_path(exepath) or find_keystore_binary()
        logger.debug(f"Using keystore binary at: {self.exepath}")
        self.path_settings = now_path(path_settings) or find_path_settings(self.exepath)
        self.keystore = self.path_settings / "logstash.keystore"
        logger.debug("Keystore path set to: %s", self.keystore)
        self.salt_iv = salt_iv or generate_salt_iv()
        # We allow both plain and obfuscated passwords to be passed in. If an
        # obfuscated password is provided, use it directly. Otherwise, create an
        # ObfuscatedValue from the plain password.
        if obvpassword and salt_iv:
            self.password = obvpassword
        elif obvpassword and not salt_iv:
            raise ValueError("salt_iv must be provided when using obvpassword")
        elif password:
            self.password = ObfuscatedValue(password, self.salt_iv)

        self.needs_restart = False  # Flag to indicate if Logstash needs restart
        self._current: dict[str, KeyEntry] = {}
        self._last_timestamp: Optional[float] = None

    def __repr__(self) -> str:
        """Return a string representation of the LogstashKeystore instance.

        Returns:
            A string representation of the instance.

        Example:
            >>> ks = LogstashKeystore('/tmp/config')  # doctest: +SKIP
            >>> repr(ks)  # doctest: +SKIP
            "LogstashKeystore(path_settings='/tmp/config', keystore=...)"
        """
        return (
            f"LogstashKeystore(path_settings={self.path_settings!r}, "
            f"keystore={self.keystore!r})"
        )

    @classmethod
    def create(
        cls,
        path_settings: Optional[Union[str, Path]],
        password=None,
        exepath=None,
        salt_iv: Optional[bytes] = None,
        obvpassword: Optional[ObfuscatedValue] = None,
    ):
        """Create a new keystore.

        Args:
            path_settings (Optional[Path]): Path to the Logstash config directory.
            password (Optional[str]): Password for the keystore.
            exepath (Optional[str]): Path to the binary.
            salt_iv (Optional[bytes]): Optional 32-byte salt/IV for obfuscation.
                If not provided, one will be generated. Must be provided if using
                obvpassword.
            obvpassword (Optional[ObfuscatedValue]): Optional ObfuscatedValue for
                the password. If provided, this will be used directly instead of
                the plain password. Requires that salt_iv is also provided to
                reveal the password when needed.

        Returns:
            LogstashKeystore: The created keystore instance.
        """
        ks = cls(
            path_settings,
            password=password,
            exepath=exepath,
            salt_iv=salt_iv,
            obvpassword=obvpassword,
        )
        create_keystore(ks.exepath, ks.path_settings, ks.password.reveal(ks.salt_iv))
        ks.needs_restart = False  # New keystore, no restart needed yet
        ks._initialize_cache()
        return ks

    @classmethod
    def load(
        cls,
        path_settings: Optional[Union[str, Path]],
        password=None,
        exepath=None,
        salt_iv: Optional[bytes] = None,
        obvpassword: Optional[ObfuscatedValue] = None,
    ):
        """Load an existing keystore.

        Args:
            path_settings (Optional[Union[str, Path]]): Path to the Logstash config
                directory, i.e. the value of --path.settings
            password (Optional[str]): Password for the keystore.
            exepath (Optional[str]): Path to the binary.
            salt_iv (Optional[bytes]): Optional 32-byte salt/IV for obfuscation.
                If not provided, one will be generated. Must be provided if using
                obvpassword.
            obvpassword (Optional[ObfuscatedValue]): Optional ObfuscatedValue for
                the password. If provided, this will be used directly instead of
                the plain password. Requires that salt_iv is also provided to
                reveal the password when needed.

        Returns:
            LogstashKeystore: The loaded keystore instance.

        Raises:
            LogstashKeystoreException: If the keystore file is invalid.
        """
        ks = cls(
            path_settings,
            password=password,
            exepath=exepath,
            salt_iv=salt_iv,
            obvpassword=obvpassword,
        )
        # Check if valid before initializing cache
        if not valid_ks(ks.keystore):
            raise LogstashKeystoreException(f"Invalid keystore file: {ks.keystore}")
        ks._initialize_cache()
        return ks

    def _add_batch_keys(self, keys_dict: Dict[str, str]) -> None:
        """Add multiple key-value pairs to the keystore.

        Args:
            keys_dict: Dictionary of key-value pairs.

        Raises:
            ValueError: If keys_dict is empty.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks._add_batch_keys({'key': 'value'})  # doctest: +SKIP
        """
        logger.debug("Adding batch keys: %s", list(keys_dict.keys()))
        if not keys_dict:
            raise ValueError("Cannot add empty dict of keys")
        key_names = [k.upper() for k in keys_dict.keys()]
        input_text = "\n".join(
            "y\n" + v if k.upper() in self.keys else v for k, v in keys_dict.items()
        )
        run_keystore_cli(
            self.exepath,
            self.path_settings,
            ["add"] + key_names + ["--stdin"],
            self.password.reveal(self.salt_iv),
            input_text=input_text,
        )

    def _add_single_key(self, key: str, value: str) -> None:
        """Add a single key-value pair to the keystore.

        Args:
            key: The key name.
            value: The value.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks._add_single_key('key', 'value')  # doctest: +SKIP
        """
        logger.debug("Adding single key: %s", key)
        input_text = "y\n" + value if key.upper() in self.keys else value
        run_keystore_cli(
            self.exepath,
            self.path_settings,
            ["add", key.upper(), "--stdin"],
            self.password.reveal(self.salt_iv),
            input_text=input_text,
        )

    def _check_timestamp(self):
        """
        Check if keystore key timestamps have changed and detect key/value
        modifications.

        Args:
            None

        Returns:
            None

        Raises:
            LogstashKeystoreModified: If the keystore has been modified externally.
        """
        fresh_data = self.read_all()  # Get fresh data for timestamp
        current_keys = set(self._current.keys())
        fresh_keys = set(fresh_data.keys())
        all_keys = current_keys | fresh_keys
        fresh_timestamp = None
        if fresh_data:
            fresh_timestamp = max(entry.timestamp for entry in fresh_data.values())

        logger.debug(
            "Last timestamp: %s, Keystore latest timestamp: %s",
            self._last_timestamp,
            fresh_timestamp,
        )

        ### Checks ###
        # Check for timestamp modification
        # Implies added or modified keys but not necessarily removed keys.
        if self._last_timestamp is not None and fresh_timestamp != self._last_timestamp:
            logger.warning(
                "Keystore modified externally: newest timestamp changed from %s to %s",
                self._last_timestamp,
                fresh_timestamp,
            )

            # Check for value changes across keys
            added = []
            removed = []
            modified = []
            for k in all_keys:
                if not k in self._current:
                    logger.warning(f"Key {k} was added out-of-band")
                    added.append(k)
                    continue
                if not k in fresh_data:
                    logger.error(f"Key {k} was removed out-of-band")
                    removed.append(k)
                    continue
                # We've appended changes to added or removed and skipped value
                # comparison for added/removed keys. If we're here, we check for
                # value changes.
                if self._current[k].obfuscated_value != fresh_data[k].obfuscated_value:
                    logger.error(f"Value for key {k} was modified out-of-band")
                    modified.append(k)

            if added:
                logger.warning("Keystore keys added out-of-band: %s", sorted(added))
            if removed:
                logger.error("Keystore keys removed out-of-band: %s", sorted(removed))
            if modified:
                logger.error(
                    "Keystore values modified out-of-band for key(s): %s", modified
                )
            if removed or modified:
                raise LogstashKeystoreModified(modified + removed, self.timestamp)

        # Otherwise, timestamps are the same. We need to check if keys were removed
        else:
            removed_keys = current_keys - fresh_keys
            # If keys have been removed, we need to raise an exception because
            # this is a destructive change that we can't detect with timestamps
            # alone. We can detect added keys with timestamps, but not removed keys,
            # so we have to check for them separately.
            if removed_keys:
                logger.error(
                    "Keystore keys removed out-of-band: %s", sorted(removed_keys)
                )
                raise LogstashKeystoreModified(list(removed_keys), self.timestamp)

        # If we haven't raised an exception, update cache with fresh_data
        self._current = fresh_data
        # Update last timestamp to the new value after processing changes
        self._last_timestamp = self.timestamp

    def _get_plain_password(self) -> str:
        """Get the plain (deobfuscated) password for keystore operations.

        Retrieves the password from instance or environment, and deobfuscates
        if necessary using a heuristic based on length.

        Note:
            The heuristic assumes passwords longer than PASSWORD_OBFUSCATED_LENGTH are
            obfuscated, following Logstash's internal behavior.

        Returns:
            The plain password.

        Raises:
            ValueError: If no password is provided.

        Example:
            >>> ks = LogstashKeystore(password='secret')  # doctest: +SKIP
            >>> ks._get_plain_password()  # doctest: +SKIP
            'secret'
        """
        if not self.password:
            raise ValueError("Password required to read keystore")
        # Heuristic: if password length > PASSWORD_OBFUSCATED_LENGTH,
        # assume it's obfuscated
        passval = self.password.reveal(self.salt_iv)
        return (
            deobfuscate(passval)
            if len(passval) > PASSWORD_OBFUSCATED_LENGTH
            else passval
        )

    def _initialize_cache(self):
        """Initialize the obfuscated cache and timestamp.

        This method reads all keys from the keystore and stores them in the
        _current cache along with their timestamps. It also sets the _last_timestamp
        to the current timestamp.

        Returns:
            None

        Raises:
            LogstashKeystoreException: If the keystore file is invalid.
        """
        logger.debug("Initializing keystore cache")
        if not valid_ks(self.keystore):
            logger.error(f"Keystore missing or invalid: {self.keystore}")
            raise LogstashKeystoreException(f"Invalid keystore file: {self.keystore}")
        self._current = self.read_all()
        self._last_timestamp = self.timestamp

    def _post_operation_update(self) -> None:
        """Update cache, timestamp, and flags after add/remove operations.

        This method should be called after any operation that modifies the keystore to
        ensure the internal state is consistent with the actual keystore file.

        Returns:
            None

        Raises:
            LogstashKeystoreException: If the keystore file is invalid after the
                operation.
        """
        # Re-read the keystore to get correct timestamps after operations
        self._current = self.read_all()
        self._last_timestamp = self.timestamp
        self.needs_restart = True

    def _remove_batch_keys(self, key_names: List[str]) -> None:
        """Remove multiple keys from the keystore.

        Args:
            key_names: List of key names to remove.

        Raises:
            ValueError: If key_names is empty.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks._remove_batch_keys(['key1', 'key2'])  # doctest: +SKIP
        """
        logger.debug("Removing batch keys: %s", key_names)
        if not key_names:
            raise ValueError("Cannot remove empty list of keys")
        upper_keys = [k.upper() for k in key_names]
        run_keystore_cli(
            self.exepath,
            self.path_settings,
            ["remove"] + upper_keys,
            self.password.reveal(self.salt_iv),
        )

    def _verify_keys(self, keys_dict: Dict[str, str]) -> None:
        """Verify that keys were added correctly.

        Args:
            keys_dict: Dictionary of expected key-value pairs.

        Raises:
            ValueError: If verification fails.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks._verify_keys({'key': 'value'})  # doctest: +SKIP
        """
        logger.debug("Verifying keys: %s", list(keys_dict.keys()))
        for k, v in keys_dict.items():
            if k.upper() not in self.keys:
                raise ValueError(f"Key {k} was not added to keystore")
            retrieved = self.get_key(k.upper())
            if retrieved != v:
                raise ValueError(
                    f"Key {k} value mismatch: expected {v}, got {retrieved}"
                )

    def _verify_removed_keys(self, key_names: List[str]) -> None:
        """Verify that keys were removed correctly.

        Args:
            key_names: List of key names that should be removed.

        Raises:
            ValueError: If verification fails.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks._verify_removed_keys(['key1'])  # doctest: +SKIP
        """
        logger.debug("Verifying removed keys: %s", key_names)
        for k in key_names:
            if k.upper() in self.keys:
                raise ValueError(f"Key {k} was not removed from keystore")

    def add_key(
        self, key: Union[str, Dict[str, str]], value: Optional[str] = None
    ) -> bool:
        """Add or update one or more keys in the keystore.

        Wrapper on create_key method to add a single key or batch of keys.
        Included because the logstash-keystore binary uses `add` to add keys.

        Args:
            key: Either a single key name (str) or a dict of key-value pairs.
            value: The value for the key if key is str; ignored if key is dict.

        Returns:
            True if successful.

        Raises:
            ValueError: If verification fails or invalid arguments.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks.add_key('my_key', 'my_value')  # doctest: +SKIP
            True
        """
        return self.create_key(key, value)

    @overload
    def backup(self, backup_path: str) -> bool: ...
    @overload
    def backup(self, backup_path: Path) -> bool: ...

    @pathify("backup_path")
    def backup(self, backup_path: Path) -> bool:
        """Backup the keystore to a file.

        Args:
            backup_path: Path to the backup file.

        Returns:
            True if successful, False if keystore does not exist.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks.backup('/tmp/backup')  # doctest: +SKIP
            True
        """
        return backup_keystore(self.keystore, backup_path)

    def create_key(
        self, key: Union[str, Dict[str, str]], value: Optional[str] = None
    ) -> bool:
        """Add or update one or more keys in the keystore.

        After adding, verifies that all keys are present and values match.

        Args:
            key (Union[str, Dict[str, str]]): Either a single key name (str) or a
                dict of key-value pairs.
            value (Optional[str]): The value for the key if key is str; ignored
                if key is dict.

        Returns:
            bool: True if successful.

        Raises:
            ValueError: If verification fails or invalid arguments.

        Note:
            This method sets needs_restart to True after successful addition.

        Example:
            >>> ks = LogstashKeystore.create(
            ...     '/tmp/keystore', 'password')  # doctest: +SKIP
            >>> ks.add_key('my_key', 'my_value')  # doctest: +SKIP
            True
            >>> ks.get_key('my_key')  # doctest: +SKIP
            'my_value'
        """
        self._check_timestamp()
        logger.debug(
            "Adding key(s): %s", list(key.keys()) if isinstance(key, dict) else key
        )
        if isinstance(key, dict):
            self._add_batch_keys(key)
            self._post_operation_update()
            self._verify_keys(key)
        else:
            if value is None:
                raise ValueError("value must be provided for single key add")
            self._add_single_key(key, value)
            self._post_operation_update()
            self._verify_keys({key: value})
        logger.info("Successfully added key(s) to keystore")
        return True

    def delete_key(self, key: Union[str, List[str]]) -> bool:
        """Remove one or more keys from the keystore.

        Args:
            key: Either a single key name (str) or a list of key names (List[str]).

        Returns:
            True if successful.

        Raises:
            ValueError: If batch removal fails or keys not found.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks.remove_key('key')  # doctest: +SKIP
            True
            >>> ks.remove_key(['key1', 'key2'])  # doctest: +SKIP
            True
        """
        self._check_timestamp()
        if isinstance(key, list):
            logger.debug("Removing batch keys: %s", key)
            self._remove_batch_keys(key)
            keys_to_remove = key
        else:
            logger.debug("Removing single key: %s", key)
            run_keystore_cli(
                self.exepath,
                self.path_settings,
                ["remove", key.upper()],
                self.password.reveal(self.salt_iv),
            )
            keys_to_remove = [key]

        self._post_operation_update()
        self._verify_removed_keys(keys_to_remove)
        logger.info("Successfully removed key(s) from keystore")
        return True

    def delete_keystore(self) -> bool:
        """Delete the keystore file.

        Returns:
            True if deleted, False if not found.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks.delete_keystore()  # doctest: +SKIP
            True
        """
        if self.keystore.exists():
            self.keystore.unlink()
            self.needs_restart = True
            logger.info("Deleted keystore file")
            return True
        return False

    def get_key(self, key_name: str) -> Optional[str]:
        """Get the value of a key from the keystore.

        Wrapper on read_key method to get a single key value.

        Args:
            key_name: The name of the key to retrieve.

        Returns:
            The key value if found, None otherwise.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> value = ks.get_key('key')  # doctest: +SKIP
        """
        return self.read_key(key_name)

    def key_exists(self, key_name: str) -> bool:
        """Check if a key exists in the keystore.

        This method uses the cached data after checking for external modifications.

        Args:
            key_name: The name of the key to check.

        Returns:
            True if the key exists, False otherwise.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks.key_exists('key')  # doctest: +SKIP
            True
        """
        self._check_timestamp()
        exists = key_name.upper() in self._current
        logger.debug("Key %s exists: %s", key_name, exists)
        return exists

    @property
    def keys(self) -> List[str]:
        """List all keys in the keystore.

        This method uses the cached data after checking for external modifications.

        Returns:
            A list of key names (uppercased).

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> keys = ks.keys  # doctest: +SKIP
        """
        self._check_timestamp()
        logger.debug("Listing keys: %d keys", len(self._current))
        return list(self._current.keys())

    def read_all(self) -> Dict[str, KeyEntry]:
        """
        Get all keys from the keystore along with their obfuscated values and
        timestamps.

        Returns:
            A dictionary of key-value pairs where the key is the key name and
            the value is a KeyEntry containing the obfuscated value and timestamp.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> all_pairs = ks.read_all()  # doctest: +SKIP
        """
        try:
            result = read_keystore(self.keystore, self._get_plain_password())
        except IncorrectPassword as e:
            raise e
        # This is a catch-all for an almost impossible to mock edge case. As such,
        # there are no working tests for this right now.
        #
        # It catches any other exceptions that may occur during reading, such as
        # spontaneous file corruption or unexpected format issues. We want to log
        # the error and raise a generic exception to avoid exposing internal details.
        except Exception as exc:
            logger.error("Error reading keystore: %s", exc)
            raise LogstashKeystoreException("Failed to read keystore") from exc
        return {
            key: KeyEntry(ObfuscatedValue(value, self.salt_iv), timestamp)
            for key, (value, timestamp) in result.items()
        }

    def read_key(self, key_name: str) -> Optional[str]:
        """Get the value of a key from the keystore.

        This method uses the cached data after checking for external modifications.

        Args:
            key_name: The name of the key to retrieve.

        Returns:
            The key value if found, None otherwise.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> value = ks.get_key('key')  # doctest: +SKIP
        """
        self._check_timestamp()
        logger.debug("Getting key: %s", key_name)
        entry = self._current.get(key_name.upper())
        return entry.obfuscated_value.reveal(self.salt_iv) if entry else None

    def remove_key(self, key: Union[str, List[str]]) -> bool:
        """Remove one or more keys from the keystore.

        Wrapper for delete_key to match naming convention.
        Included because the logstash-keystore binary uses `remove` to delete keys.

        Args:
            key: Either a single key name (str) or a list of key names (List[str]).

        Returns:
            True if successful.

        Raises:
            ValueError: If batch removal fails or keys not found.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks.remove_key('key')  # doctest: +SKIP
            True
        """
        return self.delete_key(key)

    @property
    def timestamp(self) -> Optional[float]:
        """Get the latest modified timestamp within the keystore file.

        Returns:
            Optional[float]: The latest timestamp of all key within the keystore
                 in seconds since epoch, or None if self._current is empty.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ts = ks.timestamp  # doctest: +SKIP
        """
        if self._current:
            return max(entry.timestamp for entry in self._current.values())
        return None

    def update_key(
        self, key: Union[str, Dict[str, str]], value: Optional[str] = None
    ) -> bool:
        """Update the value of one or more existing keys in the keystore.

        Wrapper on create_key for updating keys. Update is just an overwrite.
        Calling create_key again to an existing key will overwrite the existing value.
        The create_key method will verify that the new values are set correctly after
        the operation.

        Args:
            key: Either a single key name (str) or a dict of key-value pairs.
            value: The value for the key if key is str; ignored if key is dict.

        Returns:
            True if successful.

        Raises:
            ValueError: If verification fails or invalid arguments.

        Example:
            >>> ks = LogstashKeystore()  # doctest: +SKIP
            >>> ks.update_key('existing_key', 'new_value')  # doctest: +SKIP
            True
            >>> ks.update_key({'key1': 'val1', 'key2': 'val2'})  # doctest: +SKIP
            True
        """
        logger.debug(
            "Updating key(s): %s", list(key.keys()) if isinstance(key, dict) else key
        )
        result = self.create_key(key, value)
        logger.info("Successfully updated key(s) in keystore")
        return result

    def valid_keystore(self) -> bool:
        """Validate the keystore integrity.

        Checks for the bag alias "urn:logstash:secret:v1:keystore.seed"
        The presence of this indicates it was created by logstash-keystore and is
        likely valid. This does not guarantee the integrity of the keys within,
        but we should be able to read the keystore and look for keys after this.

        Returns:
            bool: True if the keystore is valid, False otherwise.
        """
        return valid_ks(self.keystore)
