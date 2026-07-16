"""
Google Workspace integration.

OAuth, Drive API, Docs/Sheets extraction.
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


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

# Scopes needed for Drive access
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


def get_oauth_url(state: str) -> str:
    """
    Generate Google OAuth URL.

    Args:
        state: State parameter for CSRF protection (should include org_id)

    Returns:
        OAuth authorization URL
    """
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


async def exchange_code(code: str) -> Dict[str, Any]:
    """
    Exchange authorization code for tokens.

    Args:
        code: Authorization code from OAuth callback

    Returns:
        Token response with access_token, refresh_token, etc.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": GOOGLE_REDIRECT_URI,
            }
        )

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code")

        return response.json()


async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    """
    Refresh an expired access token.

    Args:
        refresh_token: Refresh token from initial OAuth

    Returns:
        New token response
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        )

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to refresh token")

        return response.json()


def normalize_drive_file(file_data: Dict[str, Any], content: str, org_id: str) -> SourceItem:
    """
    Normalize Google Drive file to SourceItem.

    Args:
        file_data: Drive file metadata
        content: Extracted text content
        org_id: Organization ID

    Returns:
        SourceItem for extraction
    """
    file_id = file_data.get("id")
    name = file_data.get("name", "")
    mime_type = file_data.get("mimeType", "")
    web_link = file_data.get("webViewLink", "")

    # Determine kind based on mime type
    if "document" in mime_type:
        kind = "doc"
    elif "spreadsheet" in mime_type:
        kind = "spreadsheet"
    elif "presentation" in mime_type:
        kind = "presentation"
    else:
        kind = "file"

    created_time = file_data.get("createdTime")
    if created_time:
        source_date = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
    else:
        source_date = datetime.utcnow()

    # Get owner info
    owners = file_data.get("owners", [])
    author = owners[0].get("displayName") if owners else None

    return SourceItem(
        org_id=org_id,
        source=SourceType.GOOGLE,
        kind=kind,
        title=name,
        body=content,
        author=author,
        url=web_link,
        reference=f"gdrive:{file_id}",
        source_date=source_date
    )


async def get_file_content(access_token: str, file_id: str, mime_type: str) -> Optional[str]:
    """
    Extract text content from a Google Drive file.

    Args:
        access_token: Valid OAuth access token
        file_id: Drive file ID
        mime_type: File MIME type

    Returns:
        Extracted text content or None
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(headers=headers) as client:
        # Google Docs - export as plain text
        if "document" in mime_type:
            response = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                params={"mimeType": "text/plain"}
            )
            if response.status_code == 200:
                return response.text

        # Google Sheets - export as CSV (first sheet only for now)
        elif "spreadsheet" in mime_type:
            response = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                params={"mimeType": "text/csv"}
            )
            if response.status_code == 200:
                return response.text

        # Google Slides - export as plain text
        elif "presentation" in mime_type:
            response = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                params={"mimeType": "text/plain"}
            )
            if response.status_code == 200:
                return response.text

        return None


async def list_drive_files(
    access_token: str,
    folder_id: Optional[str] = None,
    modified_after: Optional[datetime] = None,
    page_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    List files in Google Drive.

    Args:
        access_token: Valid OAuth access token
        folder_id: Optional folder ID to filter
        modified_after: Only include files modified after this time
        page_token: Pagination token

    Returns:
        Dict with files and nextPageToken
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    # Build query
    query_parts = [
        "mimeType contains 'google-apps'",  # Only Google-native files
        "trashed = false",
    ]

    if folder_id:
        query_parts.append(f"'{folder_id}' in parents")

    if modified_after:
        query_parts.append(f"modifiedTime > '{modified_after.isoformat()}Z'")

    query = " and ".join(query_parts)

    params = {
        "q": query,
        "fields": "nextPageToken, files(id, name, mimeType, webViewLink, createdTime, modifiedTime, owners)",
        "pageSize": 100,
        "orderBy": "modifiedTime desc",
    }

    if page_token:
        params["pageToken"] = page_token

    async with httpx.AsyncClient(headers=headers) as client:
        response = await client.get(
            "https://www.googleapis.com/drive/v3/files",
            params=params
        )

        if response.status_code != 200:
            print(f"Error listing files: {response.status_code}")
            return {"files": [], "nextPageToken": None}

        return response.json()


async def backfill_google(org_id: str, access_token: str, refresh_token: str, days: int = 90):
    """
    Backfill Google Drive files.

    Fetches Google Docs, Sheets, and Slides modified in last N days.

    Args:
        org_id: Organization ID
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        days: Days to backfill
    """
    print(f"Starting Google Drive backfill for org: {org_id}")

    modified_after = datetime.utcnow() - timedelta(days=days)
    page_token = None
    files_count = 0

    while True:
        result = await list_drive_files(
            access_token=access_token,
            modified_after=modified_after,
            page_token=page_token
        )

        files = result.get("files", [])
        files_count += len(files)

        for file in files:
            try:
                # Extract content
                content = await get_file_content(
                    access_token=access_token,
                    file_id=file["id"],
                    mime_type=file["mimeType"]
                )

                if content:
                    source_item = normalize_drive_file(file, content, org_id)
                    # TODO: Route to extraction pipeline
                    print(f"  File: {source_item.title[:60]}")

            except Exception as e:
                print(f"  Error processing file {file['name']}: {e}")

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print(f"Processed {files_count} Google Drive files")
    print(f"Google Drive backfill complete for org: {org_id}")


async def handle_google_webhook(request: Request, org_id: str) -> Dict[str, str]:
    """
    Handle Google Drive webhook (push notification).

    Note: Google uses push notifications via Cloud Pub/Sub or
    direct HTTP webhooks. This handler processes change notifications.

    Args:
        request: FastAPI request
        org_id: Organization ID

    Returns:
        Status dict
    """
    # Verify the notification is from Google
    channel_id = request.headers.get("X-Goog-Channel-ID")
    resource_state = request.headers.get("X-Goog-Resource-State")

    if not channel_id:
        raise HTTPException(status_code=401, detail="Invalid notification")

    # Handle sync state
    if resource_state == "sync":
        return {"status": "sync acknowledged"}

    # Store change notification for processing
    body = await request.body()
    payload = json.loads(body) if body else {}

    async with async_session() as session:
        event = EventRaw(
            org_id=org_id,
            source="google",
            event_type=f"drive.{resource_state}",
            payload={
                "channel_id": channel_id,
                "resource_state": resource_state,
                **payload
            }
        )
        session.add(event)
        await session.commit()

    return {"status": "received", "resource_state": resource_state}


async def process_google_events():
    """
    Worker: process unprocessed Google Drive events.

    Fetches changed files and routes to extraction.
    """
    async with async_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(EventRaw)
            .where(EventRaw.source == "google")
            .where(EventRaw.processed_at.is_(None))
            .limit(100)
        )
        events = result.scalars().all()

        for event in events:
            try:
                payload = event.payload
                resource_state = payload.get("resource_state")

                if resource_state == "change":
                    # Fetch updated file and extract
                    # TODO: Get access token from org settings
                    # TODO: Fetch file and process
                    print(f"[Google] Change event for org {event.org_id}")

                event.processed_at = datetime.utcnow()
                await session.commit()

            except Exception as e:
                event.error = str(e)
                event.processed_at = datetime.utcnow()
                await session.commit()
                print(f"[Google] Error processing event {event.id}: {e}")


if __name__ == "__main__":
    import asyncio

    async def main():
        # Test OAuth URL generation
        url = get_oauth_url("test-org")
        print(f"OAuth URL: {url}")

    asyncio.run(main())
