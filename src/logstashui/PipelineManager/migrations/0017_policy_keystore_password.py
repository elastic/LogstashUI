from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('PipelineManager', '0016_backfill_pipeline_hash'),
    ]

    operations = [
        migrations.AddField(
            model_name='policy',
            name='keystore_password',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=512,
                help_text='Keystore password (encrypted at rest)',
            ),
        ),
        migrations.AddField(
            model_name='policy',
            name='keystore_password_hash',
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=64,
                help_text='SHA256 hash of keystore password for change detection',
            ),
        ),
    ]
