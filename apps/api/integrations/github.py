"""
GitHub integration.

Webhook handling, backfill, and normalization to SourceItem.
"""

import hmac
import hashlib
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx
from fastapi import Request, HTTPException

import sys
sys.path.append("../../../packages")

from core.models import SourceItem, SourceType
from database import async_session, EventRaw


GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


def verify_github_signature(payload: bytes, signature: str) -> bool:
    """
    Verify GitHub webhook signature.

    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header value

    Returns:
        True if signature is valid
    """
    if not GITHUB_WEBHOOK_SECRET:
        return True  # Dev mode: skip verification

    expected_signature = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


async def handle_github_webhook(request: Request, org_id: str) -> Dict[str, str]:
    """
    Handle GitHub webhook event.

    Verifies signature and stores raw event in events_raw table.

    Args:
        request: FastAPI request
        org_id: Organization ID

    Returns:
        Status dict
    """
    # Get signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    event_type = request.headers.get("X-GitHub-Event", "unknown")

    # Read body
    body = await request.body()

    # Verify signature
    if not verify_github_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON
    import json
    payload = json.loads(body)

    # Store raw event
    async with async_session() as session:
        event = EventRaw(
            org_id=org_id,
            source="github",
            event_type=event_type,
            payload=payload
        )
        session.add(event)
        await session.commit()

    return {"status": "received", "event_type": event_type}


def normalize_pr_merged(payload: Dict[str, Any], org_id: str) -> Optional[SourceItem]:
    """
    Normalize merged PR to SourceItem.

    Args:
        payload: GitHub webhook payload
        org_id: Organization ID

    Returns:
        SourceItem or None if not a merged PR
    """
    action = payload.get("action")
    pr = payload.get("pull_request", {})

    if action != "closed" or not pr.get("merged"):
        return None

    return SourceItem(
        org_id=org_id,
        source=SourceType.GITHUB,
        kind="pr_merged",
        title=pr.get("title", ""),
        body=pr.get("body") or "",
        author=pr.get("user", {}).get("login"),
        url=pr.get("html_url", ""),
        reference=f"PR#{pr.get('number')}",
        source_date=datetime.fromisoformat(pr.get("merged_at").replace("Z", "+00:00"))
    )


def normalize_issue(payload: Dict[str, Any], org_id: str) -> Optional[SourceItem]:
    """
    Normalize closed issue to SourceItem.

    Args:
        payload: GitHub webhook payload
        org_id: Organization ID

    Returns:
        SourceItem or None
    """
    action = payload.get("action")
    issue = payload.get("issue", {})

    if action != "closed":
        return None

    return SourceItem(
        org_id=org_id,
        source=SourceType.GITHUB,
        kind="issue",
        title=issue.get("title", ""),
        body=issue.get("body") or "",
        author=issue.get("user", {}).get("login"),
        url=issue.get("html_url", ""),
        reference=f"Issue#{issue.get('number')}",
        source_date=datetime.fromisoformat(issue.get("closed_at").replace("Z", "+00:00"))
    )


def normalize_adr_file(file_data: Dict[str, Any], org_id: str, repo_name: str) -> SourceItem:
    """
    Normalize ADR file to SourceItem.

    Args:
        file_data: File data from GitHub API
        org_id: Organization ID
        repo_name: Repository name

    Returns:
        SourceItem
    """
    return SourceItem(
        org_id=org_id,
        source=SourceType.GITHUB,
        kind="adr_file",
        title=file_data.get("name", ""),
        body=file_data.get("content", ""),
        author=None,
        url=file_data.get("html_url", ""),
        reference=f"{repo_name}:{file_data.get('path')}",
        source_date=datetime.utcnow()
    )


