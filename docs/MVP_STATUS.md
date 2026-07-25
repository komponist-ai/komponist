# Komponist MVP Status

**Last Updated:** July 2026

This document tracks what's actually implemented vs what's still needed for MVP launch.

---

## Executive Summary

| Category | Status | Progress |
|----------|--------|----------|
| Core Infrastructure | ✅ Locally verified | 90% |
| Extraction Pipeline | ✅ Local-docs slice verified | 80% |
| MCP Server | ✅ All six contracts locally verified | 93% |
| Integrations | 🚧 Provider-free contracts verified | 55% |
| Web UI | ✅ Production build and core flows verified | 88% |
| Chat Feature | ✅ Grounded live OpenAI flow verified | 88% |
| Agent Collaboration | ✅ Durable multiplayer Workrooms verified | 85% |
| Auth & Security | ✅ Session/API-key org isolation verified | 88% |
| User Management | 🚧 Multi-org membership UI | 80% |
| Deployment | 🚧 Hetzner/Coolify stack prepared | 40% |

**Overall MVP Readiness: ~75%**

**Reality check:** The local-documents → extraction → review → confirmed graph → cited chat/API/MCP loop runs end-to-end in Docker. Browser routes are session- and role-protected; programmatic routes and MCP derive the organization from revocable API keys. A private production Compose topology and Hetzner/Coolify runbook now exist, but the first clean-machine public deployment remains unverified. Live external provider OAuth/webhooks and an external MCP host such as Claude Code also remain unverified.

---

## What "Code Exists" Actually Means

⚠️ **Important distinction:**
- **Code exists** = Python/TypeScript files are written
- **Tested** = Someone ran it and verified it works
- **Production-ready** = Tested + handles errors + documented

The core local slice now has broad contract and restart coverage. External provider and deployment boundaries remain in the "code exists" state until exercised with real credentials.

---

## ✅ Actually Verified Working

### Only These Things Have Been Tested:
- [x] OpenAI Responses API request contract via injected offline client
- [x] Strict structured-output parsing and application-side schema validation
- [x] OpenAI embedding request contract and fixed 1536-dimensional output
- [x] Deterministic no-model mock clients for LLM and embeddings
- [x] Narrow extraction contracts for Decision, Goal, Constraint, and Project
- [x] Full Docker stack starts with healthy Neo4j, Postgres, API, MCP, and Web services
- [x] Local documents create reviewable entities with stable source deduplication
- [x] Authenticated browser uploads process Markdown, text, and YAML into the same review pipeline
- [x] Confirm, reject, and merge lifecycle rules persist correctly in Neo4j
- [x] Chat uses confirmed graph context and returns real Evidence citations
- [x] Chat excludes proposed entities and data belonging to another organization
- [x] MCP tool discovery and cited context search over Streamable HTTP
- [x] MCP agent reports create idempotent Decision proposals in the review queue
- [x] Organization settings and encrypted connected-source configs survive API restarts
- [x] Notion, Slack, and Google OAuth callbacks persist allowlisted tokens encrypted
- [x] MCP approval requests and immutable decisions survive MCP restarts
- [x] All six authenticated MCP tools, the brain resource, project-scoped decisions, and deterministic constraint verdicts
- [x] All organization brain routes enforce session membership and write/admin roles
- [x] Organization API keys expose cited `/v1/context`, `/v1/brain`, and project-scoped `/v1/decisions`
- [x] Revoked API keys fail immediately and unauthenticated MCP/REST access returns 401
- [x] Connector OAuth state is opaque, short-lived, persisted, and single-use
- [x] GitHub, Linear, Slack, and Google webhook endpoints reject unsigned requests by default
- [x] Typed `@komponist/sdk` context client and its `{ data, error }` contract
- [x] Provider-free Google user-login and persistent session lifecycle
- [x] Multi-user organizations, role-checked invites, and per-session org switching
- [x] Web login/session gate renders correctly in the local browser without console errors
- [x] Email/password registration, logout, and repeat login in the local browser
- [x] Compose creates private, cited presentations, briefings, and summaries from permission-scoped confirmed knowledge
- [x] Designed PDF, editable PowerPoint, and Markdown artifact downloads are verified provider-free
- [x] Cross-source document families, provenance ordering, semantic claim diffs, and the built-in three-platform example are verified provider-free
- [x] Shared Workrooms persist plans, versioned agent runs, activity events, pause/resume, redirects, and human approvals
- [x] Workroom agents retrieve only confirmed knowledge inside the room's explicit department scope and create a cited Compose briefing after approval
- [x] Workroom jobs are claimed exactly once, recover from an expired worker lease, retry with bounded backoff, and survive an API and worker restart
- [x] Room roles and visibility modes are enforced; a private room is not disclosed to non-participants
- [x] Model-generated plans are schema-strict, locally re-validated, versioned, and require human approval
- [x] Context pins and exclusions govern agent retrieval without ever widening access
- [x] Deliverables are shared through room authorization while older private deliverables stay private

