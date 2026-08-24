#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import base64
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from datetime import datetime, timezone

from PipelineManager.agent_modes import (
    apply_managed_path_bundle,
    apply_simulate_path_bundle,
    build_policy_config,
    ensure_embedded_connection,
    list_simulation_targets,
    managed_paths,
    managed_ports,
    materialize_simulate_logstash_yml,
    next_managed_instance_id,
    next_simulate_instance_id,
    normalize_policy_type,
    parse_creatable_policy_type,
    simulate_paths,
    simulate_ports,
    uses_packaged_default_paths,
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
    packaged, _ = Policy.objects.get_or_create(
        name='Packaged Policy',
        defaults={
            **defaults,
            'policy_type': Policy.PolicyType.PACKAGED,
            'agent_api_port': 9550,
            'logstash_api_port': 9600,
        },
    )
    packaged.policy_type = Policy.PolicyType.PACKAGED
    packaged.is_system = True
    packaged.agent_api_port = 9550
    packaged.logstash_api_port = 9600
    packaged.save()

    managed, _ = Policy.objects.get_or_create(
        name='Managed Policy',
        defaults={
            **defaults,
            'policy_type': Policy.PolicyType.MANAGED,
            'settings_path': '/opt/logstash-agent/managed-{instance_id}/settings',
            'logs_path': '/opt/logstash-agent/managed-{instance_id}/logs',
            'data_path': '/opt/logstash-agent/managed-{instance_id}/data',
            'keystore_env_file': '/opt/logstash-agent/managed-{instance_id}/env',
            'agent_api_port': 9550,
            'logstash_api_port': 9700,
            'logstash_yml': 'api.http.port: 9700\n',
            'logstash_source': Policy.LogstashSource.SYSTEM,
        },
    )
    managed.policy_type = Policy.PolicyType.MANAGED
    managed.is_system = True
    managed.agent_api_port = 9550
    managed.logstash_api_port = 9700
    managed.save()

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
    return packaged, managed, simulate, embedded


def test_normalize_policy_type_legacy_default():
    assert normalize_policy_type('DEFAULT') == Policy.PolicyType.PACKAGED
    assert normalize_policy_type('default') == Policy.PolicyType.PACKAGED
    assert normalize_policy_type(None) == Policy.PolicyType.PACKAGED
    assert normalize_policy_type('MANAGED') == Policy.PolicyType.MANAGED


def test_parse_creatable_policy_type():
    assert parse_creatable_policy_type(None) == (Policy.PolicyType.PACKAGED, None)
    assert parse_creatable_policy_type('') == (Policy.PolicyType.PACKAGED, None)
    assert parse_creatable_policy_type('managed')[0] == Policy.PolicyType.MANAGED
    pt, err = parse_creatable_policy_type('EMBEDDED')
    assert pt is None and 'Embedded' in err
    pt, err = parse_creatable_policy_type('DEFAULT')
    assert pt is None and 'PACKAGED' in err
    pt, err = parse_creatable_policy_type('WIZARD')
    assert pt is None and 'Invalid' in err


def test_apply_simulate_path_bundle_templates(db):
    policy = Policy.objects.create(
        name='Sim Draft',
        policy_type=Policy.PolicyType.SIMULATE,
        logstash_yml='x: 1\n',
        jvm_options='-Xms1g\n',
        log4j2_properties='x=1\n',
    )
    apply_simulate_path_bundle(policy)
    assert policy.settings_path == '/opt/logstash-agent/simulate-{instance_id}/settings'
    assert policy.logs_path == '/opt/logstash-agent/simulate-{instance_id}/logs'
    assert policy.agent_api_port == 9500
    assert policy.logstash_api_port == 9560


def test_uses_packaged_default_paths(db):
    policy = Policy.objects.create(
        name='Path Probe',
        logstash_yml='x: 1\n',
        jvm_options='-Xms1g\n',
        log4j2_properties='x=1\n',
    )
    assert uses_packaged_default_paths(policy) is True
    apply_managed_path_bundle(policy)
    assert uses_packaged_default_paths(policy) is False
    assert policy.agent_api_port == 9550
    assert policy.logstash_api_port == 9700


def test_simulate_ports_formula():
    assert simulate_ports(1) == (9501, 9561)
    assert simulate_ports(2) == (9502, 9562)


def test_managed_ports_formula():
    assert managed_ports(1) == (9551, 9701)
    assert managed_ports(2) == (9552, 9702)


def test_managed_ports_uses_policy_base(db):
    policy = Policy.objects.create(
        name='Custom Managed Ports',
        policy_type=Policy.PolicyType.MANAGED,
        agent_api_port=9800,
        logstash_api_port=9900,
        logstash_yml='x: 1\n',
        jvm_options='-Xms1g\n',
        log4j2_properties='x=1\n',
    )
    assert managed_ports(1, policy) == (9801, 9901)
    assert managed_ports(2, policy) == (9802, 9902)


def test_simulate_paths():
    p = simulate_paths(1)
    assert p['settings_path'] == '/opt/logstash-agent/simulate-1/settings'
    assert p['keystore_env_file'] == '/opt/logstash-agent/simulate-1/env'


def test_managed_paths():
    p = managed_paths(1)
    assert p['settings_path'] == '/opt/logstash-agent/managed-1/settings'
    assert p['deployment_id'] == 'managed-1'


def test_next_instance_id_skips_used(db, system_policies):
    _, _, simulate, _ = system_policies
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


def test_next_managed_instance_id_skips_used(db, system_policies):
    _, managed, _, _ = system_policies
    Connection.objects.create(
        name='m',
        connection_type='AGENT',
        host='h1',
        agent_id='id-m1',
        policy=managed,
        instance_id=1,
        agent_api_port=9551,
        logstash_api_port=9701,
    )
    assert next_managed_instance_id() == 2


def test_materialize_nested_api_http_port():
    nested = (
        "api:\n"
        "  http:\n"
        "    host: 0.0.0.0\n"
        "    port: 9560\n"
        "path:\n"
        "  logs: /opt/logstash-agent/simulate-{instance_id}/logs\n"
    )
    out = materialize_simulate_logstash_yml(nested, 9561, instance_id=1)
    assert "9560" not in out or "9561" in out
    assert "port: 9561" in out
    assert "simulate-1/logs" in out
    assert "{instance_id}" not in out


def test_build_policy_config_simulate(system_policies):
    _, _, simulate, _ = system_policies
    cfg = build_policy_config(simulate, instance_id=1)
    assert cfg['policy_type'] == 'SIMULATE'
    assert cfg['instance_id'] == 1
    assert cfg['agent_api_port'] == 9501
    assert cfg['logstash_api_port'] == 9561
    # Flat or nested form after materialize — port must be instance-specific
    assert '9561' in cfg['logstash_yml']
    assert '9560' not in cfg['logstash_yml'].replace('9561', '')
    assert cfg['logstash_unit'] == 'ls-simulate@1'


def test_build_policy_config_managed(system_policies):
    _, managed, _, _ = system_policies
    cfg = build_policy_config(managed, instance_id=1)
    assert cfg['policy_type'] == 'MANAGED'
    assert cfg['instance_id'] == 1
    assert cfg['agent_api_port'] == 9551
    assert cfg['logstash_api_port'] == 9701
    assert cfg['settings_path'] == '/opt/logstash-agent/managed-1/settings'
    assert cfg['path_root'] == '/opt/logstash-agent/managed-1'
    assert cfg['logstash_unit'] == 'logstash-managed@1'
    assert cfg['agent_unit'] == 'logstash-agent@1'
    assert 'api.http.port: 9701' in cfg['logstash_yml']


def test_build_policy_config_packaged(system_policies):
    packaged, _, _, _ = system_policies
    cfg = build_policy_config(packaged)
    assert cfg['policy_type'] == 'PACKAGED'
    assert cfg['logstash_unit'] == 'logstash'
    assert cfg['agent_unit'] == 'logstash-agent'
    assert cfg['agent_api_port'] == 9550
    assert cfg['logstash_api_port'] == 9600
    assert 'instance_id' not in cfg


def test_enroll_packaged_uses_policy_ports(db, system_policies):
    packaged, _, _, _ = system_policies
    token, _ = EnrollmentToken.objects.get_or_create(
        policy=packaged,
        name='default',
        defaults={'token': 'packaged-token-abc'},
    )
    token.token = 'packaged-token-abc'
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
                'host': 'pkghost.example',
                'agent_id': 'agent-packaged-1',
            }
        ),
        content_type='application/json',
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body['success'] is True
    assert body['policy_config']['policy_type'] == 'PACKAGED'
    assert body['policy_config']['agent_api_port'] == 9550
    assert body['policy_config']['logstash_api_port'] == 9600
    assert 'instance_id' not in body['policy_config']


