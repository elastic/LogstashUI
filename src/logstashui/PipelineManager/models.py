#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.conf import settings
from django.db import models
from Common.encryption import encrypt_credential, decrypt_credential
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password, check_password, identify_hasher
from django.utils import timezone
from datetime import timedelta
import hashlib
import re
import secrets
from Common import logstash_config_parse


class Policy(models.Model):
    """
    Represents a Logstash Agent policy configuration.

    policy_type:
      PACKAGED — distro Logstash (system unit ``logstash``); one system seed
      MANAGED  — agent-owned isolated Logstash tree(s); multi-instance
      SIMULATE — simulation agents with isolated paths
      EMBEDDED — Docker compose sim (no enroll)
      DEFAULT  — legacy alias for PACKAGED (pre-release DB rows)
    """

    class PolicyType(models.TextChoices):
        PACKAGED = 'PACKAGED', 'Packaged'
        MANAGED = 'MANAGED', 'Managed'
        SIMULATE = 'SIMULATE', 'Simulate'
        EMBEDDED = 'EMBEDDED', 'Embedded'
        # Legacy; prefer PACKAGED. Kept so unmigrated rows still validate.
        DEFAULT = 'DEFAULT', 'Default (legacy)'

    class LogstashSource(models.TextChoices):
        SYSTEM = 'SYSTEM', 'System Logstash'
        VERSION = 'VERSION', 'Pinned version (download)'

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Policy name"
    )
    policy_type = models.CharField(
        max_length=20,
        choices=PolicyType.choices,
        default=PolicyType.PACKAGED,
        help_text="Agent role this policy targets"
    )
    is_system = models.BooleanField(
        default=False,
        help_text="System-seeded policy (restricted delete / structural edit)"
    )
    cloned_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='clones',
        help_text="Source policy if this was cloned"
    )
    settings_path = models.CharField(
        max_length=255,
        default="/etc/logstash/",
        help_text="Path to Logstash settings directory"
    )
    logs_path = models.CharField(
        max_length=255,
        default="/var/log/logstash",
        help_text="Path to Logstash logs directory"
    )
    binary_path = models.CharField(
        max_length=255,
        default="/usr/share/logstash/bin",
        help_text="Path to Logstash binary directory"
    )
    data_path = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Path to Logstash data directory (optional; simulate derives from instance)"
    )
    agent_api_port = models.PositiveIntegerField(
        default=9500,
        help_text="Policy default agent FastAPI port (Packaged 9550 as-is; Managed 9550+N; Simulate/Embedded 9500+N or 9500)"
    )
    logstash_api_port = models.PositiveIntegerField(
        default=9560,
        help_text="Policy default Logstash HTTP API port (Packaged 9600 as-is; Managed 9700+N; Simulate/Embedded 9560+N or 9560)"
    )
    keystore_env_file = models.CharField(
        max_length=512,
        blank=True,
        default="/etc/default/logstash",
        help_text="Env file path where LOGSTASH_KEYSTORE_PASS is written for systemd"
    )
    logstash_source = models.CharField(
        max_length=20,
        choices=LogstashSource.choices,
        default=LogstashSource.SYSTEM,
        help_text="Where the simulate agent obtains the Logstash binary"
    )
    logstash_version = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Pinned Logstash version when logstash_source=VERSION (e.g. 9.4.3)"
    )
    logstash_download_dir = models.CharField(
        max_length=512,
        blank=True,
        default="/opt/logstash-agent/logstash-versions",
        help_text="Directory for auto-downloaded Logstash versions"
    )
    logstash_via_ui = models.BooleanField(
        default=False,
        help_text=(
            "Fetch the Logstash tarball from LogstashUI instead of "
            "artifacts.elastic.co. Only meaningful when logstash_source=VERSION "
            "on a MANAGED or SIMULATE policy."
        )
    )
    logstash_yml = models.TextField(
        help_text="Content of logstash.yml configuration file"
    )
    jvm_options = models.TextField(
        help_text="Content of jvm.options configuration file"
    )
    log4j2_properties = models.TextField(
        help_text="Content of log4j2.properties configuration file"
    )
    
    # Configuration file hashes (auto-computed on save)
    logstash_yml_hash = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        help_text="SHA256 hash of logstash.yml content"
    )
    jvm_options_hash = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        help_text="SHA256 hash of jvm.options content"
    )
    log4j2_properties_hash = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        help_text="SHA256 hash of log4j2.properties content"
    )

    # Keystore password (encrypted at rest)
    keystore_password = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Keystore password (encrypted at rest)"
    )
    keystore_password_hash = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        help_text="SHA256 hash of keystore password for change detection"
    )

    # Deployment tracking
    has_undeployed_changes = models.BooleanField(
        default=True,
        help_text="Indicates if there are changes that haven't been deployed"
    )
    current_revision_number = models.IntegerField(
        default=0,
        help_text="Current revision number of the policy"
    )
    last_deployed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the most recent successful deployment"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Policy'
        verbose_name_plural = 'Policies'
    
    def save(self, *args, **kwargs):
        """
        Override save to auto-compute hashes of configuration files
        """
        # Compute hashes from configuration file contents
        self.logstash_yml_hash = hashlib.sha256(self.logstash_yml.encode('utf-8')).hexdigest()
        self.jvm_options_hash = hashlib.sha256(self.jvm_options.encode('utf-8')).hexdigest()
        self.log4j2_properties_hash = hashlib.sha256(self.log4j2_properties.encode('utf-8')).hexdigest()

        # Encrypt keystore password and compute hash if provided as plaintext
        if self.keystore_password and not self._is_encrypted(self.keystore_password):
            self.keystore_password_hash = hashlib.sha256(
                self.keystore_password.encode('utf-8')
            ).hexdigest()
            self.keystore_password = encrypt_credential(self.keystore_password)
        elif not self.keystore_password:
            self.keystore_password_hash = ''

        super().save(*args, **kwargs)

    def _is_encrypted(self, value):
        """Check if a value is already encrypted (Fernet tokens start with 'gAAAAA')"""
        return value and value.startswith('gAAAAA')

    def get_keystore_password(self):
        """Get decrypted keystore password"""
        return decrypt_credential(self.keystore_password) if self.keystore_password else None

    @property
    def is_simulate_capable(self):
        return self.policy_type in (self.PolicyType.SIMULATE, self.PolicyType.EMBEDDED)

    def __str__(self):
        return self.name


