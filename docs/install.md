# Installing the Komponist MCP Server

This guide shows how to connect Claude Code and Cursor to your Komponist company brain.

## Prerequisites

- Komponist API running (see [deployment.md](deployment.md))
- Neo4j database initialized with your org's data
- Organization ID from your Komponist account

## Claude Code Installation

Add the Komponist MCP server to your Claude Code configuration:

### 1. Edit `.mcp.json`

```bash
# In your project or home directory
nano ~/.claude/mcp.json
```

### 2. Add Komponist server

```json
{
  "mcpServers": {
    "komponist": {
      "command": "python",
      "args": ["/path/to/komponist/apps/mcp/server.py"],
      "env": {
        "KOMPONIST_ORG_ID": "your-org-id",
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "your-password",
        "KOMPONIST_AI_MODE": "mock",
        "KOMPONIST_LLM_PROVIDER": "openai",
        "KOMPONIST_EMBEDDING_PROVIDER": "openai",
        "DATABASE_URL": "postgresql+asyncpg://..."
      }
    }
  }
}
```

Mock mode makes no AI network calls. For live extraction and semantic search,
set `KOMPONIST_AI_MODE` to `live` and add a project-scoped `OPENAI_API_KEY`.

### 3. Verify installation

```bash
# In a fresh Claude Code session
```

Ask Claude: "What auth approach do we use and why?"

Claude should call `search_company_context` and return your team's auth decision with citations.

## Cursor Installation

### 1. Open Cursor settings

`Cmd+,` (Mac) or `Ctrl+,` (Windows/Linux) → Search "MCP"

### 2. Add server config

Same JSON as Claude Code above.

### 3. Restart Cursor

The Komponist tools will appear in Cursor's composer.

## Adding Project Instructions

Tell the agent to consult Komponist before architectural decisions:

Create `CLAUDE.md` in your project root:

```markdown
# Project Instructions for Claude

## Architecture Decisions

Before making architectural changes (choosing libraries, changing data models, adding integrations):

1. **Search existing decisions**: Use `search_company_context` to find relevant ADRs and decisions
2. **Check constraints**: After drafting your approach, describe it and ask if any constraints apply
3. **Report new decisions**: After implementing, use `report_result` to document new decisions made

Example: "I'm about to add Redis for caching. Let me search for caching decisions first."

## Active Constraints

Use `get_active_decisions` to review constraints before:
- Database schema changes
- Adding dependencies
- Changing authentication/authorization
- Modifying API contracts

## After Completing Work

Always call `report_result` with:
- Summary of what you built
- New decisions made (e.g., "chose library X over Y because...")
- Any deviations from original plan
- Unresolved questions

This keeps the company brain up to date.
```

## Available Tools

### `search_company_context(query, types?, limit?)`

Search the brain for goals, decisions, constraints, and customer requests.

**Example:**
```
Agent: Let me search for our authentication decisions.

Tool call: search_company_context("authentication auth identity")

Result:
**[Decision]** Use WorkOS for enterprise identity management
  WorkOS handles SSO, directory sync, and compliance out of the box.
  Confidence: high
  📎 github · PR#142 · https://github.com/komponist/komponist/pull/142
```

### `get_active_decisions(topic?, project?)`

Get all active (non-superseded) decisions, optionally filtered by topic.

**Example:**
```
Tool call: get_active_decisions("database")

Result:
**Use Neo4j 5.x with native vector indexes as the company brain**
  Neo4j 5's native vector indexes eliminate need for separate vector DB.
  Confidence: high
  📎 manual · ADR-001 · ...
```

### `report_result(summary, new_decisions?, deviations?, unresolved_questions?, work_pack_id?)`

Report work completion and feed new decisions back into the brain.

**Example:**
```
Tool call: report_result(
  summary="Added Redis caching for API endpoints. 60% latency reduction.",
  new_decisions=[{
    "statement": "Use Redis for API response caching with 5-minute TTL",
    "detail": "Reduces P95 latency from 800ms to 320ms. TTL chosen to balance freshness and hit rate."
  }]
)

Result:
✅ Report received. 1 new decision(s) added to review queue.
```

## Testing the Connection

Run this test in Claude Code:

```
You: What architectural decisions have we made about the database?

Claude: Let me search the company brain.
[calls search_company_context("database architecture")]

Claude: Based on your company brain, you've decided to:

**Use Neo4j 5.x as the company brain storage**
- Neo4j's native vector indexes eliminate the need for a separate vector database
- Embedding dimension is fixed at 1536 (text-embedding-3-small)
- Source: ADR-001 from GitHub

This was confirmed on July 1, 2026 by sovin.
```

If you see the tool call and cited result, you're connected! 🎉

## Troubleshooting

### "Tool search_company_context not found"

- Check `.mcp.json` path is correct
- Restart Claude Code/Cursor after config changes
- Verify Python dependencies installed: `cd apps/mcp && pip install -r requirements.txt`

### "No context found for this query"

- Check Neo4j is running and accessible
- Verify `KOMPONIST_ORG_ID` matches your data's org_id
- Confirm you have confirmed entities in the graph (not just proposed)

### "Database connection failed"

- Test Neo4j connection: `cypher-shell -u neo4j -p your-password "RETURN 1"`
- Check DATABASE_URL for Postgres (tool call logging)
- Verify firewall/network allows connections

### Permission prompts

Add these to your Claude Code `~/.claude/settings.json` to reduce prompts:

```json
{
  "autoApprovals": {
    "mcp_tools": ["komponist:search_company_context", "komponist:get_active_decisions"]
  }
}
```

(Keep `report_result` and `check_constraint` requiring approval.)

## Next Steps

- Review your first extracted facts in the queue: http://localhost:3000/queue
- Connect GitHub, Slack, and Linear to start ingesting decisions
- Add constraints and watch `check_constraint` block risky actions

## Security Notes

- MCP server runs locally with your credentials
- Tool calls are logged to `tool_calls` table for metrics
- No data is sent to Komponist servers (self-hosted)
- API keys never leave your environment

---

Questions? File an issue: https://github.com/komponist/komponist/issues
