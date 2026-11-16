#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""SNMP undeployed-changes indicator driven by the input fingerprint."""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from PipelineManager.models import Connection
from SNMP.deploy_fingerprint import compute_input_fingerprint
from SNMP.models import Credential, Device, DeviceTemplate, Network, Profile, SNMPDeploymentState


@pytest.fixture
def es_connection(db):
    return Connection.objects.create(
        name='es', connection_type='CENTRALIZED',
        host='https://localhost:9200', username='elastic', password='changeme',
    )


@pytest.fixture
def credential(db):
    return Credential.objects.create(name='v2c', version='2c', community='public')


@pytest.fixture
def template(db):
    profile = Profile.objects.create(
        name='cpu', vendor='Any', profile_data={'get': {'cpu': '1.3.6.1'}},
    )
    tpl = DeviceTemplate.objects.create(name='default', vendor='Any', official=True)
    tpl.profiles.add(profile)
    return tpl


@pytest.fixture
def network(es_connection, credential):
    return Network.objects.create(
        name='lab', network_range='10.0.0.0/24', connection=es_connection,
    )


@pytest.fixture
def device(network, credential, template):
    return Device.objects.create(
        name='sw1', ip_address='10.0.0.10', credential=credential,
        network=network, device_template=template,
    )


@pytest.fixture
def deployed(device):
    """State as if the current config had just been deployed."""
    SNMPDeploymentState.objects.all().delete()
    SNMPDeploymentState.mark_deployed(compute_input_fingerprint())


@pytest.mark.django_db
class TestFingerprint:
    def test_is_stable(self, device):
        assert compute_input_fingerprint() == compute_input_fingerprint()

    def test_change_then_revert_is_unchanged(self, device):
        before = compute_input_fingerprint()
        device.port = 1161
        device.save()
        assert compute_input_fingerprint() != before
        device.port = 161
        device.save()
        assert compute_input_fingerprint() == before

    def test_save_without_edits_is_unchanged(self, device, network):
        before = compute_input_fingerprint()
        device.save()
        network.save()
        assert compute_input_fingerprint() == before

    def test_same_secret_reentered_is_unchanged(self, device, credential):
        before = compute_input_fingerprint()
        old_ciphertext = credential.community
        credential.community = 'public'
        credential.save()
        assert credential.community != old_ciphertext
        assert compute_input_fingerprint() == before

    def test_new_secret_changes(self, device, credential):
        before = compute_input_fingerprint()
        credential.community = 'private'
        credential.save()
        assert compute_input_fingerprint() != before

    def test_es_password_reentered_is_unchanged(self, device, es_connection):
        before = compute_input_fingerprint()
        es_connection.password = 'changeme'
        es_connection.save()
        assert compute_input_fingerprint() == before

    def test_agent_check_in_is_ignored(self, device, es_connection):
        before = compute_input_fingerprint()
        Connection.objects.filter(pk=es_connection.pk).update(last_check_in=timezone.now())
        assert compute_input_fingerprint() == before

    def test_template_description_is_ignored(self, device, template):
        before = compute_input_fingerprint()
        template.description = 'notes only'
        template.matching_rules = ['cisco']
        template.save()
        assert compute_input_fingerprint() == before

    @pytest.mark.parametrize('change', [
        lambda d: Device.objects.create(
            name='sw2', ip_address='10.0.0.11', credential=d.credential,
            network=d.network, device_template=d.device_template,
        ),
        lambda d: d.delete(),
        lambda d: d.device_template.profiles.clear(),
        lambda d: Profile.objects.filter(name='cpu').update(profile_data={'get': {}}),
        lambda d: Network.objects.filter(pk=d.network_id).update(interval=60),
        lambda d: Device.objects.filter(pk=d.pk).update(metadata={'rack': 'A1'}),
        lambda d: Connection.objects.filter(pk=d.network.connection_id).update(host='https://other:9200'),
    ], ids=['add-device', 'delete-device', 'template-profiles', 'profile-data',
            'network-interval', 'device-metadata', 'es-host'])
    def test_real_changes_are_detected(self, device, change):
        before = compute_input_fingerprint()
        change(device)
        assert compute_input_fingerprint() != before

    def test_upgrade_changes_it(self, device, settings):
        before = compute_input_fingerprint()
        settings.__VERSION__ = '99.0.0'
        assert compute_input_fingerprint() != before

    def test_official_profile_file_edit_changes_it(self, device, settings, tmp_path):
        profiles = tmp_path / 'SNMP' / 'data' / 'official_profiles'
        profiles.mkdir(parents=True)
        (profiles / 'generic_system.json').write_text('{"get": {}}')
        settings.BASE_DIR = tmp_path
        before = compute_input_fingerprint()
        (profiles / 'generic_system.json').write_text('{"get": {"uptime": "1.3.6.1.2.1.1.3.0"}}')
        assert compute_input_fingerprint() != before

    def test_unreferenced_connection_is_ignored(self, device):
        before = compute_input_fingerprint()
        Connection.objects.create(
            name='unused', connection_type='CENTRALIZED',
            host='https://x:9200', username='elastic', password='changeme',
        )
        assert compute_input_fingerprint() == before


