# Komponist MVP Status

**Last Updated:** July 2026

This document tracks what's actually implemented vs what's still needed for MVP launch.

---

## Executive Summary

| Category | Status | Progress |
|----------|--------|----------|
| Core Infrastructure | ✅ Locally verified | 80% |
| Extraction Pipeline | ✅ Local-docs slice verified | 80% |
| MCP Server | 🚧 Cited search verified | 65% |
| Integrations | 🚧 Code exists | 40% |
| Web UI | 🚧 Builds and runs locally | 65% |
| Chat Feature | ✅ Grounded local flow verified | 80% |
| Auth & Security | ❌ Not implemented | 5% |
| User Management | ❌ Not implemented | 0% |
| Deployment | ❌ Not implemented | 10% |

**Overall MVP Readiness: ~45%**

**Reality check:** The narrow local-documents → extraction → review → confirmed graph → cited chat loop now runs end-to-end in Docker. External integrations, authentication, MCP client interoperability, and deployment are still unverified.

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

### Unit Tests:
- `packages/core/tests/test_ai_clients.py` — 10 offline AI client contract tests (passing)
- `packages/pipelines/tests/test_contracts.py` — 3 extraction schema tests (passing)
- `apps/api/tests/review_lifecycle_e2e.py` — review lifecycle against the Docker stack (passing)
- `apps/api/tests/chat_e2e.py` — grounded chat, citations, streaming, and isolation (passing)
- `apps/mcp/tests/search_context_e2e.py` — MCP discovery, cited search, and isolation (passing)
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
- [ ] **NOT TESTED** — Never connected to Claude Code or another external MCP client
- [ ] **NOT TESTED** — Approval flow (Slack buttons) never tested

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
- [x] `lib/api.ts` — API client functions (85 lines)
- [x] Components: AppLayout, Sidebar, Nav, FactCard, ChatMessage, ChatInput, EvidenceChip
- [x] Web app builds successfully and runs in the local Docker stack
- [ ] **NOT TESTED** — No page has been loaded in a browser

### Docker Configuration (`docker/`)
- [x] `docker-compose.yml` — Full stack: Neo4j, Postgres, API, MCP, Web (176 lines)
- [x] `docker-compose.dev.yml` — Dev infrastructure only
- [x] Dockerfiles for API, MCP, Web
- [x] Docker Compose stack builds and starts successfully on the development Mac

---

## ❌ Not Implemented At All

### User Management & Authentication
- [ ] User registration
- [ ] Sign in with Google
- [ ] Email/password authentication
- [ ] Password reset flow
- [ ] Session management (JWT/cookies)
- [ ] Account settings page
- [ ] Delete account functionality
- [ ] Team/org invitations
- [ ] Role-based permissions (admin, member, viewer)
- [ ] **No code exists** — This is a complete gap

### Multi-tenancy
- [ ] Org creation/management UI
- [ ] User invite flow
- [ ] Org-scoped API keys
- [ ] **No code exists**

### Data Persistence
- [ ] OAuth tokens stored in database (currently in-memory dict, lost on restart)
- [ ] Connected sources stored in database (currently in-memory dict)
- [ ] Org settings stored in database (currently in-memory dict)
- [ ] Approval requests stored in database (currently in-memory dict)
- [ ] **Critical bug**: All state is lost when server restarts

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
- [ ] **Docker compose exists but never tested**

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

### 2. No User Authentication
There is no way to:
- Create an account
- Log in
- Protect API endpoints
- Isolate user data

### 3. All State Is In-Memory
When the server restarts, you lose:
- All connected OAuth tokens
- All connected sources
- All org settings
- All pending approvals

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
| Add user auth (Google OAuth) | 8-16 hours | New feature from scratch |
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
9. Implement Google OAuth for users
10. Add session management
11. Protect API endpoints
12. Persist tokens to database

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
│  📝 Code exists │ ❌ Not tested │ ❌ No auth │ ❌ No persistence │
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
│  ❌ Never connected     │    │  ❌ Never loaded in browser      │
└─────────────────────────┘    └─────────────────────────────────┘

Legend:
📝 = Code written but untested
❌ = Not working / Not implemented
✅ = Tested and working (none currently)
```

---

## Summary

**The honest truth:** This is a codebase, not a product. Significant code has been written, but none of it has been tested. The path from here to "10 design partners using it daily" requires:

1. **Making it run** (currently it doesn't)
2. **Adding user auth** (currently nonexistent)
3. **Testing everything** (currently nothing tested)
4. **Deploying it** (currently only Docker files)

Estimated time to MVP: **2-4 weeks of focused work**, assuming no major surprises when testing reveals bugs.
