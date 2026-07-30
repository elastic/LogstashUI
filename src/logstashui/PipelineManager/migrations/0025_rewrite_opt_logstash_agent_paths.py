#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Rewrite legacy /opt/LogstashAgent path prefixes to /opt/logstash-agent on Policy rows."""

from django.db import migrations

_OLD = "/opt/LogstashAgent"
_NEW = "/opt/logstash-agent"

_POLICY_PATH_FIELDS = (
    "settings_path",
    "logs_path",
    "binary_path",
    "data_path",
    "keystore_env_file",
    "logstash_download_dir",
)


def _rewrite(value: str) -> str:
    if not value:
        return value
    if value.startswith(_OLD):
        return _NEW + value[len(_OLD) :]
    return value.replace(_OLD, _NEW)


def forwards(apps, schema_editor):
    Policy = apps.get_model("PipelineManager", "Policy")
    for policy in Policy.objects.all().iterator():
        changed = False
        for field in _POLICY_PATH_FIELDS:
            raw = getattr(policy, field, None) or ""
            if not isinstance(raw, str) or _OLD not in raw:
                continue
            new = _rewrite(raw)
            if new != raw:
                setattr(policy, field, new)
                changed = True
        if changed:
            policy.save(update_fields=list(_POLICY_PATH_FIELDS))


def backwards(apps, schema_editor):
    Policy = apps.get_model("PipelineManager", "Policy")
    for policy in Policy.objects.all().iterator():
        changed = False
        for field in _POLICY_PATH_FIELDS:
            raw = getattr(policy, field, None) or ""
            if not isinstance(raw, str) or _NEW not in raw:
                continue
            # Only reverse our simulate/managed style prefixes
            if raw.startswith(_NEW + "/simulate-") or raw.startswith(
                _NEW + "/logstash-versions"
            ) or raw.startswith(_NEW + "/managed-"):
                new = _OLD + raw[len(_NEW) :]
                setattr(policy, field, new)
                changed = True
        if changed:
            policy.save(update_fields=list(_POLICY_PATH_FIELDS))


class Migration(migrations.Migration):
    dependencies = [
        ("PipelineManager", "0024_seed_system_policies"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
