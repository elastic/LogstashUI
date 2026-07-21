#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
SNMP walk reduce-and-ground.

Turns a raw SNMP walk into a compact, authoritative set of "grounded columns"
(name + type + enum sourced from compiled MIBs) plus an "un-grounded subtrees"
coverage report. This is what the snmp-profile-author agent should consume instead
of the raw walk: it removes the agent's need to recall MIB semantics (which is the
source of the power_mw / scrambled-enum hallucinations) and collapses 10k-50k line
walks to ~100 rows.

Pipeline role:
    walk_text --> reduce_and_ground() --> {grounded_columns, ungrounded_subtrees} --> agent

Grounding index:
    data/grounding/grounding.json  (numeric column OID -> {name, mib, type, enum, nodetype})
    Built offline from pysmi-compiled MIB JSON. See data/grounding/build_grounding.py.
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
GROUNDING_PATH = os.path.join(_HERE, "data", "grounding", "grounding.json")

# Textual conventions whose enums pysmi does not inline (defined in SNMPv2-TC etc.)
TC_ENUMS = {"TruthValue": {1: "true", 2: "false"}}


def build_grounding(json_dir):
    """Flatten pysmi-compiled MIB JSON into {oid: entry}.

    Each entry keeps only what's needed to author a profile field (functional schema),
    not documentation prose:
      name, mib, type, enum, nodetype, access
      units  (only when defined)
      table, index  (only for table columns -> how rows are keyed)
    """
    import glob
    parsed, rows = [], {}   # rows: entry_oid -> [index object names]
    for path in glob.glob(os.path.join(json_dir, "*.json")):
        mib = os.path.basename(path)[:-5]
        try:
            d = json.load(open(path))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        parsed.append((mib, d))
        for obj in d.values():
            if isinstance(obj, dict) and obj.get("nodetype") == "row" and obj.get("oid"):
                rows[obj["oid"]] = [i.get("object") for i in (obj.get("indices") or []) if i.get("object")]

    g = {}
    for mib, d in parsed:
        for name, obj in d.items():
            if not isinstance(obj, dict) or obj.get("nodetype") not in ("column", "scalar"):
                continue
            oid = obj.get("oid")
            if not oid:
                continue
            syn = obj.get("syntax") or {}
            typ = syn.get("type")
            cons = syn.get("constraints") or {}
            if "enumeration" in cons:
                enum = {int(v): k for k, v in cons["enumeration"].items()}
            else:
                enum = TC_ENUMS.get(typ)
            entry = {"name": name, "mib": mib, "type": typ, "enum": enum,
                     "nodetype": obj.get("nodetype"), "access": obj.get("maxaccess")}
            if obj.get("units"):
                entry["units"] = obj["units"]
            if obj.get("nodetype") == "column":
                parent = oid.rsplit(".", 1)[0]          # table row (entry) OID
                if parent in rows:
                    entry["table"] = parent
                    entry["index"] = rows[parent]
            g[oid] = entry
    return g


def load_grounding(path=GROUNDING_PATH):
    """Load the persisted grounding index. Returns {} (not an error) if missing,
    so importing this module never crashes the Django app."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


# Loaded once at import; the views layer references this.
GROUNDING = load_grounding()


_LINE = re.compile(r'^(\d+(?:\.\d+)+)\s*[=\t]\s*(.*)$')


def _parse(walk_text):
    for line in walk_text.splitlines():
        m = _LINE.match(line)
        if m:
            yield m.group(1), m.group(2)


def reduce_and_ground(walk_text, grounding=None, max_index_depth=14):
    """
    walk_text -> (grounded_columns, ungrounded_subtrees)

    grounded_columns: list of {oid, name, mib, type, enum, instances, sample}
                      grouped by the real MIB column OID (handles multi-index tables).
    ungrounded_subtrees: list of (prefix, count) for OIDs with no MIB match
                         -> "device exposes these subtrees; load their MIBs to cover them".
    """
    if grounding is None:
        grounding = GROUNDING
    cols = set(grounding)
    grouped, ungrounded = {}, {}
    for oid, val in _parse(walk_text):
        parts = oid.split('.')
        col = None
        # strip trailing instance arcs (longest/deepest match first) until a known column/scalar OID
        for d in range(0, min(max_index_depth, len(parts) - 1) + 1):
            cand = '.'.join(parts[:len(parts) - d])
            if cand in cols:
                col = cand
                break
        if col:
            e = grouped.setdefault(col, {"count": 0, "sample": val})
            e["count"] += 1
        else:
            pfx = '.'.join(parts[:9])
            ungrounded[pfx] = ungrounded.get(pfx, 0) + 1
    grounded = []
    for col, info in grouped.items():
        m = grounding[col]
        row = {"oid": col, "name": m["name"], "mib": m["mib"], "type": m["type"],
               "enum": m.get("enum"), "nodetype": m.get("nodetype"), "access": m.get("access"),
               "instances": info["count"], "sample": info["sample"][:50]}
        if m.get("units"):
            row["units"] = m["units"]
        if m.get("index"):
            row["table"], row["index"] = m["table"], m["index"]
        grounded.append(row)
    grounded.sort(key=lambda r: [int(x) for x in r["oid"].split('.')])
    ung = sorted(ungrounded.items(), key=lambda kv: -kv[1])
    return grounded, ung
