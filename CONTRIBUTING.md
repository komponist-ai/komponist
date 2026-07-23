# Contributing to Komponist

Thank you for helping build Komponist. The project is an open-source,
self-hostable context backend that turns company sources into reviewed,
cited knowledge for people and AI agents.

## Before you start

- Search existing issues before opening a new one.
- Open an issue or discussion before investing in a large architectural
  change.
- Never include customer data, credentials, tokens, or production exports in
  issues, pull requests, fixtures, or logs.
- Report security vulnerabilities through the private process described in
  [SECURITY.md](SECURITY.md), not through a public issue.
- Participation in this project is governed by
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Prerequisites

- Docker Desktop or Docker Engine with Docker Compose v2
- Node.js 20
- Python 3.12
- Git

The repository uses **npm**, not pnpm or Yarn.

## Quick development setup

Clone the repository and create a local configuration:

```bash
git clone https://github.com/komponist-ai/komponist.git
cd komponist
cp .env.example .env
```

For a provider-free development environment, set:

```dotenv
KOMPONIST_AI_MODE=mock
KOMPONIST_SECRET_KEY=replace-with-a-long-random-secret
OPENAI_API_KEY=
```

Start the complete stack:

```bash
docker compose --env-file .env \
  -f docker/docker-compose.yml \
  up -d --build --wait
```

The main services are:

| Service | URL |
| --- | --- |
| Web | http://localhost:3000 |
| API and OpenAPI | http://localhost:8000 and http://localhost:8000/docs |
| MCP | http://localhost:8080/mcp |
| Neo4j Browser | http://localhost:7474 |

### Web development with hot reload

```bash
docker compose --env-file .env \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.web-dev.yml \
  up -d --build
```

Changes under `apps/web` then appear without rebuilding the container.

### Running application services locally

Start infrastructure:

```bash
docker compose -f docker/docker-compose.dev.yml up -d
```

Create and populate a Python environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e packages/core -e packages/pipelines \
  -r apps/api/requirements.txt \
  -r apps/mcp/requirements.txt \
  -r packages/core/test-requirements.txt
```

Run the API:

```bash
cd apps/api
PYTHONPATH=../../packages uvicorn main:app --reload --port 8000
```

Run the web application:

```bash
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

Run MCP over Streamable HTTP:

```bash
cd apps/mcp
PYTHONPATH=../../packages fastmcp run server.py:mcp \
  --transport http --host 0.0.0.0 --port 8080
```

## Repository layout

```text
komponist/
├── apps/
│   ├── api/              # FastAPI, auth, REST, chat, connectors
│   ├── mcp/              # FastMCP server and agent tools
│   └── web/              # Next.js Studio and landing page
├── packages/
│   ├── core/             # Graph, models, AI and embedding clients
│   ├── pipelines/        # Extraction and compiler pipelines
│   └── sdk-js/           # Typed JavaScript client
├── docker/               # Development, CI, and production Compose files
├── scripts/              # CI and deployment validation
├── test-data/upload/     # Fictional documents for local testing
└── docs/                 # Status, deployment, design, FAQ, and decisions
```

## Making a change

1. Create a focused branch from the latest `main`.
2. Keep unrelated changes out of the same pull request.
3. Add or update tests for behavioral changes.
4. Update documentation when public behavior or configuration changes.
5. Run the relevant checks.
6. Use a Conventional Commit.
7. Open a pull request using the repository template.

Examples:

```text
feat(chat): add cited follow-up questions
fix(auth): reject expired organization invites
docs: clarify local OpenAI configuration
```

## Validation

Run the provider-free Python contracts:

```bash
PYTHONPATH=packages python -m pytest -q \
  packages/core/tests/test_ai_clients.py \
  packages/pipelines/tests/test_contracts.py \
  packages/pipelines/tests/test_document_relationships.py \
  packages/pipelines/tests/test_identical_document_reuse.py
```

Run the web checks:

```bash
npm --prefix apps/web ci --no-audit --no-fund
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

Run the SDK checks:

```bash
npm --prefix packages/sdk-js ci --no-audit --no-fund
npm --prefix packages/sdk-js run build
npm --prefix packages/sdk-js test
git diff --exit-code -- packages/sdk-js/dist
```

Run the Docker end-to-end suite:

```bash
docker compose \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.ci.yml \
  up -d --build --wait --wait-timeout 240

bash scripts/ci/run-e2e.sh

docker compose \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.ci.yml \
  down --volumes --remove-orphans
```

Validate the production Compose topology:

```bash
bash scripts/deploy/check-production-compose.sh
```

Pull requests must pass the required GitHub Actions checks before merge.

## Connector contributions

Connectors live in `apps/api/integrations/`. A connector must:

- normalize provider data into the shared source-item contract;
- preserve stable provider references and source timestamps;
- verify webhook signatures by default;
- store credentials through the encrypted organization configuration;
- enforce organization and department visibility;
- route content through the standard extraction and review lifecycle;
- include provider-free contract tests.

Do not add a connector that silently publishes extracted facts directly to the
confirmed graph.

## Documentation and fixtures

- Keep README and `docs/MVP_STATUS.md` aligned with verified behavior.
- Label unverified integrations and deployment boundaries clearly.
- Use fictional companies and people in examples.
- Do not paste production logs without removing credentials, personal data,
  hostnames, and identifiers.

## Releases

There is currently no automated public release pipeline. Do not create or push
version tags unless a maintainer has agreed on the release. The JavaScript SDK
is a workspace package and is not yet published to npm.

## License

By submitting a contribution, you agree that it is licensed under the
[Apache License 2.0](LICENSE). The Komponist name and logos are governed
separately by [TRADEMARKS.md](TRADEMARKS.md).
