"""E2E check for encrypted OAuth callback persistence without provider traffic."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import delete, select

import main
from database import ConnectedSource, async_session
from integrations import google, notion, slack
from persistence import get_connected_source, list_connected_sources


ORG_ID = "e2e-oauth-persistence"
ERROR_ORG_ID = "e2e-oauth-error"
NOTION_TOKEN = "notion-e2e-access-secret"
SLACK_TOKEN = "slack-e2e-access-secret"
GOOGLE_TOKEN = "google-e2e-access-secret"
GOOGLE_REFRESH = "google-e2e-refresh-secret"


async def cleanup() -> None:
    async with async_session() as session:
        await session.execute(
            delete(ConnectedSource).where(
                ConnectedSource.org_id.in_([ORG_ID, ERROR_ORG_ID])
            )
        )
        await session.commit()


async def fake_notion_exchange(_code: str) -> dict:
    return {
        "access_token": NOTION_TOKEN,
        "workspace_id": "notion-workspace-e2e",
        "workspace_name": "E2E Notion",
        "bot_id": "notion-bot-e2e",
        "owner": {"type": "workspace"},
    }


async def fake_slack_exchange(_code: str) -> dict:
    return {
        "ok": True,
        "access_token": SLACK_TOKEN,
        "team": {"id": "T-E2E", "name": "E2E Slack"},
        "bot_user_id": "B-E2E",
        "scope": "channels:history,channels:read",
    }


async def fake_google_exchange(_code: str) -> dict:
    return {
        "access_token": GOOGLE_TOKEN,
        "refresh_token": GOOGLE_REFRESH,
        "expires_in": 3600,
        "scope": "drive.readonly",
        "token_type": "Bearer",
    }


async def fake_google_reconnect(_code: str) -> dict:
    return {
        "access_token": f"{GOOGLE_TOKEN}-renewed",
        "expires_in": 3600,
        "scope": "drive.readonly",
        "token_type": "Bearer",
    }


async def fake_missing_token(_code: str) -> dict:
    return {"workspace_name": "Must not persist"}


async def run() -> None:
    await cleanup()
    original_notion = notion.exchange_code
    original_slack = slack.exchange_code
    original_google = google.exchange_code

    try:
        notion.exchange_code = fake_notion_exchange
        slack.exchange_code = fake_slack_exchange
        google.exchange_code = fake_google_exchange

        redirects = [
            await main.notion_auth_callback("notion-code", ORG_ID),
            await main.slack_auth_callback("slack-code", ORG_ID),
            await main.google_auth_callback("google-code", ORG_ID),
        ]
        for redirect in redirects:
            location = redirect.headers["location"]
            assert "status=connected" in location, location
            assert "secret" not in location, location

        public_sources = await list_connected_sources(ORG_ID)
        assert {source["type"] for source in public_sources} == {
            "notion", "slack", "google"
        }, public_sources
        assert all("config" not in source for source in public_sources), public_sources

        source_ids = {source["type"]: source["id"] for source in public_sources}
        notion_source = await get_connected_source(
            ORG_ID, source_ids["notion"], include_config=True
        )
        slack_source = await get_connected_source(
            ORG_ID, source_ids["slack"], include_config=True
        )
        google_source = await get_connected_source(
            ORG_ID, source_ids["google"], include_config=True
        )
        assert notion_source["config"]["token"] == NOTION_TOKEN, notion_source
        assert slack_source["config"]["token"] == SLACK_TOKEN, slack_source
        assert google_source["config"]["refresh_token"] == GOOGLE_REFRESH, google_source

        google.exchange_code = fake_google_reconnect
        reconnect = await main.google_auth_callback("google-code-2", ORG_ID)
        assert "status=connected" in reconnect.headers["location"]
        google_source = await get_connected_source(
            ORG_ID, source_ids["google"], include_config=True
        )
        assert google_source["config"]["access_token"].endswith("-renewed")
        assert google_source["config"]["refresh_token"] == GOOGLE_REFRESH

        notion.exchange_code = fake_missing_token
        failed = await main.notion_auth_callback("missing-token", ERROR_ORG_ID)
        assert "status=error" in failed.headers["location"]
        assert await list_connected_sources(ERROR_ORG_ID) == []

        try:
            await main.google_auth_callback("code", "INVALID ORG")
        except HTTPException as error:
            assert error.status_code == 400
        else:
            raise AssertionError("Invalid OAuth state was accepted")

        async with async_session() as session:
            ciphertexts = (
                await session.execute(
                    select(ConnectedSource.config_ciphertext)
                    .where(ConnectedSource.org_id == ORG_ID)
                )
            ).scalars().all()
        combined = " ".join(ciphertexts)
        for secret in (NOTION_TOKEN, SLACK_TOKEN, GOOGLE_TOKEN, GOOGLE_REFRESH):
            assert secret not in combined, combined

        print("OAuth callback persistence E2E: OK")
    finally:
        notion.exchange_code = original_notion
        slack.exchange_code = original_slack
        google.exchange_code = original_google
        await cleanup()


if __name__ == "__main__":
    asyncio.run(run())
