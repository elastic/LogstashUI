#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Django models for the SNMP NMS.

Rows cover monitored networks and devices, SNMP credentials, poll profiles,
device templates, and a singleton deployment-state tracker.
"""

from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from Common.encryption import encrypt_credential, decrypt_credential
from PipelineManager.models import Connection
import ipaddress


class Network(models.Model):
    """Monitored IP range that owns devices and generated Logstash pipelines.

    `deployment_mode` is CENTRALIZED (Elasticsearch CPM) or AGENT (LogstashAgent).
    Centralized networks also choose `credential_mode`: KEYSTORE references
    (`${snmp_…}`) versus PLAINTEXT secrets embedded in LSCL.
    """

    DEPLOYMENT_MODE_CHOICES = [
        ('CENTRALIZED', 'Centralized Pipeline Management'),
        ('AGENT', 'LogstashAgent'),
    ]

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Friendly name for this network"
    )
    
    network_range = models.CharField(
        max_length=50,
        help_text="Network in CIDR notation (e.g., 192.168.1.0/24)"
    )

    deployment_mode = models.CharField(
        max_length=20,
        choices=DEPLOYMENT_MODE_CHOICES,
        default='CENTRALIZED',
        help_text="Deployment mode for this network (Centralized Pipeline Management or LogstashAgent)"
    )

    credential_mode = models.CharField(
        max_length=20,
        choices=[
            ('KEYSTORE', 'Manage Keystore Manually'),
            ('PLAINTEXT', 'Plaintext Credentials'),
        ],
        default='KEYSTORE',
        help_text="How credentials are supplied to pipelines (Centralized Pipeline Management mode only)"
    )

    connection = models.ForeignKey(
        Connection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='snmp_networks',
        help_text="Elasticsearch connection for this network"
    )

    agent_connection = models.ForeignKey(
        Connection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_snmp_networks',
        help_text="LogstashAgent connection for deployment (AGENT mode only)"
    )
    
    discovery_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic device discovery on this network"
    )
    
    traps_enabled = models.BooleanField(
        default=False,
        help_text="Enable SNMP traps for this network"
    )
    
    discovery_credential = models.ForeignKey(
        'Credential',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='discovery_networks',
        help_text="SNMP credential to use for device discovery on this network"
    )
    
    credential = models.ForeignKey(
        'Credential',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trap_networks',
        help_text="SNMP credential to use for trap reception on this network"
    )
    
    interval = models.PositiveIntegerField(
        default=30,
        help_text="Polling interval in seconds"
    )
    
    namespace = models.CharField(
        max_length=100,
        default='default',
        help_text="Data stream namespace for organizing data (e.g., dev, prod, qa). Max 100 bytes."
    )

    namespace_from_device_template = models.BooleanField(
        default=False,
        help_text="When enabled, the normalized device template name is used as the data stream namespace instead of the fixed namespace value."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'SNMP Network'
        verbose_name_plural = 'SNMP Networks'
    
    def __str__(self):
        return f"{self.name} ({self.network_range})"
    
    def clean(self):
        """Validate that `network_range` is CIDR notation.

        Raises:
            ValidationError: If the range is not a valid IPv4 or IPv6 network.
        """
        super().clean()
        
        if self.network_range:
            try:
                # Validate CIDR notation
                ipaddress.ip_network(self.network_range, strict=False)
            except ValueError as e:
                raise ValidationError({
                    'network_range': f'Invalid CIDR notation: {str(e)}'
                })
    
    def save(self, *args, **kwargs):
        """Run `full_clean()` then persist the row."""
        self.full_clean()
        super().save(*args, **kwargs)

class Device(models.Model):
    """Individual SNMP-polled host.

    At least one of `ip_address` or `hostname` is required. Unassigned devices
    receive the official `default` template on save when that row exists.
    """
    
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Friendly name for this device"
    )
    
    ip_address = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="IP address of the device (optional if hostname is provided)"
    )

    hostname = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="DNS hostname of the device (optional if IP address is provided)"
    )
    
    port = models.IntegerField(
        default=161,
        help_text="SNMP port (default: 161)"
    )
    
    retries = models.IntegerField(
        default=2,
        help_text="Number of retries for SNMP requests (default: 2)"
    )
    
    timeout = models.IntegerField(
        default=1000,
        help_text="Timeout in milliseconds for SNMP requests (default: 1000)"
    )
    
    credential = models.ForeignKey(
        'Credential',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='devices',
        help_text="SNMP credential to use for this device"
    )
    
    network = models.ForeignKey(
        'Network',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='devices',
        help_text="Network this device belongs to"
    )
    
    device_template = models.ForeignKey(
        'DeviceTemplate',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='devices',
        help_text="Device template assigned to this device (defaults to 'Default' template if not specified)"
    )

    # Location fields
    site = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Site or campus this device is located at"
    )

    building = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Building within the site"
    )

    room = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Room or rack location within the building"
    )

    latitude = models.DecimalField(
        max_digits=15,
        decimal_places=10,
        null=True,
        blank=True,
        help_text="Geographic latitude of the device location"
    )

    longitude = models.DecimalField(
        max_digits=15,
        decimal_places=10,
        null=True,
        blank=True,
        help_text="Geographic longitude of the device location"
    )

    # Arbitrary user-defined key/value metadata
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary key-value metadata for this device"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'SNMP Device'
        verbose_name_plural = 'SNMP Devices'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['ip_address']),
            models.Index(fields=['hostname']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['network', 'name']),
        ]
    
    def __str__(self):
        identifier = self.ip_address or self.hostname or 'no address'
        return f"{self.name} ({identifier})"
    
    def clean(self):
        """Require an address and validate IP/hostname format.

        Raises:
            ValidationError: If both address fields are empty or a field is malformed.
        """
        super().clean()

        # At least one of ip_address or hostname must be provided
        if not self.ip_address and not self.hostname:
            raise ValidationError(
                'At least one of IP address or hostname must be provided.'
            )

        # Validate IP address format when present
        if self.ip_address:
            try:
                ipaddress.ip_address(self.ip_address)
            except ValueError:
                # Not a valid IP address
                raise ValidationError({
                    'ip_address': 'Must be a valid IP address (e.g. 192.168.1.1 or 2001:db8::1)'
                })

        # Validate hostname format when present
        if self.hostname:
            if not self.hostname.replace('-', '').replace('.', '').replace('_', '').isalnum():
                raise ValidationError({
                    'hostname': 'Must be a valid hostname'
                })
    
    def save(self, *args, **kwargs):
        """Assign the official default template when unset, then `full_clean()` and persist."""
        # If no device template is assigned, use the Default template
        # (synced from official_device_templates/default.json as 'default')
        if not self.device_template_id:
            default_template = DeviceTemplate.objects.filter(
                name='default',
                official=True
            ).first()
            
            if default_template:
                self.device_template = default_template
            # If Default template doesn't exist, leave as None (will be handled by sync)
        
        self.full_clean()
        super().save(*args, **kwargs)


class Credential(models.Model):
    """SNMP v1, v2c, or v3 secret used to poll devices or receive traps.

    Community, auth, and privacy strings are Fernet-encrypted on save. Use
    `get_community`, `get_auth_pass`, and `get_priv_pass` to decrypt.
    """
    
    SNMP_VERSION_CHOICES = [
        ('1', 'SNMPv1'),
        ('2c', 'SNMPv2c'),
        ('3', 'SNMPv3'),
    ]
    
    AUTH_PROTOCOL_CHOICES = [
        ('md5', 'MD5'),
        ('sha', 'SHA'),
        ('sha2', 'SHA2'),
        ('hmac128sha224', 'HMAC128-SHA224'),
        ('hmac192sha256', 'HMAC192-SHA256'),
        ('hmac256sha384', 'HMAC256-SHA384'),
        ('hmac384sha512', 'HMAC384-SHA512'),
    ]
    
    PRIV_PROTOCOL_CHOICES = [
        ('des', 'DES'),
        ('3des', '3DES'),
        ('aes', 'AES'),
        ('aes128', 'AES128'),
        ('aes192', 'AES192'),
        ('aes256', 'AES256'),
        ('aes256with3desKey', 'AES256 with 3DES Key'),
    ]
    
    SECURITY_LEVEL_CHOICES = [
        ('noAuthNoPriv', 'No Authentication, No Privacy'),
        ('authNoPriv', 'Authentication, No Privacy'),
        ('authPriv', 'Authentication and Privacy'),
    ]
    
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Friendly name for this credential"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Optional description of this credential"
    )
    
    version = models.CharField(
        max_length=2,
        choices=SNMP_VERSION_CHOICES,
        default='2c',
        help_text="SNMP version (1, 2c, or 3)"
    )
    
    # SNMPv1/v2c fields
    community = models.CharField(
        max_length=255,
        blank=True,
        default='public',
        help_text="Community string for SNMPv1/v2c (default: public)"
    )
    
    # SNMPv3 fields
    security_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="SNMPv3 security name or user name"
    )
    
    security_level = models.CharField(
        max_length=20,
        choices=SECURITY_LEVEL_CHOICES,
        blank=True,
        help_text="SNMPv3 security level"
    )
    
    auth_protocol = models.CharField(
        max_length=20,
        choices=AUTH_PROTOCOL_CHOICES,
        blank=True,
        help_text="SNMPv3 authentication protocol"
    )
    
    auth_pass = models.CharField(
        max_length=255,
        blank=True,
        help_text="SNMPv3 authentication passphrase or password"
    )
    
    priv_protocol = models.CharField(
        max_length=20,
        choices=PRIV_PROTOCOL_CHOICES,
        blank=True,
        help_text="SNMPv3 privacy/encryption.py protocol"
    )
    
    priv_pass = models.CharField(
        max_length=255,
        blank=True,
        help_text="SNMPv3 encryption.py password"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'SNMP Credential'
        verbose_name_plural = 'SNMP Credentials'
    
    def __str__(self):
        return f"{self.name} (SNMPv{self.version})"
    
    def clean(self):
        """Enforce version-specific required fields and reject the other version's fields.

        Raises:
            ValidationError: If community/USM fields do not match `version` and `security_level`.
        """
        super().clean()
        
        if self.version in ['1', '2c']:
            # SNMPv1/v2c requires community string
            if not self.community:
                raise ValidationError({
                    'community': 'Community string is required for SNMPv1/v2c'
                })
            
            # Clear SNMPv3 fields if set
            if any([self.security_name, self.security_level, self.auth_protocol, 
                    self.auth_pass, self.priv_protocol, self.priv_pass]):
                raise ValidationError(
                    'SNMPv3 fields should not be set for SNMPv1/v2c credentials'
                )
        
        elif self.version == '3':
            # SNMPv3 requires security_name and security_level
            if not self.security_name:
                raise ValidationError({
                    'security_name': 'Security name is required for SNMPv3'
                })
            
            if not self.security_level:
                raise ValidationError({
                    'security_level': 'Security level is required for SNMPv3'
                })
            
            # Validate based on security level
            if self.security_level == 'noAuthNoPriv':
                # No auth or priv fields should be set
                if any([self.auth_protocol, self.auth_pass, self.priv_protocol, self.priv_pass]):
                    raise ValidationError(
                        'Authentication and privacy fields should not be set for noAuthNoPriv security level'
                    )
            
            elif self.security_level == 'authNoPriv':
                # Auth fields required, priv fields should not be set
                if not self.auth_protocol:
                    raise ValidationError({
                        'auth_protocol': 'Authentication protocol is required for authNoPriv security level'
                    })
                if not self.auth_pass:
                    raise ValidationError({
                        'auth_pass': 'Authentication password is required for authNoPriv security level'
                    })
                if self.priv_protocol or self.priv_pass:
                    raise ValidationError(
                        'Privacy fields should not be set for authNoPriv security level'
                    )
            
            elif self.security_level == 'authPriv':
                # Both auth and priv fields required
                if not self.auth_protocol:
                    raise ValidationError({
                        'auth_protocol': 'Authentication protocol is required for authPriv security level'
                    })
                if not self.auth_pass:
                    raise ValidationError({
                        'auth_pass': 'Authentication password is required for authPriv security level'
                    })
                if not self.priv_protocol:
                    raise ValidationError({
                        'priv_protocol': 'Privacy protocol is required for authPriv security level'
                    })
                if not self.priv_pass:
                    raise ValidationError({
                        'priv_pass': 'Privacy password is required for authPriv security level'
                    })
            
            # Clear community string for SNMPv3
            if self.community and self.community != 'public':
                raise ValidationError(
                    'Community string should not be set for SNMPv3 credentials'
                )
    
    def save(self, *args, **kwargs):
        """Validate, encrypt plaintext secrets that are not already Fernet tokens, then persist."""
        self.full_clean()
        
        # Encrypt sensitive fields before saving
        if self.community and not self._is_encrypted(self.community):
            self.community = encrypt_credential(self.community)
        if self.auth_pass and not self._is_encrypted(self.auth_pass):
            self.auth_pass = encrypt_credential(self.auth_pass)
        if self.priv_pass and not self._is_encrypted(self.priv_pass):
            self.priv_pass = encrypt_credential(self.priv_pass)
        
        super().save(*args, **kwargs)
    
    def _is_encrypted(self, value):
        """Return True if `value` looks like a Fernet token (prefix ``gAAAAA``)."""
        return value and value.startswith('gAAAAA')
    
    def get_community(self):
        """Return the decrypted v1/v2c community string, or None."""
        return decrypt_credential(self.community) if self.community else None
    
    def get_auth_pass(self):
        """Return the decrypted SNMPv3 auth password, or None."""
        return decrypt_credential(self.auth_pass) if self.auth_pass else None
    
    def get_priv_pass(self):
        """Return the decrypted SNMPv3 privacy password, or None."""
        return decrypt_credential(self.priv_pass) if self.priv_pass else None


class Profile(models.Model):
    """OID map (get/walk/table) plus normalizers applied by a device template.

    Official catalog rows set `official_key` from bundled JSON; user rows leave it
    null. Catalog JSON also lives under `SNMP/data/official_profiles/`.
    """
    
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique name for this profile (e.g., 'cisco_custom', 'my_switch_profile')"
    )
    
    profile_data = models.JSONField(
        help_text="JSON blob containing the profile configuration (OIDs, metrics, etc.)"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Optional description of what this profile is for"
    )
    
    vendor = models.CharField(
        max_length=100,
        help_text="Vendor or manufacturer this profile is designed for (e.g., Cisco, Generic, Any)"
    )
    
    product = models.CharField(
        max_length=100,
        blank=True,
        help_text="Product line or series (e.g., iDRAC, Catalyst, ASR)"
    )
    
    normalizers = models.JSONField(
        default=list,
        blank=True,
        help_text="List of normalizer configurations to apply to profile fields"
    )
    
    official_key = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the official JSON file (e.g. 'generic_interfaces'). Null for user-created profiles."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'SNMP Profile'
        verbose_name_plural = 'SNMP Profiles'
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """Require `profile_data` to be a JSON object when present.

        Raises:
            ValidationError: If `profile_data` is not a dict.
        """
        super().clean()
        
        if self.profile_data:
            # Ensure it's a dict
            if not isinstance(self.profile_data, dict):
                raise ValidationError({
                    'profile_data': 'Profile data must be a JSON object (dictionary)'
                })
            
            # Basic validation - could be expanded based on required profile structure
            # For now, just ensure it's valid JSON
    
    def save(self, *args, **kwargs):
        """Run `full_clean()` then persist the row."""
        self.full_clean()
        super().save(*args, **kwargs)


class DeviceTemplate(models.Model):
    """Named bundle of profiles with substring matching rules for auto-assignment.

    Official templates cannot be overwritten by AI import. Deleting a non-default
    template reassigns its devices to the official `default` template.
    """
    
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique name for this device template"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Optional description of what this template is for"
    )
    
    vendor = models.CharField(
        max_length=100,
        help_text="Vendor or manufacturer this template is designed for (e.g., Cisco, Juniper, Generic)"
    )
    
    model = models.CharField(
        max_length=100,
        blank=True,
        help_text="Specific model number (e.g., 9300, 1000)"
    )
    
    product = models.CharField(
        max_length=100,
        blank=True,
        help_text="Product line or series (e.g., iDRAC, Catalyst, ASR)"
    )
    
    type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Device type (e.g., Router, Switch, Server, Firewall)"
    )
    
    matching_rules = models.JSONField(
        default=list,
        blank=True,
        help_text="List of substrings to match against device sysDescr or other identifying fields for auto-assignment"
    )
    
    official = models.BooleanField(
        default=False,
        help_text="Whether this is an official/built-in template (official templates cannot be edited or deleted)"
    )
    
    official_key = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the official JSON file (e.g. 'dell_idrac'). Null for user-created templates."
    )
    
    profiles = models.ManyToManyField(
        'Profile',
        blank=True,
        related_name='device_templates',
        help_text="SNMP profiles to apply when this template is assigned to a device"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Device Template'
        verbose_name_plural = 'Device Templates'
    
    def __str__(self):
        return self.name
    
    def clean(self):
        """Require `matching_rules` to be a list of strings when set.

        Raises:
            ValidationError: If `matching_rules` is not a list of strings.
        """
        super().clean()
        
        # Validate matching_rules is a list
        if self.matching_rules is not None:
            if not isinstance(self.matching_rules, list):
                raise ValidationError({
                    'matching_rules': 'Matching rules must be a list of strings'
                })
            
            # Ensure all items in the list are strings
            if not all(isinstance(rule, str) for rule in self.matching_rules):
                raise ValidationError({
                    'matching_rules': 'All matching rules must be strings'
                })
    
    def save(self, *args, **kwargs):
        """Run `full_clean()` then persist the row."""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Reassign devices to the official default template, then delete.

        Raises:
            ValidationError: If this is the official `default` template.
        """
        # Prevent deletion of the Default template
        if self.name == 'default' and self.official:
            raise ValidationError("Cannot delete the Default template")

        # Get the Default template
        default_template = DeviceTemplate.objects.filter(
            name='default',
            official=True
        ).exclude(id=self.id).first()
        
        if default_template:
            # Reassign all devices using this template to Default
            self.devices.all().update(device_template=default_template)
        
        # Now safe to delete
        super().delete(*args, **kwargs)
    
    def matches_device(self, device_info):
        """Return True if any matching rule is a case-insensitive substring of `device_info`.

        Args:
            device_info: Device identification string (typically sysDescr).

        Returns:
            False when rules or `device_info` are empty; otherwise whether any rule matches.
        """
        if not self.matching_rules or not device_info:
            return False
        
        device_info_lower = device_info.lower()
        return any(rule.lower() in device_info_lower for rule in self.matching_rules)


