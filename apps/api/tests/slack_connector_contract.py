"""Provider-free contract checks for the organization-scoped Slack connector."""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from integrations.slack import (  # noqa: E402
    fetch_slack_threads,
    get_oauth_url,
    handle_slack_webhook,
    list_channels,
)
from core.models import SourceItem, SourceType  # noqa: E402


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class FakeSlackClient:
    seen_authorizations: list[str] = []

    def __init__(self, *, headers: dict, **_kwargs):
        self.headers = headers
        self.seen_authorizations.append(headers["Authorization"])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url: str, params: dict):
        method = url.rsplit("/", 1)[-1]
        if method == "conversations.list":
            return FakeResponse({
                "ok": True,
                "channels": [{
                    "id": "C123",
                    "name": "board",
                    "is_private": True,
                    "is_member": True,
                }],
                "response_metadata": {"next_cursor": ""},
            })
        if method == "conversations.history":
            assert params["channel"] == "C123"
            return FakeResponse({
                "ok": True,
                "messages": [{"ts": "1784970000.000100"}],
                "response_metadata": {"next_cursor": ""},
            })
        if method == "conversations.replies":
            return FakeResponse({
                "ok": True,
                "messages": [
                    {
                        "ts": "1784970000.000100",
                        "user": "U1",
                        "text": "The board approved the event budget.",
                    },
                    {
                        "ts": "1784970030.000200",
                        "user": "U2",
                        "text": "The limit is EUR 4,800.",
                    },
                ],
            })
        if method == "users.info":
            name = "Amir" if params["user"] == "U1" else "Lea"
            return FakeResponse({
                "ok": True,
                "user": {"real_name": name, "profile": {}},
            })
        raise AssertionError(f"Unexpected Slack method: {method}")


async def check_connector() -> None:
    with patch("integrations.slack.httpx.AsyncClient", FakeSlackClient):
        channels = await list_channels("xoxb-org-token")
        assert channels == [{
            "id": "C123",
            "name": "board",
            "is_private": True,
            "is_member": True,
        }]
        items = await fetch_slack_threads(
            "org-campus",
            access_token="xoxb-org-token",
            channel_ids=["C123"],
            channel_names={"C123": "board"},
            department_id="department-board",
        )

    assert len(items) == 1
    item = items[0]
    assert item.reference == "slack:C123/1784970000.000100"
    assert item.title.startswith("#board —")
    assert "Amir: The board approved" in item.body
    assert "Lea: The limit is EUR 4,800." in item.body
    assert item.department_id == "department-board"
    assert set(FakeSlackClient.seen_authorizations) == {"Bearer xoxb-org-token"}

    query = parse_qs(urlsplit(get_oauth_url("safe-state")).query)
    scopes = set(query["scope"][0].split(","))
    assert {"channels:history", "groups:history", "users:read"} <= scopes
    assert query["state"] == ["safe-state"]
    print("✓ Slack OAuth, channel discovery, thread assembly, and org token scope")


async def check_sync_handoff() -> None:
    import main

    captured: dict = {}

    async def fake_fetch(org_id: str, **kwargs):
        captured.update({"org_id": org_id, **kwargs})
        return [SourceItem(
            org_id=org_id,
            source=SourceType.SLACK,
            kind="thread",
            title="#board — Budget approval",
            body="Amir: The board approved EUR 4,800.",
            url="https://slack.com/archives/C123/p1784970000000100",
            reference="slack:C123/1784970000.000100",
            source_date=datetime(2026, 7, 25),
            department_id=kwargs["department_id"],
        )]

    async def fake_settings(_org_id: str):
        return {"auto_confirm": False, "parallel_batch_size": 5}

    async def fake_extraction(source_item, auto_confirm: bool = False):
        assert source_item.department_id == "department-board"
        assert auto_confirm is False
        return {"entities_created": 2, "relationships_created": 1}

    with (
        patch("integrations.slack.fetch_slack_threads", fake_fetch),
        patch.object(main, "get_org_settings", fake_settings),
        patch.object(main, "run_extraction", fake_extraction),
    ):
        result = await main.sync_slack_source(
            "org-campus",
            {
                "departmentId": "department-board",
                "config": {
                    "token": "xoxb-org-token",
                    "watched_channels": ["C123"],
                    "channel_names": {"C123": "board"},
                },
            },
        )

    assert captured["access_token"] == "xoxb-org-token"
    assert captured["channel_ids"] == ["C123"]
    assert captured["department_id"] == "department-board"
    assert result["items_processed"] == 1
    assert result["entities_created"] == 2
    assert result["relationships_created"] == 1
    print("✓ manual sync hands selected Slack threads to extraction and review")


def slack_request(payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({
        "type": "http",
        "method": "POST",
        "path": "/webhooks/slack",
        "headers": [],
        "query_string": b"",
    }, receive)


async def check_webhook_tenant_binding() -> None:
    async def fake_sources(_org_id: str, include_config: bool = False):
        assert include_config is True
        return [{
            "type": "slack",
            "config": {"team_id": "T-CAMPUS"},
        }]

    with (
        patch("integrations.slack.verify_slack_signature", return_value=True),
        patch("persistence.list_connected_sources", fake_sources),
    ):
        challenge = await handle_slack_webhook(
            slack_request({
                "type": "url_verification",
                "team_id": "T-CAMPUS",
                "challenge": "verified",
            }),
            "org-campus",
        )
        assert challenge == {"challenge": "verified"}

        try:
            await handle_slack_webhook(
                slack_request({
                    "type": "url_verification",
                    "team_id": "T-OTHER",
                    "challenge": "wrong-org",
                }),
                "org-campus",
            )
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError("A signed event from another workspace was accepted")
    print("✓ signed Slack events remain bound to their Komponist organization")


if __name__ == "__main__":
    asyncio.run(check_connector())
    asyncio.run(check_sync_handoff())
    asyncio.run(check_webhook_tenant_binding())
    print("Slack connector contract: OK")
