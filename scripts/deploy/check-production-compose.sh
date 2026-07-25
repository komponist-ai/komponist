#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
compose_file="$repo_root/docker/docker-compose.production.yml"
env_file="$repo_root/deploy/hetzner/.env.production.example"

for variable in \
  NEO4J_PASSWORD \
  NEO4J_HEAP_INITIAL_SIZE \
  NEO4J_HEAP_MAX_SIZE \
  NEO4J_PAGECACHE_SIZE; do
  if grep -Fq '${'"$variable" "$compose_file"; then
    echo "Production Compose must not use resource input $variable; prefix it with KOMPONIST_ to avoid Coolify injecting an invalid Neo4j setting." >&2
    exit 1
  fi
done

if docker compose version >/dev/null 2>&1; then
  compose=(docker compose)
elif [[ -x /Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose ]]; then
  compose=(/Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose)
elif command -v docker-compose >/dev/null 2>&1 && \
  [[ "$(docker-compose version --short)" == 2.* ]]; then
  compose=(docker-compose)
else
  echo "Docker Compose v2 is required to validate the production stack." >&2
  exit 1
fi

"${compose[@]}" \
  --env-file "$env_file" \
  -f "$compose_file" \
  config --quiet

resolved_config="$({
  "${compose[@]}" \
    --env-file "$env_file" \
    -f "$compose_file" \
    config --format json
})"

python3 -c '
import json
import sys

config = json.load(sys.stdin)
services = config.get("services", {})
expected = {"api", "mcp", "neo4j", "postgres", "web", "worker"}
missing = expected - set(services)
if missing:
    raise SystemExit(f"missing production services: {sorted(missing)}")

published = {
    name: service["ports"]
    for name, service in services.items()
    if service.get("ports")
}
if published:
    raise SystemExit(f"production services publish host ports: {published}")

for database in ("postgres", "neo4j"):
    if not services[database].get("healthcheck"):
        raise SystemExit(f"{database} has no healthcheck")

for application in ("api", "mcp", "web", "worker"):
    service = services[application]
    if not service.get("healthcheck"):
        raise SystemExit(f"{application} has no healthcheck")
    if service.get("restart") != "unless-stopped":
        raise SystemExit(f"{application} does not restart unless stopped")

print("Production Compose configuration is structurally valid.")
' <<< "$resolved_config"
