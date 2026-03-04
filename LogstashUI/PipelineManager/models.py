"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

from django.db import models
from Common.encryption import encrypt_credential, decrypt_credential
from django.core.exceptions import ValidationError


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