class Connection(models.Model):
    """
    Represents a connection to either a Logstash Agent or a centralized management service.
    """

    class ConnectionType(models.TextChoices):
        AGENT = 'AGENT', 'Logstash Agent'
        CENTRALIZED = 'CENTRALIZED', 'Centralized Pipeline Management'

    name = models.CharField(
        max_length=100,
        help_text="A friendly name for this connection"
    )
    connection_type = models.CharField(
        max_length=20,
        choices=ConnectionType.choices,
        help_text="Type of connection (Agent or Centralized)"
    )

    # Agent Connection Fields (optional)
    agent_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text="Unique agent ID for Agent connections"
    )
    host = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Hostname or IP address for Agent connection"
    )
    port = models.PositiveIntegerField(
        default=22,
        blank=True,
        null=True,
        help_text="Agent port (default: 22)"
    )
    username = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Username for authentication"
    )
    password = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Password for authentication (leave empty if using key-based auth)"
    )
    ssh_key = models.TextField(
        blank=True,
        null=True,
        help_text="Private key (PEM format) for key-based authentication"
    )

    # Centralized Management Fields (optional)
    cloud_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Elastic Cloud ID for centralized management"
    )
    cloud_url = models.URLField(
        blank=True,
        null=True,
        help_text="Elastic Cloud URL (alternative to Cloud ID)"
    )
    api_key = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        help_text="API key for authentication (alternative to username/password)"
    )
    
    # Policy for Agent connections
    policy = models.ForeignKey(
        Policy,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='connections',
        help_text="Policy to apply to this agent (only for AGENT connection type)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_check_in = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time the agent checked in with logstashui"
    )
    status_blob = models.JSONField(
        null=True,
        blank=True,
        help_text="JSON blob containing agent health status information"
    )
    is_active = models.BooleanField(default=True)
    restart_on_next_checkin = models.BooleanField(
        default=False,
        help_text="If true, instructs the agent to restart Logstash on its next check-in"
    )
    desired_agent_version = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Desired LogstashAgent version for this connection (triggers upgrade on next check-in)"
    )

    # Simulate-instance fields (null for default / non-sim agents)
    instance_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Simulate instance number N (paths under /opt/logstash-agent/simulate-N)"
    )
    agent_api_port = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Agent FastAPI port for this connection (packaged 9550; managed 9550+N; simulate 9500+N; embedded 9500)"
    )
    logstash_api_port = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Logstash HTTP API port for this connection (packaged 9600; managed 9700+N; simulate 9560+N; embedded 9560)"
    )
    logstash_version_resolved = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Logstash version reported by the agent (for sim target dropdown)"
    )
    last_selected_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Last time this connection was selected as a sim target (sticky UX only)"
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Connection'
        verbose_name_plural = 'Connections'

    def __str__(self):
        return f"{self.name} ({self.get_connection_type_display()})"

    def clean(self):
        """
        Validate that the required fields are provided based on the connection type.
        """
        if self.connection_type == self.ConnectionType.AGENT:
            if not self.host:
                raise ValidationError("Host is required for Agent connections")
            # Note: AGENT connections use ApiKey table (FK reference), so no ssh_key/username/password required here
        else:  # CENTRALIZED
            if not (self.cloud_id or self.host):
                raise ValidationError(
                    "Either Cloud ID or Cloud URL is required for centralized connections"
                )
            if not (self.api_key or (self.username and self.password)):
                raise ValidationError(
                    "Either API key or username/password is required for centralized connections"
                )

    def save(self, *args, **kwargs):
        self.full_clean()

        # Encrypt sensitive fields before saving
        if self.password and not self._is_encrypted(self.password):
            self.password = encrypt_credential(self.password)
        if self.ssh_key and not self._is_encrypted(self.ssh_key):
            self.ssh_key = encrypt_credential(self.ssh_key)
        if self.api_key and not self._is_encrypted(self.api_key):
            self.api_key = encrypt_credential(self.api_key)

        super().save(*args, **kwargs)

    def _is_encrypted(self, value):
        """Check if a value is already encrypted (Fernet tokens start with 'gAAAAA')"""
        return value and value.startswith('gAAAAA')

    def get_password(self):
        """Get decrypted password"""
        return decrypt_credential(self.password) if self.password else None

    def get_api_key(self):
        """Get decrypted API key"""
        return decrypt_credential(self.api_key) if self.api_key else None


