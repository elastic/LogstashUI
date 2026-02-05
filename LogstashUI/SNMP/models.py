from django.db import models
from django.core.exceptions import ValidationError
from Core.encryption import encrypt_credential, decrypt_credential
import ipaddress


class Network(models.Model):
    """
    SNMP Network model for defining networks to monitor
    """
    
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Friendly name for this network"
    )
    
    network_range = models.CharField(
        max_length=50,
        help_text="Network in CIDR notation (e.g., 192.168.1.0/24)"
    )
    
    logstash_name = models.CharField(
        max_length=255,
        help_text="Name of the Logstash node that will monitor this network"
    )
    
    discovery_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic device discovery on this network"
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
        """
        Validate network_range is a valid CIDR notation
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
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_network_info(self):
        """
        Get network information as a dictionary
        """
        try:
            network = ipaddress.ip_network(self.network_range, strict=False)
            return {
                'network_address': str(network.network_address),
                'broadcast_address': str(network.broadcast_address),
                'netmask': str(network.netmask),
                'num_addresses': network.num_addresses,
                'hosts': network.num_addresses - 2 if network.num_addresses > 2 else 0
            }
        except ValueError:
            return {}


class Credential(models.Model):
    """
    SNMP Credential model supporting SNMPv1, v2c, and v3
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
        help_text="SNMPv3 privacy/encryption protocol"
    )
    
    priv_pass = models.CharField(
        max_length=255,
        blank=True,
        help_text="SNMPv3 encryption password"
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
        """
        Validate credential fields based on SNMP version
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
        """Check if a value is already encrypted (Fernet tokens start with 'gAAAAA')"""
        return value and value.startswith('gAAAAA')
    
    def get_community(self):
        """Get decrypted community string"""
        return decrypt_credential(self.community) if self.community else None
    
    def get_auth_pass(self):
        """Get decrypted auth password"""
        return decrypt_credential(self.auth_pass) if self.auth_pass else None
    
    def get_priv_pass(self):
        """Get decrypted priv password"""
        return decrypt_credential(self.priv_pass) if self.priv_pass else None
    
    def to_logstash_config(self):
        """
        Generate Logstash SNMP input configuration for this credential
        Returns a dict of configuration parameters
        """
        config = {
            'version': self.version
        }
        
        if self.version in ['1', '2c']:
            config['community'] = self.community
        
        elif self.version == '3':
            config['security_name'] = self.security_name
            config['security_level'] = self.security_level
            
            if self.security_level in ['authNoPriv', 'authPriv']:
                config['auth_protocol'] = self.auth_protocol
                config['auth_pass'] = self.auth_pass
            
            if self.security_level == 'authPriv':
                config['priv_protocol'] = self.priv_protocol
                config['priv_pass'] = self.priv_pass
        
        return config
