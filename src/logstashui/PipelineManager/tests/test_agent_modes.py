#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import base64
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from PipelineManager.agent_modes import (
    build_policy_config,
    ensure_embedded_connection,
    list_simulation_targets,
    next_simulate_instance_id,
    simulate_paths,
    simulate_ports,
)
from PipelineManager.models import Connection, EnrollmentToken, Policy


@pytest.fixture
def admin_client(db):
    User = get_user_model()
    user = User.objects.create_superuser('admin', 'admin@example.com', 'pass')
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def system_policies(db):
    defaults = dict(
        logstash_yml='api.http.port: 9600\n',
        jvm_options='-Xms1g\n-Xmx1g\n',
        log4j2_properties='x=1\n',
        keystore_env_file='/etc/default/logstash',
        is_system=True,
    )
    default, _ = Policy.objects.get_or_create(
        name='Default Policy',
        defaults={**defaults, 'policy_type': Policy.PolicyType.DEFAULT},
    )
    default.policy_type = Policy.PolicyType.DEFAULT
    default.is_system = True
    default.save()

    simulate, _ = Policy.objects.get_or_create(
        name='Simulate Policy',
        defaults={
            **defaults,
            'policy_type': Policy.PolicyType.SIMULATE,
            'logstash_yml': 'api.http.port: 9560\n',
            'logstash_source': Policy.LogstashSource.SYSTEM,
        },
    )
    simulate.policy_type = Policy.PolicyType.SIMULATE
    simulate.is_system = True
    simulate.logstash_yml = 'api.http.port: 9560\n'
    simulate.save()

    embedded, _ = Policy.objects.get_or_create(
        name='Embedded Policy',
        defaults={
            **defaults,
            'policy_type': Policy.PolicyType.EMBEDDED,
            'logstash_yml': 'api.http.port: 9560\n',
            'agent_api_port': 9500,
            'logstash_api_port': 9560,
        },
    )
    embedded.policy_type = Policy.PolicyType.EMBEDDED
    embedded.is_system = True
    embedded.agent_api_port = 9500
    embedded.logstash_api_port = 9560
    embedded.save()
    return default, simulate, embedded


def test_simulate_ports_formula():
    assert simulate_ports(1) == (9501, 9561)
    assert simulate_ports(2) == (9502, 9562)


def test_simulate_paths():
    p = simulate_paths(1)
    assert p['settings_path'] == '/opt/logstash-agent/simulate-1/settings'
    assert p['keystore_env_file'] == '/opt/logstash-agent/simulate-1/env'


def test_next_instance_id_skips_used(db, system_policies):
    _, simulate, _ = system_policies
    Connection.objects.create(
        name='a',
        connection_type='AGENT',
        host='h1',
        agent_id='id1',
        policy=simulate,
        instance_id=1,
        agent_api_port=9501,
        logstash_api_port=9561,
    )
    assert next_simulate_instance_id() == 2


def test_build_policy_config_simulate(system_policies):
    _, simulate, _ = system_policies
    cfg = build_policy_config(simulate, instance_id=1)
    assert cfg['policy_type'] == 'SIMULATE'
    assert cfg['instance_id'] == 1
    assert cfg['agent_api_port'] == 9501
    assert cfg['logstash_api_port'] == 9561
    assert 'api.http.port: 9561' in cfg['logstash_yml']
    assert cfg['logstash_unit'] == 'ls-simulate@1'


