# Komponist FAQ

## General

### What is Komponist?

Komponist is a context and governance layer for AI coding agents. It builds a "company brain" by ingesting decisions from GitHub, Slack, and Linear, then serves cited context to agents via MCP tools. Critically, it also governs agents by checking their actions against confirmed constraints.

### How is this different from enterprise search (Glean, etc.)?

Enterprise search is built for humans typing keywords. Komponist is built for agents: every fact is cited (source, reference, URL, excerpt), decisions are supersede-aware (no stale results), and constraint checking blocks risky actions before they happen.

### How is this different from agent memory (Hyperspell, etc.)?

Agent memory stores chat session history. Komponist stores org-level context (goals, decisions, constraints, customer requests) that applies across all agents and sessions. It's the governed memory every agent calls, not per-session persistence.

### What's the "killer feature"?

**Constraint checking.** An agent asks "may I do X?" and Komponist searches relevant constraints, adjudicates with an LLM, and returns: allowed | blocked | approval_required. If blocked, the agent sees the constraint citation and cannot proceed. If approval is required, a Slack approval flow kicks in. This is governance, not just memory retrieval.

---

## Setup

### What do I need to get started?

- Neo4j 5.x (Docker locally, or AuraDB for production)
- Postgres (Docker locally, or Neon/Supabase)
- OpenAI API key (for embeddings)
- Anthropic API key (for LLM calls)
- GitHub, Slack, and/or Linear accounts to connect

### How long does onboarding take?

About 5 minutes to connect the three integrations. Backfilling 90 days of history takes 10-30 minutes depending on data volume. Your first review session (confirming 50 facts) takes another 10-15 minutes.

### Do I need to review every extracted fact?

Yes. Every fact in the brain must be human-confirmed (ADR-009). This is core to trust: extraction is never auto-confirmed. The review queue makes this fast (inline edit, keyboard shortcuts, <5 seconds per fact).

### Can I bulk-import existing ADRs?

Not directly in MVP. The extraction pipeline runs on SourceItems (from webhooks or backfill), so your existing ADRs will be extracted during GitHub backfill. If you have hundreds, consider confirming the most critical ones first.

---

## Usage

### How do agents use Komponist?

Via MCP (Model Context Protocol). You install the Komponist MCP server, configure it in Claude Code or Cursor, and agents can call 6 tools:
- `search_company_context` — search the brain
- `get_active_decisions` — supersede-aware decisions
- `report_result` — feed new decisions back
- `check_constraint` — ask permission before risky actions
- `request_approval` — request human approval
- `get_approval_status` — poll approval state

### What if an agent ignores a constraint?

If the agent calls `check_constraint` and gets `blocked`, it should not proceed (and Claude will respect this). If an agent bypasses the tool entirely, you'll catch the violation in PR review. The goal is to block at intention time, not cleanup time.

### How do I add a new constraint?

Either:
1. Manually create a Constraint entity in the web UI (future feature)
2. Document it in an ADR or Slack decision thread, let extraction find it, then confirm it in the review queue
3. Use the MCP `report_result` tool to add it programmatically

Once confirmed, it's immediately active for `check_constraint`.

### What happens when a decision is superseded?

The old decision's status becomes `superseded` and it no longer appears in `get_active_decisions` or `search_company_context` (unless you explicitly search for superseded entities). The supersede chain is preserved, so you can view history.

### How do I know if Komponist is working?

Check these metrics:
- **Violations blocked** (the killer metric): `SELECT COUNT(*) FROM tool_calls WHERE tool = 'check_constraint' AND verdict = 'blocked'`
- **Facts confirmed**: `MATCH (e:Entity {status: 'confirmed'}) RETURN count(e)`
- **Tool calls per week**: `SELECT COUNT(*) FROM tool_calls WHERE created_at > NOW() - INTERVAL '7 days'`

If violations blocked > 0, the system is providing value.

---

## Technical

### Why Neo4j instead of Postgres with pgvector?

Graph relationships (supersedes, affects, supports, constrains) are first-class in Neo4j. Traversals are native and fast. Neo4j 5's vector indexes eliminate the need for a separate vector DB (Pinecone, Weaviate), reducing operational complexity.

### What embedding model do you use?

OpenAI `text-embedding-3-small` (1536 dimensions). **This is fixed at initialization** — changing models later requires reindexing the entire graph.

### What LLM model do you use?

- Haiku (claude-haiku-4-5-20251001) for classification (cheap gate)
- Sonnet (claude-sonnet-4) for extraction, selection, constraint adjudication (quality)

### How does deduplication work?

During extraction, we embed each fact and search for similar entities (vector cosine similarity):
- **Score > 0.92:** Exact duplicate → don't create a new entity, just attach the new Evidence node to the existing one
- **Score 0.80-0.92:** Possible duplicate → create the entity but add a RELATES_TO edge and flag for human review
- **Score < 0.80:** Fresh entity → create normally

