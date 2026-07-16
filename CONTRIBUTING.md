# Contributing to Komponist

Thank you for your interest in contributing to Komponist! We're building the open-source company brain together.

## Code of Conduct

Be kind. Assume good intent. Help others learn.

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js 20+
- Python 3.12+
- pnpm (for the web app)

### Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/komponist-ai/komponist.git
   cd komponist
   ```

2. Copy environment config:
   ```bash
   cp .env.example .env
   ```

3. Start the development stack:
   ```bash
   docker compose up -d neo4j postgres
   ```

4. Install dependencies:
   ```bash
   # Web app
   cd apps/web && pnpm install

   # Python packages
   cd packages/core && pip install -e .
   cd packages/pipelines && pip install -e .
   ```

5. Start development servers:
   ```bash
   # Terminal 1: API
   cd apps/api && uvicorn main:app --reload

   # Terminal 2: Web
   cd apps/web && pnpm dev
   ```

## How to Contribute

### Reporting Bugs

1. Check existing issues first
2. Use the bug report template
3. Include:
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Docker version, etc.)

### Suggesting Features

1. Open a discussion first for significant features
2. Describe the use case, not just the solution
3. Consider how it fits with existing architecture

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes
4. Write/update tests
5. Run the test suite: `./scripts/test.sh`
6. Commit with conventional commits: `feat: add X` or `fix: resolve Y`
7. Push and open a PR

### Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `style:` Code style (formatting, semicolons, etc.)
- `refactor:` Code change that neither fixes a bug nor adds a feature
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

## Architecture Overview

```
komponist/
├── apps/
│   ├── api/          # FastAPI backend
│   ├── mcp/          # MCP server for AI agents
│   └── web/          # Next.js frontend
├── packages/
│   ├── core/         # Shared models, graph client, LLM wrapper
│   └── pipelines/    # LangGraph extraction pipeline
├── infra/            # Infrastructure configs
└── docker-compose.yml
```

### Key Concepts

- **Entity**: A single fact, decision, goal, or constraint in the brain
- **Evidence**: Source material that supports an entity (with citations)
- **WorkPack**: A unit of work with context for AI agents
- **MCP Server**: Exposes the brain to AI coding assistants

### Data Flow

```
Sources (Slack, Notion, etc.)
    ↓
Extraction Pipeline (LangGraph)
    ↓
Review Queue (proposed entities)
    ↓
Human Review (confirm/reject/edit)
    ↓
Brain (Neo4j graph)
    ↓
MCP Server → AI Agents
```

## Building Connectors

Connectors live in `apps/api/integrations/`. Each connector:

1. Normalizes source data to `SourceItem`
2. Routes items to the extraction pipeline
3. Handles OAuth (if needed) or configuration

Example connector structure:

```python
# apps/api/integrations/my_source.py

from core.models import SourceItem, SourceType

async def fetch_items(org_id: str) -> AsyncIterator[SourceItem]:
    """Fetch and normalize items from the source."""
    # Your implementation here
    yield SourceItem(
        org_id=org_id,
        source=SourceType.MY_SOURCE,
        kind="document",
        title="...",
        body="...",
        url="...",
        reference="...",
        source_date=datetime.now()
    )
```

## Testing

```bash
# Run all tests
./scripts/test.sh

# Run specific test file
pytest packages/core/tests/test_graph.py

# Run with coverage
pytest --cov=packages/core packages/core/tests/
```

## Documentation

- Keep README.md up to date
- Add docstrings to public functions
- Update architecture docs for significant changes

## Release Process

Releases are automated via GitHub Actions when a version tag is pushed:

```bash
git tag v0.2.0
git push origin v0.2.0
```

## Getting Help

- [GitHub Discussions](https://github.com/komponist-ai/komponist/discussions) for questions
- [Discord](https://discord.gg/komponist) for real-time chat
- [Issues](https://github.com/komponist-ai/komponist/issues) for bugs

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
