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

## Components (two repos)

| Repo | Provides |
|------|----------|
| **LogstashUI** (this repo) | App: AI Onboarding models/views/UI, `agent_client`, `snmp_discovery`, the pipeline-generator normalizer fix. Migrations: `AI/0001`, `AI/0002_draftdefinition_normalizers`. |
| **SNMP AB-tool** (`RCA/lab/snmp-ab-authoring-tool`) | The Agent Builder `snmp-profile-author` agent, the `snmp-definitions-kb` grounding KB, and the sync/deploy scripts (`deploy.sh`, `seed/load-kb.py`). |

## Source of truth

**LogstashUI's on-disk `src/logstashui/SNMP/data/official_profiles/*.json` are the source of truth.**
The KB is a **derived projection**, regenerated from the repo. Never hand-edit the KB — edit the
profiles in the repo and re-sync. The agent grounds on the KB and *reuses profile/normalizer blocks
verbatim*, so a KB out of sync with the repo silently degrades authoring quality.

## Deploy sequence

1. **App** — build the image from this branch and run migrations (`python manage.py migrate` applies
   the AI + SNMP migrations, including `DraftDefinition.normalizers`).
2. **AI Agent Settings** — set the Agent Builder base URL, API key, and agent id
   (`snmp-profile-author`) under AI Onboarding → AI Agent Settings (or seed `AISettings`).
3. **Agent + tool** — push the `snmp-profile-author` agent and its `search_snmp_profiles` tool
   (PUT-in-place, idempotent, never deletes). The agent is a build artifact — deploy it with the
   dedicated script:
   ```bash
   export KB_URL="https://<cluster>.kb.<region>.cloud.es.io" KB_API_KEY="<agent-builder key>"
   python3 deploy-agent.py            # upsert tool + agent to the target cluster
   python3 deploy-agent.py --check    # drift gate: exit 0 = in sync, 1 = differs
   ```
   (`deploy.sh` remains the full one-shot installer — index + tool + agent + KB seed — for a fresh
   cluster; `deploy-agent.py` is the focused, cluster-parameterized agent push for the build/CI path.)
4. **Sync the KB from the repo (source of truth):**
   ```bash
   export ES_URL="https://<cluster>.es.<region>.cloud.es.io" ES_API_KEY="<write key>"
   python3 seed/load-kb.py --logstashui /path/to/LogstashUI --prune   # upsert + reconcile deletes = exact mirror
   ```
5. **Verify sync (gate — do this before using the agent):**
   ```bash
   python3 seed/load-kb.py --logstashui /path/to/LogstashUI --check   # prints in_sync N/N; exit 0 = OK, 1 = drift
   ```
6. **End-to-end check** — AI Onboarding → Generate on a candidate device → the draft shows
   `normalizers` → Approve → Profile + Template created → Deploy from the SNMP page → confirm scaled
   metrics land in Elasticsearch for the device IP.

## Rollback

The app is image-tagged; roll back by pointing the stack at the previous image tag. The KB is
regenerable from the repo at any time (`load-kb.py --prune`), so KB state is never a rollback blocker.

## Notes / known follow-ups

- Official profiles are stored as **DB placeholders** (`profile_data = {'is_official_placeholder': True}`);
  their real get/walk/table/normalizers content is read from the on-disk JSON at pipeline-gen time.
- **Spec drift:** the on-disk profiles and the agent already use `translate` (and occasionally
  `average`), but `gen-agent.py` pins the op set to `{multiply, ratio}` per
  `spec/normalizers.0.5.0.json`, and the pipeline generator has no `average` handler. Reconcile
  spec ↔ profiles ↔ generator.
- The KB sync (`load-kb.py --prune` + `--check`) should be wired into the release/CI pipeline so the
  KB is always a current projection of the repo.