### Unit Tests:
- `packages/core/tests/test_ai_clients.py` — 10 offline AI client contract tests (passing)
- `packages/pipelines/tests/test_contracts.py` — 3 extraction schema tests (passing)
- `apps/api/tests/review_lifecycle_e2e.py` — review lifecycle against the Docker stack (passing)
- `apps/api/tests/chat_e2e.py` — grounded chat, citations, streaming, and isolation (passing)
- `apps/mcp/tests/search_context_e2e.py` — MCP discovery, cited search, and isolation (passing)
- `apps/mcp/tests/report_result_e2e.py` — agent writeback, retry dedup, and review queue (passing)
- `apps/mcp/tests/approval_persistence_e2e.py` — approval persistence, isolation, and restart (passing)
- `apps/mcp/tests/tool_contract_e2e.py` — all tool discovery, brain resource, decision scope, and constraint verdicts (passing)
- `apps/api/tests/persistence_e2e.py` — encrypted source/settings persistence across restart (passing)
- `apps/api/tests/generated_artifacts_e2e.py` — private history, department isolation, citations, PDF/PPTX/Markdown exports, and deletion (passing)
- `apps/api/tests/document_versions_e2e.py` — authenticated cross-source grouping, latest candidate, semantic conflicts, and demo visibility (passing)
- `apps/api/tests/workrooms_e2e.py` — shared membership, room-scoped retrieval, pause/resume, redirect lineage, approval, cancellation, and Compose handoff (passing)
- `apps/api/tests/workroom_queue_e2e.py` — single-claim safety, idempotency, lease recovery, bounded retries, and restart survival (passing)
- `apps/api/tests/workroom_roles_e2e.py` — room roles, visibility modes, participant management, archive, and cross-organization isolation (passing)
- `apps/api/tests/workroom_plans_e2e.py` — strict plan schema, rejected invalid plans, draft/approve/supersede lifecycle, and task management (passing)
- `apps/api/tests/workroom_context_e2e.py` — context pins, exclusions, run snapshots, and confidential-source non-disclosure (passing)
- `apps/api/tests/workroom_messages_e2e.py` — conversation threading, references, mention scoping, and separation from the audit trail (passing)
- `apps/api/tests/workroom_deliverables_e2e.py` — shared artifact access for participants, refusal for non-participants and other organizations, and private-artifact preservation (passing)
- `apps/api/tests/workroom_plans_live_ai.py` — optional live OpenAI plan generation, skipped unless `OPENAI_API_KEY` and `RUN_LIVE_AI_TESTS=1` are set (not run in CI)
- `packages/core/tests/test_versioning.py` — content identity, family matching, chronology, and claim-diff contracts (passing)
- `apps/api/tests/oauth_persistence_e2e.py` — provider-free OAuth callback persistence (passing)
- `apps/api/tests/platform_ai_and_api_keys_e2e.py` — API keys, cited programmatic context, project scope, graph stats, approvals, and revocation (passing)
- `packages/sdk-js/tests/client.test.mjs` — typed client URLs, auth headers, scopes, validation, and errors (passing)
- `apps/api/tests/auth_session_e2e.py` — Google login state, session, restart, and logout (passing)
- `apps/api/tests/organization_membership_e2e.py` — two-user invite, roles, isolation, and org switching (passing)
- `packages/core/tests/test_queries.py` — Tests for graph queries (requires Neo4j running)

