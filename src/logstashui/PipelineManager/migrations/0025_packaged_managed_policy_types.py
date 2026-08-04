#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import secrets
from pathlib import Path

from django.db import migrations, models


def _load_default_file(name: str) -> str:
    path = Path(__file__).resolve().parent.parent / 'data' / name
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return ''


MANAGED_LOGSTASH_YML = """# Managed policy default logstash.yml
# api.http.port is overridden per-instance at enroll (9700+N)
config.reload.automatic: true
config.reload.interval: 2s
xpack.management.enabled: false
api.http.host: "0.0.0.0"
api.http.port: 9700
"""


def migrate_packaged_managed(apps, schema_editor):
    Policy = apps.get_model('PipelineManager', 'Policy')
    EnrollmentToken = apps.get_model('PipelineManager', 'EnrollmentToken')

    default_yml = _load_default_file('default_logstash.yml') or MANAGED_LOGSTASH_YML
    default_jvm = _load_default_file('default_jvm.options') or '-Xms1g\n-Xmx1g\n'
    default_log4j = _load_default_file('default_log4j2.properties') or ''

    # DEFAULT → PACKAGED on all rows
    Policy.objects.filter(policy_type='DEFAULT').update(policy_type='PACKAGED')

    # Rename system Default Policy → Packaged Policy when free
    packaged = Policy.objects.filter(name='Default Policy', is_system=True).first()
    if packaged:
        if not Policy.objects.filter(name='Packaged Policy').exists():
            packaged.name = 'Packaged Policy'
        packaged.policy_type = 'PACKAGED'
        packaged.is_system = True
        packaged.save()
    else:
        packaged = Policy.objects.filter(name='Packaged Policy').first()
        if packaged:
            packaged.policy_type = 'PACKAGED'
            packaged.is_system = True
            packaged.save()
        else:
            packaged = Policy.objects.create(
                name='Packaged Policy',
                policy_type='PACKAGED',
                is_system=True,
                settings_path='/etc/logstash/',
                logs_path='/var/log/logstash',
                binary_path='/usr/share/logstash/bin',
                data_path='',
                agent_api_port=9500,
                logstash_api_port=9600,
                keystore_env_file='/etc/default/logstash',
                logstash_source='SYSTEM',
                logstash_version='',
                logstash_download_dir='/opt/logstash-agent/logstash-versions',
                logstash_yml=default_yml,
                jvm_options=default_jvm,
                log4j2_properties=default_log4j,
                has_undeployed_changes=False,
            )

    if packaged and not EnrollmentToken.objects.filter(policy=packaged, name='default').exists():
        EnrollmentToken.objects.create(
            policy=packaged,
            name='default',
            token=secrets.token_urlsafe(32),
        )

    # Seed system Managed Policy
    managed, created = Policy.objects.get_or_create(
        name='Managed Policy',
        defaults={
            'policy_type': 'MANAGED',
            'is_system': True,
            'settings_path': '/opt/logstash-agent/managed-{instance_id}/settings',
            'logs_path': '/opt/logstash-agent/managed-{instance_id}/logs',
            'binary_path': '/usr/share/logstash/bin',
            'data_path': '/opt/logstash-agent/managed-{instance_id}/data',
            'agent_api_port': 9600,
            'logstash_api_port': 9700,
            'keystore_env_file': '/opt/logstash-agent/managed-{instance_id}/env',
            'logstash_source': 'SYSTEM',
            'logstash_version': '',
            'logstash_download_dir': '/opt/logstash-agent/logstash-versions',
            'logstash_yml': MANAGED_LOGSTASH_YML,
            'jvm_options': default_jvm,
            'log4j2_properties': default_log4j,
            'has_undeployed_changes': False,
        },
    )
    if not created:
        managed.policy_type = 'MANAGED'
        managed.is_system = True
        managed.settings_path = '/opt/logstash-agent/managed-{instance_id}/settings'
        managed.logs_path = '/opt/logstash-agent/managed-{instance_id}/logs'
        managed.data_path = '/opt/logstash-agent/managed-{instance_id}/data'
        managed.keystore_env_file = '/opt/logstash-agent/managed-{instance_id}/env'
        if not managed.logstash_download_dir or 'LogstashAgent' in (
            managed.logstash_download_dir or ''
        ):
            managed.logstash_download_dir = '/opt/logstash-agent/logstash-versions'
        managed.save()

    if not EnrollmentToken.objects.filter(policy=managed, name='default').exists():
        EnrollmentToken.objects.create(
            policy=managed,
            name='default',
            token=secrets.token_urlsafe(32),
        )


def reverse_packaged_managed(apps, schema_editor):
    Policy = apps.get_model('PipelineManager', 'Policy')
    # Convert PACKAGED back to DEFAULT; rename Packaged Policy → Default Policy if free
    Policy.objects.filter(policy_type='PACKAGED').update(policy_type='DEFAULT')
    packaged = Policy.objects.filter(name='Packaged Policy', is_system=True).first()
    if packaged and not Policy.objects.filter(name='Default Policy').exists():
        packaged.name = 'Default Policy'
        packaged.save()
    # Drop Managed Policy only if unused
    try:
        managed = Policy.objects.get(name='Managed Policy', is_system=True)
    except Policy.DoesNotExist:
        return
    if not managed.connections.exists():
        managed.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('PipelineManager', '0024_seed_system_policies'),
    ]

    operations = [
        migrations.AlterField(
            model_name='policy',
            name='policy_type',
            field=models.CharField(
                choices=[
                    ('PACKAGED', 'Packaged'),
                    ('MANAGED', 'Managed'),
                    ('SIMULATE', 'Simulate'),
                    ('EMBEDDED', 'Embedded'),
                    ('DEFAULT', 'Default (legacy)'),
                ],
                default='PACKAGED',
                help_text='Agent role this policy targets',
                max_length=20,
            ),
        ),
        migrations.RunPython(migrate_packaged_managed, reverse_packaged_managed),
    ]
