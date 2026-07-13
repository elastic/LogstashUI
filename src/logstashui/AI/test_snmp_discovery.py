#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.
"""
Unit tests for the AI-onboarding SNMP discovery walk (AI/snmp_discovery.py).

These use an in-memory fake SNMP agent (no live device / no network) so the
column-striding behaviour is locked in for CI. They guard the two regressions that
motivated the column-striding rewrite:
  1. wide tables must be COLUMN-complete (every column sampled, not just the first few);
  2. the walk must NOT depend on crafted out-of-range indices — net-snmp answers a
     GETNEXT of `col.<huge>` by wrapping to the column's first row, which would loop.
"""
import asyncio
from unittest import mock

from django.test import SimpleTestCase

from AI import snmp_discovery as sd


def _t(oid):
    return tuple(int(x) for x in oid.split("."))


class FakeAgent:
    """A minimal in-memory SNMP agent supporting GETNEXT over a fixed OID set."""

    def __init__(self, leaves, wrap=False):
        # leaves: {oid_str: value_str}
        self.items = sorted((_t(k), k, v) for k, v in leaves.items())
        self.wrap = wrap          # emulate net-snmp's wrap-on-out-of-range-index
        self.requests = []        # every OID asked for (to assert the stride shape)

    def getnext(self, oid):
        self.requests.append(oid)
        req = _t(oid)
        if self.wrap and req and req[-1] >= 2 ** 31:
            # net-snmp: GETNEXT of an out-of-range index returns the column's first row
            prefix = req[:-1]
            for t, k, v in self.items:
                if t[:len(prefix)] == prefix and len(t) > len(prefix):
                    return k, v
        for t, k, v in self.items:
            if t > req:
                return k, v
        return None


def _patched(agent):
    async def fake_next_cmd(*args, **kwargs):
        oid = args[4]  # ObjectType(ObjectIdentity(current)) -> current (patched to str)
        res = agent.getnext(oid)
        if res is None:
            return (None, 0, 0, [])
        return (None, 0, 0, [res])   # var_binds[0] = (oid_str, value_str)

    return mock.patch.multiple(
        sd,
        next_cmd=fake_next_cmd,
        ObjectType=lambda x: x,
        ObjectIdentity=lambda s: str(s),
        ContextData=lambda: None,
    )


IFTABLE = "1.3.6.1.2.1.2.2.1"


def _iftable(ncols=22, nrows=5):
    return {f"{IFTABLE}.{c}.{r}": f"v{c}.{r}"
            for c in range(1, ncols + 1) for r in range(1, nrows + 1)}


class ColumnStridingWalkTests(SimpleTestCase):
    def _walk(self, agent, root=IFTABLE):
        with _patched(agent):
            return asyncio.run(sd._walk_root(None, None, None, root))

    def test_samples_every_column_exactly_once(self):
        agent = FakeAgent(_iftable(22, 5))
        found = self._walk(agent)
        cols = sorted({k[len(IFTABLE) + 1:].split(".")[0] for k in found}, key=int)
        self.assertEqual(len(found), 22, "should sample one leaf per column")
        self.assertEqual(cols, [str(i) for i in range(1, 23)], "all 22 columns covered")

    def test_stride_increments_column_and_never_crafts_large_index(self):
        agent = FakeAgent(_iftable(22, 5))
        self._walk(agent)
        rootlen = len(_t(IFTABLE))
        for oid in agent.requests:
            arcs = _t(oid)
            self.assertTrue(all(a < 2 ** 32 for a in arcs),
                            f"out-of-range OID arc requested: {oid}")
            if oid != IFTABLE:
                extra = arcs[rootlen:]
                self.assertEqual(len(extra), 1,
                                 f"column advance must be root.<col>, got {oid}")

    def test_full_coverage_on_netsnmp_wrapping_agent(self):
        # If the walk ever appended a large index it would loop here and miss columns.
        agent = FakeAgent(_iftable(22, 5), wrap=True)
        found = self._walk(agent)
        self.assertEqual(len(found), 22, "column stride must not rely on out-of-range indices")

    def test_terminates_and_respects_column_cap(self):
        agent = FakeAgent(_iftable(200, 2))  # more columns than MAX_COLS_PER_ROOT
        found = self._walk(agent)
        self.assertLessEqual(len(found), sd.MAX_COLS_PER_ROOT)

    def test_scalar_group_samples_each_scalar(self):
        root = "1.3.6.1.2.1.1"
        agent = FakeAgent({f"{root}.{i}.0": f"s{i}" for i in range(1, 10)})
        found = self._walk(agent, root)
        self.assertEqual(len(found), 9)

    def test_stops_when_leaving_the_root_subtree(self):
        leaves = _iftable(3, 2)
        leaves["1.3.6.1.2.1.2.2.2.1"] = "sibling"  # outside IFTABLE
        agent = FakeAgent(leaves)
        found = self._walk(agent)
        self.assertTrue(all(k.startswith(IFTABLE + ".") for k in found))


class DiscoverSummaryTests(SimpleTestCase):
    def test_summary_lists_all_columns_not_truncated(self):
        # Regression guard for the old `list(leaves.items())[:12]` cap.
        pop = {"interfaces": {f"{IFTABLE}.{c}.1": f"v{c}" for c in range(1, 23)}}

        async def fake_discover(ip, port, community, version):
            return "FakeOS 1.0", pop

        with mock.patch.object(sd, "_discover", fake_discover):
            _, _, summary = sd.discover_device("192.0.2.1")
        listed = [l for l in summary.splitlines() if l.strip().startswith(IFTABLE)]
        self.assertEqual(len(listed), 22, "summary must not truncate columns")
