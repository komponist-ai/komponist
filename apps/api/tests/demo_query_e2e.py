"""E2E checks for the public, read-only landing-page demo API."""

import asyncio

import httpx


async def run() -> None:
    async with httpx.AsyncClient(
        base_url="http://localhost:8000",
        timeout=httpx.Timeout(20.0),
    ) as client:
        pilot = await client.post(
            "/demo/query",
            json={"question": "How long does the pilot run?"},
        )
        assert pilot.status_code == 200, pilot.text
        pilot_payload = pilot.json()
        assert pilot_payload["mode"] == "demo", pilot_payload
        assert "4 weeks" in pilot_payload["answer"], pilot_payload
        assert pilot_payload["sources"][0]["title"] == "01-product-strategy.md"

        access = await client.post(
            "/demo/query",
            json={"question": "How can agents access our context?"},
        )
        assert access.status_code == 200, access.text
        access_payload = access.json()
        assert "REST API or MCP" in access_payload["answer"], access_payload
        assert access_payload["sources"][0]["type"] == "Decision"

        invalid = await client.post("/demo/query", json={"question": "no"})
        assert invalid.status_code == 422, invalid.text

    print("Landing demo API E2E: OK")


if __name__ == "__main__":
    asyncio.run(run())
