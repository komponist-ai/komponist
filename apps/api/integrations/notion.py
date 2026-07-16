"""
Notion integration.

OAuth, webhooks, page/database extraction.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx
from fastapi import Request, HTTPException

import sys
sys.path.append("../../../packages")

from core.models import SourceItem, SourceType
from core.graph import GraphClient
from database import async_session, EventRaw, SyncState


NOTION_CLIENT_ID = os.getenv("NOTION_CLIENT_ID", "")
NOTION_CLIENT_SECRET = os.getenv("NOTION_CLIENT_SECRET", "")
NOTION_REDIRECT_URI = os.getenv("NOTION_REDIRECT_URI", "http://localhost:8000/auth/notion/callback")
NOTION_API_VERSION = "2022-06-28"
NOTION_API_URL = "https://api.notion.com/v1"


async def validate_token(token: str) -> Dict[str, Any]:
    """
    Validate a Notion Internal Integration token.

    Args:
        token: The integration token (starts with 'secret_' or 'ntn_')

    Returns:
        User/bot info if valid

    Raises:
        HTTPException if invalid
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
    }

    async with httpx.AsyncClient(headers=headers) as client:
        # Test the token by fetching user info
        response = await client.get(f"{NOTION_API_URL}/users/me")

        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid Notion token")

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to validate Notion token")

        return response.json()


def get_oauth_url(state: str) -> str:
    """
    Generate Notion OAuth URL.

    Args:
        state: State parameter for CSRF protection (should include org_id)

    Returns:
        OAuth authorization URL
    """
    params = {
        "client_id": NOTION_CLIENT_ID,
        "redirect_uri": NOTION_REDIRECT_URI,
        "response_type": "code",
        "owner": "user",  # or "workspace"
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://api.notion.com/v1/oauth/authorize?{query}"


async def exchange_code(code: str) -> Dict[str, Any]:
    """
    Exchange authorization code for access token.

    Args:
        code: Authorization code from OAuth callback

    Returns:
        Token response with access_token, workspace info, etc.
    """
    import base64

    # Notion uses Basic auth with client_id:client_secret
    credentials = base64.b64encode(
        f"{NOTION_CLIENT_ID}:{NOTION_CLIENT_SECRET}".encode()
    ).decode()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{NOTION_API_URL}/oauth/token",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            },
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": NOTION_REDIRECT_URI,
            }
        )

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code")

        return response.json()


def extract_text_from_blocks(blocks: List[Dict[str, Any]]) -> str:
    """
    Extract plain text from Notion blocks.

    Args:
        blocks: List of Notion block objects

    Returns:
        Concatenated plain text
    """
    text_parts = []

    for block in blocks:
        block_type = block.get("type")
        block_data = block.get(block_type, {})

        # Handle different block types
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3",
                          "bulleted_list_item", "numbered_list_item", "toggle",
                          "quote", "callout"]:
            rich_text = block_data.get("rich_text", [])
            text = "".join(rt.get("plain_text", "") for rt in rich_text)
            if text:
                text_parts.append(text)

        elif block_type == "code":
            rich_text = block_data.get("rich_text", [])
            code = "".join(rt.get("plain_text", "") for rt in rich_text)
            language = block_data.get("language", "")
            if code:
                text_parts.append(f"```{language}\n{code}\n```")

        elif block_type == "to_do":
            rich_text = block_data.get("rich_text", [])
            text = "".join(rt.get("plain_text", "") for rt in rich_text)
            checked = block_data.get("checked", False)
            checkbox = "[x]" if checked else "[ ]"
            if text:
                text_parts.append(f"{checkbox} {text}")

        elif block_type == "divider":
            text_parts.append("---")

    return "\n\n".join(text_parts)


