#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add agent_inbound_key to Connection.

    Key the UI presents to an enrolled agent's FastAPI. Existing agents
    receive one (encrypted) on their next check-in.
    """

    dependencies = [
        ('PipelineManager', '0031_deploy_system_policies'),
    ]

    operations = [
        migrations.AddField(
            model_name='connection',
            name='agent_inbound_key',
            field=models.CharField(
                blank=True,
                help_text="Encrypted key the UI presents to this agent's API (Authorization: ApiKey)",
                max_length=512,
                null=True,
            ),
        ),
    ]
