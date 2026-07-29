#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Detect Logstash keystore/env var references in pipeline configs and clone
source-policy secrets onto a simulate agent before simulation runs.

Only syncs when:
  - the pipeline is associated with a policy (ls_id / policy_id / policy_name), and
  - that policy's keystore contents differ from the simulate instance keystore.

Matching contents skip write and Logstash restart.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import requests

from PipelineManager.models import Policy

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
    return found


def resolve_source_policy(ls_id=None, policy_id=None, policy_name=None) -> Optional[Policy]:
    """
    Resolve the policy whose keystore should be cloned for simulation.

    Only returns a policy when the pipeline is explicitly associated with one
    (ls_id / policy_id / policy_name). No silent fallback to Default Policy —
    without an association we cannot upload secrets.
    """
    if policy_id is not None and policy_id != "":
        try:
            return Policy.objects.get(pk=int(policy_id))
        except (Policy.DoesNotExist, TypeError, ValueError):
            logger.warning("policy_id=%s not found", policy_id)
            return None
    if ls_id is not None and ls_id != "":
        try:
            return Policy.objects.get(pk=int(ls_id))
        except (Policy.DoesNotExist, TypeError, ValueError):
            logger.warning("ls_id=%s not found as policy", ls_id)
            return None
    if policy_name:
        try:
            return Policy.objects.get(name=policy_name)
        except Policy.DoesNotExist:
            logger.warning("policy_name=%s not found", policy_name)
            return None
    return None


def collect_policy_secrets(policy: Policy) -> tuple[dict[str, str], Optional[str]]:
    """
    Return (secrets_map, password_or_none) for all user-managed keystore entries.
    Keys are lowercased to match Logstash keystore storage.
    """
    secrets: dict[str, str] = {}
    for entry in policy.keystore_entries.filter(managed_by="user"):
        val = entry.get_key_value()
        if val is not None:
            secrets[entry.key_name.lower()] = val
    password = policy.get_keystore_password() or None
    return secrets, password


def fetch_agent_keystore(
    agent_base_url: str, *, timeout: float = 15.0
) -> dict:
    """
    GET current secrets from the simulate agent.
    Returns dict with keys: exists, secrets, secrets_count, keys.
    """
    url = agent_base_url.rstrip("/") + "/_logstash/keystore"
    resp = requests.get(url, timeout=timeout, verify=False)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Failed to read agent keystore ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()


def secrets_equal(desired: dict[str, str], current: dict[str, str]) -> bool:
    """Compare secret maps (keys lowercased)."""
    d = {str(k).lower(): str(v) for k, v in (desired or {}).items()}
    c = {str(k).lower(): str(v) for k, v in (current or {}).items()}
    # Ignore seed if present on either side
    d.pop("keystore.seed", None)
    c.pop("keystore.seed", None)
    return d == c


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
    Agent skips write/restart when contents already match.
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
    If the pipeline references ${...} and is associated with a policy, ensure
    the simulate agent keystore matches that policy.

    Flow:
      1. No ${...} refs → skip
      2. No policy association → skip (cannot upload)
      3. Load policy secrets; load agent keystore
      4. If equal → skip write/restart
      5. Else POST sync (agent restarts only on actual write)
    """
    refs: set[str] = set()
    refs |= find_keystore_refs_in_obj(components)
    refs |= find_keystore_refs_in_text(pipeline_text or "")
    if not refs:
        logger.debug("No keystore variable refs — skipping keystore sync")
        return None

    policy = resolve_source_policy(
        ls_id=ls_id, policy_id=policy_id, policy_name=policy_name
    )
    if not policy:
        logger.info(
            "Pipeline references keystore vars %s but has no associated policy — "
            "skipping keystore upload",
            sorted(refs),
        )
        return {
            "status": "skipped",
            "reason": "no_policy",
            "refs": sorted(refs),
            "unchanged": True,
            "restarted": False,
        }

    secrets, password = collect_policy_secrets(policy)

    # Compare to simulate instance before writing
    try:
        agent_ks = fetch_agent_keystore(agent_base_url)
        current = agent_ks.get("secrets") or {}
        if secrets_equal(secrets, current):
            logger.info(
                "Simulate keystore already matches policy '%s' (%d secret(s)) — "
                "skip write/restart",
                policy.name,
                len(secrets),
            )
            return {
                "status": "success",
                "unchanged": True,
                "restarted": False,
                "secrets_count": len(secrets),
                "policy": policy.name,
            }
    except Exception as fetch_err:
        logger.warning(
            "Could not read agent keystore for comparison (%s); will attempt sync",
            fetch_err,
        )

    result = sync_keystore_to_agent(
        agent_base_url, secrets, password, restart=True
    )
    result["policy"] = policy.name
    if result.get("unchanged"):
        logger.info(
            "Agent reported keystore unchanged for policy '%s' — no restart",
            policy.name,
        )
    else:
        logger.info(
            "Keystore updated on agent from policy '%s' (restarted=%s)",
            policy.name,
            result.get("restarted"),
        )
    return result