MANAGED_BY_CHOICES = [
    ('user', 'User'),
    ('snmp', 'SNMP'),
    ('library', 'Library'),
]


class Pipeline(models.Model):
    """
    Represents a Logstash pipeline configuration within a policy.
    Pipeline names must be unique within a policy, but can be reused across different policies.
    """
    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name='pipelines',
        help_text="Policy this pipeline belongs to"
    )
    name = models.CharField(
        max_length=100,
        help_text="Pipeline name (unique within policy)"
    )
    managed_by = models.CharField(
        max_length=20,
        choices=MANAGED_BY_CHOICES,
        default='user',
        help_text="Which subsystem owns this pipeline (user, snmp, library)"
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Description of the pipeline"
    )
    lscl = models.TextField(
        help_text="Logstash Configuration Language (pipeline configuration)"
    )
    lscl_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Hash of the LSCL content for change detection"
    )
    pipeline_hash = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        help_text="SHA256 hash of pipeline name + lscl + all settings, for agent change detection"
    )
    last_updated = models.DateTimeField(auto_now=True)

    revision_number = models.IntegerField(
        help_text="Revision number for this deployment",
        default=0
    )
    
    # Pipeline Settings
    pipeline_workers = models.IntegerField(
        default=1,
        help_text="Number of worker threads for pipeline execution"
    )
    pipeline_batch_size = models.IntegerField(
        default=128,
        help_text="Maximum number of events per batch"
    )
    pipeline_batch_delay = models.IntegerField(
        default=50,
        help_text="Batch delay in milliseconds"
    )
    queue_type = models.CharField(
        max_length=20,
        default='memory',
        help_text="Queue type (memory or persisted)"
    )
    queue_max_bytes = models.CharField(
        max_length=20,
        default='1gb',
        help_text="Maximum queue size (e.g., 1gb, 512mb)"
    )
    queue_checkpoint_writes = models.IntegerField(
        default=1024,
        help_text="Number of writes before checkpoint (for persisted queue)"
    )

    # Pipeline analysis flags (auto-computed on save)
    no_input = models.BooleanField(
        default=False,
        help_text="True if the pipeline's input block contains no plugins"
    )
    non_reloadable = models.BooleanField(
        default=False,
        help_text="True if the pipeline contains a stdin input plugin (prevents hot-reload)"
    )

    class Meta:
        ordering = ['policy', 'name']
        verbose_name = 'Pipeline'
        verbose_name_plural = 'Pipelines'
        constraints = [
            models.UniqueConstraint(
                fields=['policy', 'name'],
                name='unique_pipeline_per_policy'
            )
        ]

    def save(self, *args, **kwargs):
        hash_input = (
            f"{self.name}{self.lscl}{self.pipeline_workers}{self.pipeline_batch_size}"
            f"{self.pipeline_batch_delay}{self.queue_type}{self.queue_max_bytes}"
            f"{self.queue_checkpoint_writes}"
        )
        self.pipeline_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

        # Compute analysis flags from parsed pipeline
        try:
            import json as _json
            components = _json.loads(logstash_config_parse.logstash_config_to_components(self.lscl))
            inputs = components.get("input", [])

            self.no_input = len(inputs) == 0

            def _has_stdin(plugins):
                for plugin in plugins:
                    if plugin.get("plugin") == "stdin":
                        return True
                    nested = plugin.get("config", {}).get("plugins", [])
                    if nested and _has_stdin(nested):
                        return True
                return False

            self.non_reloadable = _has_stdin(inputs)
        except Exception:
            # Parsing failure — leave existing flags unchanged
            pass

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.policy.name} - {self.name}"


