#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Management', '0003_settings_agent_ui_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='settings',
            name='logstash_artifact_base_url',
            field=models.CharField(
                blank=True,
                default='',
                help_text=(
                    'Upstream source for Logstash release tarballs. Blank uses '
                    'https://artifacts.elastic.co/downloads/logstash. Point this at an '
                    'internal mirror to keep tarball fetches inside your network.'
                ),
                max_length=512,
            ),
        ),
    ]