class SNMPDeploymentState(models.Model):
    """Singleton timestamps used to cheaply detect undeployed SNMP config changes."""
    last_deployment = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Timestamp of last successful deployment"
    )
    last_config_change = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of last configuration change"
    )
    
    class Meta:
        db_table = 'snmp_deployment_state'
        verbose_name = 'SNMP Deployment State'
        verbose_name_plural = 'SNMP Deployment State'
    
    @classmethod
    def mark_config_changed(cls):
        """Stamp `last_config_change` after CRUD on networks, devices, credentials, templates, or profiles."""
        from django.utils import timezone
        state, _ = cls.objects.get_or_create(id=1)
        state.last_config_change = timezone.now()
        state.save(update_fields=['last_config_change'])
    
    @classmethod
    def has_undeployed_changes(cls):
        """Return True if config has changed since the last successful deploy.

        Never-deployed state is treated as dirty.

        Note:
            Change-then-revert can still look dirty (false positive). Opening the deploy
            diff with no actual pipeline changes clears the indicator.
        """
        state = cls.objects.filter(id=1).first()
        
        # Never deployed or no state
        if not state or not state.last_deployment:
            return True
        
        # Compare timestamps
        if not state.last_config_change:
            return False
        return state.last_config_change > state.last_deployment
    
    def __str__(self):
        if self.last_deployment:
            return f"Last deployed: {self.last_deployment}"
        return "Never deployed"

