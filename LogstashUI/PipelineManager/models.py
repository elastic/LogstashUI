#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.db import models
from Common.encryption import encrypt_credential, decrypt_credential
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password, check_password


class Policy(models.Model):
    """
    Represents a Logstash Agent policy configuration.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Policy name"
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
    logstash_yml = models.TextField(
        help_text="Content of logstash.yml configuration file"
    )
    jvm_options = models.TextField(
        help_text="Content of jvm.options configuration file"
    )
    log4j2_properties = models.TextField(
        help_text="Content of log4j2.properties configuration file"
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
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Policy'
        verbose_name_plural = 'Policies'
    
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
    is_active = models.BooleanField(default=True)

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
            if not (self.ssh_key or (self.username and self.password)):
                raise ValidationError(
                    "Either key or username/password is required for Agent connections"
                )
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
    last_updated = models.DateTimeField(auto_now=True)
    
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
    last_updated = models.DateTimeField(auto_now=True)
    
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
    
    def __str__(self):
        return f"{self.policy.name} - {self.key_name}"
    
    def save(self, *args, **kwargs):
        # Encrypt key_value before saving if not already encrypted
        if self.key_value and not self._is_encrypted(self.key_value):
            self.key_value = encrypt_credential(self.key_value)
        super().save(*args, **kwargs)
    
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
        verbose_name = 'Enrollment Token'
        verbose_name_plural = 'Enrollment Tokens'
    
    def __str__(self):
        return f"{self.policy.name} - {self.name}"


class ApiKey(models.Model):
    """
    Represents an API key used by an enrolled agent for authenticated polling/check-in.
    Each API key belongs to a specific connection.
    """
    connection = models.ForeignKey(
        Connection,
        on_delete=models.CASCADE,
        related_name='api_keys',
        help_text="Connection this API key belongs to"
    )
    api_key = models.CharField(
        max_length=512,
        help_text="Hashed API key for agent authentication"
    )
    
    class Meta:
        verbose_name = 'API Key'
        verbose_name_plural = 'API Keys'
    
    def __str__(self):
        return f"{self.connection.name} - API Key"
    
    def save(self, *args, **kwargs):
        # Always hash the API key before saving
        if self.api_key:
            self.api_key = make_password(self.api_key)
        super().save(*args, **kwargs)
    
    def verify_api_key(self, raw_api_key):
        """Verify a raw API key against the stored hash"""
        return check_password(raw_api_key, self.api_key)
