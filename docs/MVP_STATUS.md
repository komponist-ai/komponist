# Komponist MVP Status

**Last Updated:** July 2026

This document tracks what's actually implemented vs what's still needed for MVP launch.

---

## Executive Summary

| Category | Status | Progress |
|----------|--------|----------|
| Core Infrastructure | ✅ Locally verified | 85% |
| Extraction Pipeline | ✅ Local-docs slice verified | 80% |
| MCP Server | 🚧 Core tools locally verified | 80% |
| Integrations | 🚧 Code exists | 40% |
| Web UI | 🚧 Auth gate browser-verified | 78% |
| Chat Feature | ✅ Grounded local flow verified | 80% |
| Auth & Security | 🚧 Google + password sessions and org roles | 62% |
| User Management | 🚧 Multi-org membership UI | 70% |
| Deployment | ❌ Not implemented | 10% |

**Overall MVP Readiness: ~54%**

**Reality check:** The narrow local-documents → extraction → review → confirmed graph → cited chat loop now runs end-to-end in Docker. Live provider login, authenticated API isolation, MCP client interoperability, and deployment are still unverified.

---

## What "Code Exists" Actually Means

⚠️ **Important distinction:**
- **Code exists** = Python/TypeScript files are written
- **Tested** = Someone ran it and verified it works
- **Production-ready** = Tested + handles errors + documented

Almost everything in this repo is in the "code exists" state. Very little has been tested.

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
- [x] Confirm, reject, and merge lifecycle rules persist correctly in Neo4j
- [x] Chat uses confirmed graph context and returns real Evidence citations
- [x] Chat excludes proposed entities and data belonging to another organization
- [x] MCP tool discovery and cited context search over Streamable HTTP
- [x] MCP agent reports create idempotent Decision proposals in the review queue
- [x] Organization settings and encrypted connected-source configs survive API restarts
- [x] Notion, Slack, and Google OAuth callbacks persist allowlisted tokens encrypted
- [x] MCP approval requests and immutable decisions survive MCP restarts
- [x] Provider-free Google user-login and persistent session lifecycle
- [x] Multi-user organizations, role-checked invites, and per-session org switching
- [x] Web login/session gate renders correctly in the local browser without console errors
- [x] Email/password registration, logout, and repeat login in the local browser

### Unit Tests:
- `packages/core/tests/test_ai_clients.py` — 10 offline AI client contract tests (passing)
- `packages/pipelines/tests/test_contracts.py` — 3 extraction schema tests (passing)
- `apps/api/tests/review_lifecycle_e2e.py` — review lifecycle against the Docker stack (passing)
- `apps/api/tests/chat_e2e.py` — grounded chat, citations, streaming, and isolation (passing)
- `apps/mcp/tests/search_context_e2e.py` — MCP discovery, cited search, and isolation (passing)
- `apps/mcp/tests/report_result_e2e.py` — agent writeback, retry dedup, and review queue (passing)
- `apps/mcp/tests/approval_persistence_e2e.py` — approval persistence, isolation, and restart (passing)
- `apps/api/tests/persistence_e2e.py` — encrypted source/settings persistence across restart (passing)
- `apps/api/tests/oauth_persistence_e2e.py` — provider-free OAuth callback persistence (passing)
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
- [ ] **NOT TESTED** — Never connected to Claude Code or another external MCP client
- [ ] **NOT TESTED** — Real Slack delivery and button callbacks never tested

### API Server (`apps/api/`)
- [x] `main.py` — FastAPI with ~50 endpoints (code complete):
  - Health check, queue, entities, graph, chat, sources, settings
  - OAuth flows for Notion, Slack, Google
  - Export/import endpoints
- [x] `database.py` — SQLAlchemy models for Postgres (code complete)
- [x] `security.py` — Security utilities exist but NOT wired to endpoints
- [x] `integrations/notion.py` — Notion OAuth + page extraction (code complete)
- [x] `integrations/slack.py` — Slack OAuth + message extraction (code complete)
- [x] `integrations/github.py` — GitHub webhook + PR extraction (code complete)
- [x] `integrations/linear.py` — Linear webhook + issue extraction (code complete)
- [x] `integrations/google.py` — Google OAuth + Drive export (code complete)
- [x] API starts in Docker and reports healthy Neo4j and Postgres connections
- [x] Review lifecycle and grounded chat endpoints are E2E-tested
- [ ] **NOT TESTED** — Webhooks never received real events
- [ ] **NOT TESTED** — OAuth flows never completed

### Web UI (`apps/web/`)
- [x] `app/page.tsx` — Chat page with streaming (193 lines)
- [x] `app/queue/page.tsx` — Review queue (170 lines)
- [x] `app/graph/page.tsx` — Graph visualization (337 lines)
- [x] `app/onboard/page.tsx` — Source connection flow (451 lines)
- [x] `app/entities/page.tsx` — Entity list (169 lines)
- [x] `app/sources/page.tsx` — Connected sources (340 lines)
- [x] `app/settings/page.tsx` — Settings page (241 lines)
- [x] `app/settings/team/page.tsx` — Organization members, roles, and invitation links
- [x] `app/invite/page.tsx` — Authenticated invitation acceptance flow
- [x] `lib/api.ts` — API client functions (85 lines)
- [x] Components: AuthProvider, AuthGate, AppLayout, Sidebar, Nav, FactCard, ChatMessage, ChatInput, EvidenceChip
- [x] Web app builds successfully and runs in the local Docker stack
- [x] Signed-out auth gate loaded and visually verified in the local browser
- [ ] **NOT TESTED** — Authenticated pages need live Google credentials for browser verification

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
- [ ] Org-scoped API keys

