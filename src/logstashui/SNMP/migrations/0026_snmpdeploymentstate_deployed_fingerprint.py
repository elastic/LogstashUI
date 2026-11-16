from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('SNMP', '0025_network_ssl_certificate_authorities'),
    ]

    operations = [
        migrations.AddField(
            model_name='snmpdeploymentstate',
            name='deployed_fingerprint',
            field=models.CharField(
                blank=True,
                help_text='Input fingerprint of the configuration that was last deployed',
                max_length=64,
                null=True,
            ),
        ),
    ]
