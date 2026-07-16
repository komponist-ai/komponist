"""
Linear integration.

OAuth, webhooks, Project upsert, issue extraction.
"""

import os
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx
from fastapi import Request, HTTPException

import sys
sys.path.append("../../../packages")

from core.models import SourceItem, SourceType
from core.graph import GraphClient
from database import async_session, EventRaw


LINEAR_WEBHOOK_SECRET = os.getenv("LINEAR_WEBHOOK_SECRET", "")
LINEAR_API_KEY = os.getenv("LINEAR_API_KEY", "")
LINEAR_API_URL = "https://api.linear.app/graphql"


def verify_linear_signature(body: bytes, signature: str) -> bool:
    """
    Verify Linear webhook signature.

    Args:
        body: Raw request body
        signature: Linear-Signature header

    Returns:
        True if signature is valid
    """
    if not LINEAR_WEBHOOK_SECRET:
        return True  # Dev mode

    expected_signature = hmac.new(
        LINEAR_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


async def handle_linear_webhook(request: Request, org_id: str) -> Dict[str, str]:
    """
    Handle Linear webhook event.

    Args:
        request: FastAPI request
        org_id: Organization ID

    Returns:
        Status dict
    """
    signature = request.headers.get("Linear-Signature", "")
    body = await request.body()

    if not verify_linear_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)

    event_type = payload.get("type", "unknown")
    action = payload.get("action", "")

    # Store raw event
    async with async_session() as session:
        event = EventRaw(
            org_id=org_id,
            source="linear",
            event_type=f"{event_type}.{action}",
            payload=payload
        )
        session.add(event)
        await session.commit()

    return {"status": "received", "event_type": event_type}


async def upsert_project(project_data: Dict[str, Any], org_id: str):
    """
    Upsert Linear project as confirmed Project entity.

    Projects are ground truth - auto-confirmed, not reviewed.

    Args:
        project_data: Linear project data
        org_id: Organization ID
    """
    project_id = project_data.get("id")
    name = project_data.get("name", "")
    description = project_data.get("description", "")
    url = project_data.get("url", "")
    state = project_data.get("state", "")

    # Create/update Project node
    query = """
    MERGE (p:Entity:Project {org_id: $org_id, external_ref: $linear_id})
    SET p.id = coalesce(p.id, $entity_id),
        p.entity_type = 'Project',
        p.statement = $name,
        p.detail = $description,
        p.status = 'confirmed',
        p.confidence = 'high',
        p.updated_at = datetime(),
        p.confirmed_at = datetime()
    WITH p
    MERGE (e:Evidence {id: $evidence_id})
    SET e.org_id = $org_id,
        e.source = 'linear',
        e.reference = $linear_id,
        e.url = $url,
        e.excerpt = $name,
        e.source_date = datetime()
    MERGE (p)-[:CITED_BY]->(e)
    RETURN p.id as id
    """

    from uuid import uuid4

    await GraphClient.run_query(query, {
        "org_id": org_id,
        "linear_id": project_id,
        "entity_id": str(uuid4()),
        "evidence_id": str(uuid4()),
        "name": name,
        "description": description,
        "url": url
    })

    print(f"[Linear] Upserted project: {name}")


def normalize_issue(issue_data: Dict[str, Any], org_id: str) -> SourceItem:
    """
    Normalize Linear issue to SourceItem.

    Args:
        issue_data: Linear issue data
        org_id: Organization ID

    Returns:
        SourceItem for extraction
    """
    issue_id = issue_data.get("id")
    title = issue_data.get("title", "")
    description = issue_data.get("description", "")
    url = issue_data.get("url", "")
    identifier = issue_data.get("identifier", issue_id)  # e.g., "ENG-88"

    # Include comments if available
    comments = issue_data.get("comments", [])
    if comments:
        comment_text = "\n\n---\n\nComments:\n\n"
        for comment in comments:
            author = comment.get("user", {}).get("name", "unknown")
            body = comment.get("body", "")
            comment_text += f"{author}: {body}\n\n"
        description += comment_text

    created_at = issue_data.get("createdAt")
    if created_at:
        source_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    else:
        source_date = datetime.utcnow()

    return SourceItem(
        org_id=org_id,
        source=SourceType.LINEAR,
        kind="issue",
        title=title,
        body=description,
        author=issue_data.get("creator", {}).get("name"),
        url=url,
        reference=identifier,
        source_date=source_date
    )


