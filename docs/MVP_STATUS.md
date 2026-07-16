# Komponist MVP Status

**Last Updated:** July 2026

This document tracks what's actually implemented vs what's still needed for MVP launch.

---

## Executive Summary

| Category | Status | Progress |
|----------|--------|----------|
| Core Infrastructure | 🚧 Code exists | 60% |
| Extraction Pipeline | 🚧 Code exists | 70% |
| MCP Server | 🚧 Code exists | 50% |
| Integrations | 🚧 Code exists | 40% |
| Web UI | 🚧 Code exists | 50% |
| Chat Feature | 🚧 Code exists | 40% |
| Auth & Security | ❌ Not implemented | 5% |
| User Management | ❌ Not implemented | 0% |
| Deployment | ❌ Not implemented | 10% |

**Overall MVP Readiness: ~35%**

**Reality check:** Code exists for many features but **nothing has been tested end-to-end**. No infrastructure is running. No user has ever used this system.

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
- [ ] **No user-facing flow has been end-to-end tested yet**

### Unit Tests:
- `packages/core/tests/test_ai_clients.py` — 8 offline AI client contract tests (passing)
- `packages/pipelines/tests/test_contracts.py` — 3 extraction schema tests (passing)
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
- [ ] **NOT TESTED** — None of this has been run against a real Neo4j instance

### Extraction Pipeline (`packages/pipelines/`)
- [x] `extract.py` — LangGraph 6-node pipeline: classify → extract → embed → dedup → link → persist (code complete)
- [x] `graph_extract.py` — Simpler single-LLM-call extraction (code complete)
- [x] `compile.py` — Work Pack compiler pipeline (code complete)
- [x] `eval/fixtures.py` — Test fixtures for evaluation (code complete)
- [ ] **NOT TESTED** — Never run with real data

### MCP Server (`apps/mcp/`)
- [x] `server.py` — FastMCP server with 6 tools (code complete):
  - `search_company_context`
  - `get_active_decisions`
  - `report_result`
  - `check_constraint`
  - `request_approval`
  - `get_approval_status`
- [x] `constraints.py` — Constraint checking logic with LLM adjudication (code complete)
- [ ] **NOT TESTED** — Never connected to Claude Code or any MCP client
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
- [ ] **NOT TESTED** — API server has never been started
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
- [ ] **NOT TESTED** — Web app has never been started
- [ ] **NOT TESTED** — No page has been loaded in a browser

### Docker Configuration (`docker/`)
- [x] `docker-compose.yml` — Full stack: Neo4j, Postgres, API, MCP, Web (176 lines)
- [x] `docker-compose.dev.yml` — Dev infrastructure only
- [x] Dockerfiles for API, MCP, Web
- [ ] **NOT TESTED** — `docker compose up` has never been run

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

### 1. Nothing Has Been Tested
The entire codebase is "code complete" but zero features have been verified working. This includes:
- No one has run `docker compose up`
- No one has connected a Notion workspace
- No one has reviewed a fact in the queue
- No one has used the MCP tools with Claude Code
- No one has run the extraction pipeline on real data

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
- [ ] `docker compose up` starts everything without errors
- [ ] User can sign in with Google
- [ ] User can connect Notion with a token
- [ ] Syncing Notion creates entities in Neo4j
- [ ] Review queue shows proposed entities
- [ ] Confirming an entity persists to Neo4j
- [ ] Chat returns answers from the knowledge graph
- [ ] MCP server connects to Claude Code
- [ ] `search_company_context` returns results
- [ ] `check_constraint` correctly blocks/allows actions
- [ ] Data persists across server restarts

### Deployment:
- [ ] Self-hosted: `docker compose up` on any machine
- [ ] Cloud: Live at komponist.dev

**Target: 10 design partners using the system daily**

---

## Next Steps (In Order)

### Phase 0: Make It Run (1-2 days)
1. Run `docker compose up` and fix all errors
2. Apply Neo4j schema
3. Seed test data
4. Verify API health check passes

### Phase 1: Test Core Loop (2-3 days)
5. Connect Notion with real token
6. Sync pages and verify entities created
7. Open web UI and test review queue
8. Verify chat returns results

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
