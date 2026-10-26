# Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
# or more contributor license agreements. Licensed under the Elastic License;
# you may not use this file except in compliance with the Elastic License.

"""System Packaged/Managed/Simulate policies ship compliant and deployed."""

import hashlib
import importlib
import json

import pytest
import yaml
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import Client

from PipelineManager.agent_modes import materialize_simulate_logstash_yml
from PipelineManager.models import Connection, Policy, Revision
from PipelineManager.policies_crud import get_default_logstash_yml
from PipelineManager.system_policy_defaults import (
    build_required_logstash_yml,
    is_untouched_seed,
    set_path_logs,
    strip_license_header,
    unmet_requirements,
)

LICENSE_MARKER = "Elasticsearch B.V."

migration = importlib.import_module("PipelineManager.migrations.0031_deploy_system_policies")

SYSTEM_NAMES = ["Packaged Policy", "Managed Policy", "Simulate Policy"]

# What the pre-0031 seeds wrote.
OLD_MANAGED_YML = (
    "# Managed policy default logstash.yml\n"
    "config.reload.automatic: true\nconfig.reload.interval: 2s\n"
    'xpack.management.enabled: false\napi.http.host: "0.0.0.0"\napi.http.port: 9700\n'
)


def _reset_to_rev0(policy, yml):
    Revision.objects.filter(policy=policy).delete()
    policy.logstash_yml = yml
    policy.current_revision_number = 0
    policy.has_undeployed_changes = False
    policy.last_deployed_at = None
    policy.save()


@pytest.mark.parametrize("name", SYSTEM_NAMES)
def test_seeded_system_policies_are_compliant_and_deployed(db, name):
    policy = Policy.objects.get(name=name)
    assert unmet_requirements(policy.logstash_yml, policy.logs_path) == []
    assert policy.current_revision_number == 1
    assert policy.has_undeployed_changes is False
    assert policy.last_deployed_at is not None
    revision = Revision.objects.get(policy=policy)
    assert revision.revision_number == 1
    # Snapshot equals live state, so the diff UI shows no phantom changes.
    assert revision.snapshot_json["logstash_yml"] == policy.logstash_yml
    assert revision.snapshot_json["logs_path"] == policy.logs_path
    assert policy.logstash_yml_hash == hashlib.sha256(policy.logstash_yml.encode()).hexdigest()


@pytest.mark.parametrize("name", ["Managed Policy", "Simulate Policy"])
def test_instance_policies_materialize_path_logs(db, name):
    policy = Policy.objects.get(name=name)
    out = materialize_simulate_logstash_yml(policy.logstash_yml, 9701, instance_id=3)
    config = yaml.safe_load(out)
    assert "{instance_id}" not in out
    assert config["path"]["logs"].endswith("-3/logs")


def test_untouched_old_seed_is_filled_and_deployed(db):
    policy = Policy.objects.get(name="Managed Policy")
    _reset_to_rev0(policy, OLD_MANAGED_YML)

    migration.deploy_system_policies(django_apps, None)

    policy.refresh_from_db()
    assert unmet_requirements(policy.logstash_yml, policy.logs_path) == []
    assert policy.current_revision_number == 1
    assert Revision.objects.filter(policy=policy).count() == 1


def test_customized_yml_is_kept_but_deployed(db):
    policy = Policy.objects.get(name="Packaged Policy")
    custom = "node.name: mine\nlog.level: debug\n"
    _reset_to_rev0(policy, custom)

    migration.deploy_system_policies(django_apps, None)

    policy.refresh_from_db()
    assert policy.logstash_yml == custom
    assert policy.current_revision_number == 1


def test_migration_is_idempotent(db):
    policy = Policy.objects.get(name="Packaged Policy")
    before = (policy.logstash_yml, policy.current_revision_number)

    migration.deploy_system_policies(django_apps, None)
    migration.deploy_system_policies(django_apps, None)

    policy.refresh_from_db()
    assert (policy.logstash_yml, policy.current_revision_number) == before
    assert Revision.objects.filter(policy=policy).count() == 1


def test_policy_with_enrolled_agent_is_skipped(db):
    policy = Policy.objects.get(name="Packaged Policy")
    _reset_to_rev0(policy, "")
    Connection.objects.create(
        name="enrolled", connection_type="AGENT", policy=policy, agent_id="abc",
        host="10.0.0.5",
    )

    migration.deploy_system_policies(django_apps, None)

    policy.refresh_from_db()
    assert policy.current_revision_number == 0
    assert policy.logstash_yml == ""
    assert not Revision.objects.filter(policy=policy).exists()