async def process_github_events():
    """
    Worker: process unprocessed GitHub events.

    Normalizes events to SourceItems and marks as processed.
    """
    async with async_session() as session:
        # Get unprocessed events
        from sqlalchemy import select
        result = await session.execute(
            select(EventRaw)
            .where(EventRaw.source == "github")
            .where(EventRaw.processed_at.is_(None))
            .limit(100)
        )
        events = result.scalars().all()

        for event in events:
            try:
                source_item = None

                if event.event_type == "pull_request":
                    source_item = normalize_pr_merged(event.payload, event.org_id)
                elif event.event_type == "issues":
                    source_item = normalize_issue(event.payload, event.org_id)

                if source_item:
                    # Route to extraction pipeline
                    from pipelines.extract import extract_from_source
                    result = await extract_from_source(source_item)
                    if result["success"]:
                        print(f"[GitHub] Extracted {result['entities_created']} entities from {source_item.kind}")

                    # Check for write-back (PR merged with WorkPack reference)
                    if event.event_type == "pull_request" and event.payload.get("pull_request", {}).get("merged"):
                        from integrations.writeback import handle_pr_merged_writeback
                        await handle_pr_merged_writeback(event.payload["pull_request"], event.org_id)

                # Mark as processed
                event.processed_at = datetime.utcnow()
                await session.commit()

            except Exception as e:
                event.error = str(e)
                event.processed_at = datetime.utcnow()
                await session.commit()
                print(f"[GitHub] Error processing event {event.id}: {e}")


async def backfill_github(org_id: str, owner: str, repo: str, days: int = 90):
    """
    Backfill GitHub data.

    Fetches:
    - Merged PRs
    - Closed issues
    - ADR files (docs/adr/**, **ADR-*.md)

    Args:
        org_id: Organization ID
        owner: GitHub owner
        repo: Repository name
        days: Days to backfill
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise ValueError("GITHUB_TOKEN not set")

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }

    base_url = f"https://api.github.com/repos/{owner}/{repo}"

    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        # Fetch merged PRs
        print(f"Fetching merged PRs from {owner}/{repo}...")
        since = datetime.utcnow().replace(tzinfo=None)
        since_str = (since - timedelta(days=days)).isoformat() + "Z"

        prs_url = f"{base_url}/pulls"
        params = {"state": "closed", "sort": "updated", "direction": "desc"}

        response = await client.get(prs_url, params=params)
        response.raise_for_status()
        prs = response.json()

        merged_prs = [pr for pr in prs if pr.get("merged_at")]
        print(f"Found {len(merged_prs)} merged PRs")

        for pr in merged_prs:
            payload = {"action": "closed", "pull_request": pr}
            source_item = normalize_pr_merged(payload, org_id)
            if source_item:
                # TODO: Route to extraction pipeline
                print(f"  PR#{pr['number']}: {pr['title']}")

        # Fetch closed issues
        print(f"Fetching closed issues from {owner}/{repo}...")
        issues_url = f"{base_url}/issues"
        params = {"state": "closed", "since": since_str}

        response = await client.get(issues_url, params=params)
        response.raise_for_status()
        issues = response.json()

        print(f"Found {len(issues)} closed issues")

        for issue in issues:
            if "pull_request" not in issue:  # Skip PRs
                payload = {"action": "closed", "issue": issue}
                source_item = normalize_issue(payload, org_id)
                if source_item:
                    print(f"  Issue#{issue['number']}: {issue['title']}")

        # Fetch ADR files
        print(f"Fetching ADR files from {owner}/{repo}...")
        search_url = "https://api.github.com/search/code"
        queries = [
            f"repo:{owner}/{repo} path:docs/adr extension:md",
            f"repo:{owner}/{repo} filename:ADR- extension:md"
        ]

        adr_files = []
        for query in queries:
            params = {"q": query}
            response = await client.get(search_url, params=params)
            if response.status_code == 200:
                data = response.json()
                adr_files.extend(data.get("items", []))

        print(f"Found {len(adr_files)} ADR files")

        for file_info in adr_files:
            # Fetch file content
            content_url = file_info.get("url")
            response = await client.get(content_url)
            if response.status_code == 200:
                file_data = response.json()
                import base64
                content = base64.b64decode(file_data.get("content", "")).decode("utf-8")
                file_data["content"] = content

                source_item = normalize_adr_file(file_data, org_id, f"{owner}/{repo}")
                print(f"  ADR: {file_data.get('name')}")

    print(f"GitHub backfill complete for {owner}/{repo}")


if __name__ == "__main__":
    import asyncio
    from datetime import timedelta

    # Example backfill
    async def main():
        await backfill_github(
            org_id="test-org",
            owner="anthropics",
            repo="anthropic-sdk-python",
            days=30
        )

    asyncio.run(main())
