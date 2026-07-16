<p align="center">
  <img src="assets/images/komponist_logo_big.png" alt="Komponist" width="600" />
</p>

<h1 align="center">Komponist</h1>

<p align="center">
  <strong>The company brain you own.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License" /></a>
  <a href="docker/docker-compose.yml"><img src="https://img.shields.io/badge/Docker-Ready-blue" alt="Docker" /></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="docs/">Docs</a> •
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

Komponist is an open-source, self-hostable company brain for AI agents. Connect your Slack, Notion, and Google Drive to build a cited knowledge graph of your company's goals, decisions, constraints, and context. AI coding assistants query it via MCP to work with full organizational awareness.

## Quick Start

```bash
# Clone and configure
git clone https://github.com/komponist-ai/komponist.git
cd komponist
cp .env.example .env
# Add your API keys to .env

# Start everything
docker compose -f docker/docker-compose.yml up

# Visit http://localhost:3000
```

## Features

- **Self-hosted** — Run on your infrastructure. Your data stays yours.
- **Cited facts** — Every entity links back to source evidence.
- **Human-in-the-loop** — Review and confirm extracted facts before they enter the brain.
- **MCP integration** — AI coding assistants query via standard MCP tools.
- **Data portability** — Export/import your brain as YAML.
- **Configurable LLMs** — Use Anthropic, OpenAI, or local Ollama.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                         Your Sources                            │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐    │
│  │  Slack  │  │ Notion  │  │ Google  │  │ Local Documents │    │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────────┬────────┘    │
└───────┼────────────┼────────────┼────────────────┼──────────────┘
        │            │            │                │
        └────────────┴─────┬──────┴────────────────┘
                           ▼
                 ┌─────────────────┐
                 │   Extraction    │  LLM extracts goals, decisions,
                 │    Pipeline     │  constraints, customer requests
                 └────────┬────────┘
                          ▼
                 ┌─────────────────┐
                 │  Review Queue   │  You confirm, reject, or edit
                 │    (Web UI)     │  each proposed fact
                 └────────┬────────┘
                          ▼
                 ┌─────────────────┐
                 │  Company Brain  │  Neo4j graph with citations
                 │    (Neo4j)      │  and semantic search
                 └────────┬────────┘
                          ▼
                 ┌─────────────────┐
                 │   MCP Server    │  AI agents query for context
                 └─────────────────┘
```

## Architecture

```
komponist/
├── apps/
│   ├── api/              # FastAPI backend (webhooks, REST, OAuth)
│   ├── mcp/              # MCP server (6 tools for AI agents)
│   └── web/              # Next.js UI (review queue, graph browser)
├── packages/
│   ├── core/             # Graph client, models, LLM/embedding clients
│   └── pipelines/        # LangGraph extraction pipeline
├── docker/               # Docker Compose and Dockerfiles
└── docs/                 # Documentation and design system
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| web | 3000 | Next.js frontend |
| api | 8000 | FastAPI backend |
| mcp | 8080 | MCP server |
| neo4j | 7474, 7687 | Graph database |
| postgres | 5432 | App database |

## MCP Tools

The MCP server exposes six tools to AI coding assistants:

| Tool | Description |
|------|-------------|
| `search_company_context` | Semantic search across the brain |
| `get_active_decisions` | List recent confirmed decisions |
| `check_constraint` | Verify if an action violates constraints |
| `report_result` | Log outcomes back to the brain |
| `request_approval` | Ask for human approval on actions |
| `get_approval_status` | Check pending approval requests |

### Claude Code Setup

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "komponist": {
      "command": "docker",
      "args": ["exec", "-i", "komponist-mcp", "python", "-m", "server"]
    }
  }
}
```

Or connect directly:

```json
{
  "mcpServers": {
    "komponist": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Configuration

### Environment Variables

```bash
# LLM Provider (anthropic, openai, ollama)
KOMPONIST_LLM_PROVIDER=anthropic
KOMPONIST_LLM_MODEL=claude-sonnet-4-20250514

# Embeddings (openai, ollama)
KOMPONIST_EMBEDDING_PROVIDER=openai
KOMPONIST_EMBEDDING_MODEL=text-embedding-3-small

# Local documents path
KOMPONIST_LOCAL_DOCS_PATH=./docs

# Ollama (for local models)
OLLAMA_BASE_URL=http://ollama:11434

# API Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# OAuth (for connectors)
NOTION_CLIENT_ID=...
NOTION_CLIENT_SECRET=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
```

### Local Models with Ollama

Run entirely locally with Ollama:

```bash
# Pull models
ollama pull llama3
ollama pull nomic-embed-text

# Configure .env
KOMPONIST_LLM_PROVIDER=ollama
KOMPONIST_LLM_MODEL=llama3
KOMPONIST_EMBEDDING_PROVIDER=ollama
KOMPONIST_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## Development

```bash
# Start databases only
docker compose -f docker/docker-compose.dev.yml up -d

# Run API locally
cd apps/api && pip install -r requirements.txt && uvicorn main:app --reload

# Run web locally
cd apps/web && pnpm install && pnpm dev
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development guide.

## Documentation

- [Installation Guide](docs/install.md) — MCP setup for Claude Code/Cursor
- [Deployment Guide](docs/deployment.md) — Local and production deployment
- [Architecture Decisions](docs/DECISIONS.md) — ADRs and design rationale
- [Design System](docs/design.md) — UI/UX guidelines
- [FAQ](docs/faq.md) — Common questions answered

## Editions

| Edition | Description | Status |
|---------|-------------|--------|
| **Community** | Open-source, self-hosted | Available |
| **Cloud** | Managed SaaS | Coming soon |
| **Private** | Deploy to your cloud with our support | Contact us |

## Community

- [GitHub Issues](https://github.com/komponist-ai/komponist/issues) — Bug reports and feature requests
- [Discussions](https://github.com/komponist-ai/komponist/discussions) — Questions and ideas

## License

Apache 2.0. See [LICENSE](LICENSE).

---

<p align="center">
  Built with care for teams who want AI agents that understand their business.
</p>