def test_enroll_simulate_allocates_instance(db, system_policies):
    _, _, simulate, _ = system_policies
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


def test_enroll_managed_allocates_instance(db, system_policies):
    _, managed, _, _ = system_policies
    token, _ = EnrollmentToken.objects.get_or_create(
        policy=managed,
        name='default',
        defaults={'token': 'managed-token-abc'},
    )
    token.token = 'managed-token-abc'
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
                'host': 'managedhost.example',
                'agent_id': 'agent-managed-1',
            }
        ),
        content_type='application/json',
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body['success'] is True
    assert body['policy_config']['policy_type'] == 'MANAGED'
    assert body['policy_config']['instance_id'] == 1
    assert body['policy_config']['agent_api_port'] == 9551
    assert body['policy_config']['logstash_api_port'] == 9701
    assert body['policy_config']['path_root'] == '/opt/logstash-agent/managed-1'
    conn = Connection.objects.get(agent_id='agent-managed-1')
    assert conn.instance_id == 1
    assert conn.name == 'managedhost-managed-1'
    assert conn.host == 'managedhost.example'


def test_enroll_embedded_rejected(db, system_policies):
    _, _, _, embedded = system_policies
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
    _, _, simulate, embedded = system_policies
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
        last_check_in=datetime.now(timezone.utc),
        status_blob={'online': True, 'embedded': True},
    )
    # ensure_embedded=False: only the two rows we created (no extra pseudo conn)
    targets = list_simulation_targets(ensure_embedded=False)
    assert len(targets) == 2
    labels = [t['label'] for t in targets]
    # Dedicated simulate-N first; discovered embedded last
    assert labels == ['simulate-1', 'embedded']
    sim = next(t for t in targets if t['label'] == 'simulate-1')
    assert '10.0.0.5' in sim['detail']
    assert '9.4.3' in sim['detail']
    emb = next(t for t in targets if t['label'] == 'embedded')
    assert 'embedded' in emb['detail']
    # Default ensure_embedded also lists the docker pseudo-connection if probed online
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
    _, _, simulate, _ = system_policies
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


