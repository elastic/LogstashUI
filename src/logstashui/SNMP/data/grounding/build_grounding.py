#!/usr/bin/env python3
"""
Rebuild grounding.json from compiled MIB JSON.

The compiled ./mib_json build inputs are gitignored; only grounding.json (the
runtime artifact the app loads) is committed. Regenerate them as below.

Step 1 - compile MIBs to JSON (auto-fetches sources; add MIB names to extend coverage):

    uvx --from pysmi mibdump --destination-format json \
        --destination-directory ./mib_json \
        POWER-ETHERNET-MIB IF-MIB ENTITY-MIB SNMPv2-MIB HOST-RESOURCES-MIB \
        UCD-SNMP-MIB IP-MIB OSPF-MIB BRIDGE-MIB EtherLike-MIB
        # ...add vendor MIBs as needed

    GOTCHA (upstream pysmi): mibdump aborts the WHOLE batch if any one dependency
    fails to parse, so compile the MIBs INDIVIDUALLY (they accumulate in ./mib_json)
    and skip failures. BGP4-MIB and LLDP-MIB currently fail on a pysmi RFC-1212
    grammar bug (via their RMON dependency) and are omitted; retry when pysmi fixes
    it or supply a clean RFC-1212 source.

Step 2 - flatten to grounding.json:

    python3 build_grounding.py

Adding coverage = add MIB names in step 1 and rerun. No hand-maintenance of OIDs/enums.
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
