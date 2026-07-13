#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.
"""
Inline grounding for AI SNMP profile authoring.

LogstashUI is the source of truth: the authoring instructions, the field-naming
schema, the standard-MIB references, and the reference profiles all live under
SNMP/data/ and are sent INLINE with each authoring request. There is no backend
grounding store (no KB) to keep in sync — the data travels with the request.
"""
import glob
import json
import os

from django.conf import settings

_DATA = os.path.join(settings.BASE_DIR, "SNMP", "data")
_MAX_PROFILES = 40  # corpus is small + curated; a generous cap, not a real limit


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def load_instructions():
    """The authoring prompt (source of truth), sent inline as system instructions."""
    with open(os.path.join(_DATA, "authoring_instructions.md")) as f:
        return f.read()


def _relevant(profile, vendor):
    """Keep generic/Any profiles always; vendor-specific ones only on a vendor match."""
    pv = (profile.get("vendor") or "").strip().lower()
    if pv in ("", "any", "generic"):
        return True
    v = (vendor or "").strip().lower()
    return bool(v) and (pv in v or v in pv)


def build_grounding(vendor):
    """Assemble the inline grounding block from local source-of-truth files:
    field-naming schema + standard-MIB references + relevant reference profiles."""
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
