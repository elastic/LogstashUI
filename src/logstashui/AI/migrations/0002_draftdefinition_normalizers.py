# Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
# or more contributor license agreements. Licensed under the Elastic License;
# you may not use this file except in compliance with the Elastic License.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('AI', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='draftdefinition',
            name='normalizers',
            field=models.JSONField(
                default=list,
                help_text='Authored normalizer ops (multiply/ratio/...)',
            ),
        ),
    ]
