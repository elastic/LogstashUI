#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('PipelineManager', '0028_apikey_admin_tokens'),
    ]

    operations = [
        migrations.CreateModel(
            name='LogstashArtifact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filename', models.CharField(help_text='Tarball filename, e.g. logstash-9.4.3-linux-x86_64.tar.gz', max_length=255, unique=True)),
                ('version', models.CharField(db_index=True, help_text='Logstash version, e.g. 9.4.3', max_length=32)),
                ('arch', models.CharField(help_text='Platform and architecture, e.g. linux-x86_64', max_length=32)),
                ('source_url', models.CharField(blank=True, default='', help_text='Explicit upstream URL. Blank derives one from the base URL setting.', max_length=512)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('FETCHING', 'Downloading'), ('READY', 'Ready'), ('FAILED', 'Failed'), ('IMPORTING', 'Verifying import')], db_index=True, default='PENDING', max_length=16)),
                ('size_bytes', models.BigIntegerField(blank=True, help_text='Total size, from the upstream Content-Length or the file on disk', null=True)),
                ('bytes_downloaded', models.BigIntegerField(default=0, help_text='Progress counter, written on a time floor rather than per chunk')),
                ('sha512', models.CharField(blank=True, default='', help_text='Verified SHA-512 of the published tarball', max_length=128)),
                ('error', models.TextField(blank=True, default='', help_text='Why the last fetch failed')),
                ('claimed_at', models.DateTimeField(blank=True, null=True)),
                ('heartbeat_at', models.DateTimeField(blank=True, null=True)),
                ('serve_count', models.PositiveIntegerField(default=0, help_text='Fresh tarball downloads by agents. Checksum fetches and resumed range requests hit the same row but are not counted')),
                ('last_served_at', models.DateTimeField(blank=True, help_text='When the tarball was last downloaded in full', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'logstash_artifact',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='policy',
            name='logstash_via_ui',
            field=models.BooleanField(default=False, help_text='Fetch the Logstash tarball from LogstashUI instead of artifacts.elastic.co. Only meaningful when logstash_source=VERSION on a MANAGED or SIMULATE policy.'),
        ),
    ]