class Keystore(models.Model):
    """
    Represents encrypted key-value pairs stored in a policy's keystore.
    Key names must be unique within a policy, but can be reused across different policies.
    """
    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name='keystore_entries',
        help_text="Policy this keystore entry belongs to"
    )
    key_name = models.CharField(
        max_length=100,
        help_text="Key name (unique within policy)"
    )
    key_value = models.CharField(
        max_length=512,
        help_text="Encrypted key value"
    )
    managed_by = models.CharField(
        max_length=20,
        choices=MANAGED_BY_CHOICES,
        default='user',
        help_text="Which subsystem owns this keystore entry (user, snmp, library)"
    )
    kv_hash = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        help_text="SHA256 hash of key_name + key_value for change detection"
    )
    last_updated = models.DateTimeField(auto_now=True)

    revision_number = models.IntegerField(
        help_text="Revision number for this deployment",
        default=0
    )

    class Meta:
        ordering = ['policy', 'key_name']
        verbose_name = 'Keystore Entry'
        verbose_name_plural = 'Keystore Entries'
        constraints = [
            models.UniqueConstraint(
                fields=['policy', 'key_name'],
                name='unique_key_per_policy'
            )
        ]
    
    def save(self, *args, **kwargs):
        """
        Override save to encrypt key_value and auto-compute hash of key_name + key_value
        """
        # Compute hash from plaintext key_name + key_value BEFORE encryption
        # This ensures the hash is consistent for the same key-value pair
        if self.key_value and not self._is_encrypted(self.key_value):
            # Hash the plaintext value
            combined = f"{self.key_name}{self.key_value}"
            self.kv_hash = hashlib.sha256(combined.encode('utf-8')).hexdigest()
            # Then encrypt
            self.key_value = encrypt_credential(self.key_value)
        else:
            # If already encrypted, we can't recompute the hash from plaintext
            # Keep existing hash or compute from encrypted value (not ideal but necessary)
            if not self.kv_hash:
                combined = f"{self.key_name}{self.key_value}"
                self.kv_hash = hashlib.sha256(combined.encode('utf-8')).hexdigest()
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.policy.name} - {self.key_name}"
    
    def _is_encrypted(self, value):
        """Check if a value is already encrypted (Fernet tokens start with 'gAAAAA')"""
        return value and value.startswith('gAAAAA')
    
    def get_key_value(self):
        """Get decrypted key value"""
        return decrypt_credential(self.key_value) if self.key_value else None


