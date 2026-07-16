"""Restart-aware E2E check for Postgres-backed settings and sources.

Run in three phases around an API container restart:
    python tests/persistence_e2e.py seed
    # restart the API container
    python tests/persistence_e2e.py verify
    python tests/persistence_e2e.py cleanup
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import delete, select

from database import ConnectedSource, OrgSetting, async_session
from persistence import get_connected_source


ORG_ID = "e2e-persistence"
OTHER_ORG_ID = "e2e-persistence-other"
TOKEN = "e2e-secret-token-must-never-be-plaintext"


async def cleanup() -> None:
    async with async_session() as session:
        await session.execute(delete(ConnectedSource).where(ConnectedSource.org_id == ORG_ID))
        await session.execute(delete(OrgSetting).where(OrgSetting.org_id == ORG_ID))
        await session.commit()


async def seed() -> None:
    await cleanup()
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        settings = await client.put(
            "/settings",
            params={"org_id": ORG_ID},
            json={"auto_confirm": True, "parallel_batch_size": 7},
        )
        assert settings.status_code == 200, settings.text
        assert settings.json()["auto_confirm"] is True, settings.text
        assert settings.json()["parallel_batch_size"] == 7, settings.text

        source = await client.post(
            "/sources",
            params={
                "org_id": ORG_ID,
                "source_type": "local",
                "name": "Persistent E2E Documents",
            },
            json={"path": "/data/docs/e2e", "token": TOKEN},
        )
        assert source.status_code == 200, source.text
        source_payload = source.json()
        assert "config" not in source_payload, source_payload

        listed = await client.get("/sources", params={"org_id": ORG_ID})
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1, listed.text
        assert "config" not in listed.json()["sources"][0], listed.text

        isolated = await client.get("/sources", params={"org_id": OTHER_ORG_ID})
        assert isolated.status_code == 200, isolated.text
        assert isolated.json() == {"sources": [], "total": 0}, isolated.text

    async with async_session() as session:
        ciphertext = (
            await session.execute(
                select(ConnectedSource.config_ciphertext)
                .where(ConnectedSource.org_id == ORG_ID)
            )
        ).scalar_one()
    assert TOKEN not in ciphertext, ciphertext
    assert "/data/docs/e2e" not in ciphertext, ciphertext
    print("persistence E2E seed: OK")


async def verify() -> None:
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        settings = await client.get("/settings", params={"org_id": ORG_ID})
        assert settings.status_code == 200, settings.text
        assert settings.json()["auto_confirm"] is True, settings.text
        assert settings.json()["parallel_batch_size"] == 7, settings.text

        listed = await client.get("/sources", params={"org_id": ORG_ID})
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 1, listed.text
        source_id = listed.json()["sources"][0]["id"]

    private_source = await get_connected_source(
        ORG_ID, source_id, include_config=True
    )
    assert private_source is not None
    assert private_source["config"] == {
        "path": "/data/docs/e2e",
        "token": TOKEN,
    }, private_source
    print("persistence E2E restart verification: OK")


async def run() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "verify", "cleanup"}:
        raise SystemExit("usage: persistence_e2e.py seed|verify|cleanup")
    phase = sys.argv[1]
    if phase == "seed":
        await seed()
    elif phase == "verify":
        await verify()
    else:
        await cleanup()
        print("persistence E2E cleanup: OK")


if __name__ == "__main__":
    asyncio.run(run())
