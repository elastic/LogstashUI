#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.
"""
Live SNMP discovery walk used to GROUND the AI agent on OIDs the device actually
exposes — so authored profiles use verified OIDs instead of guesses.

Reuses the same pysnmp v3arch asyncio API as SNMP/snmp_test.py.
"""
import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, get_cmd, next_cmd,
)

# Curated candidate MIB roots — broad but bounded. We only keep what returns data.
# Table roots are anchored at the *Entry* node so the arc immediately after the root
# is the table COLUMN (see _walk_root's column-striding).
CANDIDATE_ROOTS = {
    "system":         "1.3.6.1.2.1.1",
    "interfaces":     "1.3.6.1.2.1.2.2.1",
    "interfaces_x":   "1.3.6.1.2.1.31.1.1.1",
    "host_system":    "1.3.6.1.2.1.25.1",
    "host_memory":    "1.3.6.1.2.1.25.2.2",     # hrMemorySize (scalar)
    "host_storage":   "1.3.6.1.2.1.25.2.3.1",   # hrStorageEntry
    "host_processor": "1.3.6.1.2.1.25.3.3.1",   # hrProcessorEntry
    "entity_sensors": "1.3.6.1.2.1.99.1.1.1",
    "bgp_peers":      "1.3.6.1.2.1.15.3.1",
    "tcp":            "1.3.6.1.2.1.6",
    "udp":            "1.3.6.1.2.1.7",
    "ip":             "1.3.6.1.2.1.4.1",
    "lldp_remote":    "1.0.8802.1.1.2.1.4",
}
MAX_COLS_PER_ROOT = 64
SYS_DESCR = "1.3.6.1.2.1.1.1.0"


def _fmt(value):
    try:
        return value.prettyPrint()
    except Exception:
        return str(value)


def _community(community, version):
    return CommunityData(community, mpModel=0 if str(version) == "1" else 1)


async def _walk_root(engine, auth, transport, root):
    """Column-striding walk: sample ONE representative leaf per column, then jump to
    the NEXT column (root.<col+1>) instead of walking every row.

    Row-first lexicographic walking exhausts the budget on the leading columns of
    wide / multi-row tables, so later columns (ifOperStatus, ifHCInOctets, ...) are
    never sampled — the agent then flags those present-but-unseen OIDs as unverified.
    We advance by incrementing the column arc (NOT by appending a large index): some
    agents (net-snmp) do not advance past a crafted out-of-range index and loop.
    """
    found = {}
    current = root
    for _ in range(MAX_COLS_PER_ROOT):
        ei, es, ex, var_binds = await next_cmd(
            engine, auth, transport, ContextData(),
            ObjectType(ObjectIdentity(current)),
            lexicographicMode=False)
        if ei or es or not var_binds:
            break
        oid, val = var_binds[0]
        oid_str = str(oid)
        if not oid_str.startswith(root + ".") or oid_str in found:
            break  # left the root subtree, or no forward progress
        found[oid_str] = _fmt(val)
        rest = oid_str[len(root) + 1:].split(".")
        try:
            # table cell root.<column>.<index...> — stride to the next column
            current = f"{root}.{int(rest[0]) + 1}" if len(rest) >= 2 else oid_str
        except ValueError:
            current = oid_str
    return found


async def _discover(ip, port, community, version):
    engine = SnmpEngine()
    auth = _community(community, version)
    transport = await UdpTransportTarget.create((ip, int(port)))

    # sysDescr first (also a reachability check)
    ei, es, ex, vb = await get_cmd(engine, auth, transport, ContextData(),
                                   ObjectType(ObjectIdentity(SYS_DESCR)))
    if ei:
        raise RuntimeError(f"SNMP unreachable: {ei}")
    sys_descr = _fmt(vb[0][1]) if vb else ""

    populated = {}
    for name, root in CANDIDATE_ROOTS.items():
        leaves = await _walk_root(engine, auth, transport, root)
        if leaves:
            populated[name] = leaves
    return sys_descr, populated


def discover_device(ip, port=161, community="public", version="2c", timeout_s=60):
    """Synchronous entry point. Returns (sys_descr, populated_dict, summary_text)."""
    sys_descr, populated = asyncio.run(asyncio.wait_for(_discover(ip, port, community, version), timeout_s))

    lines = [f"sysDescr: {sys_descr}", ""]
    for name, leaves in populated.items():
        lines.append(f"## {name}  ({len(leaves)} columns sampled)")
        for oid, val in leaves.items():
            v = (val[:60] + "…") if len(val) > 60 else val
            lines.append(f"  {oid} = {v}")
        lines.append("")
    summary = "\n".join(lines)
    return sys_descr, populated, summary