async def get_page_content(access_token: str, page_id: str) -> Optional[str]:
    """
    Fetch and extract text content from a Notion page.

    Args:
        access_token: Valid OAuth access token
        page_id: Notion page ID

    Returns:
        Extracted text content or None
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": NOTION_API_VERSION,
    }

    all_blocks = []
    start_cursor = None

    async with httpx.AsyncClient(headers=headers) as client:
        # Paginate through all blocks
        while True:
            params = {"page_size": 100}
            if start_cursor:
                params["start_cursor"] = start_cursor

            response = await client.get(
                f"{NOTION_API_URL}/blocks/{page_id}/children",
                params=params
            )

            if response.status_code != 200:
                return None

            data = response.json()
            all_blocks.extend(data.get("results", []))

            if not data.get("has_more"):
                break

            start_cursor = data.get("next_cursor")

    return extract_text_from_blocks(all_blocks)


async def get_database_items(access_token: str, database_id: str) -> List[Dict[str, Any]]:
    """
    Fetch all items from a Notion database.

    Args:
        access_token: Valid OAuth access token
        database_id: Notion database ID

    Returns:
        List of database items
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": NOTION_API_VERSION,
    }

    all_items = []
    start_cursor = None

    async with httpx.AsyncClient(headers=headers) as client:
        while True:
            body = {"page_size": 100}
            if start_cursor:
                body["start_cursor"] = start_cursor

            response = await client.post(
                f"{NOTION_API_URL}/databases/{database_id}/query",
                json=body
            )

            if response.status_code != 200:
                break

            data = response.json()
            all_items.extend(data.get("results", []))

            if not data.get("has_more"):
                break

            start_cursor = data.get("next_cursor")

    return all_items


def normalize_page(page_data: Dict[str, Any], content: str, org_id: str) -> SourceItem:
    """
    Normalize Notion page to SourceItem.

    Args:
        page_data: Notion page object
        content: Extracted text content
        org_id: Organization ID

    Returns:
        SourceItem for extraction
    """
    page_id = page_data.get("id", "").replace("-", "")

    # Extract title from properties
    properties = page_data.get("properties", {})
    title = ""

    # Title can be in different property names
    for prop_name in ["Name", "Title", "title", "name"]:
        if prop_name in properties:
            title_prop = properties[prop_name]
            if title_prop.get("type") == "title":
                rich_text = title_prop.get("title", [])
                title = "".join(rt.get("plain_text", "") for rt in rich_text)
                break

    if not title:
        title = "Untitled"

    # Get URL
    url = page_data.get("url", f"https://notion.so/{page_id}")

    # Get created time
    created_time = page_data.get("created_time")
    if created_time:
        source_date = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
    else:
        source_date = datetime.utcnow()

    # Get creator
    created_by = page_data.get("created_by", {})
    author = created_by.get("name") or created_by.get("id")

    return SourceItem(
        org_id=org_id,
        source=SourceType.NOTION,
        kind="page",
        title=title,
        body=content,
        author=author,
        url=url,
        reference=f"notion:{page_id}",
        source_date=source_date
    )


async def search_notion(
    access_token: str,
    query: Optional[str] = None,
    filter_type: Optional[str] = None,
    start_cursor: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search Notion workspace.

    Args:
        access_token: Valid OAuth access token
        query: Optional search query
        filter_type: "page" or "database"
        start_cursor: Pagination cursor

    Returns:
        Search results
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": NOTION_API_VERSION,
    }

    body: Dict[str, Any] = {"page_size": 100}

    if query:
        body["query"] = query

    if filter_type:
        body["filter"] = {"property": "object", "value": filter_type}

    if start_cursor:
        body["start_cursor"] = start_cursor

    async with httpx.AsyncClient(headers=headers) as client:
        response = await client.post(
            f"{NOTION_API_URL}/search",
            json=body
        )

        if response.status_code != 200:
            return {"results": [], "has_more": False}

        return response.json()