def test_clone_packaged_becomes_managed(admin_client, system_policies):
    packaged, _, _, _ = system_policies
    resp = admin_client.post(
        '/ConnectionManager/ClonePolicy/',
        data=json.dumps(
            {
                'source_policy_id': packaged.id,
                'new_policy_name': 'My Managed Clone',
            }
        ),
        content_type='application/json',
    )
    assert resp.status_code == 200, resp.content
    clone = Policy.objects.get(name='My Managed Clone')
    assert clone.policy_type == Policy.PolicyType.MANAGED
    assert clone.is_system is False
    assert clone.cloned_from_id == packaged.id
    assert 'managed-{instance_id}' in (clone.settings_path or '')


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


def test_ensure_embedded_connection_skip_probe(system_policies, settings, monkeypatch):
    """Listing/page render must not wait on the live HTTP probe."""
    settings.LOGSTASH_AGENT_URL = 'https://logstashagent:9500'
    probed = {'called': False}

    def _probe(timeout=2.0):
        probed['called'] = True
        return True

    monkeypatch.setattr('PipelineManager.agent_modes.probe_embedded_agent_online', _probe)
    conn = ensure_embedded_connection(probe=False)
    assert conn is not None
    assert conn.agent_id == 'embedded-local'
    assert probed['called'] is False
    assert conn.last_check_in is None


