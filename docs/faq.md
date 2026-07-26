# Komponist FAQ

This FAQ describes the current self-hostable MVP as of July 2026. For the
evidence behind each status claim, see [MVP_STATUS.md](MVP_STATUS.md).

## Product

### What is Komponist?

Komponist is an open-source context layer for organizations. It turns documents,
shared Notion pages, and selected Slack channels into a reviewed graph of
**Decisions**, **Goals**, **Constraints**, and **Projects**, keeps source
evidence attached, and exposes the confirmed context to people, products, and
AI agents.

It is more than chat over documents:

- **Ask** returns direct, cited answers and keeps multiple conversations.
- **Compose** creates cited presentations, briefings, and summaries with
  designed PDF, editable PowerPoint, and Markdown export.
- **Workrooms** coordinate humans and a durable agent around an approved plan,
  governed context, redirects, approvals, and shared deliverables.
- **Canvas** creates validated, read-only live interfaces over permission-aware
  graph queries.
- **Versions** groups likely file revisions across sources and compares their
  underlying claims.
- The **REST API**, typed JavaScript SDK, and **MCP** expose the same confirmed
  context programmatically.

### What works today?

The browser-upload → extraction → review → confirmed graph → cited answer loop
is verified end to end in Docker. Compose, Workrooms, Canvas, Versions, the API,
and all six MCP tool contracts have provider-free end-to-end coverage. The
single-server Coolify deployment has run publicly over HTTPS.

Slack selected-channel sync and Notion internal-integration sync are implemented
and have been exercised manually. Large live workspaces, every provider edge
case, external MCP hosts, backup restoration, and managed-cloud operations
still need broader validation.

### What is not ready yet?

Komponist is not yet a production-ready managed SaaS. It does not yet include
password reset, billing, quotas, enterprise SSO, operational dashboards,
off-server backup restoration, live Workroom presence, email room invitations,
parallel specialist agents, or writable Canvas actions.

Google Drive, GitHub, and Linear are not presented as working product
connectors until their complete provider flows meet the same validation bar as
uploads, Notion, and Slack.

## Knowledge and trust

### Why only four entity types?

Decisions, Goals, Constraints, and Projects are the narrow MVP ontology. They
capture durable organizational context without turning every sentence or
person name into noisy graph data. More types should be introduced only after a
real use case proves that the existing four cannot express it.

### What happens after extraction?

New entities are **proposed** by default. A member reviews the statement and its
exact evidence, then confirms, rejects, edits, or merges it. Only confirmed
knowledge is used by normal chat, Compose, Workrooms, Canvas, API, and MCP
retrieval.

An organization can deliberately enable auto-publish, but that trades review
control for speed.

### Are citations preserved?

Yes. Evidence stores the source type, source reference, excerpt, URL where
available, and source date. Answers and generated artifacts cite the evidence
that supported them. Workroom runs also keep an immutable context snapshot.

### How are duplicate uploads handled?

The extraction pipeline uses stable content identity, so uploading identical
content under another filename reuses the existing extraction while preserving
the new document provenance. Versions additionally groups likely revisions by
content hash, normalized name, chronology, and overlap between extracted
claims.

### Why Neo4j?

Relationships such as `SUPPORTS`, `AFFECTS`, `CONSTRAINS`, and `SUPERSEDES` are
part of the product, not metadata added after retrieval. Neo4j stores those
relationships and the vector index in one permission-scoped knowledge layer.
Postgres stores identity, configuration, conversations, jobs, and audit state.

## AI and privacy

### Do members need their own AI keys?

No. A deployment owner configures one centrally managed provider key. Workspace
members never enter provider credentials.

### Can Komponist run without a model?

`KOMPONIST_AI_MODE=mock` runs deterministic test doubles and makes no AI-provider
network calls. This validates workflows and contracts, but not extraction,
retrieval, planning, or writing quality.

Use `KOMPONIST_AI_MODE=live` with an OpenAI project key for real extraction,
embeddings, chat, Compose, Workroom planning, and Canvas generation.

### What leaves the server in live mode?

Relevant document and query content is sent to the centrally configured OpenAI
models. Responses API storage is disabled by default with
`KOMPONIST_OPENAI_STORE=false`. Connected source credentials are encrypted in
Postgres with `KOMPONIST_SECRET_KEY`.

## Sources

### How do I add documents?

