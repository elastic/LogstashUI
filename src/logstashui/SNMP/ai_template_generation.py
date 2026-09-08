#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.
"""SSE stream that turns an SNMP walk into AI-authored templates and profiles.

Public entry point is `stream_template_generation`, which yields SSE strings for
Django `StreamingHttpResponse`.

Pipeline:
    1. `snmp_grounding.reduce_and_ground` condenses the walk into MIB-grounded
       columns locally.
    2. `inline_grounding.build_grounding(vendor)` sends schema, standard-MIB
       references, and vendor-filtered profiles inline via
       `configuration_overrides.instructions`.
    3. `AgentBuilder.invoke_agent` streams the `snmp-profile-author` agent.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENT_JSON = os.path.join(_HERE, 'assets', 'device_template_generation', 'agents', 'snmp-profile-author.json')


# ── Vendor inference ──────────────────────────────────────────────────────────

_VENDOR_PREFIXES = {
    "CISCO":    "Cisco",
    "DELL":     "Dell",
    "HP":       "HP",
    "JUNIPER":  "Juniper",
    "ARISTA":   "Arista",
    "BROCADE":  "Brocade",
    "NETGEAR":  "Netgear",
    "UBIQUITI": "Ubiquiti",
    "MIKROTIK": "MikroTik",
    "FORTINET": "Fortinet",
    "PALO":     "Palo Alto",
    "F5":       "F5",
}


def _infer_vendor(grounded_columns):
    """Return a vendor hint such as ``Cisco`` from grounded MIB prefixes, or ``""``."""
    counts = {}
    for col in grounded_columns:
        mib = (col.get("mib") or "").upper()
        for prefix, vendor in _VENDOR_PREFIXES.items():
            if mib.startswith(prefix):
                counts[vendor] = counts.get(vendor, 0) + 1
                break
    if not counts:
        return ""
    return max(counts, key=counts.get)


# ── SSE helper ────────────────────────────────────────────────────────────────

def _sse(payload):
    return f"data: {json.dumps(payload)}\n\n"


# ── Instruction assembly ──────────────────────────────────────────────────────

def _load_base_instructions():
    """Load base agent instructions from the local `snmp-profile-author` JSON."""
    try:
        with open(_AGENT_JSON, 'r', encoding='utf-8') as fh:
            agent_def = json.load(fh)
        return agent_def.get('configuration', {}).get('instructions', '')
    except Exception:
        return ''


def _assemble_instructions(grounded_columns):
    """Build `configuration_overrides.instructions` from the agent JSON plus inline grounding.

    Sends the field-naming schema, standard-MIB references, and vendor-filtered
    reference profiles rather than a flat `template_profile_context.md` dump.
    """
    from .inline_grounding import build_grounding

    base = _load_base_instructions()
    vendor = _infer_vendor(grounded_columns)
    reference_context = build_grounding(vendor)

    parts = [base]
    if reference_context:
        parts.append(reference_context)
    return "\n\n".join(p for p in parts if p)


# ── Main stream generator ─────────────────────────────────────────────────────

def stream_template_generation(connection_id, kibana_url, walk_text, inference_id):
    """Yield SSE `data:` lines for template/profile generation.

    Args:
        connection_id: Elasticsearch/Kibana connection primary key.
        kibana_url: Optional Kibana origin override.
        walk_text: Raw SNMP walk output.
        inference_id: Agent Builder inference model id.

    Yields:
        SSE strings whose JSON `phase` is one of `grounding`, `grounding_done`,
        `invoking`, `conversation_link`, `conversation_title`, `reasoning`,
        `agent_chunk`, `tool_call`, `tool_done`, `done`, or `error`.
    """
    from Common.ai.agent_builder import AgentBuilder
    from .snmp_grounding import reduce_and_ground

    if not inference_id:
        yield _sse({"phase": "error", "message": "No inference model selected."})
        return

    # ── 1. Reduce the raw walk to MIB-grounded columns ────────────────────────
    walk_line_count = len(walk_text.splitlines())
    grounded_columns, ungrounded_subtrees = reduce_and_ground(walk_text)

    yield _sse({
        "phase":   "grounding",
        "message": (
            f"Grounding walk against compiled MIBs "
            f"({walk_line_count} lines → {len(grounded_columns)} column(s), "
            f"{len(ungrounded_subtrees)} un-grounded subtree(s))…"
        ),
    })

    if not grounded_columns:
        yield _sse({
            "phase":   "error",
            "message": (
                "No walked OIDs matched a compiled MIB in the grounding index. "
                "Load the device's MIBs (see data/grounding/) and retry."
            ),
        })
        return

    yield _sse({"phase": "grounding_done"})

    # ── 2. Build the agent prompt ──────────────────────────────────────────────
    grounding_payload = json.dumps(
        {
            "grounded_columns":    grounded_columns,
            "ungrounded_subtrees": [{"prefix": p, "count": c} for p, c in ungrounded_subtrees],
        },
        separators=(",", ":"),
    )
    user_message = (
        "Below is a REDUCED, MIB-grounded SNMP walk for one device, as JSON.\n"
        "`grounded_columns` lists every walked OID column matched to a compiled MIB, "
        "with its authoritative name, type, enum, units and instance count — author "
        "ONLY from these columns; never recall or invent OIDs.\n"
        "`ungrounded_subtrees` are OID prefixes the device exposes whose MIBs are not "
        "loaded — do NOT author them; list them so the user can load the MIBs.\n"
        "Consult the SNMP Catalog in your instructions to reuse existing profiles, "
        "then produce JSON for any new profiles required.\n\n"
        f"{grounding_payload}"
    )

    # ── 3. Assemble inline instructions ───────────────────────────────────────
    full_instructions = _assemble_instructions(grounded_columns)
    configuration_overrides = {"instructions": full_instructions} if full_instructions else None

    yield _sse({
        "phase":   "invoking",
        "message": f"Invoking SNMP Profile Author ({inference_id})…",
    })

    # ── 4. Stream agent response ───────────────────────────────────────────────
    try:
        builder = AgentBuilder(
            connection_id=int(connection_id),
            kibana_url_override=kibana_url,
        )
        kibana_base = builder._kibana_url

        for chunk in builder.invoke_agent(
            'snmp-profile-author', user_message,
            inference_id=inference_id,
            configuration_overrides=configuration_overrides,
        ):
            err = chunk.get('error')
            if err:
                msg = err if isinstance(err, str) else json.dumps(err)
                yield _sse({"phase": "error", "message": msg})
                return

            event_type = chunk.get('event')
            # Agent Builder wraps the actual payload one level deep:
            # SSE data line parses to {"data": {<actual content>}}
            outer_data = chunk.get('data') or {}
            data       = outer_data.get('data') if isinstance(outer_data.get('data'), dict) else outer_data

            if event_type == 'conversation_id_set':
                conv_id = data.get('conversation_id', '')
                if conv_id:
                    conv_url = (
                        f"{kibana_base}/app/agent_builder/agents"
                        f"/snmp-profile-author/conversations/{conv_id}"
                    )
                    yield _sse({"phase": "conversation_link", "url": conv_url, "conversation_id": conv_id})

            elif event_type == 'conversation_created':
                title = data.get('title', '')
                if title:
                    yield _sse({"phase": "conversation_title", "title": title})

            elif event_type == 'reasoning':
                reasoning_text = data.get('reasoning', '')
                if reasoning_text and not data.get('transient', False):
                    yield _sse({"phase": "reasoning", "message": reasoning_text})

            elif event_type == 'message_chunk':
                text = data.get('text_chunk', '')
                if text:
                    yield _sse({"phase": "agent_chunk", "data": {"text": text}})

            elif event_type == 'tool_call':
                tool_id = data.get('tool_id', 'unknown')
                yield _sse({"phase": "tool_call", "message": f"Calling tool: {tool_id}…"})

            elif event_type == 'tool_result':
                yield _sse({"phase": "tool_done"})

            elif event_type in ('message_complete', 'round_complete', 'thinking_complete'):
                pass  # Redundant / very large — content already built from message_chunk events

    except Exception as exc:
        yield _sse({"phase": "error", "message": f"Agent invocation failed: {exc}"})
        return

    yield _sse({"phase": "done"})
