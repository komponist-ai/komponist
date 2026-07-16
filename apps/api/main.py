"""
Komponist API

FastAPI application for webhooks, REST endpoints, and health checks.
The programmable company brain.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse

import sys
sys.path.append("../../packages")

from core.graph import GraphClient
from core.export import export_brain_yaml
from core.import_ import import_brain_yaml
from database import init_db, health_check_db


# Import security utilities
from security import validate_org_id, check_rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    GraphClient.initialize()
    await init_db()
    print("✓ Databases initialized")

    yield

    # Shutdown
    await GraphClient.close()
    print("✓ Connections closed")


app = FastAPI(
    title="Komponist API",
    description="The programmable company brain. Company context, composed for every agent.",
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for connected sources (TODO: persist to database)
connected_sources: dict = {}

# In-memory store for org settings (TODO: persist to database)
org_settings: dict = {}

def get_org_settings(org_id: str) -> dict:
    """Get settings for an org with defaults."""
    defaults = {
        "auto_confirm": True,  # Auto-confirm extracted entities by default
        "extraction_model": "gpt-4o",
        "parallel_batch_size": 5,
    }
    settings = org_settings.get(org_id, {})
    return {**defaults, **settings}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Komponist API",
        "version": "0.1.0",
        "tagline": "The programmable company brain"
    }


@app.get("/healthz")
async def health_check():
    """
    Health check endpoint.

    Verifies connectivity to Neo4j and Postgres.
    """
    neo4j_health = await GraphClient.health_check()
    postgres_health = await health_check_db()

    overall_healthy = (
        neo4j_health["status"] == "healthy" and
        postgres_health["status"] == "healthy"
    )

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "services": {
            "neo4j": neo4j_health,
            "postgres": postgres_health
        }
    }


# Queue and entity management routes

@app.get("/queue")
async def get_queue(org_id: str = "default-org"):
    """Get review queue (proposed entities)."""
    query = """
    MATCH (e:Entity {org_id: $org_id, status: 'proposed'})
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    OPTIONAL MATCH (e)-[r:RELATES_TO]->(related:Entity)
    WHERE r.score > 0.80
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.confidence as confidence,
        e.created_at as created_at,
        collect(DISTINCT ev{.id, .source, .reference, .url, .source_date}) as evidence,
        collect(DISTINCT {id: related.id, statement: related.statement, score: r.score}) as related_to
    ORDER BY e.created_at DESC
    """

    results = await GraphClient.run_query(query, {"org_id": org_id})

    # Filter out null evidence/related_to
    for r in results:
        r["evidence"] = [e for e in r.get("evidence", []) if e.get("id")]
        r["related_to"] = [rel for rel in r.get("related_to", []) if rel.get("id")]

    return {"items": results, "total": len(results)}


@app.get("/entities")
async def list_entities(
    org_id: str = "default-org",
    status: str = "confirmed",
    entity_type: Optional[str] = None,
    limit: int = 100
):
    """List brain entities."""
    type_filter = ""
    if entity_type:
        type_filter = "AND e.entity_type = $entity_type"

    query = f"""
    MATCH (e:Entity {{org_id: $org_id, status: $status}})
    {type_filter}
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.confidence as confidence,
        e.confirmed_at as confirmed_at,
        e.created_at as created_at,
        collect(ev{{.id, .source, .reference, .url}}) as evidence
    ORDER BY e.confirmed_at DESC, e.created_at DESC
    LIMIT $limit
    """

    params = {"org_id": org_id, "status": status, "limit": limit}
    if entity_type:
        params["entity_type"] = entity_type

    results = await GraphClient.run_query(query, params)

    # Filter nulls
    for r in results:
        r["evidence"] = [e for e in r.get("evidence", []) if e.get("id")]

    return {"entities": results, "total": len(results)}


@app.get("/entities/{entity_id}")
async def get_entity(entity_id: str, org_id: str = "default-org"):
    """Get entity details."""
    query = """
    MATCH (e:Entity {id: $entity_id, org_id: $org_id})
    OPTIONAL MATCH (e)-[:CITED_BY]->(ev:Evidence)
    OPTIONAL MATCH (e)-[r:SUPERSEDES]->(old:Entity)
    RETURN
        e.id as id,
        e.entity_type as entity_type,
        e.statement as statement,
        e.detail as detail,
        e.status as status,
        e.confidence as confidence,
        e.created_at as created_at,
        e.confirmed_at as confirmed_at,
        collect(DISTINCT ev{.id, .source, .reference, .url, .excerpt, .source_date}) as evidence,
        collect(DISTINCT old{.id, .statement, .status}) as superseded
    """

    results = await GraphClient.run_query(query, {"entity_id": entity_id, "org_id": org_id})

    if not results:
        return {"error": "Entity not found"}, 404

    entity = results[0]
    entity["evidence"] = [e for e in entity.get("evidence", []) if e.get("id")]
    entity["superseded"] = [s for s in entity.get("superseded", []) if s.get("id")]

    return entity


@app.get("/entities/{entity_id}/neighborhood")
async def get_entity_neighborhood(entity_id: str, org_id: str = "default-org"):
    """Get entity 1-hop neighborhood."""
    from core.queries import BrainQueries

    expansion = await BrainQueries.context_expansion(
        org_id=org_id,
        seed_ids=[entity_id],
        max_hops=1
    )

    return expansion


@app.post("/entities/{entity_id}/confirm")
async def confirm_entity(entity_id: str, org_id: str = "default-org", statement: Optional[str] = None):
    """Confirm a proposed entity."""
    from datetime import datetime

    # Update statement if provided
    if statement:
        query = """
        MATCH (e:Entity {id: $entity_id, org_id: $org_id})
        SET e.statement = $statement,
            e.status = 'confirmed',
            e.confirmed_at = datetime(),
            e.updated_at = datetime()
        RETURN e.id as id, e.status as status
        """
        params = {"entity_id": entity_id, "org_id": org_id, "statement": statement}
    else:
        query = """
        MATCH (e:Entity {id: $entity_id, org_id: $org_id})
        SET e.status = 'confirmed',
            e.confirmed_at = datetime(),
            e.updated_at = datetime()
        RETURN e.id as id, e.status as status
        """
        params = {"entity_id": entity_id, "org_id": org_id}

    result = await GraphClient.run_query(query, params)

    if not result:
        return {"error": "Entity not found"}, 404

    return result[0]


@app.post("/entities/{entity_id}/reject")
async def reject_entity(entity_id: str, org_id: str = "default-org"):
    """Reject a proposed entity."""
    query = """
    MATCH (e:Entity {id: $entity_id, org_id: $org_id})
    SET e.status = 'rejected',
        e.updated_at = datetime()
    RETURN e.id as id, e.status as status
    """

    result = await GraphClient.run_query(query, {"entity_id": entity_id, "org_id": org_id})

    if not result:
        return {"error": "Entity not found"}, 404

    return result[0]


@app.post("/entities/{entity_id}/merge")
async def merge_entity(entity_id: str, target_id: str, org_id: str = "default-org"):
    """Merge entity into another."""
    # Attach the source entity's evidence to the target, then delete source
    query = """
    MATCH (source:Entity {id: $entity_id, org_id: $org_id})
    MATCH (target:Entity {id: $target_id, org_id: $org_id})
    OPTIONAL MATCH (source)-[:CITED_BY]->(ev:Evidence)
    WITH source, target, collect(ev) as evidences
    FOREACH (ev IN evidences |
        CREATE (target)-[:CITED_BY]->(ev)
    )
    DETACH DELETE source
    RETURN target.id as target_id, count(evidences) as evidence_moved
    """

    result = await GraphClient.run_query(query, {
        "entity_id": entity_id,
        "target_id": target_id,
        "org_id": org_id
    })

    if not result:
        return {"error": "Entities not found"}, 404

    return {"merged": entity_id, "into": target_id, "evidence_moved": result[0]["evidence_moved"]}


# Webhook handlers
@app.post("/webhooks/github")
async def github_webhook():
    """GitHub webhook handler."""
    return {"status": "received"}


@app.post("/webhooks/slack")
async def slack_webhook():
    """Slack webhook handler."""
    return {"status": "received"}


@app.post("/webhooks/notion")
async def notion_webhook():
    """Notion webhook handler (placeholder - Notion doesn't have official webhooks yet)."""
    return {"status": "received"}


@app.post("/webhooks/google")
async def google_webhook():
    """Google Drive webhook handler."""
    return {"status": "received"}


FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# =============================================================================
# Notion connector endpoints
# =============================================================================

@app.get("/auth/notion")
async def notion_auth_start(org: str):
    """Start Notion OAuth flow."""
    from integrations.notion import get_oauth_url, NOTION_CLIENT_ID
    if not NOTION_CLIENT_ID:
        return {"error": "NOTION_CLIENT_ID not configured. Use token-based auth instead.", "use_token": True}
    url = get_oauth_url(state=org)
    return {"auth_url": url}


@app.post("/auth/notion/token")
async def notion_token_connect(org_id: str, token: str):
    """
    Connect Notion using an Internal Integration token.

    This is the easy setup path - no OAuth app needed.
    User creates an integration at notion.so/my-integrations and pastes the token.
    """
    from integrations.notion import validate_token
    import uuid
    from datetime import datetime

    # Validate the token
    user_info = await validate_token(token)

    # Get workspace/bot name
    bot_info = user_info.get("bot", {})
    workspace_name = bot_info.get("workspace_name", "Notion Workspace")

    # Register as a connected source
    if org_id not in connected_sources:
        connected_sources[org_id] = []

    # Check if Notion already connected
    existing = [s for s in connected_sources[org_id] if s["type"] == "notion"]
    if existing:
        # Update existing
        existing[0]["status"] = "connected"
        existing[0]["config"]["token"] = token
    else:
        # Add new
        source = {
            "id": str(uuid.uuid4()),
            "type": "notion",
            "name": workspace_name,
            "status": "connected",
            "lastSync": None,
            "itemCount": 0,
            "config": {"token": token},
            "created_at": datetime.utcnow().isoformat()
        }
        connected_sources[org_id].append(source)

    print(f"[Notion] Token validated for org {org_id}: {workspace_name}")

    return {
        "status": "connected",
        "bot": bot_info,
        "name": workspace_name,
        "message": "Token validated. Share pages with your integration to sync them."
    }


@app.get("/auth/notion/callback")
async def notion_auth_callback(code: str, state: str):
    """Handle Notion OAuth callback."""
    from integrations.notion import exchange_code
    try:
        tokens = await exchange_code(code)
        # TODO: Store tokens for org (state contains org_id)
        # For now, redirect back to frontend with success
        return RedirectResponse(
            url=f"{FRONTEND_URL}/onboard?source=notion&status=connected&org={state}"
        )
    except Exception as e:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/onboard?source=notion&status=error&org={state}&error={str(e)}"
        )


