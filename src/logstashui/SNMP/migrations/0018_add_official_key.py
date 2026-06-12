#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SNMP', '0017_remove_network_logstash_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='official_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Stable identifier from the official JSON file (e.g. 'generic_interfaces'). Null for user-created profiles.",
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='devicetemplate',
            name='official_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Stable identifier from the official JSON file (e.g. 'dell_idrac'). Null for user-created templates.",
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
    ]
