# Connect Komponist through MCP

Komponist exposes confirmed, cited company context to MCP-compatible agents over
an authenticated Streamable HTTP endpoint. The MCP server runs as part of the
normal Komponist stack; a client should not receive Neo4j, Postgres, organization
ID, or AI-provider credentials.

## Prerequisites

1. Start Komponist and verify that API, MCP, Neo4j, and Postgres are healthy.
2. Upload or sync knowledge, review it, and confirm at least one entity.
3. Open **Settings → API & MCP**.
4. Create an organization API key and copy it immediately. The plain token is
   shown once; only its hash is stored.

The local MCP URL is:

```text
http://localhost:8080/mcp
```

For a hosted deployment, use its public HTTPS MCP domain, for example:

```text
https://mcp.example.com/mcp
```

## Codex-style TOML configuration

Store the token in your shell or secret manager:

```bash
export KOMPONIST_API_KEY="kom_..."
```

Add the server to the client's TOML configuration:

```toml
[mcp_servers.komponist]
url = "http://localhost:8080/mcp"
bearer_token_env_var = "KOMPONIST_API_KEY"
```

For a hosted deployment, replace only the URL. Keep the token out of the file.

## JSON-based clients

Clients that support remote HTTP MCP servers usually accept the same information
as JSON:

```json
{
  "mcpServers": {
    "komponist": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer ${KOMPONIST_API_KEY}"
      }
    }
  }
}
```

The exact environment-variable syntax differs between clients. If a client
cannot resolve `${KOMPONIST_API_KEY}`, use its built-in secret store rather than
committing the token.

## Verify the connection

Start a fresh agent session and ask:

```text
Search Komponist for the current authentication decisions. Cite the original
evidence and tell me when no confirmed answer exists.
```

A successful connection should:

1. discover the Komponist tools;
2. call `search_company_context`;
3. return only confirmed knowledge visible to the key's organization;
4. include source evidence.

You can also ask the client to read the `company-brain://info` MCP resource.

## Available tools

### `search_company_context`

Search confirmed Decisions, Goals, Constraints, and Projects with evidence.
Use it before planning work that depends on company context.

### `get_active_decisions`

List active decisions, optionally scoped to a topic or project. Superseded and
uncited decisions are excluded from the normal result.

### `report_result`

Report completed agent work and create structured Decision proposals. Calls are
idempotent and every proposed decision enters the Review Queue; an agent cannot
silently confirm its own output.

### `check_constraint`

Check an intended action against confirmed constraints. It returns `allowed`,
`blocked`, or `approval_required` with supporting evidence.

### `request_approval`

Persist a human approval request. Delivery through an external chat provider is
separate from persistence.

### `get_approval_status`

Read the current state of a previously created approval request.

## Recommended agent instructions

Add a short policy to the repository or agent configuration:

```markdown
## Company context

Before an architectural, product, security, or data-model decision:

1. Search Komponist for relevant Decisions, Goals, Constraints, and Projects.
2. Cite the evidence you relied on.
3. Check applicable constraints before implementation.
4. If work creates a durable company decision, report it to Komponist.

Treat no result as missing context, not permission to invent company policy.
Never expose the Komponist API key in code, logs, commits, or browser bundles.
```

## Security model

- The Bearer token determines the organization. A caller does not pass or choose
  `org_id`.
- Keys are individually revocable and fail immediately after revocation.
- The current MVP's programmatic keys are organization-wide, not department
  scoped. Use them only in trusted server-side or agent environments.
- Keep separate keys for separate agents or deployments so access can be
  revoked independently.
- Use HTTPS outside localhost.
- Do not reuse the OpenAI, Neo4j, Postgres, Slack, or Notion credentials as an
  MCP key.

## Troubleshooting

### The client cannot discover tools

- Confirm the URL ends in `/mcp`.
- Confirm the MCP service is healthy and publicly reachable from the client.
- Confirm the Authorization header contains the organization key.
- Restart the client after changing its MCP configuration.

### The server returns `401`

The key is missing, malformed, revoked, or belongs to a deleted/inactive
organization membership. Create a new key under **Settings → API & MCP** and
update the client's secret.

### Search returns no context

- Confirm relevant entities in the Review Queue.
- Confirm they are **confirmed**, not only proposed.
- Check the signed-in user's organization before creating the key.
- Use a specific query.
- Remember that API/MCP keys are organization-scoped and cannot read another
  organization's graph.

### Localhost works but the hosted URL does not

Verify DNS, HTTPS, reverse-proxy routing, and that the public MCP domain forwards
to the MCP service rather than the web or API container. See
[deployment.md](deployment.md) and the
[Coolify runbook](../deploy/hetzner/README.md).

## Next steps

- Review [MVP_STATUS.md](MVP_STATUS.md) before relying on Komponist in
  production.
- Read the REST and SDK examples in the [README](../README.md#api-sdk-and-mcp).
- Report interoperability problems at
  [github.com/komponist-ai/komponist/issues](https://github.com/komponist-ai/komponist/issues).
