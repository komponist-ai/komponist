"""Provider-free contract checks for the scoped Notion connector."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages"))

from core.models import SourceItem, SourceType  # noqa: E402
from integrations.notion import (  # noqa: E402
    get_page_content,
    normalize_page,
    search_notion,
    validate_token,
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload


class FakeNotionClient:
    seen_authorizations: list[str] = []

    def __init__(self, *, headers: dict | None = None, **_kwargs):
        self.headers = headers or {}
        if self.headers.get("Authorization"):
            self.seen_authorizations.append(self.headers["Authorization"])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def request(self, method: str, url: str, **kwargs):
        if method == "POST":
            return await self.post(url, kwargs["json"])
        if method == "GET":
            return await self.get(url, kwargs.get("params"))
        raise AssertionError(f"Unexpected Notion method: {method}")

    async def post(self, url: str, json: dict):
        assert url.endswith("/search")
        assert json["filter"] == {"property": "object", "value": "page"}
        return FakeResponse({
            "results": [{"id": "page-1"}],
            "has_more": False,
            "next_cursor": None,
        })

    async def get(self, url: str, params: dict | None = None):
        block_id = url.split("/blocks/", 1)[1].split("/children", 1)[0]
        if block_id == "page-1":
            return FakeResponse({
                "results": [
                    {
                        "id": "heading",
                        "type": "heading_1",
                        "heading_1": {"rich_text": [{"plain_text": "Board decision"}]},
                        "has_children": False,
                    },
                    {
                        "id": "toggle-1",
                        "type": "toggle",
                        "toggle": {"rich_text": [{"plain_text": "Details"}]},
                        "has_children": True,
                    },
                ],
                "has_more": False,
            })
        if block_id == "toggle-1":
            return FakeResponse({
                "results": [{
                    "id": "nested",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{
                            "plain_text": "The board approved a EUR 4,800 event budget."
                        }],
                    },
                    "has_children": False,
                }],
                "has_more": False,
            })
        raise AssertionError(f"Unexpected Notion block: {block_id}")


class RateLimitedNotionClient:
    calls = 0

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def request(self, method: str, url: str, **_kwargs):
        assert method == "GET"
        assert url.endswith("/users/me")
        self.__class__.calls += 1
        if self.calls == 1:
            return FakeResponse({}, 429, {"Retry-After": "1"})
        return FakeResponse({"bot": {"workspace_name": "CampusKollektiv"}})


async def check_provider_contract() -> None:
    with patch("integrations.notion.httpx.AsyncClient", FakeNotionClient):
        pages = await search_notion("ntn_org_token", filter_type="page")
        content = await get_page_content("ntn_org_token", "page-1")

    assert pages["results"] == [{"id": "page-1"}]
    assert "Board decision" in content
    assert "Details" in content
    assert "EUR 4,800 event budget" in content
    assert set(FakeNotionClient.seen_authorizations) == {"Bearer ntn_org_token"}

    RateLimitedNotionClient.calls = 0
    with (
        patch("integrations.notion.httpx.AsyncClient", RateLimitedNotionClient),
        patch("integrations.notion.asyncio.sleep") as sleep,
    ):
        workspace = await validate_token("ntn_org_token")
    assert workspace["bot"]["workspace_name"] == "CampusKollektiv"
    assert RateLimitedNotionClient.calls == 2
    sleep.assert_awaited_once_with(1.0)

    item = normalize_page(
        {
            "id": "page-1",
            "url": "https://notion.so/page-1",
            "last_edited_time": "2026-07-25T11:00:00.000Z",
            "properties": {
                "Meeting topic": {
                    "type": "title",
                    "title": [{"plain_text": "July board meeting"}],
                },
            },
        },
        content,
        "org-campus",
    )
    assert item.title == "July board meeting"
    assert item.reference == "notion:page1"
    print("✓ Notion discovery, nested content, title fields, rate-limit recovery, and token scope")


async def check_sync_handoff() -> None:
    import main

    async def fake_search(**_kwargs):
        return {
            "results": [
                {
                    "id": "page-ok",
                    "url": "https://notion.so/page-ok",
                    "last_edited_time": "2026-07-25T11:00:00.000Z",
                    "properties": {
                        "Topic": {
                            "type": "title",
                            "title": [{"plain_text": "Board budget"}],
                        },
                    },
                },
                {"id": "page-revoked", "properties": {}},
            ],
            "has_more": False,
        }

    async def fake_content(_token: str, page_id: str):
        if page_id == "page-revoked":
            raise ValueError("page is no longer shared")
        return "The board approved the annual event budget of EUR 4,800. This decision applies immediately."

    async def fake_settings(_org_id: str):
        return {"auto_confirm": False, "parallel_batch_size": 5}

    async def fake_extraction(source_item: SourceItem, auto_confirm: bool = False):
        assert source_item.org_id == "org-campus"
        assert source_item.department_id == "department-board"
        assert auto_confirm is False
        return {"entities_created": 2, "relationships_created": 1}

    with (
        patch("integrations.notion.search_notion", fake_search),
        patch("integrations.notion.get_page_content", fake_content),
        patch.object(main, "get_org_settings", fake_settings),
        patch.object(main, "run_extraction", fake_extraction),
    ):
        result = await main.sync_notion_source(
            "org-campus",
            {
                "departmentId": "department-board",
                "config": {"token": "ntn_org_token"},
            },
        )

    assert result["status"] == "partial"
    assert result["items_processed"] == 1
    assert result["items_failed"] == 1
    assert result["entities_created"] == 2
    assert result["relationships_created"] == 1
    assert result["failed_pages"][0]["page_id"] == "page-revoked"
    print("✓ Notion sync preserves department scope, hands pages to review, and reports partial failures")


async def check_connection_persistence() -> None:
    import main

    captured: dict = {}

    async def fake_authorize(_request, org_id: str, manage: bool = False):
        assert org_id == "org-campus"
        assert manage is True
        return {"id": "owner"}

    async def fake_scope(org_id: str, _user, department_id: str | None):
        assert org_id == "org-campus"
        assert department_id == "department-board"
        return department_id

    async def fake_validate(token: str):
        assert token == "ntn_org_token"
        return {"bot": {"workspace_name": "CampusKollektiv"}}

    async def fake_upsert(**kwargs):
        captured.update(kwargs)
        return {"id": "source-notion"}

    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/auth/notion/token",
        "headers": [],
        "query_string": b"",
    })

    with (
        patch.object(main, "_authorized_org_user", fake_authorize),
        patch.object(main, "_validate_department_scope", fake_scope),
        patch("integrations.notion.validate_token", fake_validate),
        patch.object(main, "upsert_single_source_type", fake_upsert),
    ):
        result = await main.notion_token_connect(
            main.NotionTokenRequest(token="ntn_org_token"),
            request,
            org_id="org-campus",
            department_id="department-board",
        )

    assert result["status"] == "connected"
    assert captured == {
        "org_id": "org-campus",
        "source_type": "notion",
        "name": "CampusKollektiv",
        "config": {"token": "ntn_org_token"},
        "department_id": "department-board",
    }

    with (
        patch.object(main, "_authorized_org_user", fake_authorize),
        patch.object(main, "_validate_department_scope", fake_scope),
    ):
        try:
            await main.notion_token_connect(
                main.NotionTokenRequest(token="invalid-token"),
                request,
                org_id="org-campus",
                department_id="department-board",
            )
        except HTTPException as error:
            assert error.status_code == 400
        else:
            raise AssertionError("An invalid Notion token prefix was accepted")
    print("✓ internal token connection is admin-scoped and persists its department safely")


if __name__ == "__main__":
    asyncio.run(check_provider_contract())
    asyncio.run(check_connection_persistence())
    asyncio.run(check_sync_handoff())
    print("Notion connector contract: OK")
