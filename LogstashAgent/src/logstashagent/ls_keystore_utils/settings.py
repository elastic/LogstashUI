"""
Common location for settings and constants used across the ls-keystore-utils package.
"""

# Paths to search for the logstash-keystore binary and path.settings candidates

PRIMARY_PATH = "/usr/share/logstash/bin/logstash-keystore"
HOME_BREW_LS_PATH = "/opt/homebrew/Cellar/logstash"
HOME_BREW_LS_CFG = "/opt/homebrew/etc/logstash"
HOME_BREW_PATTERN = f"{HOME_BREW_LS_PATH}/*/libexec/bin/logstash-keystore"
PATTERNS = [PRIMARY_PATH, HOME_BREW_PATTERN]
ALTERNATE_LS_PATHS = {HOME_BREW_LS_PATH: HOME_BREW_LS_CFG}  # For Homebrew installations

CANDIDATES = ["/etc/logstash", "/usr/share/logstash/config"]


# Cryptographic constants for PKCS#12 parsing and generation

# OID constants for better readability
PBES2 = "pbes2"
AES128 = "2.16.840.1.101.3.4.1.2"
AES192 = "2.16.840.1.101.3.4.1.22"
AES256 = "2.16.840.1.101.3.4.1.42"

# Bag type OIDs
KEY_BAG = "1.2.840.113549.1.12.10.1.1"
PKCS8_SHROUDED_KEY_BAG = "1.2.840.113549.1.12.10.1.2"
SECRET_BAG = "1.2.840.113549.1.12.10.1.3"
CERT_BAG = "1.2.840.113549.1.12.10.1.5"

# Attribute type constants
FRIENDLY_NAME = "friendly_name"
FRIENDLY_NAME_OID = "1.2.840.113549.1.9.20"
LOCAL_KEY_ID = "local_key_id"
LOCAL_KEY_ID_OID = "1.2.840.113549.1.9.21"

ATTR_TYPES = (FRIENDLY_NAME, FRIENDLY_NAME_OID, LOCAL_KEY_ID, LOCAL_KEY_ID_OID)

# AES key length mapping
AES_KEY_LENGTHS = {
    AES128: 16,
    AES192: 24,
    AES256: 32,
}

# Salt/IV filename
SALT_IV_FILENAME = ".salt-iv"

# Password obfuscation heuristic
OBFUSCATION_KEY = b"logstash_keystore_obfuscation_key"
PASSWORD_OBFUSCATED_LENGTH = 32

# Bag alias constants
URN_PREFIX = "urn:logstash:secret:v1"
KEYSTORE_SEED = "keystore.seed"
KEYSTORE_ALIAS = URN_PREFIX + ":" + KEYSTORE_SEED

# ### Not apparently needed for Logstash keystore operations
# ### May be useful if the keystore standard changes
# PBE_WITH_SHA1_3DES = "1.2.840.113549.1.12.1.3"
