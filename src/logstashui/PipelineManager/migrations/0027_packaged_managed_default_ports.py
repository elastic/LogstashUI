#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Align Packaged/Managed policy default ports with the 9550 agent band.

Packaged agent FastAPI is 9550 (as-is); distro Logstash API stays 9600.
Managed stores 9550 / 9700 as bases; enroll assigns 9550+N / 9700+N.
Does not rewrite Connection instance ports already assigned at enroll.
"""

from django.db import migrations


def fix_policy_default_ports(apps, schema_editor):
    Policy = apps.get_model("PipelineManager", "Policy")

    for policy in Policy.objects.filter(policy_type="PACKAGED"):
        agent = int(policy.agent_api_port or 0)
        ls = int(policy.logstash_api_port or 0)
        # Old system seed (9500/9600) or draft bug (9600/9600)
        if (agent, ls) in ((9500, 9600), (9600, 9600)):
            policy.agent_api_port = 9550
            policy.logstash_api_port = 9600
            policy.save(update_fields=["agent_api_port", "logstash_api_port"])

    for policy in Policy.objects.filter(policy_type="MANAGED"):
        agent = int(policy.agent_api_port or 0)
        ls = int(policy.logstash_api_port or 0)
        if (agent, ls) == (9600, 9700):
            policy.agent_api_port = 9550
            policy.logstash_api_port = 9700
            policy.save(update_fields=["agent_api_port", "logstash_api_port"])


def noop_reverse(apps, schema_editor):
    # Port defaults are forward-only; do not restore the 9600/9600 collision.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("PipelineManager", "0026_normalize_opt_logstash_agent_paths"),
    ]

    operations = [
        migrations.RunPython(fix_policy_default_ports, noop_reverse),
    ]