def test_list_simulation_targets_does_not_probe(system_policies, monkeypatch):
    """Editor listing must not block on an unreachable embedded agent."""
    probed = {'called': False}

    def _probe(timeout=2.0):
        probed['called'] = True
        return True

    monkeypatch.setattr('PipelineManager.agent_modes.probe_embedded_agent_online', _probe)
    list_simulation_targets(ensure_embedded=True)
    assert probed['called'] is False


def test_build_policy_config_simulate_paths_use_logstash_agent_root(system_policies):
    from PipelineManager.agent_modes import build_policy_config, SIMULATE_ROOT
    from PipelineManager.models import Policy

    sim = Policy.objects.filter(policy_type=Policy.PolicyType.SIMULATE).first()
    assert sim is not None
    cfg = build_policy_config(sim, instance_id=1)
    assert cfg["settings_path"] == f"{SIMULATE_ROOT}/simulate-1/settings"
    assert cfg["logstash_download_dir"].startswith(SIMULATE_ROOT)
    assert "/opt/LogstashAgent" not in cfg["settings_path"]
    assert "/opt/LogstashAgent" not in (cfg.get("logstash_download_dir") or "")


def test_normalize_agent_opt_path_rewrites_legacy_root():
    from PipelineManager.agent_modes import normalize_agent_opt_path

    assert (
        normalize_agent_opt_path("/opt/LogstashAgent/simulate-{instance_id}/settings")
        == "/opt/logstash-agent/simulate-{instance_id}/settings"
    )
    assert (
        normalize_agent_opt_path("/opt/logstash-agent/simulate-1/settings")
        == "/opt/logstash-agent/simulate-1/settings"
    )
    assert normalize_agent_opt_path("/etc/logstash/") == "/etc/logstash/"
    assert normalize_agent_opt_path("") == ""


@pytest.mark.django_db
def test_legacy_simulate_policy_paths_rewritten_on_config(system_policies):
    """Even if DB still has legacy /opt/LogstashAgent, enroll payload is canonical."""
    from PipelineManager.agent_modes import build_policy_config
    from PipelineManager.models import Policy

    sim = Policy.objects.filter(policy_type=Policy.PolicyType.SIMULATE, is_system=True).first()
    assert sim is not None
    sim.settings_path = "/opt/LogstashAgent/simulate-{instance_id}/settings"
    sim.logs_path = "/opt/LogstashAgent/simulate-{instance_id}/logs"
    sim.data_path = "/opt/LogstashAgent/simulate-{instance_id}/data"
    sim.keystore_env_file = "/opt/LogstashAgent/simulate-{instance_id}/env"
    sim.logstash_download_dir = "/opt/LogstashAgent/logstash-versions"
    sim.save()

    cfg = build_policy_config(sim, instance_id=2)
    assert cfg["settings_path"] == "/opt/logstash-agent/simulate-2/settings"
    assert cfg["logs_path"] == "/opt/logstash-agent/simulate-2/logs"
    assert cfg["data_path"] == "/opt/logstash-agent/simulate-2/data"
    assert cfg["keystore_env_file"] == "/opt/logstash-agent/simulate-2/env"
    assert cfg["logstash_download_dir"] == "/opt/logstash-agent/logstash-versions"
    assert "/opt/LogstashAgent" not in str(cfg)


