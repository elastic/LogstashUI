#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Rewrite legacy /opt/LogstashAgent → /opt/logstash-agent on Policy path fields.

Simulate/Managed system policies seeded before the path rename kept the old
prefix because get_or_create only applied defaults on first create.
"""

from django.db import migrations

_LEGACY = "/opt/LogstashAgent"
_CANONICAL = "/opt/logstash-agent"

_PATH_FIELDS = (
    "settings_path",
    "logs_path",
    "data_path",
    "binary_path",
    "keystore_env_file",
    "logstash_download_dir",
)


def _rewrite(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(_LEGACY):
        return _CANONICAL + value[len(_LEGACY) :]
    return value.replace(_LEGACY, _CANONICAL)


def normalize_paths(apps, schema_editor):
    Policy = apps.get_model("PipelineManager", "Policy")
    for policy in Policy.objects.all().iterator():
        changed = []
        for field in _PATH_FIELDS:
            old = getattr(policy, field, None)
            new = _rewrite(old)
            if new != old:
                setattr(policy, field, new)
                changed.append(field)
        if changed:
            policy.save(update_fields=changed)


def noop_reverse(apps, schema_editor):
    # Do not re-introduce the legacy prefix.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("PipelineManager", "0025_packaged_managed_policy_types"),
    ]

    operations = [
        migrations.RunPython(normalize_paths, noop_reverse),
    ]