async def process_linear_events():
    """
    Worker: process unprocessed Linear events.

    - Project events -> upsert Project nodes
    - Issue events -> extract as SourceItems
    """
    async with async_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(EventRaw)
            .where(EventRaw.source == "linear")
            .where(EventRaw.processed_at.is_(None))
            .limit(100)
        )
        events = result.scalars().all()

        for event in events:
            try:
                payload = event.payload
                event_type = event.event_type
                action = payload.get("action", "")
                data = payload.get("data", {})

                if "Project" in event_type:
                    # Upsert project
                    await upsert_project(data, event.org_id)

                elif "Issue" in event_type and action in ["create", "update"]:
                    # Extract issue
                    source_item = normalize_issue(data, event.org_id)
                    # TODO: Route to extraction pipeline
                    print(f"[Linear] Normalized issue: {source_item.title}")

                event.processed_at = datetime.utcnow()
                await session.commit()

            except Exception as e:
                event.error = str(e)
                event.processed_at = datetime.utcnow()
                await session.commit()
                print(f"[Linear] Error processing event {event.id}: {e}")


async def backfill_linear(org_id: str):
    """
    Backfill Linear data via GraphQL API.

    Fetches:
    - All active projects
    - Issues created in last 90 days

    Args:
        org_id: Organization ID
    """
    if not LINEAR_API_KEY:
        raise ValueError("LINEAR_API_KEY not set")

    headers = {
        "Authorization": LINEAR_API_KEY,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        # Fetch projects
        print("Fetching Linear projects...")

        projects_query = """
        query {
          projects {
            nodes {
              id
              name
              description
              url
              state
            }
          }
        }
        """

        response = await client.post(
            LINEAR_API_URL,
            json={"query": projects_query}
        )

        if response.status_code != 200:
            print(f"Error fetching projects: {response.status_code}")
            return

        data = response.json()
        projects = data.get("data", {}).get("projects", {}).get("nodes", [])

        print(f"Found {len(projects)} projects")

        for project in projects:
            await upsert_project(project, org_id)

        # Fetch issues (last 90 days)
        print("Fetching Linear issues...")

        cutoff_date = (datetime.utcnow() - timedelta(days=90)).isoformat()

        issues_query = """
        query($after: String) {
          issues(
            filter: { createdAt: { gte: "%s" } }
            first: 50
            after: $after
          ) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              identifier
              title
              description
              url
              createdAt
              creator {
                name
              }
              comments {
                nodes {
                  body
                  user {
                    name
                  }
                }
              }
            }
          }
        }
        """ % cutoff_date

        cursor = None
        issues_count = 0

        while True:
            response = await client.post(
                LINEAR_API_URL,
                json={"query": issues_query, "variables": {"after": cursor}}
            )

            if response.status_code != 200:
                break

            data = response.json()
            issues_data = data.get("data", {}).get("issues", {})
            issues = issues_data.get("nodes", [])
            page_info = issues_data.get("pageInfo", {})

            issues_count += len(issues)

            for issue in issues:
                source_item = normalize_issue(issue, org_id)
                # TODO: Route to extraction pipeline
                print(f"  Issue: {source_item.reference} - {source_item.title[:50]}")

            if not page_info.get("hasNextPage"):
                break

            cursor = page_info.get("endCursor")

        print(f"Processed {issues_count} issues")

    print(f"Linear backfill complete for org: {org_id}")


if __name__ == "__main__":
    import asyncio

    async def main():
        GraphClient.initialize()
        await backfill_linear(org_id="test-org")
        await GraphClient.close()

    asyncio.run(main())