@app.get("/auth/slack")
async def slack_auth_start(org: str):
    """Start Slack OAuth flow."""
    from integrations.slack import get_oauth_url
    url = get_oauth_url(state=org)
    return {"auth_url": url}


@app.get("/auth/slack/callback")
async def slack_auth_callback(code: str, state: str):
    """Handle Slack OAuth callback."""
    from integrations.slack import exchange_code
    try:
        tokens = await exchange_code(code)
        # TODO: Store tokens for org
        return RedirectResponse(
            url=f"{FRONTEND_URL}/onboard?source=slack&status=connected&org={state}"
        )
    except Exception as e:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/onboard?source=slack&status=error&org={state}&error={str(e)}"
        )


@app.get("/auth/google")
async def google_auth_start(org: str):
    """Start Google OAuth flow."""
    from integrations.google import get_oauth_url
    url = get_oauth_url(state=org)
    return {"auth_url": url}


@app.get("/auth/google/callback")
async def google_auth_callback(code: str, state: str):
    """Handle Google OAuth callback."""
    from integrations.google import exchange_code
    try:
        tokens = await exchange_code(code)
        # TODO: Store tokens for org
        return RedirectResponse(
            url=f"{FRONTEND_URL}/onboard?source=google&status=connected&org={state}"
        )
    except Exception as e:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/onboard?source=google&status=error&org={state}&error={str(e)}"
        )