Open **Add Source → Upload documents**. Markdown, text, YAML, and YML are
supported directly. The upload enters the same extraction and review path as a
connector sync.

### How do I connect Notion?

Create a Notion Internal Integration, share only the intended pages with that
integration through **••• → Connections**, then paste its `ntn_…` or legacy
`secret_…` token in **Add Source → Notion**. A customer does not configure
deployment environment variables for this path.

### How do I connect Slack?

The Komponist deployment owner creates one Slack app and configures its client
ID, client secret, and signing secret. Each customer then uses **Connect Slack**
to install that app into their own workspace and explicitly selects the
channels Komponist may sync. Customers never receive or configure the
deployment secrets.

Start with a few high-signal channels. Importing an entire workspace at once
creates unnecessary review load and makes quality harder to evaluate.

### Does deleting a synced document delete the original?

No. Deleting a synced document removes its Komponist copy and derived context
only. It does not delete the Notion page, Slack message, or provider attachment.

## Organizations and permissions

### Is data isolated between organizations?

Yes. Browser requests derive the active organization from a revocable session.
REST and MCP requests derive it from a hashed, revocable API key. Callers
cannot select an arbitrary organization ID.

### How do departments work?

Organization-wide knowledge is visible to all active members. Department-scoped
knowledge is visible to owners/admins and to members or viewers assigned to a
matching department. Uploads can be scoped per document; connected items inherit
their source's default department.

Organization API and MCP keys are currently organization-wide. Do not expose
them to department-limited users or browser code.

### Which roles exist?

- **Owner:** all data and organization administration.
- **Admin:** all data and non-owner administration.
- **Member:** reads and contributes inside organization and assigned scopes.
- **Viewer:** read-only access inside organization and assigned scopes.

## Workrooms, Compose, and Canvas

### What can a Workroom do?

A Workroom has an objective, participants, room visibility, a versioned
model-generated plan, editable tasks, context pins/exclusions, shared
conversation, durable agent runs, an immutable activity trail, and shared
Compose deliverables. Plans require human approval before execution.

Run at least one separate worker service. Without it, jobs remain stored safely
but do not execute.

### Are Workroom agents autonomous?

The MVP runs one Komponist Analyst. It can research confirmed context and draft
a deliverable, but it cannot widen room permissions, edit source systems, or
skip explicit approvals. Pause and cancellation take effect at the next safe
step; an already-running provider request cannot be recalled.

### What does Compose generate?

Compose creates presentations, executive briefings, and summaries from
permission-scoped confirmed context. It keeps private history, shows citations
in the preview, and exports designed PDF, editable `.pptx`, or Markdown with an
evidence appendix.

### Does Canvas execute generated code?

No. The model creates a declarative `CanvasSpec` from a closed component and
query vocabulary. The server validates it and owns every graph query. A Canvas
stores the question/specification and resolves current data separately for each
viewer. The MVP is read-only and cannot call external URLs or mutate data.

## API and MCP

### How do I connect an application or agent?

Create an organization-scoped key under **Settings → API & MCP**. Use it as a
Bearer token with the REST API, typed SDK, or Streamable HTTP MCP endpoint.
Keys are hashed at rest, shown once, individually revocable, and
organization-wide in the current MVP.

### Which MCP tools exist?

- `search_company_context`
- `get_active_decisions`
- `report_result`
- `check_constraint`
- `request_approval`
- `get_approval_status`

`company-brain://info` exposes compact brain metadata. Writeback through
`report_result` creates proposed Decisions that still require review.

## Troubleshooting

### Upload or sync says it worked, but nothing appears in the graph

Check the **Review Queue** first. Proposed entities do not appear in normal
confirmed-only retrieval until approved. Also verify the active organization,
department scope, source sync result, and the graph's type/status filters.

### Search or chat returns nothing

Confirm that visible entities exist and are confirmed, then try a more specific
question. In mock mode semantic quality is intentionally not representative.
In live mode verify the embedding model still uses the 1536-dimensional graph
index.

### A Workroom run stays queued

Open the health endpoint and check `workroom_worker.workers_online`. Start the
`worker` Compose service or `python worker.py`. The job remains durable while no
worker is online.

### Where can I report a problem?

Open an issue at
[github.com/komponist-ai/komponist/issues](https://github.com/komponist-ai/komponist/issues)
with reproduction steps, the expected result, the actual result, and relevant
API/worker logs. Remove credentials and private company content first.
