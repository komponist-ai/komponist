"""Shared authenticated MCP E2E helpers."""

import hashlib
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from sqlalchemy import delete

from database import OrganizationApiKey, async_session


async def create_test_api_key(org_id: str) -> tuple[str, str]:
    raw_key = f"komponist_sk_e2e_{uuid4().hex}"
    key_id = str(uuid4())
    async with async_session() as session:
        session.add(OrganizationApiKey(
            id=key_id,
            org_id=org_id,
            name="MCP E2E",
            token_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
            token_prefix=f"{raw_key[:18]}…",
            created_by_user_id="mcp-e2e",
        ))
        await session.commit()
    return key_id, raw_key


async def delete_test_api_key(key_id: str) -> None:
    async with async_session() as session:
        await session.execute(
            delete(OrganizationApiKey).where(OrganizationApiKey.id == key_id)
        )
        await session.commit()
