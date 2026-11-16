from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Management', '0004_settings_logstash_artifact_base_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='settings',
            name='check_for_updates',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'Periodically query Docker Hub for newer LogstashUI releases '
                    'and show a notice in the nav.'
                ),
            ),
        ),
    ]