class Revision(models.Model):
    """
    Represents a deployed revision (version) of a policy.
    Each revision stores a complete snapshot of the policy state at deployment time.
    """
    revision_number = models.IntegerField(
        help_text="Revision number for this deployment"
    )
    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name='revisions',
        help_text="Policy this revision belongs to"
    )
    snapshot_json = models.JSONField(
        help_text="Complete serialized state including config files, pipelines, and keystore entries"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(
        max_length=150,
        help_text="Username of the user who created this revision"
    )
    
    class Meta:
        ordering = ['-revision_number', '-created_at']
        verbose_name = 'Revision'
        verbose_name_plural = 'Revisions'
        constraints = [
            models.UniqueConstraint(
                fields=['policy', 'revision_number'],
                name='unique_revision_per_policy'
            )
        ]
    
    def __str__(self):
        return f"{self.policy.name} - Revision {self.revision_number}"


class EnrollmentToken(models.Model):
    """
    Represents an enrollment token used during initial agent enrollment.
    Each token belongs to a specific policy.
    """
    policy = models.ForeignKey(
        Policy,
        on_delete=models.CASCADE,
        related_name='enrollment_tokens',
        help_text="Policy this enrollment token is associated with"
    )
    name = models.CharField(
        max_length=100,
        default="default",
        help_text="Name for this enrollment token"
    )
    token = models.CharField(
        max_length=512,
        help_text="Enrollment token string"
    )
    
    class Meta:
        ordering = ['policy', 'name']
        verbose_name = 'Enrollment Token'
        verbose_name_plural = 'Enrollment Tokens'
        constraints = [
            models.UniqueConstraint(
                fields=['policy', 'name'],
                name='unique_token_name_per_policy'
            )
        ]
    
    def __str__(self):
        return f"{self.policy.name} - {self.name}"


#: Namespace marker on admin API tokens. Agent keys carry no prefix, so the
#: token middleware can tell the two apart from the header alone.
API_TOKEN_SCHEME = 'lsui'


class ApiKey(models.Model):
    """
    A hashed bearer credential. Two flavours share this table:

    * **Agent keys** — issued at enrollment, scoped to a ``connection``. The
      agent sends ``connection_id`` in the request body, so the row is found
      before the hash is ever checked and no lookup column is needed. These
      rows have ``prefix=None``.
    * **Admin API tokens** — issued from Management, scoped to a ``user``, and
      presented as ``Authorization: ApiKey lsui_<prefix>_<secret>``. Here the
      header is the *only* identifier, so ``prefix`` is stored unhashed and
      indexed; without it, resolving a token would mean a PBKDF2 comparison
      against every row in the table on every request.

    Exactly one of ``connection`` / ``user`` is set.
    """
    connection = models.ForeignKey(
        Connection,
        on_delete=models.CASCADE,
        related_name='api_keys',
        null=True,
        blank=True,
        help_text="Connection this API key belongs to (agent keys only)"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='api_tokens',
        null=True,
        blank=True,
        help_text="User this API token acts as (admin tokens only)"
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Human-readable label for this token"
    )
    prefix = models.CharField(
        max_length=12,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Unhashed lookup key for admin tokens; null for agent keys"
    )
    api_key = models.CharField(
        max_length=512,
        help_text="Hashed API key for agent authentication"
    )
    created_at = models.DateTimeField(null=True, blank=True, auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'API Key'
        verbose_name_plural = 'API Keys'

    def __str__(self):
        if self.connection_id:
            return f"{self.connection.name} - API Key"
        return f"{self.name or 'unnamed'} - API Token"

    def clean(self):
        # Not a DB CheckConstraint: constraint enforcement is uneven across the
        # MySQL 8.0 floor, and this is only ever violated by our own code.
        if bool(self.connection_id) == bool(self.user_id):
            raise ValidationError(
                "An ApiKey must belong to exactly one of connection or user."
            )

    def save(self, *args, **kwargs):
        # Hash on the way in, but only once. Renaming or revoking a token
        # re-saves the row, and re-running make_password on a stored hash
        # would silently invalidate the credential.
        if self.api_key and not self._is_hashed(self.api_key):
            self.api_key = make_password(self.api_key)
        super().save(*args, **kwargs)

    @staticmethod
    def _is_hashed(value):
        try:
            identify_hasher(value)
        except ValueError:
            return False
        return True

    def verify_api_key(self, raw_api_key):
        """Verify a raw API key against the stored hash"""
        return check_password(raw_api_key, self.api_key)

    # -- admin API tokens ---------------------------------------------------

    @classmethod
    def issue_for_user(cls, user, name='', expires_at=None):
        """Mint an admin API token. Returns ``(instance, raw_token)``.

        The raw token is the only time the secret exists in plaintext — it is
        not recoverable afterwards.
        """
        # token_hex, not token_urlsafe: the prefix must contain no '_' so that
        # split('_', 2) on the wire format is unambiguous.
        prefix = secrets.token_hex(6)
        secret = secrets.token_urlsafe(32)
        token = cls(
            user=user,
            name=name,
            prefix=prefix,
            api_key=secret,
            expires_at=expires_at,
        )
        token.full_clean(exclude=['api_key'], validate_unique=False)
        token.save()
        return token, f"{API_TOKEN_SCHEME}_{prefix}_{secret}"

    @staticmethod
    def parse_token(raw):
        """Split a wire-format token into ``(prefix, secret)``.

        Returns ``(None, None)`` for anything that is not an admin token,
        including agent keys, which carry no scheme marker.
        """
        parts = (raw or '').split('_', 2)
        if len(parts) != 3 or parts[0] != API_TOKEN_SCHEME:
            return None, None
        if not parts[1] or not parts[2]:
            return None, None
        return parts[1], parts[2]

    @property
    def masked(self):
        """Display form for the token list — prefix only, never the secret."""
        return f"{API_TOKEN_SCHEME}_{self.prefix}_…" if self.prefix else ''

    @property
    def is_expired(self):
        return self.expires_at is not None and self.expires_at <= timezone.now()

    @property
    def is_active(self):
        return self.revoked_at is None and not self.is_expired


#: Release tarballs LogstashUI is willing to cache and serve. Anchored, and with
#: no path separators in any branch, so a filename that matches can never escape
#: the cache directory.
ARTIFACT_FILENAME_RE = re.compile(
    r'^logstash-(?P<version>[0-9][0-9A-Za-z.+-]{0,31})'
    r'-(?P<platform>linux|darwin|windows)'
    r'-(?P<arch>x86_64|aarch64)'
    r'\.tar\.gz(?P<checksum>\.sha512)?$'
)

#: Checksum sidecars are a few dozen bytes. Serving one must not consume a slot
#: in the download semaphore, or a burst of them starves real transfers.
SMALL_FILE_BYTES = 1024 * 1024


def parse_artifact_filename(filename):
    """Validate a requested filename.

    Returns ``(tarball_name, version, arch, is_checksum)``, where ``tarball_name``
    is the ``.tar.gz`` even when the checksum sidecar was requested — both files
    belong to one :class:`LogstashArtifact` row and one upstream fetch.

    Returns ``None`` for anything unrecognized, which callers answer with 404.
    """
    match = ARTIFACT_FILENAME_RE.match(filename or '')
    if match is None:
        return None
    is_checksum = bool(match.group('checksum'))
    tarball = filename[:-len('.sha512')] if is_checksum else filename
    arch = f"{match.group('platform')}-{match.group('arch')}"
    return tarball, match.group('version'), arch, is_checksum


class LogstashArtifact(models.Model):
    """A Logstash release tarball cached locally and served to agents.

    One row covers the ``.tar.gz`` and its ``.sha512`` sidecar; a request for
    either resolves here and a single fetch pulls both.

    The status field doubles as the cross-process lock. LogstashUI has no shared
    cache backend (no ``CACHES`` in settings, so Django falls back to per-process
    LocMemCache), and gunicorn runs 2+ worker processes, so an in-memory lock
    cannot prevent two workers starting the same 450 MB download. A conditional
    UPDATE on this row can — see :meth:`claim_for_fetch`.
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        FETCHING = 'FETCHING', 'Downloading'
        READY = 'READY', 'Ready'
        FAILED = 'FAILED', 'Failed'
        IMPORTING = 'IMPORTING', 'Verifying import'

    #: A claim whose heartbeat is older than this is assumed dead and may be
    #: taken over. Fetch greenlets die with their gunicorn worker, so on any
    #: restart mid-download this is the recovery path, not an edge case.
    STALE_CLAIM_SECONDS = 120

    filename = models.CharField(
        max_length=255,
        unique=True,
        help_text="Tarball filename, e.g. logstash-9.4.3-linux-x86_64.tar.gz"
    )
    version = models.CharField(
        max_length=32,
        db_index=True,
        help_text="Logstash version, e.g. 9.4.3"
    )
    arch = models.CharField(
        max_length=32,
        help_text="Platform and architecture, e.g. linux-x86_64"
    )
    source_url = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Explicit upstream URL. Blank derives one from the base URL setting."
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    size_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Total size, from the upstream Content-Length or the file on disk"
    )
    bytes_downloaded = models.BigIntegerField(
        default=0,
        help_text="Progress counter, written on a time floor rather than per chunk"
    )
    sha512 = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Verified SHA-512 of the published tarball"
    )
    error = models.TextField(
        blank=True,
        default="",
        help_text="Why the last fetch failed"
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    serve_count = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Fresh tarball downloads by agents. Checksum fetches and resumed "
            "range requests hit the same row but are not counted"
        )
    )
    last_served_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the tarball was last downloaded in full"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'logstash_artifact'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} ({self.status})"

    @property
    def checksum_filename(self):
        return f"{self.filename}.sha512"

    @property
    def percent(self):
        """Whole-percent progress, or None when the total is not yet known."""
        if not self.size_bytes:
            return None
        return min(100, int(self.bytes_downloaded * 100 / self.size_bytes))

    def resolve_source_url(self, base_url):
        """Upstream URL for the tarball. An explicit source_url wins."""
        if self.source_url:
            return self.source_url
        return f"{base_url.rstrip('/')}/{self.filename}"

    @classmethod
    def claim_for_fetch(cls, pk, *, now=None):
        """Atomically take ownership of a download. Returns True if we won.

        A single conditional UPDATE is the whole mechanism. It is race-free on
        every supported engine: PostgreSQL re-evaluates the WHERE clause after
        taking the row lock, InnoDB does a current read so the loser sees the
        winner's committed FETCHING, and SQLite has one global writer. Exactly
        one caller comes back with a rowcount of 1.

        A FETCHING row whose heartbeat has gone stale is also claimable, which
        is how a download orphaned by a worker restart gets picked back up.
        """
        now = now or timezone.now()
        stale_before = now - timedelta(seconds=cls.STALE_CLAIM_SECONDS)
        updated = cls.objects.filter(pk=pk).filter(
            models.Q(status__in=[cls.Status.PENDING, cls.Status.FAILED])
            | models.Q(status=cls.Status.FETCHING, heartbeat_at__lt=stale_before)
            | models.Q(status=cls.Status.FETCHING, heartbeat_at__isnull=True)
        ).update(
            status=cls.Status.FETCHING,
            claimed_at=now,
            heartbeat_at=now,
            bytes_downloaded=0,
            error='',
        )
        return updated == 1

    @classmethod
    def release_claim(cls, pk):
        """Hand a claim back without failing it, for the over-capacity path."""
        return cls.objects.filter(pk=pk, status=cls.Status.FETCHING).update(
            status=cls.Status.PENDING,
            claimed_at=None,
            heartbeat_at=None,
        )

    @classmethod
    def active_fetch_count(cls, *, now=None):
        """Fetches genuinely in flight, ignoring rows abandoned by dead workers."""
        now = now or timezone.now()
        stale_before = now - timedelta(seconds=cls.STALE_CLAIM_SECONDS)
        return cls.objects.filter(
            status=cls.Status.FETCHING,
            heartbeat_at__gte=stale_before,
        ).count()