# =============================================================================
# Export / Import endpoints
# =============================================================================

@app.get("/export", response_class=PlainTextResponse)
async def export_brain_endpoint(
    org_id: str = Query("default-org", description="Organization ID to export"),
    include_embeddings: bool = Query(False, description="Include embedding vectors (large!)"),
    include_rejected: bool = Query(False, description="Include rejected entities")
):
    """
    Export the brain to portable YAML format.

    Returns a YAML file containing all entities, relationships, evidence,
    and workpacks for the organization.
    """
    yaml_content = await export_brain_yaml(
        org_id=org_id,
        include_embeddings=include_embeddings,
        include_rejected=include_rejected
    )

    return PlainTextResponse(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f"attachment; filename=komponist-brain-{org_id}.yaml"
        }
    )


@app.post("/import")
async def import_brain_endpoint(
    file: UploadFile = File(..., description="YAML export file to import"),
    org_id: Optional[str] = Query(None, description="Override org_id (uses export's if not provided)"),
    mode: str = Query("merge", description="Import mode: merge, replace, or skip_existing")
):
    """
    Import a brain export.

    Modes:
    - merge: Update existing entities, create new ones (default)
    - skip_existing: Only import entities that don't exist
    - replace: Clear and replace all data (dangerous!)
    """
    if mode not in ["merge", "skip_existing", "replace"]:
        return {"error": f"Invalid mode: {mode}. Use merge, skip_existing, or replace."}

    # Read uploaded file
    content = await file.read()
    yaml_content = content.decode("utf-8")

    # Import
    result = await import_brain_yaml(
        yaml_content=yaml_content,
        org_id=org_id,
        mode=mode
    )

    return result