def test_already_deployed_policy_is_untouched(db):
    policy = Policy.objects.get(name="Packaged Policy")
    policy.current_revision_number = 4
    policy.logstash_yml = "log.level: debug\n"
    policy.save()

    migration.deploy_system_policies(django_apps, None)

    policy.refresh_from_db()
    assert policy.current_revision_number == 4
    assert policy.logstash_yml == "log.level: debug\n"


def test_is_untouched_seed():
    assert is_untouched_seed("", "PACKAGED")
    assert is_untouched_seed("# comments only\n", "PACKAGED")
    assert is_untouched_seed(OLD_MANAGED_YML, "MANAGED")
    assert not is_untouched_seed(OLD_MANAGED_YML.replace("2s", "5s"), "MANAGED")
    assert not is_untouched_seed(build_required_logstash_yml("PACKAGED", "/var/log/logstash"), "PACKAGED")


def test_default_logstash_yml_is_compliant():
    assert unmet_requirements(get_default_logstash_yml(), "/var/log/logstash") == []


def test_default_logstash_yml_has_no_license_header():
    yml = get_default_logstash_yml()
    assert LICENSE_MARKER not in yml
    assert yml.startswith("# ------------ LogstashAgent requirements")


@pytest.mark.parametrize("name", SYSTEM_NAMES)
def test_seeded_system_policies_have_no_license_header(db, name):
    assert LICENSE_MARKER not in Policy.objects.get(name=name).logstash_yml


def test_migration_strips_license_header_from_raw_file_seed(db):
    from PipelineManager.policies_crud import load_default_config

    raw = load_default_config("default_logstash.yml")
    assert raw.startswith("#Copyright")
    policy = Policy.objects.get(name="Packaged Policy")
    _reset_to_rev0(policy, raw)

    migration.deploy_system_policies(django_apps, None)

    policy.refresh_from_db()
    assert policy.logstash_yml == strip_license_header(raw)
    assert Revision.objects.get(policy=policy).snapshot_json["logstash_yml"] == policy.logstash_yml


def test_strip_license_header_leaves_other_text_alone():
    assert strip_license_header("# my comment\nlog.level: info\n") == "# my comment\nlog.level: info\n"
    assert strip_license_header("") == ""


def test_set_path_logs_keeps_comments():
    yml = set_path_logs(get_default_logstash_yml(), "/opt/x/logs")
    assert unmet_requirements(yml, "/opt/x/logs") == []
    assert "# Settings file in YAML" in yml


def test_set_path_logs_handles_editor_output_order():
    # The editor emits path.data before path.logs inside one path: block.
    yml = "log:\n  level: info\npath:\n  data: /d\n  logs: /var/log/logstash\napi:\n  enabled: true\n"
    out = set_path_logs(yml, "/opt/x/logs")
    assert yaml.safe_load(out)["path"] == {"data": "/d", "logs": "/opt/x/logs"}
    assert yaml.safe_load(out)["api"] == {"enabled": True}


def test_clone_packaged_to_managed_retargets_path_logs(admin_client):
    packaged = Policy.objects.get(name="Packaged Policy")
    response = admin_client.post(
        "/ConnectionManager/ClonePolicy/",
        data=json.dumps({"source_policy_id": packaged.id, "new_policy_name": "cloned-managed"}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    clone = Policy.objects.get(name="cloned-managed")
    assert clone.policy_type == Policy.PolicyType.MANAGED
    assert "{instance_id}" in clone.logs_path
    assert unmet_requirements(clone.logstash_yml, clone.logs_path) == []


@pytest.fixture
def admin_client(db):
    user = get_user_model().objects.create_superuser("admin", "a@example.com", "pass")
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.parametrize("ptype", ["PACKAGED", "MANAGED", "SIMULATE"])
def test_new_policy_from_default_is_compliant(admin_client, ptype):
    response = admin_client.post(
        "/ConnectionManager/AddPolicy/",
        data=json.dumps({"name": f"new-{ptype}", "policy_type": ptype}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    policy = Policy.objects.get(name=f"new-{ptype}")
    assert unmet_requirements(policy.logstash_yml, policy.logs_path) == []
    assert LICENSE_MARKER not in policy.logstash_yml
