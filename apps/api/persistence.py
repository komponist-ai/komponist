"""Postgres persistence for organization settings and connected sources."""

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select

from database import (
    ChatConversation,
    ChatMessageRecord,
    ConnectedSource,
    OrganizationApiKey,
    OrgSetting,
    async_session,
)


def _chat_message_dict(row: ChatMessageRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "role": row.role,
        "content": row.content,
        "sources": row.sources or [],
        "created_at": f"{row.created_at.isoformat()}Z",
    }


def _chat_conversation_dict(
    row: ChatConversation,
    messages: Optional[list[ChatMessageRecord]] = None,
) -> dict[str, Any]:
    messages = messages or []
    last_message = messages[-1].content if messages else ""
    preview = " ".join(last_message.split())
    return {
        "id": row.id,
        "title": row.title,
        "created_at": f"{row.created_at.isoformat()}Z",
        "updated_at": f"{row.updated_at.isoformat()}Z",
        "message_count": len(messages),
        "preview": preview[:140],
    }


async def list_chat_conversations(
    org_id: str, user_id: str
) -> list[dict[str, Any]]:
    """List a user's conversations, most recently active first."""
    async with async_session() as session:
        conversations = (
            await session.execute(
                select(ChatConversation)
                .where(
                    ChatConversation.org_id == org_id,
                    ChatConversation.user_id == user_id,
                )
                .order_by(ChatConversation.updated_at.desc())
            )
        ).scalars().all()
        if not conversations:
            return []

        conversation_ids = [row.id for row in conversations]
        messages = (
            await session.execute(
                select(ChatMessageRecord)
                .where(ChatMessageRecord.conversation_id.in_(conversation_ids))
                .order_by(ChatMessageRecord.created_at.asc())
            )
        ).scalars().all()
        grouped: dict[str, list[ChatMessageRecord]] = {
            conversation_id: [] for conversation_id in conversation_ids
        }
        for message in messages:
            grouped[message.conversation_id].append(message)
        return [
            _chat_conversation_dict(row, grouped[row.id]) for row in conversations
        ]


async def get_chat_conversation(
    org_id: str, user_id: str, conversation_id: str
) -> Optional[dict[str, Any]]:
    """Load one scoped conversation with every persisted message."""
    async with async_session() as session:
        conversation = (
            await session.execute(
                select(ChatConversation).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.org_id == org_id,
                    ChatConversation.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            return None
        messages = (
            await session.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.conversation_id == conversation_id,
                    ChatMessageRecord.org_id == org_id,
                )
                .order_by(ChatMessageRecord.created_at.asc())
            )
        ).scalars().all()
        return {
            "conversation": _chat_conversation_dict(conversation, messages),
            "messages": [_chat_message_dict(message) for message in messages],
        }


async def create_chat_conversation(
    org_id: str, user_id: str, title: str
) -> dict[str, Any]:
    now = datetime.utcnow()
    conversation = ChatConversation(
        id=str(uuid4()),
        org_id=org_id,
        user_id=user_id,
        title=title,
        created_at=now,
        updated_at=now,
    )
    async with async_session() as session:
        session.add(conversation)
        await session.commit()
        return _chat_conversation_dict(conversation)


async def rename_chat_conversation(
    org_id: str, user_id: str, conversation_id: str, title: str
) -> Optional[dict[str, Any]]:
    async with async_session() as session:
        conversation = (
            await session.execute(
                select(ChatConversation).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.org_id == org_id,
                    ChatConversation.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            return None
        conversation.title = title
        conversation.updated_at = datetime.utcnow()
        await session.commit()
        messages = (
            await session.execute(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.conversation_id == conversation_id,
                    ChatMessageRecord.org_id == org_id,
                )
                .order_by(ChatMessageRecord.created_at.asc())
            )
        ).scalars().all()
        return _chat_conversation_dict(conversation, messages)


async def delete_chat_conversation(
    org_id: str, user_id: str, conversation_id: str
) -> bool:
    async with async_session() as session:
        conversation = (
            await session.execute(
                select(ChatConversation).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.org_id == org_id,
                    ChatConversation.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            return False
        await session.execute(
            delete(ChatMessageRecord).where(
                ChatMessageRecord.conversation_id == conversation_id,
                ChatMessageRecord.org_id == org_id,
            )
        )
        await session.delete(conversation)
        await session.commit()
        return True


async def append_chat_message(
    org_id: str,
    user_id: str,
    conversation_id: str,
    role: str,
    content: str,
    sources: Optional[list[dict[str, Any]]] = None,
) -> Optional[dict[str, Any]]:
    """Append a turn only when the conversation belongs to this user and org."""
    async with async_session() as session:
        conversation = (
            await session.execute(
                select(ChatConversation).where(
                    ChatConversation.id == conversation_id,
                    ChatConversation.org_id == org_id,
                    ChatConversation.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            return None
        now = datetime.utcnow()
        message = ChatMessageRecord(
            id=str(uuid4()),
            conversation_id=conversation_id,
            org_id=org_id,
            role=role,
            content=content,
            sources=sources or None,
            created_at=now,
        )
        conversation.updated_at = now
        session.add(message)
        await session.commit()
        return _chat_message_dict(message)


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


def _api_key_dict(row: OrganizationApiKey) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.token_prefix,
        "created_at": row.created_at.isoformat(),
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


async def list_api_keys(org_id: str) -> list[dict[str, Any]]:
    async with async_session() as session:
        rows = (
            await session.execute(
                select(OrganizationApiKey)
                .where(OrganizationApiKey.org_id == org_id)
                .order_by(OrganizationApiKey.created_at.desc())
            )
        ).scalars().all()
        return [_api_key_dict(row) for row in rows]


async def create_api_key(
    org_id: str, name: str, created_by_user_id: str
) -> dict[str, Any]:
    raw_key = f"komponist_sk_{secrets.token_urlsafe(32)}"
    row = OrganizationApiKey(
        id=str(uuid4()),
        org_id=org_id,
        name=name,
        token_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
        token_prefix=f"{raw_key[:18]}…",
        created_by_user_id=created_by_user_id,
    )
    async with async_session() as session:
        session.add(row)
        await session.commit()
        return {**_api_key_dict(row), "key": raw_key}


async def revoke_api_key(org_id: str, key_id: str) -> bool:
    async with async_session() as session:
        row = await session.get(OrganizationApiKey, key_id)
        if row is None or row.org_id != org_id:
            return False
        if row.revoked_at is None:
            row.revoked_at = datetime.utcnow()
            await session.commit()
        return True


async def authenticate_api_key(raw_key: str) -> Optional[str]:
    """Return the organization for an active API key and record its use."""
    if not raw_key.startswith("komponist_sk_") or len(raw_key) > 200:
        return None
    token_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    async with async_session() as session:
        row = (
            await session.execute(
                select(OrganizationApiKey).where(
                    OrganizationApiKey.token_hash == token_hash,
                    OrganizationApiKey.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        row.last_used_at = datetime.utcnow()
        await session.commit()
        return row.org_id


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
    preserve_existing_config: bool = False,
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
            if preserve_existing_config:
                existing_config = _decrypt_config(row.config_ciphertext)
                config = {**existing_config, **config}
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