# =============================================================================
# Sources management
# =============================================================================

@app.get("/sources")
async def list_sources(org_id: str = Query("default-org")):
    """List connected sources for an organization."""
    org_sources = connected_sources.get(org_id, [])
    return {"sources": org_sources, "total": len(org_sources)}


@app.post("/sources")
async def add_source(
    org_id: str = Query("default-org"),
    source_type: str = Query(..., description="Source type: notion, slack, google, local"),
    name: str = Query(..., description="Display name for the source"),
    config: dict = None
):
    """Register a connected source."""
    import uuid
    from datetime import datetime

    if org_id not in connected_sources:
        connected_sources[org_id] = []

    source = {
        "id": str(uuid.uuid4()),
        "type": source_type,
        "name": name,
        "status": "connected",
        "lastSync": None,
        "itemCount": 0,
        "config": config or {},
        "created_at": datetime.utcnow().isoformat()
    }

    connected_sources[org_id].append(source)
    return source


@app.delete("/sources/{source_id}")
async def remove_source(
    source_id: str,
    org_id: str = Query("default-org"),
    remove_data: bool = Query(False)
):
    """
    Remove a connected source.

    Args:
        source_id: ID of the source to remove
        org_id: Organization ID
        remove_data: If True, also delete all entities and evidence from this source
    """
    # Get source info before removing
    source = None
    if org_id in connected_sources:
        source = next((s for s in connected_sources[org_id] if s["id"] == source_id), None)

    entities_deleted = 0
    evidence_deleted = 0

    if remove_data and source:
        source_type = source.get("type", "").lower()

        try:
            # Step 1: Delete entities that came from this source
            # (delete entities that have CITED_BY relationship to evidence from this source)
            delete_entities_query = """
            MATCH (e:Entity {org_id: $org_id})-[:CITED_BY]->(ev:Evidence)
            WHERE toLower(ev.source) = $source_type
            DETACH DELETE e
            RETURN count(e) as deleted
            """
            result = await GraphClient.run_query(delete_entities_query, {
                "org_id": org_id,
                "source_type": source_type
            })
            if result:
                entities_deleted = result[0].get("deleted", 0)

            # Step 2: Delete evidence from this source
            delete_evidence_query = """
            MATCH (ev:Evidence {org_id: $org_id})
            WHERE toLower(ev.source) = $source_type
            DETACH DELETE ev
            RETURN count(ev) as deleted
            """
            result = await GraphClient.run_query(delete_evidence_query, {
                "org_id": org_id,
                "source_type": source_type
            })
            if result:
                evidence_deleted = result[0].get("deleted", 0)

            print(f"[Disconnect] Removed {entities_deleted} entities, {evidence_deleted} evidence from {source_type}")

        except Exception as e:
            print(f"[Disconnect] Error removing data: {e}")
            import traceback
            traceback.print_exc()

    # Remove from connected sources list
    if org_id in connected_sources:
        connected_sources[org_id] = [
            s for s in connected_sources[org_id] if s["id"] != source_id
        ]

    return {
        "status": "removed",
        "source_id": source_id,
        "data_removed": remove_data,
        "entities_deleted": entities_deleted,
        "evidence_deleted": evidence_deleted
    }


@app.post("/sources/{source_id}/sync")
async def sync_source(source_id: str, org_id: str = Query("default-org")):
    """
    Sync a connected source - fetch data and extract facts.
    """
    from datetime import datetime

    # Find the source
    org_sources = connected_sources.get(org_id, [])
    source = next((s for s in org_sources if s["id"] == source_id), None)

    if not source:
        return {"error": "Source not found"}, 404

    source["status"] = "syncing"

    try:
        if source["type"] == "notion":
            result = await sync_notion_source(org_id, source)
        elif source["type"] == "local":
            result = await sync_local_source(org_id, source)
        else:
            return {"error": f"Sync not implemented for {source['type']}"}

        source["status"] = "connected"
        source["lastSync"] = datetime.utcnow().isoformat()
        source["itemCount"] = result.get("items_processed", 0)

        return result

    except Exception as e:
        source["status"] = "error"
        return {"error": str(e)}


