#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Detect Logstash keystore/env var references in pipeline configs and clone
source-policy secrets onto a simulate agent before simulation runs.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import requests

from PipelineManager.models import Keystore, Policy

logger = logging.getLogger(__name__)

# Logstash ${VAR} and ${VAR:default} forms (env / keystore)
_KEYSTORE_REF_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_.-]*)(?::[^}]*)?\}"
)


def find_keystore_refs_in_text(text: str) -> set[str]:
    if not text:
        return set()
    return set(_KEYSTORE_REF_RE.findall(text))


def find_keystore_refs_in_obj(obj: Any) -> set[str]:
    """Walk JSON-serializable structures (components tree) for ${...} refs."""
    found: set[str] = set()
    if obj is None:
        return found
    if isinstance(obj, str):
        return find_keystore_refs_in_text(obj)
    if isinstance(obj, dict):
        for v in obj.values():
            found |= find_keystore_refs_in_obj(v)
        return found
    if isinstance(obj, (list, tuple)):
        for item in obj:
            found |= find_keystore_refs_in_obj(item)
        return found
    # numbers/bools
    return found


def resolve_source_policy(ls_id=None, policy_id=None, policy_name=None) -> Optional[Policy]:
    """
    Resolve the policy whose keystore should be cloned for simulation.
    Prefer explicit ls_id / policy_id; fall back to system Default Policy.
    """
    if policy_id is not None:
        try:
            return Policy.objects.get(pk=int(policy_id))
        except (Policy.DoesNotExist, TypeError, ValueError):
            pass
    if ls_id is not None:
        try:
            return Policy.objects.get(pk=int(ls_id))
        except (Policy.DoesNotExist, TypeError, ValueError):
            pass
    if policy_name:
        try:
            return Policy.objects.get(name=policy_name)
        except Policy.DoesNotExist:
            pass
    # Prefer system Default Policy, then any DEFAULT policy
    p = Policy.objects.filter(
        policy_type=Policy.PolicyType.DEFAULT, is_system=True
    ).first()
    if p:
        return p
    p = Policy.objects.filter(name="Default Policy").first()
    if p:
        return p
    return Policy.objects.filter(policy_type=Policy.PolicyType.DEFAULT).first()


def collect_policy_secrets(policy: Policy) -> tuple[dict[str, str], Optional[str]]:
    """
    Return (secrets_map, password_or_none) for all user-managed keystore entries.
    """
    secrets: dict[str, str] = {}
    for entry in policy.keystore_entries.filter(managed_by="user"):
        val = entry.get_key_value()
        if val is not None:
            secrets[entry.key_name] = val
    password = policy.get_keystore_password() or None
    return secrets, password


def sync_keystore_to_agent(
    agent_base_url: str,
    secrets: dict[str, str],
    password: Optional[str] = None,
    *,
    restart: bool = True,
    timeout: float = 30.0,
) -> dict:
    """
    POST secrets to the simulate agent's /_logstash/keystore/sync endpoint.
    """
    url = agent_base_url.rstrip("/") + "/_logstash/keystore/sync"
    payload = {
        "secrets": secrets,
        "password": password,
        "restart": restart,
    }
    logger.info(
        "Syncing %d keystore secret(s) to %s (authenticated=%s)",
        len(secrets),
        url,
        bool(password),
    )
    resp = requests.post(url, json=payload, timeout=timeout, verify=False)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Keystore sync failed ({resp.status_code}): {resp.text[:500]}"
        )
    try:
        return resp.json()
    except Exception:
        return {"status": "ok", "raw": resp.text}


def maybe_sync_keystore_for_simulation(
    *,
    agent_base_url: str,
    components: Any = None,
    pipeline_text: str = "",
    ls_id=None,
    policy_id=None,
    policy_name=None,
) -> Optional[dict]:
    """
    If the pipeline/components reference ${...} vars, clone the source policy
    keystore to the simulate agent. Returns sync result or None if skipped.
    """
    refs: set[str] = set()
    refs |= find_keystore_refs_in_obj(components)
    refs |= find_keystore_refs_in_text(pipeline_text or "")
    if not refs:
        logger.debug("No keystore variable refs — skipping keystore sync")
        return None

    policy = resolve_source_policy(ls_id=ls_id, policy_id=policy_id, policy_name=policy_name)
    if not policy:
        logger.warning(
            "Pipeline references keystore vars %s but no source policy found",
            sorted(refs),
        )
        return None

    secrets, password = collect_policy_secrets(policy)
    if not secrets:
        logger.warning(
            "Policy '%s' has keystore refs %s but no user keystore entries",
            policy.name,
            sorted(refs),
        )
        # Still create empty keystore so Logstash doesn't fail hard on missing file
        secrets = {}

    # v1: full-clone all user secrets (not only referenced keys)
    return sync_keystore_to_agent(
        agent_base_url, secrets, password, restart=True
    )
