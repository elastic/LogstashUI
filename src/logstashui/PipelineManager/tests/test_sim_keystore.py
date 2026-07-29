#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from unittest.mock import patch, MagicMock

import pytest

from PipelineManager.models import Policy, Keystore
from PipelineManager.sim_keystore import (
    find_keystore_refs_in_text,
    find_keystore_refs_in_obj,
    resolve_source_policy,
    collect_policy_secrets,
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


@pytest.mark.django_db
def test_collect_and_maybe_sync(db):
    policy = Policy.objects.create(
        name="Ks Policy",
        policy_type=Policy.PolicyType.DEFAULT,
        logstash_yml="x: 1\n",
        jvm_options="-Xms1g\n",
        log4j2_properties="a=b\n",
        keystore_password="secret-pass",
    )
    Keystore.objects.create(
        policy=policy,
        key_name="ES_HOST",
        key_value="plaintext-host",  # save will encrypt if not already
    )
    # Force plaintext path: model encrypts on save unless already fernet
    policy.refresh_from_db()

    # Re-set with known plaintext by using encrypt path
    entry = policy.keystore_entries.get(key_name="ES_HOST")
    # get_key_value may work if save encrypted
    secrets, password = collect_policy_secrets(policy)
    assert "ES_HOST" in secrets
    assert password  # encrypted password stored

    with patch(
        "PipelineManager.sim_keystore.sync_keystore_to_agent",
        return_value={"status": "success", "secrets_count": 1},
    ) as sync:
        result = maybe_sync_keystore_for_simulation(
            agent_base_url="http://127.0.0.1:9501",
            components={"filter": [{"config": {"h": "${ES_HOST}"}}]},
            ls_id=policy.id,
        )
        assert result["status"] == "success"
        sync.assert_called_once()
        args, kwargs = sync.call_args
        assert args[0] == "http://127.0.0.1:9501"
        assert "ES_HOST" in args[1]


@pytest.mark.django_db
def test_maybe_sync_skips_without_refs(db):
    with patch("PipelineManager.sim_keystore.sync_keystore_to_agent") as sync:
        result = maybe_sync_keystore_for_simulation(
            agent_base_url="http://agent",
            components={"filter": [{"config": {"x": "1"}}]},
        )
        assert result is None
        sync.assert_not_called()


@pytest.mark.django_db
def test_resolve_default_policy(db):
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
    p = resolve_source_policy()
    assert p is not None
    assert p.name == "Default Policy"