async def sync_notion_source(org_id: str, source: dict) -> dict:
    """Sync Notion pages and extract facts with parallel processing."""
    import asyncio
    from integrations.notion import search_notion, get_page_content, normalize_page

    token = source.get("config", {}).get("token")
    if not token:
        raise ValueError("No token found for Notion source")

    print(f"[Notion Sync] Starting sync for org {org_id}")

    # Collect all pages first
    all_pages = []
    start_cursor = None

    while True:
        result = await search_notion(
            access_token=token,
            filter_type="page",
            start_cursor=start_cursor
        )

        pages = result.get("results", [])
        all_pages.extend(pages)

        if not result.get("has_more"):
            break
        start_cursor = result.get("next_cursor")

    print(f"[Notion Sync] Found {len(all_pages)} pages total, processing in parallel...")

    # Get org settings
    settings = get_org_settings(org_id)
    auto_confirm = settings.get("auto_confirm", True)
    batch_size = settings.get("parallel_batch_size", 5)

    print(f"[Notion Sync] Auto-confirm: {auto_confirm}, Batch size: {batch_size}")

    # Process pages in parallel batches
    total_entities = 0
    total_relationships = 0
    pages_processed = 0

    async def process_page(page):
        """Process a single page."""
        try:
            page_id = page["id"]
            content = await get_page_content(token, page_id)

            if content and len(content.strip()) > 50:  # Skip near-empty pages
                source_item = normalize_page(page, content, org_id)
                print(f"[Notion Sync] Processing: {source_item.title[:40]}...")

                result = await run_extraction(source_item, auto_confirm=auto_confirm)
                return {
                    "success": True,
                    "entities": result.get("entities_created", 0),
                    "relationships": result.get("relationships_created", 0)
                }
            return {"success": True, "entities": 0, "relationships": 0}
        except Exception as e:
            print(f"[Notion Sync] Error: {e}")
            return {"success": False, "entities": 0, "relationships": 0}

    # Process in batches
    for i in range(0, len(all_pages), batch_size):
        batch = all_pages[i:i + batch_size]
        print(f"[Notion Sync] Processing batch {i // batch_size + 1}/{(len(all_pages) + batch_size - 1) // batch_size}")

        # Run batch in parallel
        results = await asyncio.gather(*[process_page(page) for page in batch])

        for r in results:
            if r["success"]:
                pages_processed += 1
                total_entities += r["entities"]
                total_relationships += r["relationships"]

    print(f"[Notion Sync] Complete: {pages_processed} pages, {total_entities} entities, {total_relationships} relationships")

    return {
        "status": "complete",
        "items_processed": pages_processed,
        "entities_created": total_entities,
        "relationships_created": total_relationships
    }


async def sync_local_source(org_id: str, source: dict) -> dict:
    """Sync local documents."""
    from integrations.local_docs import backfill_local_docs

    path = source.get("config", {}).get("path", "./docs")
    result = await backfill_local_docs(org_id=org_id, docs_path=path)
    return result


