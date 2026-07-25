"""E2E checks for the public, read-only landing-page demo API."""

import asyncio

import httpx


async def run() -> None:
    async with httpx.AsyncClient(
        base_url="http://localhost:8000",
        timeout=httpx.Timeout(20.0),
    ) as client:
        forum = await client.post(
            "/demo/query",
            json={"question": "How long does the Campus Forum run?"},
        )
        assert forum.status_code == 200, forum.text
        forum_payload = forum.json()
        assert forum_payload["mode"] == "demo", forum_payload
        assert "6 weeks" in forum_payload["answer"], forum_payload
        assert forum_payload["sources"][0]["title"] == "08-campus-forum-plan-v2.md"

        access = await client.post(
            "/demo/query",
            json={"question": "Who can read highly confidential board minutes?"},
        )
        assert access.status_code == 200, access.text
        access_payload = access.json()
        assert "only to board members" in access_payload["answer"], access_payload
        assert access_payload["sources"][0]["type"] == "Constraint"

        invalid = await client.post("/demo/query", json={"question": "no"})
        assert invalid.status_code == 422, invalid.text

    print("Landing demo API E2E: OK")


if __name__ == "__main__":
    asyncio.run(run())
