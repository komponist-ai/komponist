# Hetzner + Coolify Pilot Deployment

This is the recommended low-cost deployment path for a Komponist design-partner
pilot. It runs the Web application, API, MCP server, PostgreSQL, and Neo4j on
one Hetzner Cloud server. Coolify provides Git-based deployments, HTTPS, logs,
and service management.

This setup is intentionally a **single-server pilot**, not a high-availability
production architecture. A server failure causes downtime until the server or
backup is restored.

## 1. Create the server

Create a fresh server in the [Hetzner Cloud Console](https://console.hetzner.cloud/):

| Setting | Recommended value |
| --- | --- |
| Location | Falkenstein or Nuremberg for an EU/Germany pilot |
| Image | Ubuntu 24.04 LTS |
| Type | CX33: 4 shared vCPU, 8 GB RAM, 80 GB SSD when available |
| Network | Public IPv4 and IPv6 |
| Login | SSH key; do not use password-only login |
| Backups | Enable for the pilot |
| Volume | None initially; use the server disk and monitor storage |

Komponist's idle development stack currently uses about 1.1 GB RAM, but image
builds, Coolify, Neo4j, imports, and concurrent requests need headroom.

### When Cost Optimized instances are unavailable

Hetzner capacity differs by location, so first check CX33 in Nuremberg,
Falkenstein, and Helsinki. Then use this fallback order:

| Choice | Fit | July 2026 German price including VAT, excluding IPv4/backups |
| --- | --- | --- |
| CX33, 8 GB | Preferred low-cost x86 pilot | €10.10/month |
| CAX21, 8 GB | Preferred ARM fallback if available | €12.48/month |
| CPX22, 4 GB | Temporary deployment test only | €23.19/month |
| CPX32, 8 GB | Technically suitable, but not economical for this pilot | €42.23/month |

The production stack has been built and run successfully on ARM64 during local
validation, so CAX21 is a valid option. If only CPX22 is available, use it for a
short, hourly billed deployment test, add 4 GB swap, and set these Coolify
variables before deploying:

```dotenv
KOMPONIST_NEO4J_HEAP_INITIAL_SIZE=128m
KOMPONIST_NEO4J_HEAP_MAX_SIZE=512m
KOMPONIST_NEO4J_PAGECACHE_SIZE=256m
```

CPX22 plus IPv4 is just below a €25 credit for a full month, but adding Hetzner
Backups pushes it above that credit. Since cloud servers are billed hourly up
to the monthly cap, the sensible fallback is to deploy, validate for a few
days, delete the CPX22, and move to an 8 GB CX33/CAX21 when available. Do not
use a 4 GB instance for a real customer pilot.

For a 4 GB fallback, add swap before installing Coolify:

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 2. Add a Hetzner Cloud Firewall

Attach a Hetzner firewall before installing Coolify. Use the provider firewall
rather than relying only on UFW because Docker-published ports can bypass
ordinary UFW rules.

Initial inbound rules:

| Protocol | Port | Source | Purpose |
| --- | --- | --- | --- |
| TCP | 22 | Your current public IP if practical | SSH |
| TCP | 80 | Any IPv4 and IPv6 | HTTP and certificate issuance |
| TCP | 443 | Any IPv4 and IPv6 | HTTPS |
| TCP | 8000 | Your current public IP | Initial Coolify setup |
| TCP | 6001-6002 | Your current public IP | Coolify realtime and terminal during setup |

After assigning a protected HTTPS domain to the Coolify dashboard, remove the
public 8000, 6001, and 6002 rules. Never add public rules for PostgreSQL 5432,
Neo4j 7474/7687, the API container port 8000, the MCP container port 8080, or
the Web container port 3000. Coolify's reverse proxy reaches the application
containers through their private Docker network.

## 3. Install Coolify

Connect over SSH as root and use Coolify's official installer:

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

The installer supports Ubuntu 24.04 LTS and installs Docker. Open the displayed
`http://SERVER_IP:8000` address immediately and create the first administrator;
the first person to register controls the installation.

In Coolify:

1. Set an HTTPS domain for the Coolify dashboard.
2. Enable automatic Coolify updates or establish a monthly update routine.
3. Add an email or webhook notification destination for failed deployments and
   unhealthy resources.

## 4. Configure DNS

Create three DNS `A` records pointing to the server's IPv4 address and matching
`AAAA` records when using IPv6:

| Example hostname | Komponist service |
| --- | --- |
| `app.example.com` | `web`, port 3000 |
| `api.example.com` | `api`, port 8000 |
| `mcp.example.com` | `mcp`, port 8080 |

If the domain uses Cloudflare, start with the records in DNS-only mode. The
Cloudflare proxy can be enabled after Coolify has issued and verified the TLS
certificates.

## 5. Create the Komponist resource

1. Create a Coolify project and a production environment.
2. Add a **Docker Compose** resource from the Komponist Git repository.
3. Select the deployment branch, set **Base Directory** to `/docker`, and set
   **Docker Compose Location** to `/docker-compose.production.yml`.
4. Copy every variable from [`.env.production.example`](.env.production.example)
   into Coolify's environment-variable editor.
5. Generate three independent secrets locally:

   ```bash
   openssl rand -hex 32
   openssl rand -hex 32
   openssl rand -hex 32
   ```

   Use them for `POSTGRES_PASSWORD`, `KOMPONIST_NEO4J_PASSWORD`, and
   `KOMPONIST_SECRET_KEY`. Keep `KOMPONIST_SECRET_KEY` stable: changing it makes
   already encrypted connector credentials unreadable.
6. Add the centrally managed `OPENAI_API_KEY`. Members of customer
   organizations do not provide their own provider key.
7. Keep optional connector variables empty until the matching integration is
   configured.

Do not add resource-level variables named `NEO4J_PASSWORD`,
`NEO4J_HEAP_INITIAL_SIZE`, `NEO4J_HEAP_MAX_SIZE`, or `NEO4J_PAGECACHE_SIZE` in
Coolify. Coolify injects resource variables into the Neo4j container, where any
`NEO4J_*` name is interpreted as a Neo4j configuration setting. Use only the
`KOMPONIST_NEO4J_*` deployment inputs from the example file. The production
Compose file also removes these four legacy names at Neo4j startup so a stale
Coolify variable cannot prevent the database from booting, but deleting the
obsolete resource variables still keeps the deployment configuration clear.

Assign domains to services in Coolify using their internal ports:

- `web`: `https://app.example.com:3000`
- `api`: `https://api.example.com:8000`
- `mcp`: `https://mcp.example.com:8080`

The port in Coolify tells the proxy which container port to use; visitors still
use ordinary HTTPS without a port suffix. Do not assign domains to `postgres`,
`neo4j`, or `worker`.

The `worker` service runs Workroom agent jobs and serves no HTTP traffic, so it
needs no domain. It must still be running: without it, Workroom agent runs are
stored durably but never execute. Confirm it after deploying with
`GET /healthz`, which reports `services.workroom_worker.workers_online`.

The corresponding environment variables contain public origins without port
suffixes:

```dotenv
PUBLIC_WEB_URL=https://app.example.com
PUBLIC_API_URL=https://api.example.com
PUBLIC_MCP_URL=https://mcp.example.com
```

Deploy the resource. The first build takes longer because it builds the
application images and downloads the database images. The `worker` service
reuses the API image, so it adds no extra build time.

## 6. Configure sign-in and connectors

For Google user login, register this exact authorized redirect URI in Google
Cloud:

```text
https://api.example.com/auth/login/google/callback
```

For connected sources, use the matching callbacks only when enabled:

```text
https://api.example.com/auth/notion/callback
https://api.example.com/auth/google/callback
https://api.example.com/auth/slack/callback
```

Update both the provider console and the matching Coolify variables before
testing an OAuth flow.

## 7. Verify the deployment

Check these from a private browser window:

1. `https://api.example.com/healthz` reports healthy PostgreSQL and Neo4j.
2. `https://app.example.com` loads without mixed-content or CORS errors.
3. Email/password registration, logout, and repeat login work.
4. A test document reaches the Review Queue, can be confirmed, appears in the
   graph, and produces a cited Chat answer.
5. Create and revoke a test API key in **Settings → API & MCP**.
6. Verify an authenticated MCP client against
   `https://mcp.example.com/mcp`.
7. Restart the Komponist resource and confirm users, documents, and graph data
   remain available.

The repository-side production check can also be run before each deployment:

```bash
bash scripts/deploy/check-production-compose.sh
```

## 8. Backups and recovery

For the first internal pilot:

- Keep Hetzner automatic backups enabled. The named PostgreSQL and Neo4j
  volumes live on the server disk and are therefore included in a server
  backup.
- Create a manual Hetzner snapshot before schema changes, major upgrades, or
  connector migrations.
- Test one restore before storing irreplaceable customer data.

Server backups are not an application-consistent, off-provider database backup
strategy. Before external design partners depend on Komponist, add nightly
PostgreSQL logical dumps and Neo4j database dumps to S3-compatible storage with
retention, encryption, and a documented restore drill.

## 9. Operating checklist

- Review disk, memory, CPU, health, and deployment failures weekly.
- Never commit the production environment values or paste secrets into issues.
- Rotate any credential that appears in logs or chat.
- Apply Ubuntu security updates and Coolify updates monthly, taking a snapshot
  first.
- Keep registration and organization invitations controlled during the pilot.
- Upgrade the server or split databases out before sustained memory pressure,
  large document collections, or uptime commitments.

Official references:

- [Coolify installation](https://coolify.io/docs/get-started/installation/)
- [Coolify firewall requirements](https://coolify.io/docs/knowledge-base/server/firewall)
- [Coolify Docker Compose behavior](https://coolify.io/docs/knowledge-base/docker/compose)
- [Hetzner Cloud server creation](https://docs.hetzner.com/cloud/servers/getting-started/creating-a-server/)
