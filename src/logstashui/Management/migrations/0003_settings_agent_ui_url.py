#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Management', '0002_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='settings',
            name='agent_ui_url',
            field=models.CharField(
                blank=True,
                default='',
                help_text=(
                    'Base URL agents use to reach LogstashUI (backend channel). '
                    'Prefills --logstash-ui-url in generated enroll commands. '
                    'May differ from the browser reverse-proxy URL.'
                ),
                max_length=512,
            ),
        ),
    ]