### Data Persistence
- [x] OAuth callback token responses stored encrypted in connected-source records
- [x] Connected sources and encrypted connector configs stored in Postgres
- [x] Org settings stored in Postgres
- [x] Approval requests and decisions stored in Postgres
- [x] Approval state survives MCP restarts

### Komponist Cloud (Hosted Version)
- [ ] Landing page / marketing website
- [ ] Cloud infrastructure deployment
- [ ] Multi-tenant data isolation
- [ ] Billing & subscription (Stripe)
- [ ] Usage limits & quotas
- [ ] Terms of Service / Privacy Policy
- [ ] **No code exists**

### Komponist Self-Hosted (Local Version)
- [ ] One-command setup that actually works
- [ ] Installation documentation that's been tested
- [ ] Configuration wizard
- [x] Docker Compose verified on the development Mac; clean-machine portability remains untested

### Observability
- [ ] Metrics dashboard
- [ ] Error tracking
- [ ] LLM cost tracking
- [ ] **No code exists**

---

## Critical Issues

### 1. External Integrations and MCP Remain Untested
The local vertical slice is verified, but important boundaries are still open:
- No one has completed a real Notion OAuth flow
- No one has used the MCP tools with Claude Code or another MCP client
- No live OpenAI extraction/chat request has been run with an API key
- No cloud deployment or multi-user workflow has been tested

### 2. Authentication Is Not Enforced Yet
The provider-free Google login and persistent session lifecycle work, but:
- Live Google login has not been completed with real credentials
- The Web UI gate and organization screens exist, but authenticated browser flows need live Google credentials
- Existing API endpoints still accept caller-provided `org_id` values
- The active session organization is not yet enforced on existing brain API routes

### 3. Real Provider Lifecycles Remain Unverified
Connected sources, organization settings, and approval requests now survive service restarts. Remaining gaps:
- Real provider OAuth exchanges and token refresh behavior remain unverified
- Real Slack approval delivery and signed interaction callbacks remain unverified

### 4. Security Not Applied
- `security.py` has utilities but they're not used
- API endpoints have no authentication
- Org isolation decorator exists but isn't applied

---

## Honest Effort Estimates

| Task | Effort | Why |
|------|--------|-----|
| Run Docker and fix issues | 4-8 hours | Unknown bugs will surface |
| Test Notion → Queue flow | 2-4 hours | Integration debugging |
| Test MCP with Claude Code | 2-4 hours | Protocol debugging |
| Wire auth into Web/API routes | 6-12 hours | Session-derived org isolation and UI states |
| Persist tokens/settings to DB | 4-8 hours | Schema + migration + code |
| Test full review queue flow | 2-4 hours | UI debugging |
| Deploy to cloud | 8-16 hours | Infrastructure + debugging |
| **Total to "barely working"** | **30-60 hours** | Optimistic estimate |

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
- [ ] MCP server connects to Claude Code
- [x] `search_company_context` returns confirmed results with Evidence citations
- [x] `report_result` sends new Decisions to the review queue without auto-confirming
- [ ] `check_constraint` correctly blocks/allows actions
- [ ] Data persists across server restarts

### Deployment:
- [ ] Self-hosted: `docker compose up` on any machine
- [ ] Cloud: Live at komponist.dev

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
11. Protect API endpoints
12. [x] Persist hashed session tokens to database

### Phase 3: Test MCP (1-2 days)
13. Configure MCP server in Claude Code
14. Test all 6 tools with real data
15. Fix any protocol issues

### Phase 4: Deploy (2-3 days)
16. Deploy to Fly.io
17. Set up AuraDB (Neo4j)
18. Set up Neon (Postgres)
19. Create landing page

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
│ ✅ Tested │ 🚧 Auth foundation; routes open │ ✅ Persistence    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│               Extraction Pipeline (LangGraph)                    │
│  📝 Code exists │ ❌ Not tested with real data                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Neo4j (Company Brain)                         │
│  📝 Schema defined │ ❌ Not deployed │ ❌ No data                │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                              ▼
┌─────────────────────────┐    ┌─────────────────────────────────┐
│      MCP Server         │    │          Web UI                  │
│  📝 Code exists         │    │  📝 Code exists                  │
│  ❌ Never connected     │    │  ✅ Auth gate browser-verified  │
└─────────────────────────┘    └─────────────────────────────────┘

Legend:
📝 = Code written but untested
❌ = Not working / Not implemented
✅ = Tested and working
```

---

## Summary

**The honest truth:** The local core loop and auth foundation are tested, but this is not yet a user-ready product. The path from here to "10 design partners using it daily" requires:

1. **Enforcing sessions and org isolation across API routes**
2. **Completing live Google login and authenticated browser testing**
3. **Testing live Google, Notion, and MCP integrations**
4. **Deploying and operating it safely**

Estimated time to MVP: **2-4 weeks of focused work**, assuming no major surprises when testing reveals bugs.
