#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import secrets
from pathlib import Path

from django.db import migrations


def _load_default_file(name: str) -> str:
    path = Path(__file__).resolve().parent.parent / 'data' / name
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return ''


SIMULATE_LOGSTASH_YML = """# Simulate policy default logstash.yml
# api.http.port is overridden per-instance at enroll (9560+N)
config.reload.automatic: true
config.reload.interval: 2s
xpack.management.enabled: false
api.http.host: "0.0.0.0"
api.http.port: 9560
"""

EMBEDDED_LOGSTASH_YML = """# Embedded Docker simulation logstash.yml
config.reload.automatic: true
config.reload.interval: 2s
xpack.management.enabled: false
api.http.host: "0.0.0.0"
api.http.port: 9560
"""


def seed_system_policies(apps, schema_editor):
    Policy = apps.get_model('PipelineManager', 'Policy')
    EnrollmentToken = apps.get_model('PipelineManager', 'EnrollmentToken')

    default_yml = _load_default_file('default_logstash.yml') or SIMULATE_LOGSTASH_YML
    default_jvm = _load_default_file('default_jvm.options') or '-Xms1g\n-Xmx1g\n'
    default_log4j = _load_default_file('default_log4j2.properties') or ''

    # Promote existing "Default Policy" if present
    default_policy, created = Policy.objects.get_or_create(
        name='Default Policy',
        defaults={
            'policy_type': 'DEFAULT',
            'is_system': True,
            'settings_path': '/etc/logstash/',
            'logs_path': '/var/log/logstash',
            'binary_path': '/usr/share/logstash/bin',
            'data_path': '',
            'agent_api_port': 9500,
            'logstash_api_port': 9600,
            'keystore_env_file': '/etc/default/logstash',
            'logstash_source': 'SYSTEM',
            'logstash_version': '',
            'logstash_download_dir': '/opt/LogstashAgent/logstash-versions',
            'logstash_yml': default_yml,
            'jvm_options': default_jvm,
            'log4j2_properties': default_log4j,
            'has_undeployed_changes': False,
        },
    )
    if not created:
        default_policy.policy_type = 'DEFAULT'
        default_policy.is_system = True
        if not default_policy.keystore_env_file:
            default_policy.keystore_env_file = '/etc/default/logstash'
        default_policy.save()

    if not EnrollmentToken.objects.filter(policy=default_policy, name='default').exists():
        EnrollmentToken.objects.create(
            policy=default_policy,
            name='default',
            token=secrets.token_urlsafe(32),
        )

    simulate_policy, created = Policy.objects.get_or_create(
        name='Simulate Policy',
        defaults={
            'policy_type': 'SIMULATE',
            'is_system': True,
            'settings_path': '/opt/LogstashAgent/simulate-{instance_id}/settings',
            'logs_path': '/opt/LogstashAgent/simulate-{instance_id}/logs',
            'binary_path': '/usr/share/logstash/bin',
            'data_path': '/opt/LogstashAgent/simulate-{instance_id}/data',
            'agent_api_port': 9500,
            'logstash_api_port': 9560,
            'keystore_env_file': '/opt/LogstashAgent/simulate-{instance_id}/env',
            'logstash_source': 'SYSTEM',
            'logstash_version': '',
            'logstash_download_dir': '/opt/LogstashAgent/logstash-versions',
            'logstash_yml': SIMULATE_LOGSTASH_YML,
            'jvm_options': default_jvm,
            'log4j2_properties': default_log4j,
            'has_undeployed_changes': False,
        },
    )
    if not created:
        simulate_policy.policy_type = 'SIMULATE'
        simulate_policy.is_system = True
        simulate_policy.save()

    if not EnrollmentToken.objects.filter(policy=simulate_policy, name='default').exists():
        EnrollmentToken.objects.create(
            policy=simulate_policy,
            name='default',
            token=secrets.token_urlsafe(32),
        )

    embedded_policy, created = Policy.objects.get_or_create(
        name='Embedded Policy',
        defaults={
            'policy_type': 'EMBEDDED',
            'is_system': True,
            'settings_path': '/etc/logstash/',
            'logs_path': '/var/log/logstash',
            'binary_path': '/usr/share/logstash/bin',
            'data_path': '',
            'agent_api_port': 9500,
            'logstash_api_port': 9560,
            'keystore_env_file': '',
            'logstash_source': 'SYSTEM',
            'logstash_version': '',
            'logstash_download_dir': '',
            'logstash_yml': EMBEDDED_LOGSTASH_YML,
            'jvm_options': default_jvm,
            'log4j2_properties': default_log4j,
            'has_undeployed_changes': False,
        },
    )
    if not created:
        embedded_policy.policy_type = 'EMBEDDED'
        embedded_policy.is_system = True
        embedded_policy.agent_api_port = 9500
        embedded_policy.logstash_api_port = 9560
        embedded_policy.save()


def unseed_system_policies(apps, schema_editor):
    Policy = apps.get_model('PipelineManager', 'Policy')
    # Only remove policies we created that have no connections
    for name in ('Simulate Policy', 'Embedded Policy'):
        try:
            p = Policy.objects.get(name=name, is_system=True)
        except Policy.DoesNotExist:
            continue
        if not p.connections.exists():
            p.delete()
    # Do not delete Default Policy on reverse


class Migration(migrations.Migration):

    dependencies = [
        ('PipelineManager', '0023_agent_modes_policy_connection'),
    ]

    operations = [
        migrations.RunPython(seed_system_policies, unseed_system_policies),
    ]
