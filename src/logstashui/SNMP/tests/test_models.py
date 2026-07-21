#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from SNMP.models import (
    Credential, Device, DeviceTemplate, Network, Profile, SNMPDeploymentState
)
from PipelineManager.models import Connection


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_connection(db):
    return Connection.objects.create(
        name='Test Connection',
        connection_type='CENTRALIZED',
        host='https://localhost:9200',
        username='elastic',
        password='changeme',
    )


@pytest.fixture
def test_credential_v2c(db):
    return Credential.objects.create(
        name='Cred v2c',
        version='2c',
        community='public',
    )


@pytest.fixture
def test_network(db, test_connection, test_credential_v2c):
    return Network.objects.create(
        name='Net',
        network_range='10.0.0.0/8',
        connection=test_connection,
    )


@pytest.fixture
def default_template(db):
    return DeviceTemplate.objects.create(
        name='default',
        vendor='Any',
        official=True,
    )


# ===========================================================================
# SNMPDeploymentState
# ===========================================================================

@pytest.mark.django_db
class TestSNMPDeploymentState:

    def test_mark_config_changed_creates_state(self):
        """mark_config_changed creates the singleton row when it doesn't exist."""
        SNMPDeploymentState.objects.all().delete()
        SNMPDeploymentState.mark_config_changed()
        state = SNMPDeploymentState.objects.get(id=1)
        assert state.last_config_change is not None

    def test_mark_config_changed_updates_timestamp(self):
        """Successive calls to mark_config_changed advance the timestamp."""
        SNMPDeploymentState.objects.all().delete()
        SNMPDeploymentState.mark_config_changed()
        first = SNMPDeploymentState.objects.get(id=1).last_config_change
        SNMPDeploymentState.mark_config_changed()
        second = SNMPDeploymentState.objects.get(id=1).last_config_change
        assert second >= first

    def test_has_undeployed_changes_no_state(self):
        """has_undeployed_changes returns True when no row exists (never deployed)."""
        SNMPDeploymentState.objects.all().delete()
        assert SNMPDeploymentState.has_undeployed_changes() is True

    def test_has_undeployed_changes_no_deployment(self):
        """has_undeployed_changes is True when config changed but never deployed."""
        SNMPDeploymentState.objects.all().delete()
        SNMPDeploymentState.mark_config_changed()
        assert SNMPDeploymentState.has_undeployed_changes() is True

    def test_has_undeployed_changes_after_sync(self):
        """has_undeployed_changes is False when last_deployment >= last_config_change."""
        SNMPDeploymentState.objects.all().delete()
        now = timezone.now()
        SNMPDeploymentState.objects.create(
            id=1,
            last_config_change=now,
            last_deployment=now,
        )
        assert SNMPDeploymentState.has_undeployed_changes() is False

    def test_has_undeployed_changes_after_new_change(self):
        """has_undeployed_changes is True again when config changes after deployment."""
        from datetime import timedelta
        SNMPDeploymentState.objects.all().delete()
        # Seed the state with timestamps 60 seconds in the past so mark_config_changed
        # will produce a strictly later timestamp.
        past = timezone.now() - timedelta(seconds=60)
        SNMPDeploymentState.objects.create(
            id=1,
            last_config_change=past,
            last_deployment=past,
        )
        SNMPDeploymentState.mark_config_changed()
        assert SNMPDeploymentState.has_undeployed_changes() is True

    def test_str_never_deployed(self):
        """__str__ returns 'Never deployed' when last_deployment is None."""
        SNMPDeploymentState.objects.all().delete()
        state = SNMPDeploymentState.objects.create(id=1)
        assert str(state) == 'Never deployed'

    def test_str_with_deployment(self):
        """__str__ includes the timestamp when last_deployment is set."""
        SNMPDeploymentState.objects.all().delete()
        now = timezone.now()
        state = SNMPDeploymentState.objects.create(id=1, last_deployment=now)
        assert 'Last deployed' in str(state)


# ===========================================================================
# DeviceTemplate.matches_device
# ===========================================================================

@pytest.mark.django_db
class TestDeviceTemplateMatchesDevice:

    def test_matches_with_all_rules(self):
        """matches_device returns True when all rules appear in device_info."""
        tmpl = DeviceTemplate.objects.create(
            name='cisco_switch',
            vendor='Cisco',
            matching_rules=['cisco', 'catalyst'],
        )
        assert tmpl.matches_device('Cisco Catalyst 9300 switch') is True

    def test_no_match_when_rule_absent(self):
        """matches_device returns False when a rule is not found."""
        tmpl = DeviceTemplate.objects.create(
            name='cisco_switch2',
            vendor='Cisco',
            matching_rules=['cisco', 'catalyst'],
        )
        assert tmpl.matches_device('Juniper EX2300') is False

    def test_case_insensitive(self):
        """matches_device is case-insensitive."""
        tmpl = DeviceTemplate.objects.create(
            name='cisco_switch3',
            vendor='Cisco',
            matching_rules=['CISCO'],
        )
        assert tmpl.matches_device('cisco ios') is True

    def test_empty_matching_rules(self):
        """matches_device returns False when matching_rules is empty."""
        tmpl = DeviceTemplate.objects.create(
            name='generic_tmpl',
            vendor='Generic',
            matching_rules=[],
        )
        assert tmpl.matches_device('anything') is False

    def test_empty_device_info(self):
        """matches_device returns False when device_info is empty/None."""
        tmpl = DeviceTemplate.objects.create(
            name='cisco_switch4',
            vendor='Cisco',
            matching_rules=['cisco'],
        )
        assert tmpl.matches_device('') is False
        assert tmpl.matches_device(None) is False

    def test_partial_substring_match(self):
        """A single matching rule appearing in a longer string is sufficient."""
        tmpl = DeviceTemplate.objects.create(
            name='dell_idrac',
            vendor='Dell',
            matching_rules=['idrac'],
        )
        assert tmpl.matches_device('Dell iDRAC 9 server') is True