@pytest.mark.django_db
class TestHasUndeployedChanges:
    def test_clean_right_after_deploy(self, deployed):
        assert SNMPDeploymentState.has_undeployed_changes() is False

    def test_change_then_revert_stays_clean(self, deployed, device):
        device.timeout = 5000
        device.save()
        SNMPDeploymentState.mark_config_changed()
        assert SNMPDeploymentState.has_undeployed_changes() is True

        device.timeout = 1000
        device.save()
        SNMPDeploymentState.mark_config_changed()
        assert SNMPDeploymentState.has_undeployed_changes() is False

    def test_write_that_skips_mark_config_changed_is_still_seen(self, deployed, device):
        Device.objects.filter(pk=device.pk).update(retries=9)
        assert SNMPDeploymentState.has_undeployed_changes() is True

    def test_never_deployed_is_dirty(self, device):
        SNMPDeploymentState.objects.all().delete()
        assert SNMPDeploymentState.has_undeployed_changes() is True

    def test_falls_back_to_timestamps_before_first_fingerprint(self, device):
        SNMPDeploymentState.objects.all().delete()
        now = timezone.now()
        SNMPDeploymentState.objects.create(id=1, last_deployment=now, last_config_change=now)
        assert SNMPDeploymentState.has_undeployed_changes() is False

        SNMPDeploymentState.mark_config_changed()
        assert SNMPDeploymentState.has_undeployed_changes() is True


@pytest.mark.django_db
class TestDeployStamping:
    """GetDeployDiff / DeployConfiguration record the plan-time fingerprint."""

    DIFF_URL = '/SNMP/GetDeployDiff/'
    DEPLOY_URL = '/SNMP/DeployConfiguration/'

    @pytest.fixture(autouse=True)
    def _clear_plan(self):
        cache.delete('snmp_deployment_plan')
        yield
        cache.delete('snmp_deployment_plan')

    def test_empty_diff_records_current_config(self, authenticated_client, device):
        SNMPDeploymentState.objects.all().delete()
        SNMPDeploymentState.mark_deployed('stale')
        assert SNMPDeploymentState.has_undeployed_changes() is True

        with patch('SNMP.snmp_crud.get_elastic_connection') as es:
            es.return_value.logstash.get_pipeline.return_value = {}
            first = authenticated_client.post(self.DIFF_URL).json()
            assert first['has_changes'] is True

            # The cluster now holds exactly what would be generated.
            es.return_value.logstash.get_pipeline.return_value = {
                d['pipeline_name']: {'pipeline': d['new']} for d in first['networks']
            }
            second = authenticated_client.post(self.DIFF_URL).json()

        assert second['has_changes'] is False
        state = SNMPDeploymentState.objects.get(id=1)
        assert state.deployed_fingerprint == compute_input_fingerprint()
        assert SNMPDeploymentState.has_undeployed_changes() is False

    def test_diff_caches_plan_with_fingerprint(self, authenticated_client, device):
        with patch('SNMP.snmp_crud.get_elastic_connection') as es:
            es.return_value.logstash.get_pipeline.return_value = {}
            authenticated_client.post(self.DIFF_URL)

        plan = cache.get('snmp_deployment_plan')
        assert plan['fingerprint'] == compute_input_fingerprint()
        assert isinstance(plan['diffs'], list)

    def test_successful_deploy_records_plan_time_fingerprint(self, authenticated_client, device):
        plan_fp = compute_input_fingerprint()
        cache.set('snmp_deployment_plan', {
            'fingerprint': plan_fp,
            'diffs': [{
                'network_name': 'lab', 'pipeline_name': 'snmp-lab-default-polling',
                'action': 'create', 'new': 'input {}', 'connection_id': device.network.connection_id,
            }],
        }, timeout=60)

        with patch('SNMP.snmp_crud.get_elastic_connection'), \
                patch('SNMP.snmp_crud._create_or_update_pipeline', return_value=(True, True, None, False)):
            response = authenticated_client.post(self.DEPLOY_URL)

        assert response.json()['success'] is True
        assert SNMPDeploymentState.objects.get(id=1).deployed_fingerprint == plan_fp
        assert SNMPDeploymentState.has_undeployed_changes() is False

    def test_edit_during_deploy_stays_pending(self, authenticated_client, device):
        plan_fp = compute_input_fingerprint()
        cache.set('snmp_deployment_plan', {
            'fingerprint': plan_fp,
            'diffs': [{
                'network_name': 'lab', 'pipeline_name': 'snmp-lab-default-polling',
                'action': 'create', 'new': 'input {}', 'connection_id': device.network.connection_id,
            }],
        }, timeout=60)
        # Someone edits a device after the diff was taken.
        Device.objects.filter(pk=device.pk).update(port=1161)

        with patch('SNMP.snmp_crud.get_elastic_connection'), \
                patch('SNMP.snmp_crud._create_or_update_pipeline', return_value=(True, True, None, False)):
            authenticated_client.post(self.DEPLOY_URL)

        assert SNMPDeploymentState.has_undeployed_changes() is True

    def test_failed_deploy_stays_pending(self, authenticated_client, device):
        SNMPDeploymentState.objects.all().delete()
        SNMPDeploymentState.mark_deployed('previous-deploy')
        cache.set('snmp_deployment_plan', {
            'fingerprint': compute_input_fingerprint(),
            'diffs': [{
                'network_name': 'lab', 'pipeline_name': 'bad', 'action': 'create',
                'new': 'input {}', 'connection_id': device.network.connection_id,
            }],
        }, timeout=60)

        with patch('SNMP.snmp_crud.get_elastic_connection'), \
                patch('SNMP.snmp_crud._create_or_update_pipeline', return_value=(False, False, 'boom', False)):
            response = authenticated_client.post(self.DEPLOY_URL)

        assert response.status_code == 500
        assert SNMPDeploymentState.objects.get(id=1).deployed_fingerprint == 'previous-deploy'
        assert SNMPDeploymentState.has_undeployed_changes() is True
