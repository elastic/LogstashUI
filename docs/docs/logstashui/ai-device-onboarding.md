# AI Device Onboarding — Build & Deploy Runbook

Discover an unmonitored SNMP device → let the agent author a profile from a live walk →
**review and approve** → deploy. This is an experimental feature (enable via
Management → Settings → Experimental mode).

## What this release adds

- **AI Device Onboarding** (`/AI/Onboarding/`) — discover → author → approve → deploy, with a
  human approval gate. `GenerateDraft` runs a live SNMP walk to ground the agent; `ApproveDraft`
  creates the `Profile` + `DeviceTemplate` server-side and attaches them.
- **Normalizers end-to-end** — authored profiles carry a `normalizers[]` array
  (`multiply` / `ratio` / `translate`) captured from the agent → `DraftDefinition.normalizers` →
  `Profile.normalizers` → the generated Logstash pipeline, so metrics ship scaled/decoded.
- **Fix** — user/AI-authored profile normalizers are no longer dropped at pipeline generation
  (`_get_device_profiles` now reads `Profile.normalizers`, not just inline `profile_data`).

## Components

| Repo | Provides |
|------|----------|
| **LogstashUI** (this repo) | Everything needed at runtime: AI Onboarding models/views/UI, `agent_client`, `snmp_discovery`, `inline_grounding`, the pipeline-generator normalizer fix, AND all grounding data under `SNMP/data/` (`official_profiles/`, `official_device_templates/`, `authoring_instructions.md`, `schema_reference/`, `mib_reference/`). Migrations: `AI/0001`, `AI/0002`. |
| **SNMP AB-tool** (`RCA/lab/snmp-ab-authoring-tool`) | **Optional — not required at runtime.** Authoring/validation tooling and the now-optional KB path (`deploy.sh`, `deploy-agent.py`, `seed/load-kb.py`) if you ever want retrieval at scale. |

## Grounding is inline — no backend KB

The LLM is grounded **entirely from local `SNMP/data/` files, sent with each request** (converse
`configuration_overrides`: instructions overridden, `tools: []`). There is **no `snmp-definitions-kb`,
no search tool, and no stored-agent-prompt dependency** at runtime — so there is no backend state to
drift. LogstashUI is the sole source of truth. `inline_grounding.py` assembles the field schema +
standard-MIB references + generic/vendor-matched profiles (~15K tokens) per request. Agent Builder is
just the (swappable) LLM host — `agent_client` splits `assemble_request()` (backend-agnostic) from
`send_via_agent_builder()`, so another backend drops in without touching the app.

## Deploy sequence

1. **App** — build the image from this branch and run migrations (`python manage.py migrate`).
2. **AI Agent Settings** — set the LLM host base URL + API key + agent id under AI Onboarding →
   AI Agent Settings (or seed `AISettings`). No custom agent/tool/KB is required — any reachable
   converse agent works, because the instructions are overridden per request.
3. **End-to-end check** — AI Onboarding → Generate on a candidate → draft shows OIDs + `normalizers`
   with few/no unverified → Approve → Profile + Template → Deploy from the SNMP page → confirm scaled
   metrics land in Elasticsearch for the device IP.

## Rollback

Image-tagged; roll back by pointing the stack at the previous image tag. No KB state to reconcile.

## Notes / known follow-ups

- Official profiles are stored as **DB placeholders** (`profile_data = {'is_official_placeholder': True}`);
  their real get/walk/table/normalizers content is read from the on-disk JSON at pipeline-gen time.
- **Discovery** uses a column-striding walk (`AI/snmp_discovery.py`) — samples every table column so the
  agent is grounded on complete data, not a partial walk (unit-tested in `AI/test_snmp_discovery.py`).
- **Spec drift:** profiles/agent use `translate` (and occasionally `average`), but the pinned op set is
  `{multiply, ratio}` and the pipeline generator has no `average` handler. Reconcile spec ↔ profiles ↔ generator.
- **Portability (next release):** to add another LLM backend (OpenAI, local, direct inference),
  implement one `send_via_*` alongside `send_via_agent_builder` — `assemble_request` and the app are
  unchanged. Promote the two functions to a small backend interface when the second backend lands.