# ===========================================================================
# DeviceTemplate.clean – matching_rules validation
# ===========================================================================

@pytest.mark.django_db
class TestDeviceTemplateClean:

    def test_matching_rules_must_be_list(self):
        """matching_rules must be a list; a dict raises ValidationError."""
        with pytest.raises(ValidationError):
            DeviceTemplate.objects.create(
                name='bad_rules_dict',
                vendor='Any',
                matching_rules={'key': 'value'},
            )

    def test_matching_rules_items_must_be_strings(self):
        """Each item in matching_rules must be a string."""
        with pytest.raises(ValidationError):
            DeviceTemplate.objects.create(
                name='bad_rules_int',
                vendor='Any',
                matching_rules=[1, 2, 3],
            )

    def test_empty_matching_rules_valid(self):
        """An empty list is a valid matching_rules value."""
        tmpl = DeviceTemplate.objects.create(
            name='empty_rules_ok',
            vendor='Any',
            matching_rules=[],
        )
        assert tmpl.id is not None


# ===========================================================================
# Credential – decryption helpers
# ===========================================================================

@pytest.mark.django_db
class TestCredentialDecryption:

    def test_get_community_returns_plaintext(self):
        """get_community() decrypts and returns the community string."""
        cred = Credential.objects.create(
            name='comm_test',
            version='2c',
            community='secret_community',
        )
        cred.refresh_from_db()
        assert cred.get_community() == 'secret_community'

    def test_get_community_none_when_blank(self):
        """get_community() returns None when community is blank."""
        cred = Credential.objects.create(
            name='comm_blank',
            version='2c',
            community='placeholder',  # must pass model clean
        )
        # Manually blank out after creation to avoid validation
        Credential.objects.filter(pk=cred.pk).update(community='')
        cred.refresh_from_db()
        assert cred.get_community() is None

    def test_get_auth_pass_returns_plaintext(self):
        """get_auth_pass() decrypts and returns the auth passphrase."""
        cred = Credential.objects.create(
            name='auth_test',
            version='3',
            security_name='user1',
            security_level='authPriv',
            auth_protocol='sha',
            auth_pass='authsecret',
            priv_protocol='aes',
            priv_pass='privsecret',
        )
        cred.refresh_from_db()
        assert cred.get_auth_pass() == 'authsecret'

    def test_get_priv_pass_returns_plaintext(self):
        """get_priv_pass() decrypts and returns the priv passphrase."""
        cred = Credential.objects.create(
            name='priv_test',
            version='3',
            security_name='user2',
            security_level='authPriv',
            auth_protocol='sha',
            auth_pass='authsecret2',
            priv_protocol='aes',
            priv_pass='privsecret2',
        )
        cred.refresh_from_db()
        assert cred.get_priv_pass() == 'privsecret2'

    def test_get_auth_pass_none_when_blank(self):
        """get_auth_pass() returns None when auth_pass is blank."""
        cred = Credential.objects.create(
            name='no_auth_pass',
            version='3',
            security_name='user3',
            security_level='noAuthNoPriv',
        )
        cred.refresh_from_db()
        assert cred.get_auth_pass() is None

    def test_double_save_does_not_double_encrypt(self):
        """Saving a credential twice does not encrypt an already-encrypted value."""
        cred = Credential.objects.create(
            name='double_save_test',
            version='2c',
            community='test_community',
        )
        cred.refresh_from_db()
        first_community = cred.community  # encrypted token
        cred.description = 'Updated'
        cred.save()
        cred.refresh_from_db()
        assert cred.community == first_community
        assert cred.get_community() == 'test_community'


# ===========================================================================
# Credential.clean – SNMP version validation
# ===========================================================================

