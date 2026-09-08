#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.
"""Assemble inline grounding for AI SNMP profile authoring.

Authoring instructions, field-naming schema, standard-MIB references, and
reference profiles live under `SNMP/data/` and are sent with each request.
There is no backend knowledge-base to keep in sync.
"""
import glob
import json
import os

# Resolve data path relative to this file so it works regardless of BASE_DIR.
_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_MAX_PROFILES = 40  # corpus is small + curated; a generous cap, not a real limit


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def load_instructions():
    """Return the authoring prompt from `data/authoring_instructions.md`."""
    with open(os.path.join(_DATA, "authoring_instructions.md")) as f:
        return f.read()


def _relevant(profile, vendor):
    """Keep generic/Any profiles always; keep vendor-specific ones only on a vendor match."""
    pv = (profile.get("vendor") or "").strip().lower()
    if pv in ("", "any", "generic"):
        return True
    v = (vendor or "").strip().lower()
    return bool(v) and (pv in v or v in pv)


def build_grounding(vendor):
    """Assemble schema, standard-MIB JSON, and vendor-filtered reference profiles.

    Args:
        vendor: Vendor hint used to filter official profiles.

    Returns:
        Markdown/JSON block appended to the agent's instructions.
    """
    parts = []

    schema = []
    for p in sorted(glob.glob(os.path.join(_DATA, "schema_reference", "*.md"))):
        try:
            with open(p) as f:
                schema.append(f.read())
        except Exception:
            pass
    if schema:
        parts.append("## FIELD NAMING SCHEMA (canonical — translate every OID to these names)\n"
                     + "\n\n".join(schema))

    mibs = [d for d in (_read_json(p) for p in
                        sorted(glob.glob(os.path.join(_DATA, "mib_reference", "*.json")))) if d]
    if mibs:
        parts.append("## STANDARD-MIB REFERENCES\n" + "\n".join(json.dumps(m) for m in mibs))

    profs = []
    for p in sorted(glob.glob(os.path.join(_DATA, "official_profiles", "*.json"))):
        d = _read_json(p)
        if d and _relevant(d, vendor):
            profs.append(d)
    parts.append("## REFERENCE PROFILES (reuse OIDs / field names / normalizer blocks verbatim)\n"
                 + "\n".join(json.dumps(p) for p in profs[:_MAX_PROFILES]))

    return "\n\n".join(parts)