def test_enroll_simulate_allocates_instance(db, system_policies):
    _, simulate, _ = system_policies
    token, _ = EnrollmentToken.objects.get_or_create(
        policy=simulate,
        name='default',
        defaults={'token': 'sim-token-abc'},
    )
    token.token = 'sim-token-abc'
    token.save()
    payload = base64.b64encode(
        json.dumps({'enrollment_token': token.token}).encode()
    ).decode()
    client = Client()
    resp = client.post(
        '/ConnectionManager/Enroll/',
        data=json.dumps(
            {
                'enrollment_token': payload,
                'host': 'simhost.example',
                'agent_id': 'agent-sim-1',
            }
        ),
        content_type='application/json',
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body['success'] is True
    assert body['policy_config']['instance_id'] == 1
    assert body['policy_config']['agent_api_port'] == 9501
    conn = Connection.objects.get(agent_id='agent-sim-1')
    assert conn.instance_id == 1
    assert conn.agent_api_port == 9501


def test_enroll_embedded_rejected(db, system_policies):
    _, _, embedded = system_policies
    token, _ = EnrollmentToken.objects.get_or_create(
        policy=embedded,
        name='default',
        defaults={'token': 'emb-token'},
    )
    token.token = 'emb-token'
    token.save()
    payload = base64.b64encode(
        json.dumps({'enrollment_token': token.token}).encode()
    ).decode()
    client = Client()
    resp = client.post(
        '/ConnectionManager/Enroll/',
        data=json.dumps(
            {
                'enrollment_token': payload,
                'host': 'host',
                'agent_id': 'agent-e',
            }
        ),
        content_type='application/json',
    )
    assert resp.status_code == 400
    assert 'Embedded' in resp.json()['error']


def test_list_simulation_targets(db, system_policies):
    _, simulate, embedded = system_policies
    Connection.objects.create(
        name='sim1',
        connection_type='AGENT',
        host='10.0.0.5',
        agent_id='s1',
        policy=simulate,
        instance_id=1,
        agent_api_port=9501,
        logstash_api_port=9561,
        logstash_version_resolved='9.4.3',
        is_active=True,
    )
    Connection.objects.create(
        name='embedded',
        connection_type='AGENT',
        host='nginx',
        agent_id='emb',
        policy=embedded,
        agent_api_port=9500,
        logstash_api_port=9560,
        is_active=True,
    )
    # ensure_embedded=False: only the two rows we created (no extra pseudo conn)
    targets = list_simulation_targets(ensure_embedded=False)
    assert len(targets) == 2
    labels = {t['label'] for t in targets}
    assert any('simulate-1' in lb and '9.4.3' in lb for lb in labels)
    assert any('embedded' in lb for lb in labels)
    # Default ensure_embedded also lists the docker pseudo-connection if missing
    with_auto = list_simulation_targets(ensure_embedded=True)
    assert len(with_auto) >= 2


def test_cannot_delete_system_policy(admin_client, system_policies):
    resp = admin_client.post(
        '/ConnectionManager/DeletePolicy/',
        data=json.dumps({'policy_name': 'Simulate Policy'}),
        content_type='application/json',
    )
    assert resp.status_code == 403


def test_clone_simulate_policy(admin_client, system_policies):
    _, simulate, _ = system_policies
    resp = admin_client.post(
        '/ConnectionManager/ClonePolicy/',
        data=json.dumps(
            {
                'source_policy_id': simulate.id,
                'new_policy_name': 'Simulate 8.19',
            }
        ),
        content_type='application/json',
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body['success'] is True
    clone = Policy.objects.get(name='Simulate 8.19')
    assert clone.policy_type == Policy.PolicyType.SIMULATE
    assert clone.is_system is False
    assert clone.cloned_from_id == simulate.id


def test_ensure_embedded_connection(system_policies, settings, monkeypatch):
    settings.LOGSTASH_AGENT_URL = 'https://logstashagent:9500'
    monkeypatch.setattr(
        'PipelineManager.agent_modes.probe_embedded_agent_online',
        lambda timeout=2.0: True,
    )
    conn = ensure_embedded_connection()
    assert conn is not None
    assert conn.agent_id == 'embedded-local'
    assert conn.policy.policy_type == Policy.PolicyType.EMBEDDED
    assert conn.host == 'logstashagent'
    assert conn.agent_api_port == 9500
    assert conn.last_check_in is not None
    assert (conn.status_blob or {}).get('online') is True
    # sticky: same row, host rebound on re-ensure
    Connection.objects.filter(pk=conn.pk).update(host='stale-host')
    conn2 = ensure_embedded_connection()
    assert conn2.id == conn.id
    assert conn2.host == 'logstashagent'
    assert conn2.last_check_in is not None


def test_list_targets_includes_embedded(system_policies):
    targets = list_simulation_targets(ensure_embedded=True)
    assert any(t['policy_type'] == 'EMBEDDED' for t in targets)


def test_get_simulation_targets_api(admin_client, system_policies):
    resp = admin_client.get('/ConnectionManager/GetSimulationTargets/')
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert data['count'] >= 1
    assert any(t['policy_type'] == 'EMBEDDED' for t in data['targets'])


def test_select_simulation_target_api(admin_client, system_policies):
    ensure_embedded_connection()
    targets = list_simulation_targets()
    cid = targets[0]['connection_id']
    resp = admin_client.post(
        '/ConnectionManager/SelectSimulationTarget/',
        data=json.dumps({'connection_id': cid}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    assert resp.json()['success'] is True
    assert admin_client.session.get('sim_connection_id') == cid