---

## 🚧 Code Exists But Untested

### Neo4j Schema & Queries (`packages/core/`)
- [x] `graph.py` — Async Neo4j driver singleton (code complete)
- [x] `schema.py` — Graph schema definitions (code complete)
- [x] `queries.py` — 5 core queries: hybrid search, active decisions, context expansion, supersedes chain, applicable constraints (code complete)
- [x] `models.py` — Pydantic models for entities (code complete)
- [x] `llm.py` — OpenAI Responses API wrapper plus no-network mock mode (offline contract-tested)
- [x] `embeddings.py` — OpenAI embeddings plus deterministic no-model mock mode (offline contract-tested)
- [x] Core schema, persistence, and confirmed-entity queries verified against local Neo4j

### Extraction Pipeline (`packages/pipelines/`)
- [x] `extract.py` — LangGraph 6-node pipeline: classify → extract → embed → dedup → link → persist (code complete)
- [x] `graph_extract.py` — Simpler single-LLM-call extraction (code complete)
- [x] `compile.py` — Work Pack compiler pipeline (code complete)
- [x] `eval/fixtures.py` — Test fixtures for evaluation (code complete)
- [x] Narrow extraction pipeline verified with local Markdown documents in mock mode
- [ ] Live OpenAI extraction has not been tested with an API key

### MCP Server (`apps/mcp/`)
- [x] `server.py` — FastMCP server with 6 tools (code complete):
  - `search_company_context`
  - `get_active_decisions`
  - `report_result`
  - `check_constraint`
  - `request_approval`
  - `get_approval_status`
- [x] `constraints.py` — Constraint checking logic with LLM adjudication (code complete)
- [x] `search_company_context` verified through a real FastMCP HTTP client
- [x] Search returns only confirmed, org-scoped facts with their exact Evidence
- [x] `report_result` writes structured Decisions as proposed with agent-report Evidence
- [x] `report_result` retries are idempotent and can link verified Work Packs
- [x] Approval requests persist in Postgres and remain org-isolated across MCP restarts
- [x] `get_active_decisions` applies real project scoping and requires cited decisions
- [x] `check_constraint` has a provider-free deterministic fallback and validates live structured output
- [x] All six tools and `company-brain://info` are covered through an authenticated FastMCP client
- [ ] **NOT TESTED** — Never connected to Claude Code or another external MCP client
- [ ] **NOT TESTED** — Real Slack delivery and button callbacks never tested

### API Server (`apps/api/`)
- [x] `main.py` — FastAPI with ~50 endpoints (code complete):
  - Health check, queue, entities, graph, chat, sources, settings
  - OAuth flows for Notion, Slack, Google
  - Export/import endpoints
- [x] `database.py` — SQLAlchemy models for Postgres (code complete)
- [x] `security.py` — Login rate limiting and organization validation wired to boundaries
- [x] `integrations/notion.py` — Notion OAuth + page extraction (code complete)
- [x] `integrations/slack.py` — Slack OAuth + message extraction (code complete)
- [x] `integrations/github.py` — GitHub webhook + PR extraction (code complete)
- [x] `integrations/linear.py` — Linear webhook + issue extraction (code complete)
- [x] `integrations/google.py` — Google OAuth + Drive export (code complete)
- [x] API starts in Docker and reports healthy Neo4j and Postgres connections
- [x] Review lifecycle and grounded chat endpoints are E2E-tested
- [x] Queue, entity, source, graph, settings, export/import, and approval routes enforce session roles
- [x] API-key surface returns confirmed, cited context without caller-controlled organization IDs
- [x] Webhook handlers verify signatures/tokens and reject malformed JSON
- [x] Connector OAuth state is persisted and replay-protected
- [ ] **NOT TESTED** — Webhooks never received real events
- [ ] **NOT TESTED** — OAuth flows never completed

