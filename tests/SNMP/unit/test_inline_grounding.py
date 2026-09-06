#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.
"""
Unit tests for SNMP/inline_grounding.py.

No network / no live LLM: a temp data dir is used so the selection logic is
deterministic.
"""
import json
import os
import tempfile
from unittest import mock

from django.test import SimpleTestCase

from SNMP import inline_grounding as ig


def _seed(tmp):
    for sub in ("official_profiles", "schema_reference", "mib_reference"):
        os.makedirs(os.path.join(tmp, sub))
    with open(os.path.join(tmp, "authoring_instructions.md"), "w") as f:
        f.write("AUTHORING RULES")
    with open(os.path.join(tmp, "schema_reference", "s.md"), "w") as f:
        f.write("NAMING DICT")
    with open(os.path.join(tmp, "mib_reference", "std_x.json"), "w") as f:
        json.dump({"name": "std_x"}, f)
    for name, vendor in [("generic_interfaces", "Any"), ("cisco_x", "Cisco"), ("arista_x", "Arista")]:
        with open(os.path.join(tmp, "official_profiles", f"{name}.json"), "w") as f:
            json.dump({"name": name, "vendor": vendor, "get": {"o": "1"}}, f)


class InlineGroundingTests(SimpleTestCase):
    def test_relevance_rules(self):
        self.assertTrue(ig._relevant({"vendor": "Any"}, "Arista"))
        self.assertTrue(ig._relevant({"vendor": ""}, "whatever"))
        self.assertTrue(ig._relevant({"vendor": "Arista"}, "Arista Networks EOS"))
        self.assertFalse(ig._relevant({"vendor": "Cisco"}, "Arista"))
        self.assertFalse(ig._relevant({"vendor": "Cisco"}, ""))

    def test_grounding_includes_generic_and_vendor_match_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed(tmp)
            with mock.patch.object(ig, "_DATA", tmp):
                g = ig.build_grounding("Arista Networks EOS 4.36")
        self.assertIn("NAMING DICT", g)
        self.assertIn("std_x", g)
        self.assertIn("generic_interfaces", g)
        self.assertIn("arista_x", g)
        self.assertNotIn("cisco_x", g)

    def test_grounding_has_all_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed(tmp)
            with mock.patch.object(ig, "_DATA", tmp):
                g = ig.build_grounding("Any")
        self.assertIn("FIELD NAMING SCHEMA", g)
        self.assertIn("STANDARD-MIB REFERENCES", g)
        self.assertIn("REFERENCE PROFILES", g)

    def test_load_instructions_reads_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed(tmp)
            with mock.patch.object(ig, "_DATA", tmp):
                self.assertEqual(ig.load_instructions(), "AUTHORING RULES")
