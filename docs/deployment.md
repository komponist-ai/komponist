# Deployment Guide

## Local Development

### Prerequisites
- Python 3.12+
- Node.js 18+
- Docker Desktop (for Neo4j and Postgres)

### Start Infrastructure

```bash
# Start Neo4j and Postgres
docker compose -f infra/docker-compose.dev.yml up -d

# Verify containers are running
docker ps

# Neo4j browser: http://localhost:7474 (neo4j/devpassword)
# Postgres: localhost:5432 (komponist/devpassword)
```

### Backend Setup

```bash
cd apps/api

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start API server
python main.py
# or: uvicorn main:app --reload
```

API will be available at http://localhost:8000

Health check: http://localhost:8000/healthz

### Frontend Setup

```bash
cd apps/web

# Install dependencies
npm install

# Start dev server
npm run dev
```

Web UI will be available at http://localhost:3000

### MCP Server Setup

```bash
cd apps/mcp

# Install dependencies
pip install -r requirements.txt

# Start MCP server (stdio transport)
fastmcp run server:mcp
```

See [install.md](install.md) for connecting to Claude Code/Cursor.

### Workroom Worker Setup

Workroom agent runs execute in a separate worker process, not inside the API.
The API only writes a job row to Postgres and returns, so queued and in-flight
work survives an API restart or redeploy.

```bash
cd apps/api

# Same dependencies and image as the API
python worker.py
```

Run at least one worker whenever Workrooms are in use. Without it, agent runs
stay `queued` indefinitely — the API stays healthy and keeps accepting work,
and `GET /healthz` reports `services.workroom_worker.workers_online: 0`.

Workers are stateless and safe to run several at once. Postgres hands each job
to exactly one worker using `SELECT ... FOR UPDATE SKIP LOCKED`:

```bash
docker compose -f docker/docker-compose.production.yml up -d --scale worker=3
```

Tunable via environment variables (defaults shown):

| Variable | Default | Purpose |
|----------|---------|---------|
| `KOMPONIST_WORKROOM_LEASE_SECONDS` | `120` | How long a claimed job is owned before it is considered abandoned |
| `KOMPONIST_WORKROOM_HEARTBEAT_SECONDS` | `20` | Lease renewal interval while a job runs |
| `KOMPONIST_WORKROOM_MAX_ATTEMPTS` | `3` | Attempts before a job is failed permanently |
| `KOMPONIST_WORKROOM_RETRY_SECONDS` | `5` | Base delay for exponential retry backoff |
| `KOMPONIST_WORKROOM_MAX_RETRY_SECONDS` | `300` | Upper bound on retry backoff |
| `KOMPONIST_WORKROOM_WORKER_STALE_SECONDS` | `90` | Silence after which a worker is reported offline |
| `KOMPONIST_WORKER_POLL_SECONDS` | `1` | Idle polling interval |

#### Worker recovery

If a worker crashes or its container is killed mid-job, its lease expires and
another worker requeues the job automatically — no manual step is required.
Recovery runs on every poll cycle, so the delay is bounded by the lease window.

To inspect the queue directly:

```sql
SELECT status, job_type, attempt_count, max_attempts, error_code, available_at
FROM workroom_jobs
ORDER BY updated_at DESC
LIMIT 20;
```

A job in `failed` has exhausted `max_attempts`. Its run is marked `failed` too,
and a person can retry it from the Workroom (`POST /workroom-runs/{id}/retry`)
rather than an operator editing rows by hand.

## Production Deployment

The recommended pilot architecture is one 8 GB Hetzner Cloud instance running
self-hosted Coolify and the production Compose stack in
[`docker/docker-compose.production.yml`](../docker/docker-compose.production.yml).
It keeps PostgreSQL and Neo4j on a private Docker network while Coolify exposes
only Web, API, and MCP through HTTPS.

Follow the complete [Hetzner + Coolify runbook](../deploy/hetzner/README.md).
The runbook covers server sizing, provider firewall rules, DNS, secrets,
service-domain routing, OAuth callbacks, verification, backups, and operations.

Validate the production topology locally or in CI with:

```bash
bash scripts/deploy/check-production-compose.sh
```

The single-server design is appropriate for an internal or design-partner
pilot. It does not provide high availability. Before making uptime commitments,
move application-consistent database backups off-server and consider separating
the databases from the application host.

## Health Checks

- API health: `GET /healthz`
- Returns status for Neo4j and Postgres connectivity
- Also reports `services.workroom_worker`: workers online, queue depth by
  state, and the last worker heartbeat. The API is deliberately still
  `healthy` when no worker is online, because it can accept and durably store
  work regardless; alert on `workers_online == 0` together with a non-zero
  `queued` count.
- Use for monitoring/alerting

## Monitoring

Key metrics in `tool_calls` table:
- Tool usage by org
- Violations blocked (verdict field)
- Latency per tool
- Agent client distribution

Query example:
```sql
SELECT 
  tool,
  verdict,
  COUNT(*) as calls,
  AVG(latency_ms) as avg_latency
FROM tool_calls
WHERE org_id = 'xxx'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY tool, verdict;
```

## Troubleshooting

### Neo4j connection fails
- Check APOC plugin is installed: `CALL apoc.help('all')`
- Verify credentials and URI
- Check firewall/network settings for port 7687

### Postgres connection fails
- Test with: `psql $DATABASE_URL`
- Check SSL requirements (add `?sslmode=require` if needed)
- Verify asyncpg is installed

### Webhooks not processing
- Check `events_raw` table for errors
- Verify webhook signatures
- Check worker logs
- Ensure processed_at is NULL for pending events
