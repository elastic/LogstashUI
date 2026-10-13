#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add allow_self_signed_certs to Connection.

    Defaults to True so every existing row continues to allow self-signed
    certificates (preserving the previous hard-coded behaviour). New
    connections created via the UI can opt out by unchecking the box.
    """

    dependencies = [
        ('PipelineManager', '0029_logstash_artifacts'),
    ]

    operations = [
        migrations.AddField(
            model_name='connection',
            name='allow_self_signed_certs',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'Allow self-signed TLS certificates when connecting to '
                    'Elasticsearch/Kibana. Defaults to True so existing '
                    'connections keep working after migration.'
                ),
            ),
        ),
    ]
