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

**Decision:** Postgres stores transactional application state: users,
organizations, sessions, memberships, departments, invitations, encrypted
connector configuration, chat history, API keys, approvals, Workrooms, Canvas
specifications, generated-artifact metadata, durable jobs, and audit events.
Neo4j remains the canonical store for entities, evidence, relationships,
document versions, and semantic retrieval.

**Why:** Postgres is the right durable state machine for identity, permissions,
jobs, conversations, and versioned product workflows. Neo4j owns the knowledge
model and graph traversal. Product records may reference graph IDs but do not
duplicate the graph as a second source of truth.

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

**Chosen:** OpenAI text-embedding-3-small (1536 dims).

## ADR-005: Centralized LLM Wrapper

**Decision:** All LLM calls go through `packages/core/llm.py` wrapper (model name, retries, JSON parsing, error handling in one place).

**Why:** 
- Single point for rate limiting, cost tracking, model switching
- Consistent retry logic (exponential backoff)
- Standardized JSON parsing with fallback
- Easy to A/B test prompts

## ADR-006: Next.js for Frontend

**Decision:** Next.js (App Router) + Tailwind for one responsive web application
covering the public site, authentication, sources, review, entities, graph,
cited chat, Compose, Versions, Workrooms, Canvas, teams, API keys, and exports.

**Why:**
- App Router: server components, streaming, excellent DX
- Tailwind: rapid UI iteration, design system via tokens.css
- Monorepo: shared components between marketing and product UI

## ADR-007: Hosting Stack

**Decision:** Keep a portable Docker Compose topology. The current pilot runs
Web, API, MCP, Worker, Postgres, and Neo4j on one Ubuntu server managed through
Coolify, with only routed HTTPS services exposed publicly and persistent
database volumes kept private.

**Why:** One server is the cheapest understandable pilot topology and exercises
the real deployment boundary without committing the product to a cloud vendor.
The Compose contract remains the portability layer. A managed Postgres/Neo4j
split can follow once reliability or scale justifies the operational cost.

## ADR-008: Narrow Source Wedge

**Decision:** The product-facing MVP supports direct document uploads, explicitly
shared Notion pages through an Internal Integration, and explicitly selected
Slack channels through one centrally configured Slack app.

**Why:** Uploads provide the deterministic vertical slice. Notion and Slack
cover durable documentation plus active team discussion for the first design
partner use cases. Google Drive, GitHub, Linear, email, CRM, and transcripts
remain hidden until their full provider lifecycle meets the same authentication,
scope, sync, inspection, deletion, and extraction bar.

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

## ADR-011: OpenAI-Only AI Runtime

**Decision:** Use the OpenAI Responses API for extraction, chat, and future tool
workflows. Use OpenAI `text-embedding-3-small` for semantic retrieval. Do not
require a local model runtime.

**Development mode:** `KOMPONIST_AI_MODE=mock` uses deterministic test doubles
for response schemas and 1536-dimensional vector contracts. Mock output is not
AI-generated and must never be used to evaluate extraction or retrieval quality.

**Why:** One production API and one project-scoped key reduce operational and
billing complexity. Strict structured outputs make the extraction boundary
testable, while mock mode lets infrastructure work continue before API credits
are available.

**Privacy default:** Responses are created with application storage disabled
unless `KOMPONIST_OPENAI_STORE=true` is explicitly configured.

## ADR-012: Safe Dynamic Interfaces

**Decision:** Canvas stores a declarative, versioned specification produced from
a closed component and query vocabulary. Generated output cannot contain
JavaScript, JSX, HTML, SQL, Cypher, arbitrary URLs, or write actions. The server
validates the specification and resolves every binding through parameterized,
permission-aware graph queries at view time.

**Why:** A dynamic interface is useful only if it stays live and shareable.
Storing a question/specification instead of a generated snapshot lets different
viewers see current data inside their own permissions without executing
untrusted code.

## ADR-013: Durable Human-Agent Workrooms

**Decision:** Workroom plans, tasks, participants, conversations, runs, context
snapshots, deliverables, and audit events persist in Postgres. Agent work runs
in a separate leased worker queue. Plans require human approval, redirects
create new run versions, and room scope may narrow but never widen a
participant's knowledge permissions.

**Why:** Multiplayer agent work needs a durable, inspectable state machine
rather than one long API request or a private chat transcript. Separating the
worker keeps redeploys and retries from losing intent while maintaining an
immutable record of what context supported each output.

---

**Implementation note:** These ADRs are intended to be ingested into a Komponist
workspace as source documents and reviewed like any other company decision.