async def run_extraction(source_item, auto_confirm: bool = True) -> dict:
    """Run the graph extraction pipeline on a source item."""
    try:
        # Use the new graph extraction
        from pipelines.graph_extract import extract_and_persist
        result = await extract_and_persist(source_item, source_item.org_id, auto_confirm=auto_confirm)
        return {
            "entities_created": result.get("entities_created", 0),
            "relationships_created": result.get("relationships_created", 0)
        }
    except ImportError as e:
        print(f"[Extraction] Graph pipeline not available: {e}")
        # Fallback to simple extraction
        return await run_simple_extraction(source_item, auto_confirm=auto_confirm)
    except Exception as e:
        print(f"[Extraction] Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to simple extraction
        return await run_simple_extraction(source_item, auto_confirm=auto_confirm)


async def run_simple_extraction(source_item, auto_confirm: bool = True) -> dict:
    """Simple extraction fallback when full pipeline isn't available."""
    import uuid

    # Determine status based on auto_confirm setting
    entity_status = "confirmed" if auto_confirm else "proposed"

    # Create a basic fact entity from the page
    entity_id = str(uuid.uuid4())

    query = """
    MERGE (e:Entity {id: $id})
    SET e.org_id = $org_id,
        e.entity_type = 'Fact',
        e.statement = $statement,
        e.detail = $detail,
        e.status = $status,
        e.confidence = 0.5,
        e.created_at = datetime()
    """

    # Use title as statement, body as detail
    statement = source_item.title or "Untitled"
    detail = source_item.body[:1000] if source_item.body else ""

    await GraphClient.run_query(query, {
        "id": entity_id,
        "org_id": source_item.org_id,
        "statement": statement,
        "detail": detail,
        "status": entity_status
    })

    # Create evidence
    evidence_id = str(uuid.uuid4())
    evidence_query = """
    CREATE (ev:Evidence {
        id: $evidence_id,
        source: $source,
        reference: $reference,
        url: $url,
        excerpt: $excerpt
    })
    WITH ev
    MATCH (e:Entity {id: $entity_id})
    CREATE (e)-[:CITED_BY]->(ev)
    """

    await GraphClient.run_query(evidence_query, {
        "evidence_id": evidence_id,
        "entity_id": entity_id,
        "source": source_item.source.value if hasattr(source_item.source, 'value') else str(source_item.source),
        "reference": source_item.reference,
        "url": source_item.url or "",
        "excerpt": source_item.body[:500] if source_item.body else ""
    })

    return {"entities_created": 1}


# =============================================================================
# Local Documents connector
# =============================================================================

@app.get("/connectors/local-docs/status")
async def local_docs_status():
    """Get local documents connector status."""
    from integrations.local_docs import get_local_docs_status
    return get_local_docs_status()


@app.post("/connectors/local-docs/scan")
async def local_docs_scan(
    org_id: str = Query("default-org"),
    path: Optional[str] = Query(None, description="Override docs path")
):
    """Trigger a scan of local documents."""
    from integrations.local_docs import backfill_local_docs
    result = await backfill_local_docs(org_id=org_id, docs_path=path)
    return result


# =============================================================================
# Graph API endpoints
# =============================================================================

@app.get("/graph")
async def get_graph(
    org_id: str = Query("default-org"),
    limit: int = Query(200, description="Max nodes to return"),
    entity_types: Optional[str] = Query(None, description="Comma-separated entity types to filter")
):
    """
    Get the knowledge graph for visualization.

    Returns nodes (entities) and edges (relationships).
    """
    type_filter = ""
    if entity_types:
        types = [t.strip() for t in entity_types.split(",")]
        type_filter = f"AND e.entity_type IN {types}"

    # Get nodes
    nodes_query = f"""
    MATCH (e:Entity {{org_id: $org_id}})
    WHERE e.status IN ['proposed', 'confirmed']
    {type_filter}
    RETURN
        e.id as id,
        e.name as name,
        e.entity_type as type,
        e.detail as description,
        e.status as status,
        e.confidence as confidence
    ORDER BY e.created_at DESC
    LIMIT $limit
    """

    nodes = await GraphClient.run_query(nodes_query, {
        "org_id": org_id,
        "limit": limit
    })

    # Get all node IDs for edge filtering
    node_ids = [n["id"] for n in nodes]

    if not node_ids:
        return {"nodes": [], "edges": []}

    # Get edges between these nodes
    edges_query = """
    MATCH (s:Entity {org_id: $org_id})-[r]->(t:Entity {org_id: $org_id})
    WHERE s.id IN $node_ids AND t.id IN $node_ids
    AND NOT type(r) = 'CITED_BY'
    RETURN
        s.id as source,
        t.id as target,
        type(r) as type,
        r.description as description
    """

    edges = await GraphClient.run_query(edges_query, {
        "org_id": org_id,
        "node_ids": node_ids
    })

    return {
        "nodes": nodes,
        "edges": edges
    }


@app.get("/graph/stats")
async def get_graph_stats(org_id: str = Query("default-org")):
    """Get statistics about the knowledge graph."""

    # Count nodes by type
    type_query = """
    MATCH (e:Entity {org_id: $org_id})
    WHERE e.status IN ['proposed', 'confirmed']
    RETURN e.entity_type as type, count(e) as count
    ORDER BY count DESC
    """

    type_counts = await GraphClient.run_query(type_query, {"org_id": org_id})

    # Count relationships by type
    rel_query = """
    MATCH (s:Entity {org_id: $org_id})-[r]->(t:Entity {org_id: $org_id})
    WHERE NOT type(r) = 'CITED_BY'
    RETURN type(r) as type, count(r) as count
    ORDER BY count DESC
    """

    rel_counts = await GraphClient.run_query(rel_query, {"org_id": org_id})

    # Total counts
    totals_query = """
    MATCH (e:Entity {org_id: $org_id})
    WHERE e.status IN ['proposed', 'confirmed']
    WITH count(e) as node_count
    MATCH (s:Entity {org_id: $org_id})-[r]->(t:Entity {org_id: $org_id})
    WHERE NOT type(r) = 'CITED_BY'
    RETURN node_count, count(r) as edge_count
    """

    totals = await GraphClient.run_query(totals_query, {"org_id": org_id})

    node_count = totals[0]["node_count"] if totals else 0
    edge_count = totals[0]["edge_count"] if totals else 0

    return {
        "total_nodes": node_count,
        "total_edges": edge_count,
        "nodes_by_type": {t["type"]: t["count"] for t in type_counts},
        "edges_by_type": {r["type"]: r["count"] for r in rel_counts}
    }


@app.get("/graph/neighbors/{entity_id}")
async def get_entity_neighbors(
    entity_id: str,
    org_id: str = Query("default-org"),
    depth: int = Query(1, description="How many hops to traverse")
):
    """Get the neighborhood of a specific entity."""

    # Get the entity and its neighbors up to N hops
    query = """
    MATCH path = (center:Entity {id: $entity_id, org_id: $org_id})-[*1..$depth]-(neighbor:Entity)
    WHERE neighbor.org_id = $org_id
    WITH center, neighbor, relationships(path) as rels
    UNWIND rels as r
    WITH center, neighbor, r, startNode(r) as source, endNode(r) as target
    WHERE NOT type(r) = 'CITED_BY'
    RETURN DISTINCT
        neighbor.id as id,
        neighbor.name as name,
        neighbor.entity_type as type,
        neighbor.detail as description,
        source.id as edge_source,
        target.id as edge_target,
        type(r) as edge_type
    """

    results = await GraphClient.run_query(query, {
        "entity_id": entity_id,
        "org_id": org_id,
        "depth": depth
    })

    # Build nodes and edges
    nodes = {}
    edges = []

    # Add center node
    center_query = """
    MATCH (e:Entity {id: $entity_id, org_id: $org_id})
    RETURN e.id as id, e.name as name, e.entity_type as type, e.detail as description
    """
    center = await GraphClient.run_query(center_query, {
        "entity_id": entity_id,
        "org_id": org_id
    })

    if center:
        nodes[entity_id] = {
            "id": center[0]["id"],
            "name": center[0]["name"],
            "type": center[0]["type"],
            "description": center[0]["description"],
            "isCenter": True
        }

    for row in results:
        # Add neighbor node
        if row["id"] not in nodes:
            nodes[row["id"]] = {
                "id": row["id"],
                "name": row["name"],
                "type": row["type"],
                "description": row["description"],
                "isCenter": False
            }

        # Add edge
        edge = {
            "source": row["edge_source"],
            "target": row["edge_target"],
            "type": row["edge_type"]
        }
        if edge not in edges:
            edges.append(edge)

    return {
        "center": entity_id,
        "nodes": list(nodes.values()),
        "edges": edges
    }


# =============================================================================
# Chat API endpoint
# =============================================================================

from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json
from core.llm import get_llm
from core.embeddings import embed
from core.queries import BrainQueries


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    sources: Optional[List[Dict[str, Any]]] = None


class ChatRequest(BaseModel):
    message: str
    org_id: str = "default-org"
    conversation_history: List[ChatMessage] = []
    stream: bool = True


class ChatResponse(BaseModel):
    response: str
    sources: List[Dict[str, Any]]
    conversation_id: Optional[str] = None


@app.post("/chat")
async def chat_with_brain(request: ChatRequest):
    """
    Chat interface for querying the knowledge graph.
    Uses RAG: embed query → hybrid search → LLM synthesis.
    """
    from fastapi import HTTPException

    try:
        # 1. Try to embed user query for semantic search
        query_embedding = None
        try:
            query_embedding = await embed(request.message)
        except Exception as e:
            print(f"Embedding failed: {e}")

        # 2. Hybrid search knowledge graph (text-only fallback if no embeddings)
        search_results = []
        try:
            search_results = await BrainQueries.hybrid_search(
                org_id=request.org_id,
                query_text=request.message,
                query_embedding=query_embedding,
                k=8,  # Top 8 results
                status="confirmed"
            )
        except Exception as search_error:
            # Fallback: simple text match without indexes
            print(f"Search error, using simple fallback: {search_error}")
            try:
                from core.graph import GraphClient
                fallback_query = """
                MATCH (n:Entity {org_id: $org_id, status: 'confirmed'})
                WHERE toLower(n.statement) CONTAINS toLower($query)
                   OR toLower(n.name) CONTAINS toLower($query)
                   OR toLower(n.detail) CONTAINS toLower($query)
                RETURN
                    n.id as id,
                    n.entity_type as entity_type,
                    n.statement as statement,
                    n.detail as detail,
                    n.status as status,
                    n.confidence as confidence,
                    1.0 as score
                LIMIT $k
                """
                results = await GraphClient.run_query(
                    fallback_query,
                    {"org_id": request.org_id, "query": request.message, "k": 8}
                )
                search_results = results if results else []
            except Exception as fallback_error:
                print(f"Fallback search also failed: {fallback_error}")
                search_results = []

        # 3. Build context from results
        if not search_results:
            context = "No relevant information found in the knowledge graph."
            sources = []
        else:
            context_parts = []
            for idx, result in enumerate(search_results, 1):
                context_parts.append(
                    f"{idx}. [{result['entity_type']}] {result['statement']}\n"
                    f"   Detail: {result.get('detail', 'N/A')}\n"
                    f"   Confidence: {result.get('confidence', 'N/A')}"
                )
            context = "\n\n".join(context_parts)
            sources = [
                {
                    "id": r["id"],
                    "type": r["entity_type"],
                    "statement": r["statement"],
                    "score": r.get("score", 0)
                }
                for r in search_results
            ]

        # 4. Build conversation context
        conversation_context = ""
        if request.conversation_history:
            history_parts = []
            for msg in request.conversation_history[-3:]:  # Last 3 turns
                history_parts.append(f"{msg.role}: {msg.content}")
            conversation_context = "\n".join(history_parts) + "\n\n"

        # 5. Call LLM with RAG context
        system_prompt = """You are Komponist, an AI assistant that helps users query their company's knowledge graph.

You have access to confirmed facts, decisions, goals, and relationships from the knowledge graph.

When answering:
- Base your answers on the provided context from the knowledge graph
- Cite specific entities when relevant (e.g., "According to [Decision] Use Neo4j...")
- If the context is empty or doesn't contain the answer, explain that the knowledge graph is empty or doesn't have that information yet
- Suggest that the user should add sources to populate the knowledge graph (via the Onboard page)
- Be concise but complete
- Use the user's language and tone

Context from knowledge graph:
{context}"""

        user_prompt = f"{conversation_context}User question: {request.message}"

        llm = get_llm()

        if request.stream:
            # Streaming response
            async def generate_stream():
                try:
                    async for chunk in llm.stream(
                        prompt=user_prompt,
                        system=system_prompt.format(context=context),
                        max_tokens=2048
                    ):
                        yield {
                            "event": "message",
                            "data": json.dumps({"content": chunk})
                        }
                    # Send sources at the end
                    yield {
                        "event": "sources",
                        "data": json.dumps({"sources": sources})
                    }
                    yield {"event": "done", "data": ""}
                except Exception as e:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": str(e)})
                    }

            return EventSourceResponse(generate_stream())
        else:
            # Non-streaming response
            response = await llm.call(
                prompt=user_prompt,
                system=system_prompt.format(context=context),
                max_tokens=2048
            )

            return ChatResponse(
                response=response["text"],
                sources=sources,
                conversation_id=None  # Can add conversation persistence later
            )

    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Settings API endpoints
# =============================================================================

@app.get("/settings")
async def get_settings(org_id: str = Query("default-org")):
    """Get settings for an organization."""
    return get_org_settings(org_id)


@app.put("/settings")
async def update_settings(
    org_id: str = Query("default-org"),
    auto_confirm: Optional[bool] = Query(None, description="Auto-confirm extracted entities"),
    parallel_batch_size: Optional[int] = Query(None, description="Parallel processing batch size")
):
    """Update settings for an organization."""
    if org_id not in org_settings:
        org_settings[org_id] = {}

    if auto_confirm is not None:
        org_settings[org_id]["auto_confirm"] = auto_confirm

    if parallel_batch_size is not None:
        org_settings[org_id]["parallel_batch_size"] = max(1, min(10, parallel_batch_size))

    return get_org_settings(org_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
