#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Crypto utilities for Logstash keystore operations.

This module provides functions for parsing and decrypting PKCS12 keystores
used by Logstash.
"""

import base64
import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple

# asn1crypto lacks type stubs
from asn1crypto.core import Sequence  # type: ignore[import-untyped]
from asn1crypto.pkcs12 import (
    Pfx,
    AuthenticatedSafe,
    SafeContents,
)  # type: ignore[import-untyped]
from asn1crypto.keys import EncryptedPrivateKeyInfo  # type: ignore[import-untyped]
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from .exceptions import IncorrectPassword, LogstashKeystoreException
from .utils import read_file_bytes
from .settings import (
    AES_KEY_LENGTHS,
    ATTR_TYPES,
    CERT_BAG,
    KEY_BAG,
    KEYSTORE_ALIAS,
    KEYSTORE_SEED,
    OBFUSCATION_KEY,
    PBES2,
    PKCS8_SHROUDED_KEY_BAG,
    SECRET_BAG,
    URN_PREFIX,
)

logger = logging.getLogger(__name__)

# Mapping of bag OIDs to handler functions for extracting base64 strings
BAG_HANDLERS = {
    PKCS8_SHROUDED_KEY_BAG: lambda bag, password: decrypt_private_key(
        bag["bag_value"], password
    ).decode("utf-8"),
    SECRET_BAG: lambda bag, password: bag["bag_value"]["secret_value"].native.decode(
        "utf-8"
    ),
    CERT_BAG: lambda bag, password: decrypt_private_key(
        EncryptedPrivateKeyInfo.load(bag["bag_value"]["secret_value"].native), password
    ).decode("utf-8"),
    KEY_BAG: lambda bag, password: bag["bag_value"]["private_key"].native.decode(
        "utf-8"
    ),
}


def pbkdf2_derive_key(
    hash_alg, length: int, salt: bytes, iterations: int, password: str
) -> bytes:
    """Derive a key using PBKDF2.

    Args:
        hash_alg: The hash algorithm to use.
        length: The length of the derived key.
        salt: The salt bytes.
        iterations: The number of iterations.
        password: The password string.

    Returns:
        The derived key bytes.
    """
    kdf = PBKDF2HMAC(
        algorithm=hash_alg, length=length, salt=salt, iterations=iterations
    )
    return kdf.derive(password.encode())


def decrypt_padded_data(
    encrypted_data: bytes, key: bytes, cipher_alg, iv: bytes, block_size: int
) -> bytes:
    """Decrypt and unpad data.

    Args:
        encrypted_data: The encrypted data bytes.
        key: The decryption key.
        cipher_alg: The cipher algorithm.
        iv: The initialization vector.
        block_size: The block size for padding.

    Returns:
        The decrypted and unpadded data.
    """
    cipher = Cipher(cipher_alg(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(encrypted_data) + decryptor.finalize()
    unpadder = padding.PKCS7(block_size).unpadder()
    return unpadder.update(padded_data) + unpadder.finalize()


def get_b64_string_from_bag(bag, bag_id: str, password: str) -> str:
    """Extract base64-encoded secret string from a bag.

    Args:
        bag: The PKCS12 bag object.
        bag_id: The bag type OID.
        password: The password for decryption.

    Returns:
        The base64-encoded secret string.

    Raises:
        ValueError: If decoding fails.
        NotImplementedError: If bag type is unsupported.
    """
    handler = BAG_HANDLERS.get(bag_id)
    if handler:
        return handler(bag, password)
    raise NotImplementedError(f"Unsupported bag type: {bag_id}")


def load_pfx(data: bytes) -> Pfx:
    """Load a PKCS12 PFX from bytes.

    Args:
        data: The raw bytes of the PKCS12 file.

    Returns:
        The parsed Pfx object.

    Example:
        >>> pfx = load_pfx(b'pkcs12_data')
        >>> pfx.version.native
        3
    """
    return Pfx.load(data)


def parse_authenticated_safe(pfx: Pfx) -> AuthenticatedSafe:
    """Parse the AuthenticatedSafe from a PFX object.

    Args:
        pfx: The loaded PFX object.

    Returns:
        The AuthenticatedSafe containing content info sequences.

    Example:
        >>> pfx = load_pfx(data)
        >>> auth_safe = parse_authenticated_safe(pfx)
        >>> len(auth_safe) > 0
        True
    """
    auth_safe = pfx["auth_safe"]
    auth_safe_data = auth_safe["content"].native  # type: ignore[reportIndexIssue]
    return AuthenticatedSafe.load(auth_safe_data)


def iter_safe_contents_bags(safe_contents_data: bytes) -> Iterator[Any]:
    """Iterate over bags in SafeContents data.

    Args:
        safe_contents_data: The raw bytes of SafeContents.

    Yields:
        Individual PKCS12 bags.

    Example:
        >>> bags = list(iter_safe_contents_bags(data))
        >>> len(bags) > 0
        True
    """
    safe_contents = SafeContents.load(safe_contents_data)
    yield from safe_contents


def iter_keystore_bags(data: bytes) -> Iterator[Any]:
    """Iterate over all bags in the keystore.

    Parses the PKCS12 structure, decrypting encrypted content using the provided
    password, and yields individual bags from SafeContents.

    Args:
        data: The raw bytes of the PKCS12 keystore.
        password: The password to decrypt encrypted content.

    Yields:
        Individual PKCS12 bags containing keys or secrets.

    Raises:
        NotImplementedError: If an unsupported encryption algorithm is encountered.
        ValueError: If an unsupported content type is encountered.

    Example:
        >>> bags = list(iter_keystore_bags(data, 'password'))
        >>> len(bags) > 0
        True
    """
    pfx = load_pfx(data)
    authenticated_safe = parse_authenticated_safe(pfx)
    for content_info in authenticated_safe:
        if content_info["content_type"].native != "data":
            raise ValueError(
                f"Unsupported content type in AuthenticatedSafe: "
                f"{content_info['content_type'].native}"
            )
        try:
            # safe_contents_data = decrypt_content_info(content_info, password)
            yield from iter_safe_contents_bags(content_info["content"].native)
        except ValueError:
            # Skip unsupported content types
            continue


def get_pbes2_key_length(parameters) -> int:
    """Determine the key length for PBES2 encryption.

    Args:
        parameters: The encryption algorithm parameters.

    Returns:
        The key length in bytes.

    Raises:
        NotImplementedError: If the encryption scheme is unsupported.
    """
    key_derivation_func = parameters["key_derivation_func"]
    encryption_scheme = parameters["encryption_scheme"]
    pbkdf2_params = key_derivation_func["parameters"]
    try:
        key_length = pbkdf2_params["key_length"]
    except KeyError:
        key_length = None
    if key_length:
        return key_length.native
    enc_oid = encryption_scheme["algorithm"].native
    key_len = AES_KEY_LENGTHS.get(enc_oid)
    if key_len is None:
        raise NotImplementedError(f"Unsupported encryption scheme: {enc_oid}")
    return key_len


def decrypt_private_key_pbes2(bag_value, password: str) -> bytes:
    """Decrypt private key using PBES2.

    Args:
        bag_value: The encrypted bag value.
        password: The decryption password.

    Returns:
        The decrypted private key bytes.

    Raises:
        NotImplementedError: If the encryption scheme is unsupported.
    """
    parameters = bag_value["encryption_algorithm"]["parameters"]
    pbkdf2_params = parameters["key_derivation_func"]["parameters"]
    salt = pbkdf2_params["salt"].native
    iterations = pbkdf2_params["iteration_count"].native
    key_len = get_pbes2_key_length(parameters)
    key = pbkdf2_derive_key(hashes.SHA256(), key_len, salt, iterations, password)
    enc_params = parameters["encryption_scheme"]["parameters"]
    iv = enc_params.native
    encrypted_data = bag_value["encrypted_data"].native
    private_key_info_der = decrypt_padded_data(
        encrypted_data, key, algorithms.AES, iv, 128
    )
    seq = Sequence.load(private_key_info_der)
    return seq[2].native


def decrypt_private_key(bag_value, password: str) -> bytes:
    """Decrypt an encrypted private key using the keystore password.

    Supports PBEWithSHA1And3-KeyTripleDES-CBC and PBES2 encryption.

    Args:
        bag_value: The encrypted bag value from the PKCS12 structure.
        password: The password for decryption.

    Returns:
        The decrypted private key bytes.

    Raises:
        NotImplementedError: If an unsupported encryption algorithm is used.

    Example:
        >>> key_bytes = decrypt_private_key(bag_value, 'password')
        >>> isinstance(key_bytes, bytes)
        True
    """
    encryption_algorithm = bag_value["encryption_algorithm"]
    algorithm_oid = encryption_algorithm["algorithm"].native
    # ### Not apparently needed by logstash-keystore
    # if algorithm_oid == PBE_WITH_SHA1_3DES:
    #     return decrypt_private_key_pbe_sha1_3des(bag_value, password)
    if algorithm_oid == PBES2:
        return decrypt_private_key_pbes2(bag_value, password)
    # implied else: unsupported encryption algorithm
    logger.error("Unsupported encryption algorithm: %s", algorithm_oid)
    raise NotImplementedError(f"Unsupported encryption algorithm: {algorithm_oid}")


def get_alias_from_bag(bag) -> Optional[str]:
    """Extract the friendly name alias from a PKCS12 bag.

    Args:
        bag: The PKCS12 bag object.

    Returns:
        The alias string if present, otherwise None.

    Example:
        >>> alias = get_alias_from_bag(bag)
        >>> alias is None or isinstance(alias, str)
        True
    """
    alias = None
    bag_attrs = bag["bag_attributes"] or []
    if bag_attrs:
        for attr in bag_attrs:
            attr_type = attr["type"].native
            if attr_type in ATTR_TYPES:
                alias = attr["values"][0].native
                alias = (
                    alias.decode("utf-8") if isinstance(alias, bytes) else str(alias)
                )
                # logger.debug("Found alias: %s", alias)
                break
    return alias


def get_bag_timestamp(bag) -> Optional[int]:
    """Extract creation and modification timestamps from bag attributes.

    Args:
        bag: The PKCS12 bag object.
    Returns:
        An integer timestamp since epoch, or None if not present.
    """
    timestamp = None
    bag_attrs = bag["bag_attributes"] or []
    if bag_attrs:
        for attr in bag_attrs:
            time_value = attr["values"][0].native
            # Decode bytes to string if necessary
            if isinstance(time_value, bytes):
                try:
                    time_value = time_value.decode("utf-8")
                except UnicodeDecodeError:
                    continue  # Skip if not valid UTF-8
            # Check for "Time <timestamp>" pattern
            if isinstance(time_value, str) and time_value.startswith("Time "):
                try:
                    timestamp_ms = int(time_value.split(" ")[1])
                    timestamp = int(timestamp_ms / 1000.0)
                    # logger.debug("Parsed modification time: %s", timestamp)
                    break  # Assume only one timestamp per bag
                except (ValueError, IndexError):
                    logger.warning("Failed to parse time value: %s", time_value)
    return timestamp


def is_keystore_seed_bag(bag) -> bool:
    """Check if a bag is the keystore seed.

    Args:
        bag: The PKCS12 bag object.

    Returns:
        True if the bag is the Logstash keystore seed, False otherwise.

    Example:
        >>> is_keystore_seed_bag(bag)
        False
    """
    result = get_alias_from_bag(bag) == KEYSTORE_ALIAS
    return result


def is_secret_bag_for_key(bag, key_name: str) -> bool:
    """Check if a bag contains the secret for the given key.

    Args:
        bag: The PKCS12 bag object.
        key_name: The key name to check for.

    Returns:
        True if the bag contains the secret for the key, False otherwise.

    Example:
        >>> is_secret_bag_for_key(bag, 'my_key')
        True
    """
    alias = get_alias_from_bag(bag)
    if alias:
        urn = f"{URN_PREFIX}:{key_name.lower()}"
        result = alias == urn
        return result
    return False


def validate_keystore_integrity(data: bytes) -> bool:
    """Validate keystore integrity by checking for the keystore seed bag.

    Keystore integrity validation does not fail with an incorrect password.
    A password is necessary to decrypt keys from the secret bag, but the presence
    of the keystore seed bag can be checked without a password.

    Args:
        data: The raw bytes of the PKCS12 keystore.
        password: The password for decryption.

    Returns:
        True if the keystore seed bag is found, False otherwise.

    Example:
        >>> validate_keystore_integrity(data)
        True
    """
    try:
        for bag in iter_keystore_bags(data):
            if is_keystore_seed_bag(bag):
                return True
            # logger.debug("Checked bag, not seed: %s", get_alias_from_bag(bag))
    except (ValueError, NotImplementedError) as e:
        logger.error("Error validating keystore integrity: %s", e)
        raise ValueError(
            "Unable to validate keystore integrity. Invalid format?"
        ) from e
    logger.error("Keystore seed bag not found")
    return False


def process_secret_bag(
    bag, password: str
) -> Optional[Tuple[str, str, Optional[float]]]:
    """Process a PKCS12 bag to extract a key-value pair and timestamp if it's a
    Logstash secret.

    Handles both pkcs8_shrouded_key_bag and secret_bag types, decoding
    base64-encoded values as used by Logstash.

    Args:
        bag: The PKCS12 bag object.
        password: The password for decryption.

    Returns:
        A tuple of (key, value, timestamp) if the bag contains a Logstash
        secret, None otherwise.

    Raises:
        ValueError: If base64 decoding fails.

    Example:
        >>> result = process_secret_bag(bag, 'password')
        >>> result is None or isinstance(result, tuple)
        True
    """
    bag_id = bag["bag_id"].dotted
    # logger.debug("Processing bag with ID: %s", bag_id)
    alias = get_alias_from_bag(bag)
    timestamp = get_bag_timestamp(bag)
    # logger.debug("Bag alias: %s, Timestamp: %s", alias, timestamp)
    if alias and alias.startswith(URN_PREFIX):
        key = alias.split(":")[-1]
        if key != KEYSTORE_SEED:
            try:
                b64_string = get_b64_string_from_bag(bag, bag_id, password)
                decoded_value = base64.b64decode(b64_string).decode("utf-8")
                # logger.debug("Decoded %s bag for key: %s", bag_id, key)
                return key, decoded_value, timestamp
            except (ValueError, NotImplementedError) as e:
                logger.error("Failed to process bag %s: %s", bag_id, e)
                if "Invalid padding bytes" in str(e):
                    raise ValueError("Unable to read data. Invalid password?") from e
                return None
    return None


def generate_salt_iv() -> bytes:
    """Generate new random salt and IV.

    Returns:
        32 bytes: 16 bytes salt + 16 bytes IV.

    Example:
        >>> salt_iv = generate_salt_iv()
        >>> len(salt_iv)
        32
    """
    return secrets.token_bytes(16) + secrets.token_bytes(16)


def _salt_and_iv(salt_iv: bytes) -> Tuple[bytes, bytes]:
    """Split combined salt and IV into separate components.

    Args:
        salt_iv: The combined salt and IV bytes (32 bytes total).
    Returns:
        A tuple of (salt, iv) where each is 16 bytes.
    """
    if len(salt_iv) != 32:
        raise ValueError("Invalid salt_iv length, expected 32 bytes")
    return salt_iv[:16], salt_iv[16:32]


def _get_cipher(salt: bytes, iv: bytes) -> Cipher:
    """Get a configured AES cipher for obfuscation.

    Args:
        salt: 16-byte salt for key derivation.
        iv: 16-byte initialization vector.

    Returns:
        Configured Cipher object.
    """
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = kdf.derive(OBFUSCATION_KEY)
    return Cipher(algorithms.AES(key), modes.CBC(iv))


def obfuscate_value(value: str, salt_iv: bytes) -> bytes:
    """Obfuscate a value using AES encryption with PKCS7 padding.

    Args:
        value: The string value to obfuscate.
        salt_iv: The 32-byte salt and IV combined.

    Returns:
        The encrypted bytes.

    Example:
        >>> salt_iv = b'\\x00' * 32
        >>> encrypted = obfuscate_value('test', salt_iv)
        >>> isinstance(encrypted, bytes)
        True
    """
    cipher = _get_cipher(*_salt_and_iv(salt_iv))
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded_value = padder.update(value.encode("utf-8")) + padder.finalize()
    encrypted = encryptor.update(padded_value) + encryptor.finalize()
    return encrypted


def deobfuscate_value(encrypted: bytes, salt_iv: bytes) -> str:
    """Deobfuscate a value using AES decryption with PKCS7 unpadding.

    Args:
        encrypted: The encrypted bytes.
        salt_iv: The 32-byte salt and IV combined.

    Returns:
        The original string value.

    Raises:
        ValueError: If decryption fails.

    Example:
        >>> salt_iv = b'\\x00' * 32
        >>> encrypted = obfuscate_value('test', salt_iv)
        >>> deobfuscate_value(encrypted, salt_iv)
        'test'
    """
    cipher = _get_cipher(*_salt_and_iv(salt_iv))
    decryptor = cipher.decryptor()
    decrypted_padded = decryptor.update(encrypted) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
    return decrypted.decode("utf-8")


@dataclass
class KeyEntry:
    """A data class to store a keystore key entry with its obfuscated value and
    timestamp.

    Attributes:
        obfuscated_value: The obfuscated value object.
        timestamp: The timestamp when the key was last modified
            (seconds since epoch).
    """

    obfuscated_value: "ObfuscatedValue"
    timestamp: int


class ObfuscatedValue:
    """A class to store and manage obfuscated values.

    This class encapsulates the obfuscation logic, allowing values to be stored
    securely in memory and revealed on demand.
    """

    def __init__(self, value: str, salt_iv: bytes):
        """Initialize with a plain value, obfuscating it.

        Args:
            value: The plain string value.
            salt_iv: 32-byte salt/IV for obfuscation.

        Raises:
            ValueError: If salt_iv is not 32 bytes.

        Example:
            >>> salt_iv = b'\\x00' * 32
            >>> ov = ObfuscatedValue('secret', salt_iv)
            >>> ov.reveal(salt_iv)
            'secret'
        """
        self._valid_salt(salt_iv)
        logger.debug("Obfuscating value with provided salt_iv")
        self.encrypted = obfuscate_value(value, salt_iv)

    def __eq__(self, other) -> bool:
        """Check equality: encrypted if same salt_iv, else decrypted.

        Args:
            other: Another ObfuscatedValue object or str obfuscated by the same
                salt_iv to compare.

        Returns:
            True if values match, False otherwise.

        Example:
            >>> salt_iv = b'\\x00' * 32
            >>> ov1 = ObfuscatedValue('secret', salt_iv)
            >>> ov2 = ObfuscatedValue('secret', salt_iv)
            >>> ov1 == ov2
            True
            >>> ov1 == obfuscate_value('secret', salt_iv)
            True
        """
        # Try to compare known encrypted values first
        if isinstance(other, ObfuscatedValue):
            return self.encrypted == other.encrypted
        # If other is bytes (encrypted string), compare (assuming same salt_iv)
        if isinstance(other, bytes):
            if self.encrypted == other:
                return True
        if isinstance(other, str):
            # Without the salt_iv, we can't compare encrypted values
            return False
        return False

    def __repr__(self):
        return f"ObfuscatedValue(encrypted={self.encrypted!r})"

    def reveal(self, salt_iv: bytes) -> str:
        """Reveal and return the plain value.

        Args:
            salt_iv: 32-byte salt/IV for deobfuscation.

        Returns:
            The original string value.

        Raises:
            ValueError: If salt_iv is invalid.

        Example:
            >>> salt_iv = b'\\x00' * 32
            >>> ov = ObfuscatedValue('secret', salt_iv)
            >>> ov.reveal(salt_iv)
            'secret'
        """
        self._valid_salt(salt_iv)
        logger.debug("Revealing value with provided salt_iv")
        return deobfuscate_value(self.encrypted, salt_iv)

    def _valid_salt(self, salt_iv) -> bool:
        """Raise ValueError if salt_iv is not 32 bytes

        Args:
            salt_iv: 32-byte salt/IV for obfuscation.

        Returns:
            True: If salt_iv is 32 bytes

        Raises:
            ValueError: If salt_iv is not 32 bytes.
        """
        if len(salt_iv) != 32:
            raise ValueError("salt_iv must be 32 bytes")
        return True


def secret_bag_generator(
    file: Path, password: str
) -> Iterator[Tuple[str, str, Optional[float]]]:
    """Generator that yields key-value-timestamp tuples from secret bags in the
    keystore.

    Args:
        file: Path to the keystore file.
        password: The password for decryption.

    Yields:
        Tuples of (key, value, timestamp) for each secret bag found.

    Raises:
        ValueError: If incorrect password is provided.
    """
    data = read_file_bytes(file)
    try:
        for bag in iter_keystore_bags(data):
            result = process_secret_bag(bag, password)
            if result:
                yield result
    except ValueError as e:
        if "Invalid password" in str(e):
            logger.error("Incorrect password for keystore: %s", file)
            raise IncorrectPassword from e
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Exception when reading keystore: %s", exc)
        # Double-check it's a valid keystore
        if not valid_keystore(file):
            logger.error("Not a valid keystore file: %s", file)
        raise LogstashKeystoreException from exc


def read_keystore(file: Path, password: str) -> dict[str, Tuple[str, int]]:
    """Read all key-value pairs and timestamps from the keystore as a dictionary.

    Args:
        file: Path to the keystore file.
        password: The password for decryption.

    Returns:
        A dictionary of key to (value, timestamp) tuples.

    Raises:
        IncorrectPassword: If password is incorrect (keys exist but cannot be read).
    """

    kvpairs = {}
    for result in secret_bag_generator(file, password):
        if result:
            key, value, timestamp = result
            kvpairs[key.upper()] = (value, timestamp)
    return kvpairs


def valid_keystore(file: Path) -> bool:
    """Validate the keystore integrity.

    Checks for the bag alias "urn:logstash:secret:v1:keystore.seed"
    The presence of this indicates it was created by logstash-keystore and is
    likely valid. This does not guarantee the integrity of the keys within,
    but we should be able to read the keystore and look for keys after this.

    Args:
        file: Path to the keystore file.

    Returns:
        True if the keystore is valid, False otherwise.
    """
    if not file.exists():
        return False
    # read_file_bytes also checks for existence, but we want to catch that separately
    # to avoid having to do a try/except only to return False on FileNotFoundError
    data = read_file_bytes(file)
    result = validate_keystore_integrity(data)
    return result