### Web UI (`apps/web/`)
- [x] `app/page.tsx` — Chat page with streaming (193 lines)
- [x] `app/queue/page.tsx` — Review queue (170 lines)
- [x] `app/graph/page.tsx` — Graph visualization (337 lines)
- [x] `app/onboard/page.tsx` — Source connection flow (451 lines)
- [x] Direct document upload with per-file extraction results and Review Queue handoff
- [x] `app/entities/page.tsx` — Entity list (169 lines)
- [x] `app/create/page.tsx` — Compose presentations, briefings, summaries, private history, source preview, and download
- [x] `app/versions/page.tsx` — Git-for-files families, revision timeline, semantic diffs, provenance, and built-in example
- [x] `app/sources/page.tsx` — Connected sources (340 lines)
- [x] `app/settings/page.tsx` — Settings page (241 lines)
- [x] `app/settings/team/page.tsx` — Organization members, roles, and invitation links
- [x] `app/invite/page.tsx` — Authenticated invitation acceptance flow
- [x] `lib/api.ts` — API client functions (85 lines)
- [x] Components: AuthProvider, AuthGate, AppLayout, Sidebar, Nav, FactCard, ChatMessage, ChatInput, EvidenceChip
- [x] Web app builds successfully and runs in the local Docker stack
- [x] Landingpage and API settings show the real `@komponist/sdk` contract
- [x] Signed-out auth gate loaded and visually verified in the local browser
- [x] Email/password authenticated source and settings pages browser-verified

### Docker Configuration (`docker/`)
- [x] `docker-compose.yml` — Full stack: Neo4j, Postgres, API, MCP, Web (176 lines)
- [x] `docker-compose.dev.yml` — Dev infrastructure only
- [x] Dockerfiles for API, MCP, Web
- [x] Docker Compose stack builds and starts successfully on the development Mac

---

## Remaining and Partially Implemented MVP Areas

### User Management & Authentication
- [x] User registration on first verified Google login
- [x] Sign in with Google (provider-free contract tested; live Google untested)
- [x] Email/password authentication with salted scrypt hashes and rate-limited endpoints
- [ ] Password reset flow
- [x] Persistent, revocable HttpOnly cookie sessions
- [ ] Personal account settings page
- [ ] Delete account functionality
- [x] Team/org invitation links and acceptance Web UI (email delivery still missing)
- [x] Backend roles: owner, admin, member, viewer

### Multi-tenancy
- [ ] Organization creation/rename UI
- [x] Active organization switcher and member/role UI
- [x] Membership and invitation API flow
- [x] Multiple organizations per user with per-session active org
- [x] Org-scoped, hashed, revocable API keys

### Data Persistence
- [x] OAuth callback token responses stored encrypted in connected-source records
- [x] Connected sources and encrypted connector configs stored in Postgres
- [x] Org settings stored in Postgres
- [x] Approval requests and decisions stored in Postgres
- [x] Approval state survives MCP restarts
- [x] Workrooms, tasks, run versions, and append-only activity events persist in Postgres
- [x] Workroom agent jobs run in a separate worker and survive API and worker restarts
- [x] Expired worker leases are recovered automatically and retries are bounded

### Multiplayer Workrooms

**Verified in Docker with the provider-free mock:** durable queue mechanics,
room roles and visibility, plan generation and approval, governed context,
shared conversation, shared deliverables, and restart recovery. The browser
flow was checked at 1280px and 375px in both themes.
- [x] Shared rooms visible to authorized organization members
- [x] Explicit organization/department knowledge scope
- [x] One Komponist Analyst with live activity events and cited graph research
- [x] Pause/resume, versioned redirect, approval/rejection, and Compose handoff
- [x] Durable Postgres job queue, separate worker service, and restart recovery
- [x] Explicit run state machine with deferred pause and cancellation
- [x] Explicit room membership with owner, editor, approver, and viewer roles
- [x] Organization, department, and private room visibility modes
- [x] Participant management, room settings, archive, and reopen with audit events
- [x] Versioned, human-approved plans generated through the central LLM provider
- [x] Editable tasks with assignment, dependencies, reorder, archive, and run lineage
- [x] Governed context packs with pins, exclusions, and a permission-safe preview
- [x] Immutable per-run context snapshots recording entities, evidence, and scope
- [x] Shared room conversation with replies, references, and scoped mentions
- [x] Deliverables shared with room participants through room authorization
- [ ] Live participant presence and email room invitations
- [ ] Agent-to-agent handoffs and parallel task execution