async def backfill_notion(org_id: str, access_token: str, days: int = 90):
    """
    Backfill Notion pages and databases.

    Fetches all accessible pages and extracts content.

    Args:
        org_id: Organization ID
        access_token: OAuth access token
        days: Days to backfill (not strictly enforced by Notion search)
    """
    print(f"Starting Notion backfill for org: {org_id}")

    start_cursor = None
    pages_count = 0

    while True:
        # Search for all pages
        result = await search_notion(
            access_token=access_token,
            filter_type="page",
            start_cursor=start_cursor
        )

        pages = result.get("results", [])
        pages_count += len(pages)

        for page in pages:
            try:
                # Only process pages modified within timeframe
                last_edited = page.get("last_edited_time")
                if last_edited:
                    edited_dt = datetime.fromisoformat(last_edited.replace("Z", "+00:00"))
                    if edited_dt < datetime.utcnow() - timedelta(days=days):
                        continue

                # Extract content
                page_id = page["id"]
                content = await get_page_content(access_token, page_id)

                if content:
                    source_item = normalize_page(page, content, org_id)
                    # TODO: Route to extraction pipeline
                    print(f"  Page: {source_item.title[:60]}")

            except Exception as e:
                print(f"  Error processing page: {e}")

        if not result.get("has_more"):
            break

        start_cursor = result.get("next_cursor")

    # Also process databases
    start_cursor = None
    while True:
        result = await search_notion(
            access_token=access_token,
            filter_type="database",
            start_cursor=start_cursor
        )

        databases = result.get("results", [])

        for db in databases:
            try:
                db_id = db["id"]
                items = await get_database_items(access_token, db_id)
                print(f"  Database: {db.get('title', [{}])[0].get('plain_text', 'Untitled')} ({len(items)} items)")

                # Process each database item as a page
                for item in items:
                    try:
                        content = await get_page_content(access_token, item["id"])
                        if content:
                            source_item = normalize_page(item, content, org_id)
                            # TODO: Route to extraction pipeline

                    except Exception as e:
                        print(f"    Error processing item: {e}")

            except Exception as e:
                print(f"  Error processing database: {e}")

        if not result.get("has_more"):
            break

        start_cursor = result.get("next_cursor")

    print(f"Processed {pages_count} Notion pages")
    print(f"Notion backfill complete for org: {org_id}")


async def handle_notion_webhook(request: Request, org_id: str) -> Dict[str, str]:
    """
    Handle Notion webhook event.

    Note: As of 2024, Notion doesn't have official webhooks.
    This is a placeholder for when they add webhook support,
    or for handling updates via polling/change detection.

    Args:
        request: FastAPI request
        org_id: Organization ID

    Returns:
        Status dict
    """
    body = await request.body()
    payload = json.loads(body) if body else {}

    # Store event for processing
    async with async_session() as session:
        event = EventRaw(
            org_id=org_id,
            source="notion",
            event_type=payload.get("type", "unknown"),
            payload=payload
        )
        session.add(event)
        await session.commit()

    return {"status": "received"}


async def process_notion_events():
    """
    Worker: process unprocessed Notion events.

    Since Notion lacks webhooks, this mainly handles
    manually triggered syncs or polling results.
    """
    async with async_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(EventRaw)
            .where(EventRaw.source == "notion")
            .where(EventRaw.processed_at.is_(None))
            .limit(100)
        )
        events = result.scalars().all()

        for event in events:
            try:
                payload = event.payload
                event_type = event.event_type

                # Handle different event types
                if event_type == "page.updated":
                    # Fetch and re-extract page
                    # TODO: Get access token from org settings
                    print(f"[Notion] Page update for org {event.org_id}")

                event.processed_at = datetime.utcnow()
                await session.commit()

            except Exception as e:
                event.error = str(e)
                event.processed_at = datetime.utcnow()
                await session.commit()
                print(f"[Notion] Error processing event {event.id}: {e}")


if __name__ == "__main__":
    import asyncio

    async def main():
        # Test OAuth URL generation
        url = get_oauth_url("test-org")
        print(f"OAuth URL: {url}")

    asyncio.run(main())
