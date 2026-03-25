from django.db import models
from django.core.exceptions import ValidationError
from Common.encryption import encrypt_credential, decrypt_credential
import ipaddress


class Credential(models.Model):

    PROTOCOL_CHOICES = [
        ('restconf', 'RESTCONF'),
        ('netconf', 'NETCONF'),
        ('rest', 'Vendor REST API'),
    ]

    AUTH_TYPE_CHOICES = [
        ('basic', 'HTTP Basic Auth'),
        ('token', 'Bearer Token'),
        ('api_key', 'API Key'),
        ('certificate', 'Client Certificate'),
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

    protocol = models.CharField(
        max_length=20,
        choices=PROTOCOL_CHOICES,
        default='restconf',
        help_text="Protocol this credential is used with"
    )

    auth_type = models.CharField(
        max_length=20,
        choices=AUTH_TYPE_CHOICES,
        default='basic',
        help_text="Authentication type"
    )

    # Basic Auth / NETCONF
    username = models.CharField(max_length=255, blank=True)
    password = models.CharField(max_length=512, blank=True)   # stored encrypted

    # Bearer Token / API Key
    token = models.CharField(max_length=2048, blank=True)     # stored encrypted

    # API Key header name (e.g. "X-API-Key")
    api_key_header = models.CharField(max_length=100, blank=True, default='X-API-Key')

    # TLS
    verify_ssl = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Network Credential'
        verbose_name_plural = 'Network Credentials'

    def __str__(self):
        return f"{self.name} ({self.get_protocol_display()} / {self.get_auth_type_display()})"

    def _is_encrypted(self, value):
        return value and value.startswith('gAAAAA')

    def clean(self):
        super().clean()
        if self.auth_type == 'basic' and self.protocol == 'netconf':
            if not self.username:
                raise ValidationError({'username': 'Username is required for Basic Auth / NETCONF'})
        if self.auth_type in ('token', 'api_key') and not self.token:
            raise ValidationError({'token': 'Token/key value is required'})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.password and not self._is_encrypted(self.password):
            self.password = encrypt_credential(self.password)
        if self.token and not self._is_encrypted(self.token):
            self.token = encrypt_credential(self.token)
        super().save(*args, **kwargs)

    def get_password(self):
        return decrypt_credential(self.password) if self.password else None

    def get_token(self):
        return decrypt_credential(self.token) if self.token else None


class Profile(models.Model):

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique name for this profile"
    )

    description = models.TextField(
        blank=True,
        help_text="Optional description"
    )

    vendor = models.CharField(
        max_length=100,
        blank=True,
        help_text="Vendor this profile targets (e.g. Cisco, Juniper, Generic)"
    )

    type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Category: Router, Switch, Firewall, etc."
    )

    # JSON blob: list of YANG paths / REST endpoints / NETCONF filters to collect
    profile_data = models.JSONField(
        help_text="JSON object describing data collection paths (YANG, REST, NETCONF filter)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Network Config Profile'
        verbose_name_plural = 'Network Config Profiles'

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.profile_data and not isinstance(self.profile_data, dict):
            raise ValidationError({'profile_data': 'Profile data must be a JSON object (dictionary)'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Device(models.Model):

    VENDOR_CHOICES = [
        ('cisco_ios', 'Cisco IOS/IOS-XE'),
        ('cisco_nxos', 'Cisco NX-OS'),
        ('cisco_iosxr', 'Cisco IOS-XR'),
        ('juniper', 'Juniper Junos'),
        ('arista', 'Arista EOS'),
        ('paloalto', 'Palo Alto'),
        ('fortinet', 'Fortinet FortiOS'),
        ('generic', 'Generic'),
    ]

    STATUS_CHOICES = [
        ('unknown', 'Unknown'),
        ('reachable', 'Reachable'),
        ('unreachable', 'Unreachable'),
        ('error', 'Error'),
    ]

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Friendly name for this device"
    )

    description = models.TextField(blank=True)

    vendor = models.CharField(
        max_length=50,
        choices=VENDOR_CHOICES,
        default='generic'
    )

    hostname = models.CharField(
        max_length=255,
        help_text="IP address or hostname of the device"
    )

    rest_port = models.PositiveIntegerField(
        default=443,
        help_text="Port for REST/RESTCONF (default: 443)"
    )

    netconf_port = models.PositiveIntegerField(
        default=830,
        help_text="Port for NETCONF SSH (default: 830)"
    )

    credential = models.ForeignKey(
        'Credential',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='devices',
        help_text="Credential to use for this device"
    )

    profile = models.ForeignKey(
        'Profile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='devices',
        help_text="Configuration profile to apply to this device"
    )

    use_restconf = models.BooleanField(default=True)
    use_netconf = models.BooleanField(default=False)

    last_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='unknown'
    )
    last_checked = models.DateTimeField(null=True, blank=True)
    last_status_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Network Device'
        verbose_name_plural = 'Network Devices'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['hostname']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['last_status']),
        ]

    def __str__(self):
        return f"{self.name} ({self.hostname})"

    def clean(self):
        super().clean()
        if self.hostname:
            try:
                ipaddress.ip_address(self.hostname)
            except ValueError:
                if not self.hostname.replace('-', '').replace('.', '').replace('_', '').isalnum():
                    raise ValidationError({'hostname': 'Must be a valid IP address or hostname'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