### Komponist Cloud (Hosted Version)
- [x] Landing page / marketing website
- [ ] Cloud infrastructure deployment
- [ ] Multi-tenant data isolation
- [ ] Billing & subscription (Stripe)
- [ ] Usage limits & quotas
- [ ] Terms of Service / Privacy Policy
- [ ] Hosted infrastructure and commercial operations are not implemented

### Komponist Self-Hosted (Local Version)
- [ ] One-command setup that actually works
- [ ] Installation documentation that's been tested
- [ ] Configuration wizard
- [x] Docker Compose verified on the development Mac; clean-machine portability remains untested
- [x] Private-port production Compose topology with health checks and persistent volumes
- [x] Hetzner/Coolify pilot deployment and recovery runbook

### Observability
- [ ] Metrics dashboard
- [ ] Error tracking
- [ ] LLM cost tracking
- [ ] **No code exists**

---

## Critical Issues

### 0. Workroom Limitations That Remain

- Live OpenAI plan generation has not been exercised with production
  credentials. It is verified offline through the provider abstraction, and an
  opt-in live check exists (`workroom_plans_live_ai.py`) that CI never runs.
- One agent persona (Komponist Analyst) exists. There are no agent-to-agent
  handoffs and no parallel task execution.
- Pause and cancel take effect at the next safe step. A model request already
  in flight is not aborted, and it is not billed back or retracted.
- Deliverable versioning is not implemented: approving new work creates a new
  artifact rather than a new version of an existing one.
- Room membership has no email invitation flow and no live presence.
- Withdrawing a shared deliverable revokes room access but leaves the artifact
  with its creator; there is no hard delete for shared deliverables.
- Multi-worker operation is implemented and unit-verified through concurrent
  claims, but has not been run at scale on the pilot server.

### 1. External Integrations Remain Partially Untested
The local vertical slice is verified, but important boundaries are still open:
- No one has completed a real Notion OAuth flow
- Authenticated Streamable HTTP discovery is verified with a real FastMCP client;
  Claude Code interoperability is still unverified
- Live OpenAI grounded chat is verified with `gpt-5.6-luna`; live extraction is still unverified
- No public cloud deployment or hosted multi-user workflow has been tested

### 2. Authentication Is Enforced Locally, but Production Hardening Remains
- Live Google login has not been completed with real credentials
- Browser routes validate the requested organization against the session membership
- Write routes require member-or-higher and management routes require owner/admin
- REST and MCP programmatic access derive the organization from hashed, revocable API keys
- Password reset, production rate limiting, and a formal migration system are still missing

### 3. Real Provider Lifecycles Remain Unverified
Connected sources, organization settings, and approval requests now survive service restarts. Remaining gaps:
- Real provider OAuth exchanges and token refresh behavior remain unverified
- Real Slack approval delivery and signed interaction callbacks remain unverified

### 4. Security Follow-ups
- Webhook secrets are global environment values rather than per-connection credentials
- Production needs proxy-aware rate limiting, secret rotation procedures, and a formal security review
- The accidental local diagnostic exposure of a development OpenAI key requires that key to be rotated

---

## Honest Effort Estimates

| Task | Effort | Why |
|------|--------|-----|
| Test Notion → Queue flow | 2-4 hours | Integration debugging |
| Test MCP with Claude Code | 2-4 hours | Protocol debugging |
| Test full review queue flow | 2-4 hours | UI debugging |
| Exercise prepared Hetzner deployment | 4-8 hours | DNS, build, OAuth, and recovery validation |
| Add migrations + production rate limits | 6-10 hours | Deployment safety |
| **Remaining to hosted pilot** | **20-40 hours** | Excludes provider approval delays |

---

## Definition of Done (MVP)

