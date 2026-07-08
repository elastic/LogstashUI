#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.
"""
Client for the external AI authoring agent (Elastic Agent Builder).
Calls POST {agent_url}/api/agent_builder/converse and extracts the authored
SNMP profile JSON from the response.
"""
import json
import re
import requests


def _build_prompt(sys_descr, walk_summary, vendor, proposed_name):
    return (
        "You are authoring a LogstashUI SNMP profile for a newly discovered device.\n\n"
        f"Device sysDescr:\n{sys_descr}\n\n"
        f"Vendor (best guess): {vendor or 'unknown'}\n\n"
        "A LIVE SNMP walk of the device returned data for the following OIDs. "
        "Author the profile using ONLY OIDs confirmed present below (these are verified). "
        "Prefer standard MIBs; group scalars into `get` and indexed/columnar data into `table` "
        "with ECS-style field names.\n\n"
        f"{walk_summary}\n\n"
        f"Name the profile exactly: {proposed_name}\n"
        "Return ONLY the profile JSON object with keys: name, description, vendor, product, "
        "get, walk, table. If any OID is not confirmed by the walk above, place it under an "
        "\"_unverified\" array instead of in get/walk/table."
    )


def _iter_json_objects(text):
    """Yield JSON objects embedded anywhere in a string (handles ```json fences, prose)."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
            if isinstance(obj, dict):
                yield obj
        except Exception:
            continue


def _collect(node, dict_leaves, str_leaves):
    """Recursively gather every dict and string in the response structure."""
    if isinstance(node, dict):
        dict_leaves.append(node)
        for v in node.values():
            _collect(v, dict_leaves, str_leaves)
    elif isinstance(node, list):
        for v in node:
            _collect(v, dict_leaves, str_leaves)
    elif isinstance(node, str):
        str_leaves.append(node)


def _is_profile(o):
    return isinstance(o, dict) and o.get("name") and ("get" in o or "table" in o or "_unverified" in o)


def _extract_profile(resp_json, proposed_name):
    """Find the authored profile. The agent embeds it either as a structured dict or as
    JSON inside an assistant-message string, so we search BOTH dict and string leaves."""
    dict_leaves, str_leaves = [], []
    _collect(resp_json, dict_leaves, str_leaves)

    candidates = [o for o in dict_leaves if _is_profile(o)]
    for s in str_leaves:
        for o in _iter_json_objects(s):
            if _is_profile(o):
                candidates.append(o)

    # 1) exact name match (the agent was told to use this exact name → the final answer)
    for o in candidates:
        if o.get("name") == proposed_name:
            return o
    # 2) richest profile-shaped object with actual OIDs
    sized = [o for o in candidates if o.get("get") or o.get("table")]
    if sized:
        return max(sized, key=lambda o: len(json.dumps(o)))
    return None


def generate_profile(settings, *, sys_descr, walk_summary, vendor, proposed_name, timeout_s=120):
    """
    Returns dict: {profile_json:{get,walk,table}, unverified:[], agent_notes:str, vendor, name}
    Raises RuntimeError on transport / auth / parse failure.
    """
    base = settings.agent_url.rstrip("/")
    url = f"{base}/api/agent_builder/converse"
    headers = {
        "Authorization": f"ApiKey {settings.get_api_key()}",
        "kbn-xsrf": "true",
        "Content-Type": "application/json",
    }
    payload = {"agent_id": settings.agent_id,
               "input": _build_prompt(sys_descr, walk_summary, vendor, proposed_name)}
    r = requests.post(url, headers=headers, data=json.dumps(payload),
                      verify=settings.verify_tls, timeout=timeout_s)
    if r.status_code != 200:
        raise RuntimeError(f"Agent call failed (HTTP {r.status_code}): {r.text[:300]}")
    resp = r.json()
    profile = _extract_profile(resp, proposed_name)
    if not profile:
        raise RuntimeError("Could not extract a profile from the agent response")

    unverified = profile.pop("_unverified", []) or []
    profile_json = {k: profile.get(k, {}) for k in ("get", "walk", "table")}
    # Carry the agent-authored normalizers so approved profiles ship SCALED metrics
    # (paired with _get_device_profiles reading Profile.normalizers at pipeline gen).
    normalizers = profile.get("normalizers", []) or []
    if not isinstance(normalizers, list):
        normalizers = []
    # final assistant text for provenance display
    notes = ""
    for o in _iter_json_objects(json.dumps(resp)):
        pass
    try:
        steps = resp.get("steps", [])
        texts = [s.get("text") or s.get("reasoning") for s in steps if isinstance(s, dict)]
        notes = next((t for t in reversed(texts) if t), "")[:4000]
    except Exception:
        notes = ""
    return {
        "name": profile.get("name", proposed_name),
        "vendor": profile.get("vendor", vendor),
        "description": profile.get("description", ""),
        "profile_json": profile_json,
        "normalizers": normalizers,
        "unverified": unverified,
        "agent_notes": notes,
    }
