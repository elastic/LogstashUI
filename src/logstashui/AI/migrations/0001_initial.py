# Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
# or more contributor license agreements. Licensed under the Elastic License;
# you may not use this file except in compliance with the Elastic License.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('SNMP', '0007_remove_device_profiles'),
    ]

    operations = [
        migrations.CreateModel(
            name='AISettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('agent_url', models.CharField(blank=True, help_text='Base Kibana URL of the Agent Builder deployment (e.g. https://my-deployment.kb.region.cloud.es.io)', max_length=512)),
                ('agent_id', models.CharField(default='snmp-profile-author', help_text='Agent Builder agent id used to author SNMP profiles', max_length=255)),
                ('api_key', models.CharField(blank=True, help_text="Encrypted Elasticsearch/Kibana API key (base64 'encoded' form)", max_length=1024)),
                ('verify_tls', models.BooleanField(default=True)),
                ('enabled', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'AI Settings',
                'verbose_name_plural': 'AI Settings',
            },
        ),
        migrations.CreateModel(
            name='DraftDefinition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_ip', models.CharField(blank=True, max_length=255)),
                ('sys_descr', models.TextField(blank=True)),
                ('vendor', models.CharField(blank=True, max_length=255)),
                ('proposed_name', models.CharField(max_length=255)),
                ('status', models.CharField(choices=[('pending', 'Pending approval'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=16)),
                ('profile_json', models.JSONField(default=dict, help_text='Authored {get, walk, table} blob')),
                ('unverified', models.JSONField(default=list, help_text='OIDs the agent could not verify')),
                ('walk_summary', models.TextField(blank=True, help_text='OIDs found on the live snmpwalk')),
                ('agent_notes', models.TextField(blank=True, help_text='Agent explanation / provenance')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('reviewed_by', models.CharField(blank=True, max_length=255)),
                ('created_profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='SNMP.profile')),
                ('created_template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='SNMP.devicetemplate')),
                ('device', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ai_drafts', to='SNMP.device')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