### What's the "bias toward allowed" rule?

ADR-010: `check_constraint` must default to "allowed" unless a constraint clearly and explicitly applies. Ambiguity → allowed. False positives (blocking valid work) kill trust and cause uninstall. False negatives (missing a violation) are caught in review.

### Can I run Komponist on-premises?

Yes. The system is self-hosted (no SaaS component). Run Neo4j, Postgres, and the API/MCP/web services wherever you want. No data leaves your infrastructure.

### What's the architecture?

- **Brain:** Neo4j 5 (graph + vector index)
- **App data:** Postgres (webhooks, metrics, sync state)
- **API:** FastAPI (Python 3.12, async)
- **Pipelines:** LangGraph (extraction, compiler)
- **MCP server:** FastMCP (Python, stdio/SSE transports)
- **Web UI:** Next.js 14 (App Router, Tailwind)

---

## Troubleshooting

### No facts are appearing in the review queue

Check:
1. Are webhooks configured correctly? Test with a real PR or Slack message
2. Is the worker processing events? Check `events_raw` table for `processed_at IS NULL`
3. Is the extraction pipeline running? Check API logs for "[Extract]" lines
4. Are entities being created? Query Neo4j: `MATCH (e:Entity {status: 'proposed'}) RETURN count(e)`

### Extraction is creating too many irrelevant facts

Lower the extraction quality threshold by tweaking the classify node prompt (packages/pipelines/extract.py). The gate is intentionally loose (false positives go to review, false negatives are lost forever). You can reject irrelevant facts quickly in the queue.

### search_company_context returns no results

Check:
1. Do confirmed entities exist? `MATCH (e:Entity {status: 'confirmed'}) RETURN count(e)`
2. Is your query specific enough? "auth" is too generic, "authentication library decision" is better
3. Is the embedding dimension correct? Should be 1536 for text-embedding-3-small
4. Is the org_id correct in your MCP config?

### check_constraint never blocks anything

Check:
1. Do confirmed Constraint entities exist?
2. Are constraints global or project-scoped? If project-scoped, pass the project ID
3. Is the intended_action description specific enough? "Make a change" is too vague, "Add Redis as a caching database" is specific
4. Are you testing with an action that actually violates a constraint?

### Slack approval buttons don't work

Check:
1. Is SLACK_BOT_TOKEN set correctly?
2. Is the Slack app installed in the workspace?
3. Does the bot have `chat:write` scope?
4. Is the interaction webhook endpoint configured in Slack app settings? (This is in apps/api/main.py, needs to be exposed)

---

## Best Practices

### What should I put in constraints?

Things that must never be violated:
- "Never auto-confirm extracted entities" (human-in-the-loop)
- "All storage must go through Neo4j or Postgres" (no Redis, no MongoDB)
- "Embedding dimension is fixed at 1536" (reindex is expensive)
- "Database migrations require approval" (safety)

Not: "Write tests for new features" (that's a requirement, not a constraint)

### How do I organize watched Slack channels?

Watch 2-3 high-signal channels only:
- #decisions or #engineering-decisions (explicit decision discussions)
- #engineering or #architecture (where technical choices are debated)

Do NOT watch #general, #random, or standup channels (too much noise).

### Should I backfill more than 90 days?

Probably not for MVP. More history = more facts to review. Start with 90 days, confirm those, then optionally extend.

### How often should I review the queue?

Daily or every few days. Unconfirmed facts don't appear in agent searches, so a backlog just means agents have less context. Set aside 10-15 minutes every few days to clear the queue.

---

## Roadmap

### What's not in MVP?

- Notion/CRM/email connectors
- Fine-tuned extraction models
- Multi-tenant org isolation (single org for MVP)
- Analytics dashboards
- Enterprise SSO
- Temporal "point-in-time" queries

### When will you add X integration?

If 3+ design partners ask for it, we'll prioritize it. Otherwise, post-MVP.

### Can I contribute?

Yes! File issues or PRs at github.com/komponist/komponist. Areas we'd love help with:
- Extraction prompt tuning (packages/pipelines/extract.py)
- Additional eval fixtures (packages/pipelines/eval/fixtures.py)
- Integration connectors (Notion, etc.)
- UI polish (empty states, loading states)

---

## Support

### How do I get help?

1. Check this FAQ
2. Check docs/install.md and docs/deployment.md
3. File an issue: github.com/aistos/aistos/issues
4. Email: support@komponist.dev (design partners only)

### How do I report a bug?

File an issue with:
- What you did
- What you expected
- What actually happened
- Logs (from API, MCP server, or browser console)
- Neo4j/Postgres versions

### How do I request a feature?

File an issue with:
- The problem you're solving
- Your proposed solution
- Why this is important

We prioritize features that:
1. Improve extraction quality
2. Reduce false positives in constraint checking
3. Speed up the review queue
4. Are requested by 3+ design partners

---

**Still have questions?** File an issue: https://github.com/komponist/komponist/issues
