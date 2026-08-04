#!/usr/bin/env python3
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Django-side smoke for agent modes (policy seeds, enroll MANAGED/SIMULATE/PACKAGED).

Run inside the logstashui container:
  python manage.py shell < bin/smoke_agent_modes_django.py
or:
  cd /app/src/logstashui && python /path/to/smoke_agent_modes_django.py
"""

from __future__ import annotations

import base64
import json
import sys
import uuid


def main() -> int:
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    import django

    django.setup()

    from django.test import Client

    from PipelineManager import agent_modes as am
    from PipelineManager.models import Connection, EnrollmentToken, Policy

    build_policy_config = am.build_policy_config
    next_simulate_instance_id = am.next_simulate_instance_id
    simulate_ports = am.simulate_ports
    normalize_policy_type = getattr(am, "normalize_policy_type", lambda x: (x or "PACKAGED").upper().replace("DEFAULT", "PACKAGED") if x else "PACKAGED")
    next_managed_instance_id = getattr(am, "next_managed_instance_id", None)
    managed_ports = getattr(am, "managed_ports", None)

    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if cond:
            print(f"  OK  {msg}")
        else:
            print(f" FAIL {msg}")
            failures.append(msg)

    print("=== Agent modes Django smoke ===")

    # --- Policy seeds ---
    print("\n[1] System policies")
    by_type = {p.policy_type: p for p in Policy.objects.filter(is_system=True)}
    # Accept DEFAULT until 0025 applied; prefer PACKAGED after migration
    packaged = (
        Policy.objects.filter(policy_type="PACKAGED", is_system=True).first()
        or Policy.objects.filter(name__in=["Packaged Policy", "Default Policy"], is_system=True).first()
    )
    managed = Policy.objects.filter(policy_type="MANAGED", is_system=True).first()
    simulate = Policy.objects.filter(policy_type="SIMULATE", is_system=True).first()
    embedded = Policy.objects.filter(policy_type="EMBEDDED", is_system=True).first()

    check(packaged is not None, f"Packaged/Default system policy present ({getattr(packaged, 'policy_type', None)})")
    check(simulate is not None, "Simulate system policy present")
    check(embedded is not None, "Embedded system policy present")
    if managed is None:
        print("  WARN Managed system policy missing — migration 0025 not applied yet")
    else:
        check(True, "Managed system policy present")

    if packaged:
        check(
            normalize_policy_type(packaged.policy_type) == "PACKAGED",
            f"normalize_policy_type({packaged.policy_type!r}) → PACKAGED",
        )

    # --- build_policy_config ---
    print("\n[2] policy_config payloads")
    if packaged:
        cfg = build_policy_config(packaged)
        check(cfg["policy_type"] == "PACKAGED", "packaged policy_config type")
        check(cfg.get("agent_unit") == "logstash-agent", "packaged agent_unit")
        check(cfg.get("logstash_unit") == "logstash", "packaged logstash_unit")

    if managed and next_managed_instance_id and managed_ports:
        n = next_managed_instance_id()
        cfg = build_policy_config(managed, instance_id=n)
        ap, lp = managed_ports(n)
        check(cfg["policy_type"] == "MANAGED", "managed policy_config type")
        check(cfg["instance_id"] == n, "managed instance_id")
        check(cfg["agent_api_port"] == ap and cfg["logstash_api_port"] == lp, "managed ports")
        check(cfg["agent_unit"] == f"logstash-agent@{n}", "managed agent unit")
        check(cfg["logstash_unit"] == f"logstash-managed@{n}", "managed logstash unit")
        check("/managed-" in cfg.get("settings_path", ""), "managed path under managed-N")
    elif managed:
        print("  WARN managed helpers missing in agent_modes (stale image)")

    if simulate:
        n = next_simulate_instance_id()
        cfg = build_policy_config(simulate, instance_id=n)
        ap, lp = simulate_ports(n)
        check(cfg["policy_type"] == "SIMULATE", "simulate policy_config type")
        check(cfg["agent_api_port"] == ap, "simulate agent port")
        check(cfg["agent_unit"] == f"lsagent-simulate@{n}", "simulate agent unit")

    # --- Enroll HTTP API ---
    print("\n[3] Enroll API")
    client = Client()

    def enroll(policy: Policy, host: str, agent_id: str) -> dict:
        token, _ = EnrollmentToken.objects.get_or_create(
            policy=policy,
            name=f"smoke-{agent_id[:8]}",
            defaults={"token": f"smoke-token-{uuid.uuid4().hex}"},
        )
        payload = base64.b64encode(
            json.dumps({"enrollment_token": token.token}).encode()
        ).decode()
        resp = client.post(
            "/ConnectionManager/Enroll/",
            data=json.dumps(
                {
                    "enrollment_token": payload,
                    "host": host,
                    "agent_id": agent_id,
                }
            ),
            content_type="application/json",
            secure=True,  # SECURE_SSL_REDIRECT is on in compose
        )
        try:
            body = resp.json()
        except ValueError:
            body = {
                "success": False,
                "error": f"non-json status={resp.status_code} body={resp.content[:200]!r}",
            }
        return {"status": resp.status_code, "body": body}

    if packaged:
        r = enroll(packaged, "smoke-packaged.example", f"smoke-packaged-{uuid.uuid4().hex[:8]}")
        check(r["status"] == 200 and r["body"].get("success"), "enroll PACKAGED")
        pc = (r["body"].get("policy_config") or {})
        check(pc.get("policy_type") in ("PACKAGED", "DEFAULT") or normalize_policy_type(pc.get("policy_type")) == "PACKAGED",
              f"enroll packaged policy_type={pc.get('policy_type')}")

    if managed:
        r = enroll(managed, "smoke-managed.example", f"smoke-managed-{uuid.uuid4().hex[:8]}")
        check(r["status"] == 200 and r["body"].get("success"), "enroll MANAGED")
        pc = r["body"].get("policy_config") or {}
        check(pc.get("policy_type") == "MANAGED", "enroll managed type")
        check(pc.get("instance_id") is not None, "enroll managed instance_id")
        check(str(pc.get("agent_unit", "")).startswith("logstash-agent@"), "enroll managed agent unit")
        check("managed-" in (pc.get("path_root") or pc.get("settings_path") or ""), "enroll managed paths")
        conn = Connection.objects.filter(agent_id__startswith="smoke-managed-").order_by("-id").first()
        check(conn is not None and conn.instance_id is not None, "managed connection instance_id")

    if simulate:
        r = enroll(simulate, "smoke-sim.example", f"smoke-sim-{uuid.uuid4().hex[:8]}")
        check(r["status"] == 200 and r["body"].get("success"), "enroll SIMULATE")
        pc = r["body"].get("policy_config") or {}
        check(pc.get("policy_type") == "SIMULATE", "enroll simulate type")
        check(str(pc.get("agent_unit", "")).startswith("lsagent-simulate@"), "enroll simulate unit")

    if embedded:
        r = enroll(embedded, "should-fail.example", f"smoke-emb-{uuid.uuid4().hex[:8]}")
        check(r["status"] == 400, "enroll EMBEDDED rejected")

    # --- VERSION fields on simulate/managed ---
    print("\n[4] VERSION policy fields")
    if simulate:
        simulate.logstash_source = Policy.LogstashSource.VERSION
        simulate.logstash_version = "9.4.3"
        simulate.logstash_download_dir = "/opt/logstash-agent/logstash-versions"
        simulate.save(update_fields=["logstash_source", "logstash_version", "logstash_download_dir"])
        cfg = build_policy_config(simulate, instance_id=1)
        check(cfg.get("logstash_source") == "VERSION", "simulate VERSION source in policy_config")
        check(cfg.get("logstash_version") == "9.4.3", "simulate VERSION pin in policy_config")
        # restore SYSTEM for less surprise in long-lived smoke DBs
        simulate.logstash_source = Policy.LogstashSource.SYSTEM
        simulate.logstash_version = ""
        simulate.save(update_fields=["logstash_source", "logstash_version"])

    print("\n=== Result ===")
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
