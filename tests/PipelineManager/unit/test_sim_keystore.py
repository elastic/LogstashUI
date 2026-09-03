#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from unittest.mock import patch

import pytest

from PipelineManager.models import Policy, Keystore
from PipelineManager.sim_keystore import (
    find_keystore_refs_in_text,
    find_keystore_refs_in_obj,
    resolve_source_policy,
    collect_policy_secrets,
    secrets_equal,
    maybe_sync_keystore_for_simulation,
)


def test_find_refs_simple():
    assert find_keystore_refs_in_text('hosts => "${ES_HOST}"') == {"ES_HOST"}
    assert find_keystore_refs_in_text('x => "${A:default}"') == {"A"}
    assert find_keystore_refs_in_text("no vars") == set()


def test_find_refs_in_components():
    components = {
        "filter": [
            {
                "plugin": "elasticsearch",
                "config": {"hosts": ["${ES_URL}"], "user": "${ES_USER}"},
            }
        ]
    }
    assert find_keystore_refs_in_obj(components) == {"ES_URL", "ES_USER"}


def test_secrets_equal_case_insensitive_keys():
    assert secrets_equal({"ES_HOST": "a"}, {"es_host": "a"})
    assert not secrets_equal({"ES_HOST": "a"}, {"es_host": "b"})
    assert not secrets_equal({"A": "1"}, {"A": "1", "B": "2"})


@pytest.mark.django_db
def test_collect_and_maybe_sync_when_different(db):
    policy = Policy.objects.create(
        name="Ks Policy Unique",
        policy_type=Policy.PolicyType.DEFAULT,
        logstash_yml="x: 1\n",
        jvm_options="-Xms1g\n",
        log4j2_properties="a=b\n",
        keystore_password="secret-pass",
    )
    Keystore.objects.create(
        policy=policy,
        key_name="ES_HOST",
        key_value="plaintext-host",
    )
    policy.refresh_from_db()
    secrets, password = collect_policy_secrets(policy)
    assert "es_host" in secrets
    assert password

    with patch(
        "PipelineManager.sim_keystore.fetch_agent_keystore",
        return_value={"exists": True, "secrets": {}},
    ), patch(
        "PipelineManager.sim_keystore.sync_keystore_to_agent",
        return_value={"status": "success", "unchanged": False, "restarted": True, "secrets_count": 1},
    ) as sync:
        result = maybe_sync_keystore_for_simulation(
            agent_base_url="http://127.0.0.1:9501",
            components={"filter": [{"config": {"h": "${ES_HOST}"}}]},
            ls_id=policy.id,
        )
        assert result["status"] == "success"
        assert result.get("unchanged") is False
        sync.assert_called_once()


@pytest.mark.django_db
def test_maybe_sync_skips_when_agent_matches(db):
    policy = Policy.objects.create(
        name="Ks Match Policy",
        policy_type=Policy.PolicyType.DEFAULT,
        logstash_yml="x: 1\n",
        jvm_options="-Xms1g\n",
        log4j2_properties="a=b\n",
        keystore_password="pw",
    )
    Keystore.objects.create(
        policy=policy,
        key_name="TOKEN",
        key_value="abc",
    )
    secrets, _ = collect_policy_secrets(policy)

    with patch(
        "PipelineManager.sim_keystore.fetch_agent_keystore",
        return_value={"exists": True, "secrets": secrets},
    ), patch(
        "PipelineManager.sim_keystore.sync_keystore_to_agent"
    ) as sync:
        result = maybe_sync_keystore_for_simulation(
            agent_base_url="http://agent",
            components={"filter": [{"config": {"t": "${TOKEN}"}}]},
            ls_id=policy.id,
        )
        assert result["unchanged"] is True
        assert result["restarted"] is False
        sync.assert_not_called()


@pytest.mark.django_db
def test_maybe_sync_skips_without_refs(db):
    with patch("PipelineManager.sim_keystore.sync_keystore_to_agent") as sync:
        result = maybe_sync_keystore_for_simulation(
            agent_base_url="http://agent",
            components={"filter": [{"config": {"x": "1"}}]},
            ls_id=1,
        )
        assert result is None
        sync.assert_not_called()


@pytest.mark.django_db
def test_maybe_sync_skips_without_policy(db):
    """No ls_id/policy association → cannot upload."""
    with patch("PipelineManager.sim_keystore.sync_keystore_to_agent") as sync:
        result = maybe_sync_keystore_for_simulation(
            agent_base_url="http://agent",
            components={"filter": [{"config": {"h": "${ES_HOST}"}}]},
            # no ls_id / policy_id
        )
        assert result is not None
        assert result["status"] == "skipped"
        assert result["reason"] == "no_policy"
        assert result["restarted"] is False
        sync.assert_not_called()


@pytest.mark.django_db
def test_resolve_requires_explicit_association(db):
    Policy.objects.get_or_create(
        name="Default Policy",
        defaults={
            "policy_type": Policy.PolicyType.DEFAULT,
            "is_system": True,
            "logstash_yml": "x: 1\n",
            "jvm_options": "-Xms1g\n",
            "log4j2_properties": "a=b\n",
        },
    )
    # No args → None (no silent Default fallback)
    assert resolve_source_policy() is None
    p = Policy.objects.get(name="Default Policy")
    assert resolve_source_policy(ls_id=p.id) == p