### Must Work End-to-End:
- [x] `docker compose up` starts everything without errors on the development Mac
- [ ] User can sign in with Google
- [ ] User can connect Notion with a token
- [ ] Syncing Notion creates entities in Neo4j
- [ ] Review queue shows proposed entities
- [x] Confirming an entity persists to Neo4j
- [x] Chat returns answers from confirmed graph context with Evidence citations
- [ ] MCP server connects to Claude Code (authenticated FastMCP client verified)
- [x] `search_company_context` returns confirmed results with Evidence citations
- [x] `report_result` sends new Decisions to the review queue without auto-confirming
- [x] `check_constraint` correctly blocks/allows/requires approval in deterministic contract tests
- [x] Settings, encrypted source credentials, OAuth state, and approvals persist across server restarts
- [x] Compose exports cited PDF, PowerPoint, or Markdown deliverables from permission-scoped confirmed context

### Deployment:
- [ ] Self-hosted: `docker compose up` on any machine
- [ ] Cloud: Live at komponist.dev
- [x] Private production Compose and Hetzner/Coolify runbook prepared

**Target: 10 design partners using the system daily**

---

## Next Steps (In Order)

### Phase 0: Make It Run (1-2 days)
1. [x] Run `docker compose up` and fix startup errors
2. [x] Apply Neo4j schema
3. [x] Seed isolated E2E test data
4. [x] Verify API health check passes

### Phase 1: Test Core Loop (2-3 days)
5. Connect Notion with real token
6. Sync pages and verify entities created
7. Open web UI and test review queue
8. [x] Verify chat returns confirmed results with citations

### Phase 2: Add Authentication (2-3 days)
9. [x] Implement Google OAuth contract for users
10. [x] Add persistent session management
11. [x] Protect API endpoints
12. [x] Persist hashed session tokens to database

### Phase 3: Test MCP (1-2 days)
13. [ ] Configure MCP server in Claude Code (authenticated HTTP discovery verified)
14. [x] Test all 6 tools with isolated graph data
15. [x] Fix discovered protocol, citation, and project-scope issues

### Phase 4: Deploy (1-2 days)
16. [x] Prepare a private production Compose stack
17. [x] Document the Hetzner/Coolify pilot setup
18. Deploy to an available 8 GB Hetzner instance and verify the recovery checklist
19. [x] Create landing page

---

## Architecture Diagram (Current State)

```
┌─────────────────────────────────────────────────────────────────┐
│                         Integrations                             │
├──────────┬──────────┬──────────┬──────────┬────────────────────┤
│  GitHub  │  Slack   │  Linear  │  Notion  │   Google Docs      │
│    📝    │    📝    │    📝    │    📝    │       📝           │
│ (code)   │ (code)   │ (code)   │ (code)   │    (code)          │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴────────┬───────────┘
     │          │          │          │              │
     ▼          ▼          ▼          ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API (FastAPI)                                 │
│ ✅ Tested │ ✅ Session/API-key isolation │ ✅ Persistence      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│               Extraction Pipeline (LangGraph)                    │
│ ✅ Local-doc slice │ 🚧 Live extraction still unverified         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Neo4j (Company Brain)                         │
│ ✅ Schema + local E2E data │ ❌ Not deployed                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                              ▼
┌─────────────────────────┐    ┌─────────────────────────────────┐
│      MCP Server         │    │          Web UI                  │
│ ✅ Six tools + resource │    │ ✅ Production build             │
│ 🚧 External host open   │    │ ✅ Auth/core flows verified     │
└─────────────────────────┘    └─────────────────────────────────┘

Legend:
📝 = Code written but untested
❌ = Not working / Not implemented
✅ = Tested and working
```

---

## Summary

**The honest truth:** The local core loop, authenticated API/MCP surface, SDK, and auth foundation are tested, but this is not yet a hosted user-ready product. The path from here to "10 design partners using it daily" requires:

1. **Completing live Google login and provider OAuth/webhook testing**
2. **Connecting a real external MCP host**
3. **Adding migrations, production rate limits, and operational monitoring**
4. **Deploying and operating it safely**

Estimated time to MVP: **2-4 weeks of focused work**, assuming no major surprises when testing reveals bugs.
