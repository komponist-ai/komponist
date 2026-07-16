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

## Production Deployment

### Fly.io (API + Web)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Create apps
fly apps create komponist-api
fly apps create komponist-web

# Set secrets
fly secrets set -a komponist-api \
  NEO4J_URI=<auradb_uri> \
  NEO4J_USERNAME=neo4j \
  NEO4J_PASSWORD=<password> \
  DATABASE_URL=<neon_url> \
  ANTHROPIC_API_KEY=<key> \
  OPENAI_API_KEY=<key>

# Deploy API
cd apps/api
fly deploy

# Deploy Web
cd apps/web
fly deploy
```

### AuraDB (Neo4j)

1. Create account at https://neo4j.com/cloud/aura/
2. Create "AuraDB Professional" instance
3. Save connection URI and password
4. Enable APOC procedures in instance settings
5. Use URI in NEO4J_URI env var

### Neon (Postgres)

1. Create account at https://neon.tech
2. Create new project
3. Copy connection string
4. Use in DATABASE_URL env var

### Alternative: Railway

Railway provides simpler deployment for both services:

```bash
# Install railway CLI
npm install -g @railway/cli

# Login
railway login

# Create project
railway init

# Add services
railway add  # Select PostgreSQL
railway add  # Select Neo4j (if available, otherwise use AuraDB)

# Deploy
railway up
```

## Health Checks

- API health: `GET /healthz`
- Returns status for Neo4j and Postgres connectivity
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