def test_list_targets_includes_embedded(system_policies, monkeypatch):
    monkeypatch.setattr(
        'PipelineManager.agent_modes.probe_embedded_agent_online',
        lambda timeout=2.0: True,
    )
    targets = list_simulation_targets(ensure_embedded=True)
    assert any(t['policy_type'] == 'EMBEDDED' for t in targets)
    assert targets[-1]['label'] == 'embedded'


def test_list_targets_omits_undiscovered_embedded(system_policies, monkeypatch):
    monkeypatch.setattr(
        'PipelineManager.agent_modes.probe_embedded_agent_online',
        lambda timeout=2.0: False,
    )
    targets = list_simulation_targets(ensure_embedded=True)
    assert not any(t['policy_type'] == 'EMBEDDED' for t in targets)


def test_list_targets_embedded_after_simulate(system_policies, monkeypatch):
    _, _, simulate, _ = system_policies
    monkeypatch.setattr(
        'PipelineManager.agent_modes.probe_embedded_agent_online',
        lambda timeout=2.0: True,
    )
    Connection.objects.create(
        name='sim1',
        connection_type='AGENT',
        host='10.0.0.5',
        agent_id='s1',
        policy=simulate,
        instance_id=1,
        agent_api_port=9501,
        logstash_api_port=9561,
        is_active=True,
    )
    labels = [t['label'] for t in list_simulation_targets(ensure_embedded=True)]
    assert labels[0] == 'simulate-1'
    assert labels[-1] == 'embedded'


def test_get_simulation_targets_api(admin_client, system_policies, monkeypatch):
    monkeypatch.setattr(
        'PipelineManager.agent_modes.probe_embedded_agent_online',
        lambda timeout=2.0: True,
    )
    resp = admin_client.get('/ConnectionManager/GetSimulationTargets/')
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    assert data['count'] >= 1
    assert any(t['policy_type'] == 'EMBEDDED' for t in data['targets'])
    assert data['targets'][-1]['label'] == 'embedded'


def test_select_simulation_target_api(admin_client, system_policies, monkeypatch):
    monkeypatch.setattr(
        'PipelineManager.agent_modes.probe_embedded_agent_online',
        lambda timeout=2.0: True,
    )
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


def test_get_policies_excludes_embedded(admin_client, system_policies):
    resp = admin_client.get('/ConnectionManager/GetPolicies/')
    assert resp.status_code == 200
    data = resp.json()
    assert data['success'] is True
    names = [p['name'] for p in data['policies']]
    types = [p['policy_type'] for p in data['policies']]
    assert 'Embedded Policy' not in names
    assert 'EMBEDDED' not in types
    assert 'Simulate Policy' in names


def test_pipeline_manager_hides_embedded_agent(admin_client, system_policies, monkeypatch):
    monkeypatch.setattr(
        'PipelineManager.agent_modes.probe_embedded_agent_online',
        lambda timeout=2.0: True,
    )
    ensure_embedded_connection()
    resp = admin_client.get('/ConnectionManager/')
    assert resp.status_code == 200
    names = [c['name'] for c in resp.context['connections']]
    assert 'embedded' not in names
    html = resp.content.decode()
    # Table must not render the docker pseudo-agent; sim picker is a different page
    assert 'embedded-local' not in html


def test_get_connections_excludes_embedded(admin_client, system_policies, monkeypatch):
    monkeypatch.setattr(
        'PipelineManager.agent_modes.probe_embedded_agent_online',
        lambda timeout=2.0: True,
    )
    conn = ensure_embedded_connection()
    assert conn is not None
    resp = admin_client.get('/ConnectionManager/GetConnections/')
    assert resp.status_code == 200
    ids = [c['id'] for c in resp.json()]
    assert conn.id not in ids
    names = [c['name'] for c in resp.json()]
    assert 'embedded' not in names
