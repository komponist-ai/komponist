"""Postgres persistence for organization settings and connected sources."""

import base64
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select

from database import ConnectedSource, OrgSetting, async_session


def _cipher() -> Fernet:
    secret = os.getenv("KOMPONIST_SECRET_KEY")
    if not secret or len(secret) < 16:
        raise RuntimeError(
            "KOMPONIST_SECRET_KEY must be configured with at least 16 characters "
            "before connector credentials can be persisted"
        )
    digest = hashlib.sha256(f"komponist-config-v1:{secret}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_config(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _cipher().encrypt(payload).decode("ascii")


def _decrypt_config(ciphertext: str) -> dict[str, Any]:
    try:
        payload = _cipher().decrypt(ciphertext.encode("ascii"))
        value = json.loads(payload)
    except (InvalidToken, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Stored connector configuration could not be decrypted") from error
    if not isinstance(value, dict):
        raise RuntimeError("Stored connector configuration is not an object")
    return value


def _source_dict(source: ConnectedSource, include_config: bool = False) -> dict[str, Any]:
    result = {
        "id": source.id,
        "type": source.source_type,
        "name": source.name,
        "status": source.status,
        "lastSync": source.last_sync.isoformat() if source.last_sync else None,
        "itemCount": source.item_count,
        "created_at": source.created_at.isoformat(),
    }
    if include_config:
        result["config"] = _decrypt_config(source.config_ciphertext)
    return result


async def load_org_settings(org_id: str) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        row = await session.get(OrgSetting, org_id)
        if not row:
            return None
        return {
            "auto_confirm": row.auto_confirm,
            "parallel_batch_size": row.parallel_batch_size,
        }


async def save_org_settings(
    org_id: str,
    auto_confirm: bool,
    parallel_batch_size: int,
) -> dict[str, Any]:
    async with async_session() as session:
        row = await session.get(OrgSetting, org_id)
        if row is None:
            row = OrgSetting(org_id=org_id)
            session.add(row)
        row.auto_confirm = auto_confirm
        row.parallel_batch_size = parallel_batch_size
        row.updated_at = datetime.utcnow()
        await session.commit()
        return {
            "auto_confirm": row.auto_confirm,
            "parallel_batch_size": row.parallel_batch_size,
        }


async def list_connected_sources(
    org_id: str,
    include_config: bool = False,
) -> list[dict[str, Any]]:
    async with async_session() as session:
        rows = (
            await session.execute(
                select(ConnectedSource)
                .where(ConnectedSource.org_id == org_id)
                .order_by(ConnectedSource.created_at.asc())
            )
        ).scalars().all()
        return [_source_dict(row, include_config=include_config) for row in rows]


async def get_connected_source(
    org_id: str,
    source_id: str,
    include_config: bool = False,
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        row = await session.get(ConnectedSource, source_id)
        if row is None or row.org_id != org_id:
            return None
        return _source_dict(row, include_config=include_config)


async def create_connected_source(
    org_id: str,
    source_type: str,
    name: str,
    config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    row = ConnectedSource(
        id=str(uuid4()),
        org_id=org_id,
        source_type=source_type,
        name=name,
        status="connected",
        item_count=0,
        config_ciphertext=_encrypt_config(config or {}),
    )
    async with async_session() as session:
        session.add(row)
        await session.commit()
        return _source_dict(row)


async def upsert_single_source_type(
    org_id: str,
    source_type: str,
    name: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    async with async_session() as session:
        row = (
            await session.execute(
                select(ConnectedSource)
                .where(
                    ConnectedSource.org_id == org_id,
                    ConnectedSource.source_type == source_type,
                )
                .order_by(ConnectedSource.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            row = ConnectedSource(
                id=str(uuid4()), org_id=org_id, source_type=source_type,
                name=name, config_ciphertext=_encrypt_config(config),
            )
            session.add(row)
        else:
            row.name = name
            row.status = "connected"
            row.config_ciphertext = _encrypt_config(config)
            row.updated_at = datetime.utcnow()
        await session.commit()
        return _source_dict(row)


async def update_connected_source(
    org_id: str,
    source_id: str,
    *,
    status: Optional[str] = None,
    last_sync: Optional[datetime] = None,
    item_count: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        row = await session.get(ConnectedSource, source_id)
        if row is None or row.org_id != org_id:
            return None
        if status is not None:
            row.status = status
        if last_sync is not None:
            row.last_sync = last_sync
        if item_count is not None:
            row.item_count = item_count
        row.updated_at = datetime.utcnow()
        await session.commit()
        return _source_dict(row)


async def delete_connected_source(org_id: str, source_id: str) -> bool:
    async with async_session() as session:
        result = await session.execute(
            delete(ConnectedSource).where(
                ConnectedSource.id == source_id,
                ConnectedSource.org_id == org_id,
            )
        )
        await session.commit()
        return bool(result.rowcount)
