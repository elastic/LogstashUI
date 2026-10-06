#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Reduce a raw SNMP walk into MIB-grounded columns plus ungrounded subtrees.

This is what `snmp-profile-author` should consume instead of a 10k–50k line
walk: names, types, and enums come from compiled MIBs so the agent does not
invent units or enum labels.

Index: `data/grounding/grounding.json` (column OID → name/mib/type/enum).
Rebuild with `data/grounding/build_grounding.py`.
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
GROUNDING_PATH = os.path.join(_HERE, "data", "grounding", "grounding.json")

# Textual conventions whose enums pysmi does not inline (defined in SNMPv2-TC etc.)
TC_ENUMS = {"TruthValue": {1: "true", 2: "false"}}


def build_grounding(json_dir):
    """Flatten pysmi-compiled MIB JSON into `{oid: entry}`.

    Each entry keeps authoring fields only: name, mib, type, enum, nodetype,
    access, optional units, and table/index for columns.
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
    """Load the persisted grounding index.

    Returns:
        Empty dict (not an error) if the file is missing, so importing this module
        cannot crash the Django app.
    """
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
    """Group walk lines by MIB column OID and list unmatched subtrees.

    Args:
        walk_text: Raw SNMP walk text (`oid = value` lines).
        grounding: Optional OID index; defaults to the module-level `GROUNDING`.
        max_index_depth: Max instance arcs stripped when matching a column OID.

    Returns:
        Tuple `(grounded_columns, ungrounded_subtrees)` where columns include
        name/type/enum/instances/sample, and ungrounded is `(prefix, count)` pairs.
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
