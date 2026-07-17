"""
Slack integration.

Webhook handling, thread assembly, backfill, and normalization to SourceItem.
"""

import hmac
import hashlib
import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict

import httpx
from fastapi import Request, HTTPException

import sys
sys.path.append("../../../packages")

from core.models import SourceItem, SourceType
from database import async_session, EventRaw, SyncState


SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET", "")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI", "http://localhost:8000/auth/slack/callback")

# Watched channels (configured per org)
WATCHED_CHANNELS = os.getenv("SLACK_WATCHED_CHANNELS", "").split(",")


def get_oauth_url(state: str) -> str:
    """
    Generate Slack OAuth URL.

    Args:
        state: State parameter for CSRF protection (should include org_id)

    Returns:
        OAuth authorization URL
    """
    scopes = "channels:history,channels:read,users:read"
    params = {
        "client_id": SLACK_CLIENT_ID,
        "redirect_uri": SLACK_REDIRECT_URI,
        "scope": scopes,
        "state": state,
    }
    from urllib.parse import urlencode
    query = urlencode(params)
    return f"https://slack.com/oauth/v2/authorize?{query}"


async def exchange_code(code: str) -> Dict[str, Any]:
    """
    Exchange authorization code for access token.

    Args:
        code: Authorization code from OAuth callback

    Returns:
        Token response with access_token, team info, etc.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": SLACK_REDIRECT_URI,
            }
        )

        data = response.json()

        if not data.get("ok"):
            raise HTTPException(status_code=400, detail=data.get("error", "OAuth failed"))

        return data


def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """
    Verify Slack request signature.

    Args:
        body: Raw request body
        timestamp: X-Slack-Request-Timestamp header
        signature: X-Slack-Signature header

    Returns:
        True if signature is valid
    """
    if not SLACK_SIGNING_SECRET:
        return os.getenv("KOMPONIST_ALLOW_UNSIGNED_WEBHOOKS", "false").lower() == "true"

    # Check timestamp (prevent replay attacks)
    try:
        request_timestamp = int(timestamp)
    except (TypeError, ValueError):
        return False
    current_timestamp = int(datetime.utcnow().timestamp())
    if abs(current_timestamp - request_timestamp) > 60 * 5:
        return False

    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    expected_signature = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


async def handle_slack_webhook(request: Request, org_id: str) -> Dict[str, Any]:
    """
    Handle Slack webhook event.

    Args:
        request: FastAPI request
        org_id: Organization ID

    Returns:
        Status dict or challenge response
    """
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    body = await request.body()

    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from error

    # Handle URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # Store raw event
    event = payload.get("event", {})
    event_type = event.get("type", "unknown")

    async with async_session() as session:
        raw_event = EventRaw(
            org_id=org_id,
            source="slack",
            event_type=event_type,
            payload=payload
        )
        session.add(raw_event)
        await session.commit()

    return {"status": "received", "event_type": event_type}


async def assemble_thread(channel: str, thread_ts: str, org_id: str) -> Optional[SourceItem]:
    """
    Assemble a complete Slack thread into a SourceItem.

    Args:
        channel: Channel ID
        thread_ts: Thread timestamp
        org_id: Organization ID

    Returns:
        SourceItem with full thread content
    """
    if not SLACK_BOT_TOKEN:
        return None

    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(headers=headers) as client:
        # Fetch thread messages
        response = await client.get(
            "https://slack.com/api/conversations.replies",
            params={"channel": channel, "ts": thread_ts}
        )

        if response.status_code != 200:
            return None

        data = response.json()

        if not data.get("ok"):
            return None

        messages = data.get("messages", [])

        if not messages:
            return None

        # Resolve user names
        user_cache = {}

        async def get_user_name(user_id: str) -> str:
            if user_id in user_cache:
                return user_cache[user_id]

            resp = await client.get(
                "https://slack.com/api/users.info",
                params={"user": user_id}
            )

            if resp.status_code == 200:
                user_data = resp.json()
                if user_data.get("ok"):
                    name = user_data.get("user", {}).get("real_name", user_id)
                    user_cache[user_id] = name
                    return name

            return user_id

        # Build thread body
        thread_lines = []

        for msg in messages:
            user_id = msg.get("user", "unknown")
            text = msg.get("text", "")
            user_name = await get_user_name(user_id)

            thread_lines.append(f"{user_name}: {text}")

        # Top-level message as title
        first_message = messages[0]
        title = first_message.get("text", "")[:100]

        body = "\n\n".join(thread_lines)

        # Permalink
        permalink = f"https://slack.com/archives/{channel}/p{thread_ts.replace('.', '')}"

        # Reference
        reference = f"slack:{channel}/{thread_ts}"

        # Source date
        source_date = datetime.fromtimestamp(float(thread_ts))

        return SourceItem(
            org_id=org_id,
            source=SourceType.SLACK,
            kind="thread",
            title=title,
            body=body,
            author=await get_user_name(first_message.get("user", "")),
            url=permalink,
            reference=reference,
            source_date=source_date
        )


async def process_slack_events():
    """
    Worker: process unprocessed Slack events.

    Assembles threads and routes to extraction pipeline.
    """
    async with async_session() as session:
        from sqlalchemy import select

        # Get unprocessed message events
        result = await session.execute(
            select(EventRaw)
            .where(EventRaw.source == "slack")
            .where(EventRaw.event_type == "message")
            .where(EventRaw.processed_at.is_(None))
            .limit(100)
        )
        events = result.scalars().all()

        # Group by thread
        threads = defaultdict(list)

        for event in events:
            payload = event.payload
            event_data = payload.get("event", {})

            channel = event_data.get("channel")
            thread_ts = event_data.get("thread_ts") or event_data.get("ts")

            # Only process watched channels
            if channel not in WATCHED_CHANNELS:
                event.processed_at = datetime.utcnow()
                await session.commit()
                continue

            threads[(channel, thread_ts)].append(event)

        # Check which threads are ready (no messages in last 30 minutes)
        current_time = datetime.utcnow()

        for (channel, thread_ts), thread_events in threads.items():
            # Get latest message timestamp
            latest_ts = max(
                float(e.payload.get("event", {}).get("ts", 0))
                for e in thread_events
            )
            latest_dt = datetime.fromtimestamp(latest_ts)

            # Wait 30 minutes for thread to be quiet
            if (current_time - latest_dt) < timedelta(minutes=30):
                continue

            # Thread is ready - assemble and extract
            try:
                source_item = await assemble_thread(channel, thread_ts, thread_events[0].org_id)

                if source_item:
                    # TODO: Route to extraction pipeline (Step 6)
                    print(f"[Slack] Assembled thread: {source_item.title}")

                # Mark all events in thread as processed
                for event in thread_events:
                    event.processed_at = datetime.utcnow()
                await session.commit()

            except Exception as e:
                for event in thread_events:
                    event.error = str(e)
                    event.processed_at = datetime.utcnow()
                await session.commit()
                print(f"[Slack] Error assembling thread: {e}")


async def backfill_slack(org_id: str, days: int = 90):
    """
    Backfill Slack history.

    Fetches messages from watched channels for the last N days.

    Args:
        org_id: Organization ID
        days: Days to backfill
    """
    if not SLACK_BOT_TOKEN:
        raise ValueError("SLACK_BOT_TOKEN not set")

    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    # Calculate oldest timestamp
    oldest_dt = datetime.utcnow() - timedelta(days=days)
    oldest_ts = oldest_dt.timestamp()

    async with httpx.AsyncClient(headers=headers) as client:
        for channel in WATCHED_CHANNELS:
            if not channel:
                continue

            print(f"Backfilling Slack channel: {channel}")

            cursor = None
            messages_count = 0

            while True:
                params = {
                    "channel": channel,
                    "oldest": str(oldest_ts),
                    "limit": 100
                }

                if cursor:
                    params["cursor"] = cursor

                response = await client.get(
                    "https://slack.com/api/conversations.history",
                    params=params
                )

                if response.status_code != 200:
                    break

                data = response.json()

                if not data.get("ok"):
                    print(f"  Error: {data.get('error')}")
                    break

                messages = data.get("messages", [])
                messages_count += len(messages)

                # Process messages (group by thread)
                threads = defaultdict(list)

                for msg in messages:
                    thread_ts = msg.get("thread_ts") or msg.get("ts")
                    threads[thread_ts].append(msg)

                # Assemble each thread
                for thread_ts, thread_msgs in threads.items():
                    try:
                        source_item = await assemble_thread(channel, thread_ts, org_id)
                        if source_item:
                            # TODO: Route to extraction pipeline
                            print(f"  Thread: {source_item.title[:60]}")
                    except Exception as e:
                        print(f"  Error assembling thread {thread_ts}: {e}")

                # Pagination
                cursor = data.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

            print(f"  Processed {messages_count} messages")

    print(f"Slack backfill complete for org: {org_id}")


if __name__ == "__main__":
    import asyncio

    async def main():
        await backfill_slack(
            org_id="test-org",
            days=30
        )

    asyncio.run(main())
