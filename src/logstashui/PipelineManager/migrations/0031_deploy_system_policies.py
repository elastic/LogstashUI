"""Fill in and deploy the system Packaged, Managed, and Simulate policies.

The seed migrations (0024/0025) left these policies without requirement-compliant
config and at revision 0 with no ``Revision`` row, so users had to edit, save, and
deploy them before enrolling agents. This migration:

* replaces an untouched seed ``logstash.yml`` with a compliant one,
* writes revision 1 (snapshot, counter, ``last_deployed_at``).

Only policies still at revision 0 with no revisions are touched, and policies that
already have enrolled agents are skipped: bumping their revision would push config
(and a Logstash restart) to hosts that never asked for it.
"""

import hashlib
from datetime import datetime, timezone

from django.db import migrations

from PipelineManager.system_policy_defaults import (
    build_required_logstash_yml,
    build_snapshot,
    is_untouched_seed,
    strip_license_header,
)

SYSTEM_TYPES = ("PACKAGED", "MANAGED", "SIMULATE")


def _sha256(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def deploy_system_policies(apps, schema_editor):
    Policy = apps.get_model("PipelineManager", "Policy")
    Revision = apps.get_model("PipelineManager", "Revision")

    candidates = Policy.objects.filter(
        is_system=True, policy_type__in=SYSTEM_TYPES, current_revision_number=0
    )
    for policy in candidates:
        if Revision.objects.filter(policy=policy).exists():
            continue
        if policy.connections.exists():
            continue

        if is_untouched_seed(policy.logstash_yml, policy.policy_type):
            policy.logstash_yml = build_required_logstash_yml(
                policy.policy_type, policy.logs_path
            )
        else:
            # 0024/0025 seeded Packaged from data/default_logstash.yml verbatim.
            policy.logstash_yml = strip_license_header(policy.logstash_yml)

        # Historical models skip Policy.save(), so refresh the agent-facing hashes here.
        policy.logstash_yml_hash = _sha256(policy.logstash_yml)
        policy.jvm_options_hash = _sha256(policy.jvm_options)
        policy.log4j2_properties_hash = _sha256(policy.log4j2_properties)

        pipelines = list(
            policy.pipelines.filter(managed_by="user").values(
                "name", "description", "lscl", "no_input", "non_reloadable"
            )
        )
        keystore = list(
            policy.keystore_entries.filter(managed_by="user").values("key_name", "key_value")
        )
        Revision.objects.create(
            policy=policy,
            revision_number=1,
            snapshot_json=build_snapshot(policy, pipelines, keystore),
            created_by="system",
        )
        policy.current_revision_number = 1
        policy.last_deployed_at = datetime.now(timezone.utc)
        policy.has_undeployed_changes = False
        policy.save()


def noop_reverse(apps, schema_editor):
    # Forward-only: a deployed revision may already be applied by agents.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("PipelineManager", "0030_connection_allow_self_signed_certs"),
    ]

    operations = [
        migrations.RunPython(deploy_system_policies, noop_reverse),
    ]
