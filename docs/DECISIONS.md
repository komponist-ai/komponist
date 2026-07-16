# Architectural Decision Records

These decisions will be the first Decision nodes in the Komponist brain (dogfooding from commit one).

## ADR-001: Neo4j as the Company Brain

**Decision:** Use Neo4j 5.x (AuraDB Professional for production, Docker for local dev) as the sole brain storage. Embeddings via Neo4j native vector index.

**Why:** The Company Brain is fundamentally a graph (goals, decisions, constraints, projects with typed relationships). Neo4j 5's native vector indexes eliminate the need for a separate vector DB, reducing operational complexity and keeping the brain in one queryable location.

**Alternatives considered:**
- Separate vector DB (Pinecone/Weaviate) + Neo4j: adds sync complexity
- Postgres with pgvector: poor graph traversal performance
- MongoDB: weak graph semantics

**Constraints:** Embedding dimension is fixed at initialization (e.g., 1536 for text-embedding-3-small). Changing dimensions later requires full reindex.

## ADR-002: Postgres for App Data Only

**Decision:** Postgres stores boring app data only: `users/orgs`, `events_raw` (webhook landing zone), `tool_calls` (metrics), `sync_state`. Zero brain-related data in Postgres.

**Why:** Clear separation of concerns. Postgres is excellent at OLTP (auth, webhooks, logs). Neo4j owns all knowledge graph operations.

## ADR-003: Python Backend with FastAPI

**Decision:** Python 3.12, FastAPI for API/webhooks, async Neo4j driver, LangGraph for extraction/compiler pipelines, FastMCP for MCP server.

**Why:**
- FastAPI: fast, async-native, excellent OpenAPI docs
- LangGraph: state machine orchestration for multi-step LLM pipelines
- FastMCP: simplest path to production MCP server
- Python 3.12: mature async ecosystem, type hints, pattern matching

## ADR-004: Single Embedding Model, Fixed Dimension

**Decision:** One embedding model (text-embedding-3-small, 1536 dims), fixed at start. Never change.

**Why:** Vector indexes are immutable regarding dimensionality. Changing models mid-flight requires full graph reindex (expensive, error-prone). Pick once, commit.

**Chosen:** OpenAI text-embedding-3-small (1536 dims, $0.02/1M tokens, excellent quality).

## ADR-005: Centralized LLM Wrapper

**Decision:** All LLM calls go through `packages/core/llm.py` wrapper (model name, retries, JSON parsing, error handling in one place).

**Why:** 
- Single point for rate limiting, cost tracking, model switching
- Consistent retry logic (exponential backoff)
- Standardized JSON parsing with fallback
- Easy to A/B test prompts

## ADR-006: Next.js for Frontend

**Decision:** Next.js (App Router) + Tailwind for the web app. One app: review queue + graph browser.

**Why:**
- App Router: server components, streaming, excellent DX
- Tailwind: rapid UI iteration, design system via tokens.css
- Monorepo: shared components between marketing and product UI

## ADR-007: Hosting Stack

**Decision:**
- API + Web: Fly.io or Railway (container-native, simple deploys)
- Neo4j: AuraDB Professional (managed, automatic backups, scaling)
- Postgres: Neon or Supabase (serverless, branching, connection pooling)

**Why:** Minimize operational overhead. Focus on product, not infrastructure. All three have generous free tiers for MVP.

## ADR-008: Wedge Integrations Only

**Decision:** GitHub, Slack, Linear. Nothing else in MVP.

**Why:** These three tools represent the decision-making layer at AI-native startups:
- GitHub: ADRs, PR discussions, code decisions
- Slack: real-time decisions, approvals, context
- Linear: project goals, customer requests

Notion/CRM/email/transcripts are out of scope until design partners demand them.

## ADR-009: Status-Based Entity Lifecycle

**Decision:** All brain entities have status: `proposed` → `confirmed` → `superseded` | `rejected`.

**Why:**
- Human-in-the-loop is core to trust: extraction is never auto-confirmed
- Superseded decisions stay in graph for history/chain view
- Rejected entities are soft-deleted (learning data for extraction pipeline)

## ADR-010: Bias Toward "Allowed" in Constraint Checking

**Decision:** `check_constraint` adjudication must bias hard toward `allowed`. Ambiguity → allowed with note. Block only when constraint clearly applies.

**Why:** False positives (blocking valid work) kill trust and cause tool uninstallation. False negatives (missing a violation) are caught in review. The system's value is governance, not gatekeeping.

**Target:** ≤5% false block rate on benign actions.

---

**Implementation note:** These ADRs will be manually entered as the first Decision nodes in the Komponist brain during Step 2 (graph schema) completion, demonstrating dogfooding from day one.
