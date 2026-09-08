#!/usr/bin/env python3
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Rebuild `grounding.json` from compiled MIB JSON.

`./mib_json` inputs are gitignored; only `grounding.json` is committed.

Note:
    pysmi `mibdump` aborts the whole batch if one dependency fails to parse, so
    compile MIBs individually. BGP4-MIB and LLDP-MIB currently fail on an
    RFC-1212 grammar bug via RMON and are omitted.

Examples:
    uvx --from pysmi mibdump --destination-format json \\
        --destination-directory ./mib_json IF-MIB SNMPv2-MIB
    python3 build_grounding.py
"""
import json
import os
import sys

# import the flattener from the SNMP package module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from snmp_grounding import build_grounding  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
g = build_grounding(os.path.join(HERE, "mib_json"))
out = os.path.join(HERE, "grounding.json")
with open(out, "w") as f:
    json.dump(g, f)
mibs = sorted({v["mib"] for v in g.values()})
print(f"grounding.json: {len(g)} columns from {len(mibs)} MIBs -> {out}")
print("MIBs:", ", ".join(mibs))
