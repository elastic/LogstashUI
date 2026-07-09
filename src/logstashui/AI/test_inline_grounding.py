#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.
"""
Unit tests for inline grounding (AI/inline_grounding.py) and the assemble/send seam
in AI/agent_client.py. No network / no live LLM: a temp SNMP/data dir is used so the
selection logic is deterministic.
"""
import json
import os
import tempfile
from unittest import mock

from django.test import SimpleTestCase

from AI import inline_grounding as ig
from AI import agent_client


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
        self.assertTrue(ig._relevant({"vendor": "Any"}, "Arista"))       # Any always
        self.assertTrue(ig._relevant({"vendor": ""}, "whatever"))        # blank always
        self.assertTrue(ig._relevant({"vendor": "Arista"}, "Arista Networks EOS"))  # substring match
        self.assertFalse(ig._relevant({"vendor": "Cisco"}, "Arista"))    # other vendor excluded
        self.assertFalse(ig._relevant({"vendor": "Cisco"}, ""))          # no vendor -> no match

    def test_grounding_includes_generic_and_vendor_match_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed(tmp)
            with mock.patch.object(ig, "_DATA", tmp):
                g = ig.build_grounding("Arista Networks EOS 4.36")
        self.assertIn("NAMING DICT", g)          # schema
        self.assertIn("std_x", g)                # mib refs
        self.assertIn("generic_interfaces", g)   # generic always
        self.assertIn("arista_x", g)             # vendor match included
        self.assertNotIn("cisco_x", g)           # other vendor excluded (no noise)

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


class AssembleRequestTests(SimpleTestCase):
    def test_grounding_goes_in_system_task_in_user(self):
        with mock.patch.object(ig, "load_instructions", return_value="RULES"), \
             mock.patch.object(ig, "build_grounding", return_value="GROUNDING-BLOCK"):
            system, user = agent_client.assemble_request(
                "Arista sysDescr", "walk-summary", "Arista", "arista_edge_ai")
        # grounding + instructions are inline in the system prompt (no KB / no tool)
        self.assertIn("RULES", system)
        self.assertIn("GROUNDING-BLOCK", system)
        # the per-device task (incl. the required profile name) is the user message
        self.assertIn("arista_edge_ai", user)
        self.assertIn("walk-summary", user)


class SendViaAgentBuilderTests(SimpleTestCase):
    def test_inline_payload_overrides_instructions_and_disables_tools(self):
        captured = {}

        class Resp:
            status_code = 200
            def json(self):
                return {"ok": True}

        def fake_post(url, headers=None, data=None, verify=None, timeout=None):
            captured["url"] = url
            captured["body"] = json.loads(data)
            return Resp()

        settings = mock.Mock(agent_url="https://kb.example", agent_id="snmp-profile-author",
                             verify_tls=True)
        settings.get_api_key.return_value = "k"
        with mock.patch.object(agent_client.requests, "post", fake_post):
            out = agent_client.send_via_agent_builder(settings, "SYS", "USER")
        self.assertEqual(out, {"ok": True})
        body = captured["body"]
        self.assertEqual(body["input"], "USER")
        self.assertEqual(body["configuration_overrides"]["instructions"], "SYS")
        self.assertEqual(body["configuration_overrides"]["tools"], [])  # no KB tool
        self.assertTrue(captured["url"].endswith("/api/agent_builder/converse"))