@pytest.mark.django_db
class TestCredentialClean:

    def test_v2c_requires_community(self):
        """v2c credential requires a community string."""
        with pytest.raises(ValidationError):
            cred = Credential(name='no_comm', version='2c', community='')
            cred.full_clean()

    def test_v3_noauthnopriv_rejects_auth_fields(self):
        """noAuthNoPriv should not have auth/priv fields set."""
        with pytest.raises(ValidationError):
            Credential.objects.create(
                name='bad_noauth',
                version='3',
                security_name='user',
                security_level='noAuthNoPriv',
                auth_protocol='sha',
                auth_pass='pass',
            )

    def test_v3_authnopriv_requires_auth_protocol(self):
        """authNoPriv requires auth_protocol."""
        with pytest.raises(ValidationError):
            Credential.objects.create(
                name='bad_authnopriv',
                version='3',
                security_name='user',
                security_level='authNoPriv',
                auth_protocol='',
                auth_pass='pass',
            )

    def test_v3_authnopriv_rejects_priv_fields(self):
        """authNoPriv must not have priv fields set."""
        with pytest.raises(ValidationError):
            Credential.objects.create(
                name='bad_priv',
                version='3',
                security_name='user',
                security_level='authNoPriv',
                auth_protocol='sha',
                auth_pass='pass',
                priv_protocol='aes',
            )

    def test_v3_authpriv_requires_all_fields(self):
        """authPriv requires both auth and priv protocol/pass."""
        with pytest.raises(ValidationError):
            Credential.objects.create(
                name='bad_authpriv',
                version='3',
                security_name='user',
                security_level='authPriv',
                auth_protocol='sha',
                auth_pass='pass',
                priv_protocol='aes',
                priv_pass='',  # missing
            )


# ===========================================================================
# Network.clean – CIDR validation
# ===========================================================================

@pytest.mark.django_db
class TestNetworkClean:

    def test_valid_cidr_saves(self, test_connection):
        """A valid CIDR network range saves without error."""
        net = Network.objects.create(
            name='valid_net',
            network_range='192.168.0.0/16',
            connection=test_connection,
        )
        assert net.id is not None

    def test_invalid_cidr_raises_validation_error(self, test_connection):
        """An invalid CIDR raises ValidationError on save."""
        with pytest.raises(ValidationError):
            Network.objects.create(
                name='invalid_net',
                network_range='not-a-cidr',
                connection=test_connection,
            )

    def test_host_cidr_accepted_non_strict(self, test_connection):
        """Non-strict CIDR (host bits set) is accepted by the model."""
        net = Network.objects.create(
            name='host_cidr',
            network_range='192.168.1.1/24',
            connection=test_connection,
        )
        assert net.id is not None


# ===========================================================================
# Device.clean – validation
# ===========================================================================

@pytest.mark.django_db
class TestDeviceClean:

    def test_device_requires_ip_or_hostname(self, test_credential_v2c, test_network):
        """Device.clean raises ValidationError if neither ip_address nor hostname is set."""
        with pytest.raises(ValidationError):
            Device.objects.create(
                name='no_addr',
                ip_address=None,
                hostname=None,
                credential=test_credential_v2c,
                network=test_network,
            )

    def test_device_invalid_ip_raises(self, test_credential_v2c, test_network):
        """Device.clean raises ValidationError for an invalid IP address."""
        with pytest.raises(ValidationError):
            Device.objects.create(
                name='bad_ip',
                ip_address='999.999.999.999',
                credential=test_credential_v2c,
                network=test_network,
            )

    def test_device_valid_hostname_only(self, test_credential_v2c, test_network):
        """A device with only a hostname (no IP) is valid."""
        device = Device.objects.create(
            name='hostname_only_dev',
            hostname='mydevice.example.com',
            ip_address=None,
            credential=test_credential_v2c,
            network=test_network,
        )
        assert device.id is not None

    def test_device_str_uses_ip(self, test_credential_v2c, test_network):
        """Device.__str__ uses the IP address when present."""
        device = Device.objects.create(
            name='str_test',
            ip_address='10.0.0.1',
            credential=test_credential_v2c,
            network=test_network,
        )
        assert '10.0.0.1' in str(device)

    def test_device_str_fallback_no_address(self, test_credential_v2c, test_network):
        """Device.__str__ falls back to 'no address' when both ip/hostname are None after object construction."""
        # Bypass model validation by using update() to set both to None
        device = Device.objects.create(
            name='str_no_addr',
            ip_address='1.2.3.4',
            credential=test_credential_v2c,
            network=test_network,
        )
        Device.objects.filter(pk=device.pk).update(ip_address=None, hostname=None)
        device.refresh_from_db()
        assert 'no address' in str(device)


# ===========================================================================
# Profile.clean – validation
# ===========================================================================

@pytest.mark.django_db
class TestProfileClean:

    def test_profile_data_must_be_dict(self):
        """Profile.clean raises ValidationError when profile_data is not a dict."""
        with pytest.raises(ValidationError):
            p = Profile(name='bad_profile', vendor='Generic', profile_data='not a dict')
            p.full_clean()

    def test_valid_profile_saves(self):
        """A profile with valid dict profile_data saves successfully."""
        p = Profile.objects.create(
            name='ok_profile',
            vendor='Generic',
            profile_data={'get': {'sysDescr': '1.3.6.1.2.1.1.1.0'}},
        )
        assert p.id is not None
